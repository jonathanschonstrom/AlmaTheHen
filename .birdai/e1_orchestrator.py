from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REPO = Path(os.environ.get("BIRDAI_REPO", r"C:\AlmaTheHen"))
DEFAULT_SLUG = os.environ.get(
    "BIRDAI_GITHUB_REPO", "jonathanschonstrom/AlmaTheHen"
)
REGISTRY_REL = Path(".birdai/e1_experiments.json")
PARENT_ISSUE = 28


class OrchestratorError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclasses.dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    stage: str
    state: str
    execution_issue: int
    predecessor_issue: int | None
    registration_path: str
    registration_sha256: str
    harness_path: str
    command: list[str]
    expected_runtime_parent: str | None
    auto_push_pr: bool
    allow_issue_close: bool

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ExperimentSpec":
        required = {
            "experiment_id",
            "stage",
            "state",
            "execution_issue",
            "registration_path",
            "registration_sha256",
            "harness_path",
            "command",
        }
        missing = sorted(required - set(value))
        if missing:
            raise OrchestratorError(
                f"Experiment entry missing required fields: {missing}"
            )
        command = value["command"]
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item for item in command
        ):
            raise OrchestratorError(
                f"{value.get('experiment_id')}: command must be a non-empty string list"
            )
        registration_sha = str(value["registration_sha256"]).lower()
        if (
            len(registration_sha) != 64
            or any(ch not in "0123456789abcdef" for ch in registration_sha)
        ):
            raise OrchestratorError(
                f"{value.get('experiment_id')}: invalid registration SHA-256"
            )
        state = str(value["state"])
        if state not in {
            "registered",
            "running",
            "review",
            "accepted",
            "blocked",
            "rejected",
        }:
            raise OrchestratorError(
                f"{value.get('experiment_id')}: unsupported state {state!r}"
            )
        return cls(
            experiment_id=str(value["experiment_id"]),
            stage=str(value["stage"]),
            state=state,
            execution_issue=int(value["execution_issue"]),
            predecessor_issue=(
                None
                if value.get("predecessor_issue") is None
                else int(value["predecessor_issue"])
            ),
            registration_path=str(value["registration_path"]),
            registration_sha256=registration_sha,
            harness_path=str(value["harness_path"]),
            command=list(command),
            expected_runtime_parent=(
                None
                if value.get("expected_runtime_parent") in (None, "")
                else str(value["expected_runtime_parent"])
            ),
            auto_push_pr=bool(value.get("auto_push_pr", False)),
            allow_issue_close=bool(value.get("allow_issue_close", False)),
        )


