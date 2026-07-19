extends CharacterBody3D

@export var speed := 6.0
@export var look_sensitivity := 0.002

@onready var camera: Camera3D = $Camera3D
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
		if node is MeshInstance3D and (object_name.begins_with("EntranceDoor_") or object_name.begins_with("OpenableWindow_")):
			break
		node = node.get_parent()
	if not node:
		return
	var object := node as Node3D
	var closed_y: float = object.get_meta("closed_y", object.rotation.y)
	var opening: bool = not object.get_meta("open", false)
	var direction := -1.0 if str(object.name).ends_with("_Right") else 1.0
	object.set_meta("closed_y", closed_y)
	object.set_meta("open", opening)
	object.create_tween().tween_property(object, "rotation:y", closed_y + (direction * PI / 2.0 if opening else 0.0), 0.25)
