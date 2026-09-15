from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


class SliceError(RuntimeError):
    pass


def normalize_repo_path(value: str) -> str:
    if not value or value.strip() != value:
        raise SliceError(f"Invalid repository-relative path: {value!r}")
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise SliceError(f"Use repository-relative forward-slash paths: {value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SliceError(f"Unsafe path component in: {value}")
    if parts[0].lower() == ".git":
        raise SliceError(f"Git metadata is never an allowed execution target: {value}")
    return "/".join(parts)


def atomic_create(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2) + "\n"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a BirdAI AI_TASK execution slice")
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--pass-definition", required=True)
    parser.add_argument("--allowed-file", action="append", default=[])
    parser.add_argument("--validation-command", required=True)
    parser.add_argument(
        "--validation-shell",
        choices=("PowerShell", "cmd", "bash", "Python"),
        default="PowerShell",
    )
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--timeout-reason", default="")
    parser.add_argument("--human-approval-required", action="store_true")
    parser.add_argument("--human-approval-granted", action="store_true")
    parser.add_argument("--approval-reference", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--template",
        default=str(Path(__file__).with_name("execution-slice.template.json")),
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", args.slice_id):
        raise SliceError("slice-id must match ^[a-z0-9]+(-[a-z0-9]+)+$")

    for value_name, value in (
        ("issue", args.issue),
        ("goal", args.goal),
        ("pass-definition", args.pass_definition),
        ("validation-command", args.validation_command),
    ):
        if not value.strip():
            raise SliceError(f"{value_name} must not be blank")

    if args.timeout_seconds < 1 or args.timeout_seconds > 86400:
        raise SliceError("timeout-seconds must be between 1 and 86400")

    if args.timeout_seconds > 20 and not args.timeout_reason.strip():
        raise SliceError("timeout above 20 seconds requires --timeout-reason")
    if args.human_approval_granted and not args.approval_reference.strip():
        raise SliceError("--human-approval-granted requires --approval-reference")

    allowed_files = []
    for value in args.allowed_file:
        normalized = normalize_repo_path(value)
        if normalized not in allowed_files:
            allowed_files.append(normalized)

    template_path = Path(args.template).resolve()
    task = json.loads(template_path.read_text(encoding="utf-8"))

    task["goal"]["slice_id"] = args.slice_id
    task["goal"]["issue"] = args.issue
    task["goal"]["objective"] = args.goal
    task["goal"]["pass_definition"] = args.pass_definition
    task["allowed_files"] = allowed_files
    task["authority"] = {
        "human_approval_required": bool(args.human_approval_required),
        "human_approval_granted": bool(args.human_approval_granted),
        "approval_reference": args.approval_reference.strip(),
    }
    task["validation"]["shell"] = args.validation_shell
    task["validation"]["command"] = args.validation_command
    task["validation"]["timeout_seconds"] = args.timeout_seconds
    task["validation"]["timeout_reason"] = args.timeout_reason

    destination = Path(args.output).resolve()
    atomic_create(destination, task)

    print(destination)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SliceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
