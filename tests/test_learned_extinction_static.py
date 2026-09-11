from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
resolver = (ROOT / "scripts/cognition/neural_action_resolver.gd").read_text(encoding="utf-8")
adapter = (ROOT / "brain/neural_model_extinction.py").read_text(encoding="utf-8")
server = (ROOT / "brain/brain_server.py").read_text(encoding="utf-8")

assert 'const POSITIVE_FOOD_THRESHOLD = 0.04' in resolver
assert 'const EXPERIMENT_THRESHOLD = 0.08' in resolver
assert 'const EXTINCTION_THRESHOLD = -0.08' in resolver
assert '"learned_food_access": 0.5' in resolver
assert 'learned_food_signed = -confidence' in resolver
assert 'focus_mode"] = "extinction"' in resolver
assert 'if mode in ["learned_positive", "experiment"]' in resolver
assert 'return {}\n\nfunc nearest_visible_with_cue' in resolver
assert 'best_distance = INF' not in resolver.split('func resolve_manipulation', 1)[1].split('func nearest_visible_with_cue', 1)[0]
assert 'body.needs' not in resolver

assert 'NEUTRAL_LEARNED_FOOD = 0.5' in adapter
assert 'signed_prediction = (float(encoded_prediction) - NEUTRAL_LEARNED_FOOD) * 2.0' in adapter
assert '_base._learned_food_manipulation_value = _signed_learned_food_manipulation_value' in adapter
assert 'learned_positive = max(0.0' in adapter
assert 'from neural_model_extinction import ACTIONS, ALL_INPUT_KEYS, NeuralBrain' in server

print("PASS learned-extinction static contracts")
