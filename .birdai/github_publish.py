from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class PublishError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise PublishError(
            f"git {' '.join(args)} failed ({result.returncode})\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def issue_number(value: str) -> int:
    match = re.search(r"(?:/issues/|#)?(\d+)\s*$", value.strip())
    if not match:
        raise PublishError(f"Cannot parse issue number from: {value}")
    return int(match.group(1))


def api_request(
    *,
    method: str,
    repo_slug: str,
    token: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo_slug}{path}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "BirdAI-Qwen-Executor/1",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PublishError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc

    return json.loads(body) if body else {}


def compact_comment(
    *,
    task: dict[str, Any],
    result: dict[str, Any],
    run_url: str,
    pr_url: str | None,
) -> str:
    lines = [
        f"## BirdAI executor — {result['slice_id']}",
        "",
        f"STATUS: **{result['status']}**",
        f"Base commit: `{result['base_commit']}`",
        f"Changed files: `{json.dumps(result['changed_files'])}`",
        f"Stop reason: `{result['stop_reason']}`",
        "",
        "Diagnosis:",
        f"- observed: {result['diagnosis']['observed_failure']}",
        f"- likely location: {result['diagnosis']['likely_location']}",
        f"- hypothesis: {result['diagnosis']['hypothesis']}",
        f"- minimal test: {result['diagnosis']['minimal_test']}",
        "",
        f"Actions run: {run_url}",
    ]

    if pr_url:
        lines.append(f"Pull request: {pr_url}")

    lines += [
        "",
        "No merge was performed by the implementing executor.",
    ]

    return "\n".join(lines)


def verify_result_scope(task: dict[str, Any], result: dict[str, Any]) -> None:
    allowed = set(task["allowed_files"])
    changed = set(result["changed_files"])
    outside = sorted(changed - allowed)
    if outside:
        raise PublishError(f"AI_RESULT contains changed files outside allowed_files: {outside}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish BirdAI AI_RESULT to GitHub")
    parser.add_argument("--task", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    parser.add_argument("--base", default="main")
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    task = json.loads(Path(args.task).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))

    if not args.repo_slug:
        raise PublishError("--repo-slug or GITHUB_REPOSITORY is required")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise PublishError("GITHUB_TOKEN or GH_TOKEN is required")

    if result["status"] == "PASS":
        verify_result_scope(task, result)

    issue = issue_number(task["goal"]["issue"])
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = (
        f"{server}/{args.repo_slug}/actions/runs/{args.run_id}"
        if args.run_id != "local"
        else f"{server}/{args.repo_slug}"
    )

    pr_url: str | None = None

    current_head = git(repo_path, "rev-parse", "HEAD").stdout.strip()
    if current_head != result["base_commit"]:
        raise PublishError(
            f"Checked-out HEAD differs from AI_RESULT base_commit: {current_head} != {result['base_commit']}"
        )

    if result["status"] == "PASS" and result["changed_files"]:
        branch_safe = re.sub(r"[^a-z0-9._/-]+", "-", result["slice_id"].lower()).strip("-/")
        branch = f"agent/{branch_safe}-{args.run_id}"

        actual = set(
            line.strip().replace("\\", "/")
            for line in git(repo_path, "diff", "--name-only", "HEAD").stdout.splitlines()
            if line.strip()
        )
        actual.update(
            line.strip().replace("\\", "/")
            for line in git(repo_path, "diff", "--cached", "--name-only", "HEAD").stdout.splitlines()
            if line.strip()
        )
        actual.update(
            line.strip().replace("\\", "/")
            for line in git(repo_path, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
            if line.strip()
        )

        if actual != set(result["changed_files"]):
            raise PublishError(
                f"Working tree/result mismatch. actual={sorted(actual)} result={result['changed_files']}"
            )

        git(repo_path, "switch", "-c", branch)

        git(repo_path, "config", "user.name", "birdai-qwen-executor")
        git(repo_path, "config", "user.email", "birdai-qwen-executor@users.noreply.github.com")

        git(repo_path, "add", "--", *result["changed_files"])

        staged = sorted(
            line.strip().replace("\\", "/")
            for line in git(repo_path, "diff", "--cached", "--name-only").stdout.splitlines()
            if line.strip()
        )

        if staged != sorted(result["changed_files"]):
            raise PublishError(f"Staged files mismatch: {staged}")

        git(
            repo_path,
            "commit",
            "-m",
            f"[{result['slice_id']}] Qwen execution slice",
        )
        git(repo_path, "push", "-u", "origin", branch)

        pr = api_request(
            method="POST",
            repo_slug=args.repo_slug,
            token=token,
            path="/pulls",
            payload={
                "title": f"[{result['slice_id']}] {task['goal']['objective']}"[:240],
                "head": branch,
                "base": args.base,
                "body": (
                    f"Implements execution slice `{result['slice_id']}`.\n\n"
                    f"Closes #{issue}\n\n"
                    "Generated by the bounded BirdAI Qwen executor. "
                    "The executor does not merge its own pull request.\n\n"
                    f"Validation status: **{result['status']}**\n"
                    f"Base commit: `{result['base_commit']}`\n"
                    f"Changed files: `{json.dumps(result['changed_files'])}`\n"
                    f"Actions evidence: {run_url}"
                ),
            },
        )
        pr_url = str(pr["html_url"])

    comment = compact_comment(
        task=task,
        result=result,
        run_url=run_url,
        pr_url=pr_url,
    )

    api_request(
        method="POST",
        repo_slug=args.repo_slug,
        token=token,
        path=f"/issues/{issue}/comments",
        payload={"body": comment},
    )

    print(f"STATUS: {result['status']}")
    print(f"ISSUE: #{issue}")
    if pr_url:
        print(f"PR: {pr_url}")
    print(f"RUN: {run_url}")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(1)
