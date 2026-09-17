"""Resume BirdAI's registered experiment lifecycle, stopping at explicit human gates."""
from __future__ import annotations

import argparse
import json
import os
from contextlib import nullcontext
from pathlib import Path

from lifecycle_engine import Engine
from lifecycle_github import GitHubPort
from lifecycle_store import LifecycleError, Store, read_json


def choose(registry, records, port, issue=None):
    entries = registry.get("experiments", [])
    policy = registry.get("policy", {})
    if registry.get("schema") != 1 or policy.get("phase") != "E1" or policy.get("auto_merge") is not False or policy.get("auto_issue_close") is not False or policy.get("require_human_registration") is not True:
        raise LifecycleError("Registry policy does not preserve the required human gates.")
    active = [r for r in records if r["state"] != "waiting_for_human_registration"]
    if len(active) > 1:
        raise LifecycleError("Multiple unfinished lifecycle records; coordinator reconciliation required.")
    if active:
        if issue is not None and issue != active[0]["issue"]:
            raise LifecycleError("Finish or explicitly dispose of the active experiment first.")
        issue = active[0]["issue"]
    if issue is not None:
        matches = [x for x in entries if x["execution_issue"] == issue]
        if len(matches) != 1:
            raise LifecycleError("Requested issue is not uniquely registered.")
        return matches[0]
    for entry in entries:
        if entry["state"] in {"running", "review", "blocked"}:
            raise LifecycleError("An unmanaged experiment needs review/import before new work starts.")
        if entry["state"] == "accepted":
            if port.issue_state(entry["execution_issue"]) != "CLOSED":
                raise LifecycleError("Accepted experiment still has an open issue; adopt its verified result/PR first.")
            continue
        if entry["state"] == "registered":
            return entry
    return None


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path(os.environ.get("BIRDAI_REPO", "C:/AlmaTheHen")))
    p.add_argument("--github-repo", default="jonathanschonstrom/AlmaTheHen")
    p.add_argument("--state-dir", type=Path, default=Path(os.environ.get("BIRDAI_LIFECYCLE_STATE", str(Path.home() / "AppData/Local/BirdAI/lifecycle"))))
    p.add_argument("--issue", type=int)
    p.add_argument("--status", action="store_true", help="Inspect registry/journal only; no execution or publication")
    p.add_argument("--until-gate", action="store_true", help="Advance verified steps until a human gate or technical failure")
    p.add_argument("--approve-merge", default="", metavar="PR:HEAD_SHA")
    p.add_argument("--approve-close", default="", metavar="ISSUE:MERGE_SHA")
    p.add_argument("--adopt-summary", type=Path, help="Verify a manually completed experiment instead of rerunning it")
    p.add_argument("--adopt-pr", type=int)
    p.add_argument("--authorize-correction", type=int, metavar="FAILED_ATTEMPT")
    p.add_argument("--reason", default="")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    repo = args.repo.resolve()
    root = args.state_dir.resolve()
    if root.is_relative_to(repo):
        raise LifecycleError("Lifecycle state/evidence must be outside the Git worktree.")
    if args.approve_close and args.approve_merge:
        raise LifecycleError("Merge and issue closure require separate review decisions.")
    if args.adopt_pr and not args.adopt_summary:
        raise LifecycleError("Adopting a PR also requires verification of its retained summary.")
    port = GitHubPort(repo, args.github_repo)
    store = Store(root, args.github_repo)
    with (nullcontext() if args.status else store.lock()):
        registry = read_json(repo / ".birdai/e1_experiments.json")
        spec = choose(registry, store.records(), port, args.issue)
        if spec is None:
            print(json.dumps({"state": "waiting_for_human_registration", "next_step": "Preregister the next research hypothesis", "state_directory": str(store.root)}, indent=2))
            return 0
        engine = Engine(store, port, spec)
        if args.status:
            record = engine.load()
        elif args.authorize_correction is not None:
            record = engine.authorize_correction(args.authorize_correction, args.reason)
        else:
            merge, close = args.approve_merge, args.approve_close
            for step in range(20 if args.until_gate else 1):
                before = engine.load()["state"]
                print(f"[LIFECYCLE {step + 1}] issue={engine.issue} state={before}", flush=True)
                record = engine.advance(approve_merge=merge, approve_close=close,
                                        adopt_summary=args.adopt_summary if step == 0 else None,
                                        adopt_pr=args.adopt_pr if step == 0 else None)
                if record["state"] in {"invalid_technical", "waiting_for_human_registration"}:
                    break
                same = before == record["state"]
                if same and not (merge or close):
                    break
                # Approval is one-shot; another loop first observes the remote outcome.
                merge = close = ""
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 2 if record["state"] == "invalid_technical" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LifecycleError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
