extends Node3D

const MAX_ATTENTION := 100.0

@export_category("Building Layout")
@export_range(1, 100, 1) var floors := 12
@export_range(1, 100, 1) var units_per_floor := 8
@export_range(1, 100, 1) var blinds_to_close := 4

@onready var player: Node3D = $Player
@onready var camera: Camera3D = $Player/Camera3D
@onready var flashlight: SpotLight3D = $Player/Camera3D/Flashlight
@onready var apartments: Node3D = $Apartments
@onready var objective: Label = $HUD/Objective
@onready var threat: ProgressBar = $HUD/Threat
@onready var threat_value: Label = $HUD/ThreatValue
@onready var message: Label = $HUD/Message
@onready var ending: ColorRect = $HUD/Ending
@onready var ending_text: Label = $HUD/Ending/Text
@onready var drone: AudioStreamPlayer = $Drone
@onready var heartbeat: AudioStreamPlayer = $Heartbeat
@onready var sfx: AudioStreamPlayer = $SFX

var breaches: Array[String] = []
var attention := 8.0
var watcher: Node3D
var watcher_tag := ""
var move_wait := 0.0
var gaze_warning_wait := 0.0
var game_over := false
var message_tween: Tween

func _ready() -> void:
	player.connect("privacy_changed", _on_privacy_changed)
	var room_tags: Array[String] = []
	for floor in range(floors):
		for unit in range(units_per_floor):
			room_tags.append("F%02d_U%02d" % [floor, unit])
	room_tags.shuffle()
	assert(blinds_to_close <= room_tags.size(), "Cannot open %d blinds in a %dx%d building" % [blinds_to_close, floors, units_per_floor])
	for index in range(blinds_to_close):
		var tag := room_tags[index]
		if _set_privacy(tag, true):
			breaches.append(tag)
	assert(breaches.size() == blinds_to_close, "Expected privacy controls are missing from the model")
	_add_door_numbers()
	watcher = _make_watcher()
	apartments.add_child(watcher)
	_move_watcher()
	if DisplayServer.get_name() != "headless":
		drone.stream = _make_drone()
		drone.play()
		heartbeat.stream = _make_heartbeat()
		heartbeat.play()
	_say("PRIVACY PROTOCOL FAILED\nDo not let it learn your face.", 4.0)
	_update_hud()

func _process(delta: float) -> void:
	if game_over:
		return

	move_wait -= delta
	gaze_warning_wait -= delta
	if move_wait <= 0.0:
		_move_watcher()
		move_wait = 4.0

	watcher.look_at(player.global_position, Vector3.UP)
	var gazing := _is_gazing_at_watcher()
	attention += delta * (0.18 + breaches.size() * 0.13 + (0.12 if flashlight.visible else 0.0))
	if gazing:
		attention += delta * 7.5
		if gaze_warning_wait <= 0.0:
			_say("LOOK AWAY", 0.7)
			gaze_warning_wait = 1.8
	var watcher_distance := player.global_position.distance_to(watcher.global_position)
	if watcher_distance < 3.0:
		attention += delta * 4.0

	var now := Time.get_ticks_msec() * 0.001
	var fear := maxf(clampf(attention / MAX_ATTENTION, 0.0, 1.0), 1.0 - clampf(watcher_distance / 12.0, 0.0, 1.0))
	heartbeat.volume_db = lerpf(-32.0, -5.0, fear)
	heartbeat.pitch_scale = lerpf(0.8, 1.55, fear)
	camera.fov = 75.0 + sin(now * 2.5) * fear * fear * 1.6
	var flicker := attention > 55.0 and sin(now * 31.0) + sin(now * 17.0) > 1.72
	flashlight.light_energy = 0.35 if flicker else 6.5
	for tag in breaches:
		var alarm := apartments.get_node_or_null(NodePath("LampLight_" + tag)) as OmniLight3D
		if alarm:
			alarm.light_energy = 1.7 + sin(now * 7.0 + tag.hash()) * 0.45

	if attention >= MAX_ATTENTION:
		_finish(false)
	_update_hud()

func _unhandled_input(event: InputEvent) -> void:
	if game_over and event is InputEventKey and event.physical_keycode == KEY_R and event.pressed and not event.echo:
		get_tree().call_deferred("reload_current_scene")

func _exit_tree() -> void:
	drone.stop()
	drone.stream = null
	heartbeat.stop()
	heartbeat.stream = null
	sfx.stop()
	sfx.stream = null

func _on_privacy_changed(tag: String, is_open: bool) -> void:
	if game_over:
		return
	if is_open:
		if tag not in breaches:
			breaches.append(tag)
		_say("A NEW SIGHTLINE OPENED", 1.4)
		_play_sound(70.0, 520.0, 0.5, 0.35)
	else:
		breaches.erase(tag)
		attention = maxf(0.0, attention - 14.0)
		_say("SIGHTLINE SEVERED", 1.2)
		_play_sound(180.0, 55.0, 0.32, 0.2)
	_set_alarm(tag, is_open)
	if breaches.is_empty():
		_finish(true)
	elif watcher_tag == tag:
		_move_watcher()
	_update_hud()

