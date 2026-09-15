from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / ".birdai" / "qwen_adapter.py"

def load_adapter():
    name = "birdai_qwen_adapter_windows_test"
    spec = importlib.util.spec_from_file_location(name, ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

adapter = load_adapter()

@unittest.skipUnless(os.name == "nt", "Windows launcher regression")
class WindowsStandaloneLauncherTests(unittest.TestCase):
    def _touch(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    def test_outer_qwen_cmd_resolves_to_node_and_preserves_schema(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            install = base / "qwen-code"
            runtime = install / "qwen-code"
            outer = install / "bin" / "qwen.cmd"
            node = runtime / "node" / "node.exe"
            cli = runtime / "lib" / "cli-entry.js"
            self._touch(outer)
            self._touch(node)
            self._touch(cli)
            schema = json.dumps(
                {"type": "object", "properties": {"status": {"type": "string"}}},
                separators=(",", ":"),
            )
            args = ["--prompt", "probe", "--json-schema", schema, "--output-format", "json"]
            command = adapter._build_command(str(outer), args)
            self.assertEqual(command[:2], [str(node), str(cli)])
            self.assertEqual(command[2:], args)
            self.assertEqual(command[command.index("--json-schema") + 1], schema)

    def test_inner_qwen_cmd_resolves_to_node(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw) / "qwen-code"
            inner = runtime / "bin" / "qwen.cmd"
            node = runtime / "node" / "node.exe"
            cli = runtime / "lib" / "cli-entry.js"
            self._touch(inner)
            self._touch(node)
            self._touch(cli)
            command = adapter._build_command(str(inner), ["--version"])
            self.assertEqual(command, [str(node), str(cli), "--version"])

    def test_unrelated_cmd_does_not_hijack_localappdata_qwen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            unrelated = base / "tools" / "custom-wrapper.cmd"
            ambient = base / "ambient" / "qwen-code" / "qwen-code"
            self._touch(unrelated)
            self._touch(ambient / "node" / "node.exe")
            self._touch(ambient / "lib" / "cli-entry.js")
            with mock.patch.dict(
                os.environ,
                {"LOCALAPPDATA": str(base / "ambient")},
                clear=False,
            ):
                resolved = adapter._windows_qwen_standalone_command(
                    str(unrelated),
                    ["--version"],
                )
            self.assertIsNone(resolved)

class QwenResultExtractionTests(unittest.TestCase):
    def test_qwen_023_init_event_reports_model_and_structured_result(self) -> None:
        stdout = json.dumps(
            [
                {
                    "type": "system",
                    "subtype": "init",
                    "model": "qwen3-coder-30b-a3b-instruct",
                },
                {
                    "type": "result",
                    "subtype": "success",
                    "structured_result": {
                        "diagnosis": {
                            "observed_failure": "none",
                            "likely_location": "smoke",
                            "hypothesis": "transport works",
                            "minimal_test": "structured output",
                        },
                        "strategy": {
                            "id": "probe",
                            "operation": "no-op",
                            "outcomes": ["pass"],
                        },
                        "summary": "pass",
                    },
                },
            ]
        )
        raw, contract, model = adapter._extract_qwen_result(stdout)
        self.assertEqual(model, "qwen3-coder-30b-a3b-instruct")
        self.assertIsInstance(contract, dict)
        self.assertEqual(contract["summary"], "pass")
        self.assertEqual(json.loads(raw)["summary"], "pass")

if __name__ == "__main__":
    unittest.main()
