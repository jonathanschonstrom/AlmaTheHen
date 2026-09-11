from neural_model_extinction import (
    ACTIONS, ALL_INPUT_KEYS, INPUT_KEYS, NEUTRAL_LEARNED_FOOD,
    affordance_vector, valuation, vector_from_mapping,
)
import neural_model as base


def state(**kw):
    values = {key: 0.0 for key in ALL_INPUT_KEYS}
    values["learned_food_access"] = NEUTRAL_LEARNED_FOOD
    values.update(kw)
    return values


assert len(INPUT_KEYS) == 16
assert len(ALL_INPUT_KEYS) == 18
assert NEUTRAL_LEARNED_FOOD == 0.5

neutral_vector = vector_from_mapping({"hunger": 0.8})
assert abs(neutral_vector[base.LEARNED_FOOD_ACCESS] - 0.5) < 1e-12

mi = ACTIONS.index("MANIPULATE")
neutral = valuation(vector_from_mapping(state(hunger=1.0, explore=0.8, manipulable=1.0, learned_food_access=0.5)))
positive = valuation(vector_from_mapping(state(hunger=1.0, explore=0.8, manipulable=1.0, learned_food_access=0.8)))
extinguished = valuation(vector_from_mapping(state(hunger=1.0, explore=0.8, manipulable=1.0, learned_food_access=0.2)))
assert positive[mi] > neutral[mi] + 0.45, (positive[mi], neutral[mi])
assert extinguished[mi] < neutral[mi] - 0.20, (extinguished[mi], neutral[mi])

# The learned signal is revalued by current hunger inside NeuralBrain; when sated,
# positive and negative memories must not change MANIPULATE evidence.
sated_neutral = valuation(vector_from_mapping(state(hunger=0.0, explore=0.4, manipulable=0.3, learned_food_access=0.5)))
sated_positive = valuation(vector_from_mapping(state(hunger=0.0, explore=0.4, manipulable=0.3, learned_food_access=0.9)))
sated_negative = valuation(vector_from_mapping(state(hunger=0.0, explore=0.4, manipulable=0.3, learned_food_access=0.1)))
assert abs(sated_positive[mi] - sated_neutral[mi]) < 1e-12
assert abs(sated_negative[mi] - sated_neutral[mi]) < 1e-12

# Historical 16D callers remain exactly neutral for the new signed channel.
old16 = [0.31, 0.22, 0.17, 0.52, 0.43, 0.08, 0.19, 0.0, 0.0, 0.2, 0.4, 0.3, 0.5, 0.6, 0.1, 0.7]
legacy = valuation(old16)
explicit_neutral = valuation(old16 + [0.5, 0.0])
assert all(abs(a - b) < 1e-12 for a, b in zip(legacy, explicit_neutral))

# Neutral/negative memory is not an affordance gate by itself. Only the positive
# half of the centred signal can advertise a learned opportunity.
neutral_gate = affordance_vector(vector_from_mapping(state(learned_food_access=0.5)))[mi]
negative_gate = affordance_vector(vector_from_mapping(state(learned_food_access=0.1)))[mi]
positive_gate = affordance_vector(vector_from_mapping(state(learned_food_access=0.8)))[mi]
assert neutral_gate == 0.0
assert negative_gate == 0.0
assert positive_gate >= 0.59

# Signed cognitive memory still affects MANIPULATE only.
a = valuation(vector_from_mapping(state(hunger=0.8, thirst=0.3, rest=0.2, explore=0.5, social=0.4,
    comfort=0.2, novelty=0.3, open_space=0.5, learned_food_access=0.5)))
b = valuation(vector_from_mapping(state(hunger=0.8, thirst=0.3, rest=0.2, explore=0.5, social=0.4,
    comfort=0.2, novelty=0.3, open_space=0.5, learned_food_access=0.9)))
for i, name in enumerate(ACTIONS):
    if name != "MANIPULATE":
        assert abs(a[i] - b[i]) < 1e-12, (name, a[i], b[i])

print("PASS learned-extinction analytical regressions")
