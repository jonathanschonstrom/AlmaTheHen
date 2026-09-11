extends RefCounted
## Local TCP bridge to the Python/Nengo brain.
##
## mode == "control": NeuralBrain is authoritative for action-family selection.
## Utility is evaluated only as a diagnostic reference and never actuates Alma.
## mode == "shadow": legacy behaviour; utility remains authoritative and NB is
## observed in parallel.

const PORT := 39393
const UPDATE_INTERVAL := 0.20
const RECONNECT_INTERVAL := 1.0

var peer := StreamPeerTCP.new()
var status := "offline"
var process_id := -1
var launched_process := false
var clock := 0.0
var reconnect_clock := 0.0
var request_id := 0
var pending := false
var pending_utility_family := ""
var receive_buffer := ""
var python_path := ""
var last_error := ""
var samples := 0
var agreements := 0
var log_path := ""
var mode := "control"

func start(requested_mode: String = "control") -> void:
	mode = "shadow" if requested_mode == "shadow" else "control"
	var filename = "neural-shadow.jsonl" if mode == "shadow" else "neural-control.jsonl"
	log_path = ProjectSettings.globalize_path("res://data/" + filename)
	var log = FileAccess.open(log_path, FileAccess.WRITE)
	if log != null:
		log.store_line(JSON.stringify({
			"event": "session_start",
			"mode": mode,
			"neural_brain": "v0.2.6",
			"actuator_authority": "utility" if mode == "shadow" else "neural",
			"port": PORT
		}))
		log.close()
	python_path = find_python()
	if python_path.is_empty():
		status = "saknas"
		last_error = "Kör Installera NeuralBrain.cmd"
		return
	var script = ProjectSettings.globalize_path("res://brain/brain_server.py")
	process_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT)]), false)
	if process_id <= 0:
		status = "startfel"
		last_error = "Kunde inte starta lokal Python/Nengo-server."
		return
	launched_process = true
	status = "startar"
	reconnect_clock = RECONNECT_INTERVAL

func find_python() -> String:
	for relative in ["res://brain/.venv/Scripts/pythonw.exe", "res://brain/.venv/Scripts/python.exe", "res://tools/python/pythonw.exe", "res://tools/python/python.exe"]:
		if FileAccess.file_exists(relative):
			return ProjectSettings.globalize_path(relative)
	return ""

func tick(dt: float, agent) -> void:
	agent.neural_shadow["bridge_status"] = status
	agent.neural_shadow["control_mode"] = mode
	agent.neural_shadow["actuator_authority"] = "utility" if mode == "shadow" else "neural"
	if not last_error.is_empty():
		agent.neural_shadow["error"] = last_error
	clock += dt
	reconnect_clock += dt
	poll_connection(agent)
	if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		if mode == "control":
			agent.neural_bridge_unavailable("NeuralBrain är offline; ingen utility-fallback används.")
		if not python_path.is_empty() and reconnect_clock >= RECONNECT_INTERVAL:
			reconnect_clock = 0.0
			connect_peer()
		return
	if not pending and clock >= UPDATE_INTERVAL:
		clock = 0.0
		send_snapshot(agent)

func connect_peer() -> void:
	peer = StreamPeerTCP.new()
	var err = peer.connect_to_host("127.0.0.1", PORT)
	if err != OK:
		status = "anslutningsfel"
		last_error = "TCP %s" % error_string(err)
	else:
		status = "ansluter"

func poll_connection(agent) -> void:
	if launched_process and process_id > 0 and not OS.is_process_running(process_id):
		status = "hjärnfel"
		last_error = "NeuralBrain-servern avslutades. Kör Kor NeuralBrain-test.cmd."
		process_id = -1
		launched_process = false
		python_path = ""
		pending = false
		pending_utility_family = ""
		if mode == "control":
			agent.neural_bridge_unavailable(last_error)
		if peer.get_status() != StreamPeerTCP.STATUS_NONE:
			peer.disconnect_from_host()
		return
	peer.poll()
	var connection_status = peer.get_status()
	if connection_status == StreamPeerTCP.STATUS_CONNECTED:
		if status != "online":
			status = "online"
			last_error = ""
		read_available(agent)
	elif connection_status in [StreamPeerTCP.STATUS_ERROR, StreamPeerTCP.STATUS_NONE]:
		if status == "online":
			status = "frånkopplad"
		pending = false
		pending_utility_family = ""
		if mode == "control":
			agent.neural_bridge_unavailable("NeuralBrain tappade anslutningen; ingen utility-fallback används.")

