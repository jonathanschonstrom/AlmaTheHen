from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / ".birdai" / "e1_orchestrator.py"
REGISTRY = ROOT / ".birdai" / "e1_experiments.json"


def load_module():
    spec = importlib.util.spec_from_file_location("e1_orchestrator", ORCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestE1Orchestrator(unittest.TestCase):
    def test_registry_is_conservative_and_h1a_is_accepted(self):
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["policy"]["phase"], "E1")
        self.assertEqual(data["policy"]["parent_issue"], 28)
        self.assertIs(data["policy"]["auto_merge"], False)
        self.assertIs(data["policy"]["auto_issue_close"], False)
        self.assertIs(data["policy"]["invent_research_parameters"], False)
        self.assertIs(data["policy"]["require_human_registration"], True)

        experiments = data["experiments"]
        self.assertEqual(len(experiments), 4)
        h1a = experiments[0]
        self.assertEqual(h1a["experiment_id"], "E1-B-H1a-resource-distance-v1")
        self.assertEqual(h1a["stage"], "E1-B")
        self.assertEqual(h1a["state"], "accepted")
        self.assertEqual(h1a["execution_issue"], 59)
        self.assertEqual(h1a["predecessor_issue"], 32)
        self.assertIs(h1a["auto_push_pr"], False)
        self.assertIs(h1a["allow_issue_close"], False)

        e1c = experiments[1]
        self.assertEqual(e1c["experiment_id"], "E1-C-H1a-seed-replication-v1")
        self.assertEqual(e1c["stage"], "E1-C")
        self.assertEqual(e1c["state"], "accepted")
        self.assertEqual(e1c["acceptance"]["stage_validity"], "PASS")
        self.assertEqual(e1c["acceptance"]["replication_result"], "SEED_SENSITIVE")
        self.assertEqual(e1c["acceptance"]["valid_pair_count"], 5)
        self.assertEqual(e1c["acceptance"]["support_count"], 5)
        self.assertEqual(e1c["acceptance"]["opposite_count"], 2)
        self.assertIs(e1c["acceptance"]["seed_sensitivity"], True)
        self.assertEqual(e1c["execution_issue"], 62)
        self.assertEqual(e1c["predecessor_issue"], 59)
        self.assertIs(e1c["auto_push_pr"], False)
        self.assertIs(e1c["allow_issue_close"], False)
        e1d = experiments[2]
        self.assertEqual(e1d["experiment_id"], "E1-D-H1b-resource-density-v1")
        self.assertEqual(e1d["stage"], "E1-D")
        self.assertEqual(e1d["state"], "accepted")
        self.assertEqual(e1d["acceptance"]["stage_validity"], "PASS")
        self.assertEqual(e1d["acceptance"]["hypothesis_result"], "SEED_SENSITIVE")
        self.assertEqual(e1d["acceptance"]["summary_sha256"], "c068003a5eb471ff6b92f7edf897f2b0dd1a83098fe65d9d91ccb28b7d00b002")
        self.assertEqual(e1d["acceptance"]["valid_pair_count"], 5)
        self.assertEqual(e1d["acceptance"]["support_count"], 4)
        self.assertEqual(e1d["acceptance"]["opposite_count"], 4)
        self.assertEqual(e1d["acceptance"]["neutral_pair_count"], 0)
        self.assertIs(e1d["acceptance"]["seed_sensitivity"], True)
        self.assertIs(e1d["acceptance"]["invalid_first_attempt_retained"], True)
        self.assertIs(e1d["acceptance"]["human_review_required_for_issue_close"], True)
        self.assertEqual(e1d["execution_issue"], 65)
        self.assertEqual(e1d["predecessor_issue"], 62)
        self.assertEqual(
            e1d["registration_sha256"],
            "b35a58950e1ba12f2e6006b817cbaa04d16926baca0d37272f04cbe8f0c0a88c",
        )
        self.assertIs(e1d["auto_push_pr"], False)
        self.assertIs(e1d["allow_issue_close"], False)

        e1e = experiments[3]
        self.assertEqual(e1e["experiment_id"], "E1-E-H2-early-explore-predictor-v1")
        self.assertEqual(e1e["stage"], "E1-E")
        self.assertEqual(e1e["state"], "registered")
        self.assertEqual(e1e["predecessor_issue"], 65)
        self.assertIsInstance(e1e["execution_issue"], int)
        self.assertGreater(e1e["execution_issue"], 65)
        self.assertEqual(
            e1e["registration_sha256"],
            "0311621fb4493338d5785753da0c27ce490128170dc84bb4eb096e9b79eb01f1",
        )
        self.assertEqual(
            e1e["harness_path"],
            ".birdai/e1_e_h2_early_explore_predictor.py",
        )
        self.assertEqual(
            e1e["expected_runtime_parent"],
            "d931be650b955a6378785d0bf7ded4360461f447",
        )
        self.assertIs(e1e["auto_push_pr"], False)
        self.assertIs(e1e["allow_issue_close"], False)

    def test_spec_parser_rejects_malformed_values(self):
        module = load_module()
        base = {
            "experiment_id": "x",
            "stage": "E1-C",
            "state": "registered",
            "execution_issue": 61,
            "predecessor_issue": 59,
            "registration_path": "x.json",
            "registration_sha256": "0" * 64,
            "harness_path": "x.py",
            "command": ["python", "x.py"],
            "auto_push_pr": False,
            "allow_issue_close": False,
        }

        parsed = module.ExperimentSpec.from_mapping(base)
        self.assertEqual(parsed.state, "registered")

        invalid_sha = dict(base)
        invalid_sha["registration_sha256"] = "bad"
        with self.assertRaises(module.OrchestratorError):
            module.ExperimentSpec.from_mapping(invalid_sha)

        invalid_state = dict(base)
        invalid_state["state"] = "magic"
        with self.assertRaises(module.OrchestratorError):
            module.ExperimentSpec.from_mapping(invalid_state)

    def test_next_selection_requires_open_issue_and_closed_predecessor(self):
        module = load_module()
        accepted = module.ExperimentSpec(
            experiment_id="old",
            stage="E1-B",
            state="accepted",
            execution_issue=59,
            predecessor_issue=32,
            registration_path="old.json",
            registration_sha256="0" * 64,
            harness_path="old.py",
            command=["python", "old.py"],
            expected_runtime_parent=None,
            auto_push_pr=False,
            allow_issue_close=False,
        )
        candidate = module.ExperimentSpec(
            experiment_id="next",
            stage="E1-C",
            state="registered",
            execution_issue=61,
            predecessor_issue=59,
            registration_path="next.json",
            registration_sha256="1" * 64,
            harness_path="next.py",
            command=["python", "next.py"],
            expected_runtime_parent=None,
            auto_push_pr=False,
            allow_issue_close=False,
        )

        states = {59: "CLOSED", 61: "OPEN"}
        with patch.object(
            module,
            "gh_issue_state",
            side_effect=lambda repo, slug, issue: states[issue],
        ):
            self.assertEqual(
                module.select_next([accepted, candidate], ROOT, "owner/repo"),
                candidate,
            )
            states[59] = "OPEN"
            self.assertIsNone(
                module.select_next([accepted, candidate], ROOT, "owner/repo")
            )

    def test_streaming_runner_does_not_capture_output(self):
        module = load_module()
        completed = type("Completed", (), {"returncode": 7})()
        with patch.object(module.subprocess, "run", return_value=completed) as mocked:
            code = module.run_streaming(["python", "experiment.py"], cwd=ROOT)
        self.assertEqual(code, 7)
        kwargs = mocked.call_args.kwargs
        self.assertNotIn("capture_output", kwargs)
        self.assertNotIn("stdout", kwargs)
        self.assertNotIn("stderr", kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
