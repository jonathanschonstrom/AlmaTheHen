from neural_model import (
    INPUT_KEYS, COGNITIVE_INPUT_KEYS, ALL_INPUT_KEYS, ACTIONS,
    valuation, vector_from_mapping, affordance_vector,
    LEARNED_FOOD_ACCESS, SUBSTRATE_AFFORDANCE,
)

BASE_KEYS = (
    "hunger", "thirst", "rest", "explore", "social", "safety", "comfort",
    "food", "water", "person", "rest_site", "care_site", "novelty",
    "manipulable", "motion", "open_space",
)

def state(**kw):
    x = {k: 0.0 for k in ALL_INPUT_KEYS}
    x.update(kw)
    return x

assert tuple(INPUT_KEYS) == BASE_KEYS
assert COGNITIVE_INPUT_KEYS == ("learned_food_access", "substrate_affordance")
assert len(INPUT_KEYS) == 16
assert len(ALL_INPUT_KEYS) == 18
assert ALL_INPUT_KEYS[LEARNED_FOOD_ACCESS] == "learned_food_access"
assert ALL_INPUT_KEYS[SUBSTRATE_AFFORDANCE] == "substrate_affordance"
assert len(vector_from_mapping(state())) == 18

mi = ACTIONS.index("MANIPULATE")
neutral = valuation(vector_from_mapping(state(hunger=1.0, explore=0.4, manipulable=0.2)))
learned = valuation(vector_from_mapping(state(hunger=1.0, explore=0.4, manipulable=0.2, learned_food_access=0.40)))
sated = valuation(vector_from_mapping(state(hunger=0.0, explore=0.4, manipulable=0.2, learned_food_access=0.40)))
sated_reference = valuation(vector_from_mapping(state(hunger=0.0, explore=0.4, manipulable=0.2)))
substrate = valuation(vector_from_mapping(state(hunger=1.0, substrate_affordance=0.80)))
substrate_sated = valuation(vector_from_mapping(state(hunger=0.0, substrate_affordance=0.80)))
assert learned[mi] > neutral[mi] + 0.60
assert abs(sated[mi] - sated_reference[mi]) < 1e-12
assert substrate[mi] > substrate_sated[mi] + 0.70

# Historical 16D callers remain valid and are exactly equivalent to explicit zero
# cognitive predictions.
old16 = [0.31, 0.22, 0.17, 0.52, 0.43, 0.08, 0.19, 0.0, 0.0, 0.2, 0.4, 0.3, 0.5, 0.6, 0.1, 0.7]
assert all(abs(a-b) < 1e-12 for a,b in zip(valuation(old16), valuation(old16 + [0.0, 0.0])))

# Cognitive inputs affect MANIPULATE only.
a = valuation(vector_from_mapping(state(hunger=0.8, thirst=0.3, rest=0.2, explore=0.5, social=0.4,
    comfort=0.2, novelty=0.3, open_space=0.5)))
b = valuation(vector_from_mapping(state(hunger=0.8, thirst=0.3, rest=0.2, explore=0.5, social=0.4,
    comfort=0.2, novelty=0.3, open_space=0.5, learned_food_access=0.7, substrate_affordance=0.6)))
for i, name in enumerate(ACTIONS):
    if name != "MANIPULATE":
        assert abs(a[i] - b[i]) < 1e-12, (name, a[i], b[i])

assert affordance_vector(vector_from_mapping(state(learned_food_access=0.35)))[mi] >= 0.35
assert affordance_vector(vector_from_mapping(state(substrate_affordance=0.55)))[mi] >= 0.55
print("PASS learned-affordance analytical regressions")
