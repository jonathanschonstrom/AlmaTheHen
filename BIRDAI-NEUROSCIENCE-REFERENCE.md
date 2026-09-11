# BirdAI – neurovetenskaplig referensram

**Forskningsgrund, designprinciper och spårbarhet för BirdAI v0.5.6 / NeuralBrain v0.2.6**

*Referensram v1.0 · 11 september 2026*

> Denna referensram skiljer mellan biologisk evidens, computational-neuroscience-hypoteser och BirdAI-specifika implementationsval.

## 1. Syfte och användning

Detta dokument är BirdAI-projektets neurovetenskapliga referensram. Syftet är att skilja mellan vad som är direkt belagt i fåglar, vad som är rimlig vertebrat-extrapolering, vad som endast är en computational-neuroscience-hypotes och vad som är ett rent BirdAI-implementationsval.

Referensramen ska användas vid arkitekturändringar från och med BirdAI v0.5.6 / NeuralBrain v0.2.6. Ett misslyckat regressionstest är i sig inte skäl att ändra en biologisk princip. Först ska felet lokaliseras till representation, approximation, dynamik eller själva designhypotesen.

> **Designregel:** Kärnregel: forskning definierar principer och begränsningar. Den bestämmer inte automatiskt neuronantal, Nengo-radius, synapstider, vikter, seedar, trösklar eller commitment-tider.

## 2. Evidenshierarki

| Nivå | Definition | Hur den får användas |
|---|---|---|
| A – direkt galliform evidens | Resultat från tamhöna/kyckling, vaktel eller nära galliform modell. | Kan styra biologiska principer för Alma relativt direkt, men inte numeriska parametrar utan mätdata. |
| B – direkt avian evidens | Resultat från andra fåglar, t.ex. duva eller sångfågel. | Starkt stöd för fågelgemensam mekanism; artöverföring ska anges. |
| C – vertebrat/computational | Konserverade vertebratkretsar eller biologiskt plausibla modeller. | Får användas som arkitekturhypotes, inte som artspecifik sanning. |
| D – BirdAI-modellval | Ingen direkt biologisk motsvarighet visad. | Måste beskrivas som implementation/ingenjörsval och valideras separat. |

Evidensstyrka anges dessutom som stark, måttlig eller hypotes. “Stark” betyder inte att implementationens numeriska parametrar är biologiskt uppmätta; endast att den övergripande mekanismen har robust stöd.

## 3. Anatomisk grund för en artificiell fågelhjärna

Den moderna avian-nomenklaturen är central för BirdAI. Det är fel att beskriva större delen av fågelns telencephalon som basal ganglia. Reiner et al. visar att stora dorsala delar är palliala, medan verkliga striatala och pallidala strukturer ligger subpallialt. Medialt/lateralt striatum, globus pallidus, ventral pallidum, nucleus accumbens-liknande områden, SNc/SNr och VTA har tydliga vertebrata motsvarigheter [R1].

Konsekvensen är att BirdAI inte bör använda “basal ganglia” som synonym för hela beslutssystemet. Sensorisk integration, exekutiv kontext och målhållning bör konceptuellt skiljas från själva action-selection-kretsen.

| Biologiskt system | Funktionell roll | BirdAI-motsvarighet idag | Tolkning |
|---|---|---|---|
| Palliala sensoriska nätverk | Sensorisk analys, objekt/kontext | exteroception + Godot perception | Komprimerad funktionell abstraktion |
| NCL (nidopallium caudolaterale) | Exekutiv integration, arbetsminne, mål-/regelunderhåll | integrated_state och delar av värderingslogiken | Funktionell analogi, inte anatomisk homologi |
| Hippocampal formation | Spatialt minne/orientering | memory.gd / framtida spatial minnesmodul | Ofullständigt representerad neuralt |
| Hypothalamus/hjärnstam | Homeostas, föda, vätska, kroppssignaler | interoception + physiology/homeostasis | Funktionell abstraktion |
| Striatum/pallidum/BG | Konkurrens och urval av handling | Nengo BasalGanglia | Projektets starkaste anatomiska ankare |
| Amygdala/arcopallium–PoA-komplex | Hot, affekt, social relevans | safety/threat och FLEE-gating | Endast delvis representerad |
| Motor-/hjärnstamsystem | Utförande av vald handling | Godot actuator/agent | Utanför NeuralBrain-kärnan |

