extends SceneTree

var scene: Node3D

func _init() -> void:
	var packed: PackedScene = load("res://main.tscn")
	scene = packed.instantiate()
	root.add_child(scene)
	call_deferred("check_door")

func check_door() -> void:
	await physics_frame
	var player := scene.get_node("Player") as CharacterBody3D
	var door := scene.get_node("Apartments/EntranceDoor_F00_U01") as Node3D
	var wall := scene.get_node_or_null("Apartments/RearWall_F00_U01")
	player.global_position = Vector3(door.global_position.x + 0.5, 0.0, door.global_position.z + 2.0)
	player.look_at(Vector3(door.global_position.x + 0.5, 0.0, door.global_position.z))
	await physics_frame
	var closed_y: float = door.rotation.y
	player.call("_toggle_door")
	await create_timer(0.35).timeout
	var passed: bool = wall == null and door.get_meta("open", false) and not is_equal_approx(door.rotation.y, closed_y)
	print("real_door_interaction=", "PASS" if passed else "FAIL")
	quit(0 if passed else 1)