func send_snapshot(agent) -> void:
	request_id += 1
	if mode == "shadow":
		var utility_action = str(agent.current.get("action", "look"))
		pending_utility_family = agent.action_family(utility_action)
	else:
		pending_utility_family = agent.utility_shadow_family()
	var payload = {
		"command": "step",
		"request_id": request_id,
		"age": agent.age,
		"neural_seconds": 0.05,
		"inputs": agent.neural_inputs()
	}
	var bytes = (JSON.stringify(payload) + "\n").to_utf8_buffer()
	var err = peer.put_data(bytes)
	if err == OK:
		pending = true
	else:
		status = "skrivfel"
		last_error = error_string(err)
		pending = false
		pending_utility_family = ""
		if mode == "control":
			agent.neural_bridge_unavailable("NeuralBrain kunde inte ta emot nästa sensoriska snapshot.")

func read_available(agent) -> void:
	while peer.get_available_bytes() > 0:
		var result = peer.get_data(peer.get_available_bytes())
		if result[0] != OK:
			status = "läsfel"
			last_error = error_string(result[0])
			pending = false
			pending_utility_family = ""
			if mode == "control":
				agent.neural_bridge_unavailable(last_error)
			return
		receive_buffer += result[1].get_string_from_utf8()
	while true:
		var newline = receive_buffer.find("\n")
		if newline < 0:
			break
		var line = receive_buffer.substr(0, newline).strip_edges()
		receive_buffer = receive_buffer.substr(newline + 1)
		if line.is_empty():
			continue
		var parsed = JSON.parse_string(line)
		if parsed is Dictionary:
			pending = false
			if parsed.get("ok", false):
				var utility_family = pending_utility_family
				pending_utility_family = ""
				parsed["utility_family"] = utility_family
				parsed["agreement"] = str(parsed.get("selected", "")) == utility_family and not utility_family.is_empty()
				samples += 1
				if parsed.get("agreement", false):
					agreements += 1
				parsed["bridge_status"] = "online"
				parsed["samples"] = samples
				parsed["agreement_rate"] = float(agreements) / maxf(1.0, float(samples))
				parsed["control_mode"] = mode
				parsed["actuator_authority"] = "utility" if mode == "shadow" else "neural"
				parsed["agent_action_before_apply"] = str(agent.current.get("action", ""))
				parsed["agent_family_before_apply"] = agent.action_family(str(agent.current.get("action", "look"))) if not agent.current.is_empty() else ""
				parsed["agent_phase"] = agent.phase
				parsed["agent_position"] = [agent.position.x, agent.position.y, agent.position.z]
				parsed["last_neural_actuation"] = agent.neural_last_actuation.duplicate(true)
				if mode == "control":
					agent.accept_neural_decision(parsed)
				agent.neural_shadow = parsed.duplicate(true)
				append_log(parsed)
			else:
				pending_utility_family = ""
				status = "hjärnfel"
				last_error = str(parsed.get("error", "Okänt NeuralBrain-fel"))
				agent.neural_shadow = {"bridge_status": status, "control_mode": mode, "actuator_authority": "utility" if mode == "shadow" else "neural", "error": last_error, "ok": false}
				if mode == "control":
					agent.neural_bridge_unavailable(last_error)

func append_log(payload: Dictionary) -> void:
	if log_path.is_empty():
		return
	var log = FileAccess.open(log_path, FileAccess.READ_WRITE)
	if log == null:
		return
	log.seek_end()
	log.store_line(JSON.stringify(payload))
	log.close()

func shutdown() -> void:
	if peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		peer.put_data((JSON.stringify({"command": "shutdown"}) + "\n").to_utf8_buffer())
		peer.disconnect_from_host()
	if launched_process and process_id > 0:
		OS.kill(process_id)
	process_id = -1
	launched_process = false
	pending = false
	pending_utility_family = ""
	status = "offline"