## 4. Sensorik och exteroception

Fågelns visuella system består inte av en enda “kamera-till-kortex”-väg. Avian syn bearbetas genom bland annat tectofugala och thalamofugala banor; i duva finns väl beskriven hierarkisk behandling av lokalisering, objektinformation, uppmärksamhet och objekt/ansiktsrepresentation [R4].

BirdAI:s exteroception med skalära kanaler som FOOD, WATER, PERSON, REST_SITE, CARE_SITE, NOVELTY, MANIPULABLE, MOTION och OPEN_SPACE är därför bäst beskriven som ett affordance-komprimerat perceptuellt gränssnitt. Den är inte en anatomisk simulering av avian syn.

> **Designregel:** Designkonsekvens: behåll separationen mellan rå världssignal och neuralt beslutsunderlag. Undvik framtida genvägar där rå Godot-input kopplas direkt till action populations enbart för att förbättra testresultat.

På längre sikt bör objektidentitet, rörelse, avstånd, social kategori och spatial plats kunna representeras som separata men integrerbara populationer. Det skulle ligga närmare hur fågelhjärnan löser sensorisk-to-action integration än en enda global “exteroception”-vektor.

## 5. Interoception och homeostas

Hos kyckling regleras födointag genom samverkan mellan centrala nervsystemet, mag-tarmkanal, hormoner, näringssignaler, hypothalamus och medulla oblongata. Viktigt är att vissa signaler skiljer sig från däggdjur; exempelvis kan ghrelin ha motsatt aptiteffekt i kyckling jämfört med typisk däggdjursmodell [R5]. Detta är ett starkt argument för att prioritera fågeldata framför däggdjursantaganden.

Törst är också en verklig reglerad drive: både perifer och central angiotensin II-administration har visats framkalla drickande hos tamhöns [R6]. Det stödjer att DRINK ska drivas av intern vätskestatus i kombination med tillgång till vatten, snarare än av tid eller slump.

BirdAI:s interoception – hunger, thirst, rest, explore, social, safety och comfort – är dock inte sju identifierade biologiska variabler. Det är ett lågdimesionellt kontrollgränssnitt. Hunger/thirst/rest har relativt tydliga fysiologiska ankare; explore/social/safety/comfort är mer sammansatta motivations- eller tillståndsvariabler.

> **Designregel:** Designkonsekvens: resurser ska utvecklas av simulerad metabolism/aktivitet och återställas av relevant beteende. Världsklockan får vara tidsbas men bör inte ensam vara den biologiska orsaken till hunger, törst eller trötthet.

## 6. Exekutiv integration och målunderhåll

Nidopallium caudolaterale (NCL) är en central avian struktur för arbetsminne och exekutiva funktioner. Den jämförs funktionellt med däggdjurs prefrontala cortex, men betraktas som konvergent snarare än en enkel homolog. Dopamin D1-modulation och ihållande aktivitet kan stödja att mål eller stimuli hålls aktiva över tid [R2].

Nyare anatomi visar dessutom parallella pallio-motoriska loopar från NCL mot bland annat intermediate arcopallium och medialt striatum, vilket placerar NCL i övergången mellan sensorisk/exekutiv integration och motoriskt handlingsurval [R3].

Detta ger stöd för BirdAI:s övergripande uppdelning “integrerat tillstånd → handlingsvärden → BG → premotoriskt val”. Däremot ger litteraturen inget stöd för att integrated_state som en enda 16-dimensionell Nengo-ensemble är den biologiskt korrekta implementationen.

## 7. Action valuation och basal ganglia

