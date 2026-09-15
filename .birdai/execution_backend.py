from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ExecutionBackendError(RuntimeError):
    pass


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
class ExecutionResult:
    process: ProcessRecord
    contract: dict[str, Any] | None
    raw_result: str | None
