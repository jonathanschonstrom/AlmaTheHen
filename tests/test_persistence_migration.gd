extends SceneTree

const REQUIRED_FILES := [
	"scripts/persistence.gd",
	"scripts/world/world_state.gd",
	"scripts/cognition/agent.gd",
	"scripts/cognition/homeostasis.gd",
	"scripts/cognition/memory.gd",
	"scripts/cognition/learning.gd",
	"scripts/cognition/perception.gd",
	"scripts/cognition/utility.gd",
	"scripts/cognition/neural_action_resolver.gd",
	"scripts/body/physiology.gd",
]

var _PersistenceScript
var _AgentScript
var _WorldScript
var _real_user_data_dir := ""
var _real_alma_path := ""
var _real_alma_signature_before := {}


func _init() -> void:
	call_deferred("_dispatch")


func _dispatch() -> void:
	var args := OS.get_cmdline_user_args()
	if "--child" in args:
		_run_child(args)
	else:
		_run_outer(args)


func _run_outer(args: PackedStringArray) -> void:
	var harness_only := "--harness-only" in args
	var repo_root := ProjectSettings.globalize_path("res://")
	var real_user_data_dir := OS.get_user_data_dir()
	var real_alma_path := ProjectSettings.globalize_path("user://alma/individual.json")
	var real_signature_before := _file_signature(real_alma_path)
	var run_id := "%s-%s" % [str(Time.get_unix_time_from_system()), str(Time.get_ticks_usec())]
	var sandbox := OS.get_temp_dir().path_join("birdai-e0-persistence-" + run_id)
	var project_name := "BirdAI-E0-Persistence-" + run_id
	var custom_user_dir := "birdai-e0-persistence-" + run_id

	if _same_or_child(sandbox, repo_root):
		_fail_outer("Sandbox resolved inside the tracked working tree: " + sandbox)
		return

	if DirAccess.dir_exists_absolute(sandbox) and not _remove_tree_absolute(sandbox):
		_fail_outer("Could not remove stale sandbox: " + sandbox)
		return
	if DirAccess.make_dir_recursive_absolute(sandbox) != OK:
		_fail_outer("Could not create sandbox: " + sandbox)
		return

	print("[HARNESS] sandbox=" + sandbox)

	if not _write_project_file(sandbox, project_name, custom_user_dir):
		_cleanup_outer(sandbox, "", real_user_data_dir)
		_fail_outer("Could not write sandbox project.godot")
		return

	for relative_path in REQUIRED_FILES:
		if not _copy_into_sandbox(relative_path, sandbox):
			_cleanup_outer(sandbox, "", real_user_data_dir)
			_fail_outer("Could not copy required file: " + relative_path)
			return

	if not _copy_into_sandbox("tests/test_persistence_migration.gd", sandbox):
		_cleanup_outer(sandbox, "", real_user_data_dir)
		_fail_outer("Could not copy test script into sandbox")
		return

	var godot_exe := OS.get_executable_path()
	var child_args := PackedStringArray([
		"--headless",
		"--path", sandbox,
		"--script", "res://tests/test_persistence_migration.gd",
		"--",
		"--child",
		"--real-user-data", real_user_data_dir,
		"--real-alma", real_alma_path,
	])
	if harness_only:
		child_args.append("--harness-only")

	var output: Array = []
	var exit_code := OS.execute(godot_exe, child_args, output, true, false)
	var child_output := ""
	for chunk in output:
		child_output += str(chunk)
	if not child_output.is_empty():
		print(child_output.rstrip("\r\n"))

	var child_user_data_dir := _extract_marker(child_output, "[CHILD] user_data_dir=")
	var real_signature_after := _file_signature(real_alma_path)

	var cleanup_ok := _cleanup_outer(sandbox, child_user_data_dir, real_user_data_dir)
	if cleanup_ok:
		print("[CLEANUP] PASS")
	else:
		push_error("[CLEANUP] FAIL")

	if not _signatures_equal(real_signature_before, real_signature_after):
		push_error("[HARNESS] ERROR: real Alma save changed during isolated test run")
		quit(1)
		return

	if exit_code != 0:
		push_error("[HARNESS] ERROR: child process exited with code %d" % exit_code)
		quit(1)
		return

	if not cleanup_ok:
		quit(1)
		return

	print("[HARNESS] PASS")
	quit(0)


