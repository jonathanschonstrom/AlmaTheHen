from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
ADAPTER_PATH = BIRDAI / "lmstudio_adapter.py"
RUNNER_PATH = BIRDAI / "execution_runner.py"
TASK_PATH = (
    BIRDAI
    / "tasks"
    / "issue-34-neuralbrain-outage-regression.json"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(BIRDAI))
try:
    adapter = load_module(
        "birdai_lmstudio_adapter_test",
        ADAPTER_PATH,
    )
    runner = load_module(
        "birdai_execution_runner_lmstudio_test",
        RUNNER_PATH,
    )
finally:
    if sys.path and sys.path[0] == str(BIRDAI):
        sys.path.pop(0)


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


def proposal(path: str):
    return {
        "diagnosis": {
            "observed_failure": "fixture",
            "likely_location": path,
            "hypothesis": "direct generation",
            "minimal_test": "validate output",
        },
        "strategy": {
            "id": "direct",
            "operation": "write one file",
            "outcomes": ["generated fixture"],
        },
        "files": [
            {
                "path": path,
                "content": "changed\n",
            }
        ],
        "summary": "done",
    }


class LMStudioAdapterTests(unittest.TestCase):
    def make_task(self):
        return {
            "goal": {
                "slice_id": "direct-test-slice",
                "issue": "#1",
                "objective": "Generate output.txt",
                "pass_definition": "output.txt is changed",
            },
            "allowed_files": ["output.txt"],
            "context_files": [],
            "context_ranges": [
                {
                    "path": "source.txt",
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
        }

    def test_direct_generation_writes_exact_allowed_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.txt").write_text(
                "source\n",
                encoding="utf-8",
            )
            output = root / "evidence"
            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                proposal("output.txt")
                            )
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
                    task=self.make_task(),
                    cwd=root,
                    output_dir=output,
                )

            self.assertEqual(
                (root / "output.txt").read_text(
                    encoding="utf-8"
                ),
                "changed\n",
            )
            self.assertEqual(result.process.exit_code, 0)
            self.assertEqual(
                result.contract["summary"],
                "done",
            )
            request = json.loads(
                (output / "lmstudio.request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                request["response_format"]["type"],
                "json_schema",
            )
            self.assertFalse(request["stream"])

    def test_forbidden_model_path_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "source.txt").write_text(
                "source\n",
                encoding="utf-8",
            )
            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                proposal("forbidden.txt")
                            )
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
                with self.assertRaises(
                    adapter.LMStudioAdapterError
                ):
                    client.execute(
                        task=self.make_task(),
                        cwd=root,
                        output_dir=root / "evidence",
                    )

            self.assertFalse(
                (root / "forbidden.txt").exists()
            )
            self.assertFalse(
                (root / "output.txt").exists()
            )

    def test_non_loopback_endpoint_is_rejected(self):
        with self.assertRaises(
            adapter.LMStudioAdapterError
        ):
            adapter.LMStudioAdapter(
                model="test-model",
                timeout_seconds=30,
                base_url="http://example.com/v1",
            )

    def test_runner_backend_validation(self):
        task = {
            "goal": {
                "slice_id": "direct-test-slice",
                "issue": "#1",
                "objective": "Generate output",
                "pass_definition": "output exists",
            },
            "allowed_files": [],
            "context_files": [],
            "context_ranges": [],
            "validation": {
                "shell": "Python",
                "command": "print('ok')",
                "timeout_seconds": 5,
            },
            "max_attempts": {
                "diagnostic_runs": 1,
                "validation_runs": 1,
                "same_strategy_uses": 1,
            },
            "stop_conditions": [
                "pass_definition_proven"
            ],
            "result_schema": (
                ".birdai/execution-result.schema.json"
            ),
            "execution_backend": "lmstudio",
        }
        runner.validate_task(task)

        task["execution_backend"] = "unknown"
        with self.assertRaises(runner.ExecutionError):
            runner.validate_task(task)

    def test_issue_34_uses_direct_lmstudio_backend(self):
        task = json.loads(
            TASK_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(
            task.get("execution_backend"),
            "lmstudio",
        )
        self.assertEqual(
            task["allowed_files"],
            ["tests/test_neural_control_outage.gd"],
        )


if __name__ == "__main__":
    unittest.main()
