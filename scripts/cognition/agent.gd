extends RefCounted
const Homeostasis = preload("res://scripts/cognition/homeostasis.gd")
const Memory = preload("res://scripts/cognition/memory.gd")
const Learning = preload("res://scripts/cognition/learning.gd")
const Perception = preload("res://scripts/cognition/perception.gd")
const Utility = preload("res://scripts/cognition/utility.gd")
const NeuralActionResolver = preload("res://scripts/cognition/neural_action_resolver.gd")
var body = Homeostasis.new()
var memory = Memory.new()
var learning = Learning.new()
var senses = Perception.new()
var utility = Utility.new()
var neural_actuator = NeuralActionResolver.new()
var world
var rng = RandomNumberGenerator.new()
var individual_id = ""
var bird_name = "Alma"
var hen_share = 0.8
var personality = {}
var relationship = {"familiarity": 0.0, "trust": 0.18, "attachment": 0.0, "positive": 0, "negative": 0}
var position = Vector3(0, 0, 0)
var heading = Vector3(0, 0, -1)
var age = 0.0
var decision_count = 0
var current = {}
var phase = "idle"
var phase_time = 0.0
var action_duration = 0.0
var target_position = Vector3.ZERO
var last_actions = {}
var thought = "Vad finns här?"
var sense_clock = 0.0
var last_sound_sequence = 0
var velocity_y = 0.0
var wing_timing = 0.04
var trial_height = 0.0
var trial_airtime = 0.0
var trial_start = Vector3.ZERO
var distance_walked = 0.0
var last_reward = 0.0
var last_prediction_error = 0.0
var last_causal_outcome = {}
const SEMANTIC_CONTACT_ACTIONS = ["eat", "drink", "social", "inspect", "peck", "push", "bite"]
var support_id = ""
var ascent_powered = false
var last_perch_attempts = {}
var neural_shadow = {"bridge_status": "offline", "ok": false, "selected": "", "utility_family": "", "agreement": false, "confidence": 0.0, "action_values": {}, "competition_values": {}, "affordance_gates": {}, "commitment": {}, "basal_ganglia": {}, "neurons": 0}
var neural_control_enabled := false
var neural_selected_family := ""
var neural_selection_ready := false
var neural_request_id := -1
var neural_decision_age := 0.0
var neural_last_actuation = {}

func _init(world_state = null, seed_value: int = 42) -> void:
	world = world_state
	rng.seed = seed_value
	individual_id = "alma-%x-%x" % [int(Time.get_unix_time_from_system()), seed_value]
	var hen = {"boldness": 0.30, "curiosity": 0.45, "sociality": 0.72, "persistence": 0.54, "playfulness": 0.22}
	var parrot = {"boldness": 0.56, "curiosity": 0.94, "sociality": 0.82, "persistence": 0.78, "playfulness": 0.87}
	for key in hen:
		personality[key] = lerpf(float(parrot[key]), float(hen[key]), hen_share)

func activity_level() -> float:
	var action = current.get("action", "")
	if phase in ["ascend", "descend"] or action == "wings":
		return 1.15
	if action == "flee":
		return 0.90
	if phase == "approach":
		return 0.48
	if action in ["hop", "scratch", "push", "bite", "dust_bath"]:
		return 0.55
	if action in ["preen", "inspect", "social", "eat", "drink"]:
		return 0.20
	if action in ["rest", "perch"] and phase == "act":
		return 0.04
	return 0.12

func step(dt: float) -> void:
	world.tick(dt)
	age += dt
	var resting = phase == "act" and current.get("action", "") in ["rest", "perch"]
	var quality = world.rest_quality(position, support_id) if resting else 1.0
	body.tick(dt, activity_level(), resting, quality)
	sense_clock -= dt
	if sense_clock <= 0:
		sense_clock = 0.2
		senses.sample(world, position, heading, memory, body.needs, age)
		body.observe_stimulation(senses.stimulation)
		body.observe_social_presence(0.72 if senses.sees("o8") else 0.0)
		process_stimuli()
	if senses.sees("o8"):
		relationship.familiarity = minf(1.0, relationship.familiarity + dt * 0.0007)
	if current.is_empty():
		select_action()
		return
	# Legacy utility mode keeps its historical hard safety interruption. In neural
	# control, safety is only an input to NeuralBrain; only an NB-selected FLEE
	# family may interrupt an executing non-defensive motor primitive.
	if not neural_control_enabled and body.needs.safety > 0.68 and current.action != "flee" and (position.y < 0.02 or not support_id.is_empty()):
		current.clear()
		phase = "idle"
		phase_time = 0.0
		select_action()
	phase_time += dt
	if phase == "approach":
		approach(dt)
	elif phase == "act":
		act(dt)
	elif phase == "ascend":
		ascend(dt)
	elif phase == "descend":
		descend(dt)

