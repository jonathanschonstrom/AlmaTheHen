extends RefCounted
var ranked = []
const ACTION_NAMES = {"eat": "Äter", "drink": "Dricker", "rest": "Vilar", "preen": "Putsar fjädrarna", "scratch": "Sprätter", "look": "Ser sig omkring", "wander": "Strövar", "flee": "Söker avstånd", "call": "Kluckar", "inspect": "Undersöker", "social": "Söker kontakt", "peck": "Pickar", "push": "Knuffar", "bite": "Griper med näbben", "hop": "Hoppar", "wings": "Provar vingarna", "heard": "Hörde", "touch": "Beröring", "perch": "Vilar på sittpinnen", "dust_bath": "Sandbadar"}

func choose(agent) -> Dictionary:
	ranked.clear()
	var n = agent.body.needs
	var p = agent.personality
	var now = agent.age
	add(agent, "rest", "self", pow(n.fatigue, 1.5) * 2.6, "Återfå energi", "Tröttheten behöver minska.", {"fatigue": 0.3})
	add(agent, "preen", "self", n.comfort * 0.7 + 0.075 * agent.hen_share, "Vårda fjädrarna", "Fjädrarna behöver ordnas.", {"comfort": 0.38})
	if agent.support_id.is_empty():
		add(agent, "scratch", "self", n.boredom * 0.1 + 0.04 * agent.hen_share, "Undersöka marken", "Känn på marken med fötterna.", {})
	add(agent, "look", "self", 0.10 + 0.08 * n.boredom, "Orientera sig", "Se vad som finns omkring mig.", {})
	add(agent, "wander", "ground", 0.17 + 0.19 * n.boredom * p.curiosity, "Utforska rummet", "En annan plats kan ha något nytt.", {"boredom": 0.1})
	add(agent, "call", "self", n.social * 0.22 * p.sociality + 0.07 * agent.hen_share, "Söka sällskap", "Ge ett kontaktläte.", {"social": 0.06})
	var since_wings = now - float(agent.last_actions.get("wings", -30.0))
	var wing_interest = n.boredom * 0.18 + p.curiosity * 0.09 + minf(0.32, since_wings * 0.003)
	if agent.support_id.is_empty() and agent.world.practice_clear(agent.position):
		add(agent, "wings", "self", wing_interest * (1.0 - n.fatigue) * (1.0 - n.safety), "Pröva lyftkraft", "Prova ett vingslag och känn efter.", {"boredom": 0.14, "fatigue": -0.055})
	if n.safety > 0.25:
		add(agent, "flee", "safe", n.safety * 3.4, "Söka trygghet", "Det plötsliga ljudet var nära.", {"safety": 0.36})
	for id in agent.memory.objects:
		var record = agent.memory.objects[id]
		if not record.get("present", true):
			continue
		# An absent object is only a remembered location, never live omniscience.
		var cues = record.cues
		var loc = Vector3(float(record.position[0]), float(record.position[1]), float(record.position[2]))
		var distance = agent.position.distance_to(loc)
		var travel_cost = distance * 0.024
		var recency = clampf(1.0 - (now - float(record.last_seen)) / 240.0, 0.6, 1.0)
		var novelty = 1.0 / (1.0 + float(record.visits) * 0.55)
		if float(cues.get("rail", 0)) > 0:
			var perch_model = agent.learning.model(id, "perch")
			var reachable = float(cues.get("height", 0)) <= maxf(0.39, float(agent.learning.flight.best_height) * 0.97)
			var vantage = clampf(float(cues.get("height", 0)), 0, 1.5) * 0.10 * agent.hen_share
			var score = pow(n.fatigue, 1.3) * 2.9 + n.safety * 0.8 + novelty * 0.16 + vantage + float(perch_model.effects.get("safety", 0)) * 0.4 - travel_cost
			if not reachable:
				score *= 0.24
				if agent.last_perch_attempts.has(id) and float(agent.learning.flight.best_height) <= float(agent.last_perch_attempts[id]) + 0.1:
					score *= 0.1
			if agent.support_id == id:
				score += n.fatigue * 0.15
			add(agent, "perch", id, score, "Vila med uppsikt", "En upphöjd yta att prova." if perch_model.count == 0 else "Minnet säger: " + perch_model.outcome, {})
		if float(cues.get("soft", 0)) > 0 or float(cues.get("cover", 0)) > 0:
			add_place(agent, "rest", id, pow(n.fatigue, 1.3) * 2.9 + n.safety * 1.6 + novelty * 0.14 - travel_cost, "Vila under skydd")
		if float(cues.get("loose", 0)) > 0:
			# A hen's hunger motivates searching loose ground; edible results are learned.
			var untried_ground = 1.0 / (1.0 + float(agent.learning.model(id, "scratch").count) * 0.7)
			add_place(agent, "scratch", id, 0.10 + n.hunger * agent.hen_share * 0.55 * untried_ground + n.boredom * 0.28 + novelty * 0.18 - travel_cost, "Söka i underlaget" if n.hunger > 0.4 else "Undersöka underlaget")
			add_place(agent, "dust_bath", id, n.comfort * 0.9 + novelty * 0.14 + float(cues.get("fine", 0)) * 0.14 - travel_cost, "Sköta fjäderdräkten")
		if float(cues.get("open", 0)) > 0:
			add(agent, "wings", id, (wing_interest + 0.14) * (1.0 - n.fatigue) * (1.0 - n.safety) - travel_cost, "Pröva vingarna på fri mark", "Här ser det ut att finnas plats.", {"boredom": 0.14, "fatigue": -0.055})
		if float(cues.get("person", 0)) > 0:
			add(agent, "social", id, n.social * p.sociality * (0.65 + agent.relationship.trust) * recency - travel_cost, "Känna närhet", "Den bekanta människan finns där." if agent.relationship.familiarity > 0.2 else "En lugn människa. Vågar jag närma mig?", {"social": 0.28})
			continue
		if float(cues.get("food", 0)) > 0.1:
			add(agent, "eat", id, pow(n.hunger, 1.4) * 2.4 * recency - travel_cost, "Mätta hunger", "Det luktar ätbart här.", {"hunger": 0.22})
		if float(cues.get("water", 0)) > 0.1:
			add(agent, "drink", id, pow(n.thirst, 1.4) * 2.5 * recency - travel_cost, "Släcka törst", "En blänkande vattenyta.", {"thirst": 0.20})
		for action in ["inspect", "peck", "push", "bite", "hop"]:
			var model = agent.learning.model(id, action, agent.sensory_context(id))
			var unknown = 1.0 / (1.0 + float(model.count))
			var base = {"inspect": 0.13, "peck": 0.18 * agent.hen_share, "push": 0.055, "bite": 0.075 + 0.07 * (1.0 - agent.hen_share), "hop": 0.025}[action]
			base *= 0.35 + unknown * 0.65
			if action == "hop" and float(cues.get("height", 0)) <= 0:
				continue
			# Unmet hunger also motivates new experiments when familiar food is unavailable.
			var search_drive = maxf(n.boredom, n.hunger * 0.9)
			var information = p.curiosity * search_drive * (novelty * 0.28 + unknown * 0.42)
			if action in ["push", "bite", "hop"]:
				information += p.playfulness * unknown * 0.18
			if not agent.learning.skills.has(action):
				information += p.curiosity * n.boredom * 0.15
			var learned_value = 0.0
			for effect in model.effects:
				if n.has(effect):
					learned_value += float(model.effects[effect]) * float(n[effect]) * 1.4
				elif effect == "food_access":
					learned_value += float(model.effects[effect]) * n.hunger * 1.2
			var score = base + information + learned_value - travel_cost - n.safety * (1.0 - p.boldness) * novelty * 0.5
			if id == agent.senses.focus:
				score += 0.035
			score -= (1.0 - float(model.success)) * (1.0 - p.persistence) * (1.0 - unknown) * 0.08
			var reason = "Det här har jag inte provat." if model.count == 0 else "Minnet säger: " + model.outcome
			add(agent, action, id, score, "Undersöka samband", reason, {})
	ranked.sort_custom(func(a, b): return a.score > b.score)
	return ranked[0].duplicate(true)

