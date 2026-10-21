"""Procedural lyric-video backgrounds - the 7clouds / lyrics-channel family:
twilight skies over hazy mountains, pastel cloud decks, puffy cumulus, a sunset
sea, starry nights, aurora. Varied but curated: each seed picks a scene x mood
pair that suits (sky.PAIRS), jitters the palette a little and varies the
composition inside tasteful ranges. The look rules are in sky.py.

    ./amv.sh bg-gen --count 12 --sheet               # 12 curated random skies + a sheet
    ./amv.sh bg-gen --scene clouds --mood cotton_candy --count 4
    ./amv.sh bg-gen --scene all --count 2 --sheet    # every scene, its moods in turn
    ./amv.sh bg-gen --scene ranges --mood dusk       # the reference look (Headlights background)
    -> workspace/output/backgrounds/<scene>_<mood>_<seed>.png

Scenes: ranges, clouds, cumulus, sea, night, aurora. Moods: dusk, cotton_candy,
golden_hour, fire_sunset, blue_hour, dawn, day_blue, mint, night."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from amv.core.config import load
from amv.lyric_video import sky


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


def _ranges(p: list[np.ndarray], rng, w: int, h: int) -> np.ndarray:
    """The mountain scene (tuned against the reference) on sRGB colours."""
    tl, tr, hl, hr, br, glow, haze, near_top, near_bot = p
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
    return img


SCENE_WEIGHTS = {"clouds": 3, "ranges": 2.5, "cumulus": 2, "sea": 1.2, "night": 1, "aurora": 0.8}


def pick(seed: int, scene: str | None, mood_name: str | None) -> tuple[str, str]:
    """A curated (scene, mood) for this seed: scene by weight, mood among the
    ones that suit it."""
    rng = np.random.default_rng(seed * 7919 + 13)
    if not scene:
        names = list(SCENE_WEIGHTS)
        wts = np.array([SCENE_WEIGHTS[n] for n in names], float)
        scene = names[rng.choice(len(names), p=wts / wts.sum())]
    if not mood_name:
        mood_name = sky.PAIRS[scene][rng.integers(len(sky.PAIRS[scene]))]
    return scene, mood_name


def _ground(img, m, x, y, horizon, rng, far: bool = True):
    """Low hills on the horizon: a hazy far line and a darker near one."""
    w = img.shape[1]
    layers = [(0.012, 0.025, 0.35)] if far else []
    layers.append((-0.015, 0.035, 1.0))
    for lift, amp, strength in layers:
        ridge = _ridge(rng, w, horizon - lift, amp, 0.55, cells=4)[None, :]
        cover = np.clip((y - ridge) * img.shape[0] / 1.5 + 0.5, 0, 1)
        shade = sky.smooth(0.0, 0.2, y - ridge)
        col = sky.mix(m["ground_top"], m["ground_bot"], shade)
        col = sky.mix(sky.mix(m["haze"], m["horizon"], 0.5), col, strength)
        img = sky.mix(img, col, cover)
    return img


def generate(scene: str, mood_name: str, seed: int, w: int, h: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    m = sky.mood(mood_name, rng)
    if scene == "ranges":
        keys = ("zenith", "zenith2", "horizon", "horizon2", "low", "glow", "haze", "ground_top", "ground_bot")
        img = _ranges([sky.to_srgb(m[k]) for k in keys], rng, w, h)
        if m.get("stars"):
            img = sky.stars(img, rng, 0.7, 0.8)
        return Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8))
    # soft scenes are computed at up to 1920 wide and upscaled; stars and grain at full size
    w0 = min(w, 1920)
    h0 = int(round(h * w0 / w))
    yy, xx = np.mgrid[0:h0, 0:w0].astype(np.float32)
    x, y = xx / w0, yy / h0
    aspect = w0 / h0
    noise = sky.Noise(rng)
    mirror = rng.random() < 0.4
    if scene == "sea":
        horizon = rng.uniform(0.56, 0.64)
        sun = (rng.uniform(0.25, 0.42), horizon - rng.uniform(0.03, 0.09))
    elif scene in ("night", "aurora"):
        horizon = rng.uniform(0.84, 0.93)
        sun = (rng.uniform(0.2, 0.4), rng.uniform(0.18, 0.35))    # the moon
    else:
        horizon = rng.uniform(0.8, 0.93)
        sun = (rng.uniform(0.12, 0.38), horizon - rng.uniform(0.02, 0.1))
    img = sky.sky_gradient(m, x, y, horizon, sun, aspect)
    if scene == "clouds":
        img = sky.cloud_deck(img, m, x, y, horizon, sun, aspect, rng, noise,
                             cover=rng.uniform(0.0, 0.3), soft=rng.uniform(0.35, 0.6))
        img = _ground(img, m, x, y, horizon, rng)
    elif scene == "cumulus":
        img = sky.cloud_deck(img, m, x, y, horizon, sun, aspect, rng, noise, cover=0.45, soft=0.5, alpha=0.5)
        img = sky.cumulus(img, m, x, y, horizon, sun, aspect, rng, noise)
        img = _ground(img, m, x, y, horizon, rng)
    elif scene == "sea":
        img = sky.cloud_deck(img, m, x, y, horizon, sun, aspect, rng, noise,
                             cover=rng.uniform(0.2, 0.45), soft=0.5)
        img = sky.sun_disc(img, m, x, y, sun, aspect, 0.022)
        img = sky.sea(img, m, x, y, horizon, sun, aspect, rng, noise)
    elif scene in ("night", "aurora"):
        img = sky.milky_way(img, x, y, horizon, aspect, rng, noise)
        if scene == "aurora":
            img = sky.aurora(img, x, y, horizon, aspect, rng, noise)
        elif rng.random() < 0.6:
            img = sky.sun_disc(img, m, x, y, sun, aspect, 0.018, 0.9)
        if rng.random() < 0.5:
            img = sky.cloud_deck(img, m, x, y, horizon, sun, aspect, rng, noise, cover=0.35, soft=0.5, alpha=0.6)
        img = _ground(img, m, x, y, horizon, rng)
    else:
        raise SystemExit(f"unknown scene {scene}: {', '.join(sky.PAIRS)}")
    out = sky.to_srgb(img)
    if mirror:
        out = out[:, ::-1]
    if (w0, h0) != (w, h):
        out = np.stack([np.asarray(Image.fromarray(out[..., c].astype(np.float32), "F").resize((w, h), Image.BICUBIC))
                        for c in range(3)], -1)
    if m.get("stars"):
        out = sky.stars(out, rng, horizon if not mirror else horizon, 1.0)
    out = out + rng.normal(0, 1.4, out.shape).astype(np.float32)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default=None, help=f"{', '.join(sky.PAIRS)}, all, or leave out for a curated mix")
    ap.add_argument("--mood", "--palette", dest="mood", default=None,
                    help=f"{', '.join(sky.MOODS)} (leave out: one that suits the scene)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--count", type=int, default=1, help="this many seeds from --seed on")
    ap.add_argument("--size", default="3840x2160")
    ap.add_argument("--sheet", action="store_true", help="also a contact sheet of what was made")
    ap.add_argument("-o", "--out", type=Path, default=None, help="output folder")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.lower().split("x"))
    out = args.out or load().workspace / "output" / "backgrounds"
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    scenes = list(sky.PAIRS) if args.scene == "all" else [args.scene]
    for scene in scenes:
        for i, seed in enumerate(range(args.seed, args.seed + args.count)):
            mood_name = args.mood
            if args.scene == "all" and not mood_name:
                mood_name = sky.PAIRS[scene][i % len(sky.PAIRS[scene])]
            jobs.append((seed, *pick(seed, scene, mood_name)))
    made = []
    for seed, scene, mood_name in jobs:
        if mood_name not in sky.PAIRS[scene]:
            print(f"  note: {mood_name} is not a usual mood for {scene}")
        path = out / f"{scene}_{mood_name}_{seed}.png"
        generate(scene, mood_name, seed, w, h).save(path)
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
