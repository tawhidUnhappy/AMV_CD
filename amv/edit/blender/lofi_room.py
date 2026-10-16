"""Blender (headless): a cozy lo-fi room at night - a kid at the desk with
headphones, rain on the window over a neon city, a glowing screen, a sleeping cat,
a swaying plant, steam from a mug, string lights. Everything is periodic over the
loop (8 bars = 32 beats), so frame N+1 == frame 1 and it loops forever.

    blender -b --factory-startup --python lofi_room.py -- job.json

job: {"out_dir", "fps", "width", "height", "frames", "params"}  (frames = loop length)
params:
    beats       beats in the loop (32 = 8 bars); bar = 4 beats
    intensity   0..1: 0 calm (verse), 1 pumped (chorus): lights pulse on the beat,
                speakers pump, the screen glitches, hearts float up
    only        optional list of frames to render (a test), else all
    palette     optional overrides: sky, lamp, rim, hoodie
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
P = job["params"]
FPS, W, H, L = job["fps"], job["width"], job["height"], job["frames"]
BEATS = int(P.get("beats", 32))
K = float(P.get("intensity", 0.0))
rng = random.Random(5)
TAU = 2 * math.pi

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.fps = int(round(FPS))
sc.frame_start, sc.frame_end = 1, L
for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        sc.render.engine = engine
        break
    except TypeError:
        pass
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.render.filepath = str(Path(job["out_dir"]) / "#####")
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
for attr, val in (("taa_render_samples", 32), ("use_raytracing", True), ("use_shadows", True)):
    if hasattr(sc.eevee, attr):
        setattr(sc.eevee, attr, val)

world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.01, 0.01, 0.03, 1)
bg.inputs[1].default_value = 0.4
sc.world = world


# ---------------------------------------------------------------- helpers
def mat(name, color, rough=0.7, emit=0.0, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def link(ob, parent=None, collection=None):
    (collection or sc.collection).objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def box(name, size, loc, m, parent=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name, ob.scale = name, size
    ob.data.materials.append(m)
    if parent:
        ob.parent = parent
    return ob


def sphere(name, r, loc, m, scale=(1, 1, 1), parent=None, seg=24):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=seg, ring_count=seg // 2)
    ob = bpy.context.active_object
    ob.name, ob.scale = name, scale
    ob.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    if parent:
        ob.parent = parent
    return ob


def cyl(name, r, h, loc, m, parent=None, rot=(0, 0, 0), verts=24):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, rotation=rot, vertices=verts)
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    if parent:
        ob.parent = parent
    return ob


def empty(name, loc=(0, 0, 0), parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.location = loc
    return link(ob, parent)


def key(ob, path, frames_values, interp="LINEAR"):
    """Keyframes for a property path; the loop's end frame (L+1) is added by the caller."""
    for f, v in frames_values:
        setattr(ob, path, v) if path != "scale_u" else None
        ob.keyframe_insert(path, frame=f)


def animate(ob, path, fn, step=1, index=-1):
    """Keyframe `path` every `step` frames from fn(u), u = frame phase 0..1 (periodic)."""
    for f in list(range(1, L + 1, step)) + [L + 1]:
        u = ((f - 1) % L) / L if f <= L else 0.0
        v = fn(u)
        setattr(ob, path, v)
        ob.keyframe_insert(path, frame=f)


def lamp(name, kind, loc, color, energy, rot=(0, 0, 0), size=1.0):
    d = bpy.data.lights.new(name, kind)
    d.color = color
    d.energy = energy
    if kind == "AREA":
        d.size = size
    if kind in ("POINT", "SPOT"):
        d.shadow_soft_size = 0.2
    ob = bpy.data.objects.new(name, d)
    ob.location, ob.rotation_euler = loc, rot
    return link(ob), d


def beat_pulse(u, sharp=6.0, beats=BEATS):
    """1 at each beat, decaying fast: the heartbeat of the room."""
    x = (u * beats) % 1.0
    return math.exp(-sharp * x)


def bar_u(u):
    return (u * BEATS / 4) % 1.0


# palette: night purple/blue outside, warm lamp inside, pink rim
SKY = P.get("palette", {}).get("sky", (0.10, 0.06, 0.30))
LAMP = P.get("palette", {}).get("lamp", (1.0, 0.62, 0.32))
RIM = P.get("palette", {}).get("rim", (1.0, 0.25, 0.65))
HOODIE = P.get("palette", {}).get("hoodie", (0.85, 0.35, 0.60))

