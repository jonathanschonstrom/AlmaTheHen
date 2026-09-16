extends SceneTree

const Agent = preload("res://scripts/cognition/agent.gd")

class FakeWorld:
	extends RefCounted
	var objects = {}
	var perform_result = {"outcomes": {}, "success": false, "outcome": "fake", "donor": ""}
	var perform_calls := 0
	func perform(action: String, target: String, position: Vector3, heading: Vector3) -> Dictionary:
		perform_calls += 1
		return perform_result.duplicate(true)
	func move_ground(position: Vector3, velocity: Vector3, dt: float, target: String) -> Vector3:
		return position

var failures: Array[String] = []

func fail(message: String) -> void:
	failures.append(message)
	push_error(message)

func expect_equal(actual, expected, label: String) -> void:
	if actual != expected:
		fail("%s: expected %s, got %s" % [label, str(expected), str(actual)])

func expect_true(value: bool, label: String) -> void:
	if not value:
		fail("%s: expected true" % label)

func arm(agent, action: String, target: String, context: String = "") -> void:
	agent.current = {"action": action, "target": target, "context": context, "expected": {}, "body_before": agent.body.needs.duplicate(true), "error_before": agent.body.homeostatic_error()}
	agent.phase = "act"
	agent.phase_time = 100.0
	agent.action_duration = 0.0
	agent.position = Vector3.ZERO
	agent.target_position = Vector3(10.0, 0.0, 0.0)

func latest_causal(agent) -> Dictionary:
	if agent.memory.episodes.is_empty():
		return {}
	return agent.memory.episodes[-1].get("causal", {})

func test_approach_timeout() -> void:
	var world = FakeWorld.new()
	var agent = Agent.new(world, 101)
	arm(agent, "drink", "water", "bright")
	agent.phase = "approach"
	var mb = int(agent.learning.model("water", "drink").count)
	var cb = int(agent.learning.model("water", "drink", "bright").count)
	var ab = int(agent.learning.skills.get("drink", {"attempts": 0}).attempts)
	agent.approach(0.01)
	var causal = latest_causal(agent)
	expect_equal(int(agent.learning.model("water", "drink").count), mb, "approach model")
	expect_equal(int(agent.learning.model("water", "drink", "bright").count), cb, "approach context")
	expect_equal(int(agent.learning.skills.get("drink", {"attempts": 0}).attempts), ab, "approach attempts")
	expect_equal(causal.get("execution_reason"), "approach_timeout", "approach reason")
	expect_equal(causal.get("interaction"), "not_executed", "approach interaction")
	expect_equal(causal.get("semantic_eligible"), false, "approach eligibility")
	expect_equal(causal.get("learning_update"), false, "approach update")
	expect_equal(agent.memory.episodes[-1].get("prediction_error"), null, "approach prediction error")
	print("A_APPROACH_TIMEOUT: PASS model %d->%d context %d->%d attempts %d->%d" % [mb, int(agent.learning.model("water", "drink").count), cb, int(agent.learning.model("water", "drink", "bright").count), ab, int(agent.learning.skills.get("drink", {"attempts": 0}).attempts)])

func test_target_lost() -> void:
	var world = FakeWorld.new()
	var agent = Agent.new(world, 102)
	arm(agent, "eat", "food", "known")
	var mb = int(agent.learning.model("food", "eat").count)
	var cb = int(agent.learning.model("food", "eat", "known").count)
	var ab = int(agent.learning.skills.get("eat", {"attempts": 0}).attempts)
	agent.act(0.0)
	var causal = latest_causal(agent)
	expect_equal(world.perform_calls, 0, "target lost perform")
	expect_equal(int(agent.learning.model("food", "eat").count), mb, "target lost model")
	expect_equal(int(agent.learning.model("food", "eat", "known").count), cb, "target lost context")
	expect_equal(int(agent.learning.skills.get("eat", {"attempts": 0}).attempts), ab, "target lost attempts")
	expect_equal(causal.get("execution_reason"), "target_lost", "target lost reason")
	expect_equal(causal.get("semantic_eligible"), false, "target lost eligibility")
	print("B_TARGET_LOST: PASS perform_calls=0 semantic_counts_unchanged=true")

