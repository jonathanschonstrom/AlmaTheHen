# BirdAI agent loop v1

## State machine
Preferred GitHub labels:

- `agent:ready` — eligible for Gemma
- `agent:working` — exactly one issue may have this state
- `agent:blocked` — requires human/reviewer/research intervention
- `review:needed` — PR exists and implementation must stop
- `review:changes-requested` — Gemma may modify only the same PR/issue
- `review:approved` — implementation accepted; merge still follows governance
- `research-needed` — evidence review required
- `architecture` — architecture decision required
- `phase:E0`, `phase:P1`, etc. — roadmap scope

Until repository labels are provisioned, the same states may be represented by an explicit `STATE:` line in the issue body.

## Continuous/event-driven loop
The loop is event-driven. It must not wait for an hourly schedule.

1. A single issue becomes `agent:ready`.
2. Worker claims it and changes state to `agent:working`.
3. Worker checks out clean `main` and creates `agent/issue-<number>-<slug>`.
4. Gemma receives `AGENTS.md`, governance, roadmap, relevant claim/ADR context, and the exact issue.
5. Gemma implements only the allowed scope.
6. Required tests run.
7. On failure caused by the task, Gemma may revise within scope. On a stop condition, mark `agent:blocked`.
8. On success, push and create one PR linked to the issue; change state to `review:needed`.
9. Gemma stops. It may not claim another issue.
10. Reviewer checks scope, CI, architecture, evidence requirements, and diff.
11. `REVISE` returns the same issue/PR to Gemma. `REJECT` closes the candidate. `BLOCKED` opens a research/architecture blocker. `ACCEPT` permits merge according to governance.
12. Only after merge may the next prepared microtask become `agent:ready`.

## Required context supplied to Gemma
- `AGENTS.md`
- `.birdai/governance.yaml`
- `.birdai/roadmap.yaml`
- current issue body
- only relevant ADRs and neuroscience claim sections
- changed-area source files and tests

Do not dump unrelated project history into the implementation prompt.

## Reviewer contract
A reviewer must explicitly answer:
1. Exact issue solved?
2. Correct roadmap phase?
3. Architecture preserved?
4. Biological interpretation unchanged or justified?
5. No cognitive authority moved silently to Godot?
6. No policy tuning merely to satisfy tests?
7. Required tests/regressions pass?
8. Experiment/ablation required before acceptance?
9. Diff free of unrelated changes?

Then return exactly `ACCEPT`, `REVISE`, `REJECT`, or `BLOCKED`.

## Human-only gates
Human approval is required for the categories listed in `.birdai/governance.yaml`, including new neural architecture, policy changes, learning systems, decision-authority changes, roadmap phase changes, and new accepted neural baselines.
