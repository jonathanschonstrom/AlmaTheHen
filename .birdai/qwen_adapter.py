from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class QwenAdapterError(RuntimeError):
    pass


QWEN_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["diagnosis", "strategy", "summary"],
    "properties": {
        "diagnosis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "observed_failure",
                "likely_location",
                "hypothesis",
                "minimal_test",
            ],
            "properties": {
                "observed_failure": {"type": "string"},
                "likely_location": {"type": "string"},
                "hypothesis": {"type": "string"},
                "minimal_test": {"type": "string"},
            },
        },
        "strategy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "operation", "outcomes"],
            "properties": {
                "id": {"type": "string"},
                "operation": {"type": "string"},
                "outcomes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


def _sanitized_qwen_env() -> dict[str, str]:
    """
    Remove GitHub Actions transport credentials and runner-control metadata
    before starting Qwen.

    Provider/model credentials are intentionally preserved because Qwen Code
    may require them for inference.
    """
    blocked_prefixes = (
        "GITHUB_",
        "GH_",
        "ACTIONS_",
        "RUNNER_",
        "BIRDAI_",
    )

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(blocked_prefixes)
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["QWEN_CODE_SAFE_MODE"] = "true"
    return env


@dataclass(frozen=True)
class ProcessRecord:
    command: str
    version: str
    pid: int | None
    start_utc: str | None
    exit_code: int | None
    elapsed_seconds: float
    timed_out: bool
    forced_termination: bool
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class QwenExecution:
    process: ProcessRecord
    contract: dict[str, Any] | None
    raw_result: str | None


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _decode_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    return None


def _extract_qwen_result(
    stdout: str,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        raw = stdout.strip() or None
        return raw, _decode_json_object(stdout), None

    result_text: str | None = None
    model: str | None = None

    if isinstance(payload, list):
        for item in payload:
            if (
                isinstance(item, dict)
                and item.get("type") == "system"
                and item.get("subtype") in {"session_start", "init"}
                and isinstance(item.get("model"), str)
            ):
                model = item["model"]
                break

        for item in reversed(payload):
            if isinstance(item, dict) and item.get("type") == "result":
                structured = item.get("structured_result")
                if isinstance(structured, dict):
                    return json.dumps(structured), structured, model

                candidate = item.get("result")
                if isinstance(candidate, str):
                    result_text = candidate
                    break
                if isinstance(candidate, dict):
                    return json.dumps(candidate), candidate, model

    if result_text is None and isinstance(payload, dict):
        structured = payload.get("structured_result")
        if isinstance(structured, dict):
            return json.dumps(structured), structured, model

        candidate = payload.get("result")
        if isinstance(candidate, str):
            result_text = candidate
        elif isinstance(candidate, dict):
            return json.dumps(candidate), candidate, model

        candidate_model = payload.get("model")
        if isinstance(candidate_model, str):
            model = candidate_model

    if result_text is None:
        result_text = stdout.strip() or None

    contract = _decode_json_object(result_text or "")
    return result_text, contract, model


def _terminate_tree(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return False

    forced = True

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            forced = False

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)

    return forced



def _windows_qwen_standalone_command(
    executable: str,
    args: list[str],
) -> list[str] | None:
    """
    Resolve Qwen Code's Windows standalone launcher directly to Node.

    Qwen's standalone installer uses nested .cmd launchers whose `%*`
    forwarding can strip quotes from JSON-valued arguments such as
    `--json-schema`.  Launching node.exe + lib/cli-entry.js directly preserves
    argv boundaries and avoids cmd.exe quoting entirely.

    Supported observed layouts include:

      <root>\\bin\\qwen.cmd
        -> <root>\\qwen-code\\bin\\qwen.cmd
        -> <root>\\qwen-code\\node\\node.exe
           <root>\\qwen-code\\lib\\cli-entry.js

    and direct use of the inner qwen.cmd.

    Candidate runtimes are derived only from the configured executable path.
    An unrelated .cmd/.bat must never be redirected to a globally installed
    Qwen runtime through LOCALAPPDATA or another ambient location.
    """
    if os.name != "nt":
        return None

    path = Path(executable)

    if path.suffix.lower() not in {".cmd", ".bat"}:
        return None

    roots: list[Path] = [
        path.parent.parent,
        path.parent.parent / "qwen-code",
    ]

    seen: set[str] = set()

    for root in roots:
        key = os.path.normcase(os.path.abspath(str(root)))
        if key in seen:
            continue
        seen.add(key)

        node = root / "node" / "node.exe"
        cli = root / "lib" / "cli-entry.js"

        if node.is_file() and cli.is_file():
            return [
                str(node),
                str(cli),
                *args,
            ]

    return None


def _build_command(executable: str, args: list[str]) -> list[str]:
    """
    Build argv without losing structured JSON arguments.

    On Windows, Qwen Code's standalone .cmd wrappers forward `%*` through
    multiple batch layers.  That corrupts JSON quoting for `--json-schema`.
    When the standalone runtime can be identified, bypass all batch launchers
    and execute node.exe + lib/cli-entry.js directly.

    Generic .cmd/.bat commands still fall back to cmd.exe.
    Python entrypoints are launched with the current interpreter.
    """
    suffix = os.path.splitext(executable)[1].lower()

    if os.name == "nt":
        if suffix in {".cmd", ".bat"}:
            standalone = _windows_qwen_standalone_command(
                executable,
                args,
            )
            if standalone is not None:
                return standalone

            cmd = shutil.which("cmd.exe") or os.environ.get("COMSPEC")
            if not cmd:
                raise QwenAdapterError(
                    "Cannot launch Windows command script without "
                    f"cmd.exe: {executable}"
                )

            inner = subprocess.list2cmdline(
                [executable, *args]
            )
            return [
                cmd,
                "/d",
                "/s",
                "/c",
                inner,
            ]

        if suffix in {".py", ".pyw"}:
            return [
                sys.executable,
                executable,
                *args,
            ]

    return [
        executable,
        *args,
    ]

def _version(executable: str) -> str:
    command = _build_command(executable, ["--version"])
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    value = (result.stdout or result.stderr).strip()
    return value or "unknown"


def _build_prompt(task: dict[str, Any]) -> str:
    goal = task["goal"]
    allowed = task["allowed_files"]

    contract = {
        "diagnosis": {
            "observed_failure": "string",
            "likely_location": "string",
            "hypothesis": "string",
            "minimal_test": "string",
        },
        "strategy": {
            "id": "short stable identifier",
            "operation": "what you changed or inspected",
            "outcomes": ["concrete outcome"],
        },
        "summary": "short final summary",
    }

    allowed_text = "\n".join(f"- {path}" for path in allowed) or "- NO FILE CHANGES ARE ALLOWED"

    return f"""You are the bounded implementation executor for BirdAI execution slice {goal['slice_id']}.

Objective:
{goal['objective']}

Pass definition:
{goal['pass_definition']}

Issue:
{goal['issue']}

Exact repository-relative files you are allowed to modify:
{allowed_text}

Hard execution rules:
1. Work only inside the current repository workspace.
2. Do not modify any file outside the exact allowed list.
3. If the allowed list is empty, perform diagnosis only and make no file changes.
4. Do not run git commit, git push, git checkout, git switch, git reset, git clean, or GitHub commands.
5. Do not change tests, expected behavior, policy, governance, or unrelated code unless the exact file is explicitly allowed and the objective requires it.
6. Do not use the shell to run validation. The coordinator runs the authoritative validation after you finish.
7. Prefer the smallest change that can satisfy the stated pass definition.
8. If authority, scope, or evidence is insufficient, stop without expanding scope.
9. The coordinator supplied --json-schema. You MUST finish by calling the structured_output tool exactly once with an object that matches the required schema.
10. Do not merely print the terminal object as prose or markdown, and do not continue working after structured_output is accepted.

Required terminal JSON object shape:
{json.dumps(contract, indent=2)}

The coordinator independently verifies git scope and validation results. Your prose cannot override those checks.
"""


class QwenAdapter:
    def __init__(
        self,
        *,
        command: str = "qwen",
        model: str | None = None,
        wall_time_seconds: int = 900,
        max_session_turns: int = 30,
        max_tool_calls: int = 50,
    ) -> None:
        if wall_time_seconds < 1:
            raise ValueError("wall_time_seconds must be >= 1")
        if max_session_turns < 1:
            raise ValueError("max_session_turns must be >= 1")
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be >= 1")

        resolved = shutil.which(command)
        if resolved is None and Path(command).exists():
            resolved = str(Path(command).resolve())

        if resolved is None:
            raise QwenAdapterError(f"Qwen executable not found: {command}")

        self.command = resolved
        self.model = model
        self.wall_time_seconds = wall_time_seconds
        self.max_session_turns = max_session_turns
        self.max_tool_calls = max_tool_calls

    def execute(
        self,
        *,
        task: dict[str, Any],
        cwd: Path,
        output_dir: Path,
    ) -> QwenExecution:
        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "qwen.stdout.json"
        stderr_path = output_dir / "qwen.stderr.txt"

        prompt = _build_prompt(task)

        qwen_args = [
            "--prompt",
            prompt,
            "--safe-mode",
            "--json-schema",
            json.dumps(QWEN_RESULT_SCHEMA, separators=(",", ":")),
            "--output-format",
            "json",
            "--approval-mode",
            "auto-edit",
            "--max-session-turns",
            str(self.max_session_turns),
            "--max-wall-time",
            f"{self.wall_time_seconds}s",
            "--max-tool-calls",
            str(self.max_tool_calls),
        ]

        if self.model:
            qwen_args.extend(["--model", self.model])

        command = _build_command(self.command, qwen_args)

        env = _sanitized_qwen_env()

        creationflags = 0
        popen_kwargs: dict[str, Any] = {}

        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        start_utc = _utc_now()
        started = time.monotonic()

        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            **popen_kwargs,
        )

        timed_out = False
        forced_termination = False

        try:
            stdout, stderr = process.communicate(timeout=self.wall_time_seconds + 15)
        except subprocess.TimeoutExpired:
            timed_out = True
            forced_termination = _terminate_tree(process)
            stdout, stderr = process.communicate()

        elapsed = time.monotonic() - started

        stdout_path.write_text(stdout or "", encoding="utf-8")
        stderr_path.write_text(stderr or "", encoding="utf-8")

        raw_result, contract, reported_model = _extract_qwen_result(stdout or "")
        provenance = reported_model or self.model or "configured-default"

        record = ProcessRecord(
            command=" ".join(_build_command(self.command, ["--prompt", "<bounded-task>", *qwen_args[2:]])),
            version=f"{_version(self.command)}; model={provenance}",
            pid=process.pid,
            start_utc=start_utc,
            exit_code=process.returncode,
            elapsed_seconds=round(elapsed, 6),
            timed_out=timed_out,
            forced_termination=forced_termination,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

        return QwenExecution(
            process=record,
            contract=contract,
            raw_result=raw_result,
        )
