# BirdAI agent loop v2

This contract supplements the authority order in AGENTS.md. Governance, roadmap,
neuroscience reference and accepted ADRs remain authoritative. Workflow changes
are engineering work, not evidence for a biological claim.

## State machine
Preferred GitHub labels:

- `agent:ready` — eligible for Gemma
- `agent:working` - exactly one issue AND one execution slice repository-wide may have this state
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
3. For a new issue, worker branches from clean `main`. Later slices continue the same reviewed issue branch, preserving existing work and untracked tests.
4. Gemma receives `AGENTS.md`, governance, roadmap, relevant claim/ADR context, and the exact issue.
5. Coordinator supplies one execution slice in AI_TASK.json; Gemma implements only its allowed files and goal.
6. Execute one diagnostic run and at most one targeted correction/validation run under the mandatory budget below.
7. On unresolved failure or a stop condition, mark `agent:blocked`, preserve evidence and stop.
8. On success, push and create one PR linked to the issue; change state to `review:needed`.
9. Gemma stops. It may not claim another issue.
10. Reviewer checks scope, CI, architecture, evidence requirements, and diff.
11. `REVISE` returns the same issue/PR to Gemma. `REJECT` closes the candidate. `BLOCKED` opens a research/architecture blocker. `ACCEPT` permits merge according to governance.
12. A subsequent slice of the same issue requires explicit coordinator dispatch after review. A new issue waits for review/merge or explicit blocked/rejected disposition under AGENTS.md. Slice PASS does not complete an issue, phase or baseline.

## Required context supplied to Gemma
- `AGENTS.md`
- `.birdai/governance.yaml`
- `.birdai/roadmap.yaml`
- `.birdai/AGENT_LOOP.md` and the current `AI_TASK.json`
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

## Mandatory execution slices

Issue != execution slice. An issue owns scope and acceptance and may require many
slices. Each task MUST have one technical goal, explicit observable PASS criteria,
exact allowed files, validation, maximum attempts, stop conditions and result schema.
Reference the full phase specification; never duplicate it in every AI_TASK.json.
Keep engineering, test infrastructure and feature/biology work in separate slices.

Record EXECUTION_SLICE: <id> and STATE: <state> in the parent issue. Only one slice
across all branches/workers/machines may be agent:working. One coordinator owns
dispatch; labels alone are not an atomic lock. If ownership is ambiguous, stop.
AI_RESULT.json must be an allowed file if written. Runtime sandboxes/logs belong
outside the worktree. Record task ID, base commit and attempt ledger at claim time.

## Diagnosis and hard anti-loop budget

Before correction record: observed failure -> likely location -> concrete hypothesis
-> minimal test. Localize representation, approximation, runtime, integration or
design hypothesis before considering any policy change. For new implementation,
inspect existing evidence and state the missing behavior before the initial edit.

- One hypothesis per iteration. One diagnostic run of the smallest relevant unit,
  then at most ONE targeted correction and ONE validation run. If the diagnostic
  run proves all PASS criteria, stop with PASS immediately.
- A run is one invocation of the task's validation command. A fixed check batch is
  allowed but cannot hide retries/unbounded loops. Count child invocations in evidence.
- Read exact failure evidence before the correction. If the second run fails,
  times out or is inconclusive, report BLOCKED and stop. Scope/authority conflicts
  block immediately; unused attempts do not authorize guessing.
- The same command, tool operation or recovery strategy has at most TWO uses per
  slice (initial use plus one repeat). Trivial parameter, quoting, slash or shell
  variants solving the same failure are the SAME strategy. Independent reads of
  different evidence are distinct operations, not retries of the same failure.
- Record strategy ID, operation/target, count and outcome BEFORE retrying. Counts
  survive handoff, restart and context loss. Renaming a task/hypothesis or increasing
  a timeout cannot reset them. Resuming BLOCKED requires explicit coordinator review
  and a revised task with new evidence, not an automatic fresh budget.

## Windows shell and deadlines

