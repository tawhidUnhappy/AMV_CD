"""Render an intro frame by frame from a remake plan (tmp/intro/remake_plan.json).

A remake reproduces an existing intro: every output frame names the episode
frame it shows (found by amv.intro.reference), plus the few frames that are
effects rather than footage. The plan is data, so a different intro is a
different plan, not different code.

Plan:
    {"fps": 30, "width": 1920, "height": 1080, "seconds": 11.0,
     "frames": [{"ep": 2, "n": 32975}, ...,                   # one per output frame
                {"ep": 11, "n": 9510, "fx": "zoom_blur"},
                {"ep": 1, "n": 19539, "punch": 3.0, "rgb": 14, "center": [0.35, 0.45]}],
     "grade": [{"from": 284, "gain": [0.76, 0.74, 0.31], "offset": [17, 8.5, 5.5]}],
     "caption": {"text": "...", "from": 295, "fade": 3, "y": 0.89, "size": 58, "spacing": 5},
     "audio": {"file": "...", "delay": 0.242, "fade_out": 0.25}}

`n` is the episode's frame number (0 = its first frame at 24000/1001). A
frame is fetched by seeking half a frame before it, which lands on exactly
that frame; seeking to n/fps itself does not - the container's 7ms start
offset and millisecond timestamps put some seeks one frame late or early,
measured on every segment of the first remake.

A plan is usually built from a SPEC (amv/intro/remakes/*.json, committed)
plus the reference map amv.intro.reference wrote: the map supplies every
footage frame, the spec only the frames the map cannot (effects, shots from
outside these episodes) and the look (grade, caption, audio offset). See
build_plan() for the override forms.

    ./amv.sh reference VIDEO --seconds 11
    ./amv.sh remake --spec amv/intro/remakes/NAME.json [--song PATH]
    ./amv.sh remake --plan tmp/intro/remake_plan.json      # a plan edited by hand
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from amv.core import config, paths
from amv.core.ffmpeg_tools import choose_h264_encoder, h264_encoder_args, probe_duration

SOURCE_FPS = 24000 / 1001


def episode_files() -> dict[int, Path]:
    cfg = config.load()
    pattern = re.compile(cfg.episode_pattern, re.IGNORECASE)
    files = {}
    for path in sorted(cfg.require_source().iterdir()):
        match = pattern.search(path.name)
        if match and path.suffix.lower() in (".mkv", ".mp4", ".avi", ".webm"):
            files[int(match.group(1))] = path
    return files


def source_key(entry: dict) -> tuple[str | int, int]:
    """(file path or episode number, frame number) - a frame names its source
    either way: "ep" for the configured series, "file" for anything else."""
    return (entry.get("file") or entry["ep"], int(entry["n"]))


def fetch_frames(frames: list[dict], width: int, height: int) -> dict[tuple[str | int, int], np.ndarray]:
    """Decode every distinct source frame the plan uses (a frame's "blend"
    source included), one decode per run of nearby frames."""
    wanted: dict[str | int, set[int]] = {}
    for f in frames:
        for entry in (f, f.get("blend")):
            if entry:
                src, n = source_key(entry)
                wanted.setdefault(src, set()).add(n)
    files = episode_files() if any(isinstance(src, int) for src in wanted) else {}
    out: dict[tuple[str | int, int], np.ndarray] = {}
    size = width * height * 3
    for src, numbers in wanted.items():
        path = files[src] if isinstance(src, int) else Path(src)
        ordered = sorted(numbers)
        runs: list[list[int]] = [[ordered[0]]]
        for n in ordered[1:]:
            (runs[-1].append(n) if n - runs[-1][-1] <= 48 else runs.append([n]))
        for run in runs:
            first, last = run[0], run[-1]
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{(first - 0.5) / SOURCE_FPS:.4f}", "-i", str(path),
                 "-frames:v", str(last - first + 1), "-an", "-sn", "-fps_mode", "passthrough",
                 "-vf", f"scale={width}:{height}:flags=lanczos,format=rgb24", "-f", "rawvideo", "-"],
                capture_output=True, check=True)
            data = proc.stdout
            for n in run:
                k = n - first
                if (k + 1) * size <= len(data):
                    out[(src, n)] = np.frombuffer(data[k * size:(k + 1) * size], np.uint8).reshape(height, width, 3)
    return out


def zoom(img: Image.Image, scale: float, center: tuple[float, float]) -> Image.Image:
    w, h = img.size
    cw, ch = w / scale, h / scale
    cx = min(max(center[0] * w, cw / 2), w - cw / 2)
    cy = min(max(center[1] * h, ch / 2), h - ch / 2)
    return img.resize((w, h), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def zoom_blur(img: Image.Image, strength: float, steps: int = 14) -> np.ndarray:
    """Radial blur: the average of the frame zoomed progressively about its centre."""
    acc = np.zeros((img.size[1], img.size[0], 3), np.float32)
    for i in range(steps):
        acc += np.asarray(zoom(img, 1.0 + strength * i / (steps - 1), (0.5, 0.5)), np.float32)
    return acc / steps


def white_burst(img: Image.Image) -> np.ndarray:
    """A flash of radial speed lines: a hard zoom blur, desaturated and pushed to white."""
    blurred = zoom_blur(img, 0.9, steps=18).mean(axis=2, keepdims=True)
    lines = np.clip((blurred - blurred.mean()) * 2.2, -255, 255)
    return np.clip(205 + lines, 0, 255).repeat(3, axis=2)


def rgb_split(frame: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return frame
    out = frame.copy()
    out[:, px:, 0] = frame[:, :-px, 0]
    out[:, :-px, 2] = frame[:, px:, 2]
    return out


def compose_one(entry: dict, source: np.ndarray) -> np.ndarray:
    img = Image.fromarray(source)
    if entry.get("fx") == "zoom_blur":
        if entry.get("punch", 1.0) != 1.0:
            img = zoom(img, entry["punch"], tuple(entry.get("center", (0.5, 0.5))))
        return zoom_blur(img, entry.get("strength", 0.25)).astype(np.uint8)
    if entry.get("fx") == "white_burst":
        return white_burst(img).astype(np.uint8)
    if entry.get("punch", 1.0) != 1.0 or tuple(entry.get("center", (0.5, 0.5))) != (0.5, 0.5):
        img = zoom(img, entry.get("punch", 1.0), tuple(entry.get("center", (0.5, 0.5))))
    frame = np.asarray(img)
    if entry.get("dblur"):
        frame = directional_blur(frame, entry["dblur"])
    return rgb_split(frame, int(entry.get("rgb", 0)))


def directional_blur(frame: np.ndarray, vector: list[float], steps: int = 9) -> np.ndarray:
    """Motion blur along (dx, dy) pixels - a whip pan's smear."""
    dx, dy = vector
    if abs(dx) < 1 and abs(dy) < 1:
        return frame
    acc = np.zeros(frame.shape, np.float32)
    for i in range(steps):
        k = i / (steps - 1) - 0.5
        acc += np.roll(frame, (round(dy * k), round(dx * k)), axis=(0, 1))
    return (acc / steps).astype(np.uint8)


