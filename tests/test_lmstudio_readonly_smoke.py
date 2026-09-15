from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
ADAPTER_PATH = BIRDAI / "lmstudio_adapter.py"
TASK_PATH = BIRDAI / "tasks" / "lmstudio-smoke.json"


def load_adapter():
    previous = sys.modules.get("qwen_adapter")
    sys.path.insert(0, str(BIRDAI))
    try:
        spec = importlib.util.spec_from_file_location(
            "birdai_lmstudio_readonly_smoke_test",
            ADAPTER_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {ADAPTER_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == str(BIRDAI):
            sys.path.pop(0)
        if previous is not None:
            sys.modules["qwen_adapter"] = previous


adapter = load_adapter()


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def readonly_proposal():
    return {
        "diagnosis": {
            "observed_failure": "none",
            "likely_location": "direct lmstudio transport",
            "hypothesis": "read-only structured generation is healthy",
            "minimal_test": "validate empty file proposal",
        },
        "strategy": {
            "id": "lmstudio-readonly-smoke",
            "operation": "return no file changes",
            "outcomes": ["files array remained empty"],
        },
        "files": [],
        "summary": "read-only direct LM Studio smoke passed",
    }


class LMStudioReadonlySmokeTests(unittest.TestCase):
    def test_task_is_read_only_direct_lmstudio(self) -> None:
        task = json.loads(TASK_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            task["goal"]["slice_id"],
            "infra-lmstudio-smoke",
        )
        self.assertEqual(task["goal"]["issue"], "#26")
        self.assertEqual(task["execution_backend"], "lmstudio")
        self.assertEqual(task["allowed_files"], [])
        self.assertEqual(task["context_files"], [])
        self.assertEqual(
            task["context_ranges"],
            [
                {
                    "path": ".birdai/execution-result.schema.json",
                    "start_line": 1,
                    "end_line": 18,
                }
            ],
        )

    def test_empty_allowed_files_schema_is_satisfiable(self) -> None:
        schema = adapter._proposal_schema([])
        files = schema["properties"]["files"]

        self.assertEqual(files["type"], "array")
        self.assertEqual(files["minItems"], 0)
        self.assertEqual(files["maxItems"], 0)
        self.assertNotIn("enum", json.dumps(files))

    def test_read_only_execution_writes_no_repository_file(self) -> None:
        task = json.loads(TASK_PATH.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            schema_source = root / ".birdai" / "execution-result.schema.json"
            schema_source.parent.mkdir(parents=True, exist_ok=True)
            schema_source.write_text(
                "\n".join(
                    [
                        "{",
                        '  "$schema": "http://json-schema.org/draft-07/schema#",',
                        '  "title": "BirdAI execution result v1",',
                        '  "type": "object",',
                        '  "additionalProperties": false,',
                        '  "required": [',
                        '    "slice_id",',
                        '    "status",',
                        '    "base_commit",',
                        '    "elapsed_seconds",',
                        '    "diagnosis",',
                        '    "attempts",',
                        '    "runs",',
                        '    "cleanup",',
                        '    "changed_files",',
                        '    "pass_evidence",',
                        '    "stop_reason"',
                        "  ]",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = root / "evidence"

            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(readonly_proposal())
                        }
                    }
                ]
            }

            with patch.object(
                adapter.urllib.request,
                "urlopen",
                return_value=FakeResponse(response),
            ):
                client = adapter.LMStudioAdapter(
                    model="test-model",
                    timeout_seconds=30,
                )
                result = client.execute(
                    task=task,
                    cwd=root,
                    output_dir=evidence,
                )

            self.assertEqual(result.contract["files"], [])
            self.assertEqual(
                sorted(
                    str(path.relative_to(root)).replace("\\", "/")
                    for path in root.rglob("*")
                    if path.is_file()
                    and evidence not in path.parents
                ),
                [".birdai/execution-result.schema.json"],
            )


if __name__ == "__main__":
    unittest.main()