func _set_privacy(tag: String, is_open: bool) -> bool:
	var blind_switch := apartments.get_node_or_null(NodePath("BlindSwitch_" + tag)) as Node3D
	if not blind_switch:
		return false
	blind_switch.set_meta("open", is_open)
	var prefix := "Louver_" + tag + "_"
	for child in apartments.get_children():
		if child is MeshInstance3D and str(child.name).begins_with(prefix):
			var closed_y: float = child.get_meta("closed_y", child.position.y)
			child.set_meta("closed_y", closed_y)
			child.set_meta("open", is_open)
			child.position.y = closed_y + (1.4 if is_open else 0.0)
	_set_alarm(tag, is_open)
	return true

func _set_alarm(tag: String, enabled: bool) -> void:
	var alarm := apartments.get_node_or_null(NodePath("LampLight_" + tag)) as OmniLight3D
	var bulb := apartments.get_node_or_null(NodePath("LampBulb_" + tag)) as MeshInstance3D
	if alarm:
		alarm.visible = enabled
		alarm.light_color = Color(0.75, 0.025, 0.015)
		alarm.light_energy = 1.8
		alarm.omni_range = 7.0
	if bulb:
		bulb.visible = enabled

func _move_watcher() -> void:
	var nearest := _nearest_breach()
	if nearest.is_empty():
		return
	var blind_switch := apartments.get_node(NodePath("BlindSwitch_" + nearest)) as Node3D
	var changed_rooms := watcher_tag != nearest and not watcher_tag.is_empty()
	watcher_tag = nearest
	watcher.position = Vector3(blind_switch.position.x - 2.97, blind_switch.position.y, blind_switch.position.z + 1.45)
	if changed_rooms:
		_say("SOMETHING MOVED BEHIND THE GLASS", 1.2)
		_play_sound(55.0, 28.0, 0.85, 0.55)

func _nearest_breach() -> String:
	var nearest := ""
	var nearest_distance := INF
	for tag in breaches:
		var blind_switch := apartments.get_node_or_null(NodePath("BlindSwitch_" + tag)) as Node3D
		if blind_switch:
			var distance: float = player.global_position.distance_to(blind_switch.global_position)
			if distance < nearest_distance:
				nearest = tag
				nearest_distance = distance
	return nearest

func _is_gazing_at_watcher() -> bool:
	var offset := watcher.global_position + Vector3.UP * 0.45 - camera.global_position
	return offset.length() < 12.0 and (-camera.global_transform.basis.z).dot(offset.normalized()) > 0.955

func _update_hud() -> void:
	threat.value = attention
	threat_value.text = "THE WATCHING  %02d%%" % mini(99, int(attention))
	var nearest := _nearest_breach()
	if nearest.is_empty():
		objective.text = "PRIVACY RESTORED"
		return
	var target := apartments.get_node(NodePath("BlindSwitch_" + nearest)) as Node3D
	var distance: float = player.global_position.distance_to(target.global_position)
	objective.text = "SEAL THE EXPOSED APARTMENTS  %d REMAIN\nNearest: %s  ·  %.0f m" % [breaches.size(), _describe_tag(nearest), distance]

func _add_door_numbers() -> void:
	var model_door_count := 0
	for child in apartments.get_children():
		if str(child.name).begins_with("EntranceDoor_"):
			model_door_count += 1
	assert(model_door_count == floors * units_per_floor, "Godot layout is %dx%d but the model contains %d apartment doors" % [floors, units_per_floor, model_door_count])

	for floor in range(floors):
		for unit in range(units_per_floor):
			var tag := "F%02d_U%02d" % [floor, unit]
			var door := apartments.get_node_or_null(NodePath("EntranceDoor_" + tag)) as Node3D
			if not door:
				continue
			var number := Label3D.new()
			number.name = "Number"
			number.text = "%d%02d" % [floor + 1, unit + 1]
			number.position = Vector3(0.575, 0.7, 0.08)
			number.font_size = 24
			number.outline_size = 5
			number.pixel_size = 0.006
			number.shaded = true # lighting
			number.modulate = Color(0.82, 0.78, 0.64)
			door.add_child(number)

func _describe_tag(tag: String) -> String:
	var parts := tag.split("_")
	return "FLOOR %d / UNIT %d" % [str(parts[0]).trim_prefix("F").to_int() + 1, str(parts[1]).trim_prefix("U").to_int() + 1]

func _finish(won: bool) -> void:
	game_over = true
	player.process_mode = Node.PROCESS_MODE_DISABLED
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if won:
		ending.visible = true
		ending_text.text = "NO ONE CAN SEE IN.\n\nPRIVACY RESTORED\n\nR  —  TRY AGAIN"
		_play_sound(220.0, 440.0, 1.2, 0.05)
		watcher.visible = false
	else:
		_jumpscare()

