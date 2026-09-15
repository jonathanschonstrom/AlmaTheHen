from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
RUNNER_PATH = BIRDAI / "execution_runner.py"
QWEN_PATH = BIRDAI / "qwen_adapter.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


qwen = load_module(
    "birdai_qwen_adapter_authoritative_diagnosis_test",
    QWEN_PATH,
)

previous = sys.modules.get("qwen_adapter")
sys.modules["qwen_adapter"] = qwen
try:
    runner = load_module(
        "birdai_execution_runner_authoritative_diagnosis_test",
        RUNNER_PATH,
    )
finally:
    if previous is None:
        sys.modules.pop("qwen_adapter", None)
    else:
        sys.modules["qwen_adapter"] = previous


class AuthoritativeDiagnosisTests(unittest.TestCase):
    def test_pass_ignores_false_model_failure_claim(self) -> None:
        contract = {
            "diagnosis": {
                "observed_failure": (
                    "Direct LM Studio backend did not return "
                    "a valid strict-schema response"
                ),
                "likely_location": "transport",
                "hypothesis": "backend is broken",
                "minimal_test": "retry",
            }
        }

        result = runner.authoritative_diagnosis(
            status="PASS",
            contract=contract,
            block_reason="",
        )

        self.assertEqual(result["observed_failure"], "none")
        self.assertEqual(
            result["likely_location"],
            "not_applicable",
        )
        self.assertIn(
            "authoritative validation passed",
            result["hypothesis"].lower(),
        )

    def test_blocked_observed_failure_is_coordinator_owned(self) -> None:
        contract = {
            "diagnosis": {
                "observed_failure": "model guessed wrong",
                "likely_location": "candidate implementation",
                "hypothesis": "model hypothesis",
                "minimal_test": "inspect candidate",
            }
        }

        result = runner.authoritative_diagnosis(
            status="BLOCKED",
            contract=contract,
            block_reason="Authoritative validation exited with code 1",
        )

        self.assertEqual(
            result["observed_failure"],
            "Authoritative validation exited with code 1",
        )
        self.assertEqual(
            result["likely_location"],
            "candidate implementation",
        )

    def test_blocked_without_model_contract_uses_coordinator_fallback(self) -> None:
        result = runner.authoritative_diagnosis(
            status="BLOCKED",
            contract=None,
            block_reason="Execution backend timed out",
        )

        self.assertEqual(
            result["observed_failure"],
            "Execution backend timed out",
        )
        self.assertEqual(
            result["likely_location"],
            "execution backend contract",
        )

    def test_model_diagnosis_evidence_is_separate_from_ai_result_truth(self) -> None:
        contract = {
            "diagnosis": {
                "observed_failure": "model text",
                "likely_location": "model location",
                "hypothesis": "model hypothesis",
                "minimal_test": "model test",
            }
        }

        payload = runner.model_diagnosis_evidence(contract)

        self.assertEqual(payload["source"], "model_contract")
        self.assertEqual(
            payload["diagnosis"]["observed_failure"],
            "model text",
        )


if __name__ == "__main__":
    unittest.main()