func process_stimuli() -> void:
	for event in world.events:
		if int(event.sequence) <= last_sound_sequence:
			continue
		last_sound_sequence = int(event.sequence)
		if event.source == "bird" or position.distance_to(event.position) > 8.0:
			continue
		if event.intensity > 0.7:
			var before = body.needs.duplicate(true)
			body.add_threat(float(event.intensity))
			var effects = body.drive_effects(before)
			relationship.trust = maxf(0, relationship.trust - 0.06)
			relationship.negative += 1
			memory.add_episode({"time": age, "target": event.source, "action": "heard", "outcome": "Ett plötsligt ljud gjorde mig rädd.", "reward": -0.5, "position": vec(position), "effects": effects, "outcomes": {"threat": event.intensity}})
			thought = "Oj. Bort från ljudet."
		elif event.source == "o8" and position.distance_to(event.position) < 2.5:
			body.apply_outcome({"social_contact": 0.05, "calming": 0.03})
			relationship.trust = minf(1, relationship.trust + 0.012)
			memory.remember_working("o8", "kontakt", event.text, age)

func select_action() -> void:
	if neural_control_enabled:
		if not neural_selection_ready or neural_selected_family.is_empty():
			thought = "Väntar på NeuralBrain."
			return
		var family = neural_selected_family
		neural_selection_ready = false
		current = neural_actuator.resolve(self, family)
		if current.is_empty():
			record_resolution_failure(family)
			thought = "NeuralBrain valde %s men inget aktuellt mål kunde utföras." % family
			return
		current["neural_request_id"] = neural_request_id
		neural_last_actuation = {
			"request_id": neural_request_id,
			"family": family,
			"action": str(current.get("action", "")),
			"target": str(current.get("target", "")),
			"resolution": "resolved",
			"age": age
		}
	else:
		current = utility.choose(self)
	decision_count += 1
	thought = current.reason
	var target = current.target
	if target == "ground":
		target_position = Vector3(rng.randf_range(-5.0, 5.0), 0, rng.randf_range(-5.0, 5.0))
	elif target == "safe":
		var away = (position - world.objects.o8.position).normalized()
		target_position = position + away * 2.4
		target_position.x = clampf(target_position.x, -world.WALK_LIMIT, world.WALK_LIMIT)
		target_position.z = clampf(target_position.z, -world.WALK_LIMIT, world.WALK_LIMIT)
		target_position.y = 0
	elif memory.objects.has(target):
		var loc = memory.objects[target].position
		target_position = Vector3(float(loc[0]), 0, float(loc[2]))
	else:
		target_position = Vector3(position.x, 0, position.z)
	phase = "approach" if Vector2(position.x, position.z).distance_to(Vector2(target_position.x, target_position.z)) > 0.72 else "act"
	phase_time = 0
	if not support_id.is_empty() and target != support_id and (target != "self" or current.action in ["wings", "scratch"]):
		phase = "descend"
		velocity_y = 0
		return
	if phase == "act":
		begin_act()

func sensory_context(target: String) -> String:
	var cues = memory.objects.get(target, {}).get("cues", {})
	if cues.has("lit"):
		return "lamp_lit" if float(cues.lit) > 0.5 else "lamp_dark"
	return ""