func _run_child(args: PackedStringArray) -> void:
	_real_user_data_dir = _arg_value(args, "--real-user-data")
	_real_alma_path = _arg_value(args, "--real-alma")
	var harness_only := "--harness-only" in args

	var child_user_data_dir := OS.get_user_data_dir()
	var child_alma_path := ProjectSettings.globalize_path("user://alma/individual.json")

	print("[CHILD] user_data_dir=" + child_user_data_dir)
	print("[CHILD] alma_save=" + child_alma_path)

	if _real_user_data_dir.is_empty() or _real_alma_path.is_empty():
		_fail_child("Missing real-project isolation arguments")
		return
	if _same_or_child(child_user_data_dir, _real_user_data_dir):
		_fail_child("Sandbox user-data directory equals or falls under the real BirdAI user-data directory")
		return
	if _same_or_child(child_alma_path, _real_user_data_dir):
		_fail_child("Sandbox Alma save equals or falls under the real BirdAI user-data directory")
		return
	if _norm(child_alma_path) == _norm(_real_alma_path):
		_fail_child("Sandbox Alma save equals the real BirdAI Alma save")
		return

	print("[ISOLATION] PASS")

	if harness_only:
		quit(0)
		return

	_real_alma_signature_before = _file_signature(_real_alma_path)

	_PersistenceScript = load("res://scripts/persistence.gd")
	_WorldScript = load("res://scripts/world/world_state.gd")
	_AgentScript = load("res://scripts/cognition/agent.gd")
	if _PersistenceScript == null or _WorldScript == null or _AgentScript == null:
		_fail_child("Could not load persistence/agent/world scripts after isolation proof")
		return

	var scenarios := [
		_scenario_1,
		_scenario_2,
		_scenario_3,
		_scenario_4,
		_scenario_5,
		_scenario_6,
		_scenario_7,
		_scenario_8,
		_scenario_9,
		_scenario_10,
		_scenario_11,
		_scenario_12,
		_scenario_13,
		_scenario_14,
	]

	for i in range(scenarios.size()):
		if not _reset_case():
			_fail_child("Scenario %d setup cleanup failed" % (i + 1))
			return
		if not scenarios[i].call():
			quit(1)
			return
		print("[SCENARIO %d] PASS" % (i + 1))

	if not _reset_case():
		_fail_child("Final child cleanup failed")
		return

	var real_signature_after := _file_signature(_real_alma_path)
	if not _signatures_equal(_real_alma_signature_before, real_signature_after):
		_fail_child("Real BirdAI Alma save changed during migration suite")
		return

	quit(0)


func _scenario_1() -> bool:
	var expected := ProjectSettings.globalize_path("user://alma/individual.json")
	var persistence = _PersistenceScript.new()
	return _check(_norm(persistence.path) == _norm(expected), "Scenario 1: default destination is not user://alma/individual.json")


func _scenario_2() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var explicit_path := ProjectSettings.globalize_path("user://explicit/scenario2.json")
	var default_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_valid_envelope(legacy_path, _snapshot("legacy-s2")):
		return _check(false, "Scenario 2: could not create legacy fixture")
	var legacy_before := _read_text(legacy_path)
	var persistence = _PersistenceScript.new("user://explicit/scenario2.json")
	if not _check(_norm(persistence.path) == _norm(explicit_path), "Scenario 2: explicit path was not honored"):
		return false
	if not _check(not FileAccess.file_exists(explicit_path), "Scenario 2: explicit constructor unexpectedly wrote a file"):
		return false
	if not _check(not FileAccess.file_exists(default_path), "Scenario 2: explicit constructor triggered default-path migration"):
		return false
	return _check(_read_text(legacy_path) == legacy_before, "Scenario 2: explicit constructor changed legacy source")


func _scenario_3() -> bool:
	var world = _WorldScript.new()
	var agent = _AgentScript.new(world, 303)
	agent.individual_id = "alma-scenario-3"
	var persistence = _PersistenceScript.new("user://tests/scenario3.json")
	if not _check(persistence.save(agent, world), "Scenario 3: save failed"):
		return false
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 304)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 3: load failed"):
		return false
	return _check(restored_agent.individual_id == "alma-scenario-3", "Scenario 3: individual_id was not preserved")


