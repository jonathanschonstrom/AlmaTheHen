# v0.5.8 / NeuralBrain v0.2.7 evidence

This directory contains evidence for the BG-readout experiment candidate.

## Local verified evidence

- `pure-regressions.log`: 31/31 pure regression checks pass.
- `neural-control-static.log`: 27/27 static Neural-Control contract checks pass.
- `regression-v0.2.7-local.json`: structured local regression result.
- `neural-change-from-v0.2.6.diff`: isolated NeuralBrain change evidence.
- `source-manifest.json`: source provenance manifest.

## External acceptance still required

This candidate is **not approved for merge** until it has been run on the real Windows/Nengo environment that exposed the v0.2.6 BG readout failures.

Required acceptance:

1. Run `Kor NeuralBrain-test.cmd` on Windows and retain the resulting selftest JSON.
2. Run `Kor NeuralBrain-v0.2.7-robusthet.cmd` and retain the robustness report.
3. Confirm that the previously observed downstream BG misselections (`mixed_manipulate`, `familiar_room`, `commitment_expires`) are removed without regressions in canonical scenarios.
4. Keep `main` on the verified v0.5.7 baseline until the above evidence is reviewed.
