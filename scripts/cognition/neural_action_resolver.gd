extends RefCounted
## Actuator/target adapter for NeuralBrain family-level decisions.
##
## This file does not score or choose between action families. NeuralBrain is
## authoritative for that decision. The resolver only translates a selected
## family into a concrete motor action and a currently perceived target that
## can actually be executed by the existing Godot agent/world API.

const VALID_FAMILIES = ["FLEE", "DRINK", "EAT", "REST", "SOCIAL", "CARE", "EXPLORE", "MANIPULATE"]

func resolve(agent, family: String) -> Dictionary:
	family = family.to_upper()
	if family not in VALID_FAMILIES:
		return {}
	match family:
		"FLEE":
			return make_choice(agent, "flee", "safe", family, "NeuralBrain prioriterar avstånd från hotet.")
		"DRINK":
			var water = nearest_visible_with_cue(agent, "water")
			return make_choice(agent, "drink", water, family, "NeuralBrain prioriterar vätska.") if not water.is_empty() else {}
		"EAT":
			var food = nearest_visible_with_cue(agent, "food")
			return make_choice(agent, "eat", food, family, "NeuralBrain prioriterar föda.") if not food.is_empty() else {}
		"REST":
			var rest_target = nearest_rest_target(agent)
			if rest_target.is_empty():
				return make_choice(agent, "rest", "self", family, "NeuralBrain prioriterar vila.")
			var rest_action = "perch" if is_visible_rail(agent, rest_target) else "rest"
			return make_choice(agent, rest_action, rest_target, family, "NeuralBrain prioriterar vila.")
		"SOCIAL":
			var person = nearest_visible_with_cue(agent, "person")
			if person.is_empty():
				return make_choice(agent, "call", "self", family, "NeuralBrain prioriterar social kontakt.")
			return make_choice(agent, "social", person, family, "NeuralBrain prioriterar social kontakt.")
		"CARE":
			var care = nearest_care_target(agent)
			if care.is_empty():
				return make_choice(agent, "preen", "self", family, "NeuralBrain prioriterar fjädervård.")
			if visible_cue(agent, care, "fine") > 0.0:
				return make_choice(agent, "dust_bath", care, family, "NeuralBrain prioriterar fjädervård.")
			return make_choice(agent, "preen", "self", family, "NeuralBrain prioriterar fjädervård.")
		"EXPLORE":
			# NeuralBrain has selected exploration; direction remains a low-level
			# actuator choice until spatial target selection is moved into NB.
			return make_choice(agent, "wander", "ground", family, "NeuralBrain prioriterar utforskning.")
		"MANIPULATE":
			var target = nearest_manipulable(agent)
			if target.is_empty():
				return {}
			return make_choice(agent, manipulation_primitive(agent, target), target, family, "NeuralBrain prioriterar att undersöka eller påverka ett föremål.")
	return {}

func make_choice(agent, action: String, target: String, family: String, reason: String) -> Dictionary:
	var context = agent.sensory_context(target)
	var model = agent.learning.model(target, action, context)
	return {
		"action": action,
		"target": target,
		"goal": family.capitalize(),
		"reason": reason,
		"expected": model.effects.duplicate(true) if model.count > 0 else {},
		"context": context,
		"confidence": agent.learning.confidence(target, action, context),
		"controller": "neural",
		"neural_family": family
	}

func nearest_visible_with_cue(agent, cue_name: String) -> String:
	# Pick the observation that contributed the strongest sensory affordance to
	# the corresponding scalar NB input. This recovers object identity after the
	# current v0.2.6 max-pooling perception without introducing utility scores.
	var best_id = ""
	var best_signal = -1.0
	var best_distance = INF
	for observation in agent.senses.visible:
		var cue = float(observation.cues.get(cue_name, 0.0))
		if cue <= 0.1:
			continue
		var distance = float(observation.distance)
		var proximity = clampf(1.0 - distance / 6.6, 0.0, 1.0)
		var cue_signal = cue * (0.30 + proximity * 0.70)
		if cue_signal > best_signal or (is_equal_approx(cue_signal, best_signal) and distance < best_distance):
			best_signal = cue_signal
			best_distance = distance
			best_id = str(observation.id)
	return best_id

func nearest_rest_target(agent) -> String:
	var best_id = ""
	var best_signal = -1.0
	var best_distance = INF
	for observation in agent.senses.visible:
		var cues = observation.cues
		var rest_cue = maxf(float(cues.get("rail", 0.0)), maxf(float(cues.get("soft", 0.0)), float(cues.get("cover", 0.0))))
		if rest_cue <= 0.0:
			continue
		if float(cues.get("rail", 0.0)) > 0.0:
			var height = float(cues.get("height", 0.0))
			var reachable = height <= maxf(0.39, float(agent.learning.flight.best_height) * 0.97)
			if not reachable:
				continue
		var distance = float(observation.distance)
		var proximity = clampf(1.0 - distance / 6.6, 0.0, 1.0)
		var rest_signal = rest_cue * (0.30 + proximity * 0.70)
		if rest_signal > best_signal or (is_equal_approx(rest_signal, best_signal) and distance < best_distance):
			best_signal = rest_signal
			best_distance = distance
			best_id = str(observation.id)
	return best_id

func is_visible_rail(agent, id: String) -> bool:
	for observation in agent.senses.visible:
		if str(observation.id) == id:
			return float(observation.cues.get("rail", 0.0)) > 0.0
	return false

func nearest_care_target(agent) -> String:
	var best_id = ""
	var best_signal = -1.0
	var best_distance = INF
	for observation in agent.senses.visible:
		var cues = observation.cues
		var care_cue = maxf(float(cues.get("fine", 0.0)), float(cues.get("loose", 0.0)))
		if care_cue <= 0.0:
			continue
		var distance = float(observation.distance)
		var proximity = clampf(1.0 - distance / 6.6, 0.0, 1.0)
		var care_signal = care_cue * (0.30 + proximity * 0.70)
		if care_signal > best_signal or (is_equal_approx(care_signal, best_signal) and distance < best_distance):
			best_signal = care_signal
			best_distance = distance
			best_id = str(observation.id)
	return best_id

func visible_cue(agent, id: String, cue_name: String) -> float:
	for observation in agent.senses.visible:
		if str(observation.id) == id:
			return float(observation.cues.get(cue_name, 0.0))
	return 0.0

func nearest_manipulable(agent) -> String:
	var best_id = ""
	var best_distance = INF
	for observation in agent.senses.visible:
		var id = str(observation.id)
		if not agent.world.objects.has(id):
			continue
		var kind = str(agent.world.objects[id].kind)
		if kind not in ["ball", "box", "button", "cache", "treat"]:
			continue
		var distance = float(observation.distance)
		if distance < best_distance:
			best_distance = distance
			best_id = id
	return best_id

func manipulation_primitive(agent, id: String) -> String:
	if not agent.world.objects.has(id):
		return "inspect"
	match str(agent.world.objects[id].kind):
		"button":
			return "peck"
		"ball":
			return "push"
		"box":
			return "push"
		_:
			return "inspect"
