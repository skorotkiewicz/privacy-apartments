# build_apartments.py
# Generates a privacy-protected apartment building in Blender and saves a .blend file.
#
# Run inside Blender Scripting tab, or from terminal:
#   blender --background --factory-startup --python build_apartments.py

import bpy
import bmesh
import math
import os


# ============================================================
# OUTPUT SETTINGS
# ============================================================

# Default output: user home folder, or the rebuild script's project root.
OUTPUT_BLEND = os.path.join(
    os.environ.get("REBUILD_ROOT", os.path.expanduser("~")),
    "privacy_apartments.blend"
)

# If the current Blender file is already saved, save next to it instead.
if bpy.data.filepath:
    OUTPUT_BLEND = os.path.join(
        os.path.dirname(bpy.data.filepath),
        "privacy_apartments.blend"
    )

SAVE_FILE = True

# WARNING: This deletes all existing objects in the current Blender scene.
CLEAR_EXISTING = True


# ============================================================
# BUILDING PARAMETERS
# ============================================================

FLOORS = 12 # 5
UNITS_PER_FLOOR = 8 # 4

UNIT_W = 6.5          # Apartment width
UNIT_D = 11.0         # Apartment depth
FLOOR_H = 3.3         # Floor-to-floor height

SLAB_T = 0.35         # Slab thickness
WALL_T = 0.30         # General wall thickness
PARTY_WALL_T = 0.45   # Privacy wall between apartments

GLASS_RECESS = 0.85   # How deep the window is inside the facade
JAMB_W = 0.55         # Opaque side reveal width around window
SILL_H = 1.15         # Window sill height
HEAD_H = 2.35         # Window head height

# Lower alpha = more frosted / more private.
# 0.35 is translucent privacy glass.
GLASS_ALPHA = 0.35

FIN_W = 0.35          # Vertical privacy fin width
FIN_PROJECTION = 1.6  # How far fin projects from facade

BALCONY_DEPTH = 2.0
BALCONY_SLAB_T = 0.22
BALCONY_SIDE_H = 2.35
BALCONY_FRONT_SCREEN_H = 2.35

PARAPET_H = 1.25

USE_LOUVERS = True
LOUVER_COUNT = 9


# ============================================================
# INTERIOR ROOM SETTINGS
# ============================================================

# If True, every room gets a real Blender point light.
# This looks nicer but can be heavy with many apartments.
USE_ROOM_LIGHTS = False

# Point light strength.
ROOM_LIGHT_ENERGY = 0.0


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clear_scene():
    """Remove all objects, collections, meshes, materials, cameras, lights."""

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for col in list(bpy.context.scene.collection.children):
        bpy.context.scene.collection.children.unlink(col)

    for col in list(bpy.data.collections):
        if col.users == 0:
            bpy.data.collections.remove(col)

    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)

    for cam in list(bpy.data.cameras):
        if cam.users == 0:
            bpy.data.cameras.remove(cam)

    for light in list(bpy.data.lights):
        if light.users == 0:
            bpy.data.lights.remove(light)

    for world in list(bpy.data.worlds):
        if world.users == 0:
            bpy.data.worlds.remove(world)


