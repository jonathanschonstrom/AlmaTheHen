extends SceneTree
const World = preload("res://scripts/world/world_state.gd")
const Agent = preload("res://scripts/cognition/agent.gd")
const Persistence = preload("res://scripts/persistence.gd")
const NeuralBridge = preload("res://scripts/cognition/neural_brain_bridge.gd")
var failures = []
var report = {}
var checks = 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)
	print(("PASS " if condition else "FAIL ") + label)

func run() -> void:
	var w = World.new()
	var a = Agent.new(w, 20260910)
	check(a.memory.objects.is_empty() and a.learning.models.is_empty(), "No preloaded world knowledge")
	check(a.position.y == 0 and a.learning.flight.best_height == 0, "Starts grounded with no flight experience")
	check(is_equal_approx(a.hen_share, 0.8), "Temperament: 80 percent hen")
	var counts = {}
	var previous_count = 0
	var max_hunger = 0.0
	var max_thirst = 0.0
	var visited = {}
	var in_bounds = true
	for i in range(60 * 1800):
		a.step(1.0 / 60.0)
		max_hunger = maxf(max_hunger, a.body.needs.hunger)
		max_thirst = maxf(max_thirst, a.body.needs.thirst)
		visited[w.area_at(a.position)] = true
		in_bounds = in_bounds and absf(a.position.x) <= w.WALK_LIMIT + 0.001 and absf(a.position.z) <= w.WALK_LIMIT + 0.001
		if a.memory.total_episodes > previous_count:
			var episode = a.memory.episodes.back()
			counts[episode.action] = counts.get(episode.action, 0) + 1
			previous_count = a.memory.total_episodes
		if not a.position.is_finite():
			check(false, "Finite body position")
			break
	check(a.decision_count > 100 and a.distance_walked > 10, "30 simulated minutes without human input")
	check(counts.get("eat", 0) > 0 and counts.get("drink", 0) > 0 and counts.get("rest", 0) + counts.get("perch", 0) > 0, "Autonomous eating, drinking and resting without fixed action-frequency assumptions")
	check(max_hunger < 0.99 and max_thirst < 0.99, "Homeostasis avoids critical hunger and thirst")
	check(counts.size() >= 10, "Diverse unsequenced autonomous actions")
	check(a.learning.models.has("o5:peck"), "Autonomously discovers button by pecking")
	check(a.learning.model("o5", "peck", "lamp_lit").effects.get("food_access", 0) > 0.1, "Learns food access from the lit experiment button")
	check(a.learning.model("o13", "scratch").effects.get("food_access", 0) > 0.01 and a.learning.model("o13", "scratch").count >= 4, "Learns that scratching loose soil can expose food without directly ingesting it")
	check(a.learning.flight.trials >= 8 and a.learning.flight.best_height > 0.55, "Learns short flight from measured lift")
	check(a.memory.episodes.size() <= 160, "Bounded episodic memory")
	check(in_bounds, "Remains inside expanded enclosure for entire run")
	check(counts.get("perch", 0) > 0 and counts.get("dust_bath", 0) > 0 and counts.get("scratch", 0) > 0, "Autonomously uses perches, sand and soil")
	check(visited.size() >= 6, "Autonomously visits functional areas")
	check(a.learning.model("o6", "perch").count > 0 and a.learning.model("o6", "perch").success > 0.5, "Autonomously flies to the high roost during the long run")
	var before_trust = a.relationship.trust
	w.objects.o8.position = a.position + Vector3(0.3, 0, 0)
	w.objects.o1.stock = 0
	w.refill_food_bowl(1.0, "o8")
	a.position = w.objects.o1.position
	a.support_id = ""
	a.current = {"target": "o1", "action": "eat", "expected": {}}
	a.finish(w.perform("eat", "o1", a.position, a.heading))
	check(a.relationship.trust > before_trust, "Eating offered food changes relationship")
	var w2 = World.new()
	var a2 = Agent.new(w2, 7)
	a2.body.physiology.state.metabolic_energy = 0.34
	a2.body.physiology.state.stomach_fill = 0.05
	a2.body.physiology.state.gut_energy = 0.02
	a2.body.update_drives()
	a2.position = w2.objects.o5.position + Vector3(0, 0, 0.4)
	w2.next_experiment_time = w2.now
	w2.tick(0)
	a2.senses.sample(w2, a2.position, Vector3.FORWARD, a2.memory, a2.body.needs, 0)
	a2.utility.choose(a2)
	var button_before = score_of(a2.utility.ranked, "o5", "peck")
	for i in range(3):
		w2.objects.o9.stock = 0
		w2.objects.o9.cues.food = 0.0
		w2.hatch_open = false
		w2.next_experiment_time = w2.now
		w2.tick(0)
		var result = w2.perform("peck", "o5", w2.objects.o5.position, Vector3.FORWARD)
		a2.learning.learn("o5", "peck", {"food_access": float(result.outcomes.get("food_access", 0.0))}, 0.2, result.success, result.outcome, "lamp_lit")
	a2.utility.choose(a2)
	check(score_of(a2.utility.ranked, "o5", "peck") > button_before, "Learned consequence changes future utility")
	var lit_score = score_of(a2.utility.ranked, "o5", "peck")
	for i in range(3):
		var result = w2.perform("peck", "o5", w2.objects.o5.position, Vector3.FORWARD)
		a2.learning.learn("o5", "peck", {}, -0.08, result.success, result.outcome, "lamp_dark")
	a2.senses.sample(w2, a2.position, Vector3.FORWARD, a2.memory, a2.body.needs, 0)
	a2.utility.choose(a2)
	check(lit_score > score_of(a2.utility.ranked, "o5", "peck") + 0.1, "Learned lamp context reduces futile button pecking during cooldown")
	a2.body.physiology.state.metabolic_energy = 0.88
	a2.body.physiology.state.stomach_fill = 0.75
	a2.body.physiology.state.hydration = 0.25
	a2.body.update_drives()
	a2.senses.sample(w2, Vector3(-1.8, 0, 1.0), Vector3.LEFT, a2.memory, a2.body.needs, 0)
	var urgent = a2.utility.choose(a2)
	check(urgent.action == "drink", "Urgent thirst beats curiosity")
	w2.objects.o10.active = true
	w2.objects.o10.stock = 1.0
	w2.objects.o10.cues.food = 1.0
	a2.position = w2.objects.o10.position
	a2.senses.sample(w2, a2.position, Vector3.FORWARD, a2.memory, a2.body.needs, 0)
	w2.objects.o10.active = false
	a2.senses.sample(w2, a2.position, Vector3.FORWARD, a2.memory, a2.body.needs, 0)
	a2.utility.choose(a2)
	check(not a2.memory.objects.o10.present and score_of(a2.utility.ranked, "o10", "eat") == 0, "Observing an empty remembered food location prevents repeated futile eating")
	w2.objects.o10.active = true
	w2.objects.o10.stock = 1.0
	w2.objects.o10.cues.food = 1.0
	a2.senses.sample(w2, a2.position, Vector3.FORWARD, a2.memory, a2.body.needs, 0)
	check(a2.memory.objects.o10.present and a2.memory.objects.o10.cues.food > 0, "A returned edible object becomes available when actually observed again")
	w2.emit_event("o8", w2.objects.o8.position, 1, "Plötsligt ljud")
	a2.step(0.05)
	check(a2.current.action == "flee", "Sudden sound triggers safety response")
	var test_path = ProjectSettings.globalize_path("res://data/test-individual.json")
	var p = Persistence.new(test_path)
	check(p.save(a, w), "Saves individual")
	check(p.save(a, w), "Atomically replaces save and makes backup")
	var w3 = World.new()
	var a3 = Agent.new(w3, 99)
	check(p.load_into(a3, w3), "Loads saved individual")
	check(a3.individual_id == a.individual_id and a3.memory.total_episodes == a.memory.total_episodes, "Identity and episodic memory persist")
	check(is_equal_approx(a3.relationship.trust, a.relationship.trust) and is_equal_approx(a3.learning.flight.best_height, a.learning.flight.best_height), "Relationship and motor learning persist")
	check(a3.learning.models.size() == a.learning.models.size() and is_equal_approx(w3.now, w.now), "Knowledge and world state persist")
	var contexts_match = a3.learning.contexts.size() == a.learning.contexts.size()
	for context in a.learning.contexts:
		var original = a.learning.contexts[context]
		var restored = a3.learning.contexts.get(context, {})
		contexts_match = contexts_match and original.count == restored.get("count", -1) and original.outcome == restored.get("outcome", "")
		for effect in original.effects:
			contexts_match = contexts_match and is_equal_approx(float(original.effects[effect]), float(restored.get("effects", {}).get(effect, -99)))
	check(contexts_match and is_equal_approx(w3.experiment_wait(), w.experiment_wait()), "Lamp learning and remaining experiment cooldown survive restart")
	var corrupt = FileAccess.open(test_path, FileAccess.WRITE)
	corrupt.store_string("interrupted write")
	corrupt.close()
	check(p.load_into(a3, w3) and p.recovered, "Recovers valid backup after corrupt primary")
	test_places(a)
	test_food()
	test_neural_shadow_contract()
	test_neural_control_contract()
	report = {"checks": checks, "simulated_seconds": 1800, "experiment_interval_seconds": w.EXPERIMENT_INTERVAL, "actions": counts, "areas_visited": visited.keys(), "decisions": a.decision_count, "walked_meters": a.distance_walked, "peak_hunger": max_hunger, "peak_thirst": max_thirst, "flight": a.learning.flight, "learned_models": a.learning.models.size(), "foraging": a.learning.model("o13", "scratch"), "lit_button": a.learning.model("o5", "peck", "lamp_lit"), "dark_button": a.learning.model("o5", "peck", "lamp_dark"), "episodes_total": a.memory.total_episodes, "failures": failures}
	var f = FileAccess.open("res://data/test-report.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(report, "\t"))
	f.close()
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func test_neural_shadow_contract() -> void:
	var w = World.new()
	var a = Agent.new(w, 404)
	check(a.action_family("flee") == "FLEE" and a.action_family("drink") == "DRINK" and a.action_family("eat") == "EAT", "Neural shadow maps urgent utility actions into stable action families")
	check(a.action_family("rest") == "REST" and a.action_family("perch") == "REST" and a.action_family("social") == "SOCIAL" and a.action_family("preen") == "CARE", "Neural shadow groups rest, social and care motor variants without choosing targets")
	check(a.action_family("inspect") == "MANIPULATE" and a.action_family("peck") == "MANIPULATE" and a.action_family("wander") == "EXPLORE", "Neural shadow separates object manipulation from exploration")
	a.body.physiology.state.hydration = 0.24
	a.body.physiology.state.metabolic_energy = 0.40
	a.body.physiology.state.stomach_fill = 0.08
	a.body.update_drives()
	a.position = Vector3(-2.0, 0.0, 1.1)
	a.heading = Vector3.LEFT
	a.senses.sample(w, a.position, a.heading, a.memory, a.body.needs, a.age)
	var neural = a.neural_inputs()
	var required = ["hunger", "thirst", "rest", "explore", "social", "safety", "comfort", "food", "water", "person", "rest_site", "care_site", "novelty", "manipulable", "motion", "open_space"]
	var contract_ok = true
	for key in required:
		contract_ok = contract_ok and neural.has(key) and float(neural[key]) >= 0.0 and float(neural[key]) <= 1.0
	check(contract_ok and neural.size() == required.size(), "Neural shadow exposes exactly sixteen bounded embodied/perceptual signals")
	check(float(neural.thirst) > 0.75 and float(neural.water) > 0.25, "Neural shadow independently exposes urgent thirst and perceived water")
	check(not neural.has("utility") and not neural.has("score") and not neural.has("ranked"), "Neural shadow input contract contains no utility scores")
	var bridge = NeuralBridge.new()
	check(bridge.PORT == 39393 and bridge.UPDATE_INTERVAL >= 0.1, "Neural bridge uses a local bounded-rate shadow channel")

func test_neural_control_contract() -> void:
	var w = World.new()
	var a = Agent.new(w, 405)
	a.set_neural_control(true)
	a.select_action()
	check(a.current.is_empty(), "Neural control never falls back to utility before an NB decision")
	a.accept_neural_decision({"ok": true, "selected": "EXPLORE", "request_id": 1, "age": 0.0})
	a.select_action()
	check(a.current.get("controller", "") == "neural" and a.current.action == "wander" and a.action_family(a.current.action) == "EXPLORE", "Neural EXPLORE family actuates the real agent through the motor resolver")
	var rng_before = a.rng.state
	var reference_family = a.utility_shadow_family()
	check(a.rng.state == rng_before and not reference_family.is_empty(), "Utility reference cannot perturb the neural-controlled trajectory RNG")
	a.current.clear()
	a.phase = "idle"
	a.position = Vector3(-2.0, 0.0, 1.1)
	a.heading = Vector3.LEFT
	a.senses.sample(w, a.position, a.heading, a.memory, a.body.needs, a.age)
	a.accept_neural_decision({"ok": true, "selected": "DRINK", "request_id": 2, "age": a.age})
	a.select_action()
	check(a.current.get("controller", "") == "neural" and a.current.action == "drink" and a.current.target == "o2", "Neural DRINK resolves to currently perceived water without utility ranking")
	a.current = {"action": "drink", "target": "o2", "expected": {}}
	a.phase = "act"
	a.accept_neural_decision({"ok": true, "selected": "FLEE", "request_id": 3, "age": a.age})
	check(a.current.is_empty() and a.neural_selection_ready and a.neural_selected_family == "FLEE", "Neural FLEE can interrupt an executing non-defensive motor primitive")
	a.neural_bridge_unavailable("offline")
	check(not a.neural_selection_ready, "Neural bridge failure invalidates pending control instead of enabling utility fallback")
	# Family-level decisions with valid self-directed primitives must remain executable
	# even when no matching external target is currently perceived.
	a.senses.visible = []
	for fallback in [
		{"family": "REST", "action": "rest", "target": "self"},
		{"family": "SOCIAL", "action": "call", "target": "self"},
		{"family": "CARE", "action": "preen", "target": "self"}
	]:
		a.current.clear()
		a.phase = "idle"
		a.accept_neural_decision({"ok": true, "selected": fallback.family, "request_id": 10, "age": a.age})
		a.select_action()
		check(a.current.get("controller", "") == "neural" and a.current.action == fallback.action and a.current.target == fallback.target, "Neural %s has an executable self-directed fallback" % fallback.family)
	var bridge = NeuralBridge.new()
	check(bridge.mode == "control" and bridge.UPDATE_INTERVAL >= 0.1, "Neural bridge defaults to authoritative control and retains bounded-rate sampling")

func score_of(candidates: Array, target: String, action: String) -> float:
	for candidate in candidates:
		if candidate.target == target and candidate.action == action:
			return float(candidate.score)
	return 0

func test_places(experienced) -> void:
	var w = World.new()
	var novice = Agent.new(w, 100)
	perform_attempt(novice, "perch", "o11")
	check(novice.support_id == "o11" and w.on_perch(novice.position, "o11"), "Novice jumps onto low perch and stays supported")
	var perch_save = Persistence.new(ProjectSettings.globalize_path("res://data/test-perch.json"))
	check(perch_save.save(novice, w), "Saves bird while perched")
	var restored_world = World.new()
	var restored = Agent.new(restored_world, 101)
	perch_save.load_into(restored, restored_world)
	check(restored.support_id == "o11" and restored_world.on_perch(restored.position, "o11"), "Perch support survives restart")
	perform_attempt(novice, "perch", "o6")
	check(novice.support_id.is_empty() and novice.position.y == 0 and novice.learning.model("o6", "perch").success == 0, "Flight-only roost cannot be reached by an untrained jump")
	var flyer = Agent.new(w, 102)
	flyer.learning.restore(experienced.learning.export_data())
	perform_attempt(flyer, "perch", "o6")
	check(flyer.support_id == "o6" and flyer.ascent_powered and w.on_perch(flyer.position, "o6"), "Learned wing control reaches flight-only roost by actual ascent and landing")
	flyer.body.physiology.state.hydration = 0.22
	flyer.body.physiology.state.sleep_pressure = 0.03
	flyer.body.physiology.state.physical_fatigue = 0.03
	flyer.body.update_drives()
	flyer.heading = Vector3.BACK
	flyer.senses.sample(w, flyer.position, flyer.heading, flyer.memory, flyer.body.needs, flyer.age)
	flyer.select_action()
	check(flyer.current.action == "drink" and flyer.phase == "descend", "A new need initiates descent from the high roost")
	for i in range(60 * 20):
		flyer.step(1.0 / 60)
		if flyer.body.needs.thirst < 0.7:
			break
	check(flyer.support_id.is_empty() and flyer.position.y == 0 and flyer.body.needs.thirst < 0.7, "Bird descends, walks to water and drinks at ground level")
	var bath = w.perform("dust_bath", "o7", w.objects.o7.position, Vector3.FORWARD)
	var no_bath = w.perform("dust_bath", "self", Vector3.ZERO, Vector3.FORWARD)
	check(bath.outcomes.get("feather_care", 0) > 0.4 and not no_bath.success, "Sand bath requires actual sand and physically improves feather condition")
	w.perform("scratch", "o13", w.objects.o13.position, Vector3.FORWARD)
	var forage = w.perform("scratch", "o13", w.objects.o13.position, Vector3.FORWARD)
	var bare = w.perform("scratch", "self", Vector3.ZERO, Vector3.FORWARD)
	check(forage.outcomes.get("food_ingested", 0) == 0 and forage.outcomes.get("food_access", 0) > 0 and w.objects.o10.active, "Scratching can expose food but never ingests it in the same action")
	var exposed_food = w.perform("eat", "o10", w.objects.o10.position, Vector3.FORWARD)
	check(exposed_food.outcomes.get("food_ingested", 0) > 0 and not w.objects.o10.active and bare.outcomes.get("food_ingested", 0) == 0, "Exposed forage seeds require a separate eat action")
	var covered = w.perform("rest", "o12", w.objects.o12.position, Vector3.FORWARD)
	var uncovered = w.perform("rest", "self", Vector3.ZERO, Vector3.FORWARD)
	check(covered.outcomes.rest_quality > uncovered.outcomes.rest_quality and covered.outcomes.calming > uncovered.outcomes.calming, "Shelter reports better physical rest quality and calming than bare ground")
	for id in ["o1", "o9", "o13"]:
		w.objects[id].stock = 0
	w.objects.o10.active = false
	w.tick(3600)
	check(w.objects.o1.stock == 0 and w.objects.o9.stock == 0 and w.objects.o13.stock == 0, "Waiting never replenishes ordinary food or forage reserve")
	var bowl_before_button = w.objects.o1.stock
	var forage_before_button = w.objects.o13.stock
	w.perform("peck", "o5", w.objects.o5.position, Vector3.FORWARD)
	check(w.objects.o9.stock == 1 and w.hatch_open and w.objects.o1.stock == bowl_before_button and w.objects.o13.stock == forage_before_button, "Experiment button exposes only its own reward and cannot refill survival food")
	if FileAccess.file_exists("res://data/legacy-individual.json"):
		var legacy = Persistence.new(ProjectSettings.globalize_path("res://data/legacy-individual.json"))
		var original = legacy.read_valid(legacy.path)
		var migrated_world = World.new()
		var migrated = Agent.new(migrated_world, 103)
		legacy.load_into(migrated, migrated_world)
		check(migrated.individual_id == original.agent.individual_id and migrated.memory.total_episodes == int(original.agent.memory.total_episodes), "Existing live individual and episodes migrate intact")
		check(migrated_world.objects.has("o14") and is_equal_approx(migrated_world.objects.o6.position.y, 0.95), "Old save gains new areas and flight-only perch")
		check(is_equal_approx(migrated.learning.flight.best_height, float(original.agent.learning.flight.best_height)), "Migration preserves previously learned flight")
		check(migrated_world.objects.o1.stock >= 4 and migrated_world.objects.o1.stock <= migrated_world.BOWL_CAPACITY and migrated_world.objects.o9.stock == 0 and is_equal_approx(migrated_world.experiment_wait(), 300), "Old save migrates into decoupled feeding ecology with a safe base reserve and experiment cooldown")

func test_food() -> void:
	var w = World.new()
	var initial_bowl = float(w.objects.o1.stock)
	var initial_forage = int(w.objects.o13.stock)
	check(initial_bowl > 1 and initial_forage > 0, "Baseline food and forage exist independently of the experiment apparatus")
	w.next_experiment_time = w.now
	w.tick(0)
	var first_press = w.perform("peck", "o5", w.objects.o5.position, Vector3.FORWARD)
	check(first_press.success and w.objects.o9.stock == 1 and w.hatch_open, "Ready experiment button opens hatch and exposes one small reward")
	check(is_equal_approx(float(w.objects.o1.stock), initial_bowl) and int(w.objects.o13.stock) == initial_forage, "Experiment button does not alter bowl food or forage reserve")
	check(not w.press_food_button(true).success, "Experiment cannot dispense again while reward remains")
	var reward = w.perform("eat", "o9", w.objects.o9.position, Vector3.FORWARD)
	check(reward.outcomes.get("food_ingested", 0) > 0 and w.objects.o9.stock == 0 and not w.hatch_open, "Experiment reward must be physically eaten and closes hatch when consumed")
	w.tick(299.9)
	check(not w.perform("peck", "o5", w.objects.o5.position, Vector3.FORWARD).success, "Bird cannot bypass experiment cooldown")
	var restored = World.new()
	restored.restore(w.export_data())
	check(is_equal_approx(restored.experiment_wait(), 0.1), "Partial experiment cooldown restores exactly instead of resetting")
	restored.tick(0.1001)
	check(restored.objects.o5.cues.lit == 1 and restored.objects.o9.stock == 0, "Experiment lamp becomes ready without creating food by itself")
	check(restored.press_food_button(true).success and restored.objects.o9.stock == 1 and restored.experiment_wait() > 299.99, "Ready button starts a new apparatus interval and exposes one reward")
	var before_refill = float(restored.objects.o1.stock)
	if before_refill >= restored.BOWL_CAPACITY:
		restored.objects.o1.stock = maxf(0.0, before_refill - 4.0)
		before_refill = float(restored.objects.o1.stock)
	var refill = restored.refill_food_bowl(3.0, "o8")
	check(refill.success and restored.objects.o1.stock > before_refill and restored.objects.o1.stock <= restored.BOWL_CAPACITY, "Human bowl refill is an explicit ecological action separate from the experiment")
	test_physiology()


func test_physiology() -> void:
	var Body = preload("res://scripts/cognition/homeostasis.gd")
	var quiet = Body.new()
	var active = Body.new()
	quiet.physiology.state.gut_energy = 0.0
	active.physiology.state.gut_energy = 0.0
	quiet.physiology.state.stomach_fill = 0.0
	active.physiology.state.stomach_fill = 0.0
	quiet.tick(120.0, 0.05, false, 1.0)
	active.tick(120.0, 1.0, false, 1.0)
	check(active.physiology.state.metabolic_energy < quiet.physiology.state.metabolic_energy, "Active bird consumes more metabolic energy than quiet bird over equal time")
	check(active.physiology.state.hydration < quiet.physiology.state.hydration, "Activity increases water loss instead of thirst being a clock")

	var fed = Body.new()
	fed.physiology.state.metabolic_energy = 0.34
	fed.physiology.state.stomach_fill = 0.04
	fed.physiology.state.gut_energy = 0.0
	fed.update_drives()
	var hunger_before = fed.needs.hunger
	var energy_before = float(fed.physiology.state.metabolic_energy)
	fed.apply_outcome({"food_ingested": 0.22})
	check(fed.physiology.state.stomach_fill > 0.24 and fed.needs.hunger < hunger_before, "Eating fills stomach and rapidly reduces derived food drive")
	for i in range(120):
		fed.tick(1.0, 0.05, false, 1.0)
	check(fed.physiology.state.metabolic_energy > energy_before, "Digestion later transfers ingested food into metabolic energy")

	var thirsty = Body.new()
	thirsty.physiology.state.hydration = 0.36
	thirsty.update_drives()
	var thirst_before = thirsty.needs.thirst
	thirsty.apply_outcome({"water_ingested": 0.20})
	check(thirsty.physiology.state.hydration > 0.50 and thirsty.needs.thirst < thirst_before, "Drinking changes hydration; thirst is derived from hydration state")

	var well_fed = Body.new()
	var energy_depleted = Body.new()
	well_fed.physiology.state.stomach_fill = 0.20
	energy_depleted.physiology.state.stomach_fill = 0.20
	well_fed.physiology.state.metabolic_energy = 0.76
	energy_depleted.physiology.state.metabolic_energy = 0.36
	well_fed.update_drives()
	energy_depleted.update_drives()
	check(energy_depleted.needs.hunger > well_fed.needs.hunger + 0.25, "Low usable energy amplifies hunger beyond the same stomach-fill signal")
	check(active.physiology.cumulative.metabolic_cost > quiet.physiology.cumulative.metabolic_cost and active.physiology.cumulative.water_loss > quiet.physiology.cumulative.water_loss, "Physiology records causal energy and water expenditure for calibration")

	var tired = Body.new()
	tired.physiology.state.sleep_pressure = 0.72
	tired.physiology.state.physical_fatigue = 0.55
	tired.update_drives()
	var fatigue_before = tired.needs.fatigue
	tired.tick(60.0, 0.04, true, 1.5)
	check(tired.needs.fatigue < fatigue_before and tired.physiology.state.sleep_pressure < 0.72, "Rest reduces sleep pressure and physical fatigue through physiology")

	var frightened = Body.new()
	frightened.physiology.state.acute_fear = 0.0
	frightened.physiology.state.stress_load = 0.05
	frightened.update_drives()
	frightened.add_threat(1.0)
	var safety_peak = frightened.needs.safety
	frightened.tick(12.0, 0.1, false, 1.0)
	check(safety_peak > 0.8 and frightened.needs.safety < safety_peak and frightened.physiology.state.stress_load > 0.05, "Acute fear decays faster than persistent stress load")

	var social_presence_only = Body.new()
	social_presence_only.physiology.state.social_satiation = 0.70
	for i in range(600):
		social_presence_only.observe_social_presence(0.8)
		social_presence_only.tick(1.0, 0.08, false, 1.0)
	check(social_presence_only.physiology.state.social_satiation < 0.70, "Seeing a human buffers isolation but does not itself satisfy social contact")
	var social_before_contact = float(social_presence_only.physiology.state.social_satiation)
	social_presence_only.apply_outcome({"social_contact": 0.28})
	check(social_presence_only.physiology.state.social_satiation > social_before_contact + 0.15, "Actual social contact replenishes social satiation")

	var familiar_scene = Body.new()
	familiar_scene.physiology.state.stimulation_satiation = 0.60
	for i in range(600):
		familiar_scene.observe_stimulation(0.05)
		familiar_scene.tick(1.0, 0.08, false, 1.0)
	check(familiar_scene.physiology.state.stimulation_satiation < 0.56, "Familiar low-novelty surroundings create an exploration deficit")
	var stimulation_before_info = float(familiar_scene.physiology.state.stimulation_satiation)
	familiar_scene.apply_outcome({"information_gain": 0.50})
	var stimulation_after_info = float(familiar_scene.physiology.state.stimulation_satiation)
	check(stimulation_after_info > stimulation_before_info + 0.015 and stimulation_after_info < stimulation_before_info + 0.04, "New information replenishes exploration satiation without saturating it")
	var stimulation_before_routine = stimulation_after_info
	for i in range(40):
		familiar_scene.apply_outcome({"sensory_stimulation": 0.20})
	check(is_equal_approx(float(familiar_scene.physiology.state.stimulation_satiation), stimulation_before_routine), "Routine familiar sensory throughput cannot directly refill exploration satiation")

	var short_rest = Body.new()
	short_rest.physiology.state.sleep_pressure = 0.40
	short_rest.physiology.state.physical_fatigue = 0.30
	short_rest.update_drives()
	short_rest.tick(10.0, 0.04, true, 1.25)
	check(short_rest.physiology.state.sleep_pressure > 0.36 and short_rest.physiology.state.physical_fatigue < 0.30, "Short perch rest recovers muscles without erasing sleep pressure")

	var meal = Body.new()
	meal.physiology.state.metabolic_energy = 0.76
	meal.physiology.state.stomach_fill = 0.0
	meal.physiology.state.gut_energy = 0.0
	meal.apply_outcome({"food_ingested": 0.22})
	for i in range(180):
		meal.tick(1.0, 0.20, false, 1.0)
	check(meal.physiology.state.metabolic_energy < 0.90, "One small meal cannot create an unrealistic rapid metabolic-energy surplus")
	check(float(meal.physiology.cumulative.metabolic_absorbed) < float(meal.physiology.cumulative.digestible_to_gut), "Metabolic absorption preserves an explicit conversion loss")

func perform_attempt(agent, action: String, target: String) -> void:
	agent.position = agent.world.objects[target].position + Vector3(0, 0, 0.55)
	agent.position.y = 0
	agent.support_id = ""
	agent.body.physiology.state.acute_fear = 0.0
	agent.body.physiology.state.stress_load = 0.0
	agent.body.update_drives()
	agent.target_position = agent.world.objects[target].position
	agent.current = {"action": action, "target": target, "expected": {}}
	var before = agent.memory.total_episodes
	agent.begin_act()
	for i in range(60 * 16):
		agent.step(1.0 / 60)
		if agent.memory.total_episodes > before:
			break
