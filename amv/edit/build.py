"""An effect-heavy music edit from a spec: a montage shot list (amv.intro.montage
format: zooms, pans, velocity ramps, punches, whips, shakes, flashes), plus
stutters, glitch effects on beats, kinetic text and 3D shots made in Blender.

    ./amv.sh edit workspace/global/edits/NAME.json            # render -> workspace/output/edits/NAME.mp4
    ./amv.sh edit SPEC --sheet                                 # every shot's start/mid/end as it will be framed
    ./amv.sh edit SPEC --frames 7.5,13.4,14.9                  # finished frames at those times (PNG)
    ./amv.sh edit SPEC --from 12 --to 16                       # render only that stretch (a quick look)

Spec (times are output seconds; frames = round(t * fps)):

    {"name", "song", "song_start", "seconds", "fps": 60, "width": 1080, "height": 1920,
     "look": {"contrast", "saturation", "vignette", "tint", "lift"}, "fade_in": 0, "fade_out": 0,  # seconds
     "tail": {"from": 28.7, "xfade": 0.06},         # end on the instrumental (a clean loop)
     "shots": [...],                                 # amv.intro.montage shots ("file", "at", "until", ...)
     "stutter": [{"at", "until", "hold": 4}],        # repeat each `hold` frames: a stuck, skipping picture
     "fx": [{"kind": "slice", "at", "until", "amount": 1, "shape": "decay", ...settings}],
     "always": {"scanlines": {"amount": 0.2}, "grain": {"amount": 5}},   # every frame
     "bass_zoom": {"from": 14.8, "until": 29.7, "amount": 0.05},       # zoom pulses with the bass
     "text": [{"text", "at", "until", ...}],          # amv.edit.text
     "blender": [{"script": "shatter", "at", "until", "params": {...}}]}

"kind" is any video_fx plug-in (./amv.sh plugins: the glitch_fx set - rgb_split,
slice, blocks, chroma, pixelate, posterize, invert, scanlines - and glow, grain,
outline). "shape" shapes `amount` across the event: flat, decay (hit then fade),
rise, pulse (up and down), flicker (on/off every 2 frames).

A "blender" segment: the finished-looking base frames of [at, until) are written
as PNGs, `amv/edit/blender/<script>.py` (or a path) runs in Blender headless with
{"in_dir", "out_dir", "fps", "width", "height", "frames", "at", "params"}, and
its PNGs replace those frames (glitch fx and text still go on top). Cached by
the frames' plan + script + params, so a text change does not re-render 3D.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from amv import plugins
from amv.core import paths
from amv.edit import audio, text
from amv.intro.montage import build as montage_plan
from amv.intro.remake import compose, fetch_frames, fetch_size, look_filter

SCRIPTS = Path(__file__).with_name("blender")


def frame_of(t: float, fps: float) -> int:
    return int(round(t * fps))


def plan_of(spec: dict) -> dict:
    """The montage plan (one entry per output frame) with stutters applied."""
    plan = montage_plan({"fade_in": 0.0, "fade_out": 0.0, **spec}, Path(spec["song"]))
    fps, frames = spec["fps"], plan["frames"]
    for st in spec.get("stutter", []):
        a, b, hold = frame_of(st["at"], fps), frame_of(st["until"], fps), int(st.get("hold", 4))
        for i in range(a, min(b, len(frames))):
            frames[i] = dict(frames[a + ((i - a) // hold) * hold if st.get("freeze") is None else a])
    return plan


def shape(kind: str, u: float, n: int) -> float:
    """Envelope 0-1 at fraction u of an event."""
    if kind == "decay":
        return (1 - u) ** 2
    if kind == "rise":
        return u * u
    if kind == "pulse":
        return math.sin(math.pi * u)
    if kind == "flicker":
        return float((n // 2) % 2 == 0)
    return 1.0


class Renderer:
    """Turns plan entries into finished frames (base -> look -> fx -> text -> always)."""

    def __init__(self, spec: dict, plan: dict, wav: Path):
        self.spec, self.plan = spec, plan
        self.fps, self.w, self.h = spec["fps"], spec["width"], spec["height"]
        self.src_w, self.src_h = fetch_size(self.w, self.h)
        self.out_size = None if (self.src_w, self.src_h) == (self.w, self.h) else (self.w, self.h)
        self.look = look_filter(spec.get("look"), self.w, self.h)
        self.sources: dict = {}
        self.loaded: tuple[int, int] = (-1, -1)
        bz = spec.get("bass_zoom")
        self.bass = audio.bass_envelope(wav, self.fps, len(plan["frames"])) if bz else None
        self.events = sorted(spec.get("fx", []), key=lambda e: plugins.get("video_fx", e["kind"]).order)
        self.always = [(plugins.get("video_fx", k), v) for k, v in (spec.get("always") or {}).items()]
        self.always.sort(key=lambda p: p[0].order)
        self.blender: dict[int, Path] = {}

    def entry(self, i: int) -> dict:
        e = dict(self.plan["frames"][i])
        bz = self.spec.get("bass_zoom")
        if bz and bz.get("from", 0) <= i / self.fps < bz.get("until", 1e9):
            e["punch"] = round(e.get("punch", 1.0) * (1 + float(bz["amount"]) * float(self.bass[i])), 4)
        return e

    def base(self, i: int) -> np.ndarray:
        """The composed, graded frame i - what Blender gets as its footage."""
        chunk = 48
        if not (self.loaded[0] <= i < self.loaded[1]):
            a = (i // chunk) * chunk
            b = min(len(self.plan["frames"]), a + chunk)
            self.sources = fetch_frames([self.entry(k) for k in range(a, b)], self.src_w, self.src_h)
            self.loaded = (a, b)
        return self.look(compose(self.entry(i), self.sources, self.out_size))

    def finish(self, i: int, frame: np.ndarray) -> np.ndarray:
        t = i / self.fps
        f = frame.astype(np.float32)
        for ev in self.events:
            a, b = ev["at"], ev["until"]
            if not (a <= t < b):
                continue
            plug = plugins.get("video_fx", ev["kind"])
            u = (t - a) / max(1e-6, b - a)
            amount = float(ev.get("amount", 1.0)) * shape(ev.get("shape", "flat"), u, i)
            if amount <= 0.01:
                continue
            settings = {**plug.defaults, **{k: v for k, v in ev.items() if k not in ("kind", "at", "until", "shape")},
                        "amount": amount}
            f = plugins.call(plug.apply, f, frame, settings, i)
        out = np.clip(f, 0, 255).astype(np.uint8)
        for entry in self.spec.get("text", []):
            if entry["at"] <= t < entry["until"]:
                out = text.draw(out, entry, t, i, self.fps)
        if self.always:
            f = out.astype(np.float32)
            for plug, settings in self.always:
                f = plugins.call(plug.apply, f, out, {**plug.defaults, **settings}, i)
            out = np.clip(f, 0, 255).astype(np.uint8)
        return out

    def frame(self, i: int) -> np.ndarray:
        path = self.blender.get(i)
        base = np.asarray(Image.open(path).convert("RGB")) if path else self.base(i)
        return self.finish(i, base)


def blender_segments(spec: dict, r: Renderer, work: Path) -> None:
    """Render every "blender" segment (cached) and point r.blender at its frames."""
    from amv.blender.setup import find_blender

    for seg in spec.get("blender", []):
        a, b = frame_of(seg["at"], r.fps), frame_of(seg["until"], r.fps)
        script = Path(seg["script"]) if seg["script"].endswith(".py") else SCRIPTS / f"{seg['script']}.py"
        key_src = json.dumps([[r.entry(i) for i in range(a, b)], spec.get("look"), seg, r.fps, r.w, r.h,
                              script.read_text(encoding="utf-8")], sort_keys=True)
        key = hashlib.sha1(key_src.encode()).hexdigest()[:12]
        seg_dir = work / "blender" / f"{script.stem}_{a}_{key}"
        out_dir = seg_dir / "out"
        done = seg_dir / "done"
        if not done.exists():
            in_dir = seg_dir / "in"
            in_dir.mkdir(parents=True, exist_ok=True)
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"Blender segment {script.stem}: writing {b - a} base frames...", flush=True)
            for i in range(a, b):
                Image.fromarray(r.base(i)).save(in_dir / f"{i - a + 1:05d}.png", compress_level=1)
            job = {"in_dir": str(in_dir), "out_dir": str(out_dir), "fps": r.fps, "width": r.w, "height": r.h,
                   "frames": b - a, "at": seg["at"], "params": seg.get("params", {})}
            (seg_dir / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
            blender = find_blender()
            if blender is None:
                raise SystemExit("Blender not found (./amv.sh blender-setup --check)")
            print(f"Blender segment {script.stem}: rendering (headless)...", flush=True)
            run = subprocess.run([str(blender), "-b", "--factory-startup", "--python", str(script), "--",
                                  str(seg_dir / "job.json")], capture_output=True, text=True)
            log = run.stdout + run.stderr
            (seg_dir / "blender.log").write_text(log, encoding="utf-8")
            got = sorted(out_dir.glob("*.png"))
            if run.returncode != 0 or len(got) < b - a:
                raise SystemExit(f"Blender segment {script.stem} failed ({len(got)}/{b - a} frames); "
                                 f"log {seg_dir / 'blender.log'}:\n{log[-2500:]}")
            done.write_text("ok")
        for i in range(a, b):
            r.blender[i] = out_dir / f"{i - a + 1:05d}.png"


def sheet(spec: dict, r: Renderer, out: Path) -> None:
    """Every shot's first, middle and last frame as framed (no fx), labelled."""
    shots = spec["shots"]
    starts = [0.0] + [s["until"] for s in shots[:-1]]
    tw, th = 216, 384
    cols = 3 * 4
    rows = math.ceil(len(shots) / 4)
    img = Image.new("RGB", (cols * tw, rows * (th + 24)), (10, 10, 12))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(text.font_path("DejaVuSans-Bold"), 16)
    for k, (s, t0) in enumerate(zip(shots, starts, strict=True)):
        ts = [t0 + 1 / r.fps, (t0 + s["until"]) / 2, s["until"] - 1.5 / r.fps]
        for j, t in enumerate(ts):
            i = min(len(r.plan["frames"]) - 1, frame_of(t, r.fps))
            thumb = Image.fromarray(r.base(i)).resize((tw, th), Image.BILINEAR)
            x, y = ((k % 4) * 3 + j) * tw, (k // 4) * (th + 24)
            img.paste(thumb, (x, y + 24))
        label = f"{k + 1} {s.get('id', '')} {t0:.2f}-{s['until']:.2f}"
        d.text(((k % 4) * 3 * tw + 4, (k // 4) * (th + 24) + 3), label, font=font, fill=(255, 220, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=88)
    print(f"Wrote {out}", flush=True)


def encode(spec: dict, r: Renderer, wav: Path, out: Path, a: int, b: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    seconds = (b - a) / r.fps
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{r.w}x{r.h}",
         "-r", str(r.fps), "-i", "-", "-ss", f"{a / r.fps:.4f}", "-t", f"{seconds:.4f}", "-i", str(wav),
         "-map", "0:v", "-map", "1:a", "-map_metadata", "-1",
         # capped: per-frame grain + scanlines made CRF 14 alone 155 Mbit/s (579 MB for 30 s)
         "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "50M", "-bufsize", "100M",
         "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-t", f"{seconds:.4f}", "-movflags", "+faststart",
         str(out)], stdin=subprocess.PIPE)
    for i in range(a, b):
        if (i - a) % 120 == 0:
            print(f"  frame {i}/{b}", flush=True)
        proc.stdin.write(np.ascontiguousarray(r.frame(i)).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True).stdout.split()
    print(f"Wrote {out}  streams: {' '.join(probe)}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--sheet", action="store_true", help="shot sheet only")
    parser.add_argument("--frames", default="", help="comma-separated output times: finished frames as PNG")
    parser.add_argument("--from", dest="t0", type=float, default=None)
    parser.add_argument("--to", dest="t1", type=float, default=None)
    parser.add_argument("--no-blender", action="store_true", help="skip the 3D segments (base frames instead)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    name = spec.get("name", args.spec.stem)
    work = paths.EDIT / name
    work.mkdir(parents=True, exist_ok=True)
    wav = audio.window(spec, spec["song"], work)
    plan = plan_of(spec)
    r = Renderer(spec, plan, wav)
    total = len(plan["frames"])
    if args.sheet:
        sheet(spec, r, work / "sheet.jpg")
        return
    if not args.no_blender:
        blender_segments(spec, r, work)
    if args.frames:
        for t in (float(x) for x in args.frames.split(",")):
            i = min(total - 1, frame_of(t, r.fps))
            p = work / "frames" / f"{t:07.3f}.png"
            p.parent.mkdir(exist_ok=True)
            Image.fromarray(r.frame(i)).save(p)
            print(f"Wrote {p}", flush=True)
        return
    a = frame_of(args.t0, r.fps) if args.t0 is not None else 0
    b = frame_of(args.t1, r.fps) if args.t1 is not None else total
    full = a == 0 and b == total
    out = args.out or (paths.EDITS_OUT / f"{name}.mp4" if full else work / f"part_{a}_{b}.mp4")
    encode(spec, r, wav, out, a, b)


if __name__ == "__main__":
    main()