func _scenario_4() -> bool:
	var world = _WorldScript.new()
	var agent = _AgentScript.new(world, 404)
	agent.memory.objects = {
		"memory-object": {
			"label": "Minnesobjekt",
			"first_seen": 1.0,
			"last_seen": 9.0,
			"visits": 3,
			"observations": 7,
			"facts": {"inspect": {"outcome": "bekant", "reward": 0.4, "time": 8.0}},
			"position": [1.0, 0.0, -2.0],
			"cues": {"round": 1.0},
			"present": true,
		}
	}
	agent.memory.episodes = [{"time": 8.0, "target": "memory-object", "action": "inspect", "outcome": "bekant", "reward": 0.4, "sequence": 17}]
	agent.memory.total_episodes = 17
	var persistence = _PersistenceScript.new("user://tests/scenario4.json")
	if not _check(persistence.save(agent, world), "Scenario 4: save failed"):
		return false
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 405)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 4: load failed"):
		return false
	if not _check(restored_agent.memory.objects.has("memory-object"), "Scenario 4: memory objects were not restored"):
		return false
	if not _check(restored_agent.memory.episodes.size() == 1, "Scenario 4: episodes were not restored"):
		return false
	if not _check(int(restored_agent.memory.total_episodes) == 17, "Scenario 4: total_episodes was not restored"):
		return false
	return _check(str(restored_agent.memory.episodes[0].outcome) == "bekant", "Scenario 4: episode content changed")


func _scenario_5() -> bool:
	var world = _WorldScript.new()
	var agent = _AgentScript.new(world, 505)
	agent.memory.working = [{"id": "transient", "kind": "ser", "text": "ska inte sparas", "time": 2.0}]
	var persistence = _PersistenceScript.new("user://tests/scenario5.json")
	if not _check(persistence.save(agent, world), "Scenario 5: save failed"):
		return false
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 506)
	restored_agent.memory.working = [{"id": "preexisting", "kind": "test", "text": "clear me", "time": 0.0}]
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 5: load failed"):
		return false
	return _check(restored_agent.memory.working.is_empty(), "Scenario 5: working memory was restored or not cleared")


func _scenario_6() -> bool:
	var world = _WorldScript.new()
	var agent = _AgentScript.new(world, 606)
	agent.learning.models = {"o3:push": {"count": 4, "effects": {"object_motion": 0.42}, "success": 0.75, "outcome": "rullade", "reward": 0.3, "error": 0.1}}
	agent.learning.contexts = {"o5:peck@lamp_lit": {"count": 2, "effects": {"food_access": 0.6}, "success": 1.0, "outcome": "luckan Ã¶ppnades", "reward": 0.8, "error": 0.2}}
	agent.learning.skills = {"push": {"attempts": 5, "successes": 3}}
	agent.learning.flight.timing = 0.61
	agent.learning.flight.best_timing = 0.57
	agent.learning.flight.best_height = 0.88
	agent.learning.flight.trials = 12
	agent.learning.flight.step = 0.03
	agent.learning.flight.direction = -1.0
	var persistence = _PersistenceScript.new("user://tests/scenario6.json")
	if not _check(persistence.save(agent, world), "Scenario 6: save failed"):
		return false
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 607)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 6: load failed"):
		return false
	if not _check(restored_agent.learning.models.has("o3:push"), "Scenario 6: models were not restored"):
		return false
	if not _check(restored_agent.learning.contexts.has("o5:peck@lamp_lit"), "Scenario 6: contexts were not restored"):
		return false
	if not _check(int(restored_agent.learning.skills.get("push", {}).get("attempts", 0)) == 5, "Scenario 6: skills were not restored"):
		return false
	if not _check(is_equal_approx(float(restored_agent.learning.flight.best_height), 0.88), "Scenario 6: flight best_height was not restored"):
		return false
	return _check(int(restored_agent.learning.flight.trials) == 12, "Scenario 6: flight trials were not restored")