def compose(entry: dict, sources: dict) -> np.ndarray:
    """One output frame: the source with its zoom/effect, then (in order) a
    dissolve toward "blend" at "blend.alpha", a white "flash" and a black
    "dim", each 0-1."""
    frame = compose_one(entry, sources[source_key(entry)])
    blend = entry.get("blend")
    if blend:
        other = compose_one(blend, sources[source_key(blend)]).astype(np.float32)
        a = float(blend["alpha"])
        frame = (frame.astype(np.float32) * (1 - a) + other * a).astype(np.uint8)
    if entry.get("flash"):
        a = float(entry["flash"])
        colour = np.array(entry.get("flash_color", [255, 255, 255]), np.float32)
        frame = (frame.astype(np.float32) * (1 - a) + colour * a).astype(np.uint8)
    if entry.get("dim"):
        frame = (frame.astype(np.float32) * (1 - float(entry["dim"]))).astype(np.uint8)
    return frame


def look_filter(look: dict | None, width: int, height: int):
    """The plan-wide look: contrast and saturation about mid-grey, a "lift"
    (added brightness, for footage that is dark to begin with), a per-channel
    "tint" and a vignette. Returns frame -> frame (identity without a look)."""
    if not look:
        return lambda frame: frame
    contrast, saturation = float(look.get("contrast", 1.0)), float(look.get("saturation", 1.0))
    tint = np.array(look.get("tint", [1.0, 1.0, 1.0]), np.float32)
    lift = float(look.get("lift", 0.0))
    ys = (np.arange(height) - height / 2) / (height / 2)
    xs = (np.arange(width) - width / 2) / (width / 2)
    r = np.sqrt(xs[None, :] ** 2 * (width / height) ** 2 / 2.2 + ys[:, None] ** 2 / 1.6)
    vignette = (1.0 - float(look.get("vignette", 0.0)) * np.clip(r - 0.35, 0, 1) ** 1.5)[..., None].astype(np.float32)

    def apply(frame: np.ndarray) -> np.ndarray:
        f = frame.astype(np.float32)
        grey = f.mean(axis=2, keepdims=True)
        f = grey + (f - grey) * saturation
        f = (f - 128.0) * contrast + 128.0 + lift
        return np.clip(f * tint * vignette, 0, 255).astype(np.uint8)

    return apply


