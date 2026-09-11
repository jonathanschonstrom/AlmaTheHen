# Pull request notes

This candidate intentionally changes only the NeuralBrain basal-ganglia **readout**, not policy or action valuation.

The existing 10 ms filtered BG probe is retained. Action selection uses the mean of the final 30 ms rather than one final 1 ms sample. The instantaneous value is preserved as a diagnostic.

Do not merge before Windows/Nengo acceptance evidence is attached and reviewed.
