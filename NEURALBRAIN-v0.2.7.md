# NeuralBrain v0.2.7 — BG Readout Stability

Experimentkandidat, 2026-09-11.

Den enda neurala funktionsändringen relativt v0.2.6 är hur den redan 10 ms lågpassfiltrerade utgången från `nengo.networks.BasalGanglia` avläses. v0.2.6 använde den sista enskilda simulatorpunkten. v0.2.7 använder medelvärdet av de sista 30 ms från samma probe.

Detta ändrar inte:

- analytisk policy eller vikter
- interoception/exteroception
- EXPLORE- eller MANIPULATE-decoders
- competition-evidence eller hysteresisprojektion
- BG100:s antal neuroner
- `input_bias=0.0`
- någon BG gain
- temporal commitment
- Neural Control-auktoriteten i Godot

## Varför

En ren Windows-installation av v0.5.7/v0.2.6 den 11 september 2026 gav 55/63 i den kanoniska tre-seed-sviten. I `mixed_manipulate` och `familiar_room` var analytisk vinnare, neural valuation och competition vinnare överens, medan den sista BG-samplen valde annan kanal. Det isolerar dessa missar till BG-readout efter competition. `commitment_expires` missade också i samtliga tre seeds och måste verifieras i den nya runtimekörningen; inga krav har lättats.

30 ms är ett tidsfönster över spikande motorselektionsutgång, inte en utility-fallback. Både den momentana sista BG-samplen och den integrerade BG-utgången loggas i v0.2.7.

Kandidaten är inte godkänd förrän Windows/Nengo-självtest och helst 10-seed-robustheten har körts.
