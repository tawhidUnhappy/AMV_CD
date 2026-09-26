"""A vertical Short from a spec: the song window, the slots, each shot's sub-
window, crop, speed and effects - all derived - then the montage renderer,
then title.txt / description.txt beside the video.

    ./amv.sh short amv/shorts/specs/NAME.json [--plan-only] [--deliver DIR]

Spec (amv/shorts/specs/*.json; ids come from ./amv.sh short-find sheets):

    {"name": "hell_mode_alquimia", "series": "Hell_Mode", "anime": "Hell Mode",
     "song": "/mnt/datadisk/song/X.mp3", "drop": 25.7, "build": 7.0, "seconds": 24,
     "mood": "power",                      # look + effect strength: power | dark | soft
     "build_shots": ["12-451.0", "12-491.1"],   # before the drop, calm-ish
     "drop_shot": "12-472.0",                   # lands on the drop
     "shots": ["12-495.0", {"id": "12-497.5", "x": 0.35}, ...],   # after it, one per cut
     "title": "...", "hook": "...", "tags": ["hellmode", ...]}

A shot entry is an id, or {"id", "why" (kept in the catalog), "x"/"y" (crop
centre, 0-1), "at" (source start), "speed", "zoom": [a, b]}. The last shot
holds to the end. Every build records the song window and each shot used
(crop, mood, why) in amv/shorts/catalog/ - see amv.shorts.catalog.

What is derived, and the rule behind it:
- slots: build shots split the build on its beats; after the drop a cut
  every N bass hits, N the smallest giving >= MIN_CUT s (anime is drawn on
  twos/threes; faster reads as flicker); the last shot takes what is left;
- sub-window: from the id's time when it is not the shot's start (someone
  saw that moment); else the stretch of the shot with the most motion
  (index, 8 fps) that fits the slot at the chosen speed; a shot too short is slowed, down to
  MIN_SPEED, rather than run past its cut;
- crop: a vetted x from the catalog if there is one, else the crop-wide band with the most detail/colour (find.crop_x), height
  from the focal point (amv.intro.flow.focus) when zoomed in;
- effects: build pushes in and dissolves, the last build shot zoom-blurs into
  the drop; the drop gets a flash + punch + RGB split + shake and a 4-frame
  impact freeze; every cut on an accent (a strongest-quartile hit) gets a
  punch and a shake and a velocity ramp (fast in, eased out); every 4th cut a
  short flash; a shot moving fast at its tail whips into the next along its
  measured direction; the end holds on a slow push with a fade.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from amv.intro.library import INDEX_FPS
from amv.intro.montage import build as montage_plan
from amv.intro.remake import render
from amv.shorts import catalog, find
from amv.shorts.song import analyse, find_drops, window

WIDTH, HEIGHT, FPS = 1080, 1920, 24
MIN_CUT = 0.75
MIN_SPEED = 0.45
DELIVER = Path("/mnt/datadisk/shorts")

LOOKS = {
    "power": {"contrast": 1.14, "saturation": 1.12, "lift": 2, "vignette": 0.45},
    "dark": {"contrast": 1.2, "saturation": 0.88, "lift": 4, "tint": [1.05, 0.95, 0.97], "vignette": 0.55},
    "soft": {"contrast": 1.04, "saturation": 1.08, "lift": 3, "tint": [1.03, 0.99, 1.02], "vignette": 0.3},
}
# (drop punch, accent punch, shake amount, rgb px) per mood
FORCE = {"power": (1.35, 1.16, 0.02, 14), "dark": (1.3, 1.14, 0.018, 12), "soft": (1.18, 1.07, 0.008, 6)}
IMPACT = [[0, 0.15], [0.12, 0.15], [0.3, 1.0], [1, 1.0]]
RAMP = [[0, 1.7], [0.3, 0.7], [1, 1.0]]


def mean_speed(keys: list[list[float]] | None, steps: int = 200) -> float:
    """Average of a montage velocity curve (same smoothstep as montage.build)."""
    if not keys:
        return 1.0
    keys = sorted(keys)

    def at(f: float) -> float:
        if f <= keys[0][0]:
            return keys[0][1]
        for (f0, v0), (f1, v1) in zip(keys, keys[1:], strict=False):
            if f <= f1:
                u = (f - f0) / max(1e-6, f1 - f0)
                return v0 + (v1 - v0) * u * u * (3 - 2 * u)
        return keys[-1][1]

    return sum(at((j + 0.5) / steps) for j in range(steps)) / steps


def slots(spec: dict, w) -> list[tuple[float, float]]:
    """(start, end) in output seconds for build shots, the drop shot, the rest."""
    builds = spec.get("build_shots", [])
    drop_at = w.drop - w.start
    cuts: list[float] = []
    beats = [b - w.start for b in w.build_beats]
    for k in range(1, len(builds)):
        target = drop_at * k / len(builds)
        cuts.append(min(beats, key=lambda b: abs(b - target)) if beats else target)
    if builds:
        cuts.append(drop_at)
    every = max(1, math.ceil(MIN_CUT / w.period - 1e-6))
    hits = [h - w.start for h in w.hits]
    # the drop shot + each drive shot starts on every `every`-th hit
    count = 1 + len(spec.get("shots", []))
    starts = hits[::every][:count]
    if len(starts) < count:
        raise SystemExit(f"{count} shots after the drop need {count * every} hits; the window has {len(hits)} - "
                         f"drop {count - len(starts)} shot(s) or lengthen 'seconds'")
    cuts += starts[1:]
    edges = [0.0, *cuts, w.seconds]
    return [(round(a, 4), round(b, 4)) for a, b in zip(edges, edges[1:], strict=False)]


def best_offset(shot: find.Shot, need: float) -> float:
    """Source start of the busiest `need` s inside the shot (index motion)."""
    # Only near the start: a long "shot" may be several real ones (see plan()).
    room = min(shot.duration - need, max(2.0, need))
    if room <= 0.05:
        return shot.start + max(0.0, room) / 2
    e = next(x for x in find.load_show(shot.series) if x.number == shot.episode)
    diffs = e.diffs()
    a = int(shot.start * INDEX_FPS)
    span = max(1, int(need * INDEX_FPS))
    best, score = shot.start, -1.0
    for k in range(0, int(room * INDEX_FPS) + 1):
        seg = diffs[a + k:a + k + span]
        if len(seg) and seg.mean() > score:
            best, score = shot.start + k / INDEX_FPS, float(seg.mean())
    return round(min(best, shot.end - need), 3)


def measure(file: str, start: float, need: float) -> dict:
    return catalog.cached("measure", f"{file}|{start:.3f}|{need:.3f}", lambda: _measure(file, start, need))


def _measure(file: str, start: float, need: float) -> dict:
    from amv.intro.flow import focus, motion

    ys = [focus(file, start + need * k)[1] for k in (0.1, 0.5, 0.9)]
    m = motion(file, start, max(need, 0.3))
    return {"focus": [find.crop_x(file, start, start + need), float(np.median(ys))], "tail": m["tail"]}


def plan(spec: dict) -> tuple[dict, list[dict], object]:
    w = window(Path(spec["song"]), spec.get("seconds", 24.0), spec.get("build", 7.0), spec.get("drop"))
    mood = spec.get("mood", "power")
    drop_punch, accent_punch, shake, rgb = FORCE[mood]
    entries = [*({"role": "build", **_entry(s)} for s in spec.get("build_shots", [])),
               {"role": "drop", **_entry(spec["drop_shot"])},
               *({"role": "drive", **_entry(s)} for s in spec.get("shots", []))]
    entries[-1]["role"] = "end" if entries[-1]["role"] == "drive" else entries[-1]["role"]
    edges = slots(spec, w)
    accents = {round(a - w.start, 2) for a in w.accents}

    def prepare(item: tuple[int, dict]) -> dict:
        i, e = item
        a, b = edges[i]
        shot = find.shot_at(spec["series"], e["ep"], e["t"])
        length = b - a
        velocity = None
        if e["role"] == "drop":
            velocity = IMPACT
        elif e["role"] == "drive" and round(a, 2) in accents:
            velocity = RAMP
        speed = e.get("speed", {"build": 0.85, "end": 0.75}.get(e["role"], 1.0))
        need = length * speed * mean_speed(velocity)
        margin = 0.1
        if need > shot.duration - margin:  # slow it down rather than run over the cut
            speed *= (shot.duration - margin) / need
            need = shot.duration - margin
            if speed < MIN_SPEED:
                print(f"  ! {e['id']}: {shot.duration:.2f}s shot in a {length:.2f}s slot needs speed {speed:.2f}")
        # The id's time is the moment someone looked at; start there when it
        # fits. Searching the whole "shot" is only safe from a shot start: in
        # dark scenes the 8 fps index misses cuts, a "shot" can span 40 s, and
        # the busiest stretch of it is some other scene.
        if e.get("at"):
            at = e["at"]
        elif e["t"] - shot.start > 0.25 and e["t"] + need <= shot.end + 0.05:
            at = e["t"]
        else:
            at = best_offset(shot, need)
        m = measure(shot.file, at, need)
        if "x" not in e and catalog.vetted_x(spec["series"], e["id"]) is not None:
            e = {**e, "x": catalog.vetted_x(spec["series"], e["id"])}
        return {**e, "shot": shot, "slot": (a, b), "speed": round(speed, 3), "velocity": velocity, "at": at,
                "need": round(need, 3), "accent": round(a, 2) in accents, **m}

    with ThreadPoolExecutor(max_workers=6) as ex:
        items = list(ex.map(prepare, enumerate(entries)))

    shots = []
    drive_k = 0
    for i, it in enumerate(items):
        role, (_, b) = it["role"], it["slot"]
        fx, fy = it["focus"]
        x = it.get("x", fx)
        default_zoom = {"build": [1.0, 1.08], "drop": [1.06, 1.14], "end": [1.0, 1.12]}.get(
            role, [1.04, 1.13] if drive_k % 2 == 0 else [1.13, 1.04])
        zoom = it.get("zoom", default_zoom)
        y = it.get("y", min(max(fy, 0.5 - 0.5 * (1 - 1 / max(zoom))), 0.5 + 0.5 * (1 - 1 / max(zoom))))
        shot = {"why": f"{it['id']} ({role})", "file": it["shot"].file, "at": it["at"], "until": b,
                "zoom": zoom, "ease": True, "center": [round(x, 3), round(y, 3)], "speed": it["speed"]}
        if it["velocity"]:
            shot["velocity"] = it["velocity"]
        into: dict = {}
        if role == "build" and i > 0:
            into["dissolve"] = 0.3
        if role == "drop":
            into = {"flash": 0.3, "punch": drop_punch, "frames": 6, "rgb": rgb,
                    "shake": {"amount": shake * 1.4, "frames": 8}}
        elif role in ("drive", "end"):
            drive_k += 1
            if it["accent"]:
                into = {"punch": accent_punch, "frames": 4, "rgb": rgb // 2, "shake": {"amount": shake, "frames": 5}}
            if drive_k % 4 == 0:
                into["flash"] = 0.15
        if into:
            shot["in"] = into
        nxt = items[i + 1] if i + 1 < len(items) else None
        if role == "build" and nxt and nxt["role"] == "drop":
            shot["out"] = {"whoosh": 4}
        elif nxt and role in ("drop", "drive") and not nxt["accent"]:
            tx, ty = it["tail"]
            if math.hypot(tx, ty) > 0.08:  # real movement at the tail: carry it through the cut
                n = math.hypot(tx, ty)
                shot["out"] = {"whip": {"dir": [round(tx / n, 2), round(ty / n, 2)], "frames": 3}}
        # a dissolve eats half its length past both shots' windows: keep it
        # only where the footage is there
        if into.get("dissolve"):
            prev = items[i - 1]
            spare_prev = prev["shot"].end - (prev["at"] + prev["need"])
            if spare_prev < 0.2 or it["at"] - it["shot"].start < 0.2:
                del into["dissolve"]
                into["dip"] = 3
        shots.append(shot)
    montage = {"about": spec.get("about", spec["name"]), "fps": FPS, "width": WIDTH, "height": HEIGHT,
               "seconds": w.seconds, "song": spec["song"], "song_start": w.start, "audio_fade_in": 0.05,
               "look": LOOKS[mood], "fade_in": 0.2, "fade_out": 0.6, "shots": shots}
    return montage, items, w


def _entry(s) -> dict:
    e = {"id": s} if isinstance(s, str) else dict(s)
    ep, _, t = e["id"].partition("-")
    return {**e, "ep": int(ep), "t": float(t)}


def credit(song: Path) -> tuple[str, str]:
    """(title, artist) from "Title - Artist.mp3"; the artist is a visible
    placeholder when the file does not say - never a guess."""
    stem = song.stem
    title, sep, artist = stem.partition(" - ")
    return title.strip(), (artist.strip() if sep else "<ARTIST - fill in before posting>")


def write_text(spec: dict, out_dir: Path) -> None:
    title, artist = credit(Path(spec["song"]))
    tags = spec.get("tags", [])
    hashtags = " ".join(f"#{t}" for t in ["shorts", "anime", "amv", "animeedit", *tags])
    head = spec["title"]
    if "#shorts" not in head.lower() and len(head) + 8 <= 100:
        head += " #shorts"
    (out_dir / "title.txt").write_text(head + "\n", encoding="utf-8")
    body = [spec.get("hook", ""), "",
            f"Anime: {spec['anime']}",
            f"Song: {title} - {artist}", ""]
    if spec.get("about_short"):
        body += [spec["about_short"], ""]
    body += [hashtags, "",
             "All footage and music belong to their respective owners. This is a non-profit fan edit, "
             "made for entertainment under fair use - no copyright infringement intended.",
             f"Support the official release of {spec['anime']}."]
    (out_dir / "description.txt").write_text("\n".join(body).strip() + "\n", encoding="utf-8")


def review_sheet(video: Path, out: Path, every: float = 0.5) -> None:
    """Every `every` s of the render, small, in rows of 12 - crop and flow at a glance."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"fps={1 / every},scale=180:320,drawtext=text='%{{pts\\:hms}}':x=4:y=4:fontsize=16:"
                    "fontcolor=yellow:box=1:boxcolor=black@0.6,tile=12x5:padding=4",
                    "-frames:v", "1", "-update", "1", str(out)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--plan-only", action="store_true", help="print the plan, render nothing")
    parser.add_argument("--deliver", type=Path, default=DELIVER, help="copy video + texts to DIR/NAME/")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    montage, items, w = plan(spec)
    print(f"{spec['name']}: song {w.start:.2f}-{w.end:.2f}s (drop {w.drop:.2f}, beat {w.period:.3f}s), "
          f"{len(items)} shots")
    for it, s in zip(items, montage["shots"], strict=True):
        a, b = it["slot"]
        print(f"  {a:6.2f}-{b:6.2f} {it['role']:5s} {it['id']:10s} at {it['at']:8.2f} x{it['need']:.2f}s "
              f"speed {it['speed']:.2f} crop {s['center']} {'ACCENT' if it['accent'] else ''} "
              f"{json.dumps(s.get('in', {}))} {json.dumps(s.get('out', {}))}")
    catalog.record_short(spec, args.spec, items, w)
    a = analyse(Path(spec["song"]))
    catalog.record_song(Path(spec["song"]), find_drops(Path(spec["song"])), a["tempo"], a["duration"])
    out_dir = find.SHORTS / spec["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "montage.json").write_text(json.dumps(montage, indent=1), encoding="utf-8")
    write_text(spec, out_dir)
    if args.plan_only:
        return
    frames = montage_plan(montage, Path(spec["song"]))
    video = render(frames, out_dir / "short.mp4")
    review_sheet(video, out_dir / "review.jpg")
    print(f"Wrote {out_dir / 'review.jpg'}")
    if args.deliver:
        dest = args.deliver / spec["name"]
        dest.mkdir(parents=True, exist_ok=True)
        for f in ("short.mp4", "title.txt", "description.txt"):
            shutil.copy2(out_dir / f, dest / f)
        print(f"Delivered to {dest}")


if __name__ == "__main__":
    main()
