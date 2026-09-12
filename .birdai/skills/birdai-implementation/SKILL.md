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
