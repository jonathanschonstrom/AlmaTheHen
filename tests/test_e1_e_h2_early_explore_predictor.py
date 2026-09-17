from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / ".birdai" / "e1_e_h2_early_explore_predictor.py"
CAPTURED_EVIDENCE = Path(__file__).resolve().parent / "fixtures"


def load_harness():
    spec = importlib.util.spec_from_file_location("e1_e_h2_under_test", HARNESS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {HARNESS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def state_event(tick: int, *, distance: float, o1: float, peer: float | None = None):
    world = {"o1_stock": o1}
    if peer is None:
        world.update({
            "e1d_peer_present": False,
            "e1d_peer_stock": -1.0,
            "e1d_peer_active": False,
        })
    else:
        world.update({
            "e1d_peer_present": True,
            "e1d_peer_stock": peer,
            "e1d_peer_active": True,
        })
    return {
        "event": "sim_state",
        "sim_tick": tick,
        "state": {
            "agent": {"distance_walked": distance},
            "world": world,
        },
    }


def response(tick: int, selected: str):
    return {
        "event": "response_received",
        "ok": True,
        "target_apply_tick": tick,
        "selected": selected,
        "control_mode": "control",
        "actuator_authority": "neural",
    }


def snapshot(*, distance: float, o1: float, peer: float | None = None):
    objects = {
        "o1": {"stock": o1, "position": [-4.0, 0.0, 0.0], "active": True},
    }
    if peer is not None:
        objects["e1d_food_peer"] = {
            "stock": peer,
            "position": [4.0, 0.0, 0.0],
            "active": True,
        }
    return {
        "agent": {"distance_walked": distance},
        "world": {"objects": objects},
    }


class E1EEarlyPredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = load_harness()

    def test_frozen_registration_from_windows_snapshot_is_accepted(self):
        path = CAPTURED_EVIDENCE / "e1-e-h2-early-explore-predictor-v1.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        seeds, runtime = self.h.validate_registration(reg)
        self.assertEqual(seeds, self.h.EXPECTED_SEEDS)
        self.assertEqual(runtime, "d931be650b955a6378785d0bf7ded4360461f447")

    def test_registration_rejects_seed_replacement(self):
        path = CAPTURED_EVIDENCE / "e1-e-h2-early-explore-predictor-v1.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        reg["seed_set"][0] = 1
        with self.assertRaisesRegex(self.h.PredictorError, "Seed set changed"):
            self.h.validate_registration(reg)

    def test_registration_rejects_predictor_window_change(self):
        path = CAPTURED_EVIDENCE / "e1-e-h2-early-explore-predictor-v1.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        reg["early_predictor"]["window_sim_seconds"] = [0.0, 31.0]
        with self.assertRaisesRegex(self.h.PredictorError, "window changed"):
            self.h.validate_registration(reg)

    def test_windowed_metrics_exclude_first_30_seconds_from_late_outcome_sparse(self):
        # sim_dt=10 sec => 30 sec boundary is tick 3; run ends at tick 18.
        events = []
        for tick in range(1, 19):
            stock = 10.0 if tick <= 5 else 9.0
            events.append(state_event(
                tick,
                distance=float(tick),
                o1=stock,
            ))
        events += [
            response(1, "EXPLORE"),
            response(2, "EAT"),
            response(3, "EXPLORE"),
            response(4, "EXPLORE"),
            response(5, "EAT"),
            response(6, "EXPLORE"),
        ]
        result = self.h.compute_windowed_metrics(
            events=events,
            initial=snapshot(distance=0.0, o1=10.0),
            final=snapshot(distance=18.0, o1=9.0),
            sim_dt=10.0,
            stop_tick=18,
        )
        self.assertEqual(result["boundary_tick"], 3)
        self.assertAlmostEqual(result["early"]["selected_explore_proportion"], 2 / 3)
        self.assertAlmostEqual(result["late"]["selected_explore_proportion"], 2 / 3)
        self.assertEqual(result["late"]["time_to_first_valid_food_interaction_seconds"], 30.0)
        self.assertEqual(result["late"]["total_distance_travelled_m"], 15.0)
        self.assertEqual(result["late"]["food_acquisitions"], 1.0)
        self.assertAlmostEqual(result["late"]["food_acquisition_rate_per_sim_minute"], 0.4)

    def test_windowed_metrics_sum_rich_peer_stock(self):
        events = []
        for tick in range(1, 19):
            peer = 10.0 if tick <= 8 else 9.0
            events.append(state_event(
                tick,
                distance=tick * 0.5,
                o1=10.0,
                peer=peer,
            ))
        events += [
            response(1, "EAT"),
            response(2, "EXPLORE"),
            response(3, "EAT"),
            response(4, "EXPLORE"),
            response(5, "EXPLORE"),
        ]
        result = self.h.compute_windowed_metrics(
            events=events,
            initial=snapshot(distance=0.0, o1=10.0, peer=10.0),
            final=snapshot(distance=9.0, o1=10.0, peer=9.0),
            sim_dt=10.0,
            stop_tick=18,
        )
        self.assertEqual(result["late"]["tested_resource_stock_at_30s"], 20.0)
        self.assertEqual(result["late"]["tested_resource_final_stock_total"], 19.0)
        self.assertEqual(result["late"]["food_acquisitions"], 1.0)
        self.assertEqual(result["late"]["time_to_first_valid_food_interaction_seconds"], 60.0)

    def test_early_prediction_uses_sparse_minus_rich(self):
        rich = {"e1e_early": {"selected_explore_proportion": 0.2}}
        sparse = {"e1e_early": {"selected_explore_proportion": 0.7}}
        item = self.h.early_prediction(rich, sparse)
        self.assertAlmostEqual(item["delta_sparse_minus_rich"], 0.5)
        self.assertEqual(item["label"], "predicted")

    def test_late_metric_directions_follow_frozen_direction_rules(self):
        rich = {
            "e1e_late": {
                "time_to_first_valid_food_interaction_seconds": 10.0,
                "total_distance_travelled_m": 20.0,
                "selected_explore_proportion": 0.2,
                "food_acquisition_rate_per_sim_minute": 0.8,
            }
        }
        sparse = {
            "e1e_late": {
                "time_to_first_valid_food_interaction_seconds": None,
                "total_distance_travelled_m": 25.0,
                "selected_explore_proportion": 0.4,
                "food_acquisition_rate_per_sim_minute": 0.4,
            }
        }
        directions = self.h.late_metric_directions(rich, sparse)
        self.assertEqual(
            directions,
            {metric: "predicted" for metric in self.h.PRIMARY_METRICS},
        )

    def test_late_pair_label_uses_predicted_minus_opposite_score(self):
        directions = {
            self.h.PRIMARY_METRICS[0]: "predicted",
            self.h.PRIMARY_METRICS[1]: "opposite",
            self.h.PRIMARY_METRICS[2]: "predicted",
            self.h.PRIMARY_METRICS[3]: "neutral",
        }
        result = self.h.late_pair_label(directions)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["label"], "predicted")

    def _pairs(self):
        labels = ["predicted", "opposite", "predicted", "opposite", "predicted"]
        return [
            {
                "pair_validity": "PASS",
                "early_prediction": {"label": label},
                "late_pair_label": label,
                "prediction_match": True,
            }
            for label in labels
        ]

    def test_stage_supported_requires_five_of_five_and_two_late_classes(self):
        result, counts = self.h.classify_stage(self._pairs(), "PASS")
        self.assertEqual(result, "SUPPORTED")
        self.assertEqual(counts["match_count"], 5)
        self.assertTrue(counts["both_non_neutral_late_classes_present"])

    def test_stage_four_of_five_is_inconclusive(self):
        pairs = self._pairs()
        pairs[-1]["early_prediction"]["label"] = "opposite"
        pairs[-1]["prediction_match"] = False
        result, counts = self.h.classify_stage(pairs, "PASS")
        self.assertEqual(result, "INCONCLUSIVE")
        self.assertEqual(counts["match_count"], 4)

    def test_stage_three_of_five_is_not_supported(self):
        pairs = self._pairs()
        for index in (-1, -2):
            pairs[index]["early_prediction"]["label"] = (
                "opposite" if pairs[index]["late_pair_label"] == "predicted" else "predicted"
            )
            pairs[index]["prediction_match"] = False
        result, counts = self.h.classify_stage(pairs, "PASS")
        self.assertEqual(result, "NOT_SUPPORTED")
        self.assertEqual(counts["match_count"], 3)

    def test_neutral_label_forces_inconclusive(self):
        pairs = self._pairs()
        pairs[0]["early_prediction"]["label"] = "neutral"
        pairs[0]["prediction_match"] = False
        result, _ = self.h.classify_stage(pairs, "PASS")
        self.assertEqual(result, "INCONCLUSIVE")

    def test_single_late_class_forces_inconclusive(self):
        pairs = [
            {
                "pair_validity": "PASS",
                "early_prediction": {"label": "predicted"},
                "late_pair_label": "predicted",
                "prediction_match": True,
            }
            for _ in range(5)
        ]
        result, _ = self.h.classify_stage(pairs, "PASS")
        self.assertEqual(result, "INCONCLUSIVE")

    def test_invalid_stage_has_no_scientific_result(self):
        result, _ = self.h.classify_stage(self._pairs(), "INVALID")
        self.assertIsNone(result)

    def test_e1e_harness_reuses_e1d_apparatus_without_mutating_product(self):
        density = self.h.load_density_helper(ROOT)
        self.h.configure_density_for_e1e(density)
        self.assertEqual(density.STAGE, "E1-E")
        self.assertEqual(density.REGISTRATION_SHA256, self.h.REGISTRATION_SHA256)
        source = (
            "func _init() -> void:\n"
            "\tobjects.o1.stock = BOWL_CAPACITY\n"
        )
        patched = density.inject_peer_world_runtime(source)
        self.assertIn('objects["e1d_food_peer"] = objects.o1.duplicate(true)', patched)
        self.assertIn('Vector3(4.0, 0.0, 0.0)', patched)


if __name__ == "__main__":
    unittest.main(verbosity=2)