Basal ganglia är den mest välgrundade delen av BirdAI:s neurala arkitektur. Vertebratdata stödjer en evolutionärt konserverad strategi där basala ganglier bidrar till urval av handling genom modulära kanaler och disinhibition av downstream motoriska system [R10]. Avian nomenklatur visar dessutom verkliga striatala, pallidala och dopaminerga homologer i fågelhjärnan [R1].

Sångfågelstudier visar att basal-ganglia-kretsar inte bara väljer motorik utan kan reglera beteendevariabilitet och lärande; dopamin kan förändra basal-ganglia-output och variabilitet i en socialt beroende kontext [R12].

BirdAI:s åtta diskreta handlingskanaler – FLEE, DRINK, EAT, REST, SOCIAL, CARE, EXPLORE, MANIPULATE – är däremot en projektontologi. Den biologiska litteraturen säger inte att en höna har exakt åtta exklusiva kanaler eller att de ska representeras som en vektor med en vinnare.

> **Designregel:** Designkonsekvens: behåll BG som action-selection-princip, men behandla antal kanaler, Nengo-neuronantal, input_bias, gain, synapser och decoderinställningar som tekniska parametrar tills de har separat evidens.

## 8. Exploration kontra exploitation

Humphries, Khamassi och Gurney visade i biologiskt grundade basal-ganglia-modeller att toniskt striatalt dopamin kan förändra exploration–exploitation-balansen genom att modulera action-selection-output [R11]. Detta är computational evidence, inte bevis för BirdAI:s specifika EXPLORE-formel.

Sångfågelkretsar ger direkt avian stöd för att basal ganglia och dopamin kan modulera trial-to-trial-variabilitet och explorativ motorisk variation [R12, R14].

BirdAI v0.2.6:s faktoriserade EXPLORE – base + hunger_search + thirst_search följt av safety gate – är därför en rimlig modelleringshypotes: exploration påverkas av intern drive, möjlighet/novelty och säkerhet. Men vikterna, exponenterna och faktoriseringen är D-nivå-implementation. De ska valideras mot robust beteende och inte beskrivas som biologiskt uppmätta.

Den aktuella v0.2.6-ändringen, scale_eval_points=False för de fyra EXPLORE-decodrarna, är uttryckligen en representationskorrigering i Nengo. Den förändrar inte någon biologisk hypotes och ska inte ges neurobiologisk innebörd.

## 9. Manipulation, objekt och affordances

Komplex objektmanipulation är tydligast studerad hos korvider och papegojor. Tool-use-litteraturen pekar mot NCL och andra palliala nätverk, men de neurala substraten är långt ifrån fullständigt kartlagda [R18]. Detta ger stöd för att manipulation kräver mer än “novelty = hög”; objektets egenskaper, mål, erfarenhet och aktuell motivation bör bidra.

BirdAI:s MANIPULATE-path är därför biologiskt plausibel som en separat handlingsfamilj men inte specifikt validerad för tamhöna. Den faktoriserade v0.2.5/v0.2.6-implementationen är främst ett robust neuralt representationsval.

> **Designregel:** Designkonsekvens: utveckla MANIPULATE genom rikare objekt-affordances och erfarenhetsberoende värde innan vi lägger till mer decoder-komplexitet.

## 10. Hot, rädsla och FLEE

Arcopallium/posterior pallial amygdala-komplexet är funktionellt heterogent men har en dokumenterad roll i kontroll av rädslebeteende hos fåglar. Lesionsstudier på japansk vaktel visar differential involvering av dess subdivisioner i bland annat novel-object, open-field och tonic-immobility-test [R17]. Modern nomenklatur placerar samtidigt posterior pallial amygdala och nucleus taeniae inom avian amygdala-komplex [R1].

BirdAI:s safety/threat-signal och att starkt hot kan bryta temporal commitment är därför funktionellt rimligt. Men en enda skalär SAFETY representerar många biologiskt skilda processer: predator detection, arousal, risk assessment, freezing, avoidance och escape.

