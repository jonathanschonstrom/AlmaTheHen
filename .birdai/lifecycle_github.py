"""Git/GitHub effects for the E1 lifecycle, with inspect-before-create semantics."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from lifecycle_process import run_bounded, verify_receipt
from lifecycle_store import LifecycleError, atomic_json, digest, read_json


class GitHubPort:
    def __init__(self, repo: Path, slug: str):
        self.repo, self.slug = repo.resolve(), slug

    def command(self, argv, *, cwd=None, check=True):
        try:
            cp = subprocess.run(argv, cwd=cwd or self.repo, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LifecycleError(f"Command unavailable/inconclusive; inspect before resuming: {argv[0]}") from exc
        if check and cp.returncode:
            raise LifecycleError(f"Command failed ({cp.returncode}): {argv}\n{cp.stderr}")
        return cp

    def git(self, *args, cwd=None, check=True):
        return self.command(["git", *args], cwd=cwd, check=check).stdout.strip()

    def gh(self, *args):
        return self.command(["gh", *args, "--repo", self.slug]).stdout.strip()

    def issue_state(self, issue):
        value = json.loads(self.gh("issue", "view", str(issue), "--json", "state"))
        return value["state"].upper()

    def clean_main(self, sync=False):
        if self.git("branch", "--show-current") != "main":
            raise LifecycleError("Lifecycle effects require a clean main checkout; acceptance edits use a separate worktree.")
        if self.git("status", "--porcelain=v1", "--untracked-files=all"):
            raise LifecycleError("Repository has local work; it will not be overwritten.")
        if sync:
            self.git("fetch", "origin")
            self.git("merge", "--ff-only", "origin/main")
        return self.git("rev-parse", "HEAD")

    def assert_ready(self, spec):
        self.clean_main(sync=True)
        if not re.search(r"(?m)^current_phase:\s*E1\s*$", (self.repo / ".birdai/governance.yaml").read_text(encoding="utf-8")):
            raise LifecycleError("E1 is not the active phase.")
        registry = read_json(self.repo / ".birdai/e1_experiments.json")
        entries = registry["experiments"]
        claims = json.loads(self.gh("issue", "list", "--state", "open", "--label", "agent:working", "--json", "number"))
        if any(claim["number"] != spec["execution_issue"] for claim in claims):
            raise LifecycleError("Another repository issue is claimed by a worker.")
        if any(item["state"] in {"running", "review", "blocked"} and item["execution_issue"] != spec["execution_issue"] for item in entries):
            raise LifecycleError("Another E1 experiment is active or awaiting disposition.")
        predecessor = spec.get("predecessor_issue")
        prior = next((entry for entry in entries if entry["execution_issue"] == predecessor), None)
        if predecessor and (self.issue_state(predecessor) != "CLOSED" or (prior and prior["state"] != "accepted")):
            raise LifecycleError("Predecessor is not both accepted and closed.")
        if self.issue_state(28) != "OPEN" or self.issue_state(spec["execution_issue"]) != "OPEN":
            raise LifecycleError("E1 parent/execution issue is not open.")

    def apparatus_identity(self, spec):
        return {"head": self.git("rev-parse", "HEAD"), "harness": digest(self.repo / spec["harness_path"])}

    def pull(self, number):
        return json.loads(self.gh("pr", "view", str(number), "--json",
            "number,url,state,headRefOid,headRefName,baseRefName,body,isDraft,statusCheckRollup,mergeCommit,mergeable"))

    @staticmethod
    def record_path(record):
        return f".birdai/acceptance/issue-{record['issue']}-{record['summary_sha256'][:12]}.json"

    @staticmethod
    def branch(record):
        return f"acceptance/issue-{record['issue']}-{record['summary_sha256'][:12]}"


    @staticmethod
    def _expected_registry_acceptance(record):
        acceptance = record["acceptance"]
        expected = {
            "stage_validity": acceptance["stage_validity"],
            "hypothesis_result": acceptance["hypothesis_result"],
            "summary_sha256": record["summary_sha256"],
            "valid_pair_count": acceptance["valid_pair_count"],
            "human_review_required_for_issue_close": True,
        }
        summary = read_json(Path(record["summary_path"]))
        counts = summary.get("hypothesis_counts")
        if isinstance(counts, dict):
            for key, value in counts.items():
                if value is None or isinstance(value, (str, int, float, bool)):
                    expected[key] = value
        elif acceptance["hypothesis_result"] == "SEED_SENSITIVE":
            expected["seed_sensitivity"] = True
        return expected

    @classmethod
    def _verify_registry_acceptance(cls, spec, record, entry):
        if entry.get("state") != "accepted":
            raise LifecycleError("Registry entry is not accepted.")
        if entry.get("registration_sha256") != spec["registration_sha256"]:
            raise LifecycleError("Registry registration differs from the verified evidence.")
        actual = entry.get("acceptance")
        if not isinstance(actual, dict):
            raise LifecycleError("Registry acceptance record is missing.")
        expected = cls._expected_registry_acceptance(record)
        mismatches = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if mismatches:
            raise LifecycleError(f"Registry acceptance disagrees with verified evidence: {mismatches}")

    def ensure_pr(self, spec, record, folder):
        self.clean_main(sync=True)
        if record.get("adopt_pr"):
            pr = self.pull(record["adopt_pr"])
            self.verify_pr(spec, record, pr)
            return pr
        branch = self.branch(record)
        previous = json.loads(self.gh("pr", "list", "--head", branch, "--state", "all", "--json", "number"))
        if len(previous) > 1:
            raise LifecycleError("Multiple acceptance PRs share the deterministic branch.")
        if previous:
            pr = self.pull(previous[0]["number"])
            self.verify_pr(spec, record, pr)
            if pr["state"] == "CLOSED":
                raise LifecycleError("Existing acceptance PR was rejected/closed; no duplicate will be created.")
            return pr
        worktree = folder / "acceptance-worktree"
        if not worktree.exists():
            local = self.git("branch", "--list", branch)
            remote = self.git("branch", "-r", "--list", "origin/" + branch)
            if local:
                self.git("worktree", "add", str(worktree), branch)
            elif remote:
                self.git("worktree", "add", "-b", branch, str(worktree), "origin/" + branch)
            else:
                self.git("worktree", "add", "-b", branch, str(worktree), "origin/main")
        if self.git("branch", "--show-current", cwd=worktree) != branch:
            raise LifecycleError("Acceptance worktree belongs to another branch.")
        target = self.record_path(record)
        allowed = {".birdai/e1_experiments.json", target}
        dirty = set(self.git("diff", "--name-only", "HEAD", cwd=worktree).splitlines())
        dirty.update(self.git("ls-files", "--others", "--exclude-standard", cwd=worktree).splitlines())
        if dirty - allowed:
            raise LifecycleError("Unrelated work in acceptance worktree; preserve it and stop.")
        registry_path = worktree / ".birdai/e1_experiments.json"
        registry = read_json(registry_path)
        entries = [entry for entry in registry["experiments"] if entry["execution_issue"] == record["issue"]]
        if len(entries) != 1 or entries[0]["registration_sha256"] != spec["registration_sha256"]:
            raise LifecycleError("Acceptance registry entry changed identity.")
        acceptance = dict(record["acceptance"])
        acceptance["acceptance_record"] = target
        acceptance["evidence_path"] = str(Path(record["summary_path"]).parent)
        acceptance["seed_sensitivity"] = acceptance["hypothesis_result"] == "SEED_SENSITIVE"
        summary = read_json(Path(record["summary_path"]))
        acceptance.update(summary.get("hypothesis_counts", {}))
        entries[0]["state"] = "accepted"
        entries[0]["acceptance"] = {**entries[0].get("acceptance", {}), **acceptance}
        atomic_json(registry_path, registry)
        atomic_json(worktree / target, record["acceptance"])
        self.git("diff", "--check", cwd=worktree)
        self.git("add", "--", *sorted(allowed), cwd=worktree)
        staged = self.git("diff", "--cached", "--name-only", cwd=worktree).splitlines()
        if set(staged) - allowed:
            raise LifecycleError("Unexpected staged acceptance changes.")
        if staged:
            self.git("-c", "user.name=BirdAI Lifecycle", "-c", "user.email=birdai-lifecycle@users.noreply.github.com",
                     "commit", "-m", f"Record verified {spec['experiment_id']} result", cwd=worktree)
        self.git("push", "--set-upstream", "origin", branch, cwd=worktree)
        body = folder / "acceptance-pr.md"
        body.write_text(
            f"<!-- birdai-lifecycle:{record['issue']}:{record['summary_sha256']} -->\n\n"
            f"Records the verified {spec['experiment_id']} experiment. Refs #{record['issue']}.\n\n"
            f"Technical validity: PASS. Research outcome: **{record['acceptance']['hypothesis_result']}**.\n\n"
            f"Summary SHA-256: `{record['summary_sha256']}`.\n"
            "Review the retained evidence before approving this exact PR head.\n"
            "Issue closure requires a separate human approval after post-merge verification.\n",
            encoding="utf-8",
        )
        self.gh("pr", "create", "--head", branch, "--base", "main", "--title",
                f"Record verified {spec['experiment_id']} result", "--body-file", str(body))
        created = json.loads(self.gh("pr", "list", "--head", branch, "--state", "all", "--json", "number"))
        if len(created) != 1:
            raise LifecycleError("PR creation is inconclusive; re-run to inspect, not duplicate.")
        pr = self.pull(created[0]["number"])
        self.verify_pr(spec, record, pr)
        return pr

    def verify_pr(self, spec, record, pr):
        adopted_merged = bool(record.get("adopt_pr")) and pr["state"] == "MERGED"
        if pr["baseRefName"] != "main" or (not adopted_merged and pr["headRefName"] != self.branch(record)):
            raise LifecycleError("Acceptance PR does not target the expected branch/base.")
        marker = f"<!-- birdai-lifecycle:{record['issue']}:{record['summary_sha256']} -->"
        if not adopted_merged and (marker not in pr["body"] or re.search(r"\b(close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+(?:#|https://)", pr["body"], re.I)):
            raise LifecycleError("PR identity mismatch or automatic issue-closing keyword present.")
        self.git("fetch", "origin", f"refs/pull/{pr['number']}/head")
        if self.git("rev-parse", "FETCH_HEAD") != pr["headRefOid"]:
            raise LifecycleError("PR changed while being verified.")
        stored = record["acceptance"] if adopted_merged else json.loads(self.git("show", f"FETCH_HEAD:{self.record_path(record)}"))
        registry = json.loads(self.git("show", "FETCH_HEAD:.birdai/e1_experiments.json"))
        entry = next((x for x in registry["experiments"] if x["execution_issue"] == record["issue"]), {})
        if stored != record["acceptance"]:
            raise LifecycleError("PR does not contain the exact verified acceptance record.")
        self._verify_registry_acceptance(spec, record, entry)
        if not adopted_merged and pr["state"] != "MERGED":
            base = self.git("merge-base", "origin/main", "FETCH_HEAD")
            previous = json.loads(self.git("show", f"{base}:.birdai/e1_experiments.json"))
            previous_entries = previous.pop("experiments")
            candidate = dict(registry)
            candidate_entries = candidate.pop("experiments")
            if previous != candidate or [x for x in previous_entries if x["execution_issue"] != record["issue"]] != [x for x in candidate_entries if x["execution_issue"] != record["issue"]]:
                raise LifecycleError("PR changed other experiments or registry policy.")
            before_entry = next(x for x in previous_entries if x["execution_issue"] == record["issue"])
            if {k: v for k, v in before_entry.items() if k not in {"state", "acceptance"}} != {k: v for k, v in entry.items() if k not in {"state", "acceptance"}}:
                raise LifecycleError("PR changed the registered research apparatus or parameters.")
        changed = set(self.git("diff", "--name-only", "origin/main...FETCH_HEAD").splitlines())
        if pr["state"] != "MERGED" and changed != {self.record_path(record), ".birdai/e1_experiments.json"}:
            raise LifecycleError("Acceptance PR contains missing/unrelated changes.")

    @staticmethod
    def verify_checks(pr):
        if pr.get("isDraft") or pr.get("mergeable") != "MERGEABLE":
            raise LifecycleError("PR is draft or not confirmed mergeable.")
        checks = pr.get("statusCheckRollup") or []
        if not checks:
            raise LifecycleError("No CI evidence on the reviewed PR head.")
        for check in checks:
            if "conclusion" in check:
                good = str(check.get("status", "")).upper() == "COMPLETED" and str(check["conclusion"]).upper() in {"SUCCESS", "SKIPPED", "NEUTRAL"}
            else:
                good = check.get("state") == "SUCCESS"
            if not good:
                raise LifecycleError("CI has a pending, failing or inconclusive check.")

    def merge(self, pr):
        self.gh("pr", "merge", str(pr["number"]), "--merge", "--match-head-commit", pr["headRefOid"])

    def verify_postmerge(self, spec, record):
        self.clean_main(sync=True)
        pr = self.pull(record["pr"]["number"])
        if pr["state"] != "MERGED" or pr["mergeCommit"]["oid"] != record["merge_commit"] or pr["headRefOid"] != record["pr"]["headRefOid"]:
            raise LifecycleError("Merged PR identity changed.")
        self.git("merge-base", "--is-ancestor", record["merge_commit"], "HEAD")
        expected = record["acceptance"]
        if not record.get("adopt_pr") and read_json(self.repo / self.record_path(record)) != expected:
            raise LifecycleError("Main does not contain the verified acceptance record.")
        registry = read_json(self.repo / ".birdai/e1_experiments.json")
        entry = next((x for x in registry["experiments"] if x["execution_issue"] == record["issue"]), {})
        self._verify_registry_acceptance(spec, record, entry)
        for receipt in record.get("postmerge", {}).values():
            verify_receipt(Path(receipt))

    def postmerge(self, spec, record, folder):
        self.verify_postmerge(spec, record)
        receipts = {}
        for command in ("verify-registry", "status"):
            output = folder / ("postmerge-" + command + "-" + record["merge_commit"][:12])
            if not (output / "receipt.json").exists():
                if output.exists():
                    raise LifecycleError("Interrupted post-merge check needs review; it will not be silently repeated.")
                run_bounded([sys.executable, "-B", str(self.repo / ".birdai/e1_orchestrator.py"),
                             "--repo", str(self.repo), "--github-repo", self.slug, command], self.repo, output, 20)
            verify_receipt(output / "receipt.json")
            receipts[command] = str(output / "receipt.json")
        return receipts

    def close_issue(self, issue):
        # Never put a close keyword in the PR body; this is the separate third gate.
        self.gh("issue", "close", str(issue), "--reason", "completed")
