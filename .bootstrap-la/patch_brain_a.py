from pathlib import Path
p=Path('brain/neural_model.py')
s=p.read_text(encoding='utf-8')
def rep(old,new):
    global s
    if old not in s: raise SystemExit('brain-a pattern missing: '+old[:90])
    s=s.replace(old,new,1)
rep('    "manipulable", "motion", "open_space",\n)\n\nINTEROCEPTIVE_DIMS = 7\nEXTEROCEPTIVE_DIMS = len(INPUT_KEYS) - INTEROCEPTIVE_DIMS\n\n# Global input indexes.\nHUNGER, THIRST, REST, EXPLORE, SOCIAL, SAFETY, COMFORT = range(7)\nFOOD, WATER, PERSON, REST_SITE, CARE_SITE, NOVELTY, MANIPULABLE, MOTION, OPEN_SPACE = range(7, 16)',
'''    "manipulable", "motion", "open_space", "learned_manipulation",\n    "substrate_affordance",\n)\n\nINTEROCEPTIVE_DIMS = 7\nBASE_INPUT_DIMS = 16\nEXTEROCEPTIVE_DIMS = BASE_INPUT_DIMS - INTEROCEPTIVE_DIMS\nCOGNITIVE_DIMS = 2\n\n# Global input indexes. The original 16 channels retain their positions.\nHUNGER, THIRST, REST, EXPLORE, SOCIAL, SAFETY, COMFORT = range(7)\nFOOD, WATER, PERSON, REST_SITE, CARE_SITE, NOVELTY, MANIPULABLE, MOTION, OPEN_SPACE = range(7, 16)\nLEARNED_MANIPULATION, SUBSTRATE_AFFORDANCE = range(16, 18)''')
rep('    "eval_manipulate_motion": 114, "eval_manipulate_gate": 115,\n}',
    '    "eval_manipulate_motion": 114, "eval_manipulate_gate": 115,\n    "learned_affordance_state": 45, "manipulate_learned_ctx": 46, "manipulate_substrate_ctx": 47,\n    "eval_manipulate_learned": 116, "eval_manipulate_substrate": 117,\n}')
old='''def _manipulate_value(x: Sequence[float]) -> float:\n    """Manipulation requires a perceived manipulable affordance.\n\n    Novelty is useful but not mandatory. A familiar object can still invite\n    pecking/pushing/inspection when exploratory motivation remains active.\n    """\n    explore, novelty, manipulable, motion, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)\n    value = 0.012 + manipulable * (\n        0.025 + 0.30 * explore + 0.55 * novelty + 0.06 * motion\n    )\n    return value * _suppress(safety)\n'''
new='''def _manipulate_value(x: Sequence[float]) -> float:\n    """Baseline affordance plus learned and substrate-derived manipulation value."""\n    explore, novelty, manipulable, motion, safety, learned, substrate, hunger = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)\n    value = 0.012 + manipulable * (0.025 + 0.30 * explore + 0.55 * novelty + 0.06 * motion)\n    value += 1.20 * learned\n    value += 0.52 * (hunger ** 1.15) * substrate\n    return value * _suppress(safety)\n'''
rep(old,new)
marker='''def _manipulate_motion_value(x: Sequence[float]) -> float:\n    motion, manipulable = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)\n    return manipulable * 0.06 * motion\n\n'''
insert=marker+'''def _manipulate_learned_value(x: Sequence[float]) -> float:\n    learned, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)\n    return 1.20 * learned * _suppress(safety)\n\ndef _manipulate_substrate_value(x: Sequence[float]) -> float:\n    hunger, substrate, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)\n    return 0.52 * (hunger ** 1.15) * substrate * _suppress(safety)\n\n'''
rep(marker,insert)
rep('        x[MANIPULABLE],\n    ], dtype=float)',
    '        max(float(x[MANIPULABLE]), float(x[LEARNED_MANIPULATION]), float(x[SUBSTRATE_AFFORDANCE])),\n    ], dtype=float)')
rep('''            _manipulate_value([\n                values[EXPLORE], values[NOVELTY], values[MANIPULABLE], values[MOTION], values[SAFETY],\n            ]),''',
'''            _manipulate_value([\n                values[EXPLORE], values[NOVELTY], values[MANIPULABLE], values[MOTION], values[SAFETY],\n                values[LEARNED_MANIPULATION], values[SUBSTRATE_AFFORDANCE], values[HUNGER],\n            ]),''')
p.write_text(s,encoding='utf-8')
