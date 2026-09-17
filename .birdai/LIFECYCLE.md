# E1: run again, verify, advance, stop at the human gate

`Run-Lifecycle.ps1` is the coordinator for registered experiments. It does not ask
an implementation model to decide whether an experiment passed, invent research
parameters, accept a neural baseline, or move the roadmap forward.

The states are:

```text
registered -> apparatus_preflight -> ready_to_run -> running
  -> invalid_technical | completed_valid -> result_verified
  -> acceptance_pr_open -> acceptance_merged -> postmerge_verified
  -> execution_issue_closed -> waiting_for_human_registration
```

Every invocation verifies the retained evidence before advancing. Repeating the
same invocation resumes the journal; it does not restart the experiment. The
default PowerShell launcher continues through machine steps until the next gate.
`-OneStep` advances exactly one transition and `-Status` only inspects the state.

## The three human decisions

1. Preregister the hypothesis, seeds, variables, snapshot and runtime. Put its
   hash and technical lifecycle plan in the experiment registry through review.
2. Review the result and approve the exact acceptance PR/head shown by the tool.
3. Separately approve closing the execution issue after post-merge verification.

The merge and close approvals cannot be supplied together. Saved approvals remain
valid across restart only for the exact PR head or issue/merge identity. Changing
the reviewed head invalidates the permission. Failed or pending CI prevents merge.
There is no `--admin`, automatic phase transition, or PR `Closes #...` shortcut.

## Run and resume

From the repository, with a working Python interpreter and authenticated `gh`:

```powershell
& .\.birdai\Run-Lifecycle.ps1 -Repo C:\AlmaTheHen -Python <python.exe> -Status
& .\.birdai\Run-Lifecycle.ps1 -Repo C:\AlmaTheHen -Python <python.exe>
```

At the merge gate, use the exact token printed in `human_gate.token`:

```powershell
& .\.birdai\Run-Lifecycle.ps1 -Python <python.exe> -ApproveMerge '<PR>:<reviewed-head-SHA>'
```

The coordinator merges with `--match-head-commit`, fast-forwards clean main,
verifies the merged acceptance record, and runs `verify-registry` and `status`.
It then stops at the separate issue-close gate:

```powershell
& .\.birdai\Run-Lifecycle.ps1 -Python <python.exe> -ApproveClose '<issue>:<verified-merge-SHA>'
```

Use the same state directory for all invocations on the machine. The default is
`%USERPROFILE%\AppData\Local\BirdAI\lifecycle`, keyed by repository slug. A kernel
lock excludes simultaneous coordinators. Runtime evidence and acceptance
worktrees live outside the product worktree. Do not run a second coordinator
against the same repository from another machine; this is a local ownership lock,
not a distributed GitHub lock. Existing `agent:working` claims are checked before
an experiment starts.

## Registration-side technical plan

Add `lifecycle` to a newly reviewed registry entry. Commands are argument arrays,
not shell strings. This example is a template, not an experiment registration:

```json
{
  "lifecycle": {
    "preflight": {
      "argv": ["<python.exe>", "-B", "<registered-harness.py>", "--apparatus-preflight"],
      "timeout_seconds": 120,
      "timeout_reason": "Bounded compile/startup of each preregistered apparatus arm.",
      "success_marker": "STATUS: PASS"
    },
    "run": {
      "argv": ["<python.exe>", "-B", "<registered-harness.py>"],
      "timeout_seconds": 3600,
      "timeout_reason": "Measured duration of the declared paired runs, including cleanup."
    },
    "evidence_root": "C:/BirdAI_E1_evidence"
  }
}
```

The harness must emit exactly one `SUMMARY: <absolute path>` line. The summary
must identify the registration, runtime, source snapshot, full ordered seed set,
all declared paired arms, pair comparisons and hashed run capsules. Artifact
paths and hashes are recursively checked, including hashed traces inside the
capsules. `NOT_SUPPORTED`, `SEED_SENSITIVE` and `INCONCLUSIVE` remain legitimate
research outcomes when the preregistered technical validity is PASS. The
coordinator does not recalculate or retune the research hypothesis.

## Recovery

An experiment that already completed manually can be imported without rerunning:

```powershell
& .\.birdai\Run-Lifecycle.ps1 -Python <python.exe> -Issue <number> -AdoptSummary <summary.json>
```

For an already merged manual acceptance PR, also supply `-AdoptPr <number>`.
Its registry result must match the verified summary; its merged code is checked
before issue closure. An unmerged imported PR must follow the generated acceptance
branch/record contract, so unrelated manual changes are never silently accepted.

An interrupted command without a complete verified receipt becomes
`invalid_technical`. It is not automatically rerun. Evidence and attempt counts
survive restarts. One targeted correction can be explicitly authorized after
review, with the failed attempt number and a reason:

```powershell
python -B .birdai/e1_lifecycle.py --repo C:/AlmaTheHen --issue <number> --authorize-correction 1 --reason '<reviewed diagnosis and correction>'
```

There is no third experiment attempt. Existing commits and PRs are rediscovered
through a deterministic branch and exact evidence identity. An inconclusive
merge/close response is checked against GitHub before a repeated mutation; the
same remote request has at most two uses. A closed, unmerged PR is a review
disposition and will not cause a replacement PR to be opened automatically.

Windows children enter a kill-on-close Job Object before launching the harness.
Timeouts terminate only that owned process tree. Raw stdout and stderr, process
identity, deadline, exit status and hashes are written into durable receipts.
Forced termination is never reported as a successful experiment.

No scheduler is needed for the human gates: invoking the same launcher again is
the resume operation. With no eligible registration, the normal idle state is
`waiting_for_human_registration`, not a failed experiment.