func approach(dt: float) -> void:
	if senses.sees(current.target):
		var loc = memory.objects[current.target].position
		target_position = Vector3(float(loc[0]), 0, float(loc[2]))
	var delta = target_position - position
	delta.y = 0
	var reach = 0.75 if current.target == "o4" else 0.65
	if current.target in ["ground", "safe"]:
		reach = 0.15
	if delta.length() <= reach:
		begin_act()
		return
	if phase_time > 18.0 + personality.persistence * 10.0:
		if semantic_contact_action(str(current.get("action", ""))):
			finish_execution_failure("approach_timeout", "Vägen fram fungerade inte. Jag provar något annat.")
		else:
			finish({"outcomes": {}, "success": false, "outcome": "Vägen fram fungerade inte. Jag provar något annat.", "donor": ""})
		return
	heading = heading.lerp(delta.normalized(), minf(1, dt * 6)).normalized()
	var speed = 1.6 if current.action == "flee" else 0.73
	var previous = position
	position = world.move_ground(position, heading * speed, dt, current.target)
	distance_walked += previous.distance_to(position)

func begin_act() -> void:
	phase = "act"
	phase_time = 0
	current.context = sensory_context(current.target)
	current.body_before = body.needs.duplicate(true)
	current.error_before = body.homeostatic_error()
	var durations = {"eat": 2.4, "drink": 2.3, "rest": 9.0, "perch": 10.0, "dust_bath": 5.0, "preen": 3.5, "scratch": 2.6, "look": 2.2, "wander": 0.5, "flee": 1.6, "call": 1.1, "inspect": 2.4, "social": 3.0, "peck": 1.5, "push": 1.8, "bite": 2.1, "hop": 1.4, "wings": 2.4}
	action_duration = durations.get(current.action, 2.0)
	if current.action == "perch" and support_id != current.target:
		phase = "ascend"
		ascent_powered = float(learning.flight.best_height) > 0.40 and world.support_height(current.target) > 0.4
		wing_timing = float(learning.flight.best_timing)
		velocity_y = 1.4 if ascent_powered else 2.8
		trial_height = 0
		trial_start = position
		thought = "Provar att nå träytan och landa."
		return
	if current.action == "wings" and not world.practice_clear(position):
		finish({"outcomes": {}, "success": false, "outcome": "För trångt här. Jag behöver fri mark för vingförsöket.", "donor": ""})
		return
	if current.action in ["hop", "wings"]:
		velocity_y = 1.4 if current.action == "wings" else 2.0
		trial_height = 0
		trial_airtime = 0
		trial_start = position
		if current.action == "wings":
			wing_timing = learning.next_wing_timing()
	if current.action == "look":
		heading = heading.rotated(Vector3.UP, rng.randf_range(0.8, 2.2))

func ascend(dt: float) -> void:
	var previous_y = position.y
	if ascent_powered and phase_time < 0.34:
		velocity_y += 16.0 * exp(-pow((wing_timing - 0.58) / 0.27, 2.0)) * dt
	velocity_y -= 9.81 * dt
	position.y = maxf(0, position.y + velocity_y * dt)
	trial_height = maxf(trial_height, position.y)
	var target = world.objects[current.target].position
	var direction = Vector3(target.x - position.x, 0, target.z - position.z)
	if direction.length() > 0.02:
		heading = direction.normalized()
		var travel = direction.normalized() * minf(direction.length(), 1.65 * dt)
		position.x += travel.x
		position.z += travel.z
	var height = world.support_height(current.target)
	if velocity_y <= 0 and previous_y >= height and position.y <= height and world.flat_distance(position, target) < 0.28:
		position = Vector3(target.x, height, target.z)
		support_id = current.target
		velocity_y = 0
		phase = "act"
		phase_time = 0
		thought = "Fötterna fick fäste. Här kan jag sitta och se mig om."
		return
	if position.y <= 0 and phase_time > 0.15:
		last_perch_attempts[current.target] = float(learning.flight.best_height)
		finish({"outcomes": {"physical_effort": 0.035, "sensory_stimulation": 0.02}, "success": false, "outcome": "Försöket nådde %.0f cm. Pinnen var för hög att landa på." % (trial_height * 100), "donor": ""})

