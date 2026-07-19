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

# Default output: user home folder.
OUTPUT_BLEND = os.path.join(os.path.expanduser("~"), "privacy_apartments.blend")

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

FLOORS = 5
UNITS_PER_FLOOR = 4

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

            add_box(
                f"RearWallHeader_F{f:02d}_U{u:02d}",
                (
                    unit_x,
                    rear_y,
                    z0 + door_h + (interior_h - door_h) / 2.0,
                ),
                (door_w, WALL_T, interior_h - door_h),
                mat_concrete,
                structure
            )

            door = add_box(
                f"EntranceDoor_F{f:02d}_U{u:02d}",
                (unit_x - door_w / 2.0, rear_y, z0 + door_h / 2.0),
                (door_w, 0.12, door_h),
                mat_metal,
                structure
            )
            # Hinge at local X=0; the panel extends right from the origin.
            for vertex in door.data.vertices:
                vertex.co.x += 0.5

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
            # FROSTED PRIVACY GLASS
            # ----------------------------------------------------

            add_box(
                f"PrivacyGlass_F{f:02d}_U{u:02d}",
                (unit_x, glass_y, z0 + SILL_H + glass_h / 2.0),
                (window_w, 0.06, glass_h),
                mat_glass,
                glazing
            )

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

    # ------------------------------------------------------------
    # REAR WALKWAYS + SWITCHBACK STAIR
    # ------------------------------------------------------------

    walkway_y = -outer_y - 0.8
    stair_x_a = overall_w / 2.0 + 0.6
    stair_x_b = overall_w / 2.0 + 2.0
    stair_near_y = walkway_y - 0.6
    stair_tread = 0.5
    steps_per_flight = 8
    step_rise = FLOOR_H / (steps_per_flight * 2)

    for floor in range(FLOORS):
        z0 = floor * FLOOR_H
        add_box(
            f"RearWalkway_{floor:02d}",
            (0.0, walkway_y, z0 - 0.10),
            (overall_w, 1.6, 0.20),
            mat_slab,
            core
        )
        add_box(
            f"StairFloorLanding_{floor:02d}",
            (overall_w / 2.0 + 1.3, walkway_y, z0 - 0.10),
            (3.0, 1.6, 0.20),
            mat_slab,
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

        half_z = z0 + FLOOR_H / 2.0
        flight_run = steps_per_flight * stair_tread
        flight_length = math.hypot(flight_run, FLOOR_H / 2.0)
        flight_angle = math.atan2(FLOOR_H / 2.0, flight_run)
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
        far_y = stair_near_y - steps_per_flight * stair_tread
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
