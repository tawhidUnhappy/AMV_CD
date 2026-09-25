"""A montage edit, written as a short shot list, turned into a frame plan for
the remake renderer - for intros cut like an editor would cut them: beat-
timed shots, dissolves in the quiet part, a push-in on every shot, flashes,
zoom punches and a whoosh into the drop.

    ./amv.sh montage amv/intro/montages/channel_intro.json [--song PATH] [--out PATH]

Spec (times are output seconds; "at" is where a shot starts in its file):

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
  ends; {"flash": s} fades in from white; {"punch": p, "frames": n, "rgb": px}
  starts zoomed in by p and settles over n frames with a fading RGB split;
- "out": {"whoosh": n} zoom-blurs the shot's last n frames, harder each frame.
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
        src_t = shot["at"] + (t - start) * shot.get("speed", 1.0)
        return {"file": shot["file"], "n": round(src_t * SOURCE_FPS), "punch": round(z0 + (z1 - z0) * k, 4),
                "center": shot.get("center", [0.5, 0.5])}

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
            "audio": {"file": str(song), "delay": spec.get("audio_delay", 0.0), "fade_out": spec.get("fade_out", 0.0)}}


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