func descend(dt: float) -> void:
	var direction = Vector3(target_position.x - position.x, 0, target_position.z - position.z)
	if direction.length() < 0.01:
		direction = heading
	heading = direction.normalized()
	velocity_y -= 9.81 * dt
	position = world.move_ground(position, heading * 1.1, dt, "self")
	position.y = maxf(0, position.y + velocity_y * dt)
	if position.y <= 0:
		support_id = ""
		velocity_y = 0
		phase_time = 0
		if world.flat_distance(position, target_position) > 0.65:
			phase = "approach"
		else:
			begin_act()

func act(dt: float) -> void:
	if current.action in ["wings", "hop"]:
		if phase_time < 0.34 and current.action == "wings":
			# A fixed simplified biomechanical response. The learner never receives its optimum.
			var efficiency = exp(-pow((wing_timing - 0.58) / 0.27, 2.0))
			velocity_y += 16.0 * efficiency * dt
		velocity_y -= 9.81 * dt
		position.y = maxf(0, position.y + velocity_y * dt)
		if position.y > 0:
			trial_airtime += dt
			var next = world.move_ground(position, heading * (0.4 + minf(1.0, position.y)), dt, "self")
			position.x = next.x
			position.z = next.z
		else:
			velocity_y = 0
		trial_height = maxf(trial_height, position.y)
	if phase_time < action_duration:
		return
	var outcome
	if current.action == "wings":
		position.y = 0
		learning.learn_flight(trial_height, trial_airtime, position.distance_to(trial_start))
		outcome = {"outcomes": {"sensory_stimulation": 0.18, "physical_effort": 0.055, "motor_information": clampf(trial_height * 0.6 + trial_airtime * 0.1, 0.0, 0.4)}, "success": trial_height > 0.25, "outcome": "Vingförsök: %.0f cm höjd, %.2f s i luften." % [trial_height * 100, trial_airtime], "donor": ""}
	else:
		# Verify contact again before an effect. No remote eating, drinking or manipulation.
		var scoped_contact_action = semantic_contact_action(str(current.get("action", "")))
		if scoped_contact_action and not world.objects.has(current.target):
			finish_execution_failure("target_lost", "Föremålet fanns inte längre kvar att nå.")
			return
		if world.objects.has(current.target):
			var obj = world.objects[current.target]
			var separation = Vector2(obj.position.x, obj.position.z).distance_to(Vector2(position.x, position.z))
			if not obj.active:
				if scoped_contact_action:
					finish_execution_failure("target_lost", "Föremålet var inte längre tillgängligt.")
				else:
					finish({"outcomes": {}, "success": false, "outcome": "Föremålet var inte längre inom räckhåll.", "donor": ""})
				return
			if separation > 1.0 or (current.action in ["eat", "drink"] and absf(position.y - obj.position.y) > 0.25):
				if scoped_contact_action:
					finish_execution_failure("out_of_reach", "Föremålet var inte längre inom räckhåll.")
				else:
					finish({"outcomes": {}, "success": false, "outcome": "Föremålet var inte längre inom räckhåll.", "donor": ""})
				return
		if not current.get("context", "").is_empty():
			# Observe the lamp at contact, before pressing it can change the signal.
			senses.sample(world, position, heading, memory, body.needs, age)
			var context = sensory_context(current.target)
			if context != current.context:
				current.expected = learning.model(current.target, current.action, context).effects.duplicate(true)
			current.context = context
		outcome = world.perform(current.action, current.target, position, heading)
		finish(outcome, {
			"resolution": "resolved",
			"execution": "reached",
			"execution_reason": "",
			"contact_reached": true,
			"interaction": "executed",
			"consequence": "success" if bool(outcome.get("success", false)) else "failure",
			"semantic_eligible": true
		})
		return
	finish(outcome)

func semantic_contact_action(action: String) -> bool:
	return action in SEMANTIC_CONTACT_ACTIONS

