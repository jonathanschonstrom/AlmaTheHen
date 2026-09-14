extends RefCounted
## Two generations, checksum and atomic promotion. Project-local, portable data.
const SCHEMA = 2
var path: String
var message = "Ännu inte sparad"
var recovered = false

var legacy_fallback_data: Dictionary = {}

func _init(save_path: String = "") -> void:
	if not save_path.is_empty():
		if save_path.begins_with("user://") or save_path.begins_with("res://"):
			path = ProjectSettings.globalize_path(save_path)
		else:
			path = save_path
	else:
		var target_path = ProjectSettings.globalize_path("user://alma/individual.json")

		# 1. Check for existing valid user data
		var user_primary = read_valid(target_path)
		if not user_primary.is_empty():
			path = target_path
			return

		var user_bak = read_valid(target_path + ".bak")
		if not user_bak.is_empty():
			path = target_path
			return

		# 2. Try to find legacy data
		var legacy_path = ProjectSettings.globalize_path("res://data/individual.json")
		var legacy_bak = legacy_path + ".bak"

		var data = read_valid(legacy_path)
		if data.is_empty():
			data = read_valid(legacy_bak)

		if not data.is_empty():
			# 3. Attempt migration
			var success = _migrate_data(data, target_path)
			if success:
				path = target_path
			else:
				# Migration failed: preserve legacy data as a verified fallback
				legacy_fallback_data = data
				path = target_path
		else:
			path = target_path

func _migrate_data(data: Dictionary, target_path: String) -> bool:
	var payload = JSON.stringify(data)
	var envelope = JSON.stringify({"payload": payload, "sha256": payload.sha256_text()}, "\t")
	var folder = target_path.get_base_dir()

	if DirAccess.make_dir_recursive_absolute(folder) != OK:
		message = "Sparning misslyckades: mappen är inte skrivbar."
		return false

	var file = FileAccess.open(target_path + ".tmp", FileAccess.WRITE)
	if file == null:
		message = "Sparning misslyckades: " + error_string(FileAccess.get_open_error())
		return false
	file.store_string(envelope)
	file.flush()
	file.close()

	# Preserve the prior valid generation even if an earlier primary was corrupt.
	if FileAccess.file_exists(target_path) and not read_valid(target_path).is_empty():
		var copied = DirAccess.copy_absolute(target_path, target_path + ".bak")
		if copied != OK:
			message = "Kunde inte säkra föregående sparning."
			return false
	elif FileAccess.file_exists(target_path):
		var preserved = target_path + ".unreadable-" + str(int(Time.get_unix_time_from_system()))
		if DirAccess.copy_absolute(target_path, preserved) != OK:
			message = "Kunde inte bevara den skadade sparfilen."
			return false

	var promoted = DirAccess.rename_absolute(target_path + ".tmp", target_path)
	if promoted != OK:
		message = "Kunde inte slutföra sparning: " + error_string(promoted)
		return false
	message = "Migrerad från legacy"
	return true

func save(agent, world) -> bool:
	var data = {"schema": SCHEMA, "saved_at": Time.get_datetime_string_from_system(), "agent": agent.export_data(), "world": world.export_data()}
	var payload = JSON.stringify(data)
	var envelope = JSON.stringify({"payload": payload, "sha256": payload.sha256_text()}, "\t")
	var folder = path.get_base_dir()
	if DirAccess.make_dir_recursive_absolute(folder) != OK:
		message = "Sparning misslyckades: mappen är inte skrivbar."
		return false
	var file = FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null:
		message = "Sparning misslyckades: " + error_string(FileAccess.get_open_error())
		return false
	file.store_string(envelope)
	file.flush()
	file.close()
	# Preserve the prior valid generation even if an earlier primary was corrupt.
	if FileAccess.file_exists(path) and not read_valid(path).is_empty():
		var copied = DirAccess.copy_absolute(path, path + ".bak")
		if copied != OK:
			message = "Kunde inte säkra föregående sparning."
			return false
	elif FileAccess.file_exists(path):
		var preserved = path + ".unreadable-" + str(int(Time.get_unix_time_from_system()))
		if DirAccess.copy_absolute(path, preserved) != OK:
			message = "Kunde inte bevara den skadade sparfilen."
			return false
	var promoted = DirAccess.rename_absolute(path + ".tmp", path)
	if promoted != OK:
		message = "Kunde inte slutföra sparning: " + error_string(promoted)
		return false
	message = "Sparad " + Time.get_time_string_from_system()
	return true

func read_valid(file_path: String) -> Dictionary:
	if not FileAccess.file_exists(file_path):
		return {}
	var file = FileAccess.open(file_path, FileAccess.READ)
	if file == null:
		return {}
	var parser = JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		return {}
	var envelope = parser.data
	if not envelope is Dictionary or not envelope.get("payload") is String:
		return {}
	if envelope.payload.sha256_text() != envelope.get("sha256", ""):
		return {}
	if parser.parse(envelope.payload) != OK:
		return {}
	var data = parser.data
	if not data is Dictionary:
		return {}
	var schema = int(data.get("schema", 0))
	if schema < 1 or schema > SCHEMA:
		return {}
	if not data.get("agent") is Dictionary or not data.get("world") is Dictionary:
		return {}
	return data

func load_into(agent, world) -> bool:
	var data = read_valid(path)
	var source = "primary"

	if data.is_empty():
		data = read_valid(path + ".bak")
		if not data.is_empty():
			source = "backup"

	if data.is_empty() and not legacy_fallback_data.is_empty():
		data = legacy_fallback_data
		source = "legacy"

	if data.is_empty():
		message = "Ny individ" if not FileAccess.file_exists(path) else "Sparfilen kunde inte läsas. Originalet har bevarats."
		return false

	world.restore(data.world)
	agent.restore(data.agent)

	match source:
		"backup":
			recovered = true
			message = "Återställd från reservkopia"
		"legacy":
			recovered = true
			message = "Återställd från legacy-fallback"
		_:
			recovered = false
			message = "Samma individ · minnet återläst"

	return true