def apply_grade(frame: np.ndarray, grade: dict) -> np.ndarray:
    gain = np.array(grade["gain"], np.float32)
    offset = np.array(grade["offset"], np.float32)
    return np.clip(frame.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)


def caption_layer(spec: dict, width: int, height: int) -> Image.Image:
    font_path = spec.get("font", "LiberationSans-Regular.ttf")
    if not Path(font_path).is_file():
        font_path = str(config.find_font(font_path, "LiberationSans-Regular.ttf", "Arial.ttf", "DejaVuSans.ttf"))
    font = ImageFont.truetype(font_path, spec["size"])
    widths = [font.getlength(ch) for ch in spec["text"]]
    # "width" asks for the whole line at that many pixels, by letter spacing.
    spacing = spec.get("spacing")
    if spacing is None:
        spacing = max(0.0, (spec["width"] - sum(widths)) / (len(widths) - 1)) if "width" in spec else 0.0
    total = sum(widths) + spacing * (len(widths) - 1)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x = (width - total) / 2
    y = spec["y"] * height
    for ch, w in zip(spec["text"], widths, strict=True):
        draw.text((x, y), ch, font=font, fill=(255, 255, 255, 255), anchor="ls")
        x += w + spacing
    # A soft dark halo, so the caption holds over the logo's glow.
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(4)).point(lambda a: a * 0.6))
    return Image.alpha_composite(shadow, layer)