Use PowerShell for Windows administration, preferably pwsh -NoProfile. Use native
cmdlets and literal paths: Test-Path, Get-Content, New-Item, Remove-Item -LiteralPath.
Do not switch to CMD/Unix or use cmd /c, if exist, [ -f ], or mkdir -p. Direct Godot,
Python test and other executable calls from PowerShell are allowed. Existing user
.cmd launchers are unchanged; inspect them to obtain direct validation invocations.

Default fast harness timeout is 20 seconds wall clock for the entire invocation,
including child exit and cleanup; tasks may choose 15 seconds. Any longer timeout
requires a task-local reason tied to expected/measured work BEFORE launch. Never
extend a deadline just because the previous run hung. Runner/tool must enforce it;
an output-yield interval is not a timeout. If enforcement is unavailable, BLOCKED.

A PASS marker with a live parent is not PASS: require natural parent exit 0, child
termination and cleanup within 15 seconds after the marker AND the overall deadline.
Forced termination is failure. On timeout preserve evidence and terminate only
slice-owned processes, with a separate bounded 5-second recovery/cleanup window.
Unconfirmed termination/cleanup means BLOCKED. Never kill all Godot processes or
touch real Alma saves.

## Test observability standard

Every step emits scenario ID, n/N and monotonic elapsed seconds:

```text
[START 1/3] scenario=child-exit elapsed=0.000s child launch
[PASS 1/3] scenario=child-exit elapsed=0.420s child_pid=123 start_utc=... exit_code=0
[START 2/3] scenario=child-exit elapsed=0.421s parent exit
[FAIL 2/3] scenario=child-exit elapsed=20.000s reason=deadline parent_pid=122
```

Record executable, argv, working directory, version, seed if relevant, deadline,
parent/child PID, UTC start and observed exit code (null if unknown). Use an empty
child list when no child exists. Capture stdout/stderr separately and in full;
preserve exact failure streams as raw files with paths and SHA-256 hashes, not only
a summary or last line. Report last successful step, failing/current scenario,
timeout/termination, total elapsed and cleanup paths/results, including early failure.
Cleanup is PASS, FAIL or not_applicable; cleanup failure prevents slice PASS.

Use execution-result.schema.json for AI_RESULT.json. Schema validity alone does
not prove task-specific PASS, valid evidence or budget compliance; reviewer verifies
these plus allowed-file scope. Never invent missing evidence.

## Next Gemma task

Import .birdai/skills/birdai-implementation/SKILL.md into Bionic as
birdai-implementation. Resolve its paths against the target checkout and refresh
the import from this repo version when updated. Use New-ExecutionSlice.ps1 to create
a compact task; it never runs the command or overwrites an existing file:

```powershell
$slice = @{
  SliceId = 'e0-sandbox-process-exit-001'
  Issue = 'https://github.com/jonathanschonstrom/AlmaTheHen/issues/6'
  Goal = 'Make the existing outer harness and child exit cleanly.'
  PassDefinition = 'HARNESS PASS; child terminated; parent naturally exits 0 within 15s after PASS and 20s total; sandbox cleaned; no worktree runtime residue.'
  AllowedFiles = @('tests/test_persistence_migration.gd', 'AI_RESULT.json')
  ValidationCommand = '& $GodotExe --headless --path . --script tests/test_persistence_migration.gd'
  OutputPath = '../next-slice/AI_TASK.json'
}
& ./.birdai/New-ExecutionSlice.ps1 @slice
```

This example is a proposal, not dispatch. Coordinator first inspects the actual
branch/entry point, sets GodotExe, narrows validation to exclude migration scenarios
1-14 and configures a real deadline. Preserve the existing test file. Review/archive
the previous result and ledger before deliberately installing the task on the issue
branch. Do not overwrite the active persistence task from a documentation branch.
Then invoke @birdai-implementation with the current slice ID and task path only.

Deferred work is in TECHNICAL_DEBT.md. Roadmap order remains
E0 -> P1 -> E1 -> P1.5 -> P2 -> P3 -> P3.5 -> P4 -> P5 -> P6 -> P7.
