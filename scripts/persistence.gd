extends RefCounted
## Two generations, checksum and atomic promotion. Project-local, portable data.
const SCHEMA = 2
var path: String
var message = "Ännu inte sparad"
var recovered = false

func _init(save_path: String = "") -> void:
	path = save_path if not save_path.is_empty() else ProjectSettings.globalize_path("res://data/individual.json")

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
	if data.is_empty():
		data = read_valid(path + ".bak")
		recovered = not data.is_empty()
	if data.is_empty():
		message = "Ny individ" if not FileAccess.file_exists(path) else "Sparfilen kunde inte läsas. Originalet har bevarats."
		return false
	world.restore(data.world)
	agent.restore(data.agent)
	message = "Återställd från reservkopia" if recovered else "Samma individ · minnet återläst"
	return true
