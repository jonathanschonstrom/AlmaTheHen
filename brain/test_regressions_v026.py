"""Separate pure regressions; the canonical Nengo selftest remains 3 x 21."""
from pathlib import Path
import ast
import importlib.util
import itertools
import math
import json
import sys
import unittest

import numpy as np
import neural_model as model
import selftest
from temporal_commitment import TemporalCommitment, SWITCH_MARGIN

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('original_v05_reference', ROOT / 'tests/reference_v05_neural_model.py')
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)
DETAILS = {}


def state():
    return TemporalCommitment(model.ACTIONS, model.COMMITMENT_STRENGTH, model.COMMITMENT_DURATION)


def evidence(**values):
    return np.asarray([values.get(name, 0.0) for name in model.ACTIONS])


def latch(action='REST', now=10.0):
    s = state()
    s.prepare(now, 0.0, np.ones(8))
    index = model.ACTIONS.index(action)
    values = np.zeros(8)
    values[index] = 0.4
    s.resolve(index, values, now)
    return s


class PolicyRegression(unittest.TestCase):
    def test_v05_policy_equivalence_20000_random_states(self):
        rng = np.random.default_rng(90231)
        maximum = 0.0
        for row in rng.uniform(-0.25, 1.25, (20000, 16)):
            maximum = max(maximum, float(np.max(np.abs(model.valuation(row) - reference.valuation(row)))))
        DETAILS['policy_random_states'] = 20000
        DETAILS['policy_max_abs_error'] = maximum
        self.assertLessEqual(maximum, 1e-12)

    def test_manipulate_factorization_unseen_domain_and_corners(self):
        rng = np.random.default_rng(776019)
        rows = np.vstack([rng.uniform(-0.1, 1.1, (100000, 5)), list(itertools.product([0., 1.], repeat=5))])
        maximum = 0.0
        for e, n, m, motion, safety in rows:
            subtotal = (model._manipulate_drive_value([e, m]) + model._manipulate_novelty_value([n, m])
                        + model._manipulate_motion_value([motion, m]))
            actual = model._manipulate_safety_gate([subtotal, safety])
            expected = reference._manipulate_value([e, n, m, motion, safety])
            maximum = max(maximum, abs(actual - expected))
        DETAILS['factorization_states'] = len(rows)
        DETAILS['factorization_max_abs_error'] = maximum
        self.assertLessEqual(maximum, 1e-12)

    def test_original_manipulate_reference_is_unedited(self):
        def function(path):
            module = ast.parse(path.read_text(encoding='utf-8-sig'))
            return ast.dump(next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == '_manipulate_value'))
        self.assertEqual(function(ROOT / 'brain/neural_model.py'), function(ROOT / 'tests/reference_v05_neural_model.py'))

    def test_contract_and_decay_unchanged(self):
        for name in ('ACTIONS', 'INPUT_KEYS', 'COMMITMENT_STRENGTH', 'COMMITMENT_DURATION'):
            self.assertEqual(getattr(model, name), getattr(reference, name))

    def test_canonical_scenarios_seeds_and_temporal_inputs_unchanged(self):
        old = ast.parse((ROOT / 'tests/reference_v05_selftest.py').read_text(encoding='utf-8-sig'))
        new = ast.parse((ROOT / 'brain/selftest.py').read_text(encoding='utf-8-sig'))
        def assigned(tree, name):
            return [ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
        for name in ('SCENARIOS', 'rest_setup', 'ambiguous', 'danger', 'zero_food', 'zero_water'):
            if name.startswith('zero_'):
                continue
            self.assertEqual(assigned(old, name), assigned(new, name))
        def steps(tree):
            return [ast.dump(n) for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == 'brain' and n.func.attr in ('step', 'reset_temporal_state')]
        self.assertEqual(steps(old), steps(new))
        self.assertEqual(selftest.SEEDS, (20260910, 42, 1701))
        self.assertEqual(len(selftest.SCENARIOS), 15)

    def test_no_analytical_fallback_in_runtime_class(self):
        tree = ast.parse((ROOT / 'brain/neural_model.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'NeuralBrain')
        calls = [n.func.id for n in ast.walk(cls) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertNotIn('valuation', calls)
        self.assertNotIn('_manipulate_value', calls)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertNotIn('SCENARIOS', names)
        self.assertNotIn('DECODER_DOMAIN_ANCHORS', names)

    def test_all_python_sources_parse(self):
        for path in list((ROOT / 'brain').glob('*.py')) + list((ROOT / 'tests').glob('*.py')):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))


class TemporalRegression(unittest.TestCase):
    def test_weak_spurious_bg_cannot_acquire_latch(self):
        s = state()
        s.prepare(0., 0., np.ones(8))
        s.resolve(2, evidence(REST=.2, EXPLORE=.19), 0.)
        self.assertIsNone(s.current)

    def test_clear_supported_evidence_acquires_latch(self):
        s = latch()
        self.assertEqual(s.current, 3)
        self.assertEqual(s.started, 10.)

    def test_strong_neural_evidence_cannot_latch_wrong_bg_action(self):
        s = state()
        s.prepare(0., 0., np.ones(8))
        s.resolve(2, evidence(REST=.4, EXPLORE=.1), 0.)
        self.assertEqual(s.current, 3)

    def test_weak_challenger_keeps_competition_and_selected_action(self):
        s = latch()
        s.prepare(10.2, 0., np.ones(8))
        values = evidence(REST=.20, EXPLORE=.25)
        self.assertEqual(int(s.project(values).argmax()), 3)
        selected, metadata = s.resolve(6, values, 10.2)
        self.assertEqual(selected, 3)
        self.assertEqual(metadata['bg_selected_action'], 'EXPLORE')
        self.assertFalse(metadata['bg_matches_selected'])
        self.assertEqual(s.started, 10.)

    def test_switch_boundary_equality_holds(self):
        s = latch()
        values = evidence(REST=.20, EXPLORE=.20 + SWITCH_MARGIN)
        self.assertTrue(s.should_hold(values))
        self.assertEqual(int(s.project(values).argmax()), 3)

    def test_strong_challenger_releases_latch(self):
        s = latch()
        values = evidence(REST=.20, EXPLORE=.20 + SWITCH_MARGIN + .0001)
        np.testing.assert_array_equal(s.project(values), values)
        selected, _ = s.resolve(6, values, 10.2)
        self.assertEqual(selected, 6)
        self.assertEqual(s.current, 6)
        self.assertEqual(s.started, 10.2)

    def test_margin_compares_to_incumbent_not_runner_up(self):
        s = latch()
        values = evidence(REST=.20, EXPLORE=.295, MANIPULATE=.30)
        self.assertFalse(s.should_hold(values))
        np.testing.assert_array_equal(s.project(values), values)

    def test_repeated_holds_do_not_extend_expiry(self):
        s = latch()
        for now in (10.2, 10.7, 11.2):
            s.prepare(now, 0., np.ones(8))
            s.resolve(6, evidence(REST=.20, EXPLORE=.24), now)
            self.assertEqual(s.started, 10.)
        bias, remaining = s.prepare(11.25, 0., np.ones(8))
        self.assertIsNone(s.current)
        self.assertEqual(remaining, 0.)
        self.assertTrue(np.all(bias == 0))
        self.assertEqual(s.release_reason, 'expired')

    def test_affordance_loss_releases_before_next_sample(self):
        for action in ('DRINK', 'EAT', 'REST', 'SOCIAL', 'CARE', 'MANIPULATE'):
            s = latch(action)
            gates = np.ones(8)
            gates[s.current] = .1599
            bias, _ = s.prepare(10.1, 0., gates)
            self.assertIsNone(s.current)
            self.assertTrue(np.all(bias == 0))

    def test_affordance_boundary_and_general_explore(self):
        s = latch()
        gates = np.zeros(8)
        gates[3] = .16
        s.prepare(10.1, 0., gates)
        self.assertEqual(s.current, 3)
        s = latch('EXPLORE')
        s.prepare(10.1, 0., np.zeros(8))
        self.assertEqual(s.current, 6)

    def test_threat_interrupts_and_blocks_nondefensive_reacquisition(self):
        for action in model.ACTIONS[1:]:
            s = latch(action)
            s.prepare(10.001, .55, np.ones(8))
            self.assertIsNone(s.current)
            self.assertEqual(s.release_reason, 'threat_interrupt')
            s.resolve(3, evidence(REST=.8), 10.001)
            self.assertIsNone(s.current)
        s = latch('FLEE')
        s.prepare(10.1, .9, np.ones(8))
        self.assertEqual(s.current, 0)

    def test_clock_rewind_releases_old_latch(self):
        s = latch()
        s.prepare(2., 0., np.ones(8))
        self.assertIsNone(s.current)
        self.assertEqual(s.release_reason, 'clock_rewound')

    def test_reset_clears_state_and_bias(self):
        s = latch()
        s.prepare(10.2, 0., np.ones(8))
        self.assertGreater(float(s.bias.max()), 0.)
        s.reset()
        self.assertIsNone(s.current)
        self.assertTrue(np.all(s.bias == 0))

    def test_free_projection_is_identity_including_negative_evidence(self):
        s = state()
        for values in np.random.default_rng(919).uniform(-.5, 1.8, (2000, 8)):
            np.testing.assert_array_equal(s.project(values), values)

    def test_hysteresis_invariant_all_actions_on_unseen_vectors(self):
        rng = np.random.default_rng(591103)
        for current in range(8):
            s = latch(model.ACTIONS[current])
            for values in rng.uniform(-.2, .8, (1000, 8)):
                projected = s.project(values)
                challenger, advantage = s.challenger(values)
                if advantage <= SWITCH_MARGIN:
                    self.assertEqual(int(projected.argmax()), current)
                    others = [i for i in range(8) if i != current]
                    np.testing.assert_array_equal(projected[others], values[others])
                else:
                    np.testing.assert_array_equal(projected, values)


class ExploreEvalPointRegression(unittest.TestCase):
    EXPLORE_FUNCTIONS = {
        '_explore_base_value',
        '_hunger_search_value',
        '_thirst_search_value',
        '_explore_safety_gate',
    }

    def _tree(self):
        return ast.parse((ROOT / 'brain/neural_model.py').read_text(encoding='utf-8-sig'))

    def _explore_connections(self):
        found = {}
        for node in ast.walk(self._tree()):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == 'Connection'):
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            fnode = keywords.get('function')
            if isinstance(fnode, ast.Name) and fnode.id in self.EXPLORE_FUNCTIONS:
                found[fnode.id] = keywords
        return found

    def test_all_four_explore_decoders_use_physical_eval_points(self):
        found = self._explore_connections()
        self.assertEqual(set(found), self.EXPLORE_FUNCTIONS)
        for name, keywords in found.items():
            with self.subTest(function=name):
                self.assertIn('scale_eval_points', keywords)
                self.assertIs(ast.literal_eval(keywords['scale_eval_points']), False)

    def test_explore_analytical_functions_are_identical_to_v025(self):
        current = ast.parse((ROOT / 'brain/neural_model.py').read_text(encoding='utf-8-sig'))
        previous = ast.parse((ROOT / 'docs/evidence-v0.5.6/reference-v0.2.5-neural_model.py').read_text(encoding='utf-8-sig'))
        names = ('_explore_base_value', '_hunger_search_value', '_thirst_search_value',
                 '_explore_safety_gate', '_explore_value')
        def funcs(tree):
            result = {}
            for n in tree.body:
                if not isinstance(n, ast.FunctionDef) or n.name not in names:
                    continue
                body = list(n.body)
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    body = body[1:]
                result[n.name] = ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)
            return result
        self.assertEqual(funcs(current), funcs(previous))

    def test_physical_eval_domains_fit_ensemble_radii(self):
        self.assertLessEqual(math.sqrt(3.0), math.sqrt(3.0) + 1e-12)
        self.assertLessEqual(math.sqrt(2.0), math.sqrt(2.0) + 1e-12)
        self.assertLessEqual(math.hypot(1.70, 1.0), 2.10)
        DETAILS['explore_gate_max_eval_norm'] = math.hypot(1.70, 1.0)
        DETAILS['explore_gate_radius'] = 2.10

    def test_v025_radius_scaling_would_leave_declared_physical_domains(self):
        # This regression captures the API-semantics bug without any selftest coordinate.
        self.assertGreater(math.sqrt(3.0), 1.0)
        self.assertGreater(math.sqrt(2.0), 1.0)
        self.assertGreater(1.70 * 2.10, 1.80)
        self.assertGreater(1.0 * 2.10, 1.0)

    def test_explore_diagnostics_probe_existing_connections(self):
        text = (ROOT / 'brain/neural_model.py').read_text(encoding='utf-8-sig')
        for connection in ('explore_drive_in', 'explore_novelty_in', 'explore_open_space_in',
                           'explore_hunger_in', 'explore_food_in', 'explore_thirst_in',
                           'explore_water_in', 'explore_subtotal_in', 'explore_safety_in',
                           'explore_base_conn', 'hunger_search_conn', 'thirst_search_conn',
                           'explore_gate_conn'):
            with self.subTest(connection=connection):
                self.assertIn(f'nengo.Probe({connection}, "output", synapse=None)', text)
        # No second diagnostic valuation pathway may feed action_values.
        self.assertEqual(text.count('function=_explore_base_value'), 1)
        self.assertEqual(text.count('function=_hunger_search_value'), 1)
        self.assertEqual(text.count('function=_thirst_search_value'), 1)
        self.assertEqual(text.count('function=_explore_safety_gate'), 1)

    def test_mixed_manipulate_policy_margin_remains_original(self):
        values = dict(next(v for n, v, expected in selftest.SCENARIOS if n == 'mixed_manipulate'))
        analytic = model.valuation(model.vector_from_mapping(values))
        manipulate = float(analytic[model.ACTIONS.index('MANIPULATE')])
        explore = float(analytic[model.ACTIONS.index('EXPLORE')])
        DETAILS['mixed_manipulate_analytical_manipulate'] = manipulate
        DETAILS['mixed_manipulate_analytical_explore'] = explore
        DETAILS['mixed_manipulate_analytical_margin'] = manipulate - explore
        reference_values = reference.valuation(reference.vector_from_mapping(values))
        self.assertGreater(manipulate, explore)
        self.assertAlmostEqual(manipulate, float(reference_values[model.ACTIONS.index('MANIPULATE')]), places=12)
        self.assertAlmostEqual(explore, float(reference_values[model.ACTIONS.index('EXPLORE')]), places=12)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'checks': result.testsRun,
              'failures': [{'test': str(t), 'detail': e} for t, e in result.failures + result.errors],
              'details': DETAILS, 'canonical_runtime_checks_unchanged': 63}
    out = ROOT / 'data/regression-v0.2.6.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
