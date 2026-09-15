# Windows/Nengo v0.2.6 known failures

Environment observed on the real Windows session:

- Python 3.12.10
- Nengo 4.1.0
- NumPy 2.2.6
- SciPy 1.18.1
- NeuralBrain v0.2.6
- 11,890 neurons

Canonical selftest result: **55/63 PASS**.

Observed failures:

- `mixed_manipulate`: valuation and competition select `MANIPULATE`, while BG can select another channel (`SOCIAL` or `FLEE`).
- `familiar_room`: valuation and competition select `EXPLORE`, while BG can select `FLEE` or `DRINK`.
- `commitment_expires`: commitment expires correctly and competition returns to `EXPLORE`, while BG can select `REST`.

The real Neural-Control session additionally showed that a downstream BG misselection can propagate to a real actuator action (for example a false `FLEE`).

This document records the acceptance target for v0.2.7. The v0.2.7 candidate must be tested in the same Windows/Nengo environment before merge.
