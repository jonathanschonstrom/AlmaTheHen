from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
if str(BIRDAI) not in sys.path:
    sys.path.insert(0, str(BIRDAI))

from lifecycle_evidence import registered_runtime, registered_source_snapshot
from lifecycle_github import GitHubPort


class E1ELifecycleCompatibilityTests(unittest.TestCase):
    def test_e1e_registration_provenance_supplies_runtime_and_snapshot(self):
        registration = {
            "provenance": {
                "scientific_runtime_reference": "d931be650b955a6378785d0bf7ded4360461f447",
                "source_snapshot": {
                    "path": r"C:\BirdAI_E1_evidence\source-snapshots\e1-a1-bootstrap-ab186b5.json",
                    "sha256": "3b42d55fc595bc7312e932dc9615c08e1ce2abe72f0f2bcc0984e9818e47b218",
                },
            }
        }
        self.assertEqual(
            registered_runtime(registration),
            "d931be650b955a6378785d0bf7ded4360461f447",
        )
        self.assertEqual(
            registered_source_snapshot(registration)["sha256"],
            "3b42d55fc595bc7312e932dc9615c08e1ce2abe72f0f2bcc0984e9818e47b218",
        )

    def test_legacy_registration_fields_remain_preferred(self):
        registration = {
            "runtime_commit_at_registration": "a" * 40,
            "source_snapshot": {"path": "legacy.json", "sha256": "1" * 64},
            "provenance": {
                "scientific_runtime_reference": "b" * 40,
                "source_snapshot": {"path": "new.json", "sha256": "2" * 64},
            },
        }
        self.assertEqual(registered_runtime(registration), "a" * 40)
        self.assertEqual(registered_source_snapshot(registration)["path"], "legacy.json")

    def test_registry_acceptance_checks_all_scalar_hypothesis_counts(self):
        with tempfile.TemporaryDirectory() as td:
            summary_path = Path(td) / "summary.json"
            summary_path.write_text(
                json.dumps({
                    "hypothesis_counts": {
                        "valid_pair_count": 5,
                        "match_count": 4,
                        "mismatch_count": 1,
                        "late_predicted_count": 3,
                        "late_opposite_count": 2,
                        "late_neutral_count": 0,
                        "early_neutral_count": 0,
                        "both_non_neutral_late_classes_present": True,
                    }
                }),
                encoding="utf-8",
            )
            record = {
                "acceptance": {
                    "stage_validity": "PASS",
                    "hypothesis_result": "INCONCLUSIVE",
                    "valid_pair_count": 5,
                },
                "summary_sha256": "abc",
                "summary_path": str(summary_path),
            }
            expected = GitHubPort._expected_registry_acceptance(record)
            self.assertEqual(expected["match_count"], 4)
            self.assertEqual(expected["late_opposite_count"], 2)
            self.assertIs(expected["both_non_neutral_late_classes_present"], True)

    def test_verify_summary_accepts_e1e_provenance_schema_end_to_end(self):
        from lifecycle_evidence import verify_summary
        from lifecycle_store import digest

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = root / "snapshot.json"
            snapshot.write_text('{"source":"ok"}\n', encoding="utf-8")

            seed = 123456
            runtime = "d" * 40
            registration = {
                "experiment": "E1-E-H2-early-explore-predictor-v1",
                "stage": "E1-E",
                "hypothesis_id": "H2",
                "seed_set": [seed],
                "pairing": {"pairs": [{"seed": seed, "arms": ["rich", "sparse"]}]},
                "hypothesis_result": {"values": ["SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE"]},
                "provenance": {
                    "scientific_runtime_reference": runtime,
                    "source_snapshot": {
                        "path": str(snapshot),
                        "sha256": digest(snapshot),
                    },
                },
            }
            registration_path = root / "registration.json"
            registration_path.write_text(json.dumps(registration), encoding="utf-8")
            registration_sha = digest(registration_path)

            pair_root = root / "seed"
            pair_root.mkdir()
            pair = {"seed": seed, "pair_validity": "PASS"}
            comparison = {"seed": seed, "pair_validity": "PASS"}

            for arm in ("rich", "sparse"):
                run_root = pair_root / arm
                run_root.mkdir()
                trace = run_root / "trace.jsonl"
                trace.write_text('{"tick":1}\n', encoding="utf-8")
                capsule = {
                    "runtime_commit": runtime,
                    "registration_sha256": registration_sha,
                    "neural_seed": seed,
                    "trace_path": str(trace),
                    "trace_sha256": digest(trace),
                }
                capsule_path = run_root / "capsule.json"
                capsule_path.write_text(json.dumps(capsule), encoding="utf-8")
                capsule_sha = digest(capsule_path)
                pair[arm] = {
                    "status": "PASS",
                    "capsule_path": str(capsule_path),
                    "capsule_sha256": capsule_sha,
                }
                comparison[arm] = {
                    "status": "PASS",
                    "capsule_path": str(capsule_path),
                    "capsule_sha256": capsule_sha,
                }

            comparison_path = pair_root / "pair-comparison.json"
            comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
            pair["pair_comparison_path"] = str(comparison_path)
            pair["pair_comparison_sha256"] = digest(comparison_path)

            summary = {
                "stage": "E1-E",
                "stage_validity": "PASS",
                "registration_sha256": registration_sha,
                "runtime_commit": runtime,
                "accepted_source_snapshot_sha256": digest(snapshot),
                "seed_set": [seed],
                "pair_count_declared": 1,
                "pair_count_completed": 1,
                "run_count_declared": 2,
                "hypothesis_result": "INCONCLUSIVE",
                "pairs": [pair],
                "hypothesis_counts": {
                    "valid_pair_count": 1,
                    "match_count": 0,
                    "mismatch_count": 1,
                },
                "production_runtime_mutation": "none",
                "neural_policy_change": "none",
                "learning_rule_change": "none",
            }
            summary_path = root / "summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")

            spec = {
                "experiment_id": "E1-E-H2-early-explore-predictor-v1",
                "stage": "E1-E",
                "execution_issue": 999,
                "registration_path": str(registration_path),
                "registration_sha256": registration_sha,
            }
            verified = verify_summary(spec, summary_path)
            self.assertEqual(verified["runtime_commit"], runtime)
            self.assertEqual(verified["hypothesis_result"], "INCONCLUSIVE")
            self.assertEqual(verified["valid_pair_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
