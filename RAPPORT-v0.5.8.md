# BirdAI v0.5.8 / NeuralBrain v0.2.7 — Neural Control + BG Readout

Experimentkandidat, 2026-09-11. **Inte ny baslinje.**

## Bakgrund

Första rena Windows-installationen av v0.5.7 / NeuralBrain v0.2.6 installerade Nengo 4.1.0, NumPy 2.2.6 och SciPy 1.18.1 korrekt men den kanoniska självtestsviten gav **55/63** (18/21, 18/21, 19/21).

För `mixed_manipulate` och `familiar_room` rapporterade testet uttryckligen att analytisk policy, neural valuation och competition hade rätt vinnare medan BG:s sista avläsning valde fel kanal. `commitment_expires` gav REST i stället för EXPLORE i alla tre seeds.

## Ändring

NeuralBrain v0.2.7 gör en enda neural ändring: `basal_ganglia.output`, som redan probes med 10 ms synapsfilter, läses som medelvärdet över de sista **30 ms** i stället för endast den sista simulatorpunkten. BG100, input-bias, action-value-paths, competition och temporal commitment är annars oförändrade.

Diagnostiken innehåller nu både `basal_ganglia` (30 ms-readout) och `basal_ganglia_instantaneous` (sista sample).

BirdAI v0.5.8 behåller v0.5.7:s Neural Control: NeuralBrain väljer faktisk handlingsfamilj och utility är endast diagnostisk referens.

## Acceptans

Kör i ordning:

1. `Installera NeuralBrain.cmd`
2. `Kor NeuralBrain-regression.cmd`
3. `Kor Neural Control-kontrakt.cmd`
4. `Kor NeuralBrain-test.cmd`
5. `Kor NeuralBrain-v0.2.7-robusthet.cmd`
6. Starta BirdAI och samla `data/neural-control.jsonl`

Ingen av de 63 kanoniska beteendekraven är ändrad. Om självtestet fortfarande missar ska JSON-resultatet analyseras; kandidaten får inte godkännas genom att sänka kraven.
