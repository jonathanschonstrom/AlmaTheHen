
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
    name = "birdai_qwen_adapter_stream_json_test"
    spec = importlib.util.spec_from_file_location(name, ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {ADAPTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load_adapter()


def contract():
    return {
        "diagnosis": {
            "observed_failure": "none",
            "likely_location": "stream-json",
            "hypothesis": "stream evidence works",
            "minimal_test": "parse JSONL result",
        },
        "strategy": {
            "id": "stream-json",
            "operation": "capture incremental Qwen evidence",
            "outcomes": ["structured result preserved"],
        },
        "summary": "pass",
    }


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode = 0
        self.input = None

    def communicate(self, input=None, timeout=None):
        self.input = input
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": "test-model",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "working"}],
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "structured_result": contract(),
            },
        ]
        return (
            "\n".join(json.dumps(item) for item in events) + "\n",
            "",
        )

    def poll(self):
        return self.returncode


class StreamJsonTests(unittest.TestCase):
    def test_extracts_structured_result_from_jsonl(self) -> None:
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": "qwen3-coder-30b-a3b-instruct",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "working"}],
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "structured_result": contract(),
            },
        ]
        stdout = "\n".join(json.dumps(item) for item in events) + "\n"

        raw, parsed, model = adapter._extract_qwen_result(stdout)

        self.assertEqual(model, "qwen3-coder-30b-a3b-instruct")
        self.assertEqual(parsed, contract())
        self.assertEqual(json.loads(raw), contract())

    def test_partial_jsonl_without_result_is_not_contract(self) -> None:
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": "test-model",
            },
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {
                        "type": "text_delta",
                        "text": "partial",
                    },
                },
            },
        ]
        stdout = "\n".join(json.dumps(item) for item in events) + "\n"

        raw, parsed, model = adapter._extract_qwen_result(stdout)

        self.assertIsNotNone(raw)
        self.assertIsNone(parsed)
        self.assertEqual(model, "test-model")

    def test_legacy_json_array_still_parses(self) -> None:
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": "legacy-model",
            },
            {
                "type": "result",
                "structured_result": contract(),
            },
        ]
        raw, parsed, model = adapter._extract_qwen_result(
            json.dumps(events)
        )

        self.assertEqual(model, "legacy-model")
        self.assertEqual(parsed, contract())
        self.assertEqual(json.loads(raw), contract())

    def test_execute_requests_stream_json_and_partial_messages(self) -> None:
        created = []

        def fake_popen(command, **kwargs):
            process = FakeProcess(command, **kwargs)
            created.append(process)
            return process

        task = {
            "goal": {
                "slice_id": "stream-json-test",
                "issue": "#1",
                "objective": "Return structured output.",
                "pass_definition": "Structured output is returned.",
            },
            "allowed_files": [],
            "context_files": [],
            "context_ranges": [],
        }

        with tempfile.TemporaryDirectory() as workspace_raw:
            with tempfile.TemporaryDirectory() as output_raw:
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
                            cwd=Path(workspace_raw),
                            output_dir=Path(output_raw),
                        )

        self.assertEqual(len(created), 1)
        command = created[0].command
        output_index = command.index("--output-format")
        self.assertEqual(command[output_index + 1], "stream-json")
        self.assertIn("--include-partial-messages", command)
        self.assertIsNotNone(result.contract)
        self.assertEqual(result.contract["summary"], "pass")


if __name__ == "__main__":
    unittest.main()