func _scenario_7() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var target_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_valid_envelope(legacy_path, _snapshot("legacy-primary-s7")):
		return _check(false, "Scenario 7: could not write legacy primary")
	var persistence = _PersistenceScript.new()
	var migrated: Dictionary = persistence.read_valid(target_path)
	if not _check(_norm(persistence.path) == _norm(target_path), "Scenario 7: migration target path is wrong"):
		return false
	return _check(_data_individual_id(migrated) == "legacy-primary-s7", "Scenario 7: valid legacy primary did not migrate")


func _scenario_8() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var target_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_text(legacy_path, "{broken legacy primary"):
		return _check(false, "Scenario 8: could not write corrupt legacy primary")
	if not _write_valid_envelope(legacy_path + ".bak", _snapshot("legacy-backup-s8")):
		return _check(false, "Scenario 8: could not write legacy backup")
	var persistence = _PersistenceScript.new()
	var migrated: Dictionary = persistence.read_valid(target_path)
	return _check(_data_individual_id(migrated) == "legacy-backup-s8", "Scenario 8: valid legacy .bak did not migrate")


func _scenario_9() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var user_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_valid_envelope(legacy_path, _snapshot("legacy-s9")):
		return _check(false, "Scenario 9: could not write legacy fixture")
	if not _write_valid_envelope(user_path, _snapshot("user-primary-s9")):
		return _check(false, "Scenario 9: could not write user primary")
	var persistence = _PersistenceScript.new()
	return _check(_data_individual_id(persistence.read_valid(user_path)) == "user-primary-s9", "Scenario 9: legacy data overrode valid user primary")


func _scenario_10() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var user_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_text(user_path, "{corrupt user primary"):
		return _check(false, "Scenario 10: could not write corrupt user primary")
	if not _write_valid_envelope(user_path + ".bak", _snapshot("user-backup-s10")):
		return _check(false, "Scenario 10: could not write valid user backup")
	if not _write_valid_envelope(legacy_path, _snapshot("legacy-s10")):
		return _check(false, "Scenario 10: could not write legacy fixture")
	var persistence = _PersistenceScript.new()
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 1001)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 10: backup load failed"):
		return false
	if not _check(restored_agent.individual_id == "user-backup-s10", "Scenario 10: legacy data won over valid user .bak"):
		return false
	return _check(persistence.recovered, "Scenario 10: backup recovery flag was not set")


func _scenario_11() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	if not _write_valid_envelope(legacy_path, _snapshot("legacy-unchanged-s11")):
		return _check(false, "Scenario 11: could not write legacy fixture")
	var before := _read_text(legacy_path)
	var persistence = _PersistenceScript.new()
	var after := _read_text(legacy_path)
	if not _check(not persistence.read_valid(persistence.path).is_empty(), "Scenario 11: migration did not produce valid user data"):
		return false
	return _check(before == after, "Scenario 11: legacy original changed during migration")


func _scenario_12() -> bool:
	var legacy_path := ProjectSettings.globalize_path("res://data/individual.json")
	var source_world = _WorldScript.new()
	source_world.now = 432.5
	source_world.hatch_open = true
	source_world.next_experiment_time = 987.0
	source_world.objects.o1.stock = 2.25
	source_world.objects.o8.active = false
	var source_agent = _AgentScript.new(source_world, 1201)
	source_agent.individual_id = "alma-central-s12"
	source_agent.bird_name = "Alma Persist"
	source_agent.hen_share = 0.63
	source_agent.age = 321.25
	source_agent.position = Vector3(1.25, 0.0, -0.75)
	source_agent.relationship.trust = 0.77
	source_agent.relationship.attachment = 0.44
	source_agent.personality.curiosity = 0.91
	source_agent.decision_count = 123
	source_agent.distance_walked = 45.6
	var data := {"schema": 2, "saved_at": "test-s12", "agent": source_agent.export_data(), "world": source_world.export_data()}
	if not _write_valid_envelope(legacy_path, data):
		return _check(false, "Scenario 12: could not write legacy state")
	var persistence = _PersistenceScript.new()
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 1202)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 12: migrated state could not be loaded"):
		return false
	if not _check(restored_agent.individual_id == "alma-central-s12", "Scenario 12: individual_id changed"):
		return false
	if not _check(restored_agent.bird_name == "Alma Persist", "Scenario 12: bird name changed"):
		return false
	if not _check(is_equal_approx(float(restored_agent.hen_share), 0.63), "Scenario 12: hen_share changed"):
		return false
	if not _check(is_equal_approx(restored_agent.age, 321.25), "Scenario 12: age changed"):
		return false
	if not _check(restored_agent.position.is_equal_approx(Vector3(1.25, 0.0, -0.75)), "Scenario 12: position changed"):
		return false
	if not _check(is_equal_approx(float(restored_agent.relationship.trust), 0.77), "Scenario 12: relationship trust changed"):
		return false
	if not _check(is_equal_approx(float(restored_agent.personality.curiosity), 0.91), "Scenario 12: personality changed"):
		return false
	if not _check(int(restored_agent.decision_count) == 123, "Scenario 12: decision_count changed"):
		return false
	if not _check(is_equal_approx(restored_world.now, 432.5), "Scenario 12: world time changed"):
		return false
	if not _check(restored_world.hatch_open, "Scenario 12: hatch_open changed"):
		return false
	if not _check(is_equal_approx(float(restored_world.objects.o1.stock), 2.25), "Scenario 12: world object stock changed"):
		return false
	return _check(not bool(restored_world.objects.o8.active), "Scenario 12: world object active state changed")


