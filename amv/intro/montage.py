"""A montage edit, written as a short shot list, turned into a frame plan for
the remake renderer - for intros cut like an editor would cut them: beat-
timed shots, dissolves in the quiet part, a push-in on every shot, flashes,
zoom punches and a whoosh into the drop.

    ./amv.sh montage amv/intro/montages/channel_intro.json [--song PATH] [--out PATH]

Spec (times are output seconds; "at" is where a shot starts in its file;
"song_start" is where in the song the intro begins):

    {"fps": 24, "width": 1920, "height": 1080, "seconds": 11.0,
     "look": {"contrast": 1.08, "saturation": 1.12, "vignette": 0.35},
     "fade_in": 0.7, "fade_out": 0.45,
     "shots": [
       {"file": "...mkv", "at": 310.0, "until": 2.3, "zoom": [1.0, 1.08], "center": [0.5, 0.5],
        "speed": 1.0, "in": {"dissolve": 0.5}},
       {"file": "...", "at": 861.8, "until": 5.57, "out": {"whoosh": 3}},
       {"file": "...", "at": 1159.4, "until": 6.25, "in": {"flash": 0.25}},
       {"file": "...", "at": 263.0, "until": 8.96, "in": {"punch": 1.3, "frames": 5, "rgb": 12}}]}

- a shot runs from the previous shot's "until" to its own;
- "zoom" [from, to] is a steady push-in across the shot (about "center");
- "in": {"dissolve": s} crosses from the previous shot over s seconds
  centred on the cut, so BOTH shots need s/2 of clean footage past their
  ends; {"flash": s, "flash_color": [r, g, b]} fades in from white (or that
  colour); {"dip": n} comes up out of black over n frames; {"punch": p, "frames": n, "rgb": px}
  starts zoomed in by p and settles over n frames with a fading RGB split;
- "out": {"whoosh": n} zoom-blurs the shot's last n frames, harder each frame;
  "out": {"whip": {"dir": [dx, dy], "frames": n}} whips through the cut: the
  last n frames of this shot and the first n of the next smear and slide
  along the same direction (the flow between two shots);
- "in": {"shake": {"amount": 0.02, "frames": 6}} jolts the frame on impact;
- "pan": [[x0, y0], [x1, y1]] moves the frame centre across the shot (zoom
  in first so there is room), "ease": true eases zoom and pan in and out;
- "speed" below 1 is slow motion (a shorter clean window can fill a longer slot).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from amv.core import config, paths
from amv.intro.remake import SOURCE_FPS, render


def build(spec: dict, song: Path) -> dict:
    fps, seconds = spec["fps"], spec["seconds"]
    shots = spec["shots"]
    starts = [0.0] + [s["until"] for s in shots[:-1]]
    total = round(seconds * fps)

    def source(shot: dict, start: float, t: float) -> dict:
        """Where `shot` is at output time t (may run past its own window)."""
        z0, z1 = shot.get("zoom", [1.0, 1.0])
        length = max(1e-6, shot["until"] - start)
        k = min(max((t - start) / length, 0.0), 1.0)
        ease = k * k * (3 - 2 * k) if shot.get("ease") else k
        src_t = shot["at"] + (t - start) * shot.get("speed", 1.0)
        c0, c1 = shot.get("pan", [shot.get("center", [0.5, 0.5])] * 2)
        center = [round(c0[0] + (c1[0] - c0[0]) * ease, 4), round(c0[1] + (c1[1] - c0[1]) * ease, 4)]
        return {"file": shot["file"], "n": round(src_t * SOURCE_FPS), "punch": round(z0 + (z1 - z0) * ease, 4),
                "center": center}

    frames = []
    for i in range(total):
        t = i / fps
        k = next((j for j, s in enumerate(shots) if t < s["until"] - 1e-9), len(shots) - 1)
        shot, start = shots[k], starts[k]
        entry = source(shot, start, t)
        into = shot.get("in", {})
        if "punch" in into:
            n = into.get("frames", 4)
            step = round((t - start) * fps)
            if step < n:
                ease = (1 - step / n) ** 2
                entry["punch"] = round(entry["punch"] * (1 + (into["punch"] - 1) * ease), 4)
                entry["rgb"] = round(into.get("rgb", 0) * ease)
        if "flash" in into and t - start < into["flash"]:
            entry["flash"] = round(1 - (t - start) / into["flash"], 3)
            if "flash_color" in into:
                entry["flash_color"] = into["flash_color"]
        if "dip" in into:  # comes up out of black over n frames (a flicker)
            n = into["dip"]
            step = round((t - start) * fps)
            if step < n:
                entry["dim"] = round(1 - step / n, 3)
        # A dissolve centred on this shot's start: before the cut the previous
        # shot is on top, fading out; after it, this one, fading in.
        half = into.get("dissolve", 0.0) / 2
        if half and k > 0 and t - start < half:
            before = source(shots[k - 1], starts[k - 1], t)
            entry["blend"] = {**before, "alpha": round(0.5 - (t - start) / (2 * half), 3)}
        nxt = shots[k + 1] if k + 1 < len(shots) else None
        half_next = nxt.get("in", {}).get("dissolve", 0.0) / 2 if nxt else 0.0
        if half_next and shot["until"] - t <= half_next:
            after = source(nxt, shot["until"], t)
            entry["blend"] = {**after, "alpha": round(0.5 - (shot["until"] - t) / (2 * half_next), 3)}
        # A whip across the cut: the outgoing shot slides and smears along
        # "dir" over its last n frames, the incoming one arrives along the
        # same direction and settles over its first n - so the movement reads
        # as one camera move through both shots.
        step_in = round((t - start) * fps)
        frames_left_out = round((shot["until"] - t) * fps)
        whip_out = shot.get("out", {}).get("whip")
        prev_whip = shots[k - 1].get("out", {}).get("whip") if k > 0 else None
        for whip, pos in ((whip_out, frames_left_out), (prev_whip, step_in)):
            if not whip:
                continue
            n = whip.get("frames", 3)
            if pos < n or (whip is whip_out and pos <= n):
                amount = (1 - pos / n) if whip is prev_whip else (1 - (pos - 1) / n)
                amount = max(0.0, min(1.0, amount))
                dx, dy = whip["dir"]
                width, height = spec.get("width", 1920), spec.get("height", 1080)
                entry["dblur"] = [round(dx * amount * width * 0.12), round(dy * amount * height * 0.12)]
                # Slide: leaving pushes the frame on along dir, arriving comes from behind it.
                sign = 1 if whip is whip_out else -1
                shift = 0.06 * amount * sign
                entry["punch"] = max(entry["punch"], 1.12)
                entry["center"] = [round(entry["center"][0] - dx * shift, 4), round(entry["center"][1] - dy * shift, 4)]
        shake = into.get("shake")
        if shake and step_in < shake.get("frames", 6):
            decay = 1 - step_in / shake.get("frames", 6)
            rng = (hash((k, step_in)) % 1000) / 1000.0, (hash((step_in, k, 7)) % 1000) / 1000.0
            amp = shake.get("amount", 0.02) * decay
            entry["punch"] = max(entry["punch"], 1.0 + 2.2 * shake.get("amount", 0.02))
            entry["center"] = [round(entry["center"][0] + (rng[0] - 0.5) * 2 * amp, 4),
                               round(entry["center"][1] + (rng[1] - 0.5) * 2 * amp, 4)]
        whoosh = shot.get("out", {}).get("whoosh", 0)
        frames_left = round((shot["until"] - t) * fps)
        if whoosh and frames_left <= whoosh:
            entry["fx"] = "zoom_blur"
            entry["strength"] = round(0.12 * (whoosh - frames_left + 1), 3)
        if t < spec.get("fade_in", 0.0):
            entry["dim"] = round(1 - t / spec["fade_in"], 3)
        tail = seconds - t
        if tail < spec.get("fade_out", 0.0):
            entry["dim"] = round(1 - tail / spec["fade_out"], 3)
        frames.append(entry)
    return {"fps": fps, "width": spec.get("width", 1920), "height": spec.get("height", 1080), "seconds": seconds,
            "frames": frames, "look": spec.get("look"), "caption": None,
            "audio": {"file": str(song), "start": spec.get("song_start", 0.0), "delay": spec.get("audio_delay", 0.0),
                      "fade_out": spec.get("fade_out", 0.0), "fade_in": spec.get("audio_fade_in", 0.0)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--song", type=Path, default=None, help="default: the spec's song, then config.json's")
    parser.add_argument("--out", type=Path, default=paths.INTRO / "montage.mp4")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    song = (args.song or (Path(spec["song"]) if spec.get("song") else None) or config.load().require_song()).resolve()
    plan = build(spec, song)
    plan_path = paths.INTRO / "montage_plan.json"
    plan_path.write_text(json.dumps(plan, indent=0), encoding="utf-8")
    print(f"Wrote {plan_path} ({len(plan['frames'])} frames, {len(spec['shots'])} shots)", flush=True)
    render(plan, args.out)


if __name__ == "__main__":
    main()
