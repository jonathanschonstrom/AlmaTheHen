---
name: birdai-implementation
description: Execute a bounded BirdAI implementation slice in AlmaTheHen using its governance, diagnostic budget and evidence contract. Use when Bionic or Gemma receives a current AI_TASK.json for this repository.
---

# BirdAI implementation

Resolve paths from the AlmaTheHen repository root, even after importing into Bionic.
This repo version is the source of truth for the import.

Read AGENTS.md and its authority chain, .birdai/AGENT_LOOP.md, the parent issue and
current AI_TASK.json. Load only relevant neuroscience claims/ADRs and source/tests.
Do not duplicate the full phase specification in the task.

If the working branch predates governance, fetch once and record the commit behind
origin/main. Read missing authority files with `git show <recorded-commit>:<path>`;
do not merge/rebase main or copy governance into an active product branch merely
to read it. Resolve referenced loop/template/schema files from the same recorded
tooling revision when absent locally. Before merge, an explicitly supplied PR
revision is usable for read-only handoff inspection; it does not authorize product
execution or override main's governance. Report unavailable references as BLOCKED.

Before dispatch, compare local AI_TASK.json and AI_RESULT.json IDs and attempt
counts with the assigned remote task. A stale local task and a newer blocked
result must be reconciled by the coordinator before execution. Do not restore an
older task, discard the result or reset its budget automatically.

Confirm one slice is agent:working, with this ID, on the assigned branch. Preserve
the attempt ledger and untracked implementation tests. Ambiguous ownership, stale
or incompatible task formats and exhausted budgets mean BLOCKED; do not silently
translate or overwrite an active task.

Execute one technical goal with explicit PASS criteria. Before correction record
observed failure, location, one hypothesis and minimal test. Allow one diagnostic
run and at most one correction/validation run. Same operation/recovery strategy
has at most two uses, including trivial parameter/syntax/shell/path variants and
handoffs. Follow the loop's PowerShell, enforced deadline, evidence and cleanup
contract. Never modify policy, weights, commitment or neural semantics to pass tests.

Produce AI_RESULT.json matching .birdai/execution-result.schema.json only if allowed;
preserve raw failure evidence outside the worktree. Stop at PASS or BLOCKED. Never
start another slice, merge, accept a baseline or advance the roadmap autonomously.
Missing evidence is not PASS.
