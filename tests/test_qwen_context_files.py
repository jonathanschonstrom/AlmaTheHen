from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / ".birdai" / "qwen_adapter.py"
TASK_PATH = (
    REPO_ROOT
    / ".birdai"
    / "tasks"
    / "issue-34-neuralbrain-outage-regression.json"
)


def load_adapter():
    module_name = "birdai_qwen_adapter_context_files_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ADAPTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {ADAPTER_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


adapter = load_adapter()


def make_task(context_files, allowed_files=None):
    return {
        "goal": {
            "slice_id": "test-context-files",
            "issue": "#1",
            "objective": "Create one bounded change.",
            "pass_definition": "The bounded change passes.",
        },
        "allowed_files": allowed_files or ["tests/output.txt"],
        "context_files": context_files,
    }


class ContextFilesTests(unittest.TestCase):
    def test_prompt_embeds_preloaded_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            first = root / "src" / "alpha.txt"
            second = root / "tests" / "beta.txt"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("alpha-body\n", encoding="utf-8")
            second.write_text("beta-body\n", encoding="utf-8")

            prompt = adapter._build_prompt(
                make_task(["src/alpha.txt", "tests/beta.txt"]),
                root,
            )

            self.assertIn(
                "===== BEGIN PRELOADED CONTEXT: src/alpha.txt =====",
                prompt,
            )
            self.assertIn("alpha-body", prompt)
            self.assertIn(
                "===== END PRELOADED CONTEXT: tests/beta.txt =====",
                prompt,
            )
            self.assertIn("beta-body", prompt)
            self.assertIn("read-only repository context", prompt)

    def test_missing_context_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(adapter.QwenAdapterError):
                adapter._build_prompt(
                    make_task(["src/missing.txt"]),
                    Path(raw),
                )

    def test_parent_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(adapter.QwenAdapterError):
                adapter._build_prompt(
                    make_task(["../outside.txt"]),
                    Path(raw),
                )

    def test_duplicate_context_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "src" / "same.txt"
            source.parent.mkdir(parents=True)
            source.write_text("same", encoding="utf-8")

            with self.assertRaises(adapter.QwenAdapterError):
                adapter._build_prompt(
                    make_task(
                        ["src/same.txt", "src/same.txt"]
                    ),
                    root,
                )

    def test_context_and_allowed_files_must_be_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "tests" / "same.txt"
            source.parent.mkdir(parents=True)
            source.write_text("same", encoding="utf-8")

            with self.assertRaises(adapter.QwenAdapterError):
                adapter._build_prompt(
                    make_task(
                        ["tests/same.txt"],
                        ["tests/same.txt"],
                    ),
                    root,
                )

    def test_issue_34_declares_exact_context_and_write_scope(self) -> None:
        payload = json.loads(TASK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("context_files"), [])
        self.assertEqual(
            payload["allowed_files"],
            ["tests/test_neural_control_outage.gd"],
        )
        self.assertTrue(
            set(payload.get("context_files", [])).isdisjoint(
                payload["allowed_files"]
            )
        )


if __name__ == "__main__":
    unittest.main()
