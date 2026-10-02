"""The built-in picture effects: (f float32 HxWx3, frame uint8, settings, n) -> f."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def outline(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    # Strong edges only - anime line art and silhouettes, not texture: the
    # edges of a lightly smoothed frame, thickened, softened, then boosted
    # back (blurring a thin line mask alone diluted it to near-invisible).
    grey = Image.fromarray(frame).convert("L").filter(ImageFilter.GaussianBlur(1.2))
    edges = np.asarray(grey.filter(ImageFilter.FIND_EDGES), np.float32)
    mask = np.clip((edges - 14.0) / 26.0, 0, 1)
    mask[:3], mask[-3:], mask[:, :3], mask[:, -3:] = 0, 0, 0, 0  # the image border is not an edge
    m = Image.fromarray((mask * 255).astype(np.uint8))
    w = max(1, int(o["width"]))
    m = m.filter(ImageFilter.MaxFilter(2 * (w // 2) + 1)).filter(ImageFilter.GaussianBlur(w * 0.8))
    a = (np.clip(np.asarray(m, np.float32) / 255.0 * 2.2, 0, 1) * float(o["strength"]))[..., None]
    colour = np.array(o["color"], np.float32)
    return f * (1 - a) + colour * a  # a soft line over the edge


def glow(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    img = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
    luma = np.asarray(img.convert("L"), np.float32) / 255.0
    bright = np.asarray(img, np.float32) * np.clip((luma - 0.62) / 0.38, 0, 1)[..., None]
    bloom = np.asarray(Image.fromarray(bright.astype(np.uint8)).filter(ImageFilter.GaussianBlur(14)), np.float32)
    return 255 - (255 - f) * (255 - bloom * float(o["strength"])) / 255  # screen blend


def grain(f: np.ndarray, frame: np.ndarray, o: dict, n: int) -> np.ndarray:
    rng = np.random.default_rng(n)
    return f + rng.normal(0, float(o["amount"]), frame.shape[:2]).astype(np.float32)[..., None]