M_WALL = mat("wall", (0.20, 0.16, 0.30), 0.9)
M_FLOOR = mat("floor", (0.32, 0.20, 0.17), 0.55)
M_WOOD = mat("wood", (0.42, 0.26, 0.17), 0.5)
M_DARK = mat("dark", (0.05, 0.05, 0.08), 0.4)
M_SKIN = mat("skin", (0.95, 0.72, 0.60), 0.6)
M_HAIR = mat("hair", (0.06, 0.04, 0.10), 0.5)
M_HOOD = mat("hoodie", HOODIE, 0.8)
M_PHONE = mat("phone", (0.02, 0.02, 0.03), 0.3)

# ---------------------------------------------------------------- room shell
box("floor", (7.4, 6.4, 0.1), (0, 0.2, -0.05), M_FLOOR)
box("back", (7.4, 0.15, 3.6), (0, 2.55, 1.75), M_WALL)
box("left", (0.15, 6.4, 3.6), (-3.7, 0.2, 1.75), M_WALL)
box("right", (0.15, 6.4, 3.6), (3.7, 0.2, 1.75), M_WALL)
box("ceil", (7.4, 6.4, 0.1), (0, 0.2, 3.6), mat("ceil", (0.12, 0.10, 0.20), 0.9))
# rug
cyl("rug", 1.0, 0.02, (0.6, 0.2, 0.01), mat("rug", (0.28, 0.20, 0.42), 0.95), verts=48)

# window on the back wall with a frame, mullions, and the night city + rain behind it
WX0, WX1, WZ0, WZ1 = -2.55, 0.15, 1.05, 3.05
M_FRAME = mat("frame", (0.07, 0.06, 0.10), 0.5)
for nm, sz, loc in (("wt", (WX1 - WX0 + 0.16, 0.2, 0.08), ((WX0 + WX1) / 2, 2.45, WZ1 + 0.04)),
                    ("wb", (WX1 - WX0 + 0.3, 0.3, 0.1), ((WX0 + WX1) / 2, 2.42, WZ0 - 0.05)),
                    ("wl", (0.08, 0.2, WZ1 - WZ0), (WX0 - 0.04, 2.45, (WZ0 + WZ1) / 2)),
                    ("wr", (0.08, 0.2, WZ1 - WZ0), (WX1 + 0.04, 2.45, (WZ0 + WZ1) / 2)),
                    ("wm", (0.05, 0.2, WZ1 - WZ0), ((WX0 + WX1) / 2, 2.45, (WZ0 + WZ1) / 2)),
                    ("wh", (WX1 - WX0, 0.2, 0.05), ((WX0 + WX1) / 2, 2.45, (WZ0 + WZ1) / 2))):
    box(nm, sz, loc, M_FRAME)

sky = mat("sky", SKY, 1.0, emit=1.0)
sky_ob = box("sky", (9, 0.05, 6), (-1.2, 7.5, 2.4), sky)
# gradient sky: emission driven by the object's height
nt = sky.node_tree
em_in = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
ramp = nt.nodes.new("ShaderNodeValToRGB")
texc = nt.nodes.new("ShaderNodeTexCoord")
sepx = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(texc.outputs["Generated"], sepx.inputs[0])
nt.links.new(sepx.outputs["Z"], ramp.inputs["Fac"])
ramp.color_ramp.elements[0].color = (0.45, 0.10, 0.45, 1)
ramp.color_ramp.elements[0].position = 0.15
ramp.color_ramp.elements[1].color = (0.03, 0.03, 0.18, 1)
ramp.color_ramp.elements[1].position = 0.85
nt.links.new(ramp.outputs["Color"], em_in.inputs["Emission Color"])
nt.links.new(ramp.outputs["Color"], em_in.inputs["Base Color"])
em_in.inputs["Emission Strength"].default_value = 0.55

