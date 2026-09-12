# Deferred engineering work

These follow-ups are recorded, not dispatched. Roadmap order remains
E0 -> P1 -> E1 -> P1.5 -> P2 -> P3 -> P3.5 -> P4 -> P5 -> P6 -> P7.

| ID | Evidence / gap | Follow-up and acceptance | Gate / status |
| --- | --- | --- | --- |
| TD-001 | Reported E0 harness prints PASS then hits outer timeout. | Isolate child and parent natural exit 0, external sandbox cleanup and no worktree residue. | E0 test infrastructure; deferred; no persistence scenarios here. |
| TD-002 | Existing harnesses do not uniformly emit the v2 observability contract. | Adopt scenario/step/time/process/raw-stream/cleanup evidence one harness slice at a time. | Current phase only; deferred. |
| TD-003 | Instructions alone cannot enforce Bionic retries, deadlines or concurrent claims. | Runner-side persisted budget/strategy ledger, watchdog and atomic claim; prove third equivalent attempt/concurrent claim rejected and timeout children cleaned. | Engineering integration deferred; runner absent from repo. Current dispatch requires deadline support and one coordinator. |
| TD-004 | Active persistence task has an older protocol; generated output is not a verified Bionic transport adapter. | Import repo skill, check field compatibility, archive previous result/ledger and explicitly install reviewed task; bounded dry run before product work. | E0 handoff deferred; never overwrite active task automatically. |
| TD-005 | Planning identified later persistence refactor and neural integration verification. | Review persistence after accepted E0 behavior; verify actual NeuralBrain-to-Godot control at P1. | E0 acceptance then P1; no premature refactor, tuning or baseline declaration. |
