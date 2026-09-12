# BirdAI Agent Rules

These rules bind every coding or review agent working in this repository.

## Authority order
1. `.birdai/governance.yaml`
2. `.birdai/roadmap.yaml`
3. `BIRDAI-NEUROSCIENCE-REFERENCE.md`
4. Accepted architecture decisions in `.birdai/adr/`
5. The current GitHub issue

A lower authority may not silently override a higher one.

## Core objective
Develop BirdAI toward an increasingly adaptive, biologically plausible artificial avian brain while keeping behavioral acceptance, biological plausibility, regression safety, and experimental evidence separate.

## Work rules
- Follow `.birdai/AGENT_LOOP.md`: every execution requires one bounded slice in `AI_TASK.json`; an issue is not an execution slice.
- Only one execution slice across the repository may be `agent:working`, within the one active issue. Preserve attempt counts across handoffs.
- Work on exactly one issue marked `agent:ready` at a time.
- The issue defines the allowed scope. Do not perform unrelated cleanup or opportunistic refactors.
- Use a dedicated branch for the issue. Never work directly on `main`.
- Do not merge your own pull request.
- Do not start the next issue until the current one has passed review or has been explicitly marked blocked/rejected.
- If a requirement conflicts with governance, roadmap, reference claims, or an ADR: STOP and report `BLOCKED`.

## Biological and architectural constraints
- Do not change biological policy, action-value weights, commitment constants, thresholds, or neural semantics merely to make a test pass.
- First localize failures to representation, approximation, runtime, integration, or the stated design hypothesis.
- New neural mechanisms require a claim ID from the neuroscience reference or explicit D-level classification.
- Galliform evidence outranks mammalian analogy when they conflict.
- Do not describe functional analogy as one-to-one homology without evidence.
- Behavioral improvement alone is not evidence of biological plausibility.
- Godot may validate physical feasibility; it must not silently take over cognitive choice where NeuralBrain is designated as the decision authority.
- Utility must not become a hidden control fallback in neural-control mode.

## Before coding
1. Read the issue and acceptance criteria.
2. Read every authority file relevant to the change.
3. Identify the minimum set of files that must change.
4. Inspect existing tests and baseline behavior.
5. If uncertainty changes architecture or biological interpretation, stop and request review/research.

## Before opening a PR
- Run all task-specific tests.
- Run relevant regression tests.
- Inspect the diff for unrelated changes.
- Remove debug artifacts, generated state, caches, and temporary files.
- State exactly what changed, what did not change, and which acceptance criteria were verified.

## Stop conditions
Report `BLOCKED` instead of guessing when:
- the requested implementation conflicts with a higher authority;
- the expected file/function/API does not exist;
- the baseline already fails a required test for an unrelated reason;
- the solution requires expanding scope;
- the change would alter a protected architecture decision;
- the evidence is insufficient for a biological claim the implementation depends on.

## Review outcomes
Every PR review must end in exactly one of:
- `ACCEPT`
- `REVISE`
- `REJECT`
- `BLOCKED`

CI PASS is necessary when applicable, but never sufficient by itself for ACCEPT.
