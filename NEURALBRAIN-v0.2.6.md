# NeuralBrain v0.2.6

Experimentkandidat ovanpå BirdAI v0.5.5 / NeuralBrain v0.2.5-rekonstruktionen.

## Avgränsad ändring

De fyra faktoriserade EXPLORE-avkodarna tränas nu med `scale_eval_points=False`:

- `_explore_base_value`
- `_hunger_search_value`
- `_thirst_search_value`
- `_explore_safety_gate`

Eval-punkterna skapades redan i de fysiska koordinater som populationerna representerar. I v0.2.5 använde dessa fyra anslutningar Nengos standard `scale_eval_points=True`, vilket skalar explicit angivna punkter med pre-populationens `radius`. MANIPULATE v0.2.5 använde redan `False` för motsvarande explicita 0–1-punkter.

Ingen analytisk vikt eller formel har ändrats. BG100, BG bias 0, REST commitment 0,130, switch-marginal 0,080, temporal state machine och MANIPULATE-faktorisering är oförändrade.

## Ny diagnostik

`explore_diagnostics` loggar de faktiska filtrerade anslutningsutdata som redan går genom nätet:

- EXPLORE/novelty/open-space/hunger/food/thirst/water/safety in till delbanorna
- base, hunger-search och thirst-search decoder-output
- subtotal till safety-gaten
- safety-gatens decoder-output
- slutligt EXPLORE action value

`brain/selftest.py` lägger bredvid detta den analytiska EXPLORE-dekompositionen för samma input. Diagnostiken styr aldrig en handling.

## Verifiering

`Kor NeuralBrain-regression.cmd` kör rena regressioner utan Nengo-runtime.

`Kor NeuralBrain-test.cmd` kör de oförändrade tre kanoniska seedsen × 21 krav.

`Kor NeuralBrain-v0.2.6-robusthet.cmd` kör 10 fasta seeds och kräver både alla beteendekrav, 100 % neural/analytical winner-match och 100 % BG/competition winner-match för PASS.
