extends RefCounted
## Embodied physiology for BirdAI v0.3.3.
## Time integrates physical processes; motivational drives are derived elsewhere from body state.
## All normalized body stores are 0..1 unless stated otherwise.

const TARGET_ENERGY = 0.76
const TARGET_HYDRATION = 0.80
const CRITICAL_ENERGY = 0.28
const CRITICAL_HYDRATION = 0.36
const COMFORTABLE_STOMACH = 0.46

var state = {
	"metabolic_energy": 0.76,
	"stomach_fill": 0.34,
	"gut_energy": 0.10,
	"hydration": 0.81,
	"sleep_pressure": 0.18,
	"physical_fatigue": 0.12,
	"acute_fear": 0.04,
	"stress_load": 0.08,
	"feather_condition": 0.88,
	"social_satiation": 0.70,
	"stimulation_satiation": 0.48,
	"body_condition": 0.90
}

var stimulation_input = 0.28 # perceptual novelty / information opportunity, not generic activity
var social_presence_input = 0.0 # presence buffers isolation but does not satisfy social contact
var last_intake = {"food": 0.0, "water": 0.0}
var cumulative = {
	"food_ingested": 0.0,
	"water_ingested": 0.0,
	"gastric_transferred": 0.0,
	"digestible_to_gut": 0.0,
	"metabolic_absorbed": 0.0,
	"metabolic_cost": 0.0,
	"water_loss": 0.0,
	"physical_effort": 0.0,
	"information_gained": 0.0,
	"social_contact": 0.0
}

func tick(dt: float, activity: float = 0.15, resting: bool = false, rest_quality: float = 1.0) -> void:
	activity = clampf(activity, 0.0, 1.4)
	rest_quality = clampf(rest_quality, 0.4, 1.8)

	# Food is not energy on contact. It moves through stomach -> gut -> usable reserve.
	# v0.3.2 preserves gastric timing but reduces digestible yield: the v0.3.1
	# telemetry showed a persistent positive energy drift despite heavy locomotion.
	var stomach_transfer = minf(float(state.stomach_fill), dt * 0.00125)
	state.stomach_fill -= stomach_transfer
	var digestible = stomach_transfer * 0.78
	state.gut_energy = minf(1.0, float(state.gut_energy) + digestible)
	var absorption = minf(float(state.gut_energy), dt * 0.00105)
	state.gut_energy -= absorption
	var absorbed_energy = absorption * 0.84
	state.metabolic_energy = minf(1.0, float(state.metabolic_energy) + absorbed_energy)
	cumulative.gastric_transferred += stomach_transfer
	cumulative.digestible_to_gut += digestible
	cumulative.metabolic_absorbed += absorbed_energy

	# Basal metabolism is always present. Locomotion and wing work add continuous cost.
	# Discrete high-effort actions add an additional cost through apply_outcome().
	var metabolic_cost = dt * (0.00027 + activity * 0.00050)
	var water_loss = dt * (0.00012 + activity * 0.00018)
	state.metabolic_energy -= metabolic_cost
	state.hydration -= water_loss
	cumulative.metabolic_cost += metabolic_cost
	cumulative.water_loss += water_loss

	# Sleep pressure and muscular fatigue are independent. Quiet wakefulness can recover
	# local muscular fatigue while sleep pressure continues to accumulate.
	if resting:
		# Brief quiet rests recover muscles quickly but only slowly discharge sleep pressure.
		# This prevents repeated ten-second perch bouts from acting like full sleep cycles.
		state.sleep_pressure -= dt * 0.00085 * rest_quality
		state.physical_fatigue -= dt * 0.0046 * rest_quality
	else:
		state.sleep_pressure += dt * (0.00024 + activity * 0.00009)
		state.physical_fatigue += dt * maxf(0.0, activity - 0.12) * 0.00058
		state.physical_fatigue -= dt * 0.00018

	# Fear is rapid; stress load is slower and can remain after the immediate threat ends.
	state.acute_fear -= dt * 0.040
	state.stress_load -= dt * 0.00055
	if float(state.acute_fear) > 0.45:
		state.stress_load += dt * 0.0014 * float(state.acute_fear)

	# Feather wear is primarily activity/environment driven, not a comfort clock.
	state.feather_condition -= dt * (0.000004 + activity * 0.000010)

	# Presence and contact are different social signals. Seeing a familiar individual can
	# buffer isolation, but only actual contact replenishes social satiation.
	var presence_buffer = clampf(social_presence_input, 0.0, 1.0)
	state.social_satiation -= dt * 0.00012 * (1.0 - presence_buffer * 0.45)

	# Stimulation satiation tracks information balance, not raw sensory throughput.
	# Familiar scenes create a slow exploration deficit. Perceptual novelty can buffer that
	# decay, while durable replenishment comes from actual information_gain events.
	var novelty = clampf(stimulation_input, 0.0, 1.0)
	state.stimulation_satiation -= dt * 0.00011 * (1.0 - novelty * 0.55)
	state.stimulation_satiation += dt * 0.00004 * novelty

	# Perceptual inputs represent the latest sampled environment and relax unless refreshed.
	stimulation_input = maxf(0.0, stimulation_input - dt * 0.18)
	social_presence_input = maxf(0.0, social_presence_input - dt * 0.35)
	clamp_state()

