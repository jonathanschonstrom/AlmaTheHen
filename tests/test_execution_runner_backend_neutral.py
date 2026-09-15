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
    "birdai_qwen_adapter_backend_neutral_test",
    QWEN_PATH,
)

previous = sys.modules.get("qwen_adapter")
sys.modules["qwen_adapter"] = qwen
try:
    runner = load_module(
        "birdai_execution_runner_backend_neutral_test",
        RUNNER_PATH,
    )
finally:
    if previous is None:
        sys.modules.pop("qwen_adapter", None)
    else:
        sys.modules["qwen_adapter"] = previous


class BackendNeutralRunnerTests(unittest.TestCase):
    def test_backend_diagnosis_uses_generic_fallbacks(self) -> None:
        result = runner.execution_diagnosis(
            None,
            "backend failed",
        )
        self.assertEqual(
            result["observed_failure"],
            "backend failed",
        )
        self.assertEqual(
            result["likely_location"],
            "execution backend contract",
        )
        self.assertIn(
            "execution backend",
            result["hypothesis"].lower(),
        )

    def test_backend_strategy_uses_generic_fallback_id(self) -> None:
        result = runner.execution_strategy(
            None,
            "BLOCKED",
        )
        self.assertEqual(
            result[0]["id"],
            "bounded-execution",
        )
        self.assertEqual(
            result[0]["operation"],
            "bounded repository diagnosis/implementation",
        )

    def test_source_has_no_qwen_specific_coordinator_symbols(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")

        self.assertNotIn("def qwen_diagnosis(", source)
        self.assertNotIn("def qwen_strategy(", source)
        self.assertNotIn("qwen_run =", source)
        self.assertNotIn("qwen_workspace:", source)
        self.assertNotIn("qwen_failed =", source)

        self.assertIn("def execution_diagnosis(", source)
        self.assertIn("def execution_strategy(", source)
        self.assertIn("execution_run =", source)
        self.assertIn("execution_workspace:", source)

    def test_legacy_qwen_cli_flags_remain_for_compatibility(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")

        self.assertIn('"--qwen-command"', source)
        self.assertIn('"--qwen-model"', source)
        self.assertIn("QwenAdapter(", source)
        self.assertIn(
            'task.get("execution_backend", "qwen")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
