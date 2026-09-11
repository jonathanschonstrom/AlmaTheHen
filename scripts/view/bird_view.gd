extends Node3D
const M = preload("res://scripts/view/mesh_factory.gd")
var torso: Node3D
var head: Node3D
var left_wing: Node3D
var right_wing: Node3D
var legs = []
var eyes = []
var timer = 0.0
var audio: AudioStreamPlayer3D
var last_call_count = 0

func _ready() -> void:
	var gold = M.material(Color("a76b35"))
	var honey = M.material(Color("cc9453"))
	var light = M.material(Color("dcb775"))
	var dark = M.material(Color("573e30"))
	var black = M.material(Color("201e18"), 0.25)
	var red = M.material(Color("b54938"))
	var beak = M.material(Color("d8ad5f"))
	var foot = M.material(Color("ad8658"))
	torso = Node3D.new()
	add_child(torso)
	M.sphere(torso, Vector3(0, 0.63, 0.02), Vector3(0.32, 0.37, 0.45), gold)
	M.sphere(torso, Vector3(0, 0.65, -0.23), Vector3(0.27, 0.33, 0.28), honey)
	M.sphere(torso, Vector3(0, 0.82, -0.28), Vector3(0.19, 0.29, 0.19), light)
	# Layered hackle feathers and a raised, short hen tail.
	for side in [-1, 1]:
		for i in range(7):
			var feather = M.sphere(torso, Vector3(side * (0.13 + i * 0.012), 0.84 - i * 0.042, -0.22 + i * 0.018), Vector3(0.047, 0.13, 0.055), honey if i % 2 == 0 else light)
			feather.rotation.z = side * 0.22
	for i in range(7):
		var tail = M.sphere(torso, Vector3((i - 3) * 0.05, 0.78 + absf(i - 3) * 0.018, 0.41), Vector3(0.06, 0.28, 0.09), dark if i % 2 == 0 else gold)
		tail.rotation.x = 0.65
		tail.rotation.z = (i - 3) * 0.11
	left_wing = make_wing(-1, gold, honey, dark)
	right_wing = make_wing(1, gold, honey, dark)
	head = Node3D.new()
	head.position = Vector3(0, 1.03, -0.36)
	torso.add_child(head)
	M.sphere(head, Vector3.ZERO, Vector3(0.185, 0.215, 0.195), light)
	for side in [-1, 1]:
		M.sphere(head, Vector3(side * 0.165, 0.015, -0.075), Vector3(0.032, 0.048, 0.046), honey)
		eyes.append(M.sphere(head, Vector3(side * 0.188, 0.025, -0.08), Vector3(0.016, 0.032, 0.032), black))
		M.sphere(head, Vector3(side * 0.20, 0.037, -0.093), Vector3(0.006, 0.009, 0.008), M.material(Color("fff7d9")))
		M.sphere(head, Vector3(side * 0.045, -0.18, -0.1), Vector3(0.046, 0.09, 0.038), red)
	var bill = M.cylinder(head, Vector3(0, -0.035, -0.22), 0.077, 0.20, beak, 0.005)
	bill.rotation.x = -PI / 2
	for i in range(5):
		M.sphere(head, Vector3(0, 0.19 + sin(float(i) / 4 * PI) * 0.07, -0.12 + i * 0.052), Vector3(0.039, 0.09, 0.046), red)
	for side in [-1, 1]:
		var leg = Node3D.new()
		leg.position = Vector3(side * 0.13, 0.31, 0.015)
		add_child(leg)
		M.beam(leg, Vector3.ZERO, Vector3(0, -0.25, 0.01), 0.022, foot)
		for toe in range(3):
			M.beam(leg, Vector3(0, -0.25, 0.01), Vector3((toe - 1) * 0.061, -0.285, -0.14 + absf(toe - 1) * 0.035), 0.013, foot)
		M.beam(leg, Vector3(0, -0.25, 0.02), Vector3(0, -0.27, 0.10), 0.012, foot)
		legs.append(leg)
	audio = AudioStreamPlayer3D.new()
	audio.volume_db = -23
	audio.max_distance = 14
	audio.stream = make_cluck()
	add_child(audio)

