"""Procedural lyric-video backgrounds: a twilight sky over hazy mountain
ranges (the lyrics-channel look), any size, any seed, a few palettes.

    ./amv.sh bg-gen                                  # dusk palette, seed 1, 3840x2160
    ./amv.sh bg-gen --palette sunset --seed 7 --count 4
    ./amv.sh bg-gen --palette all --count 3 --sheet  # every palette, a contact sheet
    -> workspace/output/backgrounds/<palette>_<seed>.png

The picture, back to front: a sky gradient (lerped top->horizon->bottom and
left->right), a soft glow on one side, diagonal cloud streaks (stretched
fractal noise), 3-4 mountain ranges from 1-D fractal noise - far ones barely
darker than the sky, with mist pooling in their valleys, the nearest a dark
silhouette rising from one corner - and a fine grain that keeps the
gradients from banding. The "dusk" palette is sampled from the reference
("Headlights (Lyrics)" background)."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from amv.core.config import load


def _hex(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


# top-left, top-right, horizon-left, horizon-right, bottom-right, glow, haze, near ridge (top, bottom)
PALETTES = {
    "dusk": ["b8a2e6", "9397e5", "ffa3f6", "a493e9", "0a8be0", "ffb4f8", "c49ff0", "0a5aa3", "03447f"],
    "sunset": ["7d6fc9", "4f5bb5", "ffb37a", "f07ea8", "5a4bb0", "ffd08a", "e892b0", "3b2c6e", "1f1846"],
    "night": ["1b1f4a", "0f1238", "5a3f99", "2f3a8a", "0b1e5c", "9b6bd6", "4a4590", "0b0f2e", "05071a"],
    "dawn": ["a9c6f0", "8fb5ec", "ffd2b8", "f6b3c8", "6aa8e8", "ffe4c4", "e6c1d8", "4d6fa8", "2d4a80"],
    "mint": ["9fd8e6", "86b9ea", "f7c6e8", "b7a8ee", "3f8fdc", "ffd6f0", "b9cdee", "2a5e9a", "173f73"],
}


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _noise2(rng, h: int, w: int, cells: tuple[int, int], octaves: int = 4) -> np.ndarray:
    """Fractal value noise, roughly in [-1, 1], at h x w; cells = (rows, cols) of the coarsest octave."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    ry, rx = cells
    for _ in range(octaves):
        g = rng.standard_normal((ry + 3, rx + 3)).astype(np.float32)
        up = ndimage.zoom(g, (h / (ry + 1), w / (rx + 1)), order=3)[:h, :w]
        if up.shape != (h, w):
            up = np.pad(up, ((0, h - up.shape[0]), (0, w - up.shape[1])), mode="edge")
        out += amp * up
        total += amp
        amp *= 0.5
        ry, rx = ry * 2, rx * 2
    return out / total


def _ridge(rng, n: int, base: float, amp: float, rough: float, cells: int = 5) -> np.ndarray:
    """A mountain skyline (fraction of height from the top) at n columns: smooth
    fractal 1-D noise (rounded hills, like the reference - folding |noise| into
    crests made flat-topped mesas)."""
    y = np.zeros(n, np.float32)
    a, total, c = 1.0, 0.0, cells
    for _ in range(6):
        g = rng.standard_normal(c + 3).astype(np.float32)
        up = np.interp(np.linspace(0, c + 1, n), np.arange(c + 3), g)
        up = ndimage.gaussian_filter1d(up, max(1.0, n / (c * 3)))
        y += a * up
        total += a
        a *= rough
        c *= 2
    y /= total
    return base - amp * y


