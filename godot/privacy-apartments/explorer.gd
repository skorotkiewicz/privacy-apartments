extends CharacterBody3D

signal privacy_changed(tag: String, is_open: bool)

@export var speed := 6.0
@export var look_sensitivity := 0.002
@export var step_height := 0.35

@onready var camera: Camera3D = $Camera3D
@onready var flashlight: SpotLight3D = $Camera3D/Flashlight
@onready var apartments: Node3D = $"../Apartments"
@onready var prompt: Label = $"../HUD/Prompt"

var use_was_pressed := false

func _ready() -> void:
	camera.make_current()
	floor_snap_length = step_height
	look_at(Vector3(0, global_position.y, 0))
	for node in apartments.get_children():
		if node is MeshInstance3D:
			if str(node.name).begins_with("StairOut_") or str(node.name).begins_with("StairBack_"):
				continue
			node.create_trimesh_collision()
			if str(node.name).begins_with("StairRampCollision_"):
				node.visible = false
			if str(node.name).begins_with("LampBulb_"):
				node.visible = false
				var light := OmniLight3D.new()
				light.name = str(node.name).replace("LampBulb_", "LampLight_")
				light.position = node.position
				light.visible = false
				light.light_energy = 1.0
				light.omni_range = 6.0
				apartments.add_child(light)
	_add_map_boundaries()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _add_map_boundaries() -> void:
	var ground := apartments.get_node_or_null("Ground") as MeshInstance3D
	if not ground:
		return
	var mesh_bounds := ground.get_aabb()
	var bounds := AABB(ground.transform * mesh_bounds.position, Vector3.ZERO)
	for x in [mesh_bounds.position.x, mesh_bounds.end.x]:
		for y in [mesh_bounds.position.y, mesh_bounds.end.y]:
			for z in [mesh_bounds.position.z, mesh_bounds.end.z]:
				bounds = bounds.expand(ground.transform * Vector3(x, y, z))
	var height := 4.0
	var thickness := 1.0
	_add_boundary("MapBoundaryWest", Vector3(bounds.position.x - thickness / 2.0, bounds.end.y + height / 2.0, bounds.get_center().z), Vector3(thickness, height, bounds.size.z + thickness * 2.0))
	_add_boundary("MapBoundaryEast", Vector3(bounds.end.x + thickness / 2.0, bounds.end.y + height / 2.0, bounds.get_center().z), Vector3(thickness, height, bounds.size.z + thickness * 2.0))
	_add_boundary("MapBoundaryNorth", Vector3(bounds.get_center().x, bounds.end.y + height / 2.0, bounds.position.z - thickness / 2.0), Vector3(bounds.size.x + thickness * 2.0, height, thickness))
	_add_boundary("MapBoundarySouth", Vector3(bounds.get_center().x, bounds.end.y + height / 2.0, bounds.end.z + thickness / 2.0), Vector3(bounds.size.x + thickness * 2.0, height, thickness))

func _add_boundary(name: String, position: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	body.name = name
	body.position = position
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	apartments.add_child(body)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * look_sensitivity)
		camera.rotate_x(-event.relative.y * look_sensitivity)
		camera.rotation.x = clamp(camera.rotation.x, -1.5, 1.5)
	elif event.is_action_pressed("ui_accept") and is_on_floor():
		velocity.y = 4.5
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventKey and event.physical_keycode == KEY_F and event.pressed and not event.echo:
		flashlight.visible = not flashlight.visible
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(delta: float) -> void:
	if not PhysicsServer3D.body_get_space(get_rid()).is_valid():
		return
	var was_on_floor := is_on_floor()
	var use_pressed := Input.is_physical_key_pressed(KEY_E)
	if use_pressed and not use_was_pressed:
		_toggle_interactable()
	use_was_pressed = use_pressed

	if not is_on_floor():
		velocity += get_gravity() * delta
	var right := camera.global_transform.basis.x
	var forward := -camera.global_transform.basis.z
	right.y = 0.0
	forward.y = 0.0
	var direction := (right.normalized() * (float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))) + forward.normalized() * (float(Input.is_physical_key_pressed(KEY_W)) - float(Input.is_physical_key_pressed(KEY_S)))).normalized()
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	var start_position := global_position
	var intended_motion := direction * speed * delta
	move_and_slide()
	var actual_motion := global_position - start_position
	actual_motion.y = 0.0
	if was_on_floor and intended_motion.length_squared() > 0.0 and actual_motion.length() < intended_motion.length() * 0.5:
		_try_step_up(intended_motion)
	_update_prompt()