> **Designregel:** Designkonsekvens: hot ska få preemptiv prioritet över svag handlingspersistens. Exakt threat threshold och bypass-logik är dock D-nivå-parametrar.

## 11. Social perception och social motivation

Sociala mekanismer är starkt utvecklade hos fåglar. Mesotocin/vasotocin-system och social-behavior networks är evolutionärt konserverade och kopplade till gregariousness, affiliation, pair bonding, aggression och andra sociala beteenden [R15].

Hos visuellt naiva domestic chicks aktiveras nucleus taeniae of the amygdala starkare av en naturalistisk höna än av en visuellt matchad men “scrambled” kontroll, vilket visar tidig neural känslighet för socialt relevanta stimuli [R16].

BirdAI:s PERSON + SOCIAL → SOCIAL action fångar endast en liten del av detta. På sikt bör social identitet, familiarity, dominance, affiliation, separation och flockkontext skiljas från en allmän social drive.

CARE bör tills vidare ses som projektets handlingskategori, inte som en neuroanatomiskt etablerad separat kanal. Om parental/care-beteende blir centralt behövs en egen galliform litteraturgenomgång.

## 12. Spatialt minne och orientering

Avian hippocampal formation har robust koppling till spatial inlärning, minne och orientering. Lesioner och komparativa studier stödjer funktionell likhet med däggdjurs hippocampus i spatiala uppgifter, även om exakt organisation skiljer sig [R7].

BirdAI har idag minnes- och världssystem men NeuralBrain-kärnan har ingen tydlig hippocampus-liknande spatial karta eller episodisk platsrepresentation. Detta är en av de tydligaste biologiska luckorna om målet är en djupare artificiell fågel snarare än endast reaktiv handlingsselektion.

> **Designregel:** Prioriterad framtida modul: plats-/kontextminne som kan påverka action values utan att hårdkoda världskoordinater direkt i BG.

## 13. Lärande, dopamin och performance error

Sångfågeln ger ett ovanligt starkt experimentellt fönster in i avian reinforcement learning. Basal-ganglia-projecting VTA-dopaminneuroner visar felrelaterade svar när sångutfall är bättre eller sämre än förväntat [R13]. Modeller av sångfågellärande beskriver hur BG-kretsar kan använda intern evaluering, dopaminmodulerad plasticitet och motorisk variation för att förbättra beteende [R14].

Detta motiverar att BirdAI på sikt skiljer mellan “värdera nuvarande handling” och “lära av utfallet”. En statisk utility-formel och ett plasticitetssystem är inte samma mekanism.

> **Designregel:** Designkonsekvens: om dopamin införs bör den primärt representera modulering/lärsignal eller policyregim, inte en generell “belöningspoäng” som adderas till alla action values.

## 14. Vila, sömn och återhämtning

Fåglar uppvisar både slow-wave sleep och REM-liknande sömntillstånd. Avian slow-wave activity regleras homeostatiskt och kan vara lokal: mer användning av en visuell hjärnregion under vakenhet kan ge lokal ökning i efterföljande slow-wave activity [R8]. Översikter visar dessutom djupa paralleller och skillnader mellan avian och mammalian sleep [R9].

BirdAI:s REST är därför biologiskt motiverad som mer än en låg utility eller “gör ingenting”. Rest/sömn bör på sikt påverka intern återhämtning, neural plasticitet/minneskonsolidering och aktivitetsberoende behov.

Den nuvarande REST commitment strength 0.130 och duration 1.25 s är däremot helt och hållet simuleringsparametrar. De motsvarar inte fågelsömnens fysiologiska tidskalor.

## 15. Temporal commitment, persistens och hysteresis

Ett djur byter inte nödvändigtvis mål varje gång två momentana värden korsar varandra. NCL-litteratur om ihållande mål-/arbetsminnesaktivitet [R2] och basal-ganglia-litteratur om stabilt handlingsurval [R10] gör beteendepersistens funktionellt rimlig.

