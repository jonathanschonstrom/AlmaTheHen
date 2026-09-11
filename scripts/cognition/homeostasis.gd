extends RefCounted
## Compatibility facade around embodied physiology.
## `needs` remains available to perception/utility, but every value is derived from body state.
const Physiology = preload("res://scripts/body/physiology.gd")

var physiology = Physiology.new()
var needs = {"hunger": 0.0, "thirst": 0.0, "fatigue": 0.0, "safety": 0.0, "social": 0.0, "boredom": 0.0, "comfort": 0.0}
var emotion = "Nyfiken"
var arousal = 0.3
var valence = 0.3
var frustration = 0.0

func _init() -> void:
	update_drives()

func tick(dt: float, activity: float = 0.15, resting: bool = false, rest_quality: float = 1.0) -> void:
	physiology.tick(dt, activity, resting, rest_quality)
	frustration = maxf(0.0, frustration - dt * 0.008)
	update_drives()

func apply_outcome(outcome: Dictionary) -> void:
	physiology.apply_outcome(outcome)
	update_drives()

func add_threat(intensity: float) -> void:
	physiology.add_threat(intensity)
	update_drives()

func observe_stimulation(value: float) -> void:
	physiology.observe_stimulation(value)

func observe_social_presence(value: float) -> void:
	physiology.observe_social_presence(value)

func drive_effects(before: Dictionary) -> Dictionary:
	var effects = {}
	for key in needs:
		var change = float(before.get(key, needs[key])) - float(needs[key])
		if absf(change) > 0.0005:
			effects[key] = change
	return effects

func homeostatic_error() -> float:
	return physiology.homeostatic_error()

func update_drives() -> void:
	var s = physiology.state
	# Drives are nonlinear readouts of body state, not timers. Small deviations around the
	# set point stay quiet; genuine deficits increasingly dominate action selection.
	var energy_deficit = physiology.energy_deficit_signal()
	var gastric_deficit = physiology.gastric_deficit_signal()
	needs.hunger = clampf(pow(energy_deficit, 1.08) * 0.68 + pow(gastric_deficit, 1.28) * 0.32, 0.0, 1.0)
	var hydration_deficit = physiology.hydration_deficit_signal()
	needs.thirst = clampf(pow(hydration_deficit, 0.86), 0.0, 1.0)
	needs.fatigue = clampf(float(s.sleep_pressure) * 0.62 + float(s.physical_fatigue) * 0.50, 0.0, 1.0)
	needs.safety = clampf(maxf(float(s.acute_fear), float(s.stress_load) * 0.58), 0.0, 1.0)
	needs.social = clampf(1.0 - float(s.social_satiation), 0.0, 1.0)
	needs.boredom = clampf(1.0 - float(s.stimulation_satiation), 0.0, 1.0)
	needs.comfort = clampf(1.0 - float(s.feather_condition), 0.0, 1.0)
	update_emotion()

func update_emotion() -> void:
	arousal = clampf(needs.safety * 0.82 + needs.boredom * 0.24 + needs.hunger * 0.12 + physiology.state.physical_fatigue * 0.12, 0, 1)
	valence = clampf(0.82 - needs.safety - frustration - (needs.hunger + needs.thirst + needs.fatigue) * 0.22 - physiology.state.stress_load * 0.18, -1, 1)
	if needs.safety > 0.42:
		emotion = "Rädd"
	elif frustration > 0.34:
		emotion = "Irriterad"
	elif needs.fatigue > 0.57:
		emotion = "Trött"
	elif needs.boredom > 0.32:
		emotion = "Nyfiken"
	elif valence > 0.57:
		emotion = "Nöjd"
	else:
		emotion = "Lugn"

func export_data() -> Dictionary:
	return {
		"physiology": physiology.export_data(),
		"needs": needs.duplicate(true),
		"frustration": frustration
	}

func restore(data: Dictionary, legacy_needs: Dictionary = {}) -> void:
	if data.get("physiology") is Dictionary:
		physiology.restore(data.physiology)
	elif not legacy_needs.is_empty():
		physiology.restore_from_legacy_needs(legacy_needs)
	elif data.get("needs") is Dictionary:
		physiology.restore_from_legacy_needs(data.needs)
	frustration = float(data.get("frustration", frustration))
	update_drives()

# Transitional adapter for any older call site. It converts deficit relief into body events.
func apply(effects: Dictionary) -> void:
	var outcome = {}
	if effects.has("hunger") and float(effects.hunger) > 0:
		outcome.food_ingested = float(effects.hunger)
	if effects.has("thirst") and float(effects.thirst) > 0:
		outcome.water_ingested = float(effects.thirst)
	if effects.has("comfort") and float(effects.comfort) > 0:
		outcome.feather_care = float(effects.comfort)
	if effects.has("boredom") and float(effects.boredom) > 0:
		outcome.sensory_stimulation = float(effects.boredom)
	if effects.has("social") and float(effects.social) > 0:
		outcome.social_contact = float(effects.social)
	if effects.has("safety"):
		if float(effects.safety) > 0:
			outcome.calming = float(effects.safety)
		elif float(effects.safety) < 0:
			add_threat(absf(float(effects.safety)))
	if effects.has("fatigue"):
		var relief = float(effects.fatigue)
		if relief > 0:
			physiology.state.sleep_pressure -= relief * 0.7
			physiology.state.physical_fatigue -= relief * 0.5
		elif relief < 0:
			outcome.physical_effort = absf(relief)
	apply_outcome(outcome)
