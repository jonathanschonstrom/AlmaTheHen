extends RefCounted

static func material(color: Color, roughness: float = 0.82) -> StandardMaterial3D:
	var mat = StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	return mat

static func mesh(parent: Node3D, shape: Mesh, at: Vector3, size: Vector3, mat: Material) -> MeshInstance3D:
	var node = MeshInstance3D.new()
	node.mesh = shape
	node.material_override = mat
	node.position = at
	node.scale = size
	parent.add_child(node)
	return node

static func sphere(parent: Node3D, at: Vector3, size: Vector3, mat: Material) -> MeshInstance3D:
	var shape = SphereMesh.new()
	shape.radius = 1
	shape.height = 2
	shape.radial_segments = 24
	shape.rings = 12
	return mesh(parent, shape, at, size, mat)

static func box(parent: Node3D, at: Vector3, size: Vector3, mat: Material) -> MeshInstance3D:
	return mesh(parent, BoxMesh.new(), at, size, mat)

static func cylinder(parent: Node3D, at: Vector3, radius: float, height: float, mat: Material, top_radius: float = -1.0) -> MeshInstance3D:
	var shape = CylinderMesh.new()
	shape.top_radius = top_radius if top_radius >= 0 else radius
	shape.bottom_radius = radius
	shape.height = height
	shape.radial_segments = 32
	return mesh(parent, shape, at, Vector3.ONE, mat)

static func beam(parent: Node3D, from: Vector3, to: Vector3, radius: float, mat: Material) -> MeshInstance3D:
	var node = cylinder(parent, (from + to) * 0.5, radius, from.distance_to(to), mat)
	var direction = (to - from).normalized()
	var axis = Vector3.UP.cross(direction)
	if axis.length() > 0.0001:
		node.quaternion = Quaternion(axis.normalized(), acos(clampf(Vector3.UP.dot(direction), -1, 1)))
	return node

static func ring(parent: Node3D, at: Vector3, outer: float, inner: float, mat: Material) -> MeshInstance3D:
	var shape = TorusMesh.new()
	shape.inner_radius = inner
	shape.outer_radius = outer
	shape.rings = 40
	shape.ring_segments = 12
	return mesh(parent, shape, at, Vector3(1, 0.45, 1), mat)

static func label(parent: Node3D, text: String, at: Vector3, color: Color = Color("6a7164")) -> Label3D:
	var node = Label3D.new()
	node.text = text
	node.position = at
	node.font_size = 32
	node.pixel_size = 0.006
	node.modulate = color
	node.outline_size = 3
	node.outline_modulate = Color("f0ead8")
	node.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	node.no_depth_test = true
	parent.add_child(node)
	return node
