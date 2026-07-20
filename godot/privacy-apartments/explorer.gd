extends CharacterBody3D

@export var speed := 6.0
@export var look_sensitivity := 0.002

@onready var camera: Camera3D = $Camera3D
@onready var flashlight: SpotLight3D = $Camera3D/Flashlight
@onready var apartments: Node3D = $"../Apartments"

var use_was_pressed := false

func _ready() -> void:
	camera.make_current()
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
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

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
	move_and_slide()

func _toggle_interactable() -> void:
	var query := PhysicsRayQueryParameters3D.create(camera.global_position, camera.global_position - camera.global_transform.basis.z * 4.0)
	query.exclude = [get_rid()]
	var node: Node = get_world_3d().direct_space_state.intersect_ray(query).get("collider")
	while node:
		var object_name := str(node.name)
		if node is MeshInstance3D and (object_name.begins_with("EntranceDoor_") or object_name.begins_with("OpenableWindow_") or object_name.begins_with("Louver_") or object_name.begins_with("LightSwitch") or object_name.begins_with("BlindSwitch_")):
			break
		node = node.get_parent()
	if not node:
		return
	var object := node as Node3D
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
	var opening: bool = not hit_blind.get_meta("open", false)
	hit_blind.set_meta("open", opening)
	for node in apartments.get_children():
		if node is MeshInstance3D and str(node.name).begins_with(prefix + "_"):
			var closed_y: float = node.get_meta("closed_y", node.position.y)
			node.set_meta("closed_y", closed_y)
			node.set_meta("open", opening)
			node.create_tween().tween_property(node, "position:y", closed_y + (1.4 if opening else 0.0), 0.25)
