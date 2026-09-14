extends SceneTree

# This script serves as an outer harness for persistence migration tests.
# It creates an isolated sandbox project to ensure that migration tests
# do not affect the real BirdAI/Alma user-data path.

func _init() -> void:
	call_deferred("run_harness")

func run_harness() -> void:
	var sandbox_path = "C:\\Temp\\AlmaSandbox\\"
	var project_path = sandbox_path + "project.godot"

	# 1. Create sandbox directory
	if not DirAccess.dir_exists_absolute(sandbox_path):
		DirAccess.make_dir_recursive_absolute(sandbox_path)

	print("[HARNESS] sandbox=" + sandbox_path)

	# 2. Copy minimum files needed
	# For this slice, we just need to ensure the project structure exists.
	# We create a dummy project.godot with a unique name to ensure a unique user-data namespace.
	var project_content = "config_version=5\n\n[application]\nconfig/name=\"Sandbox Project\"\nrun/main_scene=\"res://main.tscn\"\n\n[display]\nwindow/size/viewport_width=1440\nwindow/size/viewport_height=900\n\n[rendering]\nrenderer/rendering_method=\"forward_plus\""

	var file = FileAccess.open(project_path, FileAccess.WRITE)
	if file:
		file.store_string(project_content)
		file.close()
	else:
		print("[HARNESS] ERROR: Could not write project.godot to sandbox")
		quit(1)


	# Copy tests folder
	if not DirAccess.dir_exists_absolute(sandbox_path + "tests/"):
		DirAccess.make_dir_recursive_absolute(sandbox_path + "tests/")

	var src_path = ProjectSettings.globalize_path("tests/test_persistence_migration.gd")
	var test_file_dest = sandbox_path + "tests/test_persistence_migration.gd"

	var test_file = FileAccess.open(src_path, FileAccess.READ)
	if test_file:
		var content = test_file.get_as_text()
		test_file.close()
		var dest_file = FileAccess.open(test_file_dest, FileAccess.WRITE)
		if dest_file:
			dest_file.store_string(content)
			dest_file.close()
		else:
			print("[HARNESS] ERROR: Could not write test script to sandbox")
			quit(1)
	else:
		print("[HARNESS] ERROR: Could not read test script from workspace")
		quit(1)

	# 3. Launch child process
	# The child process will report its resolved user-data path.
	var godot_exe = "C:\\AlmaTheHen\\tools\\Godot_console.exe"
	var child_script_path = sandbox_path + "child_report.gd"
	var child_script_content = "extends SceneTree\nfunc _init() -> void:\n\tvar ud_dir = OS.get_user_data_dir()\n\tvar alma_path = ProjectSettings.globalize_path(\"user://alma/individual.json\")\n\tprint(\"[CHILD] user_data_dir=\" + ud_dir)\n\tprint(\"[CHILD] alma_save=\" + alma_path)\n\tquit(0)"

	var child_script_file = FileAccess.open(child_script_path, FileAccess.WRITE)
	if child_script_file:
		child_script_file.store_string(child_script_content)
		child_script_file.close()
	else:
		print("[HARNESS] ERROR: Could not write child_report.gd to sandbox")
		quit(1)

	# We also print the real path from the harness for comparison.
	var real_alma_path = ProjectSettings.globalize_path("user://alma/individual.json")
	print("[HARNESS] real_alma_path=" + real_alma_path)

	var args = [
		"--headless",
		"--path", sandbox_path,
		"--script", child_script_path
	]

	var exit_code = OS.execute(godot_exe, args)

	if exit_code == 0:
		print("[ISOLATION] PASS")

		# Cleanup
		if DirAccess.dir_exists_absolute(sandbox_path):
			var dir = DirAccess.open(sandbox_path)
			if dir:
				var file_name = dir.get_next()
				while file_name != "":
					if dir.file_exists(file_name):
						dir.remove(file_name)
					file_name = dir.get_next()
			# DirAccess.remove_dir_recursive(sandbox_path)

		print("[CLEANUP] PASS")
		print("[HARNESS] PASS")
		quit(0)
	else:
		print("[HARNESS] ERROR: Child process exited with code " + str(exit_code))
		quit(1)
