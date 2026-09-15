from neural_model import NeuralBrain, INPUT_KEYS, ALL_INPUT_KEYS
assert len(INPUT_KEYS) == 16
assert len(ALL_INPUT_KEYS) == 18
brain = NeuralBrain(seed=20260910)
try:
    assert brain.estimated_neuron_count > 11890
    print("PASS Nengo learned-affordance graph builds", brain.estimated_neuron_count)
finally:
    brain.close()
