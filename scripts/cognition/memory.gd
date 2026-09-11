extends RefCounted
## Object identities are opaque. Knowledge is added only by sensory experience.
const MAX_EPISODES = 160
var objects = {}
var episodes = []
var working = []
var total_episodes = 0

func observe(observation: Dictionary, now: float) -> void:
	var id = observation.id
	if not objects.has(id):
		objects[id] = {"label": observation.label, "first_seen": now, "last_seen": now, "visits": 0, "observations": 0, "facts": {}, "position": observation.position, "cues": observation.cues.duplicate(true)}
	var record = objects[id]
	if not record.has("observations"):
		# Migration for v0.3.1 and older memories: prior action visits imply some familiarity.
		record.observations = maxi(0, int(record.get("visits", 0)) * 8)
	record.observations = int(record.observations) + 1
	record.present = true
	record.label = observation.label
	record.last_seen = now
	record.position = observation.position
	record.cues = observation.cues.duplicate(true)
	remember_working(id, "ser", observation.label, now)

func mark_absent(id: String, now: float) -> void:
	# Keep episodes and learned facts, but stop trusting an empty remembered location.
	objects[id].present = false
	objects[id].cues = {}
	remember_working(id, "ser", "Platsen där " + objects[id].label.to_lower() + " fanns är tom.", now)

func remember_working(id: String, kind: String, text: String, now: float) -> void:
	for item in working:
		if item.id == id and item.kind == kind:
			item.time = now
			item.text = text
			return
	working.append({"id": id, "kind": kind, "text": text, "time": now})
	if working.size() > 12:
		working.pop_front()

func decay(now: float) -> void:
	working = working.filter(func(item): return now - float(item.time) < 14.0)

func add_episode(event: Dictionary) -> void:
	total_episodes += 1
	event["sequence"] = total_episodes
	episodes.append(event.duplicate(true))
	if episodes.size() > MAX_EPISODES:
		episodes.pop_front()
	var id = event.get("target", "")
	if objects.has(id):
		objects[id].visits += 1
		objects[id].facts[event.action] = {"outcome": event.outcome, "reward": event.reward, "time": event.time}

func relevant(target: String, count_limit: int = 4) -> Array:
	var result = []
	for i in range(episodes.size() - 1, -1, -1):
		if target.is_empty() or episodes[i].target == target:
			result.append(episodes[i])
		if result.size() >= count_limit:
			break
	return result

func export_data() -> Dictionary:
	return {"objects": objects, "episodes": episodes, "total_episodes": total_episodes}

func restore(data: Dictionary) -> void:
	objects = data.get("objects", {}).duplicate(true)
	for id in objects:
		if not objects[id].has("observations"):
			objects[id].observations = maxi(0, int(objects[id].get("visits", 0)) * 8)
	episodes = data.get("episodes", []).duplicate(true).slice(-MAX_EPISODES)
	total_episodes = int(data.get("total_episodes", episodes.size()))
	working.clear()
