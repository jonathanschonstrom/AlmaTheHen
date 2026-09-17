"""Bounded subprocess trees with raw streams and durable receipts (Windows/POSIX)."""
from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lifecycle_store import LifecycleError, atomic_json, digest, read_json


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes as w
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.k.CreateJobObjectW.restype = w.HANDLE
        self.k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.k.CloseHandle.argtypes = [w.HANDLE]

        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", w.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("active_limit", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        self.handle = self.k.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise LifecycleError("Windows process-tree supervision could not be established.")

    def assign(self, process):
        if not self.k.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise LifecycleError("Cannot assign gated child to Windows job; experiment not started.")

    def active(self):
        class Accounting(ctypes.Structure):
            _fields_ = [("times", ctypes.c_longlong * 4), ("faults", ctypes.c_uint32),
                        ("total", ctypes.c_uint32), ("active", ctypes.c_uint32), ("terminated", ctypes.c_uint32)]
        info = Accounting()
        if not self.k.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise LifecycleError("Cannot confirm child-process termination.")
        return info.active

    def terminate(self):
        if not self.k.TerminateJobObject(self.handle, 124):
            raise LifecycleError("Could not terminate the owned Windows job.")

    def close(self):
        if getattr(self, "handle", None):
            self.k.CloseHandle(self.handle)
            self.handle = None


def _gate() -> int:
    # Wait until the supervisor owns this process tree before launching any child.
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    child = subprocess.Popen(request["argv"], cwd=request["cwd"], stdin=subprocess.DEVNULL)
    atomic_json(Path(request["child_identity"]), {
        "pid": child.pid, "started_utc": datetime.now(timezone.utc).isoformat(),
        "argv": request["argv"], "cwd": request["cwd"],
    })
    return child.wait()


def run_bounded(argv: list[str], cwd: Path, output: Path, timeout: float) -> dict:
    if not argv or not all(isinstance(x, str) and x for x in argv) or not 0 < timeout <= 86400:
        raise LifecycleError("Invalid bounded command/deadline.")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc).isoformat()
    job = WindowsJob() if os.name == "nt" else None
    process = None
    timed_out = forced = False
    error = ""
    clean = False
    exit_code = None
    try:
        with (output / "stdout.bin").open("wb") as stdout, (output / "stderr.bin").open("wb") as stderr:
            process = subprocess.Popen(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--child-gate"],
                cwd=cwd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                start_new_session=os.name != "nt",
            )
            if job:
                job.assign(process)
            request = {"argv": argv, "cwd": str(cwd), "child_identity": str(output / "child.json")}
            process.stdin.write(json.dumps(request).encode("utf-8"))
            process.stdin.close()
            try:
                exit_code = process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = forced = True
                if job:
                    job.terminate()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                exit_code = process.returncode
            # A parent exiting while descendants remain is not a clean completion.
            if job:
                if job.active():
                    forced = True
                    job.terminate()
                deadline = time.monotonic() + 5
                while job.active() and time.monotonic() < deadline:
                    time.sleep(0.02)
                clean = job.active() == 0
            else:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    clean = True
                else:
                    forced = True
                    os.killpg(process.pid, signal.SIGKILL)
                    # Do not claim confirmed cleanup when descendants remain unobserved.
                    clean = False
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        forced = process is not None
        if job:
            try:
                job.terminate()
            except Exception:
                pass
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    finally:
        if job:
            job.close()
    receipt = {
        "argv": argv, "cwd": str(cwd), "started_utc": started_utc,
        "parent_pid": process.pid if process else None,
        "child": read_json(output / "child.json") if (output / "child.json").exists() else None,
        "exit_code": exit_code, "timeout_seconds": timeout,
        "elapsed_seconds": time.monotonic() - started,
        "timed_out": timed_out, "forced_termination": forced,
        "process_cleanup_confirmed": clean, "error": error,
        "streams": {name: {"path": str(output / (name + ".bin")), "sha256": digest(output / (name + ".bin"))}
                    for name in ("stdout", "stderr") if (output / (name + ".bin")).exists()},
    }
    atomic_json(output / "receipt.json", receipt)
    return receipt


def verify_receipt(path: Path) -> dict:
    receipt = read_json(path)
    for stream in receipt.get("streams", {}).values():
        if digest(Path(stream["path"])) != stream["sha256"]:
            raise LifecycleError("Recorded process output was modified.")
    if set(receipt.get("streams", {})) != {"stdout", "stderr"}:
        raise LifecycleError("Missing raw stdout/stderr evidence.")
    if receipt.get("exit_code") != 0 or receipt.get("timed_out") or receipt.get("forced_termination") or not receipt.get("process_cleanup_confirmed") or receipt.get("error"):
        raise LifecycleError("Command did not complete naturally with verified process cleanup.")
    return receipt


if __name__ == "__main__" and sys.argv[1:] == ["--child-gate"]:
    raise SystemExit(_gate())