# city: layers of towers with lit windows, far -> near, parallax-free (static) but twinkling
city_cols = [(0.10, 0.05, 0.22), (0.07, 0.04, 0.16), (0.04, 0.03, 0.10)]
win_cols = [(1.0, 0.8, 0.45), (0.5, 0.9, 1.0), (1.0, 0.45, 0.8)]
windows = []
for layer, y in enumerate((6.4, 5.0, 3.8)):
    x = -6.0
    while x < 3.5:
        w = rng.uniform(0.5, 1.0)
        h = rng.uniform(1.0, 3.2) * (1.0 if layer == 0 else 0.8) - layer * 0.1
        box(f"tw{layer}", (w, 0.3, h), (x + w / 2, y, h / 2 - 0.2), mat(f"t{layer}", city_cols[layer], 0.9))
        for wx in range(int(w / 0.18)):
            for wz in range(int(h / 0.3)):
                if rng.random() < 0.34:
                    ob = box("win", (0.09, 0.02, 0.12), (x + 0.14 + wx * 0.18, y - 0.17, 0.0 + wz * 0.3 - 0.0),
                             mat("w", win_cols[rng.randrange(3)], 0.5, emit=rng.uniform(2, 5)))
                    if rng.random() < 0.08:
                        windows.append(ob)
        x += w + rng.uniform(0.02, 0.2)
# neon sign on a tower, flickers on the beat
neon = mat("neon", RIM, 0.3, emit=8.0)
sign = box("sign", (1.1, 0.04, 0.16), (-1.4, 4.8, 2.5), neon)
sign.rotation_euler = (0, 0, 0)
for i in range(3):
    s2 = box("s", (0.04, 0.04, 0.55), (-1.9 + i * 0.5, 4.8, 2.5), neon)
    s2.parent = sign
    s2.matrix_parent_inverse = sign.matrix_world.inverted()

# rain: streaks outside the glass, falling, each a whole number of cycles per loop
M_RAIN = mat("rain", (0.7, 0.8, 1.0), 0.3, emit=1.2, alpha=0.6)
rain = []
for i in range(70):
    x = rng.uniform(WX0 + 0.05, WX1 - 0.05)
    ob = box("r", (0.012, 0.012, rng.uniform(0.10, 0.22)), (x, 2.35, WZ1), M_RAIN)
    ob.location.x = x
    rain.append((ob, rng.randrange(2, 6), rng.random()))
for ob, cycles, phase in rain:
    animate(ob, "location",
            lambda u, c=cycles, p=phase, o=ob: (o.location.x, 2.35,
                                                WZ1 + 0.25 - ((u * c + p) % 1.0) * (WZ1 - WZ0 + 0.5)))
# drops sliding on the glass (slower, fewer)
for i in range(7):
    x = rng.uniform(WX0 + 0.1, WX1 - 0.1)
    d = sphere("drop", 0.018, (x, 2.33, WZ1), M_RAIN, scale=(1, 0.5, 1.6), seg=8)
    ph = rng.random()
    animate(d, "location", lambda u, p=ph, x=x: (x, 2.33, WZ1 - ((u + p) % 1.0) * (WZ1 - WZ0)))

# ---------------------------------------------------------------- desk, chair, kid
DESK_Y = 2.05
box("desktop", (3.3, 0.85, 0.07), (-0.2, DESK_Y, 0.82), M_WOOD)
for lx in (-1.75, 1.35):
    for ly in (-0.35, 0.35):
        box("leg", (0.07, 0.07, 0.8), (lx, DESK_Y + ly, 0.4), M_DARK)
# monitor (screen faces the camera) on a stand
mon = empty("monitor", (0.75, DESK_Y + 0.1, 0.86))
box("mon_stand", (0.12, 0.18, 0.35), (0.75, DESK_Y + 0.1, 1.0), M_DARK)
box("mon_foot", (0.45, 0.28, 0.03), (0.75, DESK_Y + 0.1, 0.875), M_DARK)
box("mon_body", (1.45, 0.06, 0.88), (0.75, DESK_Y + 0.1, 1.55), M_DARK)
SCR_Y = DESK_Y + 0.065
screen = box("screen", (1.35, 0.01, 0.78), (0.75, SCR_Y, 1.55), mat("scr", (0.03, 0.05, 0.16), 0.2, emit=1.2))
screen_mat = screen.data.materials[0]

# on the screen: a big heart that beats, chat bubbles that arrive one per bar, glitch bars
M_HEART = mat("heart", (1.0, 0.18, 0.42), 0.3, emit=5.0)
M_CHAT_A = mat("chatA", (0.25, 0.55, 1.0), 0.3, emit=3.0)
M_CHAT_B = mat("chatB", (0.75, 0.75, 0.95), 0.3, emit=2.0)


