"""Blender (headless): the picture is a pane of glass. 3D text slams onto it,
the glass cracks (light leaking through the cracks), then on the hit it bursts
into shards that fly at the camera - and the footage behind it (the next shot)
is what was under the glass all along. Run by amv.edit.build:

    blender -b --factory-startup --python shatter.py -- job.json

job: {"in_dir", "out_dir", "fps", "width", "height", "frames", "at", "params"}
params (times are output seconds):
    break     the hit: the glass explodes (base frames from here on are the next shot)
    crack     when cracks start (stepping wider up to the break); default break - 0.6
    text      optional 3D text on the glass ("\\n" for lines), from text_in; it flies
              through the camera on the break
    text_in, font (a .ttf path), text_color [r, g, b], text_ghost [r, g, b]
    impact    [x, y] 0-1 of the frame (y from the top): where the glass breaks from
    shards    how many points the glass is triangulated from (~2x as many shards)
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
P = job["params"]
FPS, W, H, N = job["fps"], job["width"], job["height"], job["frames"]
fw, fh = 5.4, 5.4 * H / W


def rel(t: float) -> int:
    return int(round((t - job["at"]) * FPS)) + 1


BREAK = rel(P["break"])
CRACK = rel(P.get("crack", P["break"] - 0.6))
TEXT_IN = rel(P["text_in"]) if P.get("text") else None
ix, iy = P.get("impact", [0.5, 0.5])
impact = Vector(((ix - 0.5) * fw, (0.5 - iy) * fh, 0))
rng = random.Random(11)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.fps = int(round(FPS))
sc.frame_start, sc.frame_end = 1, N
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.render.filepath = str(Path(job["out_dir"]) / "#####")
sc.view_settings.view_transform = "Standard"
for owner in (sc.render, getattr(sc, "eevee", None)):
    if owner is not None and hasattr(owner, "use_motion_blur"):
        owner.use_motion_blur = True
if hasattr(sc.render, "motion_blur_shutter"):
    sc.render.motion_blur_shutter = 0.6
if hasattr(sc.eevee, "taa_render_samples"):
    sc.eevee.taa_render_samples = 24
world = bpy.data.worlds.new("w")
world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0, 0, 0, 1)
sc.world = world

first = sorted(Path(job["in_dir"]).glob("*.png"))[0]


def emission_material(name: str, color=None, strength: float = 1.0, image=None, frames: int = N,
                      uv_map: str = "UVMap") -> bpy.types.Material:
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "EXTEND"
        tex.image_user.frame_duration = frames  # past it, the last frame holds (the glass freezes)
        tex.image_user.frame_start = 1
        tex.image_user.use_auto_refresh = True
        tex.image_user.use_cyclic = False
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = uv_map
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def sequence(name: str) -> bpy.types.Image:
    img = bpy.data.images.load(str(first), check_existing=False)
    img.name = name
    img.source = "SEQUENCE"
    return img


# camera: frames the glass (z = 0) exactly
cam_data = bpy.data.cameras.new("cam")
cam_data.sensor_fit = "VERTICAL"
cam_data.sensor_height = 24.0
cam_data.lens = 50.0
cam_data.clip_start = 0.05
dist = (fh / 2) / math.tan(math.atan(12.0 / 50.0))
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
cam.location = (0, 0, dist)
sc.camera = cam


def plane(name: str, z: float, scale: float, mat) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    hx, hy = fw / 2 * scale, fh / 2 * scale
    f = bm.faces.new([bm.verts.new((x, y, z)) for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))])
    for loop, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uvl].uv = uv
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


# behind the glass: the footage itself (the next shot once the glass is gone)
behind_z = -2.0
plane("behind", behind_z, (dist - behind_z) / dist, emission_material("behind", image=sequence("behind")))
# the light that leaks through the cracks, gone with the glass
leak = plane("leak", -0.08, 1.2, emission_material("leak", (1.0, 0.95, 1.0), 2.2))
for f, hide in ((1, True), (CRACK, False), (BREAK, True)):
    leak.hide_render = hide
    leak.keyframe_insert("hide_render", frame=f)

# the glass: Delaunay triangles over random points, denser around the impact
pts = [(-fw / 2, -fh / 2), (fw / 2, -fh / 2), (fw / 2, fh / 2), (-fw / 2, fh / 2)]
for k in range(1, 6):  # the border, so the edge shards are straight
    pts += [(-fw / 2 + fw * k / 6, -fh / 2), (-fw / 2 + fw * k / 6, fh / 2)]
for k in range(1, 10):
    pts += [(-fw / 2, -fh / 2 + fh * k / 10), (fw / 2, -fh / 2 + fh * k / 10)]
count = int(P.get("shards", 260))
while len(pts) < count:
    if rng.random() < 0.55:  # clustered at the impact
        r = abs(rng.gauss(0, 1.1))
        a = rng.uniform(0, 2 * math.pi)
        x, y = impact.x + r * math.cos(a), impact.y + r * math.sin(a) * 1.3
    else:
        x, y = rng.uniform(-fw / 2, fw / 2), rng.uniform(-fh / 2, fh / 2)
    if abs(x) < fw / 2 - 0.05 and abs(y) < fh / 2 - 0.05:
        pts.append((x, y))
verts, _, faces, *_ = delaunay_2d_cdt([Vector(p) for p in pts], [], [], 0, 1e-5)
glass_img = sequence("glass")
glass_mat = emission_material("glass", image=glass_img, frames=max(1, BREAK - 1))
edge_mat = emission_material("edge", (1.0, 1.0, 1.0), 1.6)
shards = []
thick = 0.05
for face in faces:
    tri = [Vector((verts[i].x, verts[i].y, 0)) for i in face]
    c = sum(tri, Vector()) / 3
    me = bpy.data.meshes.new("shard")
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    top = [bm.verts.new(p - c) for p in tri]
    bot = [bm.verts.new(p - c - Vector((0, 0, thick))) for p in tri]
    ftop = bm.faces.new(top)
    ftop.normal_update()
    if ftop.normal.z < 0:
        ftop.normal_flip()
    for loop in ftop.loops:
        co = loop.vert.co + c
        loop[uvl].uv = (co.x / fw + 0.5, co.y / fh + 0.5)
    for a in range(3):
        b = (a + 1) % 3
        side = bm.faces.new([top[a], top[b], bot[b], bot[a]])
        side.material_index = 1
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("shard", me)
    ob.location = c
    sc.collection.objects.link(ob)
    ob.data.materials.append(glass_mat)
    ob.data.materials.append(edge_mat)
    shards.append(ob)

# cracking: the shards part a little, in three jolts, more near the impact
steps = [CRACK, CRACK + (BREAK - CRACK) // 3, CRACK + 2 * (BREAK - CRACK) // 3, BREAK - 1]
for ob in shards:
    rest = ob.location.copy()
    d = rest - impact
    near = math.exp(-d.length / 1.6)
    direction = d.normalized() if d.length > 1e-4 else Vector((0, 1, 0))
    spin = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
    ob.keyframe_insert("location", frame=1)
    ob.keyframe_insert("rotation_euler", frame=1)
    ob.keyframe_insert("location", frame=CRACK)
    ob.keyframe_insert("rotation_euler", frame=CRACK)
    for k, f in enumerate(steps[1:], 1):
        amt = k / 3
        ob.location = rest + direction * (0.02 + 0.08 * near) * amt + Vector((0, 0, 0.03 * near * amt))
        ob.rotation_euler = tuple(spin * 0.035 * near * amt)
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", frame=f)
    # the burst: a shock front from the impact, each shard flies out and at the camera
    delay = int(d.length * 1.3)
    start = ob.location.copy()
    rot0 = Vector(ob.rotation_euler)
    v = direction * (2.0 + 6.0 * near + rng.uniform(0, 2)) + Vector((0, 0, 7.0 + 16.0 * near + rng.uniform(0, 5)))
    w = spin * rng.uniform(6, 16)
    t_end = 40
    for k in range(0, t_end + 1, 2):
        f = BREAK + delay + k
        t = k / FPS
        damp = (1 - math.exp(-2.2 * t)) / 2.2
        ob.location = start + v * damp + Vector((0, -1.5 * t * t, 0))
        ob.rotation_euler = tuple(rot0 + w * damp)
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", frame=f)
    if delay:
        ob.location = start
        ob.rotation_euler = tuple(rot0)
        ob.keyframe_insert("location", frame=BREAK + delay - 1)
        ob.keyframe_insert("rotation_euler", frame=BREAK + delay - 1)

# the text: extruded, red with a cyan ghost behind it, flickering in, jittering, then through the lens
if P.get("text"):
    font = bpy.data.fonts.load(P["font"]) if P.get("font") else None
    made = []
    # strength ~1: an over-bright emission clips red and lifts green/blue - red turned pink
    for name, color, dz, strength in (("ghost", P.get("text_ghost", [0.0, 0.9, 1.0]), -0.08, 1.0),
                                      ("text", P.get("text_color", [1.0, 0.02, 0.12]), 0.0, 1.15)):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = P["text"]
        if font:
            cu.font = font
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.space_line = 0.85
        cu.size = 1.75
        cu.extrude = 0.22
        cu.bevel_depth = 0.012
        ob = bpy.data.objects.new(name, cu)
        sc.collection.objects.link(ob)
        ob.data.materials.append(emission_material(name, color, strength))
        made.append((ob, dz))
    bpy.context.view_layer.update()
    width = max(ob.dimensions.x for ob, _ in made)
    scale = fw * 0.86 / max(1e-3, width)
    flicker = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for ob, dz in made:
        ob.scale = (scale, scale, scale)
        base = Vector((0, fh * 0.03, 0.55 + dz))
        ob.location = base
        for f in range(1, N + 1):
            on = TEXT_IN <= f < BREAK + 12
            if TEXT_IN <= f < TEXT_IN + len(flicker):
                on = bool(flicker[f - TEXT_IN])
            ob.hide_render = not on
            ob.keyframe_insert("hide_render", frame=f)
        for f in range(TEXT_IN, BREAK, 3):  # a digital jitter, sideways in steps
            j = rng.random()
            off = Vector(((rng.random() - 0.5) * 0.12 if j < 0.45 else 0, (rng.random() - 0.5) * 0.04, 0))
            if ob.name.startswith("ghost"):
                off += Vector((0.05 + rng.random() * 0.06, -0.02, 0))
            ob.location = base + off
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("location", frame=f + 2)
        # a slow tilt, so the extrusion and the ghost read as 3D
        for f, rx, ry in ((TEXT_IN, 14, -18), (BREAK, -6, 12)):
            ob.rotation_euler = (math.radians(rx), math.radians(ry), 0)
            ob.keyframe_insert("rotation_euler", frame=f)
        for f, z, s in ((BREAK - 1, base.z, 1.0), (BREAK + 4, base.z + dist * 0.55, 1.4), (BREAK + 10, dist + 2, 2.0)):
            ob.location = Vector((base.x, base.y, z))
            ob.scale = (scale * s,) * 3
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("scale", frame=f)

# the camera jolts on the break and settles
for f in range(BREAK, BREAK + 22, 2):
    a = 0.06 * (1 - (f - BREAK) / 22) ** 2
    cam.location = (rng.uniform(-a, a), rng.uniform(-a, a), dist)
    cam.keyframe_insert("location", frame=f)
cam.location = (0, 0, dist)
cam.keyframe_insert("location", frame=BREAK - 1)
cam.keyframe_insert("location", frame=BREAK + 22)

bpy.ops.render.render(animation=True)
print("shatter done", N, "shards", len(shards))
