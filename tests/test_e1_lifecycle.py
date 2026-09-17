from __future__ import annotations

import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".birdai"))
from lifecycle_store import Store, LifecycleError, atomic_json, digest, read_json
from lifecycle_process import run_bounded, verify_receipt
from lifecycle_evidence import verify_summary
from lifecycle_engine import Engine, validate_plan
from lifecycle_github import GitHubPort
from e1_lifecycle import choose


def fixture(root):
    evidence = root / "evidence"
    evidence.mkdir()
    snapshot = root / "snapshot.json"
    atomic_json(snapshot, {"identity": "same-individual"})
    registration = root / "registration.json"
    reg = {"experiment": "test-paired-v1", "stage": "E1-E", "runtime_commit_at_registration": "a" * 40,
           "source_snapshot": {"path": str(snapshot), "sha256": digest(snapshot)},
           "seed_set": [17], "pairing": {"pairs": [{"seed": 17, "arms": ["left", "right"]}]},
           "hypothesis_result": {"values": ["SUPPORTED", "NOT_SUPPORTED", "SEED_SENSITIVE", "INCONCLUSIVE"]}}
    atomic_json(registration, reg)
    spec = {"experiment_id": reg["experiment"], "stage": "E1-E", "state": "registered", "execution_issue": 71,
            "predecessor_issue": 65, "registration_path": str(registration), "registration_sha256": digest(registration),
            "harness_path": "harness.py"}
    pair = {"seed": 17, "pair_validity": "PASS"}
    for arm in ("left", "right"):
        trace = evidence / (arm + ".jsonl")
        trace.write_text('{"tick": 1}\n', encoding="utf-8")
        capsule = evidence / (arm + ".json")
        atomic_json(capsule, {"runtime_commit": "a" * 40, "registration_sha256": spec["registration_sha256"],
                             "neural_seed": 17, "trace_path": str(trace), "trace_sha256": digest(trace)})
        pair[arm] = {"status": "PASS", "capsule_path": str(capsule), "capsule_sha256": digest(capsule)}
    comparison = evidence / "comparison.json"
    atomic_json(comparison, {
        "seed": 17,
        "pair_validity": "PASS",
        "left": {"status": "PASS"},
        "right": {"status": "PASS"},
    })
    pair.update(pair_comparison_path=str(comparison), pair_comparison_sha256=digest(comparison))
    summary = evidence / "summary.json"
    atomic_json(summary, {"stage": "E1-E", "stage_validity": "PASS", "runtime_commit": "a" * 40,
                         "registration_sha256": spec["registration_sha256"], "accepted_source_snapshot_sha256": digest(snapshot),
                         "seed_set": [17], "pair_count_declared": 1, "pair_count_completed": 1, "run_count_declared": 2,
                         "pairs": [pair], "hypothesis_result": "NOT_SUPPORTED", "production_runtime_mutation": "none",
                         "neural_policy_change": "none", "learning_rule_change": "none"})
    return spec, summary


