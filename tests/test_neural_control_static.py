from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')

def require(cond, label):
    if not cond:
        raise AssertionError(label)
    print('PASS', label)

agent = read('scripts/cognition/agent.gd')
bridge = read('scripts/cognition/neural_brain_bridge.gd')
resolver = read('scripts/cognition/neural_action_resolver.gd')
main = read('scripts/main.gd')
model = read('brain/neural_model.py')

require('var neural_control_enabled := false' in agent, 'agent exposes explicit neural-control state')
require('if neural_control_enabled:' in agent and 'current = neural_actuator.resolve(self, family)' in agent,
        'neural family is resolved before any utility fallback path')
select_block = agent.split('func select_action() -> void:',1)[1].split('func sensory_context',1)[0]
require(select_block.index('if neural_control_enabled:') < select_block.index('current = utility.choose(self)'),
        'neural authority precedes legacy utility branch')
require('return' in select_block.split('if not neural_selection_ready',1)[1].split('else:',1)[0],
        'missing neural decision causes wait instead of utility fallback')
require('if not neural_control_enabled and body.needs.safety > 0.68' in agent,
        'legacy Godot safety override is disabled when NeuralBrain is authoritative')
require('if family == "FLEE"' in agent and 'current.clear()' in agent.split('if family == "FLEE"',1)[1].split('func neural_bridge_unavailable',1)[0],
        'motor interruption in neural-control mode requires an NB-selected FLEE')
require('agent.accept_neural_decision(parsed)' in bridge, 'bridge applies NB response to real agent in control mode')
require('var mode := "control"' in bridge, 'bridge defaults to control mode')
require('agent.utility_shadow_family()' in bridge, 'utility retained as control-mode reference only')
require('neural_bridge_unavailable' in bridge and 'ingen utility-fallback' in bridge,
        'bridge failure explicitly avoids utility fallback')
require('utility.' not in resolver.lower() and re.search(r'\bscore\s*=', resolver.lower()) is None,
        'actuator resolver contains no utility scoring path')
for family in ['FLEE','DRINK','EAT','REST','SOCIAL','CARE','EXPLORE','MANIPULATE']:
    require(f'"{family}"' in resolver, f'resolver covers {family}')
require('make_choice(agent, "rest", "self", family' in resolver, 'REST remains executable without a visible rest target')
require('make_choice(agent, "call", "self", family' in resolver, 'SOCIAL remains executable without a visible person')
require('make_choice(agent, "preen", "self", family' in resolver, 'CARE remains executable without a visible care site')
require('result.food = maxf' in agent and 'result.water = maxf' in agent and 'result.rest_site = maxf' in agent,
        'controller experiment retains the existing semantic perception-to-NB interface')
require('neural_mode = "control"' in main and 'agent.set_neural_control(neural_mode == "control")' in main,
        'normal Godot runtime enables neural control')
require('--neural-shadow' in main, 'legacy shadow remains explicit opt-in mode')
require('neural-control.jsonl' in bridge and 'agent_position' in bridge and 'last_neural_actuation' in bridge,
        'control runtime logs neural authority plus physical trajectory context')
require('utility.gd' not in model.lower() and 'ranked' not in model.lower(), 'NeuralBrain model remains code-independent of utility ranking')
print('ALL STATIC NEURAL-CONTROL CHECKS PASS')
