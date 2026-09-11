extends RefCounted
## Running action/outcome models, revalued against current needs by Utility.
## No action sequences, XP thresholds, language model, or prefilled object facts.
var models = {}
var contexts = {}
var skills = {}
var flight = {"timing": 0.04, "best_timing": 0.04, "best_height": 0.0, "last_height": 0.0, "trials": 0, "step": 0.08, "direction": 1.0, "airtime": 0.0, "distance": 0.0}

func model(target: String, action: String, context: String = "") -> Dictionary:
	var storage = models if context.is_empty() else contexts
	var key = target + ":" + action + ("@" + context if not context.is_empty() else "")
	return storage.get(key, {"count": 0, "effects": {}, "success": 0.5, "outcome": "Okänt resultat", "reward": 0.0, "error": 0.0})

func learn(target: String, action: String, effects: Dictionary, reward: float, success: bool, outcome: String, context: String = "") -> Dictionary:
	var key = target + ":" + action
	var m = update_model(model(target, action), effects, reward, success, outcome)
	models[key] = m
	if not context.is_empty():
		contexts[key + "@" + context] = update_model(model(target, action, context), effects, reward, success, outcome)
	var skill = skills.get(action, {"attempts": 0, "successes": 0})
	skill.attempts += 1
	if success:
		skill.successes += 1
	skills[action] = skill
	return {"prediction_error": m.error, "confidence": confidence(target, action, context)}

func update_model(previous: Dictionary, effects: Dictionary, reward: float, success: bool, outcome: String) -> Dictionary:
	var m = previous.duplicate(true)
	var error = reward - float(m.reward)
	m.count += 1
	# Nonzero floor permits relearning after the environment changes.
	var alpha = maxf(0.18, 1.0 / float(m.count))
	var keys = effects.keys()
	for effect in m.effects:
		if not keys.has(effect):
			keys.append(effect)
	for effect in keys:
		m.effects[effect] = lerpf(float(m.effects.get(effect, 0)), float(effects.get(effect, 0)), alpha)
	m.reward = lerpf(float(m.reward), reward, alpha)
	m.success = lerpf(float(m.success), 1.0 if success else 0.0, alpha)
	m.outcome = outcome
	m.error = error
	return m

func confidence(target: String, action: String, context: String = "") -> float:
	return 1.0 - exp(-float(model(target, action, context).count) / 4.0)

func next_wing_timing() -> float:
	if int(flight.trials) == 0:
		return float(flight.timing)
	flight.timing = clampf(float(flight.best_timing) + float(flight.step) * float(flight.direction), 0.02, 0.95)
	return float(flight.timing)

func learn_flight(height: float, airtime: float, distance: float) -> void:
	flight.trials += 1
	flight.last_height = height
	flight.airtime = airtime
	flight.distance = distance
	# Coordinate search uses measured lift, not a hidden target or a trial-count unlock.
	if height > float(flight.best_height) + 0.003:
		flight.best_height = height
		flight.best_timing = flight.timing
	else:
		flight.direction *= -1.0
		flight.step = maxf(0.015, float(flight.step) * 0.7)

func export_data() -> Dictionary:
	return {"models": models, "contexts": contexts, "skills": skills, "flight": flight}

func restore(data: Dictionary) -> void:
	models = data.get("models", {}).duplicate(true)
	contexts = data.get("contexts", {}).duplicate(true)
	skills = data.get("skills", {}).duplicate(true)
	flight.merge(data.get("flight", {}), true)
