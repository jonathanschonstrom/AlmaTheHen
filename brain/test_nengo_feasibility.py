from neural_model_feasibility import ACTIONS, ALL_INPUT_KEYS, NeuralBrain

brain = NeuralBrain(seed=20260910)
try:
    assert len(ALL_INPUT_KEYS) == 18
    assert brain.estimated_neuron_count == 12930, brain.estimated_neuron_count
    mi = ACTIONS.index("MANIPULATE")
    ei = ACTIONS.index("EXPLORE")
    world_time = 20.0

    def step_state(values, seconds=0.40):
        global world_time
        brain.reset_temporal_state()
        # Wash previous cognitive evidence to neutral/no-opportunity.
        brain.step({
            "learned_food_access": 0.5,
            "substrate_affordance": 0.0,
        }, 0.20, world_time=world_time)
        world_time += 0.40
        brain.reset_temporal_state()
        decision = brain.step(values, seconds, world_time=world_time)
        world_time += seconds + 0.20
        return decision

    # Reproduce the live deadlock signature: high generic manipulable cue, neutral
    # learned evidence and zero executable experiment opportunity. Competition
    # itself must now prefer another family; BG readout is tested separately.
    deadlock = step_state({
        "hunger": 0.68,
        "explore": 0.98,
        "novelty": 0.02,
        "open_space": 0.25,
        "manipulable": 0.93,
        "learned_food_access": 0.5,
        "substrate_affordance": 0.0,
    })
    deadlock_manip = float(deadlock.action_values["MANIPULATE"])
    deadlock_explore = float(deadlock.action_values["EXPLORE"])
    assert float(deadlock.affordance_gates["MANIPULATE"]) < 0.01, deadlock.affordance_gates
    assert deadlock_manip < deadlock_explore - 0.10, (deadlock_manip, deadlock_explore)
    assert max(deadlock.competition_values, key=deadlock.competition_values.get) != "MANIPULATE", deadlock.competition_values

    positive = step_state({
        "hunger": 0.95,
        "explore": 0.40,
        "manipulable": 1.0,
        "learned_food_access": 0.9,
        "substrate_affordance": 0.0,
    })
    experiment = step_state({
        "hunger": 0.75,
        "explore": 0.55,
        "novelty": 0.25,
        "manipulable": 0.9,
        "learned_food_access": 0.5,
        "substrate_affordance": 0.6,
    })
    extinguished = step_state({
        "hunger": 0.95,
        "explore": 0.80,
        "manipulable": 1.0,
        "learned_food_access": 0.1,
        "substrate_affordance": 0.0,
    })

    positive_manip = float(positive.action_values["MANIPULATE"])
    experiment_manip = float(experiment.action_values["MANIPULATE"])
    extinguished_manip = float(extinguished.action_values["MANIPULATE"])

    assert float(positive.affordance_gates["MANIPULATE"]) > 0.70, positive.affordance_gates
    assert float(experiment.affordance_gates["MANIPULATE"]) > 0.50, experiment.affordance_gates
    assert float(extinguished.affordance_gates["MANIPULATE"]) < 0.01, extinguished.affordance_gates
    assert positive_manip > deadlock_manip + 0.50, (positive_manip, deadlock_manip)
    assert experiment_manip > deadlock_manip + 0.20, (experiment_manip, deadlock_manip)
    assert extinguished_manip < deadlock_manip - 0.20, (extinguished_manip, deadlock_manip)
finally:
    brain.close()

print("PASS Nengo MANIPULATE feasibility dynamics", {
    "deadlock_manip": deadlock_manip,
    "deadlock_explore": deadlock_explore,
    "positive_manip": positive_manip,
    "experiment_manip": experiment_manip,
    "extinguished_manip": extinguished_manip,
    "neurons": 12930,
})