def heart_mesh(name, size, m):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    pts = []
    for i in range(48):
        t = TAU * i / 48
        pts.append((16 * math.sin(t) ** 3,
                    13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))
    vs = [bm.verts.new((x / 17 * size, 0, (y + 2) / 17 * size)) for x, y in pts]
    f = bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=[f])
    res = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=(0, -size * 0.12, 0), verts=[v for v in res["geom"] if isinstance(v, bmesh.types.BMVert)])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(m)
    return link(ob)


h_screen = heart_mesh("heart_screen", 0.34, M_HEART)
h_screen.rotation_euler = (math.radians(90), 0, 0)
h_screen.location = (0.78, SCR_Y - 0.01, 1.62)
animate(h_screen, "scale", lambda u: tuple((1.0 + (0.22 + 0.25 * K) * beat_pulse(u),) * 3))
# a spare blinking "cursor" + code lines on the left of the screen
for i in range(5):
    ln = box("ln", (0.30 + 0.07 * ((i * 3) % 4), 0.004, 0.025), (0.28 + (0.15 + 0.035 * ((i * 3) % 4)) - 0.0, SCR_Y - 0.008,
                                                                  1.9 - i * 0.07), M_CHAT_B)
# chat bubbles: bubble n pops in at bar n, all vanish together at the loop's end -> loop-safe
bubbles = []
for n in range(8):
    right = n % 2 == 0
    bw = 0.28 + 0.05 * (n % 3)
    b = box(f"chat{n}", (bw, 0.004, 0.07),
            (1.2 - bw / 2 - (0.0 if right else 0.45), SCR_Y - 0.008, 1.25 + (7 - n) * 0.0 + (n * 0.0) - 0.0 + 0.0 +
             (0.14 - 0.00 * n) - 0.15 * 0 - n * 0.045 + 0.55 - 0.0),
            M_CHAT_A if right else M_CHAT_B)
    bubbles.append(b)
    b0 = b.scale.copy()
    animate(b, "scale", lambda u, n=n, b0=b0: tuple(b0 * (1.0 if (u * 8) >= n + 0.0 else 0.0)) if (u * 8) < n + 0.0 else
            tuple(b0 * min(1.0, 0.0 + 1.0 - math.exp(-14 * ((u * 8 - n) / 8 * L / FPS)))))
# glitch bars (intense): coloured stripes that tear across the screen on beat accents
glitch_bars = []
for i in range(4):
    gb = box("gb", (1.3, 0.004, 0.035), (0.75, SCR_Y - 0.012, 1.55), mat("gb", (0.2, 1.0, 0.9) if i % 2 else (1.0, 0.2, 0.6), 0.3, emit=5))
    glitch_bars.append((gb, i))
    animate(gb, "scale", lambda u, i=i, g0=gb.scale.copy():
            tuple(g0 * (1.0 if (K > 0.05 and (int(u * BEATS * 2) + i) % 5 == 0 and beat_pulse(u * 2 % 1.0 if False else u, 3) > 0.25) else 0.0)))
    animate(gb, "location", lambda u, i=i: (0.75 + 0.5 * math.sin(u * BEATS * 3.1 + i * 1.3) * 0.2, SCR_Y - 0.012,
                                            1.2 + 0.7 * ((u * BEATS * 0.5 + i * 0.27) % 1.0)))

# laptop-free desk props: phone (lights per bar), mug with steam, lamp, books
phone = box("phone", (0.17, 0.30, 0.012), (-0.25, DESK_Y - 0.22, 0.865), M_PHONE, rot=(0, 0, math.radians(18)))
phone_scr = box("phone_scr", (0.15, 0.27, 0.004), (-0.25, DESK_Y - 0.22, 0.873),
                mat("pscr", (0.2, 0.6, 1.0), 0.3, emit=2.5), rot=(0, 0, math.radians(18)))
animate(phone_scr.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value",
        lambda u: 0.6 + 4.0 * math.exp(-5 * bar_u(u)))

