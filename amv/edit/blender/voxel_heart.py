"""Blender (headless): the footage as a wall of cubes, each showing its own piece
of the picture; on every beat a heart-shaped block of them punches out toward the
camera and glows - a heartbeat made of pixels. Run by amv.edit.build:

    blender -b --factory-startup --python voxel_heart.py -- job.json

job: {"in_dir", "out_dir", "fps", "width", "height", "frames", "at", "params"}
params:
    beats         output seconds of the pops
    cols, rows    cubes across / down the frame (54 x 96 = 20 px cubes at 1080x1920)
    heart_center  [x, y] 0-1 of the frame (y from the top)
    heart_sizes   heart half-width per beat, 0-1 of the frame width (grow = louder)
    depth         how far a cube jumps at the heart's centre (world units; frame width 5.4)
    glow          [r, g, b] the popped cubes' extra light
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
P = job["params"]
FPS, W, H, N = job["fps"], job["width"], job["height"], job["frames"]
cols, rows = int(P.get("cols", 54)), int(P.get("rows", 96))
fw, fh = 5.4, 5.4 * H / W  # the frame in world units
cell = fw / cols
over = 0.12  # the wall runs past the frame so a camera kick never shows its edge
beats = [round((t - job["at"]) * FPS) + 1 for t in P["beats"]]
sizes = P.get("heart_sizes", [0.25] * len(beats))
cx, cy = P.get("heart_center", [0.5, 0.5])
depth = float(P.get("depth", 1.4))
glow = P.get("glow", [0.55, 0.08, 0.3])
rng = random.Random(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.fps = int(round(FPS))
sc.frame_start, sc.frame_end = 1, N
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.render.filepath = str(Path(job["out_dir"]) / "#####")
sc.view_settings.view_transform = "Standard"  # footage colours 1:1
for attr in ("use_motion_blur",):
    for owner in (sc.render, getattr(sc, "eevee", None)):
        if owner is not None and hasattr(owner, attr):
            setattr(owner, attr, True)
if hasattr(sc.eevee, "taa_render_samples"):
    sc.eevee.taa_render_samples = 16
world = bpy.data.worlds.new("w")
world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0, 0, 0, 1)
sc.world = world

# footage: the base frames as an image sequence
first = sorted(Path(job["in_dir"]).glob("*.png"))[0]
img = bpy.data.images.load(str(first))
img.source = "SEQUENCE"


def footage_material(name: str, side_dim: float, pop_glow: bool, gain: float = 1.0) -> bpy.types.Material:
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "EXTEND"
    tex.image_user.frame_duration = N
    tex.image_user.frame_start = 1
    tex.image_user.use_auto_refresh = True
    uv = nt.nodes.new("ShaderNodeUVMap")
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    # faces toward the camera full bright, cube sides darker: the cubes read as 3D
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    shade = nt.nodes.new("ShaderNodeMapRange")
    shade.inputs["From Min"].default_value, shade.inputs["From Max"].default_value = 0.0, 1.0
    shade.inputs["To Min"].default_value, shade.inputs["To Max"].default_value = side_dim, 1.0
    nt.links.new(sep.outputs["Z"], shade.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mul.inputs[6])
    nt.links.new(shade.outputs["Result"], mul.inputs[7])
    col = mul.outputs[2]
    if pop_glow:  # popped cubes (in front of the wall) light up
        possep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], possep.inputs[0])
        k = nt.nodes.new("ShaderNodeMapRange")
        k.inputs["From Min"].default_value, k.inputs["From Max"].default_value = 0.02, depth * 0.8
        k.inputs["To Min"].default_value, k.inputs["To Max"].default_value = 0.0, 0.6
        nt.links.new(possep.outputs["Z"], k.inputs["Value"])
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        nt.links.new(k.outputs["Result"], add.inputs["Factor"])
        nt.links.new(col, add.inputs[6])
        add.inputs[7].default_value = (*glow, 1.0)
        col = add.outputs[2]
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    em.inputs["Strength"].default_value = gain
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def heart(x: float, y: float) -> float:
    """< 0 inside the classic heart curve (x, y in heart units, y up)."""
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3


# the wall: one mesh, one cube island per cell; front face mapped to its cell of the picture,
# sides to the cell's centre colour (an extruded pixel)
mesh = bpy.data.meshes.new("wall")
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
c0, c1 = -int(cols * over), cols + int(cols * over)
r0, r1 = -int(rows * over), rows + int(rows * over)
cubes = []  # (verts, masks per beat, rnd)
for r in range(r0, r1):
    for c in range(c0, c1):
        x0, y1 = -fw / 2 + c * cell, fh / 2 - r * cell
        x1, y0 = x0 + cell, y1 - cell
        u0, u1 = c / cols, (c + 1) / cols
        v1, v0 = 1 - r / rows, 1 - (r + 1) / rows
        z0, z1 = -0.12, 0.0
        vs = [bm.verts.new(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
        faces = [((4, 5, 6, 7), True), ((0, 1, 5, 4), False), ((1, 2, 6, 5), False), ((2, 3, 7, 6), False),
                 ((3, 0, 4, 7), False)]
        uc = ((u0 + u1) / 2, (v0 + v1) / 2)
        for idx, front in faces:
            f = bm.faces.new([vs[i] for i in idx])
            for loop, i in zip(f.loops, idx):
                loop[uvl].uv = ((u0 if i in (4, 7) else u1), (v0 if i in (4, 5) else v1)) if front else uc
        # which hearts contain this cube (soft edge), and its own jump randomness
        px, py = (c + 0.5) / cols, (r + 0.5) / rows
        masks = []
        for s in sizes:
            hx = (px - cx) / s / 0.9
            hy = -(py - cy) * (H / W) / s / 0.9 + 0.15
            masks.append(1.0 if heart(hx, hy) <= 0 else 0.0)
        cubes.append((vs, masks, rng.random()))
bm.to_mesh(mesh)
bm.free()
wall = bpy.data.objects.new("wall", mesh)
sc.collection.objects.link(wall)
wall.data.materials.append(footage_material("wall", 0.42, True))

# behind the wall: the same picture, dim - a popped cube leaves a dark pixel, not a void
back_mesh = bpy.data.meshes.new("back")
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
ox, oy = fw * (0.5 + over), fh * (0.5 + over)
f = bm.faces.new([bm.verts.new((x, y, -0.13)) for x, y in ((-ox, -oy), (ox, -oy), (ox, oy), (-ox, oy))])
for loop, (u, v) in zip(f.loops, ((-over, -over), (1 + over, -over), (1 + over, 1 + over), (-over, 1 + over))):
    loop[uvl].uv = (u, v)
bm.to_mesh(back_mesh)
bm.free()
back = bpy.data.objects.new("back", back_mesh)
sc.collection.objects.link(back)
back.data.materials.append(footage_material("back", 1.0, False, gain=0.3))

# one shape key per beat: the cubes inside that beat's heart jumped forward
wall.shape_key_add(name="Basis")
vi = 0
order = []
for _vs, masks, rnd in cubes:
    order.append((vi, masks, rnd))
    vi += 8
for k, beat in enumerate(beats):
    key = wall.shape_key_add(name=f"beat{k}")
    for start, masks, rnd in order:
        if not masks[k]:
            continue
        dz = depth * (0.25 + 1.3 * rnd ** 1.5)
        jx, jy = (rnd - 0.5) * 0.08, ((rnd * 7.3) % 1 - 0.5) * 0.08
        for j in range(8):
            co = key.data[start + j].co
            key.data[start + j].co = (co[0] + jx, co[1] + jy, co[2] + dz)
    # the pop: up in 2 frames, settle back over ~26 (eased)
    for f, v in ((beat - 1, 0.0), (beat + 1, 1.0), (beat + 6, 0.55), (beat + 14, 0.18), (beat + 26, 0.0)):
        key.value = v
        key.keyframe_insert("value", frame=max(1, f))

# camera: frames the wall exactly; kicks a few degrees on each beat (alternating), settles
cam_data = bpy.data.cameras.new("cam")
cam_data.sensor_fit = "VERTICAL"
cam_data.sensor_height = 24.0
cam_data.lens = 50.0
dist = (fh / 2) / math.tan(math.atan(12.0 / 50.0))
pivot = bpy.data.objects.new("pivot", None)
sc.collection.objects.link(pivot)
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
cam.parent = pivot
cam.location = (0, 0, dist)
sc.camera = cam
for k, beat in enumerate(beats):
    side = 1 if k % 2 == 0 else -1
    for f, a, zoom in ((beat - 1, 0.0, 1.0), (beat + 4, 1.0, 1.1), (beat + 20, 0.15, 1.02)):
        pivot.rotation_euler = (math.radians(7.0 * a), math.radians(10.0 * a * side), math.radians(2.0 * a * side))
        pivot.keyframe_insert("rotation_euler", frame=max(1, f))
        cam.location = (0, 0, dist / zoom)
        cam.keyframe_insert("location", frame=max(1, f))
pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert("rotation_euler", frame=N)
cam.location = (0, 0, dist)
cam.keyframe_insert("location", frame=N)

bpy.ops.render.render(animation=True)
print("voxel_heart done", N)