Det finns däremot inget stöd i de granskade källorna för BirdAI:s exakta FREE/LATCHED/HOLD-state machine, SWITCH_MARGIN 0.080 eller handlingsspecifika hold-tider. TemporalCommitment ska därför behandlas som en D-nivå kontrollmekanism som stabiliserar ett diskret 5 Hz-beslutssystem, inte som en direkt simulerad hjärnstruktur.

> **Designregel:** Krav: framtida tuning av commitment ska motiveras av beteendedynamik och sensitivitetsanalys, inte beskrivas som “mer biologisk” om ingen tidsdata finns.

## 16. Bedömning av BirdAI v0.5.6 / NeuralBrain v0.2.6

| Komponent | Evidensnivå | Bedömning |
|---|---|---|
| Separat interoception / exteroception | B–D | Biologiskt rimlig uppdelning, men dimensionerna är projektval. |
| Integrated state före action valuation | B/C | Passar avian exekutiv/sensorimotorisk integration; ingen 1:1-anatomi. |
| Diskreta action values | C/D | Användbar computational abstraktion. Inte visad som åtta separata fågelkanaler. |
| BasalGanglia som konkurrenslager | A/B/C | Starkt principstöd. Den specifika Nengo-implementationen är teknisk. |
| EXPLORE factorisering | B/C/D | Motiverad princip, men formel och weights är projektval. |
| MANIPULATE factorisering | B/D | Objektbeteende har avian stöd; höna-specifik neural mapping är svag. |
| Threat bypass av commitment | A/B/D | Funktionellt rimligt; exakt tröskel/logik är modellval. |
| FREE/LATCHED/HOLD | D med funktionellt stöd | Bra stabiliseringsabstraktion; inte en anatomisk modell. |
| REST som aktiv drive | A/B | Starkt stöd för homeostatisk sömn/vila; aktuella sekunder är ej biologiska. |
| Social action | A/B | Starkt stöd för särskilda sociala system; nuvarande representation är grov. |
| CARE action | D | Behöver riktad galliform parental/care-evidens innan stark biologisk tolkning. |
| Spatial/episodiskt minne | A/B – men saknas neuralt | Klar kandidat för framtida arkitektur. |
| Dopaminbaserat lärande | B/C – ännu ej kärnmekanism | Starkt framtidsspår, särskilt för outcome learning. |

Samlad bedömning: arkitekturen har en rimlig vertebrat/avian kärna – homeostatiska drives, sensorisk kontext, pallial integration, action valuation, basal-ganglia-selection och motoriskt utfall – men den ska beskrivas som en biologiskt inspirerad funktionsmodell, inte en helhjärnesimulering.

## 17. Spårbarhetsmatris: forskning → design → kod/test

