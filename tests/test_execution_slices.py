"""Workflow-tool contract tests; no Godot, product imports or real saves."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell 7 required")


@pytest.fixture
def tmp_path():
    # Some Windows hosts set TEMP to the checkout. Always isolate our artifacts.
    with tempfile.TemporaryDirectory(prefix="birdai-slice-", dir=ROOT.parent) as directory:
        yield Path(directory)


def generate(path, *extra):
    return subprocess.run(
        [PWSH, "-NoProfile", "-File", str(ROOT / ".birdai/New-ExecutionSlice.ps1"),
         "-SliceId", "e0-tool-check-001", "-Issue", "#7", "-Goal", "Check generation",
         "-PassDefinition", "Valid compact task", "-AllowedFiles", "AI_RESULT.json",
         "-ValidationCommand", "Write-Output 'not executed'", "-OutputPath", str(path),
         *extra], capture_output=True, text=True, timeout=20,
    )


def test_generated_task_is_compact_and_refuses_overwrite(tmp_path):
    path = tmp_path / "AI_TASK.json"
    run = generate(path)
    assert run.returncode == 0, run.stderr
    original = path.read_bytes()
    task = json.loads(original)
    assert set(task) == {"goal", "allowed_files", "validation", "max_attempts",
                         "stop_conditions", "result_schema"}
    assert task["goal"]["slice_id"] == "e0-tool-check-001"
    assert task["allowed_files"] == ["AI_RESULT.json"]
    assert task["validation"]["timeout_seconds"] == 20
    assert task["max_attempts"] == {
        "diagnostic_runs": 1, "validation_runs": 1, "same_strategy_uses": 2}
    assert (ROOT / task["result_schema"]).is_file()
    assert generate(path).returncode != 0
    assert path.read_bytes() == original


def test_long_timeout_requires_reason(tmp_path):
    rejected = tmp_path / "rejected.json"
    run = generate(rejected, "-TimeoutSeconds", "60")
    assert run.returncode != 0
    assert "TimeoutReason" in run.stderr
    assert not rejected.exists()
    accepted = tmp_path / "accepted.json"
    run = generate(accepted, "-TimeoutSeconds", "60", "-TimeoutReason", "Measured build: 40s")
    assert run.returncode == 0, run.stderr
    assert json.loads(accepted.read_text())["validation"]["timeout_reason"] == "Measured build: 40s"


def test_result_schema_rejects_false_pass_and_excess_attempts(tmp_path):
    # Test-Json exercises the actual shipped schema without another Python dependency.
    schema = str(ROOT / ".birdai/execution-result.schema.json").replace("'", "''")
    result = {
        "slice_id": "e0-check-001", "status": "BLOCKED", "base_commit": "test",
        "elapsed_seconds": 0, "diagnosis": dict.fromkeys(
            ["observed_failure", "likely_location", "hypothesis", "minimal_test"], "preflight"),
        "attempts": {"diagnostic_runs": 0, "validation_runs": 0, "strategies": []},
        "runs": [], "cleanup": {"status": "not_applicable", "paths": [], "details": "No launch"},
        "changed_files": [], "pass_evidence": [], "stop_reason": "Deadline unavailable",
    }
    cases = [result, {**result, "status": "PASS"},
             {**result, "attempts": {"diagnostic_runs": 2, "validation_runs": 0, "strategies": []}}]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    escaped = str(path).replace("'", "''")
    command = (f"$cases = Get-Content -Raw -LiteralPath '{escaped}' | ConvertFrom-Json; "
               f"@($cases | ForEach-Object {{ ($_ | ConvertTo-Json -Depth 20) | "
               f"Test-Json -SchemaFile '{schema}' -ErrorAction SilentlyContinue }}) | ConvertTo-Json")
    run = subprocess.run([PWSH, "-NoProfile", "-Command", command],
                         capture_output=True, text=True, timeout=20)
    assert json.loads(run.stdout) == [True, False, False], run.stderr
