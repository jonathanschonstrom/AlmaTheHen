from neural_model_extinction import ALL_INPUT_KEYS, NeuralBrain

brain = NeuralBrain(seed=20260910)
try:
    assert len(ALL_INPUT_KEYS) == 18
    assert brain.input_values.shape[0] == 18
    assert brain.estimated_neuron_count == 12930, brain.estimated_neuron_count

    world_time = 10.0

    def manipulate_value(encoded_memory: float) -> float:
        nonlocal_world = None
        # Wash out the previous cognitive pattern at the signed-neutral point.
        # We inspect pre-BG action evidence only; the known v0.2.6 BG readout
        # instability is intentionally outside this experiment's acceptance gate.
        global world_time
        brain.reset_temporal_state()
        brain.step({"learned_food_access": 0.5}, 0.20, world_time=world_time)
        world_time += 0.40
        brain.reset_temporal_state()
        decision = brain.step({
            "hunger": 0.95,
            "explore": 0.40,
            "manipulable": 1.0,
            "learned_food_access": encoded_memory,
        }, 0.40, world_time=world_time)
        world_time += 0.60
        return float(decision.action_values["MANIPULATE"])

    neutral = manipulate_value(0.5)
    positive = manipulate_value(0.9)
    extinguished = manipulate_value(0.1)

    assert positive > neutral + 0.30, (positive, neutral, extinguished)
    assert extinguished < neutral - 0.30, (positive, neutral, extinguished)
    assert positive > extinguished + 0.80, (positive, neutral, extinguished)
finally:
    brain.close()

print(
    "PASS learned-extinction Nengo signed dynamics",
    {"positive": positive, "neutral": neutral, "extinguished": extinguished, "neurons": 12930},
)