func _try_step_up(motion: Vector3) -> void:
	var parameters := PhysicsTestMotionParameters3D.new()
	var result := PhysicsTestMotionResult3D.new()
	parameters.from = global_transform
	parameters.motion = Vector3.UP * step_height
	if PhysicsServer3D.body_test_motion(get_rid(), parameters):
		return
	var raised := global_transform.translated(Vector3.UP * step_height)
	parameters.from = raised
	parameters.motion = motion
	if PhysicsServer3D.body_test_motion(get_rid(), parameters):
		return
	var target := raised.translated(motion)
	parameters.from = target
	parameters.motion = Vector3.DOWN * (step_height + floor_snap_length)
	if not PhysicsServer3D.body_test_motion(get_rid(), parameters, result):
		return
	if result.get_collision_normal().dot(up_direction) < cos(floor_max_angle):
		return
	global_transform = target.translated(result.get_travel())
	velocity.y = 0.0

func _find_interactable() -> Node3D:
	var query := PhysicsRayQueryParameters3D.create(camera.global_position, camera.global_position - camera.global_transform.basis.z * 4.0)
	query.exclude = [get_rid()]
	var node: Node = get_world_3d().direct_space_state.intersect_ray(query).get("collider")
	while node:
		var object_name := str(node.name)
		if node is MeshInstance3D and (object_name.begins_with("EntranceDoor_") or object_name.begins_with("OpenableWindow_") or object_name.begins_with("Louver_") or object_name.begins_with("LightSwitch") or object_name.begins_with("BlindSwitch_")):
			return node as Node3D
		node = node.get_parent()
	return null

func _update_prompt() -> void:
	var object := _find_interactable()
	prompt.text = ""
	if not object:
		return
	var object_name := str(object.name)
	if object_name.begins_with("Louver_") or object_name.begins_with("BlindSwitch_"):
		prompt.text = "[ E ]  %s PRIVACY SEAL" % ("CLOSE" if object.get_meta("open", false) else "OPEN")
	elif object_name.begins_with("LightSwitch"):
		prompt.text = "[ E ]  TOGGLE LIGHT"
	else:
		prompt.text = "[ E ]  %s" % ("CLOSE" if object.get_meta("open", false) else "OPEN")

func _toggle_interactable() -> void:
	var object := _find_interactable()
	if not object:
		return
	if str(object.name).begins_with("Louver_") or str(object.name).begins_with("BlindSwitch_"):
		_toggle_blinds(object)
		return
	if str(object.name).begins_with("LightSwitch"):
		_toggle_light(object)
		return
	var closed_y: float = object.get_meta("closed_y", object.rotation.y)
	var opening: bool = not object.get_meta("open", false)
	var direction := -1.0 if str(object.name).ends_with("_Right") else 1.0
	object.set_meta("closed_y", closed_y)
	object.set_meta("open", opening)
	object.create_tween().tween_property(object, "rotation:y", closed_y + (direction * PI / 2.0 if opening else 0.0), 0.25)

func _toggle_light(light_switch: Node3D) -> void:
	var switch_name := str(light_switch.name)
	var tag := switch_name.substr(switch_name.find("_") + 1)
	var extras: Dictionary = light_switch.get_meta("extras", {})
	var controlled_name := str(extras.get("controls", "LampLight_" + tag))
	var light := apartments.get_node_or_null(NodePath(controlled_name))
	if light:
		light.visible = not light.visible
		var bulb := apartments.get_node_or_null(NodePath("LampBulb_" + tag))
		if bulb:
			bulb.visible = light.visible

func _toggle_blinds(hit_blind: Node3D) -> void:
	var prefix := str(hit_blind.name)
	if prefix.begins_with("BlindSwitch_"):
		prefix = "Louver_" + prefix.trim_prefix("BlindSwitch_")
	else:
		prefix = prefix.substr(0, prefix.rfind("_"))
	var tag := prefix.trim_prefix("Louver_")
	var opening: bool = not hit_blind.get_meta("open", false)
	var blind_switch := apartments.get_node_or_null(NodePath("BlindSwitch_" + tag))
	if blind_switch:
		blind_switch.set_meta("open", opening)
	for node in apartments.get_children():
		if node is MeshInstance3D and str(node.name).begins_with(prefix + "_"):
			var closed_y: float = node.get_meta("closed_y", node.position.y)
			node.set_meta("closed_y", closed_y)
			node.set_meta("open", opening)
			node.create_tween().tween_property(node, "position:y", closed_y + (1.4 if opening else 0.0), 0.25)
	privacy_changed.emit(tag, opening)