| ID | Forskningspåstående | Evidens | BirdAI-konsekvens | Nuvarande implementation | Status | Källor |
|---|---|---|---|---|---|---|
| ANA-01 | Fågelns telencephalon består av omfattande pallium samt verkliga subpalliala BG-strukturer. | A/B · stark | Skilj integration från basal ganglia. | Intero/extero + integrated_state + separat BG | Implementerad princip | R1 |
| EXO-01 | Avian vision har parallella banor och hierarkisk objekt/lokaliseringsbearbetning. | B · stark | Exteroception bör vara preprocessad representation, inte rå sensorström direkt till handling. | exteroception | Delvis | R4 |
| INT-01 | Födointag hos kyckling integrerar CNS, hypothalamus/medulla, tarm, hormoner och näring. | A · stark | Hunger ska vara fysiologisk drive kopplad till resurser/metabolism. | hunger + physiology/homeostasis | Delvis | R5 |
| INT-02 | Angiotensin II kan utlösa drickrespons i tamhöns. | A · måttlig/stark | Törst ska ha intern fysiologisk orsak och vatten-affordance. | thirst + WATER -> DRINK | Implementerad princip | R6 |
| EXEC-01 | NCL stödjer working memory och goal-state maintenance. | B · stark | Behåll exekutiv/integrativ nivå före motoriskt urval. | integrated_state / valuation | Funktionell analogi | R2 |
| EXEC-02 | NCL har nedåtgående pallio-motoriska loopar mot arcopallium och medial striatum. | B · stark | Sensorisk/exekutiv state kan påverka motor/BG-kanaler via separata banor. | valuation -> BG -> actuator | Principstöd | R3 |
| BG-01 | Basal ganglia action selection är en konserverad vertebratstrategi. | C + avian anatomi · stark | Separat action-selection-lager är motiverat. | Nengo BasalGanglia | Implementerad | R10,R1 |
| BG-02 | Avian BG-output och variabilitet moduleras av dopamin. | B · stark | BG får i framtiden ha neuromodulatorisk regime-control/plasticitet. | ej explicit dopaminlager | Lucka | R12 |
| EXP-01 | Striatalt dopamin kan i modeller ändra explore/exploit-balans. | C · hypotes/modell | EXPLORE bör kunna vara dynamiskt reglerad, inte fast slump. | factorized EXPLORE | Delvis | R11 |
| RL-01 | VTA-dopaminneuroner i sångfågel kodar performance-error-liknande signaler. | B · stark | Skilj outcome evaluation från momentant action value. | learning utanför BG-kärnan | Lucka/delvis | R13,R14 |
| THR-01 | Arcopallium/PoA-subregioner deltar i avian fear behavior. | A (vaktel) · stark | Hot ska kunna prioritera escape/avoidance. | SAFETY/MOTION -> FLEE; threat release | Delvis | R17 |
| SOC-01 | Mesotocin/vasotocin-system modulerar gregariousness/socialitet i fåglar. | B · stark | Social motivation ska vara särskilt tillstånd, inte bara objektattraktion. | SOCIAL + PERSON | Grov implementation | R15 |
| SOC-02 | TnA aktiveras av naturalistisk conspecific stimulus i naiva kycklingar. | A · stark | Social perception kan ha medfödd bias. | PERSON / SOCIAL | Delvis | R16 |
| MEM-01 | Avian hippocampus är central för spatialt minne och orientering. | B · stark | Lägg separat spatial kontext/minne före action valuation. | ingen tydlig neural hippocampusmodul | Lucka | R7 |
| SLP-01 | Avian sleep är homeostatisk och lokal brain-use kan påverka SWA. | B · stark | REST bör påverka återhämtning och på sikt plasticitet/minne. | REST | Delvis | R8,R9 |
| MAN-01 | Komplex object/tool-use hos vissa fåglar involverar exekutiva palliala system inklusive NCL. | B · måttlig | MANIPULATE bör bero på affordance + mål + erfarenhet. | factorized MANIPULATE | Delvis | R18 |
| COM-01 | Mål kan upprätthållas med persistent avian exekutiv aktivitet. | B · stark för persistens; D för implementation | Diskret beslutsloop behöver stabilitet/hysteresis. | TemporalCommitment FREE/LATCHED/HOLD | Implementation, ej anatomi | R2 |
| COM-02 | Exakta hold-tider/switch-margin saknar direkt biologisk förankring. | D | Får endast tunas som dynamikparameter. | 0.080 margin; action-specifika durations | Projektval | — |
| CARE-01 | Separat CARE-kanal är inte förankrad av denna litteraturöversikt. | D | Ingen stark neurobiologisk etikett ännu. | CARE | Forskningslucka | — |

## 18. Regler för framtida arkitekturändringar

1. En ny neural mekanism ska ha minst ett claim-ID i spårbarhetsmatrisen eller uttryckligen märkas som D-nivå-experiment.
1. Direkt chicken/galliform-evidens ska prioriteras över mammal analogi när de motsäger varandra.
1. Mammal/avian funktionell analogi får inte beskrivas som en-to-en-homologi om litteraturen själv varnar för detta.
1. Testfixturer får inte styra biologiska vikter bakvägen. Om ett scenario misslyckas ska representation och approximation lokaliseras innan policyformeln ändras.
1. Neurala runtime-parametrar (neuronantal, radius, eval points, synapser, seeds, solverinställningar) dokumenteras som implementation, inte biologi.
1. Behavioral acceptance och biological plausibility är två skilda kvalitetskriterier. En version kan klara alla tester men ändå sakna biologisk täckning, och omvänt.
1. Stora nya system – hippocampus, dopamin/plasticitet, social identitet, reproduction – ska införas som separata experimentgrenar med kontrollerad jämförelse.

