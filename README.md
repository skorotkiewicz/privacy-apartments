# The Last Private Building

A first-person horror game set in a privacy-focused apartment building. Random apartments begin with exposed blinds; close every privacy breach before **The Watching** learns your face.

The building is procedurally generated in Blender, exported as GLB, and played in Godot.

## Requirements

- [Blender](https://www.blender.org/)
- [Godot 4.7](https://godotengine.org/)
- Bash for the rebuild script

Both `blender` and `godot` should be available on your `PATH`.

## Run the game

```bash
godot --path godot/privacy-apartments
```

Or open the project in the editor:

```bash
godot --editor --path godot/privacy-apartments
```

## Controls

| Input | Action |
|---|---|
| `WASD` | Move |
| Mouse | Look |
| `E` | Use doors, windows, lights, and blinds |
| `F` | Toggle flashlight |
| `Space` | Jump |
| `Esc` | Release mouse |
| `R` | Restart after winning or losing |

## Gameplay

- Each new game randomly selects unique apartments with open blinds.
- Close every exposed blind to restore privacy.
- Looking at The Watching, approaching it, and using the flashlight increase its attention.
- High attention causes stronger heartbeat, camera panic, and flashlight flicker.
- Reaching maximum attention triggers a jumpscare and ends the game.

## Configure the building

The geometry and game settings must use the same dimensions.

### Blender geometry

Edit `build_apartments.py`:

```python
FLOORS = 12
UNITS_PER_FLOOR = 8
```

### Godot gameplay

Select the `ApartmentExplorer` root node in `main.tscn` and edit **Building Layout** in the Inspector, or change the defaults near the top of `game.gd`:

```gdscript
@export_range(1, 100, 1) var floors := 12
@export_range(1, 100, 1) var units_per_floor := 8
@export_range(1, 100, 1) var blinds_to_close := 4
```

`blinds_to_close` controls how many unique rooms the player must seal. It cannot exceed `floors * units_per_floor`.

Godot checks the imported apartment count at startup and reports a clear error if its layout settings do not match the model.

## Rebuild the building

After changing the Blender geometry settings, run:

```bash
./rebuild_model.sh
```

This command:

1. Generates `privacy_apartments.blend` with Blender.
2. Exports `privacy_apartments.glb`.
3. Copies the GLB into `godot/privacy-apartments/assets/`.

Godot automatically reimports the model when the project opens. For CI or other fully headless workflows, trigger the import manually:

```bash
godot --headless --editor --path godot/privacy-apartments --quit
```

## Project structure

```text
build_apartments.py                         Procedural Blender building generator
rebuild_model.sh                            Blender → GLB → Godot rebuild command
privacy_apartments.blend                    Generated Blender scene
privacy_apartments.glb                      Generated root GLB
godot/privacy-apartments/assets/            Godot model assets
godot/privacy-apartments/main.tscn          Main game scene
godot/privacy-apartments/game.gd            Horror game loop and objectives
godot/privacy-apartments/explorer.gd        First-person movement and interaction
```

## Smoke test

```bash
godot --headless --path godot/privacy-apartments --quit-after 3
```
