from neural_model_feasibility import (
    ACTIONS,
    ALL_INPUT_KEYS,
    INPUT_KEYS,
    NEUTRAL_LEARNED_FOOD,
    POSITIVE_FOOD_THRESHOLD,
    EXPERIMENT_THRESHOLD,
    affordance_vector,
    manipulation_feasibility_from_mapping,
    valuation,
    vector_from_mapping,
)
import neural_model as base


def live_state(**kw):
    values = {key: 0.0 for key in ALL_INPUT_KEYS}
    values["learned_food_access"] = NEUTRAL_LEARNED_FOOD
    values.update(kw)
    return values


mi = ACTIONS.index("MANIPULATE")

# Exact liveness bug: a strong historical manipulable cue with no positive
# learned target and no executable experiment must not enter the old generic
# MANIPULATE pathway.
no_target_state = live_state(
    hunger=0.68,
    explore=0.98,
    novelty=0.02,
    manipulable=0.93,
    learned_food_access=0.5,
    substrate_affordance=0.0,
)
no_target_vector = vector_from_mapping(no_target_state)
assert manipulation_feasibility_from_mapping(no_target_state) == 0.0
assert no_target_vector[base.MANIPULABLE] == 0.0
assert affordance_vector(no_target_vector)[mi] == 0.0
no_target_values = valuation(no_target_vector)
assert no_target_values[mi] < no_target_values[ACTIONS.index("EXPLORE")], no_target_values

# A learned positive target remains executable and re-opens the old generic
# affordance proportionally while the signed learned decoder supplies its own
# hunger-dependent value.
positive_state = live_state(
    hunger=0.95,
    explore=0.40,
    manipulable=1.0,
    learned_food_access=0.9,
)
positive_vector = vector_from_mapping(positive_state)
assert manipulation_feasibility_from_mapping(positive_state) > 0.75
assert positive_vector[base.MANIPULABLE] > 0.75
assert affordance_vector(positive_vector)[mi] > 0.75
assert valuation(positive_vector)[mi] > no_target_values[mi] + 0.50

# A genuine experiment opportunity also makes MANIPULATE executable. The wire
# name substrate_affordance is retained for compatibility but now represents
# experiment evidence for substrate OR classic manipulation targets.
experiment_state = live_state(
    hunger=0.75,
    explore=0.55,
    novelty=0.25,
    manipulable=0.9,
    learned_food_access=0.5,
    substrate_affordance=0.6,
)
experiment_vector = vector_from_mapping(experiment_state)
assert abs(manipulation_feasibility_from_mapping(experiment_state) - 0.6) < 1e-12
assert abs(experiment_vector[base.MANIPULABLE] - 0.54) < 1e-12
assert abs(affordance_vector(experiment_vector)[mi] - 0.6) < 1e-12
assert valuation(experiment_vector)[mi] > no_target_values[mi] + 0.20

# Extinction remains inhibitory and never becomes executable just because a
# generic manipulable object is still perceptually present.
extinguished_state = live_state(
    hunger=0.95,
    explore=0.80,
    manipulable=1.0,
    learned_food_access=0.1,
)
extinguished_vector = vector_from_mapping(extinguished_state)
assert manipulation_feasibility_from_mapping(extinguished_state) == 0.0
assert extinguished_vector[base.MANIPULABLE] == 0.0
assert affordance_vector(extinguished_vector)[mi] == 0.0
assert valuation(extinguished_vector)[mi] <= no_target_values[mi]

# Resolver/Python threshold boundary is strict on both channels.
assert manipulation_feasibility_from_mapping({"learned_food_access": 0.5 + POSITIVE_FOOD_THRESHOLD / 2.0}) == 0.0
assert manipulation_feasibility_from_mapping({"substrate_affordance": EXPERIMENT_THRESHOLD}) == 0.0

# Historical 16D mapping callers remain untouched by the v5 gate.
legacy_mapping = {key: 0.0 for key in INPUT_KEYS}
legacy_mapping["manipulable"] = 0.73
legacy_vector = vector_from_mapping(legacy_mapping)
assert abs(legacy_vector[base.MANIPULABLE] - 0.73) < 1e-12

print("PASS manipulate-feasibility analytical regressions")
