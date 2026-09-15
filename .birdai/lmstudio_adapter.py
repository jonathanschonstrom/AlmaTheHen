from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from execution_backend import ExecutionBackendError, ExecutionResult, ProcessRecord


class LMStudioAdapterError(ExecutionBackendError):
    pass


DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "qwen3-coder-30b-a3b-instruct"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_SEED = 20260915


def _normalize_repo_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
    ):
        raise LMStudioAdapterError(
            f"Invalid repository-relative path: {value!r}"
        )

    if "\\" in value or value.startswith("/") or re.match(
        r"^[A-Za-z]:",
        value,
    ):
        raise LMStudioAdapterError(
            "Path must be repository-relative with forward slashes: "
            f"{value}"
        )

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise LMStudioAdapterError(
            f"Unsafe repository-relative path: {value}"
        )
    if parts[0].lower() == ".git":
        raise LMStudioAdapterError(
            f"Git metadata is not an allowed path: {value}"
        )

    return "/".join(parts)


def _loopback_base_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http":
        raise LMStudioAdapterError(
            "Direct LM Studio backend requires local HTTP"
        )
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise LMStudioAdapterError(
            "Direct LM Studio backend only permits loopback endpoints: "
            f"{value}"
        )
    if not parsed.path.rstrip("/").endswith("/v1"):
        raise LMStudioAdapterError(
            "LM Studio base URL must end in /v1"
        )
    return value.rstrip("/")


def _resolve_context_path(
    cwd: Path,
    relative: str,
) -> Path:
    root = cwd.resolve()
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise LMStudioAdapterError(
            f"Context path does not exist: {relative}"
        ) from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LMStudioAdapterError(
            f"Context path escaped workspace: {relative}"
        ) from exc

    if not resolved.is_file():
        raise LMStudioAdapterError(
            f"Context path is not a regular file: {relative}"
        )

    return resolved


def _render_context(
    task: dict[str, Any],
    cwd: Path,
) -> str:
    allowed = {
        _normalize_repo_path(value)
        for value in task.get("allowed_files", [])
    }

    sections: list[str] = []
    seen_files: set[str] = set()

    context_files = task.get("context_files", [])
    if context_files is None:
        context_files = []
    if not isinstance(context_files, list):
        raise LMStudioAdapterError(
            "AI_TASK context_files must be an array"
        )

    for value in context_files:
        relative = _normalize_repo_path(value)
        if relative in seen_files:
            raise LMStudioAdapterError(
                f"Duplicate context file: {relative}"
            )
        seen_files.add(relative)

        if relative in allowed:
            raise LMStudioAdapterError(
                "Read-only context overlaps allowed_files: "
                f"{relative}"
            )

        path = _resolve_context_path(cwd, relative)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise LMStudioAdapterError(
                f"Context file is not UTF-8 text: {relative}"
            ) from exc

        sections.append(
            f"===== BEGIN CONTEXT FILE: {relative} =====\n"
            f"{content}\n"
            f"===== END CONTEXT FILE: {relative} ====="
        )

    context_ranges = task.get("context_ranges", [])
    if context_ranges is None:
        context_ranges = []
    if not isinstance(context_ranges, list):
        raise LMStudioAdapterError(
            "AI_TASK context_ranges must be an array"
        )

    seen_ranges: set[tuple[str, int, int]] = set()

    for item in context_ranges:
        if not isinstance(item, dict):
            raise LMStudioAdapterError(
                "AI_TASK context_ranges entries must be objects"
            )
        if set(item) != {"path", "start_line", "end_line"}:
            raise LMStudioAdapterError(
                "AI_TASK context_ranges entries require exactly "
                "path, start_line, and end_line"
            )

        relative = _normalize_repo_path(item["path"])
        start = item["start_line"]
        end = item["end_line"]

        if relative in allowed:
            raise LMStudioAdapterError(
                "Read-only context overlaps allowed_files: "
                f"{relative}"
            )
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
        ):
            raise LMStudioAdapterError(
                f"Invalid context range: {relative}:{start}-{end}"
            )
        if end - start + 1 > 250:
            raise LMStudioAdapterError(
                f"Context range exceeds 250 lines: "
                f"{relative}:{start}-{end}"
            )

        key = (relative, start, end)
        if key in seen_ranges:
            raise LMStudioAdapterError(
                f"Duplicate context range: {relative}:{start}-{end}"
            )
        seen_ranges.add(key)

        path = _resolve_context_path(cwd, relative)
        try:
            lines = path.read_text(
                encoding="utf-8"
            ).splitlines()
        except UnicodeDecodeError as exc:
            raise LMStudioAdapterError(
                f"Context range file is not UTF-8 text: {relative}"
            ) from exc

        if end > len(lines):
            raise LMStudioAdapterError(
                f"Context range exceeds file length {len(lines)}: "
                f"{relative}:{start}-{end}"
            )

        numbered = "\n".join(
            f"{line_number:04d}: {lines[line_number - 1]}"
            for line_number in range(start, end + 1)
        )

        sections.append(
            "===== BEGIN CONTEXT RANGE: "
            f"{relative}:{start}-{end} =====\n"
            f"{numbered}\n"
            "===== END CONTEXT RANGE: "
            f"{relative}:{start}-{end} ====="
        )

    if not sections:
        raise LMStudioAdapterError(
            "Direct LM Studio backend requires explicit "
            "context_files or context_ranges"
        )

    return "\n\n".join(sections)


