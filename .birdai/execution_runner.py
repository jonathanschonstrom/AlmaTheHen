from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qwen_adapter import ProcessRecord, QwenAdapter, QwenAdapterError


class ExecutionError(RuntimeError):
    pass


REQUIRED_RESULT_KEYS = {
    "slice_id",
    "status",
    "base_commit",
    "elapsed_seconds",
    "diagnosis",
    "attempts",
    "runs",
    "cleanup",
    "changed_files",
    "pass_evidence",
    "stop_reason",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise ExecutionError(
            f"git {' '.join(args)} failed ({result.returncode})\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def normalize_repo_path(value: str) -> str:
    if not value or value.strip() != value:
        raise ExecutionError(f"Invalid repository-relative path: {value!r}")

    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ExecutionError(f"Path must be repository-relative with forward slashes: {value}")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ExecutionError(f"Path contains unsafe component: {value}")
    if parts[0].lower() == ".git":
        raise ExecutionError(f"Git metadata is never an allowed execution target: {value}")

    return "/".join(parts)


def validate_task(task: dict[str, Any]) -> None:
    for key in ("goal", "allowed_files", "validation", "max_attempts", "stop_conditions", "result_schema"):
        if key not in task:
            raise ExecutionError(f"AI_TASK missing field: {key}")

    backend = task.get("execution_backend", "qwen")
    if backend not in {"qwen", "lmstudio"}:
        raise ExecutionError(
            "AI_TASK execution_backend must be qwen or lmstudio"
        )

    goal = task["goal"]
    for key in ("slice_id", "issue", "objective", "pass_definition"):
        if not isinstance(goal.get(key), str) or not goal[key].strip():
            raise ExecutionError(f"AI_TASK goal.{key} must be a non-empty string")

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", goal["slice_id"]):
        raise ExecutionError(f"Invalid slice_id: {goal['slice_id']}")

    allowed = task["allowed_files"]
    if not isinstance(allowed, list):
        raise ExecutionError("AI_TASK allowed_files must be an array")

    normalized = [normalize_repo_path(str(path)) for path in allowed]
    if len(normalized) != len(set(normalized)):
        raise ExecutionError("AI_TASK allowed_files contains duplicates")

    context = task.get("context_files", [])
    if context is None:
        context = []
    if not isinstance(context, list):
        raise ExecutionError("AI_TASK context_files must be an array")

    normalized_context = [
        normalize_repo_path(str(path))
        for path in context
    ]
    if len(normalized_context) != len(set(normalized_context)):
        raise ExecutionError("AI_TASK context_files contains duplicates")

    overlap = sorted(set(normalized).intersection(normalized_context))
    if overlap:
        raise ExecutionError(
            "AI_TASK context_files are read-only and cannot overlap allowed_files: "
            + ", ".join(overlap)
        )


    context_ranges = task.get("context_ranges", [])
    if context_ranges is None:
        context_ranges = []
    if not isinstance(context_ranges, list):
        raise ExecutionError("AI_TASK context_ranges must be an array")

    seen_ranges: set[tuple[str, int, int]] = set()
    ranges_by_path: dict[str, list[tuple[int, int]]] = {}

    for item in context_ranges:
        if not isinstance(item, dict):
            raise ExecutionError(
                "AI_TASK context_ranges entries must be objects"
            )
        if set(item) != {"path", "start_line", "end_line"}:
            raise ExecutionError(
                "AI_TASK context_ranges entries require exactly "
                "path, start_line, and end_line"
            )

        path = normalize_repo_path(str(item["path"]))
        start = item["start_line"]
        end = item["end_line"]

        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
        ):
            raise ExecutionError(
                f"Invalid context range for {path}: {start}-{end}"
            )

        if end - start + 1 > 250:
            raise ExecutionError(
                f"AI_TASK context range exceeds 250 lines: "
                f"{path}:{start}-{end}"
            )

        if path in normalized:
            raise ExecutionError(
                "AI_TASK context_ranges are read-only and cannot overlap "
                f"allowed_files: {path}"
            )

        key = (path, start, end)
        if key in seen_ranges:
            raise ExecutionError(
                f"AI_TASK context_ranges contains duplicate: "
                f"{path}:{start}-{end}"
            )
        seen_ranges.add(key)
        ranges_by_path.setdefault(path, []).append((start, end))

    for path, ranges in ranges_by_path.items():
        ranges.sort()
        previous_end = 0
        for start, end in ranges:
            if start <= previous_end:
                raise ExecutionError(
                    f"AI_TASK context_ranges overlap for {path}"
                )
            previous_end = end


    authority = task.get("authority", {})
    if authority:
        if not isinstance(authority, dict):
            raise ExecutionError("AI_TASK authority must be an object")
        required = bool(authority.get("human_approval_required", False))
        granted = bool(authority.get("human_approval_granted", False))
        reference = str(authority.get("approval_reference", "")).strip()
        if granted and not reference:
            raise ExecutionError("Granted human approval requires authority.approval_reference")

    validation = task["validation"]
    if not isinstance(validation.get("command"), str) or not validation["command"].strip():
        raise ExecutionError("AI_TASK validation.command must be non-empty")

    timeout = validation.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ExecutionError("AI_TASK validation.timeout_seconds must be > 0")


def changed_files(repo: Path) -> list[str]:
    files: set[str] = set()

    for args in (
        ("diff", "--name-only", "--relative", "HEAD"),
        ("diff", "--cached", "--name-only", "--relative"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        result = git(repo, *args)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                files.add(line.replace("\\", "/"))

    return sorted(files)


def repo_clean(repo: Path) -> bool:
    return not changed_files(repo)


def validate_scope(actual: list[str], allowed: list[str]) -> tuple[bool, list[str]]:
    allowed_set = {normalize_repo_path(path) for path in allowed}
    outside = [path for path in actual if path not in allowed_set]
    return not outside, outside


def process_tree_terminate(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return False

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
            pass

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)

    return True


def shell_command(shell_name: str, command: str) -> tuple[list[str], str]:
    key = shell_name.strip().lower()

    if key == "powershell":
        executable = shutil.which("pwsh") or shutil.which("powershell.exe")
        if executable is None:
            raise ExecutionError("PowerShell validation requested but no pwsh/powershell.exe found")
        return [executable, "-NoProfile", "-NonInteractive", "-Command", command], "PowerShell"

    if key == "cmd":
        executable = shutil.which("cmd.exe")
        if executable is None:
            raise ExecutionError("cmd validation requested but cmd.exe not found")
        return [executable, "/d", "/s", "/c", command], "cmd"

    if key == "bash":
        executable = shutil.which("bash")
        if executable is None:
            raise ExecutionError("bash validation requested but bash not found")
        return [executable, "-lc", command], "bash"

    if key == "python":
        return [sys.executable, "-c", command], f"Python {platform.python_version()}"

    raise ExecutionError(f"Unsupported validation shell: {shell_name}")


def run_validation(
    *,
    task: dict[str, Any],
    repo: Path,
    output_dir: Path,
) -> ProcessRecord:
    validation = task["validation"]
    command, version = shell_command(
        str(validation.get("shell", "PowerShell")),
        str(validation["command"]),
    )
    timeout = float(validation["timeout_seconds"])

    stdout_path = output_dir / "validation.stdout.txt"
    stderr_path = output_dir / "validation.stderr.txt"

    env = os.environ.copy()
    env["BIRDAI_EXECUTION_OUTPUT_DIR"] = str(output_dir)
    env["BIRDAI_SLICE_ID"] = task["goal"]["slice_id"]
    env["BIRDAI_ISSUE"] = task["goal"]["issue"]

    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    start_utc = utc_now()
    started = time.monotonic()

    process = subprocess.Popen(
        command,
        cwd=str(repo),
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
    forced = False

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        forced = process_tree_terminate(process)
        stdout, stderr = process.communicate()

    elapsed = time.monotonic() - started

    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")

    return ProcessRecord(
        command=str(validation["command"]),
        version=version,
        pid=process.pid,
        start_utc=start_utc,
        exit_code=process.returncode,
        elapsed_seconds=round(elapsed, 6),
        timed_out=timed_out,
        forced_termination=forced,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def run_record(
    *,
    scenario_id: str,
    record: ProcessRecord,
    cwd: Path,
    failed_step: str | None,
    last_passed_step: str | None,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "command": record.command,
        "cwd": str(cwd),
        "version": record.version,
        "seed": None,
        "timeout_seconds": max(record.elapsed_seconds, 0.001) if scenario_id in {"qwen-agent", "lmstudio-bounded"} else 1,
        "elapsed_seconds": record.elapsed_seconds,
        "parent": {
            "pid": record.pid,
            "start_utc": record.start_utc,
            "exit_code": record.exit_code,
        },
        "children": [],
        "timed_out": record.timed_out,
        "forced_termination": record.forced_termination,
        "last_passed_step": last_passed_step,
        "failed_step": failed_step,
        "stdout": {
            "path": str(record.stdout_path),
            "sha256": sha256(record.stdout_path),
        },
        "stderr": {
            "path": str(record.stderr_path),
            "sha256": sha256(record.stderr_path),
        },
    }


def qwen_diagnosis(contract: dict[str, Any] | None, fallback: str) -> dict[str, str]:
    if not isinstance(contract, dict):
        return {
            "observed_failure": fallback,
            "likely_location": "qwen execution contract",
            "hypothesis": "Qwen did not return the required terminal JSON object",
            "minimal_test": "inspect qwen stdout/stderr evidence",
        }

    diagnosis = contract.get("diagnosis")
    if not isinstance(diagnosis, dict):
        return {
            "observed_failure": fallback,
            "likely_location": "qwen execution contract",
            "hypothesis": "terminal JSON omitted diagnosis",
            "minimal_test": "inspect qwen stdout/stderr evidence",
        }

    result: dict[str, str] = {}
    for key in ("observed_failure", "likely_location", "hypothesis", "minimal_test"):
        value = diagnosis.get(key)
        result[key] = str(value).strip() if value is not None else ""

    if any(not value for value in result.values()):
        return {
            "observed_failure": fallback,
            "likely_location": "qwen execution contract",
            "hypothesis": "terminal diagnosis was incomplete",
            "minimal_test": "inspect qwen stdout/stderr evidence",
        }

    return result


def qwen_strategy(contract: dict[str, Any] | None, outcome: str) -> list[dict[str, Any]]:
    strategy = contract.get("strategy") if isinstance(contract, dict) else None

    if not isinstance(strategy, dict):
        return [{
            "id": "qwen-bounded-execution",
            "operation": "bounded repository diagnosis/implementation",
            "uses": 1,
            "outcomes": [outcome],
        }]

    outcomes = strategy.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        outcomes = [outcome]

    return [{
        "id": str(strategy.get("id") or "qwen-bounded-execution"),
        "operation": str(strategy.get("operation") or "bounded repository diagnosis/implementation"),
        "uses": 1,
        "outcomes": [str(item) for item in outcomes],
    }]


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _require_exact_keys(
    value: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise ExecutionError(f"{label} missing fields: {sorted(missing)}")
    if extra:
        raise ExecutionError(f"{label} unexpected fields: {sorted(extra)}")


def _require_string(value: Any, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise ExecutionError(f"{label} must be a string")
    if nonempty and not value:
        raise ExecutionError(f"{label} must not be empty")
    return value


def _require_nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExecutionError(f"{label} must be a number")
    number = float(value)
    if number < 0:
        raise ExecutionError(f"{label} must be >= 0")
    return number


def _require_process_identity(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ExecutionError(f"{label} must be an object")
    _require_exact_keys(value, {"pid", "start_utc", "exit_code"}, label)

    pid = value["pid"]
    if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int)):
        raise ExecutionError(f"{label}.pid must be integer or null")

    start_utc = value["start_utc"]
    if start_utc is not None and not isinstance(start_utc, str):
        raise ExecutionError(f"{label}.start_utc must be string or null")

    exit_code = value["exit_code"]
    if exit_code is not None and (
        isinstance(exit_code, bool) or not isinstance(exit_code, int)
    ):
        raise ExecutionError(f"{label}.exit_code must be integer or null")


def _require_hashed_stream(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise ExecutionError(f"{label} must be an object")
    _require_exact_keys(value, {"path", "sha256"}, label)
    _require_string(value["path"], f"{label}.path")

    digest = _require_string(value["sha256"], f"{label}.sha256")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ExecutionError(f"{label}.sha256 must be lowercase SHA-256")


def structural_result_check(result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ExecutionError("AI_RESULT must be an object")

    _require_exact_keys(result, REQUIRED_RESULT_KEYS, "AI_RESULT")

    _require_string(result["slice_id"], "AI_RESULT.slice_id", nonempty=True)
    if result["status"] not in {"PASS", "BLOCKED"}:
        raise ExecutionError("AI_RESULT.status must be PASS or BLOCKED")
    _require_string(result["base_commit"], "AI_RESULT.base_commit")
    _require_nonnegative_number(
        result["elapsed_seconds"],
        "AI_RESULT.elapsed_seconds",
    )

    diagnosis = result["diagnosis"]
    if not isinstance(diagnosis, dict):
        raise ExecutionError("AI_RESULT.diagnosis must be an object")
    diagnosis_keys = {
        "observed_failure",
        "likely_location",
        "hypothesis",
        "minimal_test",
    }
    _require_exact_keys(diagnosis, diagnosis_keys, "AI_RESULT.diagnosis")
    for key in diagnosis_keys:
        _require_string(diagnosis[key], f"AI_RESULT.diagnosis.{key}")

    attempts = result["attempts"]
    if not isinstance(attempts, dict):
        raise ExecutionError("AI_RESULT.attempts must be an object")
    _require_exact_keys(
        attempts,
        {"diagnostic_runs", "validation_runs", "strategies"},
        "AI_RESULT.attempts",
    )

    for key in ("diagnostic_runs", "validation_runs"):
        value = attempts[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1:
            raise ExecutionError(
                f"AI_RESULT.attempts.{key} must be integer in [0, 1]"
            )

    strategies = attempts["strategies"]
    if not isinstance(strategies, list):
        raise ExecutionError("AI_RESULT.attempts.strategies must be an array")

    for index, strategy in enumerate(strategies):
        label = f"AI_RESULT.attempts.strategies[{index}]"
        if not isinstance(strategy, dict):
            raise ExecutionError(f"{label} must be an object")
        _require_exact_keys(
            strategy,
            {"id", "operation", "uses", "outcomes"},
            label,
        )
        _require_string(strategy["id"], f"{label}.id")
        _require_string(strategy["operation"], f"{label}.operation")

        uses = strategy["uses"]
        if isinstance(uses, bool) or not isinstance(uses, int) or not 1 <= uses <= 2:
            raise ExecutionError(f"{label}.uses must be integer in [1, 2]")

        outcomes = strategy["outcomes"]
        if not isinstance(outcomes, list) or not all(
            isinstance(item, str) for item in outcomes
        ):
            raise ExecutionError(f"{label}.outcomes must be an array of strings")

    runs = result["runs"]
    if not isinstance(runs, list) or len(runs) > 2:
        raise ExecutionError("AI_RESULT.runs must be an array with at most 2 items")

    run_keys = {
        "scenario_id",
        "command",
        "cwd",
        "version",
        "seed",
        "timeout_seconds",
        "elapsed_seconds",
        "parent",
        "children",
        "timed_out",
        "forced_termination",
        "last_passed_step",
        "failed_step",
        "stdout",
        "stderr",
    }

    for index, run_item in enumerate(runs):
        label = f"AI_RESULT.runs[{index}]"
        if not isinstance(run_item, dict):
            raise ExecutionError(f"{label} must be an object")
        _require_exact_keys(run_item, run_keys, label)

        for key in ("scenario_id", "command", "cwd", "version"):
            _require_string(run_item[key], f"{label}.{key}")

        seed = run_item["seed"]
        if seed is not None and (
            isinstance(seed, bool) or not isinstance(seed, (str, int))
        ):
            raise ExecutionError(f"{label}.seed must be string, integer, or null")

        timeout_seconds = _require_nonnegative_number(
            run_item["timeout_seconds"],
            f"{label}.timeout_seconds",
        )
        if timeout_seconds <= 0:
            raise ExecutionError(f"{label}.timeout_seconds must be > 0")

        _require_nonnegative_number(
            run_item["elapsed_seconds"],
            f"{label}.elapsed_seconds",
        )

        _require_process_identity(run_item["parent"], f"{label}.parent")

        children = run_item["children"]
        if not isinstance(children, list):
            raise ExecutionError(f"{label}.children must be an array")
        for child_index, child in enumerate(children):
            _require_process_identity(
                child,
                f"{label}.children[{child_index}]",
            )

        for key in ("timed_out", "forced_termination"):
            if not isinstance(run_item[key], bool):
                raise ExecutionError(f"{label}.{key} must be boolean")

        for key in ("last_passed_step", "failed_step"):
            value = run_item[key]
            if value is not None and not isinstance(value, str):
                raise ExecutionError(
                    f"{label}.{key} must be string or null"
                )

        _require_hashed_stream(run_item["stdout"], f"{label}.stdout")
        _require_hashed_stream(run_item["stderr"], f"{label}.stderr")

    cleanup = result["cleanup"]
    if not isinstance(cleanup, dict):
        raise ExecutionError("AI_RESULT.cleanup must be an object")
    _require_exact_keys(
        cleanup,
        {"status", "paths", "details"},
        "AI_RESULT.cleanup",
    )
    if cleanup["status"] not in {"PASS", "FAIL", "not_applicable"}:
        raise ExecutionError(
            "AI_RESULT.cleanup.status must be PASS, FAIL, or not_applicable"
        )
    if not isinstance(cleanup["paths"], list) or not all(
        isinstance(item, str) for item in cleanup["paths"]
    ):
        raise ExecutionError("AI_RESULT.cleanup.paths must be an array of strings")
    _require_string(cleanup["details"], "AI_RESULT.cleanup.details")

    changed = result["changed_files"]
    if not isinstance(changed, list) or not all(
        isinstance(item, str) for item in changed
    ):
        raise ExecutionError("AI_RESULT.changed_files must be an array of strings")

    evidence = result["pass_evidence"]
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise ExecutionError("AI_RESULT.pass_evidence must be an array of strings")

    _require_string(
        result["stop_reason"],
        "AI_RESULT.stop_reason",
        nonempty=True,
    )

    if result["status"] == "PASS":
        if not runs:
            raise ExecutionError("PASS requires at least one run")
        if not evidence:
            raise ExecutionError("PASS requires pass_evidence")
        if cleanup["status"] not in {"PASS", "not_applicable"}:
            raise ExecutionError(
                "PASS requires cleanup.status PASS or not_applicable"
            )

        for index, run_item in enumerate(runs):
            if run_item["timed_out"]:
                raise ExecutionError(
                    f"PASS run {index} cannot be timed_out"
                )
            if run_item["forced_termination"]:
                raise ExecutionError(
                    f"PASS run {index} cannot be forced_termination"
                )
            if run_item["parent"]["exit_code"] != 0:
                raise ExecutionError(
                    f"PASS run {index} requires parent.exit_code == 0"
                )

def schema_check(result: dict[str, Any], schema_path: Path) -> str:
    structural_result_check(result)

    try:
        import jsonschema  # type: ignore
    except ImportError:
        return "birdai-v1-stdlib"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(result)
    return "birdai-v1-stdlib+draft7-jsonschema"



def tracked_repo_files(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo),
        capture_output=True,
        check=True,
    )
    raw = result.stdout.decode("utf-8", errors="surrogateescape")
    return sorted(path for path in raw.split("\0") if path)


def materialize_qwen_workspace(
    *,
    repo: Path,
    output_dir: Path,
) -> tuple[Path, list[str]]:
    workspace = output_dir / "qwen-workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    tracked = tracked_repo_files(repo)

    for relative in tracked:
        source = repo / relative
        destination = workspace / relative

        if source.is_dir():
            raise ExecutionError(
                f"Tracked directory/submodule is not supported by isolated executor v1: {relative}"
            )

        if is_unsafe_link(source):
            raise ExecutionError(
                f"Tracked symlink is not supported by isolated executor v1: {relative}"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    return workspace, tracked


def digest_file(path: Path) -> str:
    return sha256(path)


def is_unsafe_link(path: Path) -> bool:
    if path.is_symlink():
        return True

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return True

    return False


def workspace_change_set(
    *,
    repo: Path,
    workspace: Path,
    tracked: list[str],
) -> tuple[list[str], list[str]]:
    tracked_set = set(tracked)
    changed: set[str] = set()
    unsafe_symlinks: set[str] = set()

    for relative in tracked:
        original = repo / relative
        candidate = workspace / relative

        if not candidate.exists() and not candidate.is_symlink():
            changed.add(relative)
            continue

        if is_unsafe_link(candidate):
            changed.add(relative)
            unsafe_symlinks.add(relative)
            continue

        if not candidate.is_file():
            changed.add(relative)
            continue

        if digest_file(original) != digest_file(candidate):
            changed.add(relative)

    for candidate in workspace.rglob("*"):
        if candidate.is_dir() and not is_unsafe_link(candidate):
            continue

        relative = candidate.relative_to(workspace).as_posix()
        if relative in tracked_set:
            continue

        changed.add(relative)
        if is_unsafe_link(candidate):
            unsafe_symlinks.add(relative)

    return sorted(changed), sorted(unsafe_symlinks)


def apply_workspace_changes(
    *,
    repo: Path,
    workspace: Path,
    changes: list[str],
) -> None:
    for relative in changes:
        normalized = normalize_repo_path(relative)
        source = workspace / normalized
        destination = repo / normalized

        if is_unsafe_link(source):
            raise ExecutionError(f"Qwen created a symlink, which is not allowed: {normalized}")

        if source.exists():
            if not source.is_file():
                raise ExecutionError(
                    f"Qwen changed a non-file path, which executor v1 does not support: {normalized}"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        else:
            if destination.exists() or is_unsafe_link(destination):
                if destination.is_dir():
                    raise ExecutionError(
                        f"Qwen requested directory deletion, unsupported in executor v1: {normalized}"
                    )
                destination.unlink()


def write_workspace_evidence(
    *,
    output_dir: Path,
    changes: list[str],
    unsafe_symlinks: list[str],
) -> Path:
    path = output_dir / "qwen-workspace-changes.json"
    payload = {
        "changed_files": changes,
        "unsafe_symlinks": unsafe_symlinks,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def save_candidate_patch(repo: Path, output_dir: Path) -> Path:
    patch_path = output_dir / "candidate.diff"
    result = git(repo, "diff", "--binary", "HEAD", check=False)
    patch_path.write_text(result.stdout or "", encoding="utf-8")
    return patch_path


def rollback_repo(repo: Path) -> None:
    git(repo, "restore", "--staged", "--worktree", "--", ".", check=False)
    git(repo, "clean", "-fd", check=False)



def main() -> int:
    parser = argparse.ArgumentParser(description="BirdAI bounded Qwen execution runner")
    parser.add_argument("--task", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--result", default="")
    parser.add_argument("--qwen-command", default=os.environ.get("BIRDAI_QWEN_COMMAND", "qwen"))
    parser.add_argument("--qwen-model", default=os.environ.get("BIRDAI_QWEN_MODEL", ""))
    parser.add_argument("--agent-wall-time", type=int, default=900)
    parser.add_argument("--max-session-turns", type=int, default=30)
    parser.add_argument("--max-tool-calls", type=int, default=50)
    args = parser.parse_args()

    started = time.monotonic()
    repo = Path(args.repo).resolve()

    if not repo.exists():
        raise ExecutionError(f"Repository path does not exist: {repo}")

    probe = git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    if probe.returncode != 0 or probe.stdout.strip().lower() != "true":
        raise ExecutionError(f"Not a git working tree: {repo}")

    raw_task_path = Path(args.task)
    task_path = (
        (repo / raw_task_path).resolve()
        if not raw_task_path.is_absolute()
        else raw_task_path.resolve()
    )

    try:
        task_rel = task_path.relative_to(repo).as_posix()
    except ValueError as exc:
        raise ExecutionError(f"AI_TASK must be inside the repository: {task_path}") from exc

    tracked_task = git(
        repo,
        "ls-files",
        "--error-unmatch",
        "--",
        task_rel,
        check=False,
    )
    if tracked_task.returncode != 0:
        raise ExecutionError(
            f"AI_TASK must be tracked by git on the checked-out commit: {task_rel}"
        )

    output_dir = Path(args.output_dir).resolve()
    try:
        output_dir.relative_to(repo)
    except ValueError:
        pass
    else:
        raise ExecutionError(
            f"Execution output directory must be outside the repository: {output_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = (
        Path(args.result).resolve()
        if args.result
        else output_dir / "AI_RESULT.json"
    )

    task = json.loads(task_path.read_text(encoding="utf-8"))
    validate_task(task)

    base_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    before = changed_files(repo)
    if before:
        raise ExecutionError(f"Repository must be clean before execution: {before}")

    schema_path = (repo / task["result_schema"]).resolve()
    try:
        schema_path.relative_to(repo)
    except ValueError as exc:
        raise ExecutionError(
            f"Execution result schema must be inside repository: {schema_path}"
        ) from exc
    if not schema_path.exists():
        raise ExecutionError(f"Execution result schema not found: {schema_path}")

    qwen_run = None
    validation_run = None
    qwen_workspace: Path | None = None
    status = "BLOCKED"
    stop_reason = "second_run_failed_timed_out_or_inconclusive"
    pass_evidence: list[str] = []
    block_reason = ""
    scope_outside: list[str] = []
    candidate_changes: list[str] = []
    unsafe_symlinks: list[str] = []
    rollback_performed = False

    authority = task.get("authority", {})
    authority_required = (
        bool(authority.get("human_approval_required", False))
        if isinstance(authority, dict)
        else False
    )
    authority_granted = (
        bool(authority.get("human_approval_granted", False))
        if isinstance(authority, dict)
        else False
    )

    try:
        if authority_required and not authority_granted:
            block_reason = (
                "Human approval is required by AI_TASK but has not been granted"
            )
            stop_reason = "authority_or_scope_conflict"
        else:
            qwen_workspace, tracked = materialize_qwen_workspace(
                repo=repo,
                output_dir=output_dir,
            )

            backend = task.get("execution_backend", "qwen")
            if backend == "lmstudio":
                from lmstudio_adapter import LMStudioAdapter

                adapter = LMStudioAdapter(
                    model=args.qwen_model or None,
                    timeout_seconds=args.agent_wall_time,
                )
            else:
                adapter = QwenAdapter(
                    command=args.qwen_command,
                    model=args.qwen_model or None,
                    wall_time_seconds=args.agent_wall_time,
                    max_session_turns=args.max_session_turns,
                    max_tool_calls=args.max_tool_calls,
                )
            qwen_run = adapter.execute(
                task=task,
                cwd=qwen_workspace,
                output_dir=output_dir,
            )

            real_repo_intrusions = changed_files(repo)

            candidate_changes, unsafe_symlinks = workspace_change_set(
                repo=repo,
                workspace=qwen_workspace,
                tracked=tracked,
            )
            write_workspace_evidence(
                output_dir=output_dir,
                changes=candidate_changes,
                unsafe_symlinks=unsafe_symlinks,
            )

            scope_ok, scope_outside = validate_scope(
                candidate_changes,
                task["allowed_files"],
            )

            if real_repo_intrusions:
                candidate_changes = sorted(
                    set(candidate_changes + real_repo_intrusions)
                )
                scope_outside = sorted(
                    set(
                        scope_outside
                        + [
                            path
                            for path in real_repo_intrusions
                            if path not in set(task["allowed_files"])
                        ]
                    )
                )
                block_reason = (
                    "Qwen modified the real repository while assigned to the "
                    "isolated workspace: "
                    f"{real_repo_intrusions}"
                )
                stop_reason = "authority_or_scope_conflict"
            elif unsafe_symlinks:
                block_reason = (
                    "Qwen created or replaced paths with links/junctions: "
                    f"{unsafe_symlinks}"
                )
                stop_reason = "authority_or_scope_conflict"
            elif qwen_run.process.timed_out:
                block_reason = "Qwen agent exceeded the execution wall-time budget"
            elif qwen_run.process.exit_code != 0:
                block_reason = (
                    f"Qwen agent exited with code {qwen_run.process.exit_code}"
                )
            elif qwen_run.contract is None:
                block_reason = (
                    "Qwen agent did not return the required terminal JSON contract"
                )
            elif not scope_ok:
                block_reason = (
                    "Qwen attempted files outside allowed_files in isolated workspace: "
                    f"{scope_outside}"
                )
                stop_reason = "authority_or_scope_conflict"
            else:
                apply_workspace_changes(
                    repo=repo,
                    workspace=qwen_workspace,
                    changes=candidate_changes,
                )

                validation_run = run_validation(
                    task=task,
                    repo=repo,
                    output_dir=output_dir,
                )

                after_validation = changed_files(repo)
                candidate_changes = after_validation
                validation_scope_ok, validation_outside = validate_scope(
                    after_validation,
                    task["allowed_files"],
                )

                if validation_outside:
                    scope_outside = sorted(
                        set(scope_outside + validation_outside)
                    )

                if validation_run.timed_out:
                    block_reason = "Authoritative validation timed out"
                elif validation_run.exit_code != 0:
                    block_reason = (
                        "Authoritative validation exited with code "
                        f"{validation_run.exit_code}"
                    )
                elif not validation_scope_ok:
                    block_reason = (
                        "Validation changed files outside allowed_files: "
                        f"{validation_outside}"
                    )
                    stop_reason = "authority_or_scope_conflict"
                else:
                    status = "PASS"
                    stop_reason = "pass_definition_proven"
                    pass_evidence = [
                        (
                            "Generator ran in an isolated tracked-file workspace "
                            "without repository metadata"
                        ),
                        (
                            "candidate changed_files are a subset of "
                            "AI_TASK.allowed_files"
                        ),
                        "authoritative task validation exited 0",
                        f"pass definition: {task['goal']['pass_definition']}",
                    ]
    except QwenAdapterError as exc:
        block_reason = str(exc)

    if status == "BLOCKED":
        if changed_files(repo):
            save_candidate_patch(repo, output_dir)
            rollback_repo(repo)
            rollback_performed = True

        if changed_files(repo):
            raise ExecutionError(
                "Coordinator failed to restore the repository after a blocked slice"
            )

    if qwen_workspace is not None and qwen_workspace.exists():
        shutil.rmtree(qwen_workspace)

    elapsed = round(time.monotonic() - started, 6)

    diagnosis = qwen_diagnosis(
        qwen_run.contract if qwen_run else None,
        block_reason or "No execution failure reported",
    )
    strategies = (
        qwen_strategy(
            qwen_run.contract,
            "PASS" if status == "PASS" else block_reason or "BLOCKED",
        )
        if qwen_run is not None
        else []
    )

    runs: list[dict[str, Any]] = []

    if qwen_run is not None:
        qwen_failed = (
            qwen_run.process.exit_code != 0
            or qwen_run.process.timed_out
            or qwen_run.contract is None
            or bool(scope_outside)
            or bool(unsafe_symlinks)
        )
        runs.append(
            run_record(
                scenario_id=(
                    "lmstudio-bounded"
                    if task.get("execution_backend") == "lmstudio"
                    else "qwen-agent"
                ),
                record=qwen_run.process,
                cwd=output_dir / "qwen-workspace",
                failed_step="bounded_qwen_execution" if qwen_failed else None,
                last_passed_step=(
                    None if qwen_failed else "bounded_qwen_execution"
                ),
            )
        )

    if validation_run is not None:
        validation_failed = (
            validation_run.exit_code != 0
            or validation_run.timed_out
            or bool(scope_outside)
        )
        validation_record = run_record(
            scenario_id="validation",
            record=validation_run,
            cwd=repo,
            failed_step=(
                "authoritative_validation" if validation_failed else None
            ),
            last_passed_step=(
                None if validation_failed else "authoritative_validation"
            ),
        )
        validation_record["timeout_seconds"] = float(
            task["validation"]["timeout_seconds"]
        )
        runs.append(validation_record)

    if status == "BLOCKED" and not block_reason:
        block_reason = "Execution did not prove the pass definition"

    cleanup_failed = any(
        run["timed_out"] and not run["forced_termination"]
        for run in runs
    )

    cleanup_details = (
        "Isolated Qwen workspace removed; blocked repository changes rolled back; "
        "no unconfirmed timed-out process remains."
        if status == "BLOCKED"
        else "Isolated Qwen workspace removed; coordinator owns process lifetime."
    )
    if rollback_performed:
        cleanup_details += " Candidate diff was saved before rollback."

    result = {
        "slice_id": task["goal"]["slice_id"],
        "status": status,
        "base_commit": base_commit,
        "elapsed_seconds": elapsed,
        "diagnosis": diagnosis,
        "attempts": {
            "diagnostic_runs": 1 if qwen_run is not None else 0,
            "validation_runs": 1 if validation_run is not None else 0,
            "strategies": strategies,
        },
        "runs": runs,
        "cleanup": {
            "status": "FAIL" if cleanup_failed else "PASS",
            "paths": [],
            "details": cleanup_details,
        },
        "changed_files": candidate_changes,
        "pass_evidence": pass_evidence,
        "stop_reason": (
            stop_reason
            if status == "PASS"
            else f"{stop_reason}: {block_reason}"
        ),
    }

    validation_mode = schema_check(result, schema_path)
    atomic_json(result_path, result)

    print(f"STATUS: {status}")
    print(f"SLICE: {task['goal']['slice_id']}")
    print(f"BASE_COMMIT: {base_commit}")
    print(f"CHANGED_FILES: {json.dumps(candidate_changes)}")
    print(f"RESULT_SCHEMA_VALIDATION: {validation_mode}")
    print(f"AI_RESULT: {result_path}")

    if scope_outside:
        print(f"SCOPE_VIOLATIONS: {json.dumps(scope_outside)}")

    if status != "PASS":
        print(f"BLOCKER: {block_reason}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExecutionError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(1)