def render(plan: dict, out: Path) -> Path:
    width, height, fps = plan["width"], plan["height"], plan["fps"]
    frames = plan["frames"]
    print(f"Decoding source frames for {len(frames)} output frames...", flush=True)
    sources = fetch_frames(frames, width, height)
    look = look_filter(plan.get("look"), width, height)
    caption = plan.get("caption")
    layer = caption_layer(caption, width, height) if caption else None

    audio = plan["audio"]
    delay_ms = int(round(audio.get("delay", 0.0) * 1000))
    seconds = plan["seconds"]
    fade = audio.get("fade_out", 0.0)
    afilter = f"adelay={delay_ms}|{delay_ms},atrim=0:{seconds},asetpts=PTS-STARTPTS"
    if fade:
        afilter += f",afade=t=out:st={seconds - fade:.3f}:d={fade}"
    if audio.get("fade_in"):
        afilter += f",afade=t=in:st=0:d={float(audio['fade_in']):.3f}"
    encoder = choose_h264_encoder("auto")
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
         "-r", str(fps), "-i", "-", "-ss", f"{float(audio.get('start', 0.0)):.3f}", "-i", audio["file"],
         "-filter_complex", f"[1:a]{afilter}[a]",
         "-map", "0:v", "-map", "[a]", *h264_encoder_args(encoder, "p7", 16), "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "320k", "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    for i, entry in enumerate(frames):
        frame = look(compose(entry, sources))
        for grade in plan.get("grade", []):
            if i >= grade["from"]:
                frame = apply_grade(frame, grade)
        if layer is not None and i >= caption["from"]:
            alpha = min(1.0, (i - caption["from"] + 1) / max(1, caption.get("fade", 1)))
            img = Image.fromarray(frame).convert("RGBA")
            faded = layer.copy()
            faded.putalpha(layer.getchannel("A").point(lambda a, k=alpha: a * k))
            frame = np.asarray(Image.alpha_composite(img, faded).convert("RGB"))
        proc.stdin.write(np.ascontiguousarray(frame, np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed to encode the remake")
    print(f"Wrote {out}  ({probe_duration(out):.2f}s)", flush=True)
    return out


def build_plan(spec: dict, reference_map: list[dict], song: Path) -> dict:
    """A render plan from a spec and a reference map.

    Every frame starts as the map's match. Then, in order, each override
    replaces its "frames" (a list, or [first, last] as {"from": a, "to": b}):
      - "like": i        -> the source frame of map frame i
      - "anchor": i, "step": s -> map frame i's episode, stepping back s source
                            frames per output frame (for frames the map could
                            not match because they are zoomed or covered)
    Any other key is copied onto each frame: a list as long as "frames" is
    per frame ("punch", "rgb", "center", "fx", "strength"), anything else is
    the same for all. "require" entries check the map before anything is
    built, so a spec never renders against a map it was not written for.
    """
    frames = [{"ep": f["ep"], "n": f["n"]} for f in reference_map]
    if len(frames) < round(spec["seconds"] * spec["fps"]):
        raise SystemExit(f"the reference map has {len(frames)} frames; the spec needs "
                         f"{round(spec['seconds'] * spec['fps'])}")
    for need in spec.get("require", []):
        got = reference_map[need["frame"]]
        if got["corr"] < need.get("min_corr", 0.99) or ("ep" in need and got["ep"] != need["ep"]):
            raise SystemExit(f"reference map frame {need['frame']} is {got}, the spec expects {need} - "
                             "was the map made from the same video?")
    special = {"frames", "from", "to", "like", "anchor", "step", "about"}
    for override in spec.get("overrides", []):
        targets = override.get("frames") or list(range(override["from"], override["to"] + 1))
        for k, i in enumerate(targets):
            if "like" in override:
                base = reference_map[override["like"]]
                entry = {"ep": base["ep"], "n": base["n"]}
            elif "anchor" in override:
                base = reference_map[override["anchor"]]
                entry = {"ep": base["ep"], "n": base["n"] - round((override["anchor"] - i) * override["step"])}
            else:
                entry = dict(frames[i])
            for key, value in override.items():
                if key in special:
                    continue
                per_frame = isinstance(value, list) and len(value) == len(targets) and key != "center" \
                    or (key == "center" and value and isinstance(value[0], list))
                picked = value[k] if per_frame else value
                if picked is not None:
                    entry[key] = picked
            frames[i] = entry
    frames = frames[: round(spec["seconds"] * spec["fps"])]
    return {
        "fps": spec["fps"], "width": spec["width"], "height": spec["height"], "seconds": spec["seconds"],
        "frames": frames, "grade": [{k: v for k, v in g.items() if k != "about"} for g in spec.get("grade", [])],
        "caption": spec.get("caption"),
        "audio": {"file": str(song), **spec.get("audio", {})},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--spec", type=Path, help="a remake spec (amv/intro/remakes/*.json)")
    source.add_argument("--plan", type=Path, help="render this plan as it stands")
    parser.add_argument("--map", type=Path, default=paths.INTRO / "reference_map.json",
                        help="the reference map a spec is built on")
    parser.add_argument("--song", type=Path, default=None, help="default: song from config.json")
    parser.add_argument("--out", type=Path, default=paths.INTRO / "remake.mp4")
    args = parser.parse_args()

    if args.spec:
        reference_map = json.loads(args.map.read_text(encoding="utf-8"))["frames"]
        song = (args.song or config.load().require_song()).resolve()
        plan = build_plan(json.loads(args.spec.read_text(encoding="utf-8")), reference_map, song)
        plan_path = paths.INTRO / "remake_plan.json"
        plan_path.write_text(json.dumps(plan, indent=0), encoding="utf-8")
        print(f"Wrote {plan_path}", flush=True)
    else:
        plan = json.loads((args.plan or paths.INTRO / "remake_plan.json").read_text(encoding="utf-8"))
    render(plan, args.out)


if __name__ == "__main__":
    main()
