from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
agent = (ROOT / "scripts/cognition/agent.gd").read_text(encoding="utf-8")
resolver = (ROOT / "scripts/cognition/neural_action_resolver.gd").read_text(encoding="utf-8")
model = (ROOT / "brain/neural_model.py").read_text(encoding="utf-8")

def require(cond, label):
    if not cond:
        raise AssertionError(label)
    print("PASS", label)

require('"learned_food_access": 0.0' in agent and '"substrate_affordance": 0.0' in agent,
        "agent exposes learned consequence and substrate channels")
require('"scratch"]' in agent and 'return "MANIPULATE"' in agent,
        "scratch belongs to neural MANIPULATE family")
require('body.needs' not in resolver,
        "resolver never revalues candidates from current physiological drives")
require('kind == "forage"' not in resolver and 'kind == \'forage\'' not in resolver,
        "resolver contains no hardcoded forage-object rule")
require('"ground"' in resolver and '"loose"' in resolver and 'return "scratch"' in resolver,
        "scratch is exposed by substrate cues rather than object identity")
unsigned_transport = 'learned_food_access = clampf(predicted * reliability' in resolver
signed_transport = 'learned_food_signed' in resolver and '"learned_food_access": 0.50 + 0.50 * learned_food_signed' in resolver
require(unsigned_transport or signed_transport,
        "resolver transports learned food consequence without hunger multiplication")
require('BASE_INPUT_DIMS = len(INPUT_KEYS)' in model and 'input_node[INTEROCEPTIVE_DIMS:BASE_INPUT_DIMS]' in model,
        "original 16 neural channels retain their old anatomical slice")
require('input_node[BASE_INPUT_DIMS:]' in model and 'cognitive_affordances' in model,
        "new cognitive signals use a separate neural population")
require('_learned_food_manipulation_value' in model and '_substrate_manipulation_value' in model,
        "NeuralBrain performs state-dependent revaluation")
require('manipulate_learned_ctx' in model and 'manipulate_substrate_ctx' in model,
        "learned and substrate evidence have dedicated neural pathways")
print("ALL LEARNED-AFFORDANCE STATIC CHECKS PASS")