def generate(palette: str, seed: int, w: int, h: int) -> Image.Image:
    p = [_hex(c) for c in PALETTES[palette]]
    tl, tr, hl, hr, br, glow, haze, near_top, near_bot = p
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = xx / w, yy / h
    aspect = w / h

    # sky: top row and horizon row lerped across x, then down
    top = tl[None, None] * (1 - x[..., None]) + tr[None, None] * x[..., None]
    hor_x = _smooth(0.0, 1.0, x)[..., None]
    horizon = hl[None, None] * (1 - hor_x) + hr[None, None] * hor_x
    k = _smooth(0.05, 0.68, y)[..., None]
    sky = top * (1 - k) + horizon * k
    low = _smooth(0.62, 1.05, y)[..., None] * _smooth(0.25, 1.0, x)[..., None]
    sky = sky * (1 - low) + br[None, None] * low
    # the glow on one side, just above the horizon
    # built with the glow and the near range on the left; ~1 in 3 is mirrored at the end
    # (mirroring only the glow left the sky gradient pink on the wrong side)
    mirror = rng.random() < 0.3
    gx = 0.0
    d = np.sqrt(((x - gx) * aspect) ** 2 + ((y - 0.6) * 1.6) ** 2)
    g = np.exp(-(d / 0.75) ** 2)[..., None] * 0.55
    sky = sky * (1 - g) + glow[None, None] * g

    # cloud streaks: long, thin, rising to the right
    sh = y - 0.18 * (x - 0.5)
    streak = _noise2(rng, h // 4, w // 4, (6, 2), 3)
    streak = ndimage.zoom(streak, (h / streak.shape[0], w / streak.shape[1]), order=1)[:h, :w]
    streak = ndimage.map_coordinates(streak, [np.clip(sh * h, 0, h - 1), xx], order=1)
    cloud = (streak * 0.035 * (1 - _smooth(0.5, 0.72, y)))[..., None]
    sky = sky * (1 + cloud) + 255 * np.clip(cloud, 0, None) * 0.15

    img = sky
    # mountain ranges, far to near
    layers = [
        dict(base=0.66, amp=0.07, rough=0.62, alpha=0.10, mist=0.85, blur=3.0, rise=0.07),
        dict(base=0.73, amp=0.07, rough=0.62, alpha=0.18, mist=0.8, blur=2.0, rise=0.06),
    ]
    away = 1 - np.abs(np.linspace(0, 1, w) - gx)  # ranges climb away from the glow
    for L in layers:
        ridge = _ridge(rng, w, L["base"], L["amp"], L["rough"], cells=3) - L["rise"] * away
        ry = ridge[None, :] * h
        edge = 1.2 + L["blur"] * h / 1080
        cover = np.clip((yy - ry) / edge + 0.5, 0, 1)
        # mist measured from a smoothed skyline: following every bump made vertical stripes
        soft = ndimage.gaussian_filter1d(ridge, w / 40)
        depth = _smooth(0.0, 0.10, y - soft[None, :])
        col_a = (img * 0.82 + haze[None, None] * 0.18) * (1 - L["alpha"]) + near_top[None, None] * L["alpha"]
        col = col_a * (1 - (depth * L["mist"])[..., None]) + img * (depth * L["mist"])[..., None]
        img = img * (1 - cover[..., None]) + col * cover[..., None]

    # the near range: a dark silhouette rising from one corner
    t = np.linspace(0, 1, w)
    slope = 0.715 + 0.75 * t
    ridge = _ridge(rng, w, 0.0, 0.035, 0.6, cells=4) + slope
    # a lower, rounded hill in front of it, past a saddle (the reference's second hump)
    cx, peak = rng.uniform(0.33, 0.40), rng.uniform(0.885, 0.91)
    hump = peak + 3.2 * np.abs(t - cx) ** 1.7 + _ridge(rng, w, 0.0, 0.018, 0.62, cells=8)
    ridge = np.minimum(ridge, hump)
    ry = ridge[None, :] * h
    cover = np.clip((yy - ry) / (1.0 + h / 1080) + 0.5, 0, 1)
    shade = _smooth(0.0, 0.35, y - ridge[None, :])[..., None]
    col = near_top[None, None] * (1 - shade) + near_bot[None, None] * shade
    img = img * (1 - cover[..., None]) + col * cover[..., None]

    # grain against banding, then a touch of softness
    img = img + rng.normal(0, 1.4, img.shape).astype(np.float32)
    img = ndimage.gaussian_filter(img, (0.6 * h / 1080, 0.6 * h / 1080, 0))
    if mirror:
        img = img[:, ::-1]
    return Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--palette", default="dusk", help=f"{', '.join(PALETTES)} or all")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--count", type=int, default=1, help="this many seeds from --seed on")
    ap.add_argument("--size", default="3840x2160")
    ap.add_argument("--sheet", action="store_true", help="also a contact sheet of what was made")
    ap.add_argument("-o", "--out", type=Path, default=None, help="output folder")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    out = args.out or load().workspace / "output" / "backgrounds"
    out.mkdir(parents=True, exist_ok=True)
    names = list(PALETTES) if args.palette == "all" else [args.palette]
    made = []
    for name in names:
        for seed in range(args.seed, args.seed + args.count):
            path = out / f"{name}_{seed}.png"
            generate(name, seed, w, h).save(path)
            made.append(path)
            print(path)
    if args.sheet and made:
        tw = 480
        th = int(tw * h / w)
        cols = min(4, len(made))
        sheet = Image.new("RGB", (cols * tw, ((len(made) + cols - 1) // cols) * th))
        for i, path in enumerate(made):
            sheet.paste(Image.open(path).resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
        sheet.save(out / "sheet.jpg", quality=90)
        print(out / "sheet.jpg")


if __name__ == "__main__":
    main()
