"""The glitch effects: (f float32 HxWx3, frame uint8, settings, n) -> f.
"amount" 0-1 scales each one; 0 returns f untouched."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _rng(o: dict, n: int, salt: int) -> np.random.Generator:
    return np.random.default_rng((n // max(1, int(o.get("hold", 1)))) * 7919 + salt + int(o.get("seed", 0)))


def rgb_split(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    px = int(round(float(o["px"]) * float(o["amount"])))
    if px <= 0:
        return f
    out = f.copy()
    out[:, px:, 0] = f[:, :-px, 0]
    out[:, :-px, 2] = f[:, px:, 2]
    return out


def slice(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:  # noqa: A001 - the effect's name
    a = float(o["amount"])
    if a <= 0:
        return f
    rng = _rng(o, n, 1)
    h, w = f.shape[:2]
    out = f.copy()
    count = max(1, int(round(int(o["bands"]) * (0.4 + 0.6 * a))))
    for _ in range(count):
        y0 = int(rng.integers(0, h))
        bh = int(rng.integers(max(2, h // 120), max(4, h // 14)))
        shift = int(rng.normal(0, float(o["shift"]) * a))
        if shift:
            band = f[y0:y0 + bh]
            out[y0:y0 + bh] = np.roll(band, shift, axis=1)
            if rng.random() < 0.35:  # some torn bands also lose a channel
                out[y0:y0 + bh, :, int(rng.integers(0, 3))] *= 0.25
    return out


def blocks(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    if a <= 0:
        return f
    rng = _rng(o, n, 2)
    h, w = f.shape[:2]
    s = int(o["size"])
    out = f.copy()
    for _ in range(int(a * (h // s) * (w // s) * 0.18)):
        bw, bh = s * int(rng.integers(1, 4)), s * int(rng.integers(1, 3))
        x, y = int(rng.integers(0, max(1, w - bw))), int(rng.integers(0, max(1, h - bh)))
        sx = int(np.clip(x + rng.integers(-3, 4) * s, 0, w - bw))
        sy = int(np.clip(y + rng.integers(-2, 3) * s, 0, h - bh))
        block = f[sy:sy + bh, sx:sx + bw]
        if rng.random() < 0.5:
            block = block[..., rng.permutation(3)]
        if rng.random() < 0.25:  # a flat smeared block, as when a codec loses its data
            block = np.broadcast_to(block.mean(axis=(0, 1), keepdims=True), block.shape)
        out[y:y + bh, x:x + bw] = block
    return out


def chroma(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    k = float(o["scale"]) * float(o["amount"])
    if k <= 1e-4:
        return f
    h, w = f.shape[:2]
    out = f.copy()
    for ch, scale in ((0, 1 + k), (2, 1 - k * 0.6)):
        cw, chh = w / scale, h / scale
        m = int(np.ceil(max(cw - w, chh - h, 0) / 2)) + 2  # shrinking needs room past the edge
        plane = np.pad(np.clip(f[..., ch], 0, 255).astype(np.uint8), m, mode="edge") if scale < 1 else \
            np.clip(f[..., ch], 0, 255).astype(np.uint8)
        img = Image.fromarray(plane)
        o = m if scale < 1 else 0
        box = (o + (w - cw) / 2, o + (h - chh) / 2, o + (w + cw) / 2, o + (h + chh) / 2)
        out[..., ch] = np.asarray(img.resize((w, h), Image.BILINEAR, box=box), np.float32)
    return out


def pixelate(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    s = int(round(float(o["size"]) * float(o["amount"])))
    if s < 2:
        return f
    h, w = f.shape[:2]
    img = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
    return np.asarray(img.resize((max(1, w // s), max(1, h // s)), Image.BILINEAR).resize((w, h), Image.NEAREST),
                      np.float32)


def posterize(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    if a <= 0:
        return f
    levels = max(2.0, 2.0 + (1 - a) * 30 + int(o["levels"]) - 2)
    step = 255.0 / (levels - 1)
    return np.round(f / step) * step


def invert(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    return f if a <= 0 else f * (1 - a) + (255.0 - f) * a


def scanlines(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    a = float(o["amount"])
    if a <= 0:
        return f
    h = f.shape[0]
    period = max(2, int(o["period"]))
    y = np.arange(h)
    lines = np.where(y % period < period // 2, 1.0 - 0.28 * a, 1.0)
    bar_y = (n * 9) % (h + 300) - 150  # a soft bright bar rolling down
    bar = 1.0 + 0.10 * a * np.exp(-((y - bar_y) / 70.0) ** 2)
    return f * (lines * bar)[:, None, None]