def run(
    args: Iterable[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int | float | None = None,
) -> CommandResult:
    argv = [str(arg) for arg in args]
    cp = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    result = CommandResult(cp.returncode, cp.stdout, cp.stderr)
    if check and result.returncode != 0:
        raise OrchestratorError(
            f"Command failed ({result.returncode}): {' '.join(argv)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OrchestratorError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrchestratorError(f"Invalid JSON {path}: {exc}") from exc


def load_registry(repo: Path) -> list[ExperimentSpec]:
    path = repo / REGISTRY_REL
    root = load_json(path)
    if not isinstance(root, dict):
        raise OrchestratorError("E1 registry root must be an object.")
    if root.get("schema") != 1:
        raise OrchestratorError(
            f"Unsupported E1 registry schema: {root.get('schema')!r}"
        )
    raw = root.get("experiments")
    if not isinstance(raw, list):
        raise OrchestratorError("E1 registry experiments must be a list.")
    specs = [ExperimentSpec.from_mapping(item) for item in raw]
    ids = [spec.experiment_id for spec in specs]
    if len(ids) != len(set(ids)):
        raise OrchestratorError("Duplicate experiment_id in E1 registry.")
    return specs


def current_phase(repo: Path) -> str:
    governance = (repo / ".birdai/governance.yaml").read_text(encoding="utf-8")
    for raw in governance.splitlines():
        line = raw.strip()
        if line.startswith("current_phase:"):
            return line.split(":", 1)[1].strip()
    raise OrchestratorError("Could not find current_phase in governance.yaml.")


def require_clean_main(repo: Path) -> tuple[str, str]:
    branch = run(["git", "branch", "--show-current"], cwd=repo).stdout.strip()
    if branch != "main":
        raise OrchestratorError(
            f"Orchestrator requires main before selecting work; found {branch!r}."
        )
    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
    ).stdout
    if status:
        raise OrchestratorError("Repository is not clean:\n" + status)
    run(["git", "fetch", "origin"], cwd=repo)
    head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    origin = run(["git", "rev-parse", "origin/main"], cwd=repo).stdout.strip()
    if head != origin:
        raise OrchestratorError(f"HEAD != origin/main: {head} != {origin}")
    return head, origin


def gh_issue_state(repo: Path, slug: str, issue: int) -> str:
    return run(
        [
            "gh",
            "issue",
            "view",
            str(issue),
            "--repo",
            slug,
            "--json",
            "state",
            "--jq",
            ".state",
        ],
        cwd=repo,
    ).stdout.strip().upper()


def gh_issue_title(repo: Path, slug: str, issue: int) -> str:
    return run(
        [
            "gh",
            "issue",
            "view",
            str(issue),
            "--repo",
            slug,
            "--json",
            "title",
            "--jq",
            ".title",
        ],
        cwd=repo,
    ).stdout.strip()


def validate_spec_files(repo: Path, spec: ExperimentSpec) -> None:
    registration = Path(spec.registration_path)
    if not registration.is_absolute():
        registration = repo / registration
    if not registration.is_file():
        raise OrchestratorError(
            f"{spec.experiment_id}: registration missing: {registration}"
        )
    actual_sha = sha256_file(registration)
    if actual_sha.lower() != spec.registration_sha256.lower():
        raise OrchestratorError(
            f"{spec.experiment_id}: registration SHA mismatch: "
            f"{actual_sha} != {spec.registration_sha256}"
        )

    harness = Path(spec.harness_path)
    if not harness.is_absolute():
        harness = repo / harness
    if not harness.is_file():
        raise OrchestratorError(
            f"{spec.experiment_id}: harness missing: {harness}"
        )


def accepted(spec: ExperimentSpec, repo: Path, slug: str) -> bool:
    return (
        spec.state == "accepted"
        and gh_issue_state(repo, slug, spec.execution_issue) == "CLOSED"
    )


def select_next(
    specs: list[ExperimentSpec],
    repo: Path,
    slug: str,
) -> ExperimentSpec | None:
    for spec in specs:
        if accepted(spec, repo, slug):
            continue
        if spec.state != "registered":
            continue
        if (
            spec.predecessor_issue is not None
            and gh_issue_state(repo, slug, spec.predecessor_issue) != "CLOSED"
        ):
            continue
        if gh_issue_state(repo, slug, spec.execution_issue) != "OPEN":
            continue
        return spec
    return None


def registry_summary(
    specs: list[ExperimentSpec],
    repo: Path,
    slug: str,
) -> list[dict[str, Any]]:
    rows = []
    for spec in specs:
        rows.append(
            {
                "experiment_id": spec.experiment_id,
                "stage": spec.stage,
                "registry_state": spec.state,
                "execution_issue": spec.execution_issue,
                "issue_state": gh_issue_state(
                    repo, slug, spec.execution_issue
                ),
                "predecessor_issue": spec.predecessor_issue,
            }
        )
    return rows


def print_status(repo: Path, slug: str) -> int:
    if current_phase(repo) != "E1":
        raise OrchestratorError("Governance current phase is not E1.")
    head, _ = require_clean_main(repo)
    parent_state = gh_issue_state(repo, slug, PARENT_ISSUE)
    specs = load_registry(repo)
    rows = registry_summary(specs, repo, slug)
    next_spec = select_next(specs, repo, slug)

    print("STATUS: PASS")
    print("CURRENT_PHASE: E1")
    print(f"MAIN_COMMIT: {head}")
    print(f"PARENT_ISSUE_28: {parent_state}")
    print("REGISTRY:")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if next_spec is None:
        print("NEXT_REGISTERED_EXPERIMENT: NONE")
        print("HUMAN_REGISTRATION_REQUIRED: YES")
    else:
        print(f"NEXT_REGISTERED_EXPERIMENT: {next_spec.experiment_id}")
        print(f"NEXT_STAGE: {next_spec.stage}")
        print(f"NEXT_EXECUTION_ISSUE: #{next_spec.execution_issue}")
        print("HUMAN_REGISTRATION_REQUIRED: NO")
    return 0


def run_next(repo: Path, slug: str, dry_run: bool) -> int:
    if current_phase(repo) != "E1":
        raise OrchestratorError("Governance current phase is not E1.")
    head, _ = require_clean_main(repo)
    if gh_issue_state(repo, slug, PARENT_ISSUE) != "OPEN":
        raise OrchestratorError("Parent E1 design issue #28 is not open.")

    specs = load_registry(repo)
    spec = select_next(specs, repo, slug)
    if spec is None:
        print("STATUS: BLOCKED")
        print("BLOCKER: NO_REGISTERED_ELIGIBLE_EXPERIMENT")
        print("CURRENT_PHASE: E1")
        print(f"MAIN_COMMIT: {head}")
        print("HUMAN_REGISTRATION_REQUIRED: YES")
        print(
            "NEXT_DESIGN_BOUNDARY: register the next E1 stage before execution; "
            "the orchestrator will not invent seeds, variables, or hypotheses."
        )
        return 2

    validate_spec_files(repo, spec)
    title = gh_issue_title(repo, slug, spec.execution_issue)

    print("ORCHESTRATION_PREFLIGHT: PASS")
    print(f"EXPERIMENT: {spec.experiment_id}")
    print(f"STAGE: {spec.stage}")
    print(f"EXECUTION_ISSUE: #{spec.execution_issue} {title}")
    print(f"MAIN_COMMIT: {head}")
    print("REGISTRATION: VERIFIED")
    print("PREDECESSOR_GATE: PASS")
    print("REPOSITORY_GATE: PASS")
    print("AUTO_MERGE: NO")
    print("AUTO_ISSUE_CLOSE: NO")

    if dry_run:
        print("DRY_RUN: YES")
        print("COMMAND: " + json.dumps(spec.command, ensure_ascii=False))
        print("HUMAN_REVIEW_REQUIRED: YES")
        return 0

    if spec.auto_push_pr:
        raise OrchestratorError(
            f"{spec.experiment_id}: registry requests auto_push_pr=true, "
            "but v1 deliberately forbids that capability."
        )
    if spec.allow_issue_close:
        raise OrchestratorError(
            f"{spec.experiment_id}: registry requests allow_issue_close=true, "
            "but v1 deliberately forbids that capability."
        )

    result = run(
        spec.command,
        cwd=repo,
        check=False,
        timeout=None,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    print(f"EXPERIMENT_EXIT_CODE: {result.returncode}")
    print("MERGE: NOT PERFORMED")
    print("ISSUE_CLOSE: NOT PERFORMED")
    print("HUMAN_REVIEW_REQUIRED: YES")
    return result.returncode


def verify_registry(repo: Path, slug: str) -> int:
    specs = load_registry(repo)
    for spec in specs:
        if spec.state in {"registered", "running", "review"}:
            validate_spec_files(repo, spec)
        if spec.predecessor_issue == spec.execution_issue:
            raise OrchestratorError(
                f"{spec.experiment_id}: predecessor cannot equal execution issue"
            )
        if spec.auto_push_pr or spec.allow_issue_close:
            raise OrchestratorError(
                f"{spec.experiment_id}: unsafe automation flag enabled"
            )
    print("STATUS: PASS")
    print(f"REGISTRY_ENTRIES: {len(specs)}")
    print("REGISTRATION_HASHES: VERIFIED")
    print("AUTO_MERGE: DISABLED")
    print("AUTO_ISSUE_CLOSE: DISABLED")
    print("RESEARCH_PARAMETER_INVENTION: DISABLED")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Conservative E1 experiment orchestrator."
    )
    parser.add_argument(
        "--repo",
        default=str(DEFAULT_REPO),
        help="AlmaTheHen repository path",
    )
    parser.add_argument(
        "--github-repo",
        default=DEFAULT_SLUG,
        help="GitHub owner/repository",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("verify-registry")

    run_next_parser = sub.add_parser("run-next")
    run_next_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the next registered experiment without running it.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        raise OrchestratorError(f"Repository does not exist: {repo}")

    if args.command == "status":
        return print_status(repo, args.github_repo)
    if args.command == "verify-registry":
        return verify_registry(repo, args.github_repo)
    if args.command == "run-next":
        return run_next(repo, args.github_repo, args.dry_run)
    raise OrchestratorError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OrchestratorError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
