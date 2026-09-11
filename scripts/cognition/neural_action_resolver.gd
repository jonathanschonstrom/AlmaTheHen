extends RefCounted
## Actuator/target adapter for NeuralBrain family-level decisions.
##
## This file does not score or choose between action families. NeuralBrain is
## authoritative for that decision. The resolver only translates a selected
## family into a concrete motor action and a currently perceived target that
## can actually be executed by the existing Godot agent/world API.

const VALID_FAMILIES = ["FLEE", "DRINK", "EAT", "REST", "SOCIAL", "CARE", "EXPLORE", "MANIPULATE"]
const POSITIVE_FOOD_THRESHOLD = 0.04
const EXPERIMENT_THRESHOLD = 0.08
const EXTINCTION_THRESHOLD = -0.08

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
			return make_choice(agent, "wander", "ground", family, "NeuralBrain prioriterar utforskning.")
		"MANIPULATE":
			var resolved = resolve_manipulation(agent)
			var target = str(resolved.get("target", ""))
			var action = str(resolved.get("action", ""))
			if target.is_empty() or action.is_empty():
				return {}
			return make_choice(agent, action, target, family, "NeuralBrain prioriterar manipulation; resolvern uttrycker det target/action/context-spår som bär den neurala evidensen.")
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

func manipulation_candidates(agent) -> Array:
	# Candidate construction is drive-free. It separates physical actionability,
	# epistemic uncertainty and learned consequences. Current hunger is not used.
	var candidates = []
	for observation in agent.senses.visible:
		var id = str(observation.id)
		if not agent.world.objects.has(id):
			continue
		var action = manipulation_primitive(agent, id)
		if action.is_empty():
			continue
		var distance = float(observation.distance)
		var proximity = clampf(1.0 - distance / 6.6, 0.0, 1.0)
		var availability = 0.30 + proximity * 0.70
		var context = agent.sensory_context(id)
		var model = agent.learning.model(id, action, context)
		var count = maxf(0.0, float(model.count))
		var confidence = clampf(agent.learning.confidence(id, action, context), 0.0, 1.0)
		var success = clampf(float(model.success), 0.0, 1.0)

		# Signed food prediction: positive evidence predicts future access; explicit
		# learned absence/failure becomes negative evidence. Zero means unknown/neutral.
		var learned_food_signed = 0.0
		if count > 0.0:
			var reliability = 0.50 + 0.50 * confidence
			if model.effects.has("food_access"):
				var predicted_food = clampf(float(model.effects.get("food_access", 0.0)), 0.0, 1.0)
				if predicted_food > POSITIVE_FOOD_THRESHOLD:
					learned_food_signed = predicted_food * success * reliability
				else:
					learned_food_signed = -confidence
			elif success < 0.5:
				learned_food_signed = -confidence * (1.0 - success)
		learned_food_signed = clampf(learned_food_signed, -1.0, 1.0)

		var cues = observation.cues
		var substrate_physical = minf(float(cues.get("ground", 0.0)), float(cues.get("loose", 0.0))) * availability
		var interaction_uncertainty = 1.0 / (1.0 + count * 0.70)
		var substrate_experiment = substrate_physical * interaction_uncertainty
		var kind = str(agent.world.objects[id].kind)
		var classic = kind in ["ball", "box", "button", "cache", "treat"]
		var classic_experiment = availability * interaction_uncertainty if classic else 0.0
		var experiment_evidence = maxf(substrate_experiment, classic_experiment)

		candidates.append({
			"target": id,
			"action": action,
			"context": context,
			"distance": distance,
			"availability": availability,
			"learned_food_signed": learned_food_signed,
			"learned_food_access": 0.50 + 0.50 * learned_food_signed,
			"substrate_physical": substrate_physical,
			"substrate_experiment": substrate_experiment,
			"interaction_uncertainty": interaction_uncertainty,
			"experiment_evidence": experiment_evidence,
			"classic": classic
		})
	return candidates

func focused_manipulation_candidate(agent) -> Dictionary:
	var candidates = manipulation_candidates(agent)
	if candidates.is_empty():
		return {}

	# Attention is selected without physiological drives. Positive learned causal
	# evidence wins first; otherwise the least-tested executable affordance gets an
	# experiment. Only when neither exists do we expose the strongest extinction
	# trace to NeuralBrain, and that negative focus is not executed by the resolver.
	var positive = {}
	var positive_score = 0.0
	var experiment = {}
	var experiment_score = 0.0
	var negative = {}
	var negative_score = 0.0
	for candidate in candidates:
		var signed_food = float(candidate.learned_food_signed)
		if signed_food > positive_score:
			positive_score = signed_food
			positive = candidate
		var epistemic = float(candidate.experiment_evidence)
		if epistemic > experiment_score:
			experiment_score = epistemic
			experiment = candidate
		if signed_food < negative_score:
			negative_score = signed_food
			negative = candidate

	if positive_score > POSITIVE_FOOD_THRESHOLD:
		var selected_positive = positive.duplicate(true)
		selected_positive["focus_mode"] = "learned_positive"
		return selected_positive
	if experiment_score > EXPERIMENT_THRESHOLD:
		var selected_experiment = experiment.duplicate(true)
		selected_experiment["focus_mode"] = "experiment"
		return selected_experiment
	if negative_score < EXTINCTION_THRESHOLD:
		var selected_negative = negative.duplicate(true)
		selected_negative["focus_mode"] = "extinction"
		return selected_negative
	return {}

func neural_affordance_inputs(agent) -> Dictionary:
	# 0.5 is the neutral point for signed learned-food evidence. The historical
	# wire name substrate_affordance is retained, but in v5 it carries the current
	# executable *experiment* opportunity for either substrate or classic objects.
	var result = {"learned_food_access": 0.5, "substrate_affordance": 0.0}
	var focus = focused_manipulation_candidate(agent)
	if focus.is_empty():
		return result
	result.learned_food_access = clampf(float(focus.learned_food_access), 0.0, 1.0)
	var mode = str(focus.get("focus_mode", ""))
	if mode == "experiment":
		result.substrate_affordance = clampf(float(focus.experiment_evidence), 0.0, 1.0)
	return result

func resolve_manipulation(agent) -> Dictionary:
	var focus = focused_manipulation_candidate(agent)
	if focus.is_empty():
		return {}
	var mode = str(focus.get("focus_mode", ""))
	if mode in ["learned_positive", "experiment"]:
		return focus
	# Extinction is neural inhibitory evidence, never a command to repeat the action.
	return {}

func nearest_visible_with_cue(agent, cue_name: String) -> String:
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
	return str(resolve_manipulation(agent).get("target", ""))

func manipulation_primitive(agent, id: String) -> String:
	if not agent.world.objects.has(id):
		return ""
	var cues = agent.memory.objects.get(id, {}).get("cues", {})
	if float(cues.get("ground", 0.0)) > 0.1 and float(cues.get("loose", 0.0)) > 0.1:
		return "scratch"
	match str(agent.world.objects[id].kind):
		"button":
			return "peck"
		"ball", "box":
			return "push"
		"cache", "treat":
			return "inspect"
	return ""