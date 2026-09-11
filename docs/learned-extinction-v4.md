# Learned extinction v4 — experiment gate

This stacked experiment starts from `experiment/learned-affordance-v3`. It does not include the separate BG-readout experiment.

## Why this iteration exists

The long learned-affordance live run proved that the new causal path worked, but also exposed perseveration:

- 8,629 total decisions; MANIPULATE dominated the run.
- `o5:peck@lamp_lit`: 80 successful experiences with `food_access = 0.6`.
- `o5:peck@lamp_dark`: 1,758 failed experiences.
- `o13:scratch`: 1,720 experiences; the forage stock was exhausted and the learned `food_access` effect had fallen to 0.
- Neutral/repeated objects were still manipulated far beyond useful information gain.

The failure was architectural: v3 transported only an unsigned positive learned-food bonus and the resolver always found some manipulable target. Learned absence could therefore remove a bonus, but could not inhibit repetition.

## v4 hypothesis

Keep the existing 18D transport and the same 12,930-neuron topology, but reinterpret `learned_food_access` as a centred signed prediction:

- `0.5` = neutral / unknown
- `> 0.5` = positive predicted future food access
- `< 0.5` = extinction / negative evidence

Godot constructs target/action/context-specific prediction evidence without consulting current drives. NeuralBrain converts the centred prediction to signed evidence and revalues it with current hunger. Negative evidence can therefore reduce MANIPULATE instead of merely removing a positive bonus.

Physical actionability, epistemic uncertainty and learned consequence remain separate inside the resolver. Repeated neutral interactions reduce uncertainty. The old nearest-object fallback is removed: an extinguished target supplies inhibitory neural evidence but is not executed again merely because MANIPULATE was selected.

## Compatibility gate

Before live acceptance:

1. existing Neural-Control static contracts remain green;
2. existing learned-affordance tests remain green;
3. all v0.2.6 pure regressions remain green when the cognitive path is neutral;
4. explicit 16D callers map to signed-neutral `0.5` and preserve the historical policy;
5. the v4 Nengo graph still builds at 12,930 neurons.

## Best live test

Continue the existing learned-affordance save rather than resetting the individual. It already contains strong positive and negative context-specific evidence.

Expected qualitative behavior:

- when the button is lit and hunger makes food access valuable, the positive `lamp_lit` model may still drive `MANIPULATE -> peck`;
- once the lamp is dark, the dark-context extinction trace should drive `learned_food_access < 0.5` and repeated dark pecking should collapse rather than continue hundreds of times;
- exhausted `o13` should no longer sustain repeated scratch once its uncertainty is low and its learned food-access prediction is extinguished;
- genuinely untried loose substrate can still receive a finite epistemic experiment window;
- no `body.needs` lookup or `if hungry -> target` rule is allowed in the resolver.

## Live acceptance metrics

Compare against the v3 run, not against zero behavior.

- Dark-button pecks should fall by at least an order of magnitude over an equivalent observation window; no hundreds/thousands-long perseverative sequence.
- Scratch on an already exhausted `o13` should likewise fall by at least an order of magnitude.
- A lit button with the learned positive model must remain usable; extinction must be context-specific, not global avoidance of the button.
- MANIPULATE should no longer occupy roughly three quarters of decisions solely because exhausted affordances remain visible.
- Neural actuator authority must remain `neural` with no utility fallback.
- BG-vs-competition disagreement is logged separately because this branch intentionally retains the known v0.2.6 BG-readout defect.

Do not merge from this experiment until those live properties are demonstrated.
