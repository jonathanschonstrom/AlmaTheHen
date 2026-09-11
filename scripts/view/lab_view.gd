extends Node3D
const M = preload("res://scripts/view/mesh_factory.gd")
const BirdView = preload("res://scripts/view/bird_view.gd")
var world
var bird: Node3D
var nodes = {}
var hatch: Node3D
var target_ring: Node3D
var camera: Camera3D
var orbit = 0.68
var elevation = 0.76
var distance = 22.0
var zoom = 16.6
var tags = []
var food_visuals = {}
var button_lamp: MeshInstance3D

func build(world_state) -> void:
	world = world_state
	var floor_mat = M.material(Color("c8c3a5"))
	var edge = M.material(Color("797f68"))
	var wood = M.material(Color("ab8255"))
	var wood_light = M.material(Color("c7a773"))
	var terracotta = M.material(Color("af765b"))
	var water = M.material(Color("6ca6b2"), 0.19)
	var seed_mat = M.material(Color("d8b35c"))
	M.box(self, Vector3(0, -0.18, 0), Vector3(12.2, 0.35, 12.2), edge)
	M.box(self, Vector3(0, -0.035, 0), Vector3(12.0, 0.08, 12.0), floor_mat)
	M.box(self, Vector3(0, 0.65, -6), Vector3(12.0, 1.3, 0.14), M.material(Color("d7d3ba")))
	M.box(self, Vector3(-6, 0.65, 0), Vector3(0.14, 1.3, 12.0), M.material(Color("b7bea0")))
	for x in range(14):
		M.box(self, Vector3(-5.6 + x * 0.87, 0.006, 0), Vector3(0.012, 0.008, 11.8), M.material(Color("b9b79b")))
	for id in world.areas:
		var area = world.areas[id]
		M.cylinder(self, area.position + Vector3(0, 0.012, 0), area.radius, 0.015, M.material(area.color))
		var zone_label = M.label(self, area.name.to_upper(), area.position + Vector3(0, 0.08, float(area.radius) + 0.20), Color("62694f"))
		zone_label.font_size = 38
	# A screened sleeping corner with a small roof and two separated roosts.
	M.box(self, Vector3(-5.93, 1.25, -4.1), Vector3(0.10, 2.5, 3.7), wood)
	M.box(self, Vector3(-3.6, 1.25, -5.93), Vector3(4.7, 2.5, 0.10), wood_light)
	M.box(self, Vector3(-3.6, 2.53, -5.35), Vector3(4.8, 0.08, 1.2), wood)
	# Window frames, sparse grasses, scattered straw: all generated primitives.
	for x in [0.0, 2.5, 5.0]:
		M.box(self, Vector3(x, 1.12, -5.90), Vector3(1.9, 0.53, 0.035), M.material(Color("c6d8ce")))
		M.box(self, Vector3(x, 0.85, -5.83), Vector3(2.05, 0.06, 0.2), wood_light)
		M.box(self, Vector3(x, 1.12, -5.81), Vector3(0.045, 0.53, 0.035), wood)
	var random = RandomNumberGenerator.new()
	random.seed = 3451
	for i in range(50):
		var straw = M.box(self, Vector3(random.randf_range(-5.65, 5.65), 0.03, random.randf_range(-5.65, 5.65)), Vector3(random.randf_range(0.06, 0.16), 0.009, 0.014), wood_light)
		straw.rotation.y = random.randf_range(0, TAU)
	for p in [Vector3(-5.5, 0, 4.8), Vector3(5.3, 0, -5.0), Vector3(5.3, 0, 5.1)]:
		M.cylinder(self, p + Vector3(0, 0.2, 0), 0.23, 0.4, terracotta, 0.29)
		for i in range(8):
			M.beam(self, p + Vector3(0, 0.35, 0), p + Vector3(random.randf_range(-0.3, 0.3), random.randf_range(0.65, 1.1), random.randf_range(-0.25, 0.25)), 0.033, M.material(Color("6f8460")))
	for id in world.objects:
		var obj = world.objects[id]
		var root = Node3D.new()
		root.position = obj.position
		add_child(root)
		nodes[id] = root
		match obj.kind:
			"food", "water":
				M.cylinder(root, Vector3(0, 0.08, 0), 0.36, 0.13, terracotta if obj.kind == "food" else M.material(Color("688d91")))
				M.ring(root, Vector3(0, 0.15, 0), 0.38, 0.30, terracotta if obj.kind == "food" else M.material(Color("7e9d9e")))
				var contents = Node3D.new()
				root.add_child(contents)
				M.cylinder(contents, Vector3(0, 0.145, 0), 0.30, 0.018, seed_mat if obj.kind == "food" else water)
				if obj.kind == "food":
					food_visuals[id] = contents
					for i in range(24):
						M.sphere(contents, Vector3(random.randf_range(-0.2, 0.2), 0.17, random.randf_range(-0.2, 0.2)), Vector3(0.024, 0.016, 0.041), seed_mat)
			"ball":
				M.sphere(root, Vector3(0, 0.24, 0), Vector3.ONE * 0.24, M.material(Color("b65e46"), 0.38))
				M.ring(root, Vector3(0, 0.24, 0), 0.245, 0.23, M.material(Color("e0b08b")))
			"box":
				M.box(root, Vector3(0, 0.28, 0), Vector3(0.8, 0.55, 0.75), wood_light)
				for h in [0.08, 0.27, 0.46]:
					M.box(root, Vector3(0, h, 0.385), Vector3(0.82, 0.012, 0.01), wood)
				M.box(root, Vector3(0, 0.56, 0), Vector3(0.86, 0.03, 0.8), wood)
			"button":
				M.cylinder(root, Vector3(0, 0.07, 0), 0.28, 0.14, M.material(Color("526c61")))
				M.cylinder(root, Vector3(0, 0.17, 0), 0.16, 0.08, M.material(Color("e6b753"), 0.3))
				button_lamp = M.sphere(root, Vector3(0, 0.14, -0.23), Vector3(0.08, 0.055, 0.08), M.material(Color("314138"), 0.25))
				button_lamp.material_override.emission_enabled = true
				M.beam(self, obj.position + Vector3(0.25, 0.025, 0), world.objects.o9.position + Vector3(0, 0.025, 0), 0.022, edge)
			"perch":
				for x in [-0.58, 0.58]:
					M.cylinder(root, Vector3(x, -obj.position.y * 0.5, 0), 0.045, obj.position.y, wood)
					M.box(root, Vector3(x, -obj.position.y + 0.04, 0), Vector3(0.17, 0.07, 0.5), wood)
				M.beam(root, Vector3(-0.74, 0, 0), Vector3(0.74, 0, 0), 0.065, wood_light)
			"dust":
				M.ring(root, Vector3(0, 0.045, 0), 1.26, 1.19, wood_light)
			"nest":
				M.sphere(root, Vector3(0, 0.02, 0), Vector3(0.8, 0.045, 0.65), M.material(Color("d4ba7e")))
				for i in range(32):
					var straw = M.box(root, Vector3(random.randf_range(-0.65, 0.65), 0.05, random.randf_range(-0.5, 0.5)), Vector3(0.22, 0.015, 0.022), wood_light)
					straw.rotation.y = random.randf_range(0, TAU)
			"forage":
				for i in range(42):
					var offset = Vector3(random.randf_range(-1.0, 1.0), 0.04, random.randf_range(-1.0, 1.0))
					M.beam(root, offset, offset + Vector3(0.025, random.randf_range(0.06, 0.17), 0.01), 0.012, M.material(Color("8f9b64")))
			"human":
				var human = M.material(Color("719c94"))
				M.ring(root, Vector3(0, 0.02, 0), 0.43, 0.40, human)
				M.cylinder(root, Vector3(0, 0.52, 0), 0.18, 0.76, human, 0.24)
				M.sphere(root, Vector3(0, 1.04, 0), Vector3.ONE * 0.15, M.material(Color("c1cfbd")))
			"cache":
				M.box(root, Vector3(0, 0.18, 0), Vector3(0.7, 0.36, 0.65), wood)
				M.box(root, Vector3(0, 0.05, 0.42), Vector3(0.6, 0.08, 0.45), wood_light)
				var contents = Node3D.new()
				root.add_child(contents)
				food_visuals[id] = contents
				for i in range(12):
					M.sphere(contents, Vector3(random.randf_range(-0.23, 0.23), 0.105, random.randf_range(0.25, 0.56)), Vector3(0.024, 0.016, 0.041), seed_mat)
				hatch = M.box(root, Vector3(0, 0.2, 0.335), Vector3(0.68, 0.38, 0.04), wood_light)
			"treat":
				for i in range(10):
					M.sphere(root, Vector3(random.randf_range(-0.13, 0.13), 0.04, random.randf_range(-0.13, 0.13)), Vector3(0.025, 0.02, 0.04), seed_mat)
		var tag_names = {"o1": "FRÖN", "o2": "VATTEN", "o3": "BOLL", "o4": "LÅDA", "o5": "EXPERIMENT", "o6": "FLYGPLATS", "o7": "", "o8": "DU", "o9": "BELÖNING", "o10": "FRÖN", "o11": "LÅG SITTPINNE", "o12": "STRÖBÄDD", "o13": "", "o14": ""}
		var object_label = M.label(root, tag_names[id], Vector3(0, 0.025, 0.6))
		object_label.pixel_size = 0.0075
		tags.append(object_label)
	target_ring = M.ring(self, Vector3.ZERO, 0.5, 0.475, M.material(Color("d9a853")))
	var env_node = WorldEnvironment.new()
	var env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("1c2b28")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("d8e5df")
	env.ambient_light_energy = 0.36
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.ssao_enabled = true
	env.ssao_radius = 0.6
	env.ssao_intensity = 1.1
	env_node.environment = env
	add_child(env_node)
	var sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-54, -30, 0)
	sun.light_color = Color("ffe6b8")
	sun.light_energy = 1.0
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 25
	add_child(sun)
	var fill = DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-30, 140, 0)
	fill.light_color = Color("bdd9db")
	fill.light_energy = 0.16
	add_child(fill)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.current = true
	camera.far = 100
	add_child(camera)
	update_camera()
	bird = BirdView.new()
	add_child(bird)