func make_wing(side: int, gold: Material, honey: Material, dark: Material) -> Node3D:
	var wing = Node3D.new()
	wing.position = Vector3(side * 0.27, 0.77, 0.0)
	torso.add_child(wing)
	M.sphere(wing, Vector3(side * 0.025, -0.05, 0.05), Vector3(0.095, 0.19, 0.30), gold)
	for i in range(7):
		var feather = M.sphere(wing, Vector3(side * (0.07 + i * 0.004), -0.1 - i * 0.012, 0.02 + i * 0.037), Vector3(0.035, 0.15, 0.095), honey if i % 2 == 0 else dark)
		feather.rotation.x = -0.35
	return wing

func update(agent, dt: float) -> void:
	timer += dt
	position = agent.position
	var wanted = atan2(-agent.heading.x, -agent.heading.z)
	rotation.y = lerp_angle(rotation.y, wanted, minf(1, dt * 9))
	var moving = agent.phase == "approach"
	var action = agent.current.get("action", "look")
	var active = agent.phase == "act"
	torso.position.y = absf(sin(timer * 10)) * 0.022 if moving else sin(timer * 2.1) * 0.008
	torso.rotation.x = 0
	head.rotation.x = 0
	head.rotation.z = sin(timer * 1.7) * 0.055
	head.rotation.y = sin(timer * 1.1) * 0.18 if not moving else 0.0
	for i in range(2):
		legs[i].rotation.x = sin(timer * 10 + i * PI) * 0.45 if moving else 0
	left_wing.rotation.z = 0
	right_wing.rotation.z = 0
	if agent.phase == "ascend" or agent.phase == "descend":
		var spread = 0.75 + (sin(timer * 34) * 0.8 if agent.ascent_powered and agent.phase == "ascend" else 0.0)
		left_wing.rotation.z = -spread
		right_wing.rotation.z = spread
	if not agent.support_id.is_empty():
		torso.rotation.z = sin(timer * 1.8) * 0.025
	else:
		torso.rotation.z = 0
	if active:
		match action:
			"eat", "drink", "peck", "bite":
				var peck = maxf(0, sin(timer * 7))
				torso.rotation.x = peck * 0.45
				head.rotation.x = peck * 0.9
			"scratch":
				legs[0].rotation.x = sin(timer * 12) * 0.9
				head.rotation.x = 0.38
			"preen":
				head.rotation.y = 1.4 + sin(timer * 5) * 0.25
				head.rotation.x = 0.35
			"rest", "perch":
				torso.position.y = -0.14
				head.rotation.x = 0.17
			"dust_bath":
				torso.position.y = -0.17
				torso.rotation.z = sin(timer * 8) * 0.45
				left_wing.rotation.z = -0.75
				right_wing.rotation.z = 0.75
			"wings":
				var flap = 0.55 + sin(timer * 34) * 0.85
				left_wing.rotation.z = -flap
				right_wing.rotation.z = flap
	for eye in eyes:
		eye.scale.y = 0.003 if (fmod(timer, 5.3) > 5.12 or (active and action in ["rest", "perch"])) else 0.032
	var calls = int(agent.learning.skills.get("call", {}).get("attempts", 0))
	if calls > last_call_count:
		audio.play()
	last_call_count = calls

func make_cluck() -> AudioStreamWAV:
	var stream = AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 22050
	var bytes = PackedByteArray()
	var count = 7000
	bytes.resize(count * 2)
	for i in range(count):
		var t = float(i) / 22050
		var envelope = exp(-t * 15) * minf(1, t * 120)
		var sample = sin(TAU * (520 * t - 340 * t * t)) * envelope * 0.35
		bytes.encode_s16(i * 2, int(sample * 32760))
	stream.data = bytes
	return stream