# mug + steam
M_MUG = mat("mug", (0.9, 0.9, 0.95), 0.4)
cyl("mug", 0.07, 0.12, (-0.65, DESK_Y - 0.15, 0.9), M_MUG)
cyl("coffee", 0.062, 0.005, (-0.65, DESK_Y - 0.15, 0.955), mat("coffee", (0.12, 0.06, 0.03), 0.3))
M_STEAM = mat("steam", (1.0, 0.95, 1.0), 1.0, emit=0.8, alpha=0.35)
for i in range(6):
    st = sphere("steam", 0.03, (-0.65, DESK_Y - 0.15, 0.97), M_STEAM, seg=8)
    off = i / 6

    def steam(u, off=off):
        t = (u * BEATS / 4 / 2 + off) % 1.0  # one wisp per 2 bars
        return (-0.65 + 0.05 * math.sin(t * TAU * 2 + off * 6), DESK_Y - 0.15 + 0.01 * t, 0.97 + 0.32 * t)

    animate(st, "location", steam)
    animate(st, "scale", lambda u, off=off: (lambda t: (math.sin(math.pi * t) * (1.0 + t),) * 3)((u * BEATS / 8 + off) % 1.0))

# desk lamp (warm) - the main practical light
lamp_base = cyl("lamp_base", 0.09, 0.02, (-1.45, DESK_Y + 0.15, 0.87), M_DARK)
box("lamp_arm1", (0.025, 0.025, 0.42), (-1.45, DESK_Y + 0.15, 1.08), M_DARK, rot=(0, math.radians(10), 0))
shade = cyl("lamp_shade", 0.12, 0.10, (-1.35, DESK_Y + 0.12, 1.34), mat("shade", LAMP, 0.6, emit=3.0),
            rot=(math.radians(25), math.radians(10), 0))
L_LAMP, d_lamp = lamp("lamp", "POINT", (-1.30, DESK_Y + 0.05, 1.28), LAMP, 160)
animate(d_lamp, "energy", lambda u: 160 * (1.0 + 0.08 * math.sin(u * TAU * 3) + 0.25 * K * beat_pulse(u, 5)))

# books + a poster on the back wall (the heart glitch)
for i, (c, hh) in enumerate(((0.8, 0.05), (0.3, 0.04), (0.55, 0.06))):
    box("book", (0.28, 0.20, hh), (-1.9, DESK_Y + 0.05, 0.86 + hh * (i + 0.5)),
        mat(f"b{i}", (c, 0.3 + 0.2 * i, 0.5 + 0.1 * i), 0.6))
poster = box("poster", (0.7, 0.02, 0.95), (1.85, 2.45, 2.0), mat("poster", (0.12, 0.10, 0.25), 0.7))
ph_heart = heart_mesh("ph", 0.4, mat("phh", (1.0, 0.3, 0.55), 0.4, emit=2.0))
ph_heart.rotation_euler = (math.radians(90), 0, 0)
ph_heart.location = (1.85, 2.42, 2.05)
animate(ph_heart, "scale", lambda u: tuple((1.0 + 0.10 * beat_pulse(u),) * 3))

# string lights along the top of the back wall: a sagging line, twinkling
M_BULB = mat("bulb", (1.0, 0.9, 0.7), 0.3, emit=6.0)
bulbs = []
for i in range(16):
    t = i / 15
    x = -3.5 + 7.0 * t
    z = 3.15 - 0.22 * math.sin(math.pi * ((t * 2) % 1.0))
    bm_ = mat(f"bulb{i}", [(1.0, 0.65, 0.35), (1.0, 0.4, 0.75), (0.5, 0.7, 1.0)][i % 3], 0.3, emit=6.0)
    ob = sphere("bulb", 0.04, (x, 2.43, z), bm_, seg=10)
    bulbs.append(ob)
    n_ = bm_.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    animate(n_, "default_value", lambda u, i=i: 2.5 + 3.5 * (0.5 + 0.5 * math.sin(u * TAU * 2 + i * 0.9)) +
            K * 6 * beat_pulse((u + (i % 4) * 0.25 / 8) % 1.0, 4))

# plant in the right corner: pot + leaves, sways one cycle per 2 bars
plant = empty("plant", (2.9, 1.9, 0.34))
cyl("pot", 0.2, 0.34, (2.9, 1.9, 0.17), mat("pot", (0.75, 0.42, 0.28), 0.6))
M_LEAF = mat("leaf", (0.18, 0.60, 0.40), 0.5)
for i in range(9):
    a = TAU * i / 9
    lf = sphere("leaf", 0.09, (0, 0, 0), M_LEAF, scale=(0.55, 0.12, 2.0), seg=10, parent=plant)
    lf.location = (0.12 * math.cos(a), 0.12 * math.sin(a), 0.15 + 0.12 * (i % 3))
    lf.rotation_euler = (math.radians(25 * math.sin(a)), math.radians(-25 * math.cos(a)), a)
