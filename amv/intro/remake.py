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

    uv run python -m amv.intro.remake [--plan PATH] [--out PATH]
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


def fetch_frames(frames: list[dict], width: int, height: int) -> dict[tuple[int, int], np.ndarray]:
    """Decode every distinct source frame the plan uses, one decode per run
    of nearby frames, keyed by (episode, frame number on the source clock)."""
    files = episode_files()
    wanted: dict[int, set[int]] = {}
    for f in frames:
        wanted.setdefault(f["ep"], set()).add(int(f["n"]))
    out: dict[tuple[int, int], np.ndarray] = {}
    size = width * height * 3
    for ep, numbers in wanted.items():
        ordered = sorted(numbers)
        runs: list[list[int]] = [[ordered[0]]]
        for n in ordered[1:]:
            (runs[-1].append(n) if n - runs[-1][-1] <= 48 else runs.append([n]))
        for run in runs:
            first, last = run[0], run[-1]
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{(first - 0.5) / SOURCE_FPS:.4f}", "-i", str(files[ep]),
                 "-frames:v", str(last - first + 1), "-an", "-sn", "-fps_mode", "passthrough",
                 "-vf", f"scale={width}:{height}:flags=lanczos,format=rgb24", "-f", "rawvideo", "-"],
                capture_output=True, check=True)
            data = proc.stdout
            for n in run:
                k = n - first
                if (k + 1) * size <= len(data):
                    out[(ep, n)] = np.frombuffer(data[k * size:(k + 1) * size], np.uint8).reshape(height, width, 3)
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


def compose(entry: dict, source: np.ndarray) -> np.ndarray:
    img = Image.fromarray(source)
    if entry.get("fx") == "zoom_blur":
        return zoom_blur(img, entry.get("strength", 0.25)).astype(np.uint8)
    if entry.get("fx") == "white_burst":
        return white_burst(img).astype(np.uint8)
    if entry.get("punch", 1.0) != 1.0:
        img = zoom(img, entry["punch"], tuple(entry.get("center", (0.5, 0.5))))
    return rgb_split(np.asarray(img), int(entry.get("rgb", 0)))


def apply_grade(frame: np.ndarray, grade: dict) -> np.ndarray:
    gain = np.array(grade["gain"], np.float32)
    offset = np.array(grade["offset"], np.float32)
    return np.clip(frame.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)


def caption_layer(spec: dict, width: int, height: int) -> Image.Image:
    font_path = spec.get("font") or str(config.find_font("LiberationSans-Regular.ttf", "Arial.ttf", "DejaVuSans.ttf"))
    font = ImageFont.truetype(font_path, spec["size"])
    spacing = spec.get("spacing", 0)
    widths = [font.getlength(ch) for ch in spec["text"]]
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
    caption = plan.get("caption")
    layer = caption_layer(caption, width, height) if caption else None

    audio = plan["audio"]
    delay_ms = int(round(audio.get("delay", 0.0) * 1000))
    seconds = plan["seconds"]
    fade = audio.get("fade_out", 0.0)
    afilter = f"adelay={delay_ms}|{delay_ms},atrim=0:{seconds},asetpts=PTS-STARTPTS"
    if fade:
        afilter += f",afade=t=out:st={seconds - fade:.3f}:d={fade}"
    encoder = choose_h264_encoder("auto")
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
         "-r", str(fps), "-i", "-", "-i", audio["file"], "-filter_complex", f"[1:a]{afilter}[a]",
         "-map", "0:v", "-map", "[a]", *h264_encoder_args(encoder, "p7", 16), "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "320k", "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    for i, entry in enumerate(frames):
        source = sources[(entry["ep"], int(entry["n"]))]
        frame = compose(entry, source)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", type=Path, default=paths.INTRO / "remake_plan.json")
    parser.add_argument("--out", type=Path, default=paths.INTRO / "remake.mp4")
    args = parser.parse_args()
    render(json.loads(args.plan.read_text(encoding="utf-8")), args.out)


if __name__ == "__main__":
    main()
