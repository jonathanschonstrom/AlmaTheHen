from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
resolver = (ROOT / "scripts/cognition/neural_action_resolver.gd").read_text(encoding="utf-8")
adapter = (ROOT / "brain/neural_model_feasibility.py").read_text(encoding="utf-8")
server = (ROOT / "brain/brain_server.py").read_text(encoding="utf-8")

# Resolver exposes exactly the same evidence that makes an experiment executable.
assert 'if mode == "experiment":' in resolver
assert 'focus.experiment_evidence' in resolver
assert 'focus.substrate_experiment' not in resolver.split('func neural_affordance_inputs', 1)[1].split('func resolve_manipulation', 1)[0]
assert 'if mode in ["learned_positive", "experiment"]' in resolver
assert 'body.needs' not in resolver

# Python keeps the 18D contract, gates only the historical generic manipulable
# cue, and preserves signed extinction as a separate pathway.
assert 'POSITIVE_FOOD_THRESHOLD = 0.04' in adapter
assert 'EXPERIMENT_THRESHOLD = 0.08' in adapter
assert 'x[_base.MANIPULABLE] *= _live_feasibility_from_transport(x)' in adapter
assert 'live_cognitive_contract = any(key in values for key in COGNITIVE_INPUT_KEYS)' in adapter
assert 'gates[ACTIONS.index("MANIPULATE")] = _live_feasibility_from_transport(x)' in adapter
assert 'return _ext.affordance_vector(raw)' in adapter
assert '_base.vector_from_mapping = vector_from_mapping' in adapter
assert '_base.affordance_vector = affordance_vector' in adapter

# Live logging must expose the feasibility state so a no-target stall can be
# diagnosed without inferring it from position alone.
assert 'from neural_model_feasibility import (' in server
assert '"manipulation_feasibility": manipulation_feasibility_from_mapping(inputs)' in server

print("PASS MANIPULATE feasibility static contracts")
