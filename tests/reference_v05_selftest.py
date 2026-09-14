"""Standalone Windows/runtime test for BirdAI NeuralBrain v0.2.
Frozen from the verified portable package.
Original full-file SHA-256: cf4a2b31923056e619c15be683a8be8d2bdd28fbe100efd263941a81c261edd9
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from neural_model import ACTIONS, NeuralBrain, affordance_vector, valuation, vector_from_mapping

SCENARIOS = [
    ("danger", {"safety": 0.95, "motion": 0.8}, "FLEE"),
    ("thirst", {"thirst": 0.92, "water": 1.0, "explore": 0.2}, "DRINK"),
    ("hunger", {"hunger": 0.92, "food": 1.0, "explore": 0.2}, "EAT"),
    ("rest", {"rest": 0.92, "rest_site": 1.0, "explore": 0.15}, "REST"),
    ("social", {"social": 0.92, "person": 1.0, "explore": 0.15}, "SOCIAL"),
    ("care", {"comfort": 0.92, "care_site": 1.0, "explore": 0.15}, "CARE"),
    ("novel_world", {"explore": 0.90, "novelty": 0.85, "open_space": 0.8}, "EXPLORE"),
    ("hungry_search", {"hunger": 0.95, "food": 0.0, "explore": 0.30, "novelty": 0.10, "open_space": 0.4}, "EXPLORE"),
    ("thirsty_search", {"thirst": 0.95, "water": 0.0, "explore": 0.30, "novelty": 0.10, "open_space": 0.4}, "EXPLORE"),
    ("novel_object", {"explore": 0.75, "novelty": 0.75, "manipulable": 1.0}, "MANIPULATE"),
    ("mixed_rest", {
        "rest": 0.15, "rest_site": 0.95, "explore": 0.48, "novelty": 0.03,
        "manipulable": 0.55, "food": 0.55, "hunger": 0.14, "social": 0.30,
    }, "REST"),
    ("mixed_manipulate", {
        "rest": 0.12, "rest_site": 0.25, "explore": 0.48, "novelty": 0.12,
        "manipulable": 0.92, "food": 0.35, "hunger": 0.14, "social": 0.25,
    }, "MANIPULATE"),
    ("mixed_eat", {
        "hunger": 0.26, "food": 0.92, "explore": 0.48, "novelty": 0.03,
        "manipulable": 0.85, "rest": 0.12, "rest_site": 0.45,
    }, "EAT"),
    ("mixed_drink", {
        "thirst": 0.30, "water": 0.90, "explore": 0.46, "novelty": 0.03,
        "manipulable": 0.75, "rest": 0.13, "rest_site": 0.50,
    }, "DRINK"),
    ("familiar_room", {
        "explore": 0.48, "novelty": 0.02, "open_space": 0.55,
        "manipulable": 0.20, "rest": 0.08, "rest_site": 0.10,
    }, "EXPLORE"),
]


def diagnostic_result(name: str, values: dict, expected: str, decision, analytical: np.ndarray) -> dict:
    neural_values = np.asarray([decision.action_values[action] for action in ACTIONS], dtype=float)
    competition_values = np.asarray([decision.competition_values[action] for action in ACTIONS], dtype=float)
    neural_argmax = int(neural_values.argmax())
    competition_argmax = int(competition_values.argmax())
    analytical_argmax = int(analytical.argmax())
    return {
        "scenario": name,
        "expected": expected,
        "selected": decision.selected,
        "ok": decision.selected == expected,
        "confidence": decision.confidence,
        "inputs": {key: float(value) for key, value in values.items()},
        "action_values": decision.action_values,
        "competition_values": decision.competition_values,
        "basal_ganglia_output": decision.basal_ganglia_output,
        "affordance_gates": decision.affordance_gates,
        "commitment": decision.commitment,
        "analytical_values": {action: float(analytical[i]) for i, action in enumerate(ACTIONS)},
        "analytical_pick": ACTIONS[analytical_argmax],
        "neural_value_pick": ACTIONS[neural_argmax],
        "competition_value_pick": ACTIONS[competition_argmax],
        "decoder_rmse": float(np.sqrt(np.mean((neural_values - analytical) ** 2))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/neural-selftest.json")
    args = parser.parse_args()

    brain = NeuralBrain(seed=20260910)
    results = []
    failures = []
    world_time = 10.0

    for name, values, expected in SCENARIOS:
        brain.reset_temporal_state()
        brain.step({}, 0.15, world_time=world_time)
        world_time += 0.25
        brain.reset_temporal_state()
        analytical = valuation(vector_from_mapping(values))
        decision = brain.step(values, 0.35, world_time=world_time)
        world_time += 0.50
        item = diagnostic_result(name, values, expected, decision, analytical)
        if not item["ok"]:
            failures.append(
                f"{name}: expected {expected}, BG got {decision.selected}; "
                f"neural-values={item['neural_value_pick']}, "
                f"competition={item['competition_value_pick']}, "
                f"analytical={item['analytical_pick']}"
            )
        results.append(item)

    brain.reset_temporal_state()
    brain.step({}, 0.15, world_time=100.0)
    brain.reset_temporal_state()
    rest_setup = {"rest": 0.28, "rest_site": 0.95, "explore": 0.15, "novelty": 0.01}
    setup = brain.step(rest_setup, 0.35, world_time=101.0)
    if setup.selected != "REST":
        failures.append(f"commitment_setup: expected REST, got {setup.selected}")
    results.append(diagnostic_result(
        "commitment_setup", rest_setup, "REST", setup,
        valuation(vector_from_mapping(rest_setup)),
    ))

    ambiguous = {"rest": 0.06, "rest_site": 0.70, "explore": 0.50, "novelty": 0.08, "open_space": 0.40}
    ambiguous_decision = brain.step(ambiguous, 0.20, world_time=101.20)
    ambiguous_item = diagnostic_result(
        "commitment_holds_ambiguous", ambiguous, "REST", ambiguous_decision,
        valuation(vector_from_mapping(ambiguous)),
    )
    if ambiguous_item["analytical_pick"] != "EXPLORE":
        failures.append("commitment_holds_ambiguous: analytical fixture no longer favours EXPLORE")
    if ambiguous_decision.selected != "REST":
        failures.append(f"commitment_holds_ambiguous: expected REST persistence, got {ambiguous_decision.selected}")
    results.append(ambiguous_item)

    expired = brain.step(ambiguous, 0.30, world_time=102.60)
    expired_item = diagnostic_result(
        "commitment_expires", ambiguous, "EXPLORE", expired,
        valuation(vector_from_mapping(ambiguous)),
    )
    if expired.selected != "EXPLORE":
        failures.append(f"commitment_expires: expected EXPLORE after expiry, got {expired.selected}")
    results.append(expired_item)

    brain.reset_temporal_state()
    brain.step(rest_setup, 0.35, world_time=110.0)
    danger = {"safety": 0.90, "motion": 0.90, "rest": 0.20, "rest_site": 1.0, "explore": 0.45}
    danger_decision = brain.step(danger, 0.25, world_time=110.20)
    danger_item = diagnostic_result(
        "threat_interrupts_commitment", danger, "FLEE", danger_decision,
        valuation(vector_from_mapping(danger)),
    )
    if danger_decision.selected != "FLEE":
        failures.append(f"threat_interrupts_commitment: expected FLEE, got {danger_decision.selected}")
    results.append(danger_item)

    zero_food = vector_from_mapping({"hunger": 1.0, "food": 0.0})
    zero_water = vector_from_mapping({"thirst": 1.0, "water": 0.0})
    gates_food = affordance_vector(zero_food)
    gates_water = affordance_vector(zero_water)
    if gates_food[ACTIONS.index("EAT")] != 0.0:
        failures.append("affordance_gate: EAT must be zero when food is absent")
    if gates_water[ACTIONS.index("DRINK")] != 0.0:
        failures.append("affordance_gate: DRINK must be zero when water is absent")

    brain.close()
    report = {
        "status": "PASS" if not failures else "FAIL",
        "backend": "nengo",
        "model": "NeuralBrain v0.2 motivational + affordance gating + temporal commitment",
        "neurons": brain.estimated_neuron_count,
        "checks": len(results) + 2,
        "failures": failures,
        "results": results,
        "invariants": {
            "eat_gate_without_food": float(gates_food[ACTIONS.index("EAT")]),
            "drink_gate_without_water": float(gates_water[ACTIONS.index("DRINK")]),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
