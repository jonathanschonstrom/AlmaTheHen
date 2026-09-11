extends RefCounted
## Small deterministic world. Hidden physical properties never enter Perception.
const LAYOUT_VERSION = 4
const EXPERIMENT_INTERVAL = 300.0
# Compatibility alias: retained for older diagnostics only.
const FOOD_INTERVAL = EXPERIMENT_INTERVAL
const BOWL_CAPACITY = 12.0
const FORAGE_RESERVE = 8
const WALK_LIMIT = 5.55
const OBJECT_LIMIT = 5.35
var objects = {}
var areas = {}
var events = []
var now = 0.0
var hatch_open = false
var next_experiment_time = EXPERIMENT_INTERVAL
var last_event = "En ny dag i rummet."
var event_sequence = 0

func _init() -> void:
	areas = {
		"shelter": {"name": "Skyddad vila", "position": Vector3(-3.1, 0, -3.35), "radius": 1.85, "color": Color("b7ae87")},
		"feeding": {"name": "Mat & vatten", "position": Vector3(-4.0, 0, 0.85), "radius": 1.55, "color": Color("c8b997")},
		"dust": {"name": "Sandbad", "position": Vector3(3.25, 0, -3.8), "radius": 1.25, "color": Color("ddc596")},
		"forage": {"name": "Sprättjord", "position": Vector3(3.3, 0, 3.8), "radius": 1.45, "color": Color("8e8260")},
		"practice": {"name": "Fri vingyta", "position": Vector3(0.9, 0, -2.5), "radius": 1.4, "color": Color("b7c39a")},
		"objects": {"name": "Undersök & prova", "position": Vector3(0.1, 0, 2.4), "radius": 1.6, "color": Color("c8b591")}
	}
	add("o1", "Ljus skål med frön", "food", Vector3(-4.0, 0, 0), {"food": 1.0}, 0.4)
	add("o2", "Blänkande blå skål", "water", Vector3(-4.0, 0, 1.7), {"water": 1.0}, 0.38)
	add("o3", "Röd rund sak", "ball", Vector3(-0.2, 0, 2.7), {"round": 1.0}, 0.25)
	add("o4", "Brun låda", "box", Vector3(0.8, 0, 1.4), {"height": 0.55}, 0.48)
	add("o5", "Liten gul yta med lampa", "button", Vector3(-3.0, 0, 0.6), {"shiny": 0.8, "lit": 0.0}, 0.22)
	add("o6", "Hög träpinne", "perch", Vector3(-3.9, 0.95, -4.45), {"height": 1.015, "rail": 1.0}, 0.35)
	add("o7", "Fin mjuk sand", "dust", areas.dust.position, {"ground": 1.0, "loose": 1.0, "fine": 1.0}, 1.25)
	add("o8", "Människa", "human", Vector3(-3.0, 0, 3.6), {"person": 1.0}, 0.33)
	add("o9", "Trälucka", "cache", Vector3(-2.65, 0, -0.5), {"food": 0.0}, 0.42)
	objects.o9.stock = 0.0
	objects.o1.stock = BOWL_CAPACITY
	add("o10", "Små frön", "treat", Vector3(-2, 0, 2.5), {"food": 0.0}, 0.12)
	objects.o10.active = false
	objects.o10.stock = 0.0
	add("o11", "Låg träpinne", "perch", Vector3(-2.45, 0.22, -2.45), {"height": 0.285, "rail": 1.0}, 0.35)
	add("o12", "Mjuk ströbädd under skydd", "nest", Vector3(-3.1, 0, -3.35), {"soft": 1.0, "cover": 1.0}, 0.8)
	add("o13", "Lös jord med strån", "forage", areas.forage.position, {"ground": 1.0, "loose": 1.0}, 1.45)
	objects.o13.stock = FORAGE_RESERVE
	objects.o13.searches = 0
	add("o14", "Fri öppen mark", "practice", areas.practice.position, {"open": 1.0}, 1.4)

func add(id: String, label: String, kind: String, position: Vector3, cues: Dictionary, radius: float) -> void:
	objects[id] = {"id": id, "label": label, "kind": kind, "position": position, "cues": cues, "radius": radius, "active": true, "velocity": Vector3.ZERO, "stock": 4.0, "donor": ""}

func tick(dt: float) -> void:
	now += dt
	events = events.filter(func(event): return now - float(event.time) < 2.0)
	for id in objects:
		var obj = objects[id]
		if obj.velocity.length() > 0.01:
			obj.position += obj.velocity * dt
			obj.velocity *= exp(-dt * 2.8)
			for axis in [0, 2]:
				if absf(obj.position[axis]) > OBJECT_LIMIT:
					obj.position[axis] = clampf(obj.position[axis], -OBJECT_LIMIT, OBJECT_LIMIT)
					obj.velocity[axis] *= -0.5
	# The yellow button is a cognitive experiment, not a survival feeder.
	objects.o5.cues.lit = 1.0 if experiment_wait() <= 0 and objects.o9.stock <= 0 else 0.0