func _jumpscare() -> void:
	_play_sound(620.0, 35.0, 0.8, 0.8)
	watcher.reparent(camera, false)
	watcher.position = Vector3(0.0, -1.02, -4.0)
	watcher.rotation = Vector3(0.0, PI, 0.0)
	watcher.scale = Vector3.ONE
	var lunge := create_tween().set_parallel()
	lunge.tween_property(watcher, "position:z", -0.55, 0.22).set_trans(Tween.TRANS_EXPO).set_ease(Tween.EASE_IN)
	lunge.tween_property(watcher, "scale", Vector3.ONE * 1.18, 0.22).set_trans(Tween.TRANS_EXPO).set_ease(Tween.EASE_IN)
	await lunge.finished
	await get_tree().create_timer(0.12).timeout
	ending.visible = true
	ending_text.text = "IT KNOWS YOUR FACE.\n\nTHE WATCHING IS INSIDE\n\nR  —  TRY AGAIN"

func _say(text: String, hold: float) -> void:
	if message_tween:
		message_tween.kill()
	message.text = text
	message.modulate.a = 1.0
	message_tween = create_tween()
	message_tween.tween_interval(hold)
	message_tween.tween_property(message, "modulate:a", 0.0, 0.6)

func _make_watcher() -> Node3D:
	var root := Node3D.new()
	root.name = "TheWatching"

	var shadow := StandardMaterial3D.new()
	shadow.albedo_color = Color(0.001, 0.001, 0.002)
	shadow.roughness = 1.0
	var body := MeshInstance3D.new()
	var body_mesh := CapsuleMesh.new()
	body_mesh.radius = 0.28
	body_mesh.height = 2.45
	body.mesh = body_mesh
	body.material_override = shadow
	root.add_child(body)

	var head := MeshInstance3D.new()
	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.27
	head_mesh.height = 0.72
	head.mesh = head_mesh
	head.position.y = 0.95
	head.material_override = shadow
	root.add_child(head)

	var glow := StandardMaterial3D.new()
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.albedo_color = Color(0.8, 0.01, 0.005)
	glow.emission_enabled = true
	glow.emission = Color(1.0, 0.005, 0.0)
	glow.emission_energy_multiplier = 5.0
	for x in [-0.10, 0.10]:
		var eye := MeshInstance3D.new()
		var eye_mesh := SphereMesh.new()
		eye_mesh.radius = 0.045
		eye_mesh.height = 0.09
		eye.mesh = eye_mesh
		eye.position = Vector3(x, 1.02, -0.25)
		eye.material_override = glow
		root.add_child(eye)
	return root

func _play_sound(start_hz: float, end_hz: float, duration: float, grit: float) -> void:
	if DisplayServer.get_name() == "headless":
		return
	sfx.stream = _make_sound(start_hz, end_hz, duration, grit)
	sfx.play()

func _make_sound(start_hz: float, end_hz: float, duration: float, grit: float) -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_8_BITS
	stream.mix_rate = 11025
	var frame_count := int(stream.mix_rate * duration)
	var samples := PackedByteArray()
	samples.resize(frame_count)
	var phase := 0.0
	for frame in range(frame_count):
		var progress := float(frame) / frame_count
		var frequency := lerpf(start_hz, end_hz, progress)
		phase += TAU * frequency / stream.mix_rate
		var envelope := sin(progress * PI)
		var wave := sin(phase) * (1.0 - grit) + sin(phase * 7.13) * grit
		samples[frame] = int(wave * envelope * 110.0) & 0xff
	stream.data = samples
	return stream

func _make_heartbeat() -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_8_BITS
	stream.mix_rate = 11025
	stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
	stream.loop_end = int(stream.mix_rate * 1.2)
	var samples := PackedByteArray()
	samples.resize(stream.loop_end)
	for frame in range(stream.loop_end):
		var cycle := float(frame) / stream.mix_rate
		var sample := 0.0
		for offset in [0.0, 0.24]:
			var age: float = cycle - float(offset)
			if age >= 0.0 and age < 0.22:
				sample += sin(age * TAU * 52.0) * exp(-age * 20.0) * (1.0 if offset == 0.0 else 0.7)
		samples[frame] = int(clampf(sample, -1.0, 1.0) * 100.0) & 0xff
	stream.data = samples
	return stream

func _make_drone() -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_8_BITS
	stream.mix_rate = 11025
	stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
	stream.loop_end = stream.mix_rate * 4
	var samples := PackedByteArray()
	samples.resize(stream.loop_end)
	for frame in range(stream.loop_end):
		var time := float(frame) / stream.mix_rate
		var pulse := sin(time * TAU * 43.0) * 0.38 + sin(time * TAU * 47.0) * 0.24
		var tremolo := 0.65 + sin(time * TAU * 0.25) * 0.2
		samples[frame] = int(pulse * tremolo * 127.0) & 0xff
	stream.data = samples
	return stream