func test_reached_but_empty_is_learnable() -> void:
	var world = FakeWorld.new()
	world.objects["food"] = {"active": true, "position": Vector3.ZERO}
	world.perform_result = {"outcomes": {}, "success": false, "outcome": "Maten var slut.", "donor": ""}
	var agent = Agent.new(world, 103)
	arm(agent, "eat", "food")
	var mb = int(agent.learning.model("food", "eat").count)
	var ab = int(agent.learning.skills.get("eat", {"attempts": 0}).attempts)
	agent.act(0.0)
	var causal = latest_causal(agent)
	expect_equal(world.perform_calls, 1, "empty perform")
	expect_equal(int(agent.learning.model("food", "eat").count), mb + 1, "empty model")
	expect_equal(int(agent.learning.skills["eat"].attempts), ab + 1, "empty attempts")
	expect_equal(causal.get("interaction"), "executed", "empty interaction")
	expect_equal(causal.get("consequence"), "failure", "empty consequence")
	expect_equal(causal.get("semantic_eligible"), true, "empty eligibility")
	expect_equal(causal.get("learning_update"), true, "empty update")
	expect_true(agent.memory.episodes[-1].get("prediction_error") != null, "empty prediction error")
	print("C_REACHED_EMPTY: PASS model %d->%d attempts %d->%d" % [mb, int(agent.learning.model("food", "eat").count), ab, int(agent.learning.skills["eat"].attempts)])

func test_successful_interaction_unchanged() -> void:
	var world = FakeWorld.new()
	world.objects["water"] = {"active": true, "position": Vector3.ZERO}
	world.perform_result = {"outcomes": {"hydration": 0.2}, "success": true, "outcome": "Drack vatten.", "donor": ""}
	var agent = Agent.new(world, 104)
	arm(agent, "drink", "water")
	var mb = int(agent.learning.model("water", "drink").count)
	var ab = int(agent.learning.skills.get("drink", {"attempts": 0}).attempts)
	agent.act(0.0)
	var causal = latest_causal(agent)
	expect_equal(world.perform_calls, 1, "success perform")
	expect_equal(int(agent.learning.model("water", "drink").count), mb + 1, "success model")
	expect_equal(int(agent.learning.skills["drink"].attempts), ab + 1, "success attempts")
	expect_equal(causal.get("interaction"), "executed", "success interaction")
	expect_equal(causal.get("consequence"), "success", "success consequence")
	expect_equal(causal.get("semantic_eligible"), true, "success eligibility")
	print("D_SUCCESSFUL_INTERACTION: PASS model %d->%d attempts %d->%d" % [mb, int(agent.learning.model("water", "drink").count), ab, int(agent.learning.skills["drink"].attempts)])

func test_no_target_resolution_observable() -> void:
	var world = FakeWorld.new()
	var agent = Agent.new(world, 105)
	var models_before = agent.learning.models.size()
	var skills_before = agent.learning.skills.size()
	agent.record_resolution_failure("DRINK")
	var causal = latest_causal(agent)
	expect_equal(agent.learning.models.size(), models_before, "no target models")
	expect_equal(agent.learning.skills.size(), skills_before, "no target skills")
	expect_equal(causal.get("resolution"), "no_target", "no target resolution")
	expect_equal(causal.get("execution"), "not_started", "no target execution")
	expect_equal(causal.get("semantic_eligible"), false, "no target eligibility")
	print("E_NO_TARGET: PASS semantic_learning_unchanged=true observable=true")

func _initialize() -> void:
	test_approach_timeout()
	test_target_lost()
	test_reached_but_empty_is_learnable()
	test_successful_interaction_unchanged()
	test_no_target_resolution_observable()
	if failures.is_empty():
		print("E1_A2_EXECUTION_INTEGRITY: PASS")
		print("PRECONTACT_SEMANTIC_CONTAMINATION: BLOCKED")
		print("EXECUTED_NEGATIVE_CONSEQUENCE_LEARNABLE: PASS")
		print("EXECUTED_SUCCESS_CONSEQUENCE_LEARNABLE: PASS")
		print("CAUSAL_OBSERVABILITY: PASS")
		quit(0)
	else:
		print("E1_A2_EXECUTION_INTEGRITY: FAIL count=%d" % failures.size())
		for message in failures:
			print("FAILURE: " + message)
		quit(1)