plant.location = (2.9, 1.9, 0.34)
animate(plant, "rotation_euler", lambda u: (math.radians(2.2 * math.sin(u * TAU * 4)), math.radians(2.6 * math.sin(u * TAU * 4 + 1.0)), 0))

# cat asleep on a cushion: breathes once per bar-and-a-half... whole cycles only -> 8 per loop
cush = cyl("cushion", 0.38, 0.12, (1.1, 0.7, 0.06), mat("cush", (0.35, 0.25, 0.55), 0.95), verts=40)
M_CAT = mat("cat", (0.88, 0.62, 0.30), 0.9)
cat = empty("cat", (1.1, 0.7, 0.2))
body = sphere("cat_body", 0.22, (0, 0, 0.0), M_CAT, scale=(1.4, 1.0, 0.7), parent=cat)
head = sphere("cat_head", 0.12, (0.25, -0.12, 0.0), M_CAT, scale=(1, 1, 0.9), parent=cat)
for sx in (-1, 1):
    ear = bpy.data.objects.new("ear", bpy.data.meshes.new("ear"))
    bpy.ops.mesh.primitive_cone_add(radius1=0.045, depth=0.08, location=(0.25 + sx * 0.06, -0.12, 0.10), vertices=3)
    e = bpy.context.active_object
    e.data.materials.append(M_CAT)
    e.parent = cat
    bpy.data.objects.remove(ear)
tail = sphere("tail", 0.07, (-0.30, 0.1, 0.0), M_CAT, scale=(2.4, 0.7, 0.7), parent=cat)
animate(body, "scale", lambda u: (1.4 * (1 + 0.025 * math.sin(u * TAU * 8)), 1.0 * (1 + 0.03 * math.sin(u * TAU * 8)),
                                  0.7 * (1 + 0.06 * math.sin(u * TAU * 8))))
animate(tail, "rotation_euler", lambda u: (0, 0, math.radians(16 * math.sin(u * TAU * 2))))

# speakers: pump on the beat (intense) or breathe (calm)
for sx in (-3.35, 3.35):
    spk = box("spk", (0.4, 0.4, 0.85), (sx, 1.55, 0.43), M_DARK)
    cone = cyl("cone", 0.12, 0.05, (sx + (0.21 if sx < 0 else -0.21), 1.55, 0.55), mat("cone", (0.3, 0.3, 0.4), 0.5),
               rot=(0, math.radians(90), 0))
    animate(cone, "scale", lambda u: (1.0 + (0.06 + 0.30 * K) * beat_pulse(u, 7),) * 3)
    cone2 = cyl("cone2", 0.07, 0.05, (sx + (0.21 if sx < 0 else -0.21), 1.55, 0.25), mat("cone2", (0.3, 0.3, 0.4), 0.5),
                rot=(0, math.radians(90), 0))

# -------------------------------------------------------------- the girl (an appended, rigged anime model)
GIRL_FILE = P.get("girl", "/mnt/datadisk/AMV_CD/workspace/assets/models/anime_girl_seated.blend")
with bpy.data.libraries.load(GIRL_FILE, link=False) as (src, dst):
    dst.objects = list(src.objects)
girl = empty("girl", (0, 0, 0))
rig = None
for ob in dst.objects:
    if ob is None or ob.name.startswith("Icosphere"):  # a stray sphere that came along in the file
        continue
    sc.collection.objects.link(ob)
    if ob.type == "ARMATURE":
        rig = ob
rig.parent = girl
# anime look: no glossy highlights, a soft emission lift so the lit side is never muddy
for ob in dst.objects:
    if ob is not None and ob.type == "MESH":
        for slot in ob.material_slots:
            m = slot.material
            if m and m.use_nodes:
                for nd in m.node_tree.nodes:
                    if nd.type == "BSDF_PRINCIPLED":
                        for k, v in (("Roughness", 0.9), ("Specular IOR Level", 0.0), ("Coat Weight", 0.0)):
                            if k in nd.inputs:
                                nd.inputs[k].default_value = v


def pose(name, x=0.0, y=0.0, z=0.0):
    pb = rig.pose.bones[name + "_MECH_RIG"]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return pb