func experiment_wait() -> float:
	return maxf(0.0, next_experiment_time - now)

func food_wait() -> float:
	# Compatibility alias for old UI/tests. Means apparatus cooldown in v0.3.1+.
	return experiment_wait()

func refill_food_bowl(amount: float = 4.0, donor: String = "o8") -> Dictionary:
	if donor == "o8" and (not objects.has("o8") or not objects.o8.active):
		return {"success": false, "outcome": "Ingen människa är i rummet för att fylla skålen."}
	var before = float(objects.o1.stock)
	objects.o1.stock = minf(BOWL_CAPACITY, before + maxf(0.0, amount))
	objects.o1.cues.food = 1.0 if objects.o1.stock > 0 else 0.0
	objects.o1.donor = donor
	var added = float(objects.o1.stock) - before
	if added <= 0:
		return {"success": false, "outcome": "Fröskålen är redan fylld."}
	emit_event(donor, objects.o1.position, 0.20, "Människan fyllde på fröskålen.")
	return {"success": true, "outcome": "Fröskålen fick %.0f nya portioner." % added}

func area_at(at: Vector3) -> String:
	for id in areas:
		if flat_distance(at, areas[id].position) <= float(areas[id].radius):
			return id
	return ""

func area_name(at: Vector3) -> String:
	return areas.get(area_at(at), {}).get("name", "Mellan områdena")

func support_height(id: String) -> float:
	return float(objects[id].position.y) + 0.065

func is_perch(id: String) -> bool:
	return objects.has(id) and objects[id].kind == "perch"

func on_perch(at: Vector3, id: String) -> bool:
	return is_perch(id) and flat_distance(at, objects[id].position) < 0.3 and absf(at.y - support_height(id)) < 0.025

func practice_clear(at: Vector3) -> bool:
	return absf(at.x) < WALK_LIMIT - 1.1 and absf(at.z) < WALK_LIMIT - 1.1 and flat_distance(at, objects.o4.position) > 1.3 and area_at(at) != "shelter"

func rest_quality(at: Vector3, support: String = "") -> float:
	return (1.5 if area_at(at) == "shelter" else 1.0) + (0.25 if on_perch(at, support) else 0.0)

static func flat_distance(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x, a.z).distance_to(Vector2(b.x, b.z))

func emit_event(source: String, position: Vector3, intensity: float, text: String) -> void:
	event_sequence += 1
	events.append({"sequence": event_sequence, "source": source, "position": position, "intensity": intensity, "text": text, "time": now})
	last_event = text