func apply_outcome(outcome: Dictionary) -> void:
	var food = maxf(0.0, float(outcome.get("food_ingested", 0.0)))
	if food > 0:
		state.stomach_fill = minf(1.0, float(state.stomach_fill) + food)
		# Only a trace reaches the digestive pool immediately; most energy must be digested.
		state.gut_energy = minf(1.0, float(state.gut_energy) + food * 0.02)
		last_intake.food = food
		cumulative.food_ingested += food
	var water = maxf(0.0, float(outcome.get("water_ingested", 0.0)))
	if water > 0:
		state.hydration = minf(1.0, float(state.hydration) + water)
		last_intake.water = water
		cumulative.water_ingested += water

	var effort = maxf(0.0, float(outcome.get("physical_effort", 0.0)))
	if effort > 0:
		var effort_energy_cost = effort * 0.18
		var effort_water_loss = effort * 0.06
		state.physical_fatigue += effort * 0.48
		state.metabolic_energy -= effort_energy_cost
		state.hydration -= effort_water_loss
		cumulative.physical_effort += effort
		cumulative.metabolic_cost += effort_energy_cost
		cumulative.water_loss += effort_water_loss

	var care = maxf(0.0, float(outcome.get("feather_care", 0.0)))
	if care > 0:
		state.feather_condition += care

	var sensory = maxf(0.0, float(outcome.get("sensory_stimulation", 0.0)))
	var information = maxf(0.0, float(outcome.get("information_gain", 0.0)))
	if sensory > 0:
		# Routine sensory activity is transient arousal only. Repeating a familiar sensation
		# (for example flapping the wings) must not refill exploration satiation by itself.
		stimulation_input = maxf(stimulation_input, sensory * 0.18)
	if information > 0:
		# New information replenishes stimulation, but with state-dependent diminishing returns.
		# This prevents a familiar environment from being pinned near 1.0 by many small events.
		var saturation_gate = 1.0 - float(state.stimulation_satiation) * 0.65
		state.stimulation_satiation += information * 0.07 * maxf(0.25, saturation_gate)
		stimulation_input = maxf(stimulation_input, information)
		cumulative.information_gained += information

	var social = maxf(0.0, float(outcome.get("social_contact", 0.0)))
	if social > 0:
		state.social_satiation += social * 0.75
		social_presence_input = maxf(social_presence_input, minf(1.0, social * 1.5))
		cumulative.social_contact += social

	var calming = maxf(0.0, float(outcome.get("calming", 0.0)))
	if calming > 0:
		state.acute_fear -= calming
		state.stress_load -= calming * 0.42

	var threat_relief = maxf(0.0, float(outcome.get("threat_distance_gain", 0.0)))
	if threat_relief > 0:
		state.acute_fear -= threat_relief
		state.stress_load -= threat_relief * 0.20
	clamp_state()

func add_threat(intensity: float) -> void:
	intensity = clampf(intensity, 0.0, 1.0)
	state.acute_fear = maxf(float(state.acute_fear), intensity * 0.92)
	state.stress_load = minf(1.0, float(state.stress_load) + intensity * 0.18)
	clamp_state()

func observe_stimulation(value: float) -> void:
	stimulation_input = maxf(stimulation_input, clampf(value, 0.0, 1.0))

