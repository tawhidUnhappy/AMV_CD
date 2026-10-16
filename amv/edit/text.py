"""Kinetic text for an edit: a word or line that slams in (scale pop), holds,
and glitches - torn bands and split channels on the text alone, so the words
stay readable while the picture under them is wrecked.

A spec "text" entry: {"text", "at", "until", "font", "size", "y" (0-1 of the
height, the line's centre), "color", "stroke", "glitch" 0-1, "pop" (start scale),
"tracking" (px between letters), "flicker" (frames of on/off at the start)}."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from amv.core import config


def font_path(name: str) -> str:
    """A font file: a path, a file in workspace/assets/fonts/, or a system font name."""
    if Path(name).is_file():
        return name
    local = config.load().workspace / "assets" / "fonts"
    for cand in sorted(local.glob(f"{name}*")) if local.is_dir() else []:
        return str(cand)
    found = config.find_font(name, f"{name}.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf")
    if found is None:
        raise SystemExit(f"font {name!r} not found (put it in workspace/assets/fonts/)")
    return str(found)


@lru_cache(maxsize=32)
def _layer(text: str, font: str, size: int, color: tuple, stroke: int, tracking: int, width: int) -> Image.Image:
    """The text, centred, on a transparent canvas as wide as the frame, with a
    dark glow behind it so it reads over any footage."""
    f = ImageFont.truetype(font_path(font), size)
    lines = text.split("\n")
    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 0.92)
    h = line_h * len(lines) + 2 * size // 3
    layer = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for k, line in enumerate(lines):
        widths = [f.getlength(ch) for ch in line]
        total = sum(widths) + tracking * (len(line) - 1)
        x, y = (width - total) / 2, size // 3 + k * line_h
        for ch, w in zip(line, widths, strict=True):
            d.text((x, y), ch, font=f, fill=(*color, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            x += w + tracking
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    shadow.putalpha(layer.getchannel("A").filter(ImageFilter.GaussianBlur(size // 10)).point(lambda a: a * 0.7))
    return Image.alpha_composite(shadow, layer)


def draw(frame: np.ndarray, entry: dict, t: float, n: int, fps: float) -> np.ndarray:
    """`frame` (uint8 HxWx3) with the text entry as it is at output time t."""
    h, w = frame.shape[:2]
    u = (t - entry["at"]) * fps  # frames since it appeared
    flick = int(entry.get("flicker", 0))
    if flick and u < flick and (int(u) // 2) % 2 == 1:
        return frame
    layer = _layer(entry["text"], entry.get("font", "Anton"), int(entry.get("size", 160)),
                   tuple(entry.get("color", [255, 255, 255])), int(entry.get("stroke", 0)),
                   int(entry.get("tracking", 4)), w)
    pop = float(entry.get("pop", 1.25))
    k = min(1.0, u / 5.0)
    scale = pop + (1 - pop) * (1 - (1 - k) ** 3)
    left = entry["until"] - t
    if left * fps < 3:  # out: squash flat over the last 3 frames, like a CRT switching off
        sy = max(0.05, left * fps / 3)
    else:
        sy = 1.0
    if abs(scale - 1) > 1e-3 or sy < 1:
        layer = layer.resize((max(1, round(layer.width * scale)), max(1, round(layer.height * scale * sy))),
                             Image.BICUBIC)
    rgba = np.asarray(layer, np.float32)
    g = float(entry.get("glitch", 0.0)) * (1.0 if u < 8 else 0.35)
    if g > 0:
        from amv.plugins.glitch_fx.effects import rgb_split, slice as tear

        rng = np.random.default_rng(n // 2 + 11)
        if rng.random() < 0.6 + 0.4 * g:
            rgba = tear(rgba, None, {"amount": g, "bands": 6, "shift": 60, "hold": 2}, n)
        rgb = rgb_split(rgba[..., :3], None, {"amount": g, "px": 14}, n)
        alpha = np.maximum(rgba[..., 3], rgb_split(rgba[..., 3:].repeat(3, 2), None,
                                                    {"amount": g, "px": 14}, n).max(axis=2))
        rgba = np.concatenate([rgb, alpha[..., None]], axis=2)
    lh, lw = rgba.shape[:2]
    cy = int(entry.get("y", 0.5) * h)
    x0, y0 = (w - lw) // 2, cy - lh // 2
    xs, ys = max(0, x0), max(0, y0)
    xe, ye = min(w, x0 + lw), min(h, y0 + lh)
    if xe <= xs or ye <= ys:
        return frame
    part = rgba[ys - y0:ye - y0, xs - x0:xe - x0]
    a = part[..., 3:] / 255.0
    out = frame.astype(np.float32)
    out[ys:ye, xs:xe] = out[ys:ye, xs:xe] * (1 - a) + part[..., :3] * a
    return np.clip(out, 0, 255).astype(np.uint8)