func occluded(origin: Vector3, target: Vector3, target_id: String) -> bool:
	if target_id == "o4" or origin.y > 0.5 or target.y > 0.5:
		return false
	var a = Vector2(origin.x, origin.z)
	var b = Vector2(target.x, target.z)
	var c = Vector2(objects.o4.position.x, objects.o4.position.z)
	var ab = b - a
	var t = clampf((c - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0, 1)
	return t > 0.02 and t < 0.97 and (a + ab * t).distance_to(c) < 0.4

func move_ground(origin: Vector3, desired: Vector3, dt: float, target_id: String) -> Vector3:
	var velocity = desired
	# Obstacle avoidance for the box; other items are low or open below the perch.
	var away = origin - objects.o4.position
	away.y = 0
	if away.length() < 1.05 and target_id != "o4":
		velocity += away.normalized() * (1.05 - away.length()) * 3.0
	var result = origin + velocity * dt
	var delta = result - objects.o4.position
	delta.y = 0
	if delta.length() < 0.68 and origin.y < 0.55:
		if delta.length() < 0.001:
			delta = Vector3.RIGHT
		var safe = objects.o4.position + delta.normalized() * 0.68
		result.x = safe.x
		result.z = safe.z
	result.x = clampf(result.x, -WALK_LIMIT, WALK_LIMIT)
	result.z = clampf(result.z, -WALK_LIMIT, WALK_LIMIT)
	return result

func perform(action: String, id: String, body_position: Vector3, heading: Vector3) -> Dictionary:
	# The world reports physical/sensory outcomes. It never edits psychological need bars.
	var result = {"outcomes": {}, "success": true, "outcome": "Inget särskilt hände.", "donor": ""}
	var obj = objects.get(id, {})
	var area = area_at(body_position)
	match action:
		"rest":
			result.outcomes = {"rest_quality": rest_quality(body_position), "calming": 0.025 if area == "shelter" else 0.008}
			result.outcome = "Skyddet och ströbädden gav ostörd vila." if area == "shelter" else "Vilade en stund på marken."
		"perch":
			if not on_perch(body_position, id):
				return {"outcomes": {"physical_effort": 0.025}, "success": false, "outcome": "Nådde inte pinnen. Behöver ett högre och bättre riktat lyft.", "donor": ""}
			result.outcomes = {"rest_quality": 1.25, "calming": 0.045, "sensory_stimulation": 0.035}
			result.outcome = "Landade på pinnen, höll balansen och vilade med bättre utsikt."
		"dust_bath":
			if area == "dust":
				result.outcomes = {"feather_care": 0.58, "sensory_stimulation": 0.16, "calming": 0.025}
				result.outcome = "Den fina sanden kom in mellan fjädrarna. Fjäderdräkten känns bättre."
			else:
				result.success = false
				result.outcome = "Underlaget fungerade dåligt för sandbad."
		"preen":
			result.outcomes = {"feather_care": 0.38, "sensory_stimulation": 0.055}
			result.outcome = "Fjädrarna ligger bättre."
		"scratch":
			result.outcomes = {"sensory_stimulation": 0.025, "physical_effort": 0.012}
			result.outcome = "Det fasta golvet gav inget att gräva i."
			if area == "forage":
				objects.o13.searches += 1
				result.outcomes.sensory_stimulation = 0.10
				result.outcome = "Sprättade undan jord och strån."
				# Scratching exposes a separate food object. Eating requires a later decision.
				if int(objects.o13.searches) % 2 == 0 and objects.o13.stock > 0 and not objects.o10.active:
					objects.o13.stock -= 1
					objects.o10.active = true
					objects.o10.stock = 1.0
					objects.o10.cues.food = 1.0
					objects.o10.donor = ""
					var side = -1.0 if int(objects.o13.searches) % 4 == 0 else 1.0
					objects.o10.position = body_position + Vector3(0.22 * side, 0.0, 0.16)
					result.outcomes.information_gain = 0.12
					result.outcomes.food_access = 0.22
					result.outcome = "Sprättandet blottade några små frön i jorden."
			elif area == "dust":
				result.outcomes = {"sensory_stimulation": 0.08, "feather_care": 0.04, "physical_effort": 0.010}
				result.outcome = "Sanden är lös och fin. Den går att sprätta i."
		"look":
			result.outcomes = {"sensory_stimulation": 0.025}
			result.outcome = "Såg sig omkring."
		"wander":
			result.outcomes = {"sensory_stimulation": 0.10, "physical_effort": 0.010}
			result.outcome = "Undersökte en annan del av rummet."
		"flee":
			result.outcomes = {"threat_distance_gain": 0.36, "physical_effort": 0.035}
			result.outcome = "Större avstånd kändes tryggare."
		"call":
			result.outcomes = {"social_expression": 0.06, "sensory_stimulation": 0.015}
			result.outcome = "Gav ifrån sig ett kontaktläte."
			emit_event("bird", body_position, 0.2, "Ett mjukt kluckande.")
		"inspect":
			result.outcomes = {"information_gain": 0.13}
			result.outcome = "Tittade nära och kände på ytan."
		"social":
			if not obj.is_empty() and obj.active:
				result.outcomes = {"social_contact": 0.28, "calming": 0.06, "sensory_stimulation": 0.04}
				result.outcome = "Människan stod lugnt kvar."
				result.donor = id
			else:
				result.success = false
				result.outcome = "Människan var inte kvar."
		"eat", "drink", "peck", "push", "bite", "hop":
			if obj.is_empty() or not obj.active:
				result.success = false
				result.outcome = "Föremålet fanns inte kvar."
				return result
			match action:
				"eat":
					if obj.kind in ["food", "cache", "treat"] and obj.stock > 0 and (obj.kind != "cache" or hatch_open):
						obj.stock -= 1
						var portion = 0.22
						if obj.kind in ["treat", "cache"]:
							portion = 0.11
						result.outcomes = {"food_ingested": portion, "sensory_stimulation": 0.025}
						result.outcome = "Fröna gick att äta. Magen fylldes lite."
						result.donor = obj.donor
						if obj.stock <= 0:
							obj.cues.food = 0.0
							if obj.kind == "cache":
								hatch_open = false
							if obj.kind == "treat":
								obj.active = false
					else:
						result.success = false
						result.outcome = "Här fanns inget att äta just nu."
				"drink":
					if obj.kind == "water":
						result.outcomes = {"water_ingested": 0.20}
						result.outcome = "Vatten kom in i kroppen."
					else:
						result.success = false
				"peck":
					if obj.kind == "button":
						var pressed = press_food_button(false)
						result.success = pressed.success
						result.outcomes = {"food_access": 0.6, "information_gain": 0.18} if pressed.success else {"sensory_stimulation": 0.01}
						result.outcome = pressed.outcome
					elif obj.kind == "ball":
						obj.velocity = heading * 1.6
						result.outcomes = {"object_motion": 0.50, "information_gain": 0.15, "physical_effort": 0.008}
						result.outcome = "Den runda saken rullade efter näbbkontakten."
					else:
						result.outcomes = {"sensory_stimulation": 0.03, "physical_effort": 0.004}
						result.outcome = "Ytan kändes fast mot näbben."
				"push", "bite":
					if obj.kind in ["ball", "box"]:
						obj.velocity = heading * (1.8 if obj.kind == "ball" else 0.35) * (1.0 if action == "push" else -0.6)
						result.outcomes = {"object_motion": 0.42, "information_gain": 0.13, "physical_effort": 0.025}
						result.outcome = "Föremålet gick att knuffa." if action == "push" else "Näbben fick grepp. Föremålet flyttades lite."
					else:
						result.success = false
						result.outcome = "Föremålet gick inte att flytta."
				"hop":
					result.outcomes = {"sensory_stimulation": 0.08, "physical_effort": 0.035}
					result.success = float(obj.cues.get("height", 0)) <= 0.25
					result.outcome = "Ett kort skutt från marken." if result.success else "Skuttet räckte inte upp till kanten."
	last_event = result.outcome
	return result

func press_food_button(by_user: bool = false) -> Dictionary:
	# Separate cognitive apparatus: button -> hatch -> small reward. It never refills baseline food.
	if experiment_wait() > 0:
		return {"success": false, "outcome": "Knappen klickade men lampan var mörk. Luckan öppnades inte."}
	if objects.o9.stock > 0 or hatch_open:
		return {"success": false, "outcome": "Luckan är redan öppen och belöningen finns kvar."}
	hatch_open = true
	objects.o9.stock = 1.0
	objects.o9.cues.food = 1.0
	objects.o9.donor = "o8" if by_user else ""
	next_experiment_time = now + EXPERIMENT_INTERVAL
	objects.o5.cues.lit = 0.0
	emit_event("o8" if by_user else "o5", objects.o5.position, 0.3, "Klick. Luckan öppnades och ett litet frö blev tillgängligt.")
	return {"success": true, "outcome": "Lampan lyste. Pickandet öppnade luckan och gjorde ett litet frö tillgängligt."}

func export_data() -> Dictionary:
	var saved = {}
	for id in objects:
		var obj = objects[id].duplicate(true)
		obj.position = [obj.position.x, obj.position.y, obj.position.z]
		obj.velocity = [obj.velocity.x, obj.velocity.y, obj.velocity.z]
		saved[id] = obj
	return {"layout_version": LAYOUT_VERSION, "objects": saved, "now": now, "hatch_open": hatch_open, "next_experiment_time": next_experiment_time, "event_sequence": event_sequence}

func restore(data: Dictionary) -> void:
	now = float(data.get("now", 0))
	hatch_open = bool(data.get("hatch_open", false))
	next_experiment_time = float(data.get("next_experiment_time", data.get("next_food_time", now + EXPERIMENT_INTERVAL)))
	event_sequence = int(data.get("event_sequence", 0))
	for id in data.get("objects", {}):
		if not objects.has(id):
			continue
		var obj = data.objects[id].duplicate(true)
		if int(data.get("layout_version", 1)) < 2:
			# Upgrade physical layout without discarding the individual's experiences.
			for key in ["stock", "active", "donor"]:
				if obj.has(key):
					objects[id][key] = obj[key]
			if id in ["o1", "o9", "o10"]:
				objects[id].cues.food = float(obj.cues.get("food", 0))
			continue
		obj.position = Vector3(float(obj.position[0]), float(obj.position[1]), float(obj.position[2]))
		obj.velocity = Vector3.ZERO
		objects[id] = obj
	if int(data.get("layout_version", 1)) < 3:
		objects.o9.stock = 0
		objects.o9.cues.food = 0
		objects.o10.active = false
	if int(data.get("layout_version", 1)) < 4:
		# v0.3.1 decouples ordinary feeding, foraging and the button experiment.
		objects.o1.stock = clampf(maxf(float(objects.o1.stock), 4.0), 0.0, BOWL_CAPACITY)
		objects.o1.cues.food = 1.0 if objects.o1.stock > 0 else 0.0
		objects.o13.stock = maxi(int(objects.o13.stock), FORAGE_RESERVE)
		objects.o9.stock = 0.0
		objects.o9.cues.food = 0.0
		hatch_open = false
		objects.o10.active = false
		objects.o10.stock = 0.0
		objects.o10.cues.food = 0.0
		next_experiment_time = now + EXPERIMENT_INTERVAL
	objects.o5.cues.lit = 1.0 if experiment_wait() <= 0 and objects.o9.stock <= 0 else 0.0