func update_camera() -> void:
	camera.position = Vector3(sin(orbit) * cos(elevation), sin(elevation), cos(orbit) * cos(elevation)) * distance
	camera.look_at(Vector3(0, 0.15, 0))
	camera.size = zoom
	camera.h_offset = zoom * 0.2

func update(agent, dt: float) -> void:
	for id in nodes:
		nodes[id].position = world.objects[id].position
		nodes[id].visible = world.objects[id].active
	for id in food_visuals:
		food_visuals[id].visible = world.objects[id].stock > 0 and (id != "o9" or world.hatch_open)
	var lamp_ready = float(world.objects.o5.cues.lit) > 0.5
	button_lamp.material_override.albedo_color = Color("a8ec73") if lamp_ready else Color("314138")
	button_lamp.material_override.emission = Color("72c93d") if lamp_ready else Color.BLACK
	hatch.position.y = lerpf(hatch.position.y, 0.62 if world.hatch_open else 0.2, minf(1, dt * 5))
	var target = agent.current.get("target", agent.senses.focus)
	target_ring.visible = nodes.has(target) and world.objects[target].active
	if target_ring.visible:
		target_ring.position = world.objects[target].position + Vector3(0, 0.03, 0)
		target_ring.position.y = world.support_height(target) + 0.03 if world.is_perch(target) else 0.03
	bird.update(agent, dt)

func ground_point(screen_position: Vector2) -> Variant:
	var origin = camera.project_ray_origin(screen_position)
	var direction = camera.project_ray_normal(screen_position)
	return Plane(Vector3.UP, 0).intersects_ray(origin, direction)
