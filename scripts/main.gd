extends Node3D
const World = preload("res://scripts/world/world_state.gd")
const Agent = preload("res://scripts/cognition/agent.gd")
const Persistence = preload("res://scripts/persistence.gd")
const Lab = preload("res://scripts/view/lab_view.gd")
const Inspector = preload("res://scripts/view/inspector.gd")
const NeuralBridge = preload("res://scripts/cognition/neural_brain_bridge.gd")
var world
var agent
var persistence
var lab
var inspector
var neural
var paused = false
var speed = 1.0
var accumulator = 0.0
var save_clock = 0.0
var ui_clock = 0.0
var total_runtime = 0.0
var smoke_mode = false
var capture_path = ""
var quit_after = -1.0
var allow_save = true
var neural_mode = "control"

func _ready() -> void:
	get_tree().auto_accept_quit = false
	var save_path = ""
	for arg in OS.get_cmdline_user_args():
		if arg == "--smoke":
			smoke_mode = true
			allow_save = false
		elif arg.begins_with("--capture="):
			capture_path = arg.trim_prefix("--capture=")
		elif arg.begins_with("--quit-after="):
			quit_after = float(arg.trim_prefix("--quit-after="))
		elif arg.begins_with("--save-path="):
			save_path = arg.trim_prefix("--save-path=")
		elif arg == "--neural-shadow":
			neural_mode = "shadow"
		elif arg == "--neural-control":
			neural_mode = "control"
	world = World.new()
	agent = Agent.new(world, 20260910 if smoke_mode else int(Time.get_unix_time_from_system()))
	persistence = Persistence.new(save_path)
	if not smoke_mode:
		persistence.load_into(agent, world)
	neural = NeuralBridge.new()
	if not smoke_mode:
		agent.set_neural_control(neural_mode == "control")
		neural.start(neural_mode)
	lab = Lab.new()
	add_child(lab)
	lab.build(world)
	inspector = Inspector.new()
	add_child(inspector)
	inspector.interaction.connect(interact)
	inspector.speed_changed.connect(func(value): speed = value)
	inspector.pause_changed.connect(func(): paused = not paused)
	inspector.save_requested.connect(save)
	DisplayServer.window_set_title("BirdAI · Alma — en autonom liten fågel")
	if smoke_mode:
		speed = 3.0
	print("BirdAI ready. Individual: ", agent.individual_id, " | Save: ", persistence.path, " | Neural mode: ", neural_mode)

func _process(dt: float) -> void:
	total_runtime += dt
	if not paused:
		accumulator += minf(dt, 0.15) * speed
		while accumulator >= 1.0 / 60:
			agent.step(1.0 / 60)
			accumulator -= 1.0 / 60
	lab.update(agent, dt * speed if not paused else 0)
	if neural != null and not smoke_mode:
		neural.tick(dt, agent)
	ui_clock += dt
	if ui_clock >= 0.15:
		inspector.update(agent, persistence, paused, speed, ui_clock)
		ui_clock = 0
	save_clock += dt
	if save_clock >= 15:
		save_clock = 0
		save(false)
	if not capture_path.is_empty() and total_runtime > 4.0:
		var target = capture_path
		capture_path = ""
		capture.call_deferred(target)
	if quit_after > 0 and total_runtime >= quit_after:
		save(false)
		print("BirdAI smoke complete: ", agent.decision_count, " decisions; ", agent.memory.total_episodes, " episodes.")
		if neural != null:
			neural.shutdown()
		get_tree().quit()

func capture(path: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(path)

func save(announce: bool = true) -> void:
	if not allow_save:
		return
	var success = persistence.save(agent, world)
	if announce:
		inspector.announce("Samma individ sparad." if success else persistence.message)

func interact(kind: String) -> void:
	match kind:
		"experiment":
			var result = world.press_food_button(true)
			if result.success:
				inspector.announce("Den gula experimentknappen öppnade luckan. Ett litet frö finns bakom den.")
			elif world.experiment_wait() > 0:
				var remaining = int(ceil(world.experiment_wait()))
				inspector.announce("Experimentknappen är redo om %d:%02d simulerade minuter." % [remaining / 60, remaining % 60])
			else:
				inspector.announce(result.outcome)
		"refill":
			var result = world.refill_food_bowl(4.0, "o8")
			inspector.announce(result.outcome)
		"call":
			if world.objects.o8.active:
				world.emit_event("o8", world.objects.o8.position, 0.28, "Ett mjukt lockläte från människan.")
				inspector.announce("Ett lugnt ljud från din plats.")
		"touch":
			inspector.announce(agent.touch())
		"presence":
			world.objects.o8.active = not world.objects.o8.active
			world.emit_event("o8", world.objects.o8.position, 0.3, "Människan kom tillbaka." if world.objects.o8.active else "Människan gick ut.")
			inspector.announce(world.last_event)
		"noise":
			world.emit_event("o8", world.objects.o8.position, 1.0, "Ett plötsligt ljud från människans plats.")
			inspector.announce("Ett kort ljud. Se hur trygghet påverkar valet.")

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		lab.orbit -= event.relative.x * 0.008
		lab.elevation = clampf(lab.elevation + event.relative.y * 0.006, 0.32, 1.25)
		lab.update_camera()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			lab.zoom = clampf(lab.zoom - 0.6, 6, 22)
			lab.update_camera()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			lab.zoom = clampf(lab.zoom + 0.6, 6, 22)
			lab.update_camera()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			var point = lab.ground_point(event.position)
			if point != null and world.flat_distance(point, world.objects.o5.position) < 0.42:
				interact("experiment")
			elif point != null and absf(point.x) < world.WALK_LIMIT and absf(point.z) < world.WALK_LIMIT:
				world.objects.o8.position = Vector3(point.x, 0, point.z)
				world.objects.o8.active = true
				world.emit_event("o8", world.objects.o8.position, 0.25, "Människan flyttade sig.")
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			paused = not paused
		elif event.keycode == KEY_S and event.ctrl_pressed:
			save()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		save(false)
		if neural != null:
			neural.shutdown()
		get_tree().quit()

func _exit_tree() -> void:
	if neural != null:
		neural.shutdown()