## 19. Prioriterad forsknings- och utvecklingsroadmap

| Prioritet | Spår | Varför |
|---|---|---|
| P1 | Verifiera v0.2.6 EXPLORE-representation | Nuvarande blockerare är teknisk/neural robusthet, inte en ny biologisk teori. |
| P2 | Spatial hippocampus-/contextmodul | Stort biologiskt område som i princip saknas i NeuralBrain idag. |
| P3 | Outcome learning + dopaminmodulerad plasticitet | Gör BirdAI adaptiv i stället för enbart handkodad utility-policy. |
| P4 | Rikare social representation | Conspecific identity, familiarity, dominance, affiliation och flockkontext. |
| P5 | Sleep/rest som verklig återhämtningsprocess | Koppla aktivitet, rest drive, fysiologi och senare konsolidering. |
| P6 | Threat-system med flera delsignaler | Skilj detection, risk assessment, freeze/avoid/escape i stället för en enda SAFETY. |
| P7 | Reproduktion/genetik | Först när basbeteende och socialt system är stabila; Proto kan då bli relevant. |

## 20. Aktuell projektstatus och avgränsning

Denna referensram är skriven mot BirdAI v0.5.6 / NeuralBrain v0.2.6 – EXPLORE physical-domain eval-point candidate. Den versionen behåller v0.2.5:s policy, BG100 utan extra bias/gain, temporal commitment och MANIPULATE-faktorisering. Den funktionella v0.2.6-ändringen är scale_eval_points=False på fyra EXPLORE-function-decoders samt diagnostiska probes. Windows/Nengo-runtime är fortfarande den auktoritativa acceptansen för kandidaten.

Skyddade Godot-filer och beteendeloopen ska inte ändras för att “matcha forskningen” utan ett separat designbeslut. Dokumentet cementerar principerna och gör framtida avsteg synliga; det ersätter inte regressionstestning.

## 21. Referenser