# seated, leaning a little forward, forearms up holding a phone close to her chest
BASE = {"thigh.L": (-90, 0, 4), "thigh.R": (-90, 0, -4), "shin.L": (90, 0, 0), "shin.R": (90, 0, 0),
        "spine.001": (-8, 0, 0), "spine.003": (-6, 0, 0), "spine.005": (14, 0, 0),
        "upper_arm.L": (35, 0, -20), "forearm.L": (95, 0, 0), "hand.L": (0, 0, 0),
        "upper_arm.R": (35, 0, 20), "forearm.R": (95, 0, 0), "hand.R": (0, 0, 0)}
for n, v in BASE.items():
    pose(n, *v)
GIRL_POS = P.get("girl_pos", [-0.55, 1.5])
GIRL_YAW = P.get("girl_yaw", 62.0)  # degrees about Z; 0 faces the camera (-Y); 90 faces +X
girl.rotation_euler = (0, 0, math.radians(GIRL_YAW))
girl.location = (GIRL_POS[0], GIRL_POS[1], 0.0)
bpy.context.view_layer.update()
hip = rig.matrix_world @ rig.pose.bones["thigh.L_MECH_RIG"].head
soles = [(rig.matrix_world @ rig.pose.bones[n + "_MECH_RIG"].tail).z for n in ("toe.L", "toe.R", "foot.L", "foot.R")]
girl.location.z = -min(soles) + 0.03  # feet on the floor
girl.location.x += GIRL_POS[0] - hip.x  # the hip (not the model's origin) goes where the chair is
girl.location.y += GIRL_POS[1] - hip.y
bpy.context.view_layer.update()
hip = rig.matrix_world @ rig.pose.bones["thigh.L_MECH_RIG"].head
SEAT_Z = hip.z - 0.07
fwd = Vector((math.sin(math.radians(GIRL_YAW)), -math.cos(math.radians(GIRL_YAW)), 0))  # her facing direction
print("girl hip", hip, "seat", SEAT_Z, "facing", fwd)
cyl("seat", 0.25, 0.07, (hip.x, hip.y, SEAT_Z), mat("chair", (0.10, 0.10, 0.20), 0.6))
box("chair_back", (0.5, 0.07, 0.6), (hip.x - fwd.x * 0.24, hip.y - fwd.y * 0.24, SEAT_Z + 0.36),
    mat("chairb", (0.10, 0.10, 0.20), 0.6), rot=(0, 0, math.atan2(fwd.y, fwd.x) + math.pi / 2))
cyl("chair_post", 0.03, SEAT_Z - 0.05, (hip.x, hip.y, (SEAT_Z - 0.05) / 2), M_DARK)
cyl("chair_base", 0.28, 0.03, (hip.x, hip.y, 0.04), M_DARK)

# alive: breathing, a head bob on every beat, thumbs, a slow sway; keyframed on the pose bones
def bob(u):
    return beat_pulse(u, 5)


for name, fn in (("spine.003", lambda u: (BASE["spine.003"][0] + 1.6 * math.sin(u * TAU * 8) - 1.5 * K * bob(u), 0,
                                          2.0 * math.sin(u * TAU * 2))),
                 ("spine.005", lambda u: (BASE["spine.005"][0] - 3.5 * bob(u) - 4.0 * K * bob(u), 0,
                                          4.0 * math.sin(u * TAU * 2 + 0.6))),
                 ("hand.L", lambda u: (4 * math.sin(u * TAU * BEATS / 2), 0, 0)),
                 ("hand.R", lambda u: (4 * math.sin(u * TAU * BEATS / 2 + 1.7), 0, 0))):
    pb = rig.pose.bones[name + "_MECH_RIG"]
    pb.rotation_mode = "XYZ"
    for f in list(range(1, L + 1)) + [L + 1]:
        u = ((f - 1) % L) / L if f <= L else 0.0
        x, y, z = fn(u)
        pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
        pb.keyframe_insert("rotation_euler", frame=f)

# the phone in her hands: its blue light on her face (the "blue light" of the song)
hand_mid = (rig.matrix_world @ rig.pose.bones["hand.L_MECH_RIG"].head + rig.matrix_world @ rig.pose.bones["hand.R_MECH_RIG"].head) / 2
phone2 = box("phone_hand", (0.09, 0.17, 0.008), hand_mid + Vector((0, 0, 0.02)), mat("ph2", (0.25, 0.6, 1.0), 0.3, emit=3.0),
             rot=(math.radians(-25), 0, math.radians(GIRL_YAW)))
animate(phone2.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value",
        lambda u: 2.0 + 3.0 * math.exp(-5 * bar_u(u)) + 1.5 * K * bob(u))
