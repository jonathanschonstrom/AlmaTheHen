from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[1] / ".birdai" / "e1_d_h1b_resource_density.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("e1_d_h1b_under_test", HARNESS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {HARNESS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class E1DApparatusRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = load_harness()

    def test_density_bridge_uses_explicit_gdscript_types(self):
        source = (
            "func e1_d3_state(agent) -> Dictionary:\n"
            "\treturn {}\n"
            "func should_pause_simulation() -> bool:\n"
            "\treturn false\n"
        )
        patched = self.harness.density_lightweight_bridge_state(source)
        self.assertIn("var peer_present: bool = bool(", patched)
        self.assertIn("var peer_stock: float = -1.0", patched)
        self.assertIn("var peer_active: bool = false", patched)
        self.assertNotIn("peer_present :=", patched)
        self.assertNotIn("peer_stock :=", patched)
        self.assertNotIn("peer_active :=", patched)

    def test_rich_runtime_predeclares_exact_peer_from_o1_clone(self):
        source = (
            "func _init() -> void:\n"
            "\tobjects.o1.stock = BOWL_CAPACITY\n"
        )
        patched = self.harness.inject_peer_world_runtime(source)
        self.assertIn(
            'objects["e1d_food_peer"] = objects.o1.duplicate(true)',
            patched,
        )
        self.assertIn(
            'objects["e1d_food_peer"]["id"] = "e1d_food_peer"',
            patched,
        )
        self.assertIn(
            'objects["e1d_food_peer"]["position"] = Vector3(4.0, 0.0, 0.0)',
            patched,
        )

    def test_preflight_runtime_imports_subprocess(self):
        self.assertTrue(hasattr(self.harness, "subprocess"))
        self.assertTrue(hasattr(self.harness.subprocess, "run"))
        self.assertTrue(hasattr(self.harness.subprocess, "TimeoutExpired"))

    def test_peer_injection_refuses_ambiguous_or_existing_runtime(self):
        with self.assertRaises(self.harness.DensityError):
            self.harness.inject_peer_world_runtime(
                "\tobjects.o1.stock = BOWL_CAPACITY\n"
                "\tobjects.o1.stock = BOWL_CAPACITY\n"
            )
        with self.assertRaises(self.harness.DensityError):
            self.harness.inject_peer_world_runtime(
                "\tobjects.o1.stock = BOWL_CAPACITY\n"
                '# e1d_food_peer already present\n'
            )


if __name__ == "__main__":
    unittest.main()
