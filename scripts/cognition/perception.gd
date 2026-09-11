extends RefCounted
## 250-degree visual field, short-range scent, contact, hearing and occlusion.
var visible = []
var focus = ""
var focus_score = 0.0
var stimulation = 0.0

func sample(world, body_position: Vector3, heading: Vector3, memory, needs: Dictionary, now: float) -> void:
	visible.clear()
	focus_score = -1.0
	focus = ""
	stimulation = 0.0
	for id in world.objects:
		var obj = world.objects[id]
		if not obj.active:
			continue
		var delta = obj.position - body_position
		delta.y = 0
		var distance = delta.length()
		var angle_ok = distance < 1.1 or heading.dot(delta.normalized()) > cos(deg_to_rad(125.0))
		var sight_range = 6.6 + minf(2.0, body_position.y * 2.0)
		var can_see = distance < sight_range and angle_ok and not world.occluded(body_position, obj.position, id)
		var scent = obj.cues.get("food", 0.0) > 0 and distance < 2.8
		if not can_see and not scent:
			continue
		var cues = obj.cues.duplicate(true)
		if not can_see:
			cues = {"food": cues.get("food", 0.0)}
		var observation = {"id": id, "label": obj.label, "position": [obj.position.x, obj.position.y, obj.position.z], "cues": cues, "distance": distance, "moving": obj.velocity.length() > 0.1}
		visible.append(observation)
		memory.observe(observation, now)
		# Perceptual novelty habituates from repeated observation even if the bird never acts on
		# the object. Action visits remain a separate cognitive familiarity signal.
		var observations = float(memory.objects[id].get("observations", 1))
		var novelty = 1.0 / (1.0 + observations * 0.035 + float(memory.objects[id].visits) * 0.70)
		var proximity_interest = clampf(1.0 - distance / maxf(sight_range, 0.001), 0.0, 1.0) * 0.05
		stimulation = maxf(stimulation, clampf(novelty * 0.82 + (0.18 if observation.moving else 0.0) + proximity_interest, 0.0, 1.0))
		var salience = novelty * 0.4 + (0.22 if observation.moving else 0.0) + float(cues.get("food", 0)) * needs.hunger + float(cues.get("water", 0)) * needs.thirst + float(cues.get("person", 0)) * needs.social * 0.6 - distance * 0.045
		if salience > focus_score:
			focus_score = salience
			focus = id
	for id in memory.objects:
		if sees(id) or not memory.objects[id].get("present", true):
			continue
		var remembered = memory.objects[id].position
		var location = Vector3(float(remembered[0]), float(remembered[1]), float(remembered[2]))
		if world.flat_distance(body_position, location) < 1.1 and not world.occluded(body_position, location, id):
			memory.mark_absent(id, now)
	for sound in world.events:
		if now - float(sound.time) < 1.0 and body_position.distance_to(sound.position) < 8.0:
			# Sound can be salient without being treated as sustained cognitive enrichment.
			stimulation = maxf(stimulation, clampf(float(sound.intensity) * 0.55, 0.0, 1.0))
			memory.remember_working(sound.source, "hör", sound.text, now)
			if sound.intensity > 0.7:
				focus = sound.source
				focus_score = 2.0
	memory.decay(now)

func sees(id: String) -> bool:
	for item in visible:
		if item.id == id:
			return true
	return false
