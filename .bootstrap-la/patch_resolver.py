from pathlib import Path

p = Path('scripts/cognition/neural_action_resolver.gd')
s = p.read_text(encoding='utf-8')

def rep(old, new):
    global s
    if old not in s:
        raise SystemExit('resolver pattern missing: ' + old[:100])
    s = s.replace(old, new, 1)

rep('\t\t"MANIPULATE":\n\t\t\tvar target = nearest_manipulable(agent)\n\t\t\tif target.is_empty():\n\t\t\t\treturn {}\n\t\t\treturn make_choice(agent, manipulation_primitive(agent, target), target, family, "NeuralBrain prioriterar att undersöka eller påverka ett föremål.")',
    '\t\t"MANIPULATE":\n\t\t\tvar manipulation = manipulation_features(agent)\n\t\t\tvar target = str(manipulation.get("target", ""))\n\t\t\tvar action = str(manipulation.get("action", ""))\n\t\t\tif target.is_empty() or action.is_empty():\n\t\t\t\treturn {}\n\t\t\treturn make_choice(agent, action, target, family, "NeuralBrain prioriterar en möjlig handling vars konsekvens är relevant eller ännu okänd.")')

marker = 'func nearest_visible_with_cue(agent, cue_name: String) -> String:\n'
insert = '''func manipulation_features(agent) -> Dictionary:\n\tvar best = {"target": "", "action": "", "salience": -1.0, "availability": 0.0, "learned_value": 0.0, "substrate_affordance": 0.0}\n\tfor observation in agent.senses.visible:\n\t\tvar id = str(observation.id)\n\t\tif not agent.world.objects.has(id):\n\t\t\tcontinue\n\t\tvar action = manipulation_primitive(agent, id)\n\t\tif action.is_empty():\n\t\t\tcontinue\n\t\tvar distance = float(observation.distance)\n\t\tvar availability = clampf(1.0 - distance / 6.6, 0.0, 1.0)\n\t\tavailability = 0.30 + availability * 0.70\n\t\tvar context = agent.sensory_context(id)\n\t\tvar model = agent.learning.model(id, action, context)\n\t\tvar learned_value = 0.0\n\t\tif float(model.count) > 0.0:\n\t\t\tfor effect in model.effects:\n\t\t\t\tif agent.body.needs.has(effect):\n\t\t\t\t\tlearned_value += float(model.effects[effect]) * float(agent.body.needs[effect])\n\t\t\t\telif effect == "food_access":\n\t\t\t\t\tlearned_value += float(model.effects[effect]) * float(agent.body.needs.hunger)\n\t\t\tvar confidence = agent.learning.confidence(id, action, context)\n\t\t\tvar reliability = 0.35 + 0.65 * clampf((float(model.success) + confidence) * 0.5, 0.0, 1.0)\n\t\t\tlearned_value = clampf(maxf(0.0, learned_value) * reliability * availability, 0.0, 1.0)\n\t\tvar cues = observation.cues\n\t\tvar substrate = minf(float(cues.get("ground", 0.0)), float(cues.get("loose", 0.0))) * availability\n\t\tvar unknown = 1.0 / (1.0 + float(model.count))\n\t\tvar search_drive = maxf(float(agent.body.needs.boredom), float(agent.body.needs.hunger))\n\t\tvar salience = availability * 0.04 + learned_value * 1.15 + substrate * (0.15 + 0.45 * float(agent.body.needs.hunger)) + unknown * 0.08 * float(agent.personality.curiosity) * search_drive\n\t\tif salience > float(best.salience):\n\t\t\tbest = {"target": id, "action": action, "salience": salience, "availability": availability, "learned_value": learned_value, "substrate_affordance": substrate}\n\treturn best\n\n'''
if marker not in s:
    raise SystemExit('resolver insertion marker missing')
s = s.replace(marker, insert + marker, 1)

start = s.index('func nearest_manipulable(agent) -> String:')
end = len(s)
old = s[start:end]
new = '''func nearest_manipulable(agent) -> String:\n\treturn str(manipulation_features(agent).get("target", ""))\n\nfunc manipulation_primitive(agent, id: String) -> String:\n\tif not agent.world.objects.has(id):\n\t\treturn ""\n\tvar cues = agent.memory.objects.get(id, {}).get("cues", {})\n\tif float(cues.get("ground", 0.0)) > 0.1 and float(cues.get("loose", 0.0)) > 0.1:\n\t\treturn "scratch"\n\tmatch str(agent.world.objects[id].kind):\n\t\t"button":\n\t\t\treturn "peck"\n\t\t"ball", "box":\n\t\t\treturn "push"\n\t\t"cache", "treat":\n\t\t\treturn "inspect"\n\treturn ""\n'''
s = s[:start] + new
p.write_text(s, encoding='utf-8')
