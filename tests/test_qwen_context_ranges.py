
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / ".birdai" / "qwen_adapter.py"
RUNNER_PATH = REPO_ROOT / ".birdai" / "execution_runner.py"
TASK_PATH = (
    REPO_ROOT / ".birdai" / "tasks"
    / "issue-34-neuralbrain-outage-regression.json"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load_module(
    "birdai_qwen_adapter_context_ranges_test",
    ADAPTER_PATH,
)

_previous_qwen_adapter = sys.modules.get("qwen_adapter")
sys.modules["qwen_adapter"] = adapter
try:
    runner = load_module(
        "birdai_execution_runner_context_ranges_test",
        RUNNER_PATH,
    )
finally:
    if _previous_qwen_adapter is None:
        sys.modules.pop("qwen_adapter", None)
    else:
        sys.modules["qwen_adapter"] = _previous_qwen_adapter


def minimal_task():
    return {
        "goal": {
            "slice_id": "test-context-ranges",
            "issue": "#1",
            "objective": "Create one bounded change.",
            "pass_definition": "The bounded change passes.",
        },
        "allowed_files": ["tests/output.txt"],
        "context_files": [],
        "context_ranges": [],
        "validation": {
            "shell": "Python",
            "command": "print('ok')",
            "timeout_seconds": 10,
            "timeout_reason": "",
        },
        "max_attempts": {
            "diagnostic_runs": 1,
            "validation_runs": 1,
            "same_strategy_uses": 1,
        },
        "stop_conditions": ["pass_definition_proven"],
        "result_schema": ".birdai/execution-result.schema.json",
    }


class ContextRangesTests(unittest.TestCase):
    def test_adapter_renders_only_requested_lines(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "src" / "sample.txt"
            source.parent.mkdir(parents=True)
            source.write_text(
                "one\ntwo\nthree\nfour\nfive\n",
                encoding="utf-8",
            )

            task = minimal_task()
            task["context_ranges"] = [
                {
                    "path": "src/sample.txt",
                    "start_line": 2,
                    "end_line": 4,
                }
            ]

            rendered = adapter._render_context_files(task, root)
            self.assertIn(
                "BEGIN PRELOADED CONTEXT: src/sample.txt:2-4",
                rendered,
            )
            self.assertIn("two\nthree\nfour", rendered)
            self.assertNotIn("\none\n", rendered)
            self.assertNotIn("\nfive\n", rendered)

    def test_adapter_rejects_range_outside_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "sample.txt"
            source.write_text("one\ntwo\n", encoding="utf-8")

            task = minimal_task()
            task["context_ranges"] = [
                {
                    "path": "sample.txt",
                    "start_line": 1,
                    "end_line": 3,
                }
            ]

            with self.assertRaises(adapter.QwenAdapterError):
                adapter._render_context_files(task, root)

    def test_runner_rejects_write_scope_overlap(self) -> None:
        task = minimal_task()
        task["context_ranges"] = [
            {
                "path": "tests/output.txt",
                "start_line": 1,
                "end_line": 1,
            }
        ]

        with self.assertRaises(runner.ExecutionError):
            runner.validate_task(task)

    def test_runner_rejects_overlapping_ranges(self) -> None:
        task = minimal_task()
        task["context_ranges"] = [
            {
                "path": "src/source.gd",
                "start_line": 10,
                "end_line": 30,
            },
            {
                "path": "src/source.gd",
                "start_line": 25,
                "end_line": 40,
            },
        ]

        with self.assertRaises(runner.ExecutionError):
            runner.validate_task(task)

    def test_issue_34_uses_compact_ranges_only(self) -> None:
        task = json.loads(TASK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(task.get("context_files"), [])
        self.assertEqual(
            task.get("context_ranges"),
            [
                {
                    "path": "tests/run_tests.gd",
                    "start_line": 1,
                    "end_line": 18,
                },
                {
                    "path": "tests/run_tests.gd",
                    "start_line": 172,
                    "end_line": 196,
                },
                {
                    "path": "scripts/cognition/agent.gd",
                    "start_line": 128,
                    "end_line": 165,
                },
                {
                    "path": "scripts/cognition/agent.gd",
                    "start_line": 373,
                    "end_line": 411,
                },
            ],
        )
        self.assertEqual(
            task["allowed_files"],
            ["tests/test_neural_control_outage.gd"],
        )


if __name__ == "__main__":
    unittest.main()