func observe_social_presence(value: float) -> void:
	social_presence_input = maxf(social_presence_input, clampf(value, 0.0, 1.0))

func clamp_state() -> void:
	for key in state:
		state[key] = clampf(float(state[key]), 0.0, 1.0)

func energy_deficit_signal() -> float:
	return clampf((TARGET_ENERGY - float(state.metabolic_energy)) / maxf(0.001, TARGET_ENERGY - CRITICAL_ENERGY), 0.0, 1.0)

func gastric_deficit_signal() -> float:
	return clampf((COMFORTABLE_STOMACH - float(state.stomach_fill)) / COMFORTABLE_STOMACH, 0.0, 1.0)

func hydration_deficit_signal() -> float:
	return clampf((TARGET_HYDRATION - float(state.hydration)) / maxf(0.001, TARGET_HYDRATION - CRITICAL_HYDRATION), 0.0, 1.0)

func homeostatic_error() -> float:
	# Weighted deviation from viable/comfortable ranges. The nonlinear signals avoid
	# treating tiny harmless deviations as equivalent to genuine physiological deficit.
	var energy_error = energy_deficit_signal()
	var gastric_error = gastric_deficit_signal()
	var hydration_error = hydration_deficit_signal()
	return pow(energy_error, 1.25) * 1.55 + pow(gastric_error, 1.35) * 0.34 + pow(hydration_error, 1.20) * 1.75 + float(state.sleep_pressure) * 0.62 + float(state.physical_fatigue) * 0.40 + float(state.acute_fear) * 1.25 + float(state.stress_load) * 0.42 + (1.0 - float(state.feather_condition)) * 0.16

func export_data() -> Dictionary:
	return {
		"state": state.duplicate(true),
		"stimulation_input": stimulation_input,
		"social_presence_input": social_presence_input,
		"last_intake": last_intake.duplicate(true),
		"cumulative": cumulative.duplicate(true)
	}

func restore(data: Dictionary) -> void:
	if data.get("state") is Dictionary:
		for key in state:
			if data.state.has(key) and (data.state[key] is float or data.state[key] is int):
				state[key] = float(data.state[key])
	stimulation_input = float(data.get("stimulation_input", stimulation_input))
	social_presence_input = float(data.get("social_presence_input", social_presence_input))
	if data.get("last_intake") is Dictionary:
		last_intake.merge(data.last_intake, true)
	if data.get("cumulative") is Dictionary:
		cumulative.merge(data.cumulative, true)
	clamp_state()

func restore_from_legacy_needs(needs: Dictionary) -> void:
	# Approximate a plausible body state from v0.2 deficit bars while preserving identity/memory.
	var hunger = clampf(float(needs.get("hunger", 0.32)), 0.0, 1.0)
	var thirst = clampf(float(needs.get("thirst", 0.26)), 0.0, 1.0)
	var fatigue = clampf(float(needs.get("fatigue", 0.12)), 0.0, 1.0)
	var safety = clampf(float(needs.get("safety", 0.08)), 0.0, 1.0)
	state.metabolic_energy = clampf(TARGET_ENERGY - hunger * (TARGET_ENERGY - CRITICAL_ENERGY) * 0.78, 0.20, 0.92)
	state.stomach_fill = clampf(COMFORTABLE_STOMACH * (1.0 - hunger * 0.86), 0.04, 0.62)
	state.gut_energy = clampf(0.18 - hunger * 0.10, 0.02, 0.22)
	state.hydration = clampf(TARGET_HYDRATION - thirst * (TARGET_HYDRATION - CRITICAL_HYDRATION) * 0.88, 0.22, 0.92)
	state.sleep_pressure = fatigue * 0.72
	state.physical_fatigue = fatigue * 0.52
	state.acute_fear = safety
	state.stress_load = clampf(safety * 0.40, 0.03, 0.55)
	state.social_satiation = 1.0 - clampf(float(needs.get("social", 0.25)), 0.0, 1.0)
	state.stimulation_satiation = 1.0 - clampf(float(needs.get("boredom", 0.52)), 0.0, 1.0)
	state.feather_condition = 1.0 - clampf(float(needs.get("comfort", 0.12)), 0.0, 1.0)
	clamp_state()