- **[R1]** Reiner, A., Perkel, D. J., Bruce, L. L., et al. (2004). Revised nomenclature for avian telencephalon and some related brainstem nuclei. Journal of Comparative Neurology, 473(3), 377–414. DOI: 10.1002/cne.20118. PMID: 15116397.
- **[R2]** Güntürkün, O. (2005). Avian and mammalian “prefrontal cortices”: limited degrees of freedom in the evolution of the neural mechanisms of goal-state maintenance. Brain Research Bulletin, 66(4–6), 311–316. DOI: 10.1016/j.brainresbull.2005.02.004. PMID: 16144607.
- **[R3]** Steinemer, A., Simon, A., Güntürkün, O., & Rook, N. (2024). Parallel executive pallio-motor loops in the pigeon brain. Journal of Comparative Neurology, 532(4), e25611. DOI: 10.1002/cne.25611. PMID: 38625816.
- **[R4]** Clark, W. J., & Colombo, M. (2020). The functional architecture, receptive field characteristics, and representation of objects in the visual network of the pigeon brain. Progress in Neurobiology, 195, 101781. DOI: 10.1016/j.pneurobio.2020.101781. PMID: 32097689.
- **[R5]** Saneyasu, T. (2024). Recent Research on Mechanisms of Feeding Regulation in Chicks. Journal of Poultry Science, 61, 2024012. DOI: 10.2141/jpsa.2024012. PMID: 38681189.
- **[R6]** Snapir, N., Robinzon, B., & Godschalk, M. (1976). The drinking response of the chicken to peripheral and central administration of angiotensin II. Pharmacology Biochemistry and Behavior, 5(1), 5–10. DOI: 10.1016/0091-3057(76)90279-3. PMID: 996041.
- **[R7]** Mayer, U., Watanabe, S., & Bischof, H.-J. (2013). Spatial memory and the avian hippocampus: research in zebra finches. Journal of Physiology – Paris, 107(1–2), 2–12. DOI: 10.1016/j.jphysparis.2012.05.002. PMID: 22613455.
- **[R8]** Lesku, J. A., Vyssotski, A. L., Martinez-Gonzalez, D., Wilzeck, C., & Rattenborg, N. C. (2011). Local sleep homeostasis in the avian brain: convergence of sleep function in mammals and birds? Proceedings of the Royal Society B, 278(1717), 2419–2428. DOI: 10.1098/rspb.2010.2316. PMID: 21208955.
- **[R9]** Beckers, G. J. L., & Rattenborg, N. C. (2015). An in depth view of avian sleep. Neuroscience & Biobehavioral Reviews, 50, 120–127. DOI: 10.1016/j.neubiorev.2014.07.019. PMID: 25107492.
- **[R10]** Frost-Nylén, J., Thompson, W. S., Robertson, B., & Grillner, S. (2024). The Basal Ganglia Downstream Control of Action – An Evolutionarily Conserved Strategy. Current Neuropharmacology, 22(9), 1419–1430. DOI: 10.2174/1570159X21666230810141746. PMID: 37563813.
- **[R11]** Humphries, M. D., Khamassi, M., & Gurney, K. (2012). Dopaminergic control of the exploration–exploitation trade-off via the basal ganglia. Frontiers in Neuroscience, 6, 9. DOI: 10.3389/fnins.2012.00009. PMID: 22347155.
- **[R12]** Budzillo, A., Duffy, A., Miller, K. E., Fairhall, A. L., & Perkel, D. J. (2017). Dopaminergic modulation of basal ganglia output through coupled excitation–inhibition. Proceedings of the National Academy of Sciences, 114(22), 5713–5718. DOI: 10.1073/pnas.1611146114. PMID: 28507134.
- **[R13]** Gadagkar, V., Puzerey, P. A., Chen, R., Baird-Daniel, E., Farhang, A. R., & Goldberg, J. H. (2016). Dopamine neurons encode performance error in singing birds. Science, 354(6317), 1278–1282. DOI: 10.1126/science.aah6837. PMID: 27940871.
- **[R14]** Fee, M. S., & Goldberg, J. H. (2011). A hypothesis for basal ganglia-dependent reinforcement learning in the songbird. Neuroscience, 198, 152–170. DOI: 10.1016/j.neuroscience.2011.09.069. PMID: 22015923.
- **[R15]** Goodson, J. L., Kelly, A. M., & Kingsbury, M. A. (2012). Evolving nonapeptide mechanisms of gregariousness and social diversity in birds. Hormones and Behavior, 61(3), 239–250. DOI: 10.1016/j.yhbeh.2012.01.005. PMID: 22269661.
- **[R16]** Mayer, U., Rosa-Salva, O., Loveland, J. L., & Vallortigara, G. (2019). Selective response of the nucleus taeniae of the amygdala to a naturalistic social stimulus in visually naive domestic chicks. Scientific Reports, 9, 9849. DOI: 10.1038/s41598-019-46322-5. PMID: 31285532.
- **[R17]** Saint-Dizier, H., Constantin, P., Davies, D. C., Leterrier, C., Lévy, F., & Richard, S. (2009). Subdivisions of the arcopallium/posterior pallial amygdala complex are differentially involved in the control of fear behaviour in the Japanese quail. Brain Research Bulletin. DOI: 10.1016/j.brainresbull.2009.03.004. PMID: 19480989.
- **[R18]** Striedter, G. F. (2013). Bird brains and tool use: beyond instrumental conditioning. Brain, Behavior and Evolution, 82(1), 55–67. DOI: 10.1159/000352003. PMID: 23979456.
