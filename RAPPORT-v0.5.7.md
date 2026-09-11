# BirdAI v0.5.7 / NeuralBrain v0.2.6 — Neural Control

Experimentkandidat. **Inte en ny baslinje.**

## Mål

Denna kandidat testar en enda arkitekturell förändring: NeuralBrain v0.2.6 får faktisk beslutsauktoritet över Almas handlingsfamilj i normal körning. Utility-systemet behålls som diagnostisk jämförelse men får inte välja den verkliga handlingen i control-läge.

NeuralBrain-matematiken är oförändrad från v0.5.6: BG100, EXPLORE, MANIPULATE, decoderinställningar och temporal commitment har inte justerats.

## Kontrollflöde

Normal start (`Starta BirdAI.cmd`) använder:

`värld/kropp -> perception -> 16 NeuralBrain-inputs -> Nengo/BG100 -> selected family -> neural_action_resolver -> konkret Godot-handling -> värld/kropp`

`utility.gd` körs parallellt endast för referensloggning. Dess RNG-användning isoleras genom att agentens RNG-state sparas och återställs runt referensberäkningen.

Legacy shadow kan startas explicit med `Starta Neural Shadow.cmd`.

## Family -> actuator

NeuralBrain v0.2.6 är fortfarande ett family-level-system. Därför tillkommer `scripts/cognition/neural_action_resolver.gd`. Den väljer **inte mellan familjer** och innehåller inga utility-poäng. Den översätter endast NeuralBrains redan valda familj till en genomförbar motorhandling och ett aktuellt sensoriskt mål:

- FLEE -> `flee/safe`
- DRINK -> det aktuellt observerade vatten som starkast bidrar till vatten-signalen
- EAT -> den aktuellt observerade föda som starkast bidrar till food-signalen
- REST -> observerad genomförbar viloplats/perch, annars `rest/self`
- SOCIAL -> observerad person, annars `call/self`
- CARE -> observerad vårdplats, annars `preen/self`
- EXPLORE -> `wander/ground`
- MANIPULATE -> närmaste observerade manipulerbara objekt + enkel affordancebaserad motorprimitive

Detta är avsiktligt ett actuatorlager, inte en alternativ beslutsmodell.

## Ingen dold fallback

Om NeuralBrain saknas, kraschar eller tappar anslutningen i control-läge används inte utility som reservcontroller. Pågående motorprimitive får normalt avslutas och agenten väntar därefter på NeuralBrain. Ett nytt neuralt FLEE-val får avbryta en pågående icke-defensiv primitive omedelbart. Den äldre Godot-regeln som själv avbröt en handling vid hög `safety` är därför begränsad till legacy utility/shadow-läge; i control-läge är `safety` en NB-input och det krävs ett faktiskt NB-val av FLEE för motoravbrottet.

## Loggning

Control-läge skriver `data/neural-control.jsonl`.

Utöver tidigare neurala diagnostikfält loggas bland annat:

- `control_mode`
- `actuator_authority`
- faktisk agenthandling före applicering
- faktisk handlingsfamilj före applicering
- agentfas
- agentposition
- senaste faktiskt aktuerade NB-familj/action/target (`last_neural_actuation`)
- utility-familj som diagnostisk referens

Shadow-läge fortsätter skriva `data/neural-shadow.jsonl`.

## Avgränsning

Denna kandidat gör **inte** NeuralBrain mer perceptuellt detaljerad. De befintliga semantiska inputsignalerna (`food`, `water`, `person`, `novelty`, osv.) behålls. Spatial target selection och råare perception är separata framtida steg efter att controller-loopen verifierats.

Miljön är också oförändrad i denna kandidat.

## Filer med avsiktlig kontrolländring

- `scripts/cognition/agent.gd`
- `scripts/cognition/neural_brain_bridge.gd`
- `scripts/cognition/neural_action_resolver.gd` (ny)
- `scripts/main.gd`
- `scripts/view/inspector.gd`
- `tests/run_tests.gd`
- `tests/test_neural_control_static.py` (ny)
- `Starta BirdAI.cmd`
- `Starta Neural Shadow.cmd` (ny)
- `Starta kompatibilitetslage.cmd`
- `Installera NeuralBrain.cmd`
- `Kor Neural Control-kontrakt.cmd` (ny)
- `project.godot`, `VERSION.txt`, `README.md` och denna rapport

Utility, fysiologi, homeostasis, learning, memory, perception, world och persistence ska förbli oförändrade mot v0.5.6.

## Acceptance för Windows

1. `Kor tester.cmd` passerar, inklusive de nya controller-kontrakten.
2. `Kor NeuralBrain-regression.cmd` är oförändrad mot v0.5.6.
3. `Kor NeuralBrain-test.cmd` och robustness ger samma neurala resultat som v0.5.6 inom seedvariationen; controllerbytet ska inte användas för att "fixa" 60/63-problemet.
4. Normal grafisk start visar att faktiska utförda handlingar kommer från NB-familjer.
5. Vid avstängd NeuralBrain står agenten utan ny beslutsauktoritet; utility får inte ta över.
6. `Starta Neural Shadow.cmd` reproducerar explicit legacy shadow-beteende.
7. `utility.gd`, fysiologi, homeostasis, learning, memory, perception, world och persistence är byte-identiska med v0.5.6.
