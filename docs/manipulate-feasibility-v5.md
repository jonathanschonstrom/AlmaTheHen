# MANIPULATE feasibility v5

## Problem observed in the v4 live run

Learned-extinction v4 fixed the previous manipulation perseveration, but the live closed loop exposed a separate liveness failure.

For roughly 937 simulated seconds Alma remained at the same position while NeuralBrain continued updating. During the stall the characteristic state was approximately:

- generic `manipulable ~= 0.93`
- `learned_food_access = 0.5` (signed-neutral)
- `substrate_affordance = 0.0`
- MANIPULATE won analytical/spiking competition and BG selection
- the resolver had no positive learned target and no remaining experiment target, therefore `resolve_manipulation()` returned `{}`
- the Godot agent remained idle

A later environmental perturbation (the human becoming visible) altered competition enough for another executable family to win and movement resumed.

This is a controller-contract mismatch, not an extinction failure: the historical generic manipulable cue could advertise MANIPULATE even after the target/action resolver had no executable manipulation.

## v5 hypothesis

A family-level action should only compete when the current perceptual/cognitive state contains an executable opportunity for that family.

For MANIPULATE, v5 defines feasibility from the two existing cognitive channels without adding another transport dimension or neuron population:

1. positive learned target/action/context consequence (`learned_food_access` above signed neutral), or
2. a still-relevant experiment opportunity (`substrate_affordance`; the legacy wire name is retained, but the v5 live semantics are resolver `experiment_evidence` for substrate or classic manipulable targets).

Negative/extinguished learned evidence remains a separate signed inhibitory contribution. It does not make an action executable.

## Implementation

- Transport remains 18D.
- Nengo topology remains 12,930 neurons.
- `neural_action_resolver.gd` transports its current `experiment_evidence` for the selected experiment focus, including classic objects as well as loose substrate.
- `neural_model_feasibility.py` gates only the historical generic `manipulable` transport value in live 18D mode.
- The temporal MANIPULATE affordance gate uses the same feasibility signal, so a stale MANIPULATE commitment is released when no executable opportunity remains.
- Historical 16D callers retain the pre-v5 policy/affordance semantics exactly.
- No `MANIPULATE -> EXPLORE` fallback was added. A non-executable family is prevented from winning rather than being silently translated into another behaviour.
- The server logs `manipulation_feasibility` explicitly for closed-loop diagnosis.

Resolver/Python thresholds are aligned with a small numerical tolerance so an exactly encoded boundary cannot be treated as executable on one side but non-executable on the other.

## Windows CI evidence

Run `34638394658` on SHA `5133577904005d516ed6687197ffdaa7131829a9` passed:

- Neural-Control static contracts
- learned-affordance static contracts
- learned-extinction static contracts
- MANIPULATE-feasibility static contracts
- all 28 v0.2.6 pure regressions
- learned-affordance analytical regressions
- learned-extinction analytical regressions
- MANIPULATE-feasibility analytical regressions
- 12,930-neuron learned-affordance Nengo build
- signed-extinction Nengo dynamics
- MANIPULATE-feasibility Nengo dynamics

### Spiking MANIPULATE values

With the same Nengo seed and no BG acceptance requirement:

- reproduced no-target/deadlock state: MANIPULATE `0.1211342269`, EXPLORE `0.5969704500`
- positive learned opportunity: MANIPULATE `1.2662462453`
- executable experiment opportunity: MANIPULATE `0.6861130370`
- extinguished/non-executable opportunity: MANIPULATE `-0.7720872421`

Thus the specific no-target state no longer makes MANIPULATE the competition winner, while positive learned and novel experiment opportunities remain strongly expressible.

The v4 signed-extinction regression remains unchanged:

- positive `1.3140488558`
- neutral `0.4023360516`
- extinguished `-0.5649317190`

## Isolation

This experiment is stacked on learned-extinction v4 and does not include the separate BG-readout v0.2.7 candidate. Known v0.2.6 BG readout instability therefore remains out of scope and must still be measured separately.

## Live acceptance gate

Do not merge until a Godot closed-loop run verifies:

1. neural actuator authority remains intact and utility never falls back;
2. there is no prolonged `selected=MANIPULATE` + `manipulation_feasibility=0` + idle/fixed-position stall;
3. positive lit-button memory remains usable under hunger;
4. genuinely untested classic objects and loose substrate can still receive a finite experiment window;
5. extinguished targets remain inhibited and do not re-enter long perseveration;
6. MANIPULATE competition/selection and resolver actuation can be audited separately from BG divergence.
