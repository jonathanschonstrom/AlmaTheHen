from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
BACKEND_PATH = BIRDAI / "execution_backend.py"
QWEN_PATH = BIRDAI / "qwen_adapter.py"
LMSTUDIO_PATH = BIRDAI / "lmstudio_adapter.py"
RUNNER_PATH = BIRDAI / "execution_runner.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(BIRDAI))
try:
    backend = load_module(
        "execution_backend",
        BACKEND_PATH,
    )
    lmstudio = load_module(
        "birdai_lmstudio_adapter_contract_test",
        LMSTUDIO_PATH,
    )
finally:
    if sys.path and sys.path[0] == str(BIRDAI):
        sys.path.pop(0)


class ExecutionBackendContractTests(unittest.TestCase):
    def test_lmstudio_uses_backend_neutral_types(self) -> None:
        self.assertIs(
            sys.modules["execution_backend"],
            backend,
        )
        self.assertTrue(
            issubclass(
                lmstudio.LMStudioAdapterError,
                backend.ExecutionBackendError,
            )
        )
        self.assertIs(
            lmstudio.ProcessRecord,
            backend.ProcessRecord,
        )
        self.assertIs(
            lmstudio.ExecutionResult,
            backend.ExecutionResult,
        )

    def test_lmstudio_has_no_qwen_adapter_dependency(self) -> None:
        source = LMSTUDIO_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "from qwen_adapter import",
            source,
        )
        self.assertIn(
            "from execution_backend import",
            source,
        )

    def test_qwen_adapter_remains_legacy_self_contained(self) -> None:
        source = QWEN_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "from execution_backend import",
            source,
        )
        self.assertIn("class ProcessRecord:", source)
        self.assertIn("class QwenExecution:", source)

    def test_runner_uses_lazy_lmstudio_error_type(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "backend_error_type = QwenAdapterError",
            source,
        )
        self.assertIn(
            "from execution_backend import ExecutionBackendError",
            source,
        )
        self.assertIn(
            "backend_error_type = ExecutionBackendError",
            source,
        )
        self.assertIn(
            "except backend_error_type as exc:",
            source,
        )

        pre_main = source.split("def main()", 1)[0]
        self.assertNotIn(
            "from execution_backend import",
            pre_main,
        )


if __name__ == "__main__":
    unittest.main()
