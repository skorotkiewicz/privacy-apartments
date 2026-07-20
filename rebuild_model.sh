#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
GODOT_PROJECT="$ROOT/godot/privacy-apartments"
export REBUILD_ROOT="$ROOT"

blender --background "$ROOT/privacy_apartments.blend" \
  --python "$ROOT/build_apartments.py" \
  --python-expr "import bpy, os; bpy.ops.export_scene.gltf(filepath=os.path.join(os.environ['REBUILD_ROOT'], 'privacy_apartments.glb'), export_format='GLB', export_extras=True, export_lights=False)"

cp "$ROOT/privacy_apartments.glb" "$GODOT_PROJECT/assets/privacy_apartments.glb"
# godot --headless --editor --path "$GODOT_PROJECT" --quit

echo "Rebuilt .blend, .glb, and Godot import."