class FakePort:
    def __init__(self, repo):
        self.repo = repo
        self.pr = None
        self.created = self.merged = self.closed = self.post_checks = 0
        self.states = {28: "OPEN", 65: "CLOSED", 71: "OPEN"}
        self.crash_after_create = self.crash_after_merge = self.crash_after_close = False
        self.identity = "apparatus-v1"
        self.ready_calls = 0

    def assert_ready(self, spec):
        self.ready_calls += 1

    def apparatus_identity(self, spec):
        return self.identity

    def ensure_pr(self, spec, record, folder):
        if self.pr is None:
            self.created += 1
            self.pr = {"number": 99, "url": "https://example.test/pull/99", "headRefOid": "b" * 40,
                       "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
                       "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]}
        if self.crash_after_create:
            self.crash_after_create = False
            raise LifecycleError("simulated crash after remote PR creation")
        return copy.deepcopy(self.pr)

    def pull(self, number):
        return copy.deepcopy(self.pr)

    def verify_pr(self, spec, record, pr):
        pass

    verify_checks = staticmethod(GitHubPort.verify_checks)

    def merge(self, pr):
        self.merged += 1
        self.pr.update(state="MERGED", mergeCommit={"oid": "c" * 40})
        if self.crash_after_merge:
            self.crash_after_merge = False
            raise LifecycleError("simulated lost merge response")

    def postmerge(self, spec, record, folder):
        self.post_checks += 1
        return {"verify-registry": "PASS", "status": "PASS"}

    def verify_postmerge(self, spec, record):
        if self.pr["state"] != "MERGED":
            raise LifecycleError("not merged")

    def issue_state(self, issue):
        return self.states[issue]

    def close_issue(self, issue):
        self.closed += 1
        self.states[issue] = "CLOSED"
        if self.crash_after_close:
            self.crash_after_close = False
            raise LifecycleError("simulated lost issue-close response")


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="birdai-lifecycle-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.spec, self.summary = fixture(self.root)
        self.store = Store(self.root / "state", "fixture/repo")
        self.fake_repo = self.root / "fake-repo"
        self.fake_repo.mkdir()
        self.port = FakePort(self.fake_repo)

    def engine(self, plan=None):
        return Engine(self.store, self.port, self.spec, plan)

    def to_pr(self):
        self.engine().advance(adopt_summary=self.summary)
        self.engine().advance()
        return self.engine().advance()

    def to_postmerge(self):
        record = self.to_pr()
        self.engine().advance(approve_merge=f"99:{'b' * 40}")
        self.engine().advance()
        return self.engine().advance()

    def test_full_lifecycle_restarts_at_every_step_and_stops_at_both_gates(self):
        self.assertEqual(self.engine().advance(adopt_summary=self.summary)["state"], "completed_valid")
        self.assertEqual(self.engine().advance()["state"], "result_verified")
        self.assertEqual(self.engine().advance()["state"], "acceptance_pr_open")
        gate = self.engine().advance()
        self.assertEqual(gate["human_gate"]["kind"], "merge")
        self.assertEqual(self.port.merged, 0)
        self.engine().advance(approve_merge=gate["human_gate"]["token"])
        self.assertEqual(self.engine().advance()["state"], "acceptance_merged")
        self.assertEqual(self.engine().advance()["state"], "postmerge_verified")
        gate = self.engine().advance()
        self.assertEqual(gate["human_gate"]["kind"], "issue_close")
        self.assertEqual(self.port.closed, 0)
        self.engine().advance(approve_close=gate["human_gate"]["token"])
        self.assertEqual(self.engine().advance()["state"], "execution_issue_closed")
        self.assertEqual(self.engine().advance()["state"], "waiting_for_human_registration")
        self.assertEqual(self.engine().advance()["state"], "waiting_for_human_registration")
        self.assertEqual((self.port.created, self.port.merged, self.port.closed), (1, 1, 1))

    def test_crash_after_pr_creation_does_not_duplicate_it(self):
        self.port.crash_after_create = True
        self.engine().advance(adopt_summary=self.summary)
        self.engine().advance()
        with self.assertRaises(LifecycleError):
            self.engine().advance()
        self.assertEqual(self.engine().advance()["state"], "acceptance_pr_open")
        self.assertEqual(self.port.created, 1)

    def test_lost_merge_response_is_reconciled_without_another_merge(self):
        self.to_pr()
        self.port.crash_after_merge = True
        with self.assertRaises(LifecycleError):
            self.engine().advance(approve_merge=f"99:{'b' * 40}")
        self.assertEqual(self.engine().advance()["state"], "acceptance_merged")
        self.assertEqual(self.port.merged, 1)

    def test_lost_close_response_is_reconciled_without_another_close(self):
        self.to_postmerge()
        self.port.crash_after_close = True
        with self.assertRaises(LifecycleError):
            self.engine().advance(approve_close=f"71:{'c' * 40}")
        self.assertEqual(self.engine().advance()["state"], "execution_issue_closed")
        self.assertEqual(self.port.closed, 1)

    def test_wrong_or_changed_head_cannot_use_merge_approval(self):
        self.to_pr()
        with self.assertRaises(LifecycleError):
            self.engine().advance(approve_merge=f"99:{'d' * 40}")
        self.port.pr["headRefOid"] = "d" * 40
        with self.assertRaises(LifecycleError):
            self.engine().advance(approve_merge=f"99:{'b' * 40}")
        self.assertEqual(self.port.merged, 0)

    def test_failed_ci_blocks_approved_merge(self):
        self.to_pr()
        self.port.pr["statusCheckRollup"][0]["conclusion"] = "FAILURE"
        with self.assertRaises(LifecycleError):
            self.engine().advance(approve_merge=f"99:{'b' * 40}")
        self.assertEqual(self.port.merged, 0)

    def test_saved_human_approval_survives_restart_before_remote_effect(self):
        self.to_pr()
        with patch.object(self.port, "merge", side_effect=LifecycleError("connection interrupted")):
            with self.assertRaises(LifecycleError):
                self.engine().advance(approve_merge=f"99:{'b' * 40}")
        self.engine().advance()
        self.assertEqual(self.port.merged, 1)
        self.assertEqual(self.engine().advance()["state"], "acceptance_merged")

    def test_changed_evidence_blocks_publication(self):
        self.engine().advance(adopt_summary=self.summary)
        self.engine().advance()
        (self.summary.parent / "left.jsonl").write_text("changed", encoding="utf-8")
        with self.assertRaises(LifecycleError):
            self.engine().advance()
        self.assertEqual(self.port.created, 0)

    def test_seed_loss_and_invalid_pair_are_rejected(self):
        value = read_json(self.summary)
        value["pairs"] = []
        atomic_json(self.summary, value)
        with self.assertRaises(LifecycleError):
            verify_summary(self.spec, self.summary)

    def test_not_supported_remains_valid_without_retuning(self):
        result = verify_summary(self.spec, self.summary)
        self.assertEqual(result["stage_validity"], "PASS")
        self.assertEqual(result["hypothesis_result"], "NOT_SUPPORTED")

    def test_hypothesis_qualified_stage_requires_matching_preregistration(self):
        registration = Path(self.spec["registration_path"])
        reg = read_json(registration)
        reg["hypothesis_id"] = "H2"
        atomic_json(registration, reg)
        self.spec["registration_sha256"] = digest(registration)
        summary = read_json(self.summary)
        summary["registration_sha256"] = self.spec["registration_sha256"]
        summary["stage"] = "E1-E-H2"
        for arm in ("left", "right"):
            path = Path(summary["pairs"][0][arm]["capsule_path"])
            capsule = read_json(path)
            capsule["registration_sha256"] = self.spec["registration_sha256"]
            atomic_json(path, capsule)
            summary["pairs"][0][arm]["capsule_sha256"] = digest(path)
        atomic_json(self.summary, summary)
        self.assertEqual(verify_summary(self.spec, self.summary)["stage_validity"], "PASS")
        summary["stage"] = "E1-E-H3"
        atomic_json(self.summary, summary)
        with self.assertRaises(LifecycleError):
            verify_summary(self.spec, self.summary)

    def test_lock_excludes_another_process(self):
        script = "from lifecycle_store import Store; from pathlib import Path; s=Store(Path(__import__('sys').argv[1]),'fixture/repo');\nwith s.lock(): print('acquired')"
        env = dict(os.environ, PYTHONPATH=str(ROOT / ".birdai"))
        with self.store.lock():
            cp = subprocess.run([sys.executable, "-B", "-c", script, str(self.root / "state")], env=env, capture_output=True, timeout=5)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn(b"Another lifecycle coordinator", cp.stderr)

    def test_interrupted_run_is_not_relaunched_and_retry_budget_survives(self):
        plan = {"preflight": {"argv": [sys.executable, "-c", "pass"], "timeout_seconds": 2},
                "run": {"argv": [sys.executable, "-c", "pass"], "timeout_seconds": 2}, "evidence_root": str(self.root)}
        record = self.engine(plan).load()
        record.update(state="running", attempts=1, run_receipt=str(self.root / "missing.json"))
        self.store.save(record)
        self.assertEqual(self.engine(plan).advance()["state"], "invalid_technical")
        self.assertEqual(self.engine(plan).advance()["state"], "invalid_technical")
        self.assertEqual(self.port.ready_calls, 0)
        self.engine(plan).authorize_correction(1, "Reviewed missing receipt and repaired apparatus")
        record = self.store.load(71)
        record.update(state="invalid_technical", attempts=2)
        self.store.save(record)
        with self.assertRaises(LifecycleError):
            self.engine(plan).authorize_correction(2, "Third try")

    def test_new_issue_cannot_bypass_unfinished_record(self):
        registry = {"schema": 1, "policy": {"phase": "E1", "auto_merge": False, "auto_issue_close": False, "require_human_registration": True}, "experiments": [self.spec]}
        with self.assertRaises(LifecycleError):
            choose(registry, [{"issue": 70, "state": "invalid_technical"}], self.port, 71)

    def test_real_preflight_and_run_receipts_advance_without_repeating(self):
        plan = {"preflight": {"argv": [sys.executable, "-c", "print('PREFLIGHT: PASS')"], "timeout_seconds": 5, "success_marker": "PREFLIGHT: PASS"},
                "run": {"argv": [sys.executable, "-c", f"print({('SUMMARY: ' + str(self.summary))!r})"], "timeout_seconds": 5},
                "evidence_root": str(self.summary.parent)}
        self.assertEqual(self.engine(plan).advance()["state"], "apparatus_preflight")
        self.assertEqual(self.engine(plan).advance()["state"], "ready_to_run")
        self.assertEqual(self.engine(plan).advance()["state"], "running")
        self.assertEqual(self.engine(plan).advance()["state"], "completed_valid")
        self.assertEqual(self.engine(plan).advance()["state"], "result_verified")
        self.assertEqual(self.store.load(71)["attempts"], 1)
        self.assertEqual(self.port.ready_calls, 2)

    def test_timeout_terminates_owned_descendant(self):
        pidfile = self.root / "grandchild.pid"
        child = "import time; time.sleep(20)"
        code = f"import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c',{child!r}]); Path({str(pidfile)!r}).write_text(str(p.pid)); time.sleep(20)"
        output = self.root / "timed-command"
        receipt = run_bounded([sys.executable, "-c", code], self.root, output, 1.5)
        self.assertTrue(receipt["timed_out"])
        self.assertTrue(receipt["forced_termination"])
        self.assertTrue(pidfile.exists())
        if os.name == "nt":
            self.assertTrue(receipt["process_cleanup_confirmed"])
        with self.assertRaises(LifecycleError):
            verify_receipt(output / "receipt.json")

    def test_receipt_detects_raw_log_tampering(self):
        output = self.root / "normal-command"
        run_bounded([sys.executable, "-c", "print('real output')"], self.root, output, 5)
        verify_receipt(output / "receipt.json")
        (output / "stdout.bin").write_bytes(b"replaced")
        with self.assertRaises(LifecycleError):
            verify_receipt(output / "receipt.json")

    def test_real_git_acceptance_publication_is_idempotent_and_scoped(self):
        repo, remote = self.root / "repo", self.root / "remote.git"
        repo.mkdir()
        def git(*args, cwd=repo):
            return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        git("init", "--initial-branch=main")
        git("config", "user.name", "Lifecycle Test")
        git("config", "user.email", "test@example.invalid")
        (repo / ".birdai").mkdir()
        (repo / ".birdai/governance.yaml").write_text("current_phase: E1\n", encoding="utf-8")
        (repo / ".birdai/e1_orchestrator.py").write_text("print('STATUS: PASS')\n", encoding="utf-8")
        (repo / "harness.py").write_text("pass\n", encoding="utf-8")
        atomic_json(repo / ".birdai/e1_experiments.json", {"schema": 1, "experiments": [self.spec]})
        git("add", ".")
        git("commit", "-m", "fixture baseline")
        git("init", "--bare", str(remote))
        git("remote", "add", "origin", str(remote))
        git("push", "-u", "origin", "main")
        baseline = git("rev-parse", "HEAD")

        class OfflinePort(GitHubPort):
            pr = None
            creates = 0
            issue_closed = False

            def gh(self, *args):
                if args[:2] == ("pr", "list"):
                    return json.dumps([] if self.pr is None else [{"number": 99}])
                if args[:2] == ("pr", "create"):
                    self.creates += 1
                    branch = args[args.index("--head") + 1]
                    head = self.git("rev-parse", branch)
                    git("--git-dir", str(remote), "update-ref", "refs/pull/99/head", head)
                    self.pr = {"number": 99, "url": "https://example.invalid/pull/99", "state": "OPEN",
                               "headRefName": branch, "headRefOid": head, "baseRefName": "main",
                               "isDraft": False, "mergeable": "MERGEABLE",
                               "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                               "body": Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8")}
                    return self.pr["url"]
                if args[:2] == ("pr", "merge"):
                    if args[args.index("--match-head-commit") + 1] != self.pr["headRefOid"]:
                        raise AssertionError("Unpinned merge")
                    git("merge", "--no-ff", "--no-edit", self.pr["headRefOid"])
                    git("push", "origin", "main")
                    self.pr.update(state="MERGED", mergeCommit={"oid": git("rev-parse", "HEAD")})
                    return "merged"
                if args[:2] == ("issue", "view"):
                    return json.dumps({"state": "CLOSED" if self.issue_closed else "OPEN"})
                if args[:2] == ("issue", "close"):
                    self.issue_closed = True
                    return "closed"
                raise AssertionError(args)

            def pull(self, number):
                return copy.deepcopy(self.pr)

        port = OfflinePort(repo, "fixture/repo")
        engine = Engine(self.store, port, self.spec)
        engine.advance(adopt_summary=self.summary)
        record = engine.advance()
        pr = port.ensure_pr(self.spec, record, engine.folder)
        self.assertEqual(port.ensure_pr(self.spec, record, engine.folder)["headRefOid"], pr["headRefOid"])
        self.assertEqual(port.creates, 1)
        self.assertEqual(git("rev-parse", "HEAD"), baseline)
        self.assertEqual(git("status", "--porcelain"), "")
        self.assertEqual(set(git("diff", "--name-only", baseline, pr["headRefOid"]).splitlines()),
                         {".birdai/e1_experiments.json", port.record_path(record)})
        self.assertNotIn("Closes #", pr["body"])
        engine.advance()
        engine.advance(approve_merge=f"99:{pr['headRefOid']}")
        self.assertEqual(engine.advance()["state"], "acceptance_merged")
        self.assertEqual(engine.advance()["state"], "postmerge_verified")
        gate = engine.advance()["human_gate"]
        self.assertFalse(port.issue_closed)
        self.assertEqual(gate["kind"], "issue_close")
        engine.advance(approve_close=gate["token"])
        self.assertEqual(engine.advance()["state"], "execution_issue_closed")
        self.assertEqual(engine.advance()["state"], "waiting_for_human_registration")


    def test_pair_comparison_semantic_identity_is_verified(self):
        summary = read_json(self.summary)
        pair = summary["pairs"][0]
        comparison_path = Path(pair["pair_comparison_path"])
        comparison = read_json(comparison_path)
        comparison["seed"] = 999
        atomic_json(comparison_path, comparison)
        pair["pair_comparison_sha256"] = digest(comparison_path)
        atomic_json(self.summary, summary)
        with self.assertRaisesRegex(LifecycleError, "Pair comparison identity/validity"):
            verify_summary(self.spec, self.summary)

    def test_evidence_root_must_be_outside_git_worktree(self):
        plan = {
            "preflight": {"argv": [sys.executable, "-c", "pass"], "timeout_seconds": 2},
            "run": {"argv": [sys.executable, "-c", "pass"], "timeout_seconds": 2},
            "evidence_root": str(self.fake_repo / "evidence"),
        }
        with self.assertRaisesRegex(LifecycleError, "outside the Git worktree"):
            validate_plan(plan, self.fake_repo)

    def test_registry_acceptance_must_match_verified_result(self):
        acceptance = verify_summary(self.spec, self.summary)
        record = {
            "acceptance": acceptance,
            "summary_sha256": acceptance["summary_sha256"],
            "summary_path": acceptance["summary_path"],
        }
        entry = {
            "state": "accepted",
            "registration_sha256": self.spec["registration_sha256"],
            "acceptance": {
                "stage_validity": "PASS",
                "hypothesis_result": "SUPPORTED",
                "summary_sha256": acceptance["summary_sha256"],
                "valid_pair_count": 1,
                "human_review_required_for_issue_close": True,
            },
        }
        with self.assertRaisesRegex(LifecycleError, "disagrees with verified evidence"):
            GitHubPort._verify_registry_acceptance(self.spec, record, entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