def get_collection(name):
    """Create or reuse a top-level collection."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)

    if col.name not in bpy.context.scene.collection.children.keys():
        bpy.context.scene.collection.children.link(col)

    return col


def make_material(name, rgba, metallic=0.0, roughness=0.7):
    """Create a simple Principled BSDF material."""

    if len(rgba) == 3:
        rgba = (rgba[0], rgba[1], rgba[2], 1.0)

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)

    mat.use_nodes = True
    node_tree = mat.node_tree

    bsdf = next(
        (n for n in node_tree.nodes if n.type == 'BSDF_PRINCIPLED'),
        None
    )

    if bsdf is None:
        node_tree.nodes.clear()
        out = node_tree.nodes.new('ShaderNodeOutputMaterial')
        bsdf = node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = rgba

    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = rgba[3]

    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic

    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness

    # Transparency settings, mainly for Eevee / viewport.
    if rgba[3] < 1.0:
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass

        try:
            mat.shadow_method = 'CLIP'
        except Exception:
            pass

        try:
            mat.use_screen_refraction = True
        except Exception:
            pass

    return mat


def add_box(name, center, size, material, collection, rotation_euler=None):
    """Add a box object using bmesh."""

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    obj.scale = size

    if rotation_euler is not None:
        obj.rotation_euler = rotation_euler

    if material is not None:
        obj.data.materials.append(material)

    collection.objects.link(obj)

    return obj


def bake_scale(obj):
    """
    Bake object scale into mesh vertices.

    This is useful for doors/windows because Godot rotates them more cleanly
    when they do not have non-uniform scale.
    """

    sx, sy, sz = obj.scale

    if (
        abs(sx - 1.0) < 1e-6 and
        abs(sy - 1.0) < 1e-6 and
        abs(sz - 1.0) < 1e-6
    ):
        return

    for vertex in obj.data.vertices:
        vertex.co.x *= sx
        vertex.co.y *= sy
        vertex.co.z *= sz

    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()


def set_hinge_geometry(obj, direction=1.0):
    """
    Move panel geometry away from its hinge origin, then bake scale.

    direction = 1.0
        Panel extends toward +X from the origin.
        Good for left-hinged panels.

    direction = -1.0
        Panel extends toward -X from the origin.
        Good for right-hinged panels.
    """

    for vertex in obj.data.vertices:
        vertex.co.x += 0.5 * direction

    obj.data.update()
    bake_scale(obj)


def make_emission_material(name, rgba, strength=5.0):
    """Create or reuse a Principled BSDF material with emission."""

    if len(rgba) == 3:
        rgba = (rgba[0], rgba[1], rgba[2], 1.0)

    mat = make_material(name, rgba)

    node_tree = mat.node_tree
    bsdf = next(
        (n for n in node_tree.nodes if n.type == 'BSDF_PRINCIPLED'),
        None
    )

    if bsdf is not None:
        # Blender 4.x usually uses "Emission Color".
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = rgba

            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = strength

        # Older Blender versions may use "Emission".
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = rgba

            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = strength

    return mat


def add_point_light(name, location, energy, collection):
    """Add a point light object."""

    light_data = bpy.data.lights.new(name, type='POINT')
    light_data.energy = energy

    try:
        light_data.shadow_soft_size = 0.35
    except Exception:
        pass

    light_obj = bpy.data.objects.new(name, light_data)
    light_obj.location = location

    collection.objects.link(light_obj)

    return light_obj


def add_nice_room(
    unit_x,
    z0,
    unit_w,
    unit_d,
    interior_h,
    outer_y,
    wall_t,
    door_w,
    f,
    u,
    add_lights=True,
    light_energy=30.0
):
    """
    Build one nice room and place it inside one apartment.
    The same room layout is copied to every apartment by calling this
    function for each unit.
    """

    room_col = get_collection("InteriorRooms")
    light_col = get_collection("InteriorLights")

    tag = f"F{f:02d}_U{u:02d}"

    floor_top = z0 + 0.02
    ceiling_z = z0 + interior_h

    left_x = unit_x - unit_w / 2.0 + 0.08
    right_x = unit_x + unit_w / 2.0 - 0.08

    rear_y = -outer_y + wall_t + 0.08
    front_y = outer_y - 1.05
    center_y = (rear_y + front_y) / 2.0

    # ------------------------------------------------------------
    # ROOM MATERIALS
    # ------------------------------------------------------------

    mat_room_floor = make_material(
        "RoomWoodFloor",
        (0.42, 0.30, 0.20, 1.0),
        roughness=0.55
    )

    mat_ceiling = make_material(
        "RoomCeiling",
        (0.92, 0.92, 0.90, 1.0),
        roughness=0.9
    )

    mat_rug = make_material(
        "Rug",
        (0.35, 0.45, 0.55, 1.0),
        roughness=0.95
    )

    mat_bed_frame = make_material(
        "BedFrame",
        (0.36, 0.26, 0.18, 1.0),
        roughness=0.6
    )

    mat_mattress = make_material(
        "Mattress",
        (0.85, 0.85, 0.82, 1.0),
        roughness=0.85
    )

    mat_blanket = make_material(
        "Blanket",
        (0.30, 0.42, 0.50, 1.0),
        roughness=0.9
    )

    mat_pillow = make_material(
        "Pillow",
        (0.92, 0.92, 0.90, 1.0),
        roughness=0.9
    )

    mat_wardrobe = make_material(
        "Wardrobe",
        (0.75, 0.72, 0.66, 1.0),
        roughness=0.7
    )

    mat_desk = make_material(
        "DeskWood",
        (0.50, 0.38, 0.26, 1.0),
        roughness=0.6
    )

    mat_chair = make_material(
        "Chair",
        (0.25, 0.25, 0.28, 1.0),
        roughness=0.7
    )

    mat_plant_pot = make_material(
        "PlantPot",
        (0.60, 0.60, 0.58, 1.0),
        roughness=0.8
    )

    mat_plant = make_material(
        "Plant",
        (0.18, 0.42, 0.18, 1.0),
        roughness=0.9
    )

    mat_switch = make_material(
        "SwitchWhite",
        (0.90, 0.90, 0.88, 1.0),
        roughness=0.4
    )

    mat_switch_button = make_material(
        "SwitchButton",
        (0.80, 0.80, 0.78, 1.0),
        roughness=0.3
    )

    mat_lamp_body = make_material(
        "LampBody",
        (0.20, 0.20, 0.22, 1.0),
        metallic=0.7,
        roughness=0.35
    )

    mat_lamp_emit = make_emission_material(
        "LampEmit",
        (1.0, 0.92, 0.78, 1.0),
        6.0
    )

    # ------------------------------------------------------------
    # ROOM SHELL
    # ------------------------------------------------------------

    add_box(
        f"RoomFloor_{tag}",
        (unit_x, 0.0, z0 + 0.01),
        (unit_w - 0.16, unit_d - 0.35, 0.02),
        mat_room_floor,
        room_col
    )

    add_box(
        f"RoomCeiling_{tag}",
        (unit_x, 0.0, ceiling_z - 0.01),
        (unit_w - 0.16, unit_d - 0.35, 0.02),
        mat_ceiling,
        room_col
    )

    add_box(
        f"Rug_{tag}",
        (unit_x, center_y + 0.45, floor_top + 0.01),
        (2.8, 1.9, 0.02),
        mat_rug,
        room_col
    )

    # ------------------------------------------------------------
    # BED
    # ------------------------------------------------------------

    bed_w = 1.6
    bed_d = 2.1
    bed_base_h = 0.26
    mattress_h = 0.18

    bed_x = left_x + bed_w / 2.0 + 0.08
    bed_y = rear_y + bed_d / 2.0 + 0.05

    add_box(
        f"BedBase_{tag}",
        (bed_x, bed_y, floor_top + bed_base_h / 2.0),
        (bed_w, bed_d, bed_base_h),
        mat_bed_frame,
        room_col
    )

    add_box(
        f"BedHeadboard_{tag}",
        (bed_x, rear_y + 0.05, floor_top + 0.55),
        (bed_w, 0.08, 0.70),
        mat_bed_frame,
        room_col
    )

    add_box(
        f"Mattress_{tag}",
        (bed_x, bed_y, floor_top + bed_base_h + mattress_h / 2.0),
        (bed_w - 0.08, bed_d - 0.08, mattress_h),
        mat_mattress,
        room_col
    )

    pillow_z = floor_top + bed_base_h + mattress_h + 0.06

    add_box(
        f"PillowLeft_{tag}",
        (bed_x - 0.35, bed_y - bed_d / 2.0 + 0.32, pillow_z),
        (0.55, 0.32, 0.12),
        mat_pillow,
        room_col
    )

    add_box(
        f"PillowRight_{tag}",
        (bed_x + 0.35, bed_y - bed_d / 2.0 + 0.32, pillow_z),
        (0.55, 0.32, 0.12),
        mat_pillow,
        room_col
    )

    add_box(
        f"Blanket_{tag}",
        (bed_x, bed_y + 0.25, floor_top + bed_base_h + mattress_h + 0.025),
        (bed_w - 0.12, bed_d - 1.10, 0.05),
        mat_blanket,
        room_col
    )

    # ------------------------------------------------------------
    # NIGHTSTAND
    # ------------------------------------------------------------

    nightstand_x = bed_x + bed_w / 2.0 + 0.25
    nightstand_y = rear_y + 0.30

    add_box(
        f"Nightstand_{tag}",
        (nightstand_x, nightstand_y, floor_top + 0.25),
        (0.45, 0.40, 0.50),
        mat_bed_frame,
        room_col
    )

    # ------------------------------------------------------------
    # WARDROBE
    # ------------------------------------------------------------

    wardrobe_w = 1.2
    wardrobe_d = 0.6
    wardrobe_h = 2.2

    wardrobe_x = right_x - wardrobe_w / 2.0 - 0.08
    wardrobe_y = rear_y + wardrobe_d / 2.0 + 0.05

    add_box(
        f"Wardrobe_{tag}",
        (wardrobe_x, wardrobe_y, floor_top + wardrobe_h / 2.0),
        (wardrobe_w, wardrobe_d, wardrobe_h),
        mat_wardrobe,
        room_col
    )

    # ------------------------------------------------------------
    # DESK + CHAIR
    # ------------------------------------------------------------

    desk_w = 1.35
    desk_d = 0.6
    desk_h = 0.74

    desk_x = right_x - desk_w / 2.0 - 0.25
    desk_y = front_y - desk_d / 2.0 - 0.15

    add_box(
        f"DeskTop_{tag}",
        (desk_x, desk_y, floor_top + desk_h),
        (desk_w, desk_d, 0.05),
        mat_desk,
        room_col
    )

    add_box(
        f"DeskLegLeft_{tag}",
        (desk_x - desk_w / 2.0 + 0.04, desk_y, floor_top + desk_h / 2.0),
        (0.06, desk_d - 0.08, desk_h),
        mat_desk,
        room_col
    )

    add_box(
        f"DeskLegRight_{tag}",
        (desk_x + desk_w / 2.0 - 0.04, desk_y, floor_top + desk_h / 2.0),
        (0.06, desk_d - 0.08, desk_h),
        mat_desk,
        room_col
    )

    chair_x = desk_x
    chair_y = desk_y - 0.55
    chair_seat_h = 0.45

    add_box(
        f"ChairSeat_{tag}",
        (chair_x, chair_y, floor_top + chair_seat_h),
        (0.45, 0.45, 0.06),
        mat_chair,
        room_col
    )

    add_box(
        f"ChairSupport_{tag}",
        (chair_x, chair_y, floor_top + chair_seat_h / 2.0),
        (0.10, 0.10, chair_seat_h),
        mat_chair,
        room_col
    )

    add_box(
        f"ChairBack_{tag}",
        (chair_x, chair_y - 0.21, floor_top + chair_seat_h + 0.27),
        (0.45, 0.06, 0.55),
        mat_chair,
        room_col
    )

    # ------------------------------------------------------------
    # PLANT
    # ------------------------------------------------------------

    plant_x = left_x + 0.35
    plant_y = front_y - 0.35

    add_box(
        f"PlantPot_{tag}",
        (plant_x, plant_y, floor_top + 0.175),
        (0.32, 0.32, 0.35),
        mat_plant_pot,
        room_col
    )

    add_box(
        f"Plant_{tag}",
        (plant_x, plant_y, floor_top + 0.35 + 0.275),
        (0.45, 0.45, 0.55),
        mat_plant,
        room_col
    )

    # ------------------------------------------------------------
    # CEILING LAMP
    # ------------------------------------------------------------

    lamp_name = f"Lamp_{tag}"
    bulb_name = f"LampBulb_{tag}"
    light_name = f"LampLight_{tag}"

    lamp_x = unit_x
    lamp_y = center_y + 0.20

    lamp_shade = add_box(
        f"LampShade_{tag}",
        (lamp_x, lamp_y, ceiling_z - 0.34),
        (0.55, 0.55, 0.16),
        mat_lamp_body,
        room_col
    )

    lamp_shade["asset_type"] = "lamp"
    lamp_shade["apartment"] = tag

    add_box(
        f"LampMount_{tag}",
        (lamp_x, lamp_y, ceiling_z - 0.02),
        (0.14, 0.14, 0.04),
        mat_lamp_body,
        room_col
    )

    add_box(
        f"LampRod_{tag}",
        (lamp_x, lamp_y, ceiling_z - 0.16),
        (0.03, 0.03, 0.24),
        mat_lamp_body,
        room_col
    )

    bulb = add_box(
        bulb_name,
        (lamp_x, lamp_y, ceiling_z - 0.425),
        (0.45, 0.45, 0.03),
        mat_lamp_emit,
        room_col
    )

    bulb["asset_type"] = "lamp_bulb"
    bulb["apartment"] = tag

    # ------------------------------------------------------------
    # REAL POINT LIGHT
    # ------------------------------------------------------------

    controlled_name = bulb_name

    if add_lights:
        light = add_point_light(
            light_name,
            (lamp_x, lamp_y, ceiling_z - 0.55),
            light_energy,
            light_col
        )

        light["asset_type"] = "light"
        light["apartment"] = tag
        light["controlled_by"] = f"LightSwitch_{tag}"

        controlled_name = light_name

    # ------------------------------------------------------------
    # LIGHT SWITCH NEAR DOOR
    # ------------------------------------------------------------

    switch_x = unit_x + door_w / 2.0 + 0.18
    switch_y = -outer_y + wall_t + 0.015
    switch_z = z0 + 1.20

    switch = add_box(
        f"LightSwitch_{tag}",
        (switch_x, switch_y, switch_z),
        (0.09, 0.025, 0.14),
        mat_switch,
        room_col
    )

    switch_button = add_box(
        f"LightSwitchButton_{tag}",
        (switch_x, switch_y + 0.013, switch_z),
        (0.035, 0.012, 0.05),
        mat_switch_button,
        room_col
    )

    switch["asset_type"] = "light_switch"
    switch["apartment"] = tag
    switch["controls"] = controlled_name

    switch_button["asset_type"] = "light_switch_button"
    switch_button["apartment"] = tag
    switch_button["controls"] = controlled_name

    blind_switch = add_box(
        f"BlindSwitch_{tag}",
        (right_x - 0.28, front_y, switch_z),
        (0.09, 0.025, 0.14),
        mat_switch_button,
        room_col
    )
    blind_switch["asset_type"] = "blind_switch"
    blind_switch["apartment"] = tag


# ============================================================
# MAIN BUILD FUNCTION
# ============================================================

def build_privacy_apartments():
    if CLEAR_EXISTING:
        clear_scene()

    # Collections
    site = get_collection("Site")
    structure = get_collection("Structure")
    privacy = get_collection("PrivacyWallsAndFins")
    balconies = get_collection("PrivateBalconies")
    glazing = get_collection("PrivacyGlazing")
    louvers = get_collection("WindowLouvers")
    core = get_collection("PrivateCore")
    view = get_collection("CameraAndLights")

    # ------------------------------------------------------------
    # MATERIALS
    # ------------------------------------------------------------

    mat_ground = make_material(
        "Ground",
        (0.15, 0.27, 0.15, 1.0),
        roughness=1.0
    )

    mat_plaza = make_material(
        "Plaza",
        (0.50, 0.50, 0.48, 1.0),
        roughness=0.95
    )

    mat_slab = make_material(
        "Slab",
        (0.68, 0.66, 0.62, 1.0),
        roughness=0.9
    )

    mat_concrete = make_material(
        "Concrete",
        (0.60, 0.58, 0.54, 1.0),
        roughness=0.92
    )

    mat_privacy = make_material(
        "PrivacyWall",
        (0.86, 0.84, 0.79, 1.0),
        roughness=0.88
    )

    mat_metal = make_material(
        "MetalFins",
        (0.22, 0.23, 0.25, 1.0),
        metallic=0.85,
        roughness=0.38
    )

    mat_glass = make_material(
        "FrostedPrivacyGlass",
        (0.72, 0.83, 0.88, GLASS_ALPHA),
        metallic=0.0,
        roughness=0.18
    )

    mat_wood = make_material(
        "WoodDeck",
        (0.48, 0.33, 0.20, 1.0),
        roughness=0.62
    )

    mat_railing_glass = make_material(
        "RailingGlass",
        (0.55, 0.78, 0.88, 0.42),
        roughness=0.12
    )

    # ------------------------------------------------------------
    # OVERALL DIMENSIONS
    # ------------------------------------------------------------

    overall_w = (
        (UNITS_PER_FLOOR + 1) * PARTY_WALL_T
        + UNITS_PER_FLOOR * UNIT_W
    )

    overall_d = UNIT_D
    building_h = FLOORS * FLOOR_H
    interior_h = FLOOR_H - SLAB_T
    outer_y = overall_d / 2.0

    # ------------------------------------------------------------
    # SITE
    # ------------------------------------------------------------

    add_box(
        "Ground",
        (0.0, 0.0, -SLAB_T - 0.10),
        (overall_w + 120.0, overall_d + 120.0, 0.2),
        mat_ground,
        site
    )

    add_box(
        "Plaza",
        (0.0, 8.0, -SLAB_T + 0.03),
        (overall_w + 30.0, overall_d + 34.0, 0.06),
        mat_plaza,
        site
    )

    # ------------------------------------------------------------
    # FLOOR SLABS + ROOF SLAB
    # ------------------------------------------------------------

    for f in range(FLOORS + 1):
        z_top = f * FLOOR_H

        add_box(
            f"Slab_{f:02d}",
            (0.0, 0.0, z_top - SLAB_T / 2.0),
            (overall_w, overall_d, SLAB_T),
            mat_slab,
            structure
        )

    # ------------------------------------------------------------
    # FULL-HEIGHT PRIVACY WALLS BETWEEN APARTMENTS
    # ------------------------------------------------------------

    privacy_wall_h = building_h + PARAPET_H
    fin_h = privacy_wall_h + 0.9

    for i in range(UNITS_PER_FLOOR + 1):
        x = (
            -overall_w / 2.0
            + PARTY_WALL_T / 2.0
            + i * (UNIT_W + PARTY_WALL_T)
        )

        # Solid wall between apartments.
        add_box(
            f"PartyPrivacyWall_{i:02d}",
            (x, 0.0, privacy_wall_h / 2.0),
            (PARTY_WALL_T, overall_d, privacy_wall_h),
            mat_privacy,
            privacy
        )

        # External facade fin, blocks lateral window-to-window views.
        add_box(
            f"FacadePrivacyFin_{i:02d}",
            (x, outer_y + FIN_PROJECTION / 2.0, fin_h / 2.0),
            (FIN_W, FIN_PROJECTION, fin_h),
            mat_metal,
            privacy
        )

    # ------------------------------------------------------------
    # APARTMENTS
    # ------------------------------------------------------------

    window_w = max(0.6, UNIT_W - 2.0 * JAMB_W)
    glass_h = max(0.2, HEAD_H - SILL_H)

    reveal_d = GLASS_RECESS
    facade_y = outer_y - reveal_d / 2.0
    glass_y = outer_y - reveal_d + 0.04

    for f in range(FLOORS):
        z0 = f * FLOOR_H
        z_center = z0 + interior_h / 2.0

        # Balcony side privacy walls at every unit boundary.
        balcony_y = outer_y + BALCONY_DEPTH / 2.0

        for i in range(UNITS_PER_FLOOR + 1):
            x = (
                -overall_w / 2.0
                + PARTY_WALL_T / 2.0
                + i * (UNIT_W + PARTY_WALL_T)
            )

            add_box(
                f"BalconySideWall_F{f:02d}_B{i:02d}",
                (x, balcony_y, z0 + BALCONY_SIDE_H / 2.0),
                (0.22, BALCONY_DEPTH + 0.25, BALCONY_SIDE_H),
                mat_privacy,
                balconies
            )

        for u in range(UNITS_PER_FLOOR):
            unit_x = (
                -overall_w / 2.0
                + PARTY_WALL_T
                + UNIT_W / 2.0
                + u * (UNIT_W + PARTY_WALL_T)
            )

            # ----------------------------------------------------
            # REAR WALL + PRIVATE DOOR
            # ----------------------------------------------------

            door_w = 1.15
            door_h = 2.2
            rear_y = -outer_y + WALL_T / 2.0
            side_w = (UNIT_W - door_w) / 2.0

            for side, offset in (
                ("Left", -(door_w + side_w) / 2.0),
                ("Right", (door_w + side_w) / 2.0),
            ):
                add_box(
                    f"RearWall{side}_F{f:02d}_U{u:02d}",
                    (unit_x + offset, rear_y, z_center),
                    (side_w, WALL_T, interior_h),
                    mat_concrete,
                    structure
                )

            rear_header_h = interior_h - door_h

            if rear_header_h > 0.001:
                add_box(
                    f"RearWallHeader_F{f:02d}_U{u:02d}",
                    (
                        unit_x,
                        rear_y,
                        z0 + door_h + rear_header_h / 2.0,
                    ),
                    (door_w, WALL_T, rear_header_h),
                    mat_concrete,
                    structure
                )

            # Door hinge is at local X=0; the panel extends right from origin.
            door = add_box(
                f"EntranceDoor_F{f:02d}_U{u:02d}",
                (unit_x - door_w / 2.0, rear_y, z0 + door_h / 2.0),
                (door_w, 0.12, door_h),
                mat_metal,
                structure
            )

            set_hinge_geometry(door, 1.0)
            door["asset_type"] = "door"
            door["hinge"] = "left"

            # ----------------------------------------------------
            # FRONT FACADE OPAQUE WINDOW REVEAL
            # ----------------------------------------------------

            left_jamb_x = unit_x - UNIT_W / 2.0 + JAMB_W / 2.0
            right_jamb_x = unit_x + UNIT_W / 2.0 - JAMB_W / 2.0

            add_box(
                f"FrontJambLeft_F{f:02d}_U{u:02d}",
                (left_jamb_x, facade_y, z_center),
                (JAMB_W, reveal_d, interior_h),
                mat_concrete,
                structure
            )

            add_box(
                f"FrontJambRight_F{f:02d}_U{u:02d}",
                (right_jamb_x, facade_y, z_center),
                (JAMB_W, reveal_d, interior_h),
                mat_concrete,
                structure
            )

            if SILL_H > 0.001:
                add_box(
                    f"FrontSill_F{f:02d}_U{u:02d}",
                    (unit_x, facade_y, z0 + SILL_H / 2.0),
                    (window_w, reveal_d, SILL_H),
                    mat_concrete,
                    structure
                )

            header_h = interior_h - HEAD_H

            if header_h > 0.001:
                add_box(
                    f"FrontHeader_F{f:02d}_U{u:02d}",
                    (unit_x, facade_y, z0 + HEAD_H + header_h / 2.0),
                    (window_w, reveal_d, header_h),
                    mat_concrete,
                    structure
                )

            # ----------------------------------------------------
            # OPENABLE FROSTED PRIVACY WINDOWS
            # ----------------------------------------------------

            window_panel_w = window_w / 2.0 - 0.03

            for side, hinge_x, direction in (
                ("Left", unit_x - window_w / 2.0, 1.0),
                ("Right", unit_x + window_w / 2.0, -1.0),
            ):
                window = add_box(
                    f"OpenableWindow_F{f:02d}_U{u:02d}_{side}",
                    (hinge_x, glass_y, z0 + SILL_H + glass_h / 2.0),
                    (window_panel_w, 0.06, glass_h),
                    mat_glass,
                    glazing
                )

                set_hinge_geometry(window, direction)

                window["asset_type"] = "window"
                window["hinge"] = "left" if direction > 0.0 else "right"

            # ----------------------------------------------------
            # WINDOW EYEBROW / HORIZONTAL PRIVACY HOOD
            # ----------------------------------------------------

            eyebrow_proj = 0.95

            add_box(
                f"WindowEyebrow_F{f:02d}_U{u:02d}",
                (unit_x, outer_y + eyebrow_proj / 2.0, z0 + HEAD_H + 0.08),
                (window_w + 0.5, eyebrow_proj, 0.16),
                mat_metal,
                privacy
            )

            # ----------------------------------------------------
            # PRIVATE BALCONY
            # ----------------------------------------------------

            add_box(
                f"BalconySlab_F{f:02d}_U{u:02d}",
                (unit_x, balcony_y, z0 - BALCONY_SLAB_T / 2.0),
                (UNIT_W, BALCONY_DEPTH, BALCONY_SLAB_T),
                mat_slab,
                balconies
            )

            add_box(
                f"BalconyDeck_F{f:02d}_U{u:02d}",
                (unit_x, balcony_y, z0 + 0.015),
                (UNIT_W - 0.30, BALCONY_DEPTH - 0.25, 0.03),
                mat_wood,
                balconies
            )

            # Frosted front balcony screen.
            screen_y = outer_y + BALCONY_DEPTH - 0.08

            add_box(
                f"BalconyFrontScreen_F{f:02d}_U{u:02d}",
                (unit_x, screen_y, z0 + BALCONY_FRONT_SCREEN_H / 2.0),
                (UNIT_W - 0.25, 0.10, BALCONY_FRONT_SCREEN_H),
                mat_glass,
                balconies
            )

            add_box(
                f"BalconyScreenCap_F{f:02d}_U{u:02d}",
                (unit_x, screen_y, z0 + BALCONY_FRONT_SCREEN_H + 0.03),
                (UNIT_W - 0.25, 0.16, 0.06),
                mat_metal,
                balconies
            )

            # ----------------------------------------------------
            # ANGLED WINDOW LOUVERS
            # ----------------------------------------------------

            if USE_LOUVERS and LOUVER_COUNT > 0:
                louver_y = outer_y + 0.35
                spacing = glass_h / (LOUVER_COUNT + 1)
                rot = (math.radians(-38.0), 0.0, 0.0)

                for k in range(1, LOUVER_COUNT + 1):
                    lz = z0 + SILL_H + spacing * k

                    add_box(
                        f"Louver_F{f:02d}_U{u:02d}_{k:02d}",
                        (unit_x, louver_y, lz),
                        (window_w, 0.38, 0.045),
                        mat_metal,
                        louvers,
                        rotation_euler=rot
                    )

            # ----------------------------------------------------
            # NICE INTERIOR ROOM copied to every apartment
            # ----------------------------------------------------

            add_nice_room(
                unit_x=unit_x,
                z0=z0,
                unit_w=UNIT_W,
                unit_d=UNIT_D,
                interior_h=interior_h,
                outer_y=outer_y,
                wall_t=WALL_T,
                door_w=door_w,
                f=f,
                u=u,
                add_lights=USE_ROOM_LIGHTS,
                light_energy=ROOM_LIGHT_ENERGY
            )

    # ------------------------------------------------------------
    # REAR WALKWAYS + SWITCHBACK STAIR
    # ------------------------------------------------------------

    walkway_y = -outer_y - 0.8
    walkway_back_y = walkway_y - 0.8

    stair_x_a = overall_w / 2.0 + 0.6
    stair_x_b = overall_w / 2.0 + 2.0

    stair_near_y = walkway_y - 0.6

    stair_tread = 0.5
    steps_per_flight = 8
    step_rise = FLOOR_H / (steps_per_flight * 2.0)

    flight_run = steps_per_flight * stair_tread
    flight_length = math.hypot(flight_run, FLOOR_H / 2.0)
    flight_angle = math.atan2(FLOOR_H / 2.0, flight_run)

    far_y = stair_near_y - flight_run

    for floor in range(FLOORS):
        z0 = floor * FLOOR_H
        half_z = z0 + FLOOR_H / 2.0

        add_box(
            f"RearWalkway_{floor:02d}",
            (0.0, walkway_y, z0 - 0.10),
            (overall_w, 1.6, 0.20),
            mat_slab,
            core
        )

        # ------------------------------------------------------------
        # FIXED: rear handrail now adjusts with overall_w.
        # For top floor it extends over the stair landing side.
        # ------------------------------------------------------------
        if floor == FLOORS - 1:
            rear_rail_w = overall_w - 0.25 + 1.4
            rear_rail_x = -0.03 + 0.7
        else:
            rear_rail_w = overall_w - 0.25
            rear_rail_x = -0.03

        add_box(
            f"FloorHandrailRear_F{floor:02d}",
            (rear_rail_x, walkway_back_y, z0 + 0.55),
            (rear_rail_w, 0.10, 1.10),
            mat_railing_glass,
            core
        )

        add_box(
            f"FloorHandrailLeft_F{floor:02d}",
            (-overall_w / 2.0, walkway_y, z0 + 0.55),
            (0.10, 1.6, 1.10),
            mat_railing_glass,
            core
        )

        if floor == 0:
            add_box(
                "StairHandrailEntrance_F00",
                (stair_x_b + 0.046045, walkway_back_y, z0 + 0.55),
                (0.10, 1.6, 1.10),
                mat_railing_glass,
                core,
                rotation_euler=(0.0, 0.0, math.radians(90.0))
            )
        else:
            add_box(
                f"StairHandrailEnd_F{floor:02d}",
                (stair_x_a + 0.8373, walkway_y + 0.80928, z0 + 0.55),
                (2.548747, 0.10, 1.10),
                mat_railing_glass,
                core
            )

        add_box(
            f"StairFloorLanding_{floor:02d}",
            (overall_w / 2.0 + 1.3, walkway_y, z0 - 0.10),
            (3.0, 1.6, 0.20),
            mat_slab,
            core
        )

        add_box(
            f"StairHandrailFloor_F{floor:02d}",
            (overall_w / 2.0 + 2.8, walkway_y, z0 + 0.55),
            (0.10, 1.6, 1.10),
            mat_railing_glass,
            core
        )

        if floor == FLOORS - 1:
            continue

        for step in range(steps_per_flight):
            top = z0 + (step + 1) * step_rise

            add_box(
                f"StairOut_F{floor:02d}_{step:02d}",
                (
                    stair_x_a,
                    stair_near_y - (step + 0.5) * stair_tread,
                    z0 + (top - z0) / 2.0,
                ),
                (1.2, stair_tread, top - z0),
                mat_concrete,
                core
            )

        add_box(
            f"StairRampCollision_Out_F{floor:02d}",
            (
                stair_x_a,
                stair_near_y - flight_run / 2.0,
                z0 + FLOOR_H / 4.0,
            ),
            (1.2, flight_length, 0.12),
            mat_concrete,
            core,
            rotation_euler=(-flight_angle, 0.0, 0.0)
        )

        out_outer_z = (
            z0
            + FLOOR_H / 4.0
            + 0.55
            + (0.31205 if floor == 0 else 0.0)
        )

        add_box(
            f"StairHandrailOutOuter_F{floor:02d}",
            (stair_x_a - 0.65, stair_near_y - 2.47513, out_outer_z),
            (0.10, flight_length, 1.10),
            mat_railing_glass,
            core
        )

        out_inner_length = (
            2.0
            if floor == 0
            else (4.14653 if floor in (1, 2) else flight_length)
        )

        out_inner_z = z0 + FLOOR_H / 4.0 + 0.55 + 0.013908

        add_box(
            f"StairHandrailOutInner_F{floor:02d}",
            (stair_x_a + 0.65, stair_near_y - 1.767388, out_inner_z),
            (0.10, out_inner_length, 1.10),
            mat_railing_glass,
            core
        )

        add_box(
            f"StairHalfLanding_F{floor:02d}",
            (
                (stair_x_a + stair_x_b) / 2.0,
                far_y - 0.3,
                half_z - 0.10,
            ),
            (2.8, 1.1, 0.20),
            mat_slab,
            core
        )

        add_box(
            f"StairHandrailHalf_F{floor:02d}",
            (
                (stair_x_a + stair_x_b) / 2.0,
                far_y - 0.85,
                half_z + 0.55,
            ),
            (2.8, 0.10, 1.10),
            mat_railing_glass,
            core
        )

        for step in range(steps_per_flight):
            top = half_z + (step + 1) * step_rise

            add_box(
                f"StairBack_F{floor:02d}_{step:02d}",
                (
                    stair_x_b,
                    far_y + (step + 0.5) * stair_tread,
                    half_z + (top - half_z) / 2.0,
                ),
                (1.2, stair_tread, top - half_z),
                mat_concrete,
                core
            )

        add_box(
            f"StairRampCollision_Back_F{floor:02d}",
            (
                stair_x_b,
                far_y + flight_run / 2.0,
                half_z + FLOOR_H / 4.0,
            ),
            (1.2, flight_length, 0.12),
            mat_concrete,
            core,
            rotation_euler=(flight_angle, 0.0, 0.0)
        )

        back_inner_h = 1.092331 if floor == 0 else 1.10
        back_inner_z = half_z + FLOOR_H / 4.0 + 0.55 + 0.013908

        add_box(
            f"StairHandrailBackInner_F{floor:02d}",
            (stair_x_b - 0.65, far_y + 2.93008, back_inner_z),
            (0.10, 2.0, back_inner_h),
            mat_railing_glass,
            core
        )

        add_box(
            f"StairHandrailBackOuter_F{floor:02d}",
            (stair_x_b + 0.65, far_y + 1.46561, back_inner_z),
            (0.10, flight_length, 1.10),
            mat_railing_glass,
            core
        )

    # ------------------------------------------------------------
    # ROOF PARAPET
    # ------------------------------------------------------------

    pt = 0.32
    z_parapet = building_h + PARAPET_H / 2.0

    add_box(
        "Parapet_Front",
        (0.0, outer_y - pt / 2.0, z_parapet),
        (overall_w, pt, PARAPET_H),
        mat_concrete,
        structure
    )

    add_box(
        "Parapet_Back",
        (0.0, -outer_y + pt / 2.0, z_parapet),
        (overall_w, pt, PARAPET_H),
        mat_concrete,
        structure
    )

    add_box(
        "Parapet_Left",
        (-overall_w / 2.0 + pt / 2.0, 0.0, z_parapet),
        (pt, overall_d, PARAPET_H),
        mat_concrete,
        structure
    )

    add_box(
        "Parapet_Right",
        (overall_w / 2.0 - pt / 2.0, 0.0, z_parapet),
        (pt, overall_d, PARAPET_H),
        mat_concrete,
        structure
    )

    # ------------------------------------------------------------
    # CAMERA + LIGHT
    # ------------------------------------------------------------

    target = bpy.data.objects.new("ViewTarget", None)
    target.location = (0.0, 0.0, building_h * 0.42)
    view.objects.link(target)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 32

    cam_obj = bpy.data.objects.new("Camera", cam_data)
    cam_obj.location = (
        overall_w * 0.95,
        outer_y * 1.9 + 22.0,
        building_h * 1.35
    )

    view.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    track = cam_obj.constraints.new(type='TRACK_TO')
    track.target = target
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    sun_data = bpy.data.lights.new("Sun", type='SUN')
    sun_data.energy = 4.5

    sun_obj = bpy.data.objects.new("Sun", sun_data)
    sun_obj.rotation_euler = (
        math.radians(58.0),
        math.radians(12.0),
        math.radians(145.0)
    )

    view.objects.link(sun_obj)

    # ------------------------------------------------------------
    # WORLD
    # ------------------------------------------------------------

    world = bpy.data.worlds.get("World")
    if world is None:
        world = bpy.data.worlds.new("World")

    bpy.context.scene.world = world
    world.use_nodes = True

    bg = next(
        (n for n in world.node_tree.nodes if n.type == 'BACKGROUND'),
        None
    )

    if bg is not None:
        bg.inputs[0].default_value = (0.58, 0.66, 0.75, 1.0)
        bg.inputs[1].default_value = 1.0

    # ------------------------------------------------------------
    # RENDER / UNITS
    # ------------------------------------------------------------

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'

    try:
        scene.render.engine = 'CYCLES'
    except Exception:
        pass

    # Update scene before saving.
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    # ------------------------------------------------------------
    # SAVE .BLEND FILE
    # ------------------------------------------------------------

    if SAVE_FILE:
        try:
            bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_BLEND)
            print(f"Saved Blender file: {OUTPUT_BLEND}")
        except Exception as exc:
            print(f"Could not save automatically: {exc}")
            print("Use File > Save As... and save as privacy_apartments.blend")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_privacy_apartments()