func record_resolution_failure(family: String) -> void:
	last_causal_outcome = {
		"selected_family": family,
		"resolution": "no_target",
		"execution": "not_started",
		"execution_reason": "no_target",
		"contact_reached": false,
		"interaction": "not_executed",
		"consequence": "not_observed",
		"semantic_eligible": false,
		"learning_update": false,
		"learning_model": "",
		"context_model": ""
	}
	neural_last_actuation = {
		"request_id": neural_request_id,
		"family": family,
		"action": "",
		"target": "",
		"resolution": "no_target",
		"age": age
	}
	memory.add_episode({
		"time": age,
		"target": "",
		"action": "",
		"context": "",
		"outcome": "NeuralBrain valde en familj men inget aktuellt mål kunde lösas.",
		"reward": 0.0,
		"position": vec(position),
		"effects": {},
		"outcomes": {},
		"expected": {},
		"prediction_error": null,
		"causal": last_causal_outcome.duplicate(true)
	})

func finish_execution_failure(reason: String, outcome_text: String) -> void:
	finish(
		{"outcomes": {}, "success": false, "outcome": outcome_text, "donor": ""},
		{
			"resolution": "resolved",
			"execution": "failed",
			"execution_reason": reason,
			"contact_reached": false,
			"interaction": "not_executed",
			"consequence": "not_observed",
			"semantic_eligible": false
		}
	)

func finish(result: Dictionary, causal_stage: Dictionary = {}) -> void:
	var before = current.get("body_before", body.needs.duplicate(true)).duplicate(true)
	var error_before = float(current.get("error_before", body.homeostatic_error()))
	var outcomes = result.get("outcomes", {}).duplicate(true)
	var experienced_outcomes = outcomes.duplicate(true)
	var semantic_eligible = bool(causal_stage.get("semantic_eligible", true))
	var raw_information = maxf(0.0, float(outcomes.get("information_gain", 0.0)))
	var experienced_information = raw_information
	if raw_information > 0.0:
		var prior_model = learning.model(current.target, current.action, current.get("context", ""))
		experienced_information = raw_information / (1.0 + float(prior_model.count) * 0.75)
		experienced_outcomes.information_gain = experienced_information
	if outcomes.is_empty() and result.get("effects") is Dictionary and not result.effects.is_empty():
		body.apply(result.effects)
	else:
		body.apply_outcome(experienced_outcomes)
	var effects = body.drive_effects(before)
	for key in ["food_access", "object_motion", "motor_information"]:
		if outcomes.has(key):
			effects[key] = float(outcomes[key])
	var reward = (error_before - body.homeostatic_error()) * 1.8
	reward += experienced_information * 0.16
	reward += maxf(0.0, float(outcomes.get("sensory_stimulation", 0.0))) * 0.02
	if outcomes.has("food_access"):
		reward += float(outcomes.food_access) * float(before.get("hunger", body.needs.hunger)) * 0.8
	if not result.success:
		reward -= 0.08
		body.frustration += 0.06
	var prediction_error = null
	var learning_update = false
	if semantic_eligible:
		var learned = learning.learn(current.target, current.action, effects, reward, result.success, result.outcome, current.get("context", ""))
		prediction_error = learned.prediction_error
		last_prediction_error = float(learned.prediction_error)
		learning_update = true
	else:
		last_prediction_error = 0.0
	last_reward = reward
	if raw_information > 0.0:
		experienced_outcomes["raw_information_gain"] = raw_information
	var context = str(current.get("context", ""))
	last_causal_outcome = {
		"selected_family": action_family(str(current.get("action", ""))),
		"resolution": str(causal_stage.get("resolution", "resolved")),
		"execution": str(causal_stage.get("execution", "reached")),
		"execution_reason": str(causal_stage.get("execution_reason", "")),
		"contact_reached": bool(causal_stage.get("contact_reached", true)),
		"interaction": str(causal_stage.get("interaction", "executed")),
		"consequence": str(causal_stage.get("consequence", "success" if bool(result.get("success", false)) else "failure")),
		"semantic_eligible": semantic_eligible,
		"learning_update": learning_update,
		"learning_model": current.target + ":" + current.action if learning_update else "",
		"context_model": current.target + ":" + current.action + "@" + context if learning_update and not context.is_empty() else ""
	}
	memory.add_episode({"time": age, "target": current.target, "action": current.action, "context": context, "outcome": result.outcome, "reward": reward, "position": vec(position), "effects": effects, "outcomes": experienced_outcomes, "expected": current.get("expected", {}), "prediction_error": prediction_error, "causal": last_causal_outcome.duplicate(true)})
	last_actions[current.target + ":" + current.action] = age
	last_actions[current.action] = age
	if result.get("donor", "") == "o8":
		relationship.trust = minf(1, relationship.trust + (0.055 if current.action == "eat" else 0.015))
		relationship.attachment = minf(1, relationship.attachment + 0.008)
		relationship.positive += 1
	if current.action in ["inspect", "peck", "bite", "push", "wings"]:
		personality.curiosity = clampf(personality.curiosity + clampf(reward, -0.1, 0.3) * 0.001, 0.38, 0.72)
	thought = result.outcome
	current = {}
	phase = "idle"
	phase_time = 0

