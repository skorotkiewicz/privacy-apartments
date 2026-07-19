extends CharacterBody3D

@export var speed := 6.0
@export var look_sensitivity := 0.002

@onready var camera: Camera3D = $Camera3D
@onready var apartments: Node3D = $"../Apartments"

func _ready() -> void:
	camera.make_current()
	look_at(Vector3(0, global_position.y, 0))
	for node in apartments.get_children():
		if node is MeshInstance3D:
			node.create_trimesh_collision()
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
