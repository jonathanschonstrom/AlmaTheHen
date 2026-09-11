# BirdAI v0.5.7 / NeuralBrain v0.2.6 — Neural Control

**Experimentkandidat. Ingen ny baslinje utses före Windows/Nengo-verifiering.**

Den neurala modellen är oförändrad från v0.5.6. Den stora skillnaden är integrationslagret: i normal körning är **NeuralBrain faktisk beslutsfattare för handlingsfamiljen**, medan `utility.gd` endast körs som diagnostisk referens.

## Normal körning

1. Packa upp i en ny mapp.
2. Kör `Installera NeuralBrain.cmd`.
3. Kör `Kor NeuralBrain-regression.cmd`.
4. Kör `Kor NeuralBrain-test.cmd`.
5. Kör `Kor NeuralBrain-v0.2.6-robusthet.cmd` om den neurala v0.2.6-kandidaten också ska verifieras.
6. Starta `Starta BirdAI.cmd`.

Normal start använder neural control. Om NeuralBrain inte är tillgänglig finns **ingen utility-fallback**.

För den äldre diagnostiska kontrollformen, starta `Starta Neural Shadow.cmd`. Då styr utility agenten och NeuralBrain observeras parallellt.

## Kontrollarkitektur

`värld/kropp -> perception -> NeuralBrain -> BG100/commitment -> vald familj -> neural_action_resolver -> agent/world`

NeuralBrain v0.2.6 väljer fortfarande familj (`FLEE`, `DRINK`, `EAT`, `REST`, `SOCIAL`, `CARE`, `EXPLORE`, `MANIPULATE`) snarare än exakt objekt och motorsekvens. Den nya resolverkomponenten är därför ett poängfritt actuatorlager som väljer ett genomförbart sensoriskt mål inom den redan valda familjen.

Utility används aldrig som family-selector i control-läge.

## Loggar

- Neural control: `data/neural-control.jsonl`
- Explicit shadow: `data/neural-shadow.jsonl`
- Godot runtime: `data/runtime.log`

Se `RAPPORT-v0.5.7.md` för exakt avgränsning och Windows-acceptance.