func touch() -> String:
	if not world.objects.o8.active or position.distance_to(world.objects.o8.position) > 1.7:
		return "Människan behöver stå närmare för försiktig kontakt."
	var accepted = relationship.trust > 0.3
	var text = "Lugn beröring. Den bekanta handen känns trygg." if accepted else "En obekant hand. Jag vill ha lite avstånd."
	if accepted:
		body.apply_outcome({"social_contact": 0.16, "calming": 0.05})
	else:
		body.add_threat(0.22)
	relationship.trust = clampf(relationship.trust + (0.025 if accepted else -0.01), 0, 1)
	memory.add_episode({"time": age, "target": "o8", "action": "touch", "outcome": text, "reward": 0.2 if accepted else -0.1, "position": vec(position), "effects": {}})
	return text


func set_neural_control(enabled: bool) -> void:
	neural_control_enabled = enabled
	if not enabled:
		neural_selected_family = ""
		neural_selection_ready = false
		neural_request_id = -1
		neural_decision_age = 0.0

func accept_neural_decision(decision: Dictionary) -> void:
	if not neural_control_enabled or not decision.get("ok", false):
		return
	var family = str(decision.get("selected", "")).to_upper()
	if family not in NeuralActionResolver.VALID_FAMILIES:
		return
	neural_selected_family = family
	neural_selection_ready = true
	neural_request_id = int(decision.get("request_id", -1))
	neural_decision_age = float(decision.get("age", age))
	# FLEE is the only family allowed to abort an already executing motor
	# primitive immediately. Other family changes take effect at the next
	# action boundary so partial eating/manipulation does not fabricate outcomes.
	if family == "FLEE" and not current.is_empty() and action_family(str(current.get("action", ""))) != "FLEE":
		current.clear()
		phase = "idle"
		phase_time = 0.0
		thought = "NeuralBrain avbröt pågående handling för FLEE."

func neural_bridge_unavailable(message: String = "") -> void:
	if not neural_control_enabled:
		return
	neural_selection_ready = false
	if current.is_empty():
		thought = "NeuralBrain är inte tillgänglig." if message.is_empty() else message

func utility_shadow_family() -> String:
	# Utility remains a diagnostic comparator in neural-control mode. Preserve
	# the agent RNG exactly so the reference calculation cannot perturb the
	# actual neural-controlled trajectory.
	var previous_state = rng.state
	var choice = utility.choose(self)
	rng.state = previous_state
	return action_family(str(choice.get("action", "look")))

func action_family(action: String) -> String:
	if action == "flee":
		return "FLEE"
	if action == "drink":
		return "DRINK"
	if action == "eat":
		return "EAT"
	if action in ["rest", "perch"]:
		return "REST"
	if action in ["social", "call", "touch"]:
		return "SOCIAL"
	if action in ["preen", "dust_bath"]:
		return "CARE"
	if action in ["inspect", "peck", "push", "bite", "hop"]:
		return "MANIPULATE"
	return "EXPLORE"