def _proposal_schema(
    allowed_files: list[str],
) -> dict[str, Any]:
    allowed = [
        _normalize_repo_path(value)
        for value in allowed_files
    ]

    if allowed:
        files_schema: dict[str, Any] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": allowed,
                    },
                    "content": {
                        "type": "string",
                        "minLength": 1,
                    },
                },
            },
            "minItems": len(allowed),
            "maxItems": len(allowed),
        }
    else:
        files_schema = {
            "type": "array",
            "minItems": 0,
            "maxItems": 0,
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "diagnosis",
            "strategy",
            "files",
            "summary",
        ],
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
                "required": [
                    "id",
                    "operation",
                    "outcomes",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "operation": {"type": "string"},
                    "outcomes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "files": files_schema,
            "summary": {"type": "string"},
        },
    }


def _build_messages(
    task: dict[str, Any],
    context: str,
) -> list[dict[str, str]]:
    goal = task["goal"]
    allowed = [
        _normalize_repo_path(value)
        for value in task["allowed_files"]
    ]

    system = (
        "You are BirdAI's bounded code generator. "
        "You have no tools, no shell, and no repository access. "
        "The supplied repository context is complete and authoritative "
        "for this bounded slice. Return only data conforming to the "
        "supplied JSON schema. Every file object must contain the "
        "complete final file content, never a patch. Never propose a "
        "path outside the exact allowed list. Do not create reports, "
        "logs, metadata, or unrelated changes."
    )

    user = (
        f"Execution slice: {goal['slice_id']}\n"
        f"Issue: {goal['issue']}\n\n"
        f"Objective:\n{goal['objective']}\n\n"
        f"Pass definition:\n{goal['pass_definition']}\n\n"
        "Exact files that must be generated:\n"
        f"{json.dumps(allowed, ensure_ascii=False)}\n\n"
        f"Repository context:\n{context}\n\n"
        "Generate the smallest complete implementation that satisfies "
        "the pass definition. The coordinator independently enforces "
        "path scope and runs authoritative validation."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _http_json(
    *,
    url: str,
    method: str,
    timeout: int,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    body = None
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer lm-studio",
    }
    if payload is not None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise LMStudioAdapterError(
            f"LM Studio HTTP {exc.code} from {url}: {raw[:4000]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LMStudioAdapterError(
            f"Cannot reach LM Studio at {url}: {exc}"
        ) from exc
    except TimeoutError as exc:
        raise LMStudioAdapterError(
            f"LM Studio request exceeded {timeout}s"
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LMStudioAdapterError(
            f"LM Studio returned non-JSON data: {raw[:4000]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise LMStudioAdapterError(
            "LM Studio returned a non-object JSON response"
        )

    return parsed, raw


def _validate_and_write_files(
    *,
    proposal: dict[str, Any],
    allowed_files: list[str],
    cwd: Path,
) -> list[str]:
    allowed = [
        _normalize_repo_path(value)
        for value in allowed_files
    ]
    allowed_set = set(allowed)

    files = proposal.get("files")
    if not isinstance(files, list):
        raise LMStudioAdapterError(
            "Structured proposal files must be an array"
        )

    seen: set[str] = set()
    validated: list[tuple[str, str]] = []

    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise LMStudioAdapterError(
                f"Structured proposal files[{index}] must be an object"
            )

        relative = _normalize_repo_path(item.get("path"))
        content = item.get("content")

        if relative not in allowed_set:
            raise LMStudioAdapterError(
                f"Model proposed forbidden path: {relative}"
            )
        if relative in seen:
            raise LMStudioAdapterError(
                f"Model proposed duplicate path: {relative}"
            )
        if not isinstance(content, str) or not content:
            raise LMStudioAdapterError(
                f"Model returned empty content for: {relative}"
            )

        seen.add(relative)
        validated.append((relative, content))

    if seen != allowed_set:
        raise LMStudioAdapterError(
            "Model did not return exactly allowed_files. "
            f"Expected={sorted(allowed_set)} actual={sorted(seen)}"
        )

    root = cwd.resolve()
    for relative, content in validated:
        destination = cwd / relative
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        resolved_parent = destination.parent.resolve()
        try:
            resolved_parent.relative_to(root)
        except ValueError as exc:
            raise LMStudioAdapterError(
                f"Destination escaped workspace: {relative}"
            ) from exc

        destination.write_text(
            content,
            encoding="utf-8",
            newline="\n",
        )

    return sorted(seen)


class LMStudioAdapter:
    def __init__(
        self,
        *,
        model: str | None,
        timeout_seconds: int,
        base_url: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.base_url = _loopback_base_url(
            base_url
            or os.environ.get(
                "BIRDAI_LMSTUDIO_BASE_URL",
                DEFAULT_BASE_URL,
            )
        )
        self.model = (
            model
            or os.environ.get(
                "BIRDAI_LMSTUDIO_MODEL",
                DEFAULT_MODEL,
            )
        )
        self.timeout_seconds = timeout_seconds
        self.max_tokens = (
            max_tokens
            or int(
                os.environ.get(
                    "BIRDAI_LMSTUDIO_MAX_TOKENS",
                    str(DEFAULT_MAX_TOKENS),
                )
            )
        )

        if self.timeout_seconds <= 0:
            raise LMStudioAdapterError(
                "LM Studio timeout must be > 0"
            )
        if self.max_tokens <= 0:
            raise LMStudioAdapterError(
                "LM Studio max tokens must be > 0"
            )

    def execute(
        self,
        *,
        task: dict[str, Any],
        cwd: Path,
        output_dir: Path,
    ) -> ExecutionResult:
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        response_path = output_dir / "lmstudio.response.json"
        request_path = output_dir / "lmstudio.request.json"
        stderr_path = output_dir / "lmstudio.stderr.txt"
        stderr_path.write_text("", encoding="utf-8")

        context = _render_context(task, cwd)
        schema = _proposal_schema(task["allowed_files"])
        payload = {
            "model": self.model,
            "messages": _build_messages(task, context),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "birdai_bounded_proposal",
                    "strict": True,
                    "schema": schema,
                },
            },
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
            "seed": DEFAULT_SEED,
            "stream": False,
        }

        request_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        started = time.monotonic()
        response, raw_response = _http_json(
            url=f"{self.base_url}/chat/completions",
            method="POST",
            timeout=self.timeout_seconds,
            payload=payload,
        )
        elapsed = time.monotonic() - started

        response_path.write_text(
            raw_response,
            encoding="utf-8",
        )

        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LMStudioAdapterError(
                "LM Studio response contained no choices"
            )

        first = choices[0]
        if not isinstance(first, dict):
            raise LMStudioAdapterError(
                "LM Studio first choice was not an object"
            )

        message = first.get("message")
        if not isinstance(message, dict):
            raise LMStudioAdapterError(
                "LM Studio response contained no message object"
            )

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LMStudioAdapterError(
                "LM Studio message content was empty"
            )

        try:
            proposal = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LMStudioAdapterError(
                "LM Studio structured message was not valid JSON"
            ) from exc

        if not isinstance(proposal, dict):
            raise LMStudioAdapterError(
                "LM Studio structured proposal was not an object"
            )

        _validate_and_write_files(
            proposal=proposal,
            allowed_files=task["allowed_files"],
            cwd=cwd,
        )

        process = ProcessRecord(
            command=(
                f"POST {self.base_url}/chat/completions "
                f"model={self.model}"
            ),
            version=(
                "LM Studio OpenAI-compatible API; "
                f"model={self.model}"
            ),
            pid=None,
            start_utc=None,
            exit_code=0,
            elapsed_seconds=round(elapsed, 6),
            timed_out=False,
            forced_termination=False,
            stdout_path=response_path,
            stderr_path=stderr_path,
        )

        return ExecutionResult(
            process=process,
            contract=proposal,
            raw_result=content,
        )
