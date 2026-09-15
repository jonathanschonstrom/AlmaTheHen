from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / ".birdai" / "qwen_adapter.py"


def load_adapter():
    module_name = "birdai_qwen_adapter_stdin_prompt_test"
    spec = importlib.util.spec_from_file_location(module_name, ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {ADAPTER_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


adapter = load_adapter()


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode = 0
        self.communicated_input = None
        self.communicated_timeout = None

    def communicate(self, input=None, timeout=None):
        self.communicated_input = input
        self.communicated_timeout = timeout
        payload = [
            {
                "type": "system",
                "subtype": "init",
                "model": "test-model",
            },
            {
                "type": "result",
                "structured_result": {
                    "diagnosis": {
                        "observed_failure": "none",
                        "likely_location": "test",
                        "hypothesis": "stdin transport works",
                        "minimal_test": "captured process input",
                    },
                    "strategy": {
                        "id": "stdin",
                        "operation": "transport prompt on stdin",
                        "outcomes": ["prompt was not placed in argv"],
                    },
                    "summary": "ok",
                },
            },
        ]
        return json.dumps(payload), ""


class StdinPromptTransportTests(unittest.TestCase):
    def test_large_prompt_uses_stdin_not_argv(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_raw:
            with tempfile.TemporaryDirectory() as output_raw:
                workspace = Path(workspace_raw)
                output = Path(output_raw)

                context_file = workspace / "context.txt"
                marker = "BIRDAI_LARGE_CONTEXT_MARKER_"
                context_file.write_text(
                    marker + ("x" * 40000),
                    encoding="utf-8",
                )

                task = {
                    "goal": {
                        "slice_id": "stdin-prompt-test",
                        "issue": "#1",
                        "objective": "Return structured output.",
                        "pass_definition": "Structured output is returned.",
                    },
                    "allowed_files": ["tests/output.txt"],
                    "context_files": ["context.txt"],
                }

                created = []

                def fake_popen(command, **kwargs):
                    process = FakeProcess(command, **kwargs)
                    created.append(process)
                    return process

                qwen = adapter.QwenAdapter(
                    command=sys.executable,
                    model="test-model",
                    wall_time_seconds=30,
                    max_session_turns=5,
                    max_tool_calls=5,
                )

                with patch.object(
                    adapter.subprocess,
                    "Popen",
                    side_effect=fake_popen,
                ):
                    with patch.object(
                        adapter,
                        "_version",
                        return_value="test-version",
                    ):
                        result = qwen.execute(
                            task=task,
                            cwd=workspace,
                            output_dir=output,
                        )

                self.assertEqual(len(created), 1)
                process = created[0]

                self.assertIs(
                    process.kwargs.get("stdin"),
                    adapter.subprocess.PIPE,
                )
                self.assertNotIn("--prompt", process.command)
                self.assertNotIn(marker, " ".join(process.command))
                self.assertIsInstance(process.communicated_input, str)
                self.assertIn(marker, process.communicated_input)
                self.assertGreater(
                    len(process.communicated_input),
                    32767,
                )
                self.assertIsNotNone(result.contract)
                self.assertEqual(
                    result.contract["strategy"]["id"],
                    "stdin",
                )

    def test_command_evidence_does_not_embed_prompt(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            '["--prompt", "<bounded-task>"',
            source,
        )
        self.assertIn(
            "<bounded-task-stdin>",
            source,
        )


if __name__ == "__main__":
    unittest.main()