func neural_inputs() -> Dictionary:
	# NeuralBrain receives physiology + perception only. utility.gd scores are never exposed.
	var n = body.needs
	var result = {
		"hunger": clampf(float(n.hunger), 0.0, 1.0),
		"thirst": clampf(float(n.thirst), 0.0, 1.0),
		"rest": clampf(float(n.fatigue), 0.0, 1.0),
		"explore": clampf(float(n.boredom), 0.0, 1.0),
		"social": clampf(float(n.social), 0.0, 1.0),
		"safety": clampf(float(n.safety), 0.0, 1.0),
		"comfort": clampf(float(n.comfort), 0.0, 1.0),
		"food": 0.0,
		"water": 0.0,
		"person": 0.0,
		"rest_site": 0.0,
		"care_site": 0.0,
		"novelty": 0.0,
		"manipulable": 0.0,
		"motion": 0.0,
		"open_space": 0.0
	}
	for observation in senses.visible:
		var id = str(observation.id)
		var cues = observation.cues
		var distance = float(observation.distance)
		var proximity = clampf(1.0 - distance / 6.6, 0.0, 1.0)
		var record = memory.objects.get(id, {})
		var observations = float(record.get("observations", 1))
		var visits = float(record.get("visits", 0))
		var novelty = 1.0 / (1.0 + observations * 0.035 + visits * 0.70)
		var availability = 0.30 + proximity * 0.70
		result.food = maxf(float(result.food), float(cues.get("food", 0.0)) * availability)
		result.water = maxf(float(result.water), float(cues.get("water", 0.0)) * availability)
		result.person = maxf(float(result.person), float(cues.get("person", 0.0)) * availability)
		var rest_cue = maxf(float(cues.get("rail", 0.0)), maxf(float(cues.get("soft", 0.0)), float(cues.get("cover", 0.0))))
		result.rest_site = maxf(float(result.rest_site), rest_cue * availability)
		var care_cue = maxf(float(cues.get("fine", 0.0)), float(cues.get("loose", 0.0)))
		result.care_site = maxf(float(result.care_site), care_cue * availability)
		result.novelty = maxf(float(result.novelty), novelty * availability)
		result.motion = maxf(float(result.motion), (1.0 if observation.moving else 0.0) * availability)
		result.open_space = maxf(float(result.open_space), float(cues.get("open", 0.0)) * availability)
		if world.objects.has(id):
			var kind = str(world.objects[id].kind)
			if kind in ["ball", "box", "button", "cache", "treat"]:
				result.manipulable = maxf(float(result.manipulable), availability)
	return result

func export_data() -> Dictionary:
	return {"individual_id": individual_id, "name": bird_name, "hen_share": hen_share, "age": age, "position": vec(position), "heading": vec(heading), "body": body.export_data(), "needs": body.needs.duplicate(true), "personality": personality, "relationship": relationship, "memory": memory.export_data(), "learning": learning.export_data(), "last_actions": last_actions, "decision_count": decision_count, "distance_walked": distance_walked, "rng_state": str(rng.state), "rng_seed": str(rng.seed), "support_id": support_id, "last_perch_attempts": last_perch_attempts}

func restore(data: Dictionary) -> void:
	individual_id = data.get("individual_id", individual_id)
	bird_name = data.get("name", "Alma")
	hen_share = float(data.get("hen_share", hen_share))
	age = float(data.get("age", 0))
	position = unvec(data.get("position", [0, 0, 0]))
	support_id = data.get("support_id", "")
	if not world.on_perch(position, support_id):
		support_id = ""
		position.y = 0
	last_perch_attempts = data.get("last_perch_attempts", {}).duplicate(true)
	heading = unvec(data.get("heading", [0, 0, -1])).normalized()
	body.restore(data.get("body", {}), data.get("needs", {}))
	personality.merge(data.get("personality", {}), true)
	relationship.merge(data.get("relationship", {}), true)
	memory.restore(data.get("memory", {}))
	learning.restore(data.get("learning", {}))
	last_actions = data.get("last_actions", {}).duplicate(true)
	decision_count = int(data.get("decision_count", 0))
	distance_walked = float(data.get("distance_walked", 0))
	rng.seed = int(data.get("rng_seed", "42"))
	rng.state = int(data.get("rng_state", str(rng.state)))
	current.clear()
	thought = "Jag känner igen rummet."

static func vec(v: Vector3) -> Array:
	return [v.x, v.y, v.z]

static func unvec(v: Array) -> Vector3:
	return Vector3(float(v[0]), float(v[1]), float(v[2]))