func _scenario_13() -> bool:
	var user_path := ProjectSettings.globalize_path("user://alma/individual.json")
	if not _write_text(user_path, "{corrupt primary"):
		return _check(false, "Scenario 13: could not write corrupt primary")
	if not _write_valid_envelope(user_path + ".bak", _snapshot("user-backup-s13")):
		return _check(false, "Scenario 13: could not write backup")
	var persistence = _PersistenceScript.new()
	var restored_world = _WorldScript.new()
	var restored_agent = _AgentScript.new(restored_world, 1301)
	if not _check(persistence.load_into(restored_agent, restored_world), "Scenario 13: .bak recovery failed"):
		return false
	if not _check(restored_agent.individual_id == "user-backup-s13", "Scenario 13: wrong backup content restored"):
		return false
	return _check(persistence.recovered, "Scenario 13: recovered flag was not set")


func _scenario_14() -> bool:
	var sandbox_alma := ProjectSettings.globalize_path("user://alma/individual.json")
	var explicit_path := ProjectSettings.globalize_path("user://explicit/scenario14.json")
	var world = _WorldScript.new()
	var agent = _AgentScript.new(world, 1401)
	agent.individual_id = "explicit-s14"
	var real_before := _file_signature(_real_alma_path)
	var persistence = _PersistenceScript.new("user://explicit/scenario14.json")
	if not _check(persistence.save(agent, world), "Scenario 14: explicit-path save failed"):
		return false
	if not _check(_norm(persistence.path) == _norm(explicit_path), "Scenario 14: explicit path changed"):
		return false
	if not _check(FileAccess.file_exists(explicit_path), "Scenario 14: explicit test file was not written"):
		return false
	if not _check(not FileAccess.file_exists(sandbox_alma), "Scenario 14: explicit test wrote sandbox default Alma path"):
		return false
	if not _check(not _same_or_child(explicit_path, _real_user_data_dir), "Scenario 14: explicit test path falls under real BirdAI user-data"):
		return false
	return _check(_signatures_equal(real_before, _file_signature(_real_alma_path)), "Scenario 14: real BirdAI Alma save changed")


func _snapshot(individual_id: String) -> Dictionary:
	var world = _WorldScript.new()
	world.now = 12.5
	var agent = _AgentScript.new(world, 77)
	agent.individual_id = individual_id
	return {"schema": 2, "saved_at": "fixture", "agent": agent.export_data(), "world": world.export_data()}


func _data_individual_id(data: Dictionary) -> String:
	if data.is_empty():
		return ""
	var agent_data = data.get("agent", {})
	if not agent_data is Dictionary:
		return ""
	return str(agent_data.get("individual_id", ""))


func _reset_case() -> bool:
	var paths := [
		ProjectSettings.globalize_path("res://data"),
		ProjectSettings.globalize_path("user://alma"),
		ProjectSettings.globalize_path("user://tests"),
		ProjectSettings.globalize_path("user://explicit"),
	]
	for path in paths:
		if DirAccess.dir_exists_absolute(path) and not _remove_tree_absolute(path):
			return false
	return true