_, d_ph = lamp("phone_glow", "POINT", tuple(hand_mid + Vector((0, 0, 0.25)) + fwd * 0.1), (0.3, 0.6, 1.0), 12)
animate(d_ph, "energy", lambda u: 8 + 14 * math.exp(-5 * bar_u(u)) + 8 * K * bob(u))

# floating hearts rise from the monitor in the intense mix (loop-safe: whole cycles)
for i in range(7):
    hh = heart_mesh("fh", 0.09, M_HEART)
    hh.rotation_euler = (math.radians(90), 0, 0)
    phase = i / 7
    cyc = 1 + (i % 2)
    x0 = 0.2 + 1.1 * ((i * 0.37) % 1.0)

    def fl(u, p=phase, c=cyc, x0=x0):
        t = (u * c + p) % 1.0
        return (x0 + 0.12 * math.sin(t * TAU * 2), SCR_Y - 0.3, 1.5 + 1.2 * t)

    animate(hh, "location", fl)
    animate(hh, "scale", lambda u, p=phase, c=cyc: tuple(
        (K * math.sin(math.pi * ((u * c + p) % 1.0)) * (1.0 + 0.4 * beat_pulse(u)),) * 3))

# lights -------------------------------------------------------------------------
_, d_win = lamp("window_blue", "AREA", (-1.2, 2.3, 2.0), (0.35, 0.45, 1.0), 260, rot=(math.radians(-100), 0, 0), size=2.2)
animate(d_win, "energy", lambda u: 260 * (1.0 + 0.10 * math.sin(u * TAU * 2) + 0.35 * K * beat_pulse(u, 6)))
_, d_rim = lamp("rim", "AREA", (3.4, 0.2, 2.2), RIM, 120, rot=(0, math.radians(-70), math.radians(70)), size=2.0)
animate(d_rim, "energy", lambda u: 120 * (1.0 + 0.8 * K * beat_pulse(u, 5)))
# the blue light dancing on the ceiling: a spot whose pool wanders and flickers
sp, d_sp = lamp("ceiling_blue", "SPOT", (0.2, 0.3, 1.2), (0.3, 0.5, 1.0), 900, rot=(math.radians(180), 0, 0))
d_sp.spot_size = math.radians(70)
animate(sp, "rotation_euler", lambda u: (math.radians(180 + 14 * math.sin(u * TAU * 2)), math.radians(16 * math.sin(u * TAU)), 0))
animate(d_sp, "energy", lambda u: 500 * (0.6 + 0.4 * math.sin(u * TAU * 4) ** 2 + 0.7 * K * beat_pulse(u, 6)))
_, d_fill = lamp("fill", "POINT", (0.0, -3.0, 2.4), (0.8, 0.6, 1.0), 120)

# camera: a gentle sway so the still room breathes
cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 36.0
cam_d.clip_start = 0.1
cam = bpy.data.objects.new("cam", cam_d)
link(cam)
cam.location = (0.1, -4.4, 1.55)
cam.rotation_euler = (math.radians(88.5), 0, math.radians(0.5))
sc.camera = cam
animate(cam, "location", lambda u: (0.1 + 0.05 * math.sin(u * TAU), -4.4 + 0.04 * math.sin(u * TAU * 2), 1.55 + 0.015 * math.sin(u * TAU * 4)))

# neon sign + city windows twinkle
animate(neon.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"], "default_value",
        lambda u: 6.0 + 3.0 * (1.0 if (int(u * BEATS * 2) % 7 != 3) else 0.15) + 5.0 * K * beat_pulse(u, 6))

for obj in bpy.data.objects:
    if obj.type == "MESH":
        for p in obj.data.polygons:
            p.use_smooth = p.use_smooth
if P.get("close"):  # a test camera: [x, y, z, lens, target x, y, z]
    cx, cy, cz, ln, tx, ty, tz = P["close"]
    animate_off = cam.animation_data and cam.animation_data.action
    if animate_off:
        cam.animation_data_clear()
    cam.location = (cx, cy, cz)
    cam_d.lens = ln
    d = Vector((tx - cx, ty - cy, tz - cz))
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
if job.get("params", {}).get("only"):
    for f in job["params"]["only"]:
        sc.frame_set(f)
        sc.render.filepath = str(Path(job["out_dir"]) / f"{f:05d}")
        bpy.ops.render.render(write_still=True)
else:
    bpy.ops.render.render(animation=True)
print("lofi_room done", L)
