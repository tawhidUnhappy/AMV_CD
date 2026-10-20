"""The camera effects: (f float32 HxWx3, frame uint8, settings, n) -> f."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageFilter


def shake(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    if a <= 0:
        return f
    rng = np.random.default_rng((n // max(1, int(o.get("hold", 2)))) * 104729 + int(o.get("seed", 0)))
    h, w = f.shape[:2]
    dx, dy = rng.uniform(-1, 1, 2) * float(o["px"]) * a
    angle = float(rng.uniform(-1, 1) * float(o["rot"]) * a)
    scale = 1 + float(o.get("zoom", 0.0)) * a
    pad = int(abs(dx) + abs(dy) + max(w, h) * math.sin(math.radians(abs(angle))) * 0.6 + 8)
    big = np.pad(np.clip(f, 0, 255).astype(np.uint8), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    img = Image.fromarray(big)
    if abs(angle) > 0.01:
        img = img.rotate(angle, resample=Image.BILINEAR)
    cw, ch = w / scale, h / scale
    cx, cy = pad + w / 2 + dx, pad + h / 2 + dy
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return np.asarray(img.resize((w, h), Image.BILINEAR, box=box), np.float32)


def blur(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    r = float(o["radius"]) * float(o["amount"])
    if r < 0.5:
        return f
    img = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r)), np.float32)


def exposure(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    if a <= 0:
        return f
    out = f * (2 ** (float(o["stops"]) * a))
    hi = np.clip(out - 200, 0, None)
    small = Image.fromarray(np.clip(hi, 0, 255).astype(np.uint8)).resize((f.shape[1] // 4, f.shape[0] // 4))
    bloom = np.asarray(small.filter(ImageFilter.GaussianBlur(12)).resize((f.shape[1], f.shape[0]), Image.BILINEAR),
                       np.float32)
    return np.clip(out + bloom * float(o["bloom"]) * a, 0, 255)