func _write_valid_envelope(path: String, data: Dictionary) -> bool:
	var payload := JSON.stringify(data)
	var envelope := JSON.stringify({"payload": payload, "sha256": payload.sha256_text()}, "\t")
	return _write_text(path, envelope)


func _write_text(path: String, content: String) -> bool:
	var parent := path.get_base_dir()
	if DirAccess.make_dir_recursive_absolute(parent) != OK:
		return false
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(content)
	file.flush()
	file.close()
	return true


func _read_text(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	var content := file.get_as_text()
	file.close()
	return content


func _file_signature(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {"exists": false, "sha256": "", "length": 0}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {"exists": true, "sha256": "<unreadable>", "length": -1}
	var content := file.get_as_text()
	file.close()
	return {"exists": true, "sha256": content.sha256_text(), "length": content.length()}


func _signatures_equal(a: Dictionary, b: Dictionary) -> bool:
	return bool(a.get("exists", false)) == bool(b.get("exists", false)) and str(a.get("sha256", "")) == str(b.get("sha256", "")) and int(a.get("length", 0)) == int(b.get("length", 0))


func _write_project_file(sandbox: String, project_name: String, custom_user_dir: String) -> bool:
	var content := "config_version=5\n\n[application]\nconfig/name=\"%s\"\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name=\"%s\"\n\n[rendering]\nrenderer/rendering_method=\"gl_compatibility\"\nrenderer/rendering_method.mobile=\"gl_compatibility\"\n" % [project_name, custom_user_dir]
	return _write_text(sandbox.path_join("project.godot"), content)


func _copy_into_sandbox(relative_path: String, sandbox: String) -> bool:
	var source := ProjectSettings.globalize_path("res://" + relative_path)
	if not FileAccess.file_exists(source):
		return false
	var destination := sandbox.path_join(relative_path)
	if DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
		return false
	return DirAccess.copy_absolute(source, destination) == OK


func _cleanup_outer(sandbox: String, child_user_data_dir: String, real_user_data_dir: String) -> bool:
	var ok := true
	if not child_user_data_dir.is_empty():
		if _same_or_child(child_user_data_dir, real_user_data_dir):
			push_error("Refusing to clean child user-data because it overlaps the real user-data path")
			ok = false
		elif DirAccess.dir_exists_absolute(child_user_data_dir) and not _remove_tree_absolute(child_user_data_dir):
			ok = false
	if DirAccess.dir_exists_absolute(sandbox) and not _remove_tree_absolute(sandbox):
		ok = false
	return ok


func _remove_tree_absolute(path: String) -> bool:
	if not DirAccess.dir_exists_absolute(path):
		if FileAccess.file_exists(path):
			return DirAccess.remove_absolute(path) == OK
		return true
	var dir := DirAccess.open(path)
	if dir == null:
		return false
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if entry != "." and entry != "..":
			var child := path.path_join(entry)
			if dir.current_is_dir():
				if not _remove_tree_absolute(child):
					dir.list_dir_end()
					return false
			elif DirAccess.remove_absolute(child) != OK:
				dir.list_dir_end()
				return false
		entry = dir.get_next()
	dir.list_dir_end()
	return DirAccess.remove_absolute(path) == OK


func _extract_marker(text: String, marker: String) -> String:
	for line in text.replace("\r\n", "\n").split("\n"):
		if line.begins_with(marker):
			return line.substr(marker.length()).strip_edges()
	return ""


func _arg_value(args: PackedStringArray, name: String) -> String:
	var index := args.find(name)
	if index < 0 or index + 1 >= args.size():
		return ""
	return args[index + 1]


func _norm(path: String) -> String:
	return path.replace("\\", "/").trim_suffix("/").to_lower()


func _same_or_child(candidate: String, parent: String) -> bool:
	var c := _norm(candidate)
	var p := _norm(parent)
	if c.is_empty() or p.is_empty():
		return false
	return c == p or c.begins_with(p + "/")


func _check(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error("[ASSERT] " + message)
	return false


func _fail_child(message: String) -> void:
	push_error("[CHILD] ERROR: " + message)
	quit(1)


func _fail_outer(message: String) -> void:
	push_error("[HARNESS] ERROR: " + message)
	quit(1)
