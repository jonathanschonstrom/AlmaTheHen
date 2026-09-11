from pathlib import Path

p = Path('scripts/cognition/agent.gd')
s = p.read_text(encoding='utf-8')

def rep(old, new):
    global s
    if old not in s:
        raise SystemExit('agent pattern missing: ' + old[:80])
    s = s.replace(old, new, 1)

rep('if action in ["inspect", "peck", "push", "bite", "hop"]:\n\t\treturn "MANIPULATE"',
    'if action in ["inspect", "peck", "push", "bite", "hop", "scratch"]:\n\t\treturn "MANIPULATE"')

rep('\t\t"motion": 0.0,\n\t\t"open_space": 0.0\n\t}',
    '\t\t"motion": 0.0,\n\t\t"open_space": 0.0,\n\t\t"learned_manipulation": 0.0,\n\t\t"substrate_affordance": 0.0\n\t}')

rep('\t\tif world.objects.has(id):\n\t\t\tvar kind = str(world.objects[id].kind)\n\t\t\tif kind in ["ball", "box", "button", "cache", "treat"]:\n\t\t\t\tresult.manipulable = maxf(float(result.manipulable), availability)\n\treturn result',
    '\t\tif world.objects.has(id):\n\t\t\tvar kind = str(world.objects[id].kind)\n\t\t\tif kind in ["ball", "box", "button", "cache", "treat"]:\n\t\t\t\tresult.manipulable = maxf(float(result.manipulable), availability)\n\tvar manipulation = neural_actuator.manipulation_features(self)\n\tresult.manipulable = maxf(float(result.manipulable), float(manipulation.get("availability", 0.0)))\n\tresult.learned_manipulation = clampf(float(manipulation.get("learned_value", 0.0)), 0.0, 1.0)\n\tresult.substrate_affordance = clampf(float(manipulation.get("substrate_affordance", 0.0)), 0.0, 1.0)\n\treturn result')

p.write_text(s, encoding='utf-8')
