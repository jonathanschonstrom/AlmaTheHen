from __future__ import annotations

import json
import os
import stat
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIRDAI = ROOT / ".birdai"
RUNNER = BIRDAI / "execution_runner.py"


RESULT_SCHEMA_PATH = BIRDAI / "execution-result.schema.json"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}"
        )
    return result


class RunnerTests(unittest.TestCase):
    def make_repo(self) -> tuple[Path, Path]:
        temp = Path(tempfile.mkdtemp(prefix="birdai-runner-test-"))
        repo = temp / "repo"
        repo.mkdir()

        run(["git", "init"], repo)
        run(["git", "config", "user.name", "test"], repo)
        run(["git", "config", "user.email", "test@example.invalid"], repo)

        (repo / ".birdai").mkdir()
        shutil.copy2(
            RESULT_SCHEMA_PATH,
            repo / ".birdai" / "execution-result.schema.json",
        )
        (repo / "allowed.txt").write_text("before\n", encoding="utf-8")
        (repo / "forbidden.txt").write_text("untouched\n", encoding="utf-8")

        run(["git", "add", "."], repo)
        run(["git", "commit", "-m", "base"], repo)

        return temp, repo

    def fake_qwen(self, temp: Path, edit_file: str) -> Path:
        executable = temp / "fake_qwen.py"
        executable.write_text(
            f"""#!{sys.executable}
import json
import pathlib
import sys

if "--version" in sys.argv:
    print("fake-qwen 1.0")
    raise SystemExit(0)

pathlib.Path({edit_file!r}).write_text("changed\\n", encoding="utf-8")
contract = {{
    "diagnosis": {{
        "observed_failure": "fixture",
        "likely_location": "fixture",
        "hypothesis": "fixture",
        "minimal_test": "fixture",
    }},
    "strategy": {{
        "id": "fixture-edit",
        "operation": "edit one file",
        "outcomes": ["changed fixture"],
    }},
    "summary": "done",
}}
print(json.dumps([
    {{
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(contract),
    }}
]))
""",
            encoding="utf-8",
            newline="\n",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IEXEC)
        return executable

    def make_task(self, repo: Path, allowed: list[str]) -> Path:
        task = {
            "goal": {
                "slice_id": "test-slice",
                "issue": "#1",
                "objective": "change fixture",
                "pass_definition": "allowed.txt contains changed",
            },
            "allowed_files": allowed,
            "validation": {
                "shell": "Python",
                "command": "from pathlib import Path; assert Path('allowed.txt').read_text() == 'changed\\n'",
                "timeout_seconds": 5,
                "timeout_reason": "",
            },
            "max_attempts": {
                "diagnostic_runs": 1,
                "validation_runs": 1,
                "same_strategy_uses": 2,
            },
            "stop_conditions": [
                "pass_definition_proven",
                "second_run_failed_timed_out_or_inconclusive",
                "strategy_budget_exhausted",
                "authority_or_scope_conflict",
                "unrelated_baseline_failure",
                "deadline_enforcement_unavailable",
                "cleanup_or_process_termination_unconfirmed",
            ],
            "result_schema": ".birdai/execution-result.schema.json",
        }
        path = repo / "AI_TASK.json"
        path.write_text(json.dumps(task), encoding="utf-8")
        run(["git", "add", "AI_TASK.json"], repo)
        run(["git", "commit", "-m", "task"], repo)
        return path

    def test_pass_when_qwen_changes_only_allowed_file(self) -> None:
        temp, repo = self.make_repo()
        task = self.make_task(repo, ["allowed.txt"])
        fake = self.fake_qwen(temp, "allowed.txt")
        output = temp / "out"

        result = run(
            [
                sys.executable,
                str(RUNNER),
                "--task",
                str(task),
                "--repo",
                str(repo),
                "--output-dir",
                str(output),
                "--qwen-command",
                str(fake),
                "--agent-wall-time",
                "10",
                "--max-session-turns",
                "5",
                "--max-tool-calls",
                "5",
            ],
            repo,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads((output / "AI_RESULT.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["changed_files"], ["allowed.txt"])
        self.assertEqual(payload["attempts"]["validation_runs"], 1)


    def test_windows_launcher_wraps_cmd_and_python_scripts(self) -> None:
        sys.path.insert(0, str(BIRDAI))
        try:
            import qwen_adapter

            with (
                mock.patch.object(qwen_adapter.os, "name", "nt"),
                mock.patch.object(
                    qwen_adapter.shutil,
                    "which",
                    return_value=r"C:\Windows\System32\cmd.exe",
                ),
            ):
                cmd_launch = qwen_adapter._build_command(
                    r"C:\Users\test\AppData\Roaming\npm\qwen.cmd",
                    ["--version"],
                )
                self.assertEqual(
                    cmd_launch[:4],
                    [
                        r"C:\Windows\System32\cmd.exe",
                        "/d",
                        "/s",
                        "/c",
                    ],
                )
                self.assertIn("qwen.cmd", cmd_launch[4])
                self.assertIn("--version", cmd_launch[4])

                py_launch = qwen_adapter._build_command(
                    r"C:\tmp\fake_qwen.py",
                    ["--version"],
                )
                self.assertEqual(py_launch[0], sys.executable)
                self.assertEqual(py_launch[1], r"C:\tmp\fake_qwen.py")
                self.assertEqual(py_launch[2], "--version")
        finally:
            sys.modules.pop("qwen_adapter", None)
            if sys.path and sys.path[0] == str(BIRDAI):
                sys.path.pop(0)

    def test_qwen_environment_scrubs_github_and_runner_credentials(self) -> None:
        sys.path.insert(0, str(BIRDAI))
        try:
            import qwen_adapter

            with mock.patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "write-token",
                    "GH_TOKEN": "gh-token",
                    "GITHUB_WORKSPACE": r"C:\real\repo",
                    "ACTIONS_RUNTIME_TOKEN": "runtime-token",
                    "RUNNER_TEMP": r"C:\runner\temp",
                    "BIRDAI_INTERNAL": "internal",
                    "DASHSCOPE_API_KEY": "provider-key",
                },
                clear=False,
            ):
                env = qwen_adapter._sanitized_qwen_env()

            self.assertNotIn("GITHUB_TOKEN", env)
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("GITHUB_WORKSPACE", env)
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", env)
            self.assertNotIn("RUNNER_TEMP", env)
            self.assertNotIn("BIRDAI_INTERNAL", env)
            self.assertEqual(env["DASHSCOPE_API_KEY"], "provider-key")
            self.assertEqual(env["QWEN_CODE_SAFE_MODE"], "true")
        finally:
            sys.modules.pop("qwen_adapter", None)
            if sys.path and sys.path[0] == str(BIRDAI):
                sys.path.pop(0)

    def test_block_when_qwen_tampers_with_real_repo(self) -> None:
        temp, repo = self.make_repo()
        task = self.make_task(repo, ["allowed.txt"])
        fake = self.fake_qwen(temp, str(repo / "allowed.txt"))
        output = temp / "out"

        result = run(
            [
                sys.executable,
                str(RUNNER),
                "--task",
                str(task),
                "--repo",
                str(repo),
                "--output-dir",
                str(output),
                "--qwen-command",
                str(fake),
                "--agent-wall-time",
                "10",
                "--max-session-turns",
                "5",
                "--max-tool-calls",
                "5",
            ],
            repo,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(
            (output / "AI_RESULT.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["attempts"]["validation_runs"], 0)
        self.assertIn("authority_or_scope_conflict", payload["stop_reason"])
        self.assertEqual(
            (repo / "allowed.txt").read_text(encoding="utf-8"),
            "before\n",
        )
        self.assertEqual(
            run(["git", "status", "--short"], repo).stdout.strip(),
            "",
        )

    def test_block_before_qwen_when_human_approval_is_required(self) -> None:
        temp, repo = self.make_repo()
        task = self.make_task(repo, ["allowed.txt"])

        payload = json.loads(task.read_text(encoding="utf-8"))
        payload["authority"] = {
            "human_approval_required": True,
            "human_approval_granted": False,
            "approval_reference": "",
        }
        task.write_text(json.dumps(payload), encoding="utf-8")
        run(["git", "add", "AI_TASK.json"], repo)
        run(["git", "commit", "-m", "require approval"], repo)

        output = temp / "out"
        result = run(
            [
                sys.executable,
                str(RUNNER),
                "--task",
                str(task),
                "--repo",
                str(repo),
                "--output-dir",
                str(output),
                "--qwen-command",
                str(temp / "does-not-exist"),
            ],
            repo,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads((output / "AI_RESULT.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["attempts"]["diagnostic_runs"], 0)
        self.assertEqual(payload["changed_files"], [])
        self.assertIn("authority_or_scope_conflict", payload["stop_reason"])
        self.assertEqual(run(["git", "status", "--short"], repo).stdout.strip(), "")

    def test_block_when_qwen_changes_forbidden_file(self) -> None:
        temp, repo = self.make_repo()
        task = self.make_task(repo, ["allowed.txt"])
        fake = self.fake_qwen(temp, "forbidden.txt")
        output = temp / "out"

        result = run(
            [
                sys.executable,
                str(RUNNER),
                "--task",
                str(task),
                "--repo",
                str(repo),
                "--output-dir",
                str(output),
                "--qwen-command",
                str(fake),
                "--agent-wall-time",
                "10",
                "--max-session-turns",
                "5",
                "--max-tool-calls",
                "5",
            ],
            repo,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads((output / "AI_RESULT.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["changed_files"], ["forbidden.txt"])
        self.assertEqual(payload["attempts"]["validation_runs"], 0)
        self.assertIn("authority_or_scope_conflict", payload["stop_reason"])
        self.assertEqual((repo / "forbidden.txt").read_text(encoding="utf-8"), "untouched\n")
        self.assertEqual(run(["git", "status", "--short"], repo).stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
