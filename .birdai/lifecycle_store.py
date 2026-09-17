"""Durable, process-locked lifecycle records. No experiment is inferred from a log marker."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path


class LifecycleError(RuntimeError):
    pass


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise LifecycleError(f"Cannot read {path}: {exc}") from exc


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Store:
    def __init__(self, root: Path, slug: str):
        key = hashlib.sha256(slug.lower().encode()).hexdigest()[:20]
        self.root = root.resolve() / key
        self.root.mkdir(parents=True, exist_ok=True)
        self.slug = slug

    @contextmanager
    def lock(self):
        # Kernel locks release on process death. Never remove the lock inode.
        with (self.root / "coordinator.lock").open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise LifecycleError("Another lifecycle coordinator owns this repository.") from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self, issue: int):
        path = self.root / f"issue-{issue}.json"
        if not path.exists():
            return None
        value = read_json(path)
        if value.get("schema") != 1 or value.get("repo") != self.slug or value.get("issue") != issue:
            raise LifecycleError("Lifecycle journal identity/schema mismatch.")
        return value

    def save(self, record: dict):
        atomic_json(self.root / f"issue-{record['issue']}.json", record)

    def records(self):
        return [read_json(path) for path in self.root.glob("issue-*.json")]