func add_place(agent, action: String, target: String, score: float, goal: String) -> void:
	var model = agent.learning.model(target, action)
	for key in model.effects:
		if agent.body.needs.has(key):
			var weight = 5.0 if key == "hunger" else 1.4
			score += float(model.effects[key]) * float(agent.body.needs[key]) * weight
		elif key == "food_access":
			# Searching can be valuable because it exposes food even though scratching itself is not eating.
			score += float(model.effects[key]) * float(agent.body.needs.hunger) * 3.0
	var reason = "Prova hur platsen känns." if model.count == 0 else "Minnet säger: " + model.outcome
	add(agent, action, target, score, goal, reason, {})

func add(agent, action: String, target: String, score: float, goal: String, reason: String, innate: Dictionary) -> void:
	var context = agent.sensory_context(target)
	var model = agent.learning.model(target, action, context)
	var last_key = target + ":" + action
	var elapsed = agent.age - float(agent.last_actions.get(last_key, -1000.0))
	# Habituation prevents repeated neutral actions from dominating exploration.
	if elapsed < 18.0 and action not in ["eat", "drink", "rest", "flee"]:
		score *= lerpf(0.12, 1.0, elapsed / 18.0)
	if action == "wings" and agent.age - float(agent.last_actions.get("wings", -30.0)) < 20:
		score *= 0.08
	if action in ["eat", "drink"] and elapsed < 4.0:
		score *= 0.6
	var expected = model.effects.duplicate(true) if model.count > 0 else innate.duplicate(true)
	ranked.append({"action": action, "target": target, "score": maxf(0, score) + agent.rng.randf_range(0, 0.006), "goal": goal, "reason": reason, "expected": expected, "context": context, "confidence": agent.learning.confidence(target, action, context), "outcome": model.outcome if model.count > 0 else "Ännu oprövat"})
