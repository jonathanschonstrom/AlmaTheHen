"""One verified lifecycle transition at a time; all external effects are restartable."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from lifecycle_evidence import verify_summary
from lifecycle_process import run_bounded, verify_receipt
from lifecycle_store import LifecycleError, Store, digest, read_json


STATES = (
    "registered", "apparatus_preflight", "ready_to_run", "running",
    "invalid_technical", "completed_valid", "result_verified", "acceptance_pr_open",
    "acceptance_merged", "postmerge_verified", "execution_issue_closed",
    "waiting_for_human_registration",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_plan(plan, repo: Path | None = None):
    for stage in ("preflight", "run"):
        command = plan.get(stage, {})
        if not isinstance(command.get("argv"), list) or not command["argv"] or not all(isinstance(x, str) and x for x in command["argv"]):
            raise LifecycleError(f"Missing explicit {stage} argv in approved lifecycle plan.")
        deadline = command.get("timeout_seconds")
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not 0 < deadline <= 86400:
            raise LifecycleError(f"Missing bounded {stage} deadline.")
        if deadline > 20 and not command.get("timeout_reason"):
            raise LifecycleError(f"A {stage} deadline over 20 seconds needs a recorded reason.")
    evidence_root = plan.get("evidence_root")
    if not evidence_root:
        raise LifecycleError("Lifecycle plan needs an evidence_root outside the repository.")
    if repo is not None:
        root = Path(evidence_root).resolve()
        worktree = Path(repo).resolve()
        if root == worktree or root.is_relative_to(worktree):
            raise LifecycleError("Lifecycle evidence_root must be outside the Git worktree.")


class Engine:
    def __init__(self, store: Store, port, spec: dict, plan: dict | None = None):
        self.store, self.port, self.spec = store, port, spec
        self.plan = plan or spec.get("lifecycle", {})
        self.issue = int(spec["execution_issue"])
        self.folder = store.root / f"issue-{self.issue}"

    def save_state(self, record, state, detail=""):
        if state not in STATES:
            raise LifecycleError("Unknown lifecycle state.")
        record.pop("human_gate", None)
        record["state"] = state
        record["history"].append({"state": state, "at": now(), "detail": detail})
        self.store.save(record)
        return record

    def load(self):
        record = self.store.load(self.issue)
        if record is None:
            record = {
                "schema": 1, "repo": self.store.slug, "issue": self.issue,
                "experiment_id": self.spec["experiment_id"],
                "registration_sha256": self.spec["registration_sha256"],
                "state": "registered", "attempts": 0, "history": [],
                "plan_hash": plan_hash(self.plan), "approvals": {},
            }
        if record["experiment_id"] != self.spec["experiment_id"] or record["registration_sha256"] != self.spec["registration_sha256"]:
            raise LifecycleError("Journal identity changed; do not reset an existing attempt ledger.")
        if record["plan_hash"] != plan_hash(self.plan):
            raise LifecycleError("Lifecycle plan changed; review and explicitly authorize a correction first.")
        return record

    def evidence(self, record):
        return verify_summary(self.spec, Path(record["summary_path"]), record.get("summary_sha256"))

    def _receipt(self, record, stage):
        path = Path(record[stage + "_receipt"])
        if not path.exists():
            raise LifecycleError("Interrupted command has no completed receipt; it will not be rerun automatically.")
        receipt = verify_receipt(path)
        if receipt["argv"] != self.plan[stage]["argv"] or Path(receipt["cwd"]).resolve() != self.port.repo.resolve():
            raise LifecycleError("Receipt belongs to a different command/workspace.")
        return receipt

    def _start(self, record, stage):
        validate_plan(self.plan, self.port.repo)
        self.port.assert_ready(self.spec)
        folder = self.folder / f"attempt-{record['attempts']}" / stage
        if folder.exists():
            raise LifecycleError("Attempt output already exists; refusing to overwrite or repeat it.")
        record[stage + "_receipt"] = str(folder / "receipt.json")
        record["apparatus_identity"] = self.port.apparatus_identity(self.spec)
        self.save_state(record, "apparatus_preflight" if stage == "preflight" else "running", "launch intent persisted")
        command = self.plan[stage]
        run_bounded(command["argv"], self.port.repo, folder, command["timeout_seconds"])
        return record

    def advance(self, *, approve_merge="", approve_close="", adopt_summary=None, adopt_pr=None):
        record = self.load()
        # Re-check the immutable registration on every continuation, including human gates.
        if digest(Path(self.spec["registration_path"])) != record["registration_sha256"]:
            raise LifecycleError("Preregistration changed since dispatch.")
        state = record["state"]
        if adopt_summary is not None:
            if state != "registered":
                raise LifecycleError("A manual result can only be adopted before this lifecycle starts.")
            evidence = verify_summary(self.spec, Path(adopt_summary))
            record.update(summary_path=evidence["summary_path"], summary_sha256=evidence["summary_sha256"],
                          adopted_manual_result=True)
            if adopt_pr:
                record["adopt_pr"] = int(adopt_pr)
            return self.save_state(record, "completed_valid", "existing evidence verified; no experiment rerun")
        if state == "registered":
            if record["attempts"] >= 2:
                raise LifecycleError("Two-attempt budget exhausted; no automatic reset is permitted.")
            record["attempts"] += 1
            return self._start(record, "preflight")
        if state in {"apparatus_preflight", "running"}:
            stage = "preflight" if state == "apparatus_preflight" else "run"
            try:
                receipt = self._receipt(record, stage)
                if self.port.apparatus_identity(self.spec) != record["apparatus_identity"]:
                    raise LifecycleError("Apparatus changed during the recorded command.")
                if stage == "preflight":
                    marker = self.plan["preflight"].get("success_marker")
                    output = Path(receipt["streams"]["stdout"]["path"]).read_text(encoding="utf-8", errors="replace")
                    if marker and marker not in output.splitlines():
                        raise LifecycleError("Required apparatus-preflight evidence is absent.")
                    return self.save_state(record, "ready_to_run")
                output = Path(receipt["streams"]["stdout"]["path"]).read_text(encoding="utf-8", errors="replace")
                summaries = {line[len("SUMMARY:"):].strip() for line in output.splitlines() if line.startswith("SUMMARY:")}
                if len(summaries) != 1:
                    raise LifecycleError("Run must identify exactly one retained SUMMARY path.")
                path = Path(summaries.pop()).resolve(strict=True)
                if not path.is_relative_to(Path(self.plan["evidence_root"]).resolve()):
                    raise LifecycleError("Run summary is outside the approved evidence root.")
                record.update(summary_path=str(path), summary_sha256=digest(path))
                self.evidence(record)
                return self.save_state(record, "completed_valid")
            except (LifecycleError, OSError, ValueError, KeyError) as exc:
                return self.save_state(record, "invalid_technical", str(exc))
        if state == "ready_to_run":
            self._receipt(record, "preflight")
            if self.port.apparatus_identity(self.spec) != record["apparatus_identity"]:
                return self.save_state(record, "invalid_technical", "Apparatus changed after preflight.")
            return self._start(record, "run")
        if state == "invalid_technical":
            return record
        if state == "completed_valid":
            record["acceptance"] = self.evidence(record)
            return self.save_state(record, "result_verified")
        if state == "result_verified":
            self.evidence(record)
            # ensure_pr uses a deterministic branch and inspects existing commits/PRs first.
            record["pr"] = self.port.ensure_pr(self.spec, record, self.folder)
            return self.save_state(record, "acceptance_pr_open")
        if state == "acceptance_pr_open":
            self.evidence(record)
            pr = self.port.pull(record["pr"]["number"])
            self.port.verify_pr(self.spec, record, pr)
            if pr["headRefOid"] != record["pr"]["headRefOid"]:
                raise LifecycleError("PR head changed; prior review approval no longer applies.")
            if pr["state"] == "MERGED":
                record["merge_commit"] = pr["mergeCommit"]["oid"]
                return self.save_state(record, "acceptance_merged", "merge confirmed by GitHub")
            if pr["state"] != "OPEN":
                raise LifecycleError("Acceptance PR was closed without merge; human disposition is required.")
            token = f"{pr['number']}:{pr['headRefOid']}"
            approve_merge = approve_merge or record.get("approvals", {}).get("merge", {}).get("token", "")
            if not approve_merge:
                record["human_gate"] = {"kind": "merge", "token": token, "url": pr["url"]}
                self.store.save(record)
                return record
            if approve_merge != token:
                raise LifecycleError("Merge approval does not match the exact PR/head.")
            self.port.verify_checks(pr)
            if record.get("merge_requests", 0) >= 2:
                raise LifecycleError("Merge request remains inconclusive after two attempts; coordinator review required.")
            record["merge_requests"] = record.get("merge_requests", 0) + 1
            record["approvals"]["merge"] = {"token": token, "at": now()}
            self.store.save(record)  # persist permission/intent before the remote mutation
            self.port.merge(pr)
            # Re-read on the next transition; a timed-out merge request is never blindly repeated.
            return record
        if state == "acceptance_merged":
            self.evidence(record)
            record["postmerge"] = self.port.postmerge(self.spec, record, self.folder)
            return self.save_state(record, "postmerge_verified")
        if state == "postmerge_verified":
            self.evidence(record)
            self.port.verify_postmerge(self.spec, record)
            if self.port.issue_state(self.issue) == "CLOSED":
                return self.save_state(record, "execution_issue_closed", "issue closure confirmed by GitHub")
            token = f"{self.issue}:{record['merge_commit']}"
            approve_close = approve_close or record.get("approvals", {}).get("issue_close", {}).get("token", "")
            if not approve_close:
                record["human_gate"] = {"kind": "issue_close", "token": token}
                self.store.save(record)
                return record
            if approve_close != token:
                raise LifecycleError("Issue-close approval does not match the verified issue/merge.")
            if record.get("close_requests", 0) >= 2:
                raise LifecycleError("Issue-close request remains inconclusive after two attempts; coordinator review required.")
            record["close_requests"] = record.get("close_requests", 0) + 1
            record["approvals"]["issue_close"] = {"token": token, "at": now()}
            self.store.save(record)
            self.port.close_issue(self.issue)
            return record
        if state == "execution_issue_closed":
            self.port.verify_postmerge(self.spec, record)
            if self.port.issue_state(self.issue) != "CLOSED":
                raise LifecycleError("Execution issue was reopened; human review is required.")
            return self.save_state(record, "waiting_for_human_registration")
        if state == "waiting_for_human_registration":
            return record
        raise LifecycleError(f"Unsupported persisted state: {state}")

    def authorize_correction(self, previous_attempt: int, reason: str):
        record = self.store.load(self.issue)
        if not record or record["state"] != "invalid_technical" or previous_attempt != record["attempts"] or not reason.strip():
            raise LifecycleError("A correction needs the failed attempt identity and a human review reason.")
        if record["attempts"] >= 2 or record["registration_sha256"] != self.spec["registration_sha256"]:
            raise LifecycleError("Budget exhausted or research registration changed; cannot authorize a retry.")
        validate_plan(self.plan, self.port.repo)
        record["plan_hash"] = plan_hash(self.plan)
        record["approvals"]["correction"] = {"attempt": previous_attempt, "reason": reason, "at": now()}
        return self.save_state(record, "registered", "reviewed correction authorized; previous evidence retained")
