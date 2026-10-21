"""Procedural skies for lyric-video backgrounds - the 7clouds / lyrics-channel
family: soft, low-contrast, natural, never noisy. Scenes x moods, curated.

What makes them read as real sky (sources in the amv-ops notes):
- the gradient is deepest at the zenith and paler, whiter and brighter at the
  horizon (longer light path, multiple scattering); at sunset the horizon and
  the region round the sun warm up, and a haze band glows along the horizon.
  Colours are mixed in linear light - sRGB mixing muddies sunset gradients.
- clouds are fBm noise (gain 0.5, lacunarity 2, rotated octaves so no grid
  shows), domain-warped for organic shapes, cut by a coverage remap
  clamp((n - a) / (b - a)) (a: how much cloud, b - a: how soft), lit by the
  density difference toward the sun (Quilez's directional derivative), two
  colours (lit / shade) plus a silver lining near the sun. A cloud deck is a
  plane seen in perspective: shapes shrink, flatten and fade into the
  horizon haze with distance.
- variety comes from curated scene x mood pairs, a small palette jitter and
  composition ranges per seed - never free random colours."""

from __future__ import annotations

import colorsys
import math

import numpy as np
from scipy import ndimage


def hexrgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


# zenith, zenith2 (the side away from the sun), mid, horizon, horizon2, low (bottom, away side),
# glow (round the sun), sun, haze, cloud_lit, cloud_shade, ground_top, ground_bot; night: stars
MOODS = {
    "dusk": dict(zenith="a69ce4", zenith2="8f95e4", mid="c3a3ec", horizon="ffa3f6", horizon2="a493e9",
                 low="0a8be0", glow="ffb4f8", sun="fff0fb", haze="c49ff0", cloud_lit="ffd2f6",
                 cloud_shade="9b8ad6", ground_top="0a5aa3", ground_bot="03447f"),
    "cotton_candy": dict(zenith="7aa6ec", zenith2="8db4f0", mid="b9c3f2", horizon="ffc6e4", horizon2="d9c4f2",
                         low="8fb4ee", glow="ffe2f1", sun="fff6fb", haze="f2d0ea", cloud_lit="fff4fa",
                         cloud_shade="c8b2e6", ground_top="6d7fc4", ground_bot="4c5aa0"),
    "golden_hour": dict(zenith="3f63ad", zenith2="35559e", mid="8ea0d4", horizon="ffc47c", horizon2="f2a58e",
                        low="6f6aa8", glow="ffe3a0", sun="fff6d8", haze="f5c39a", cloud_lit="ffd08c",
                        cloud_shade="8a6f9a", ground_top="3b2f5e", ground_bot="1f1838"),
    "fire_sunset": dict(zenith="252a66", zenith2="1d2257", mid="6c3d8c", horizon="ff7b48", horizon2="e2577a",
                        low="4a2e72", glow="ffc865", sun="fff1c4", haze="f08a6a", cloud_lit="ff9d5c",
                        cloud_shade="4e2b66", ground_top="241536", ground_bot="120a1c"),
    "blue_hour": dict(zenith="1a275a", zenith2="141f4c", mid="3c4f96", horizon="8aa3e0", horizon2="6f84cc",
                      low="23347a", glow="c3cdf2", sun="eef2ff", haze="7d8fd2", cloud_lit="aebee9",
                      cloud_shade="56649f", ground_top="111a40", ground_bot="080d24"),
    "dawn": dict(zenith="86ace8", zenith2="7ea2e2", mid="b8c8ee", horizon="ffd3b4", horizon2="f4bccb",
                 low="8fb0e6", glow="ffe8cc", sun="fff8ec", haze="f0d4d0", cloud_lit="fff1e2",
                 cloud_shade="b9a6c9", ground_top="5a6fa6", ground_bot="384a80"),
    "day_blue": dict(zenith="2f6fd6", zenith2="3a7ad8", mid="6aa3ea", horizon="cfe5fb", horizon2="bcd8f6",
                     low="5b97e2", glow="f4f9ff", sun="ffffff", haze="d8e8f8", cloud_lit="ffffff",
                     cloud_shade="b3c4df", ground_top="2c5a96", ground_bot="173c6c"),
    "mint": dict(zenith="8cc7e2", zenith2="7fb0e6", mid="b2d6ec", horizon="f5c8e6", horizon2="b8aaee",
                 low="3f8fdc", glow="ffd8f0", sun="fff6fb", haze="bccfee", cloud_lit="fff6fb",
                 cloud_shade="a9bde0", ground_top="2a5e9a", ground_bot="173f73"),
    "night": dict(zenith="060a22", zenith2="05081c", mid="111c4e", horizon="2e3b80", horizon2="25306e",
                  low="0c1640", glow="5c6cc0", sun="e8ecff", haze="2a3576", cloud_lit="3a4a8c",
                  cloud_shade="141b44", ground_top="0b1030", ground_bot="04061a", stars=True),
}

# scene -> moods that suit it (a night sea or aurora at noon never comes up)
PAIRS = {
    "ranges": ["dusk", "cotton_candy", "golden_hour", "fire_sunset", "blue_hour", "dawn", "mint", "night"],
    "clouds": ["dusk", "cotton_candy", "golden_hour", "fire_sunset", "dawn", "day_blue", "blue_hour", "mint"],
    "cumulus": ["day_blue", "cotton_candy", "dawn", "golden_hour", "dusk", "mint"],
    "sea": ["golden_hour", "fire_sunset", "dusk", "cotton_candy", "dawn", "blue_hour"],
    "night": ["night"],
    "aurora": ["night"],
}


def mood(name: str, rng) -> dict:
    """The palette as linear-light colours, hue-jittered a little (±6°) and
    saturation ±8% - variety that stays inside the mood."""
    m = MOODS[name]
    dh = rng.uniform(-6, 6) / 360
    ds = rng.uniform(0.92, 1.08)
    out = {}
    for k, v in m.items():
        if not isinstance(v, str):
            out[k] = v
            continue
        r, g, b = hexrgb(v)
        hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
        r, g, b = colorsys.hls_to_rgb((hh + dh) % 1, ll, min(1, ss * ds))
        out[k] = np.array([r, g, b], np.float32) ** 2.2
    return out


def to_srgb(lin: np.ndarray) -> np.ndarray:
    return np.clip(lin, 0, 1) ** (1 / 2.2) * 255


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t, np.float32)
    if t.ndim and t.shape[-1] != 3:
        t = t[..., None]
    return a * (1 - t) + b * t


class Noise:
    """Smooth periodic noise: a Gaussian-filtered random tile, sampled with
    wrap-around; fbm sums octaves with each octave rotated so no grid lines up."""

    def __init__(self, rng, size: int = 512, sigma: float = 3.0):
        t = ndimage.gaussian_filter(rng.standard_normal((size, size)).astype(np.float32), sigma, mode="wrap")
        self.t = (t - t.mean()) / t.std()
        self.size = size
        self.rot = [rng.uniform(0, 2 * math.pi) for _ in range(10)]
        self.off = [rng.uniform(0, size, 2) for _ in range(10)]

    def __call__(self, u, v):
        return ndimage.map_coordinates(self.t, [v, u], order=1, mode="grid-wrap")

    def fbm(self, u, v, octaves: int = 6, gain: float = 0.5, lac: float = 2.0):
        out = np.zeros(np.shape(u), np.float32)
        amp, f, total = 1.0, 1.0, 0.0
        for k in range(octaves):
            c, s = math.cos(self.rot[k]), math.sin(self.rot[k])
            uu, vv = u * f, v * f
            out += amp * self((c * uu - s * vv) + self.off[k][0], (s * uu + c * vv) + self.off[k][1])
            total += amp
            amp *= gain
            f *= lac
        return out / total

    def warped(self, u, v, octaves: int = 6, warp: float = 6.0):
        """fbm(p + warp * q), q = (fbm(p), fbm(p + (5.2, 1.3))) - domain warping."""
        qu = self.fbm(u, v, 4)
        qv = self.fbm(u + 5.2 * 9, v + 1.3 * 9, 4)
        return self.fbm(u + warp * qu, v + warp * qv, octaves)


def sky_gradient(m: dict, x, y, horizon: float, sun: tuple[float, float], aspect: float) -> np.ndarray:
    """Zenith -> mid -> horizon by elevation, the far side cooler, a warm glow
    round the sun and a haze band along the horizon (linear light)."""
    e = np.clip((horizon - y) / horizon, 0, 1)                 # 0 at the horizon, 1 at the top
    sx = sun[0]
    side = smooth(0.0, 1.0, np.abs(x - sx))                    # 0 near the sun, 1 far from it
    zen = mix(m["zenith"], m["zenith2"], side)
    hor = mix(m["horizon"], m["horizon2"], side)
    k1 = smooth(0.0, 0.45, e)
    k2 = smooth(0.35, 1.0, e)
    col = mix(mix(hor, m["mid"], k1), zen, k2)
    d = np.sqrt(((x - sx) * aspect) ** 2 + ((y - sun[1]) * 1.4) ** 2)
    col = mix(col, m["glow"], 0.75 * np.exp(-(d / 0.55) ** 2))
    band = np.exp(-e / 0.10) * (0.35 + 0.4 * np.exp(-((x - sx) * aspect / 0.9) ** 2))
    col = mix(col, m["haze"], 0.6 * band)
    below = y > horizon
    if below.any():
        col = np.where(below[..., None], mix(hor, m["low"], smooth(horizon, 1.0, y)), col)
    return col


def sun_disc(img, m, x, y, sun, aspect, radius: float, strength: float = 1.0):
    d = np.sqrt(((x - sun[0]) * aspect) ** 2 + (y - sun[1]) ** 2)
    disc = smooth(radius * 1.08, radius * 0.92, d)
    bloom = np.exp(-(d / (radius * 4)) ** 2) * 0.5 + np.exp(-(d / (radius * 12)) ** 2) * 0.25
    img = mix(img, m["sun"], np.clip(disc + bloom, 0, 1) * strength)
    return img


def cloud_deck(img, m, x, y, horizon, sun, aspect, rng, noise: Noise, cover: float, soft: float, alpha: float = 0.95):
    """A cloud layer over the sky seen in perspective: plane depth z ~ 1/elevation,
    shapes shrink and flatten toward the horizon and fade into its haze; lit by
    the density difference toward the sun."""
    e = np.clip((horizon - y) / horizon, 0, 1)
    z = 1.0 / (e + 0.12)
    scale = 9.0
    u = (x - 0.5) * aspect * z * scale
    v = z * scale * 1.8                      # stretched across: decks read as wide, shallow banks
    d = noise.warped(u, v, 6, warp=1.2)
    a, b = cover, cover + soft
    cov = smooth(a, b, d)
    # light: density toward the sun (the sun sits on the far horizon: toward +z and its side)
    du = np.tanh((sun[0] - x) * 6) * 0.6       # sign() flipped under the sun: a hard vertical seam
    eps = 1.2
    d2 = noise.warped(u + eps * du, v + eps * 1.0, 6, warp=1.2)
    lit = np.clip((d - d2) * 2.2 + 0.55, 0, 1)
    near_sun = np.exp(-(((x - sun[0]) * aspect) ** 2 + ((y - sun[1]) * 1.5) ** 2) / 0.35)
    col = mix(m["cloud_shade"], m["cloud_lit"], lit)
    rim = cov * (1 - cov) * 4 * near_sun
    col = mix(col, m["sun"], np.clip(rim * 0.8, 0, 1))
    # atmospheric perspective: far clouds melt into the horizon haze
    far = smooth(0.25, 0.0, e)
    col = mix(col, mix(m["haze"], m["horizon"], 0.5), far * 0.75)
    fade = smooth(0.015, 0.12, e) * alpha
    return mix(img, col, cov * fade)


def cumulus(img, m, x, y, horizon, sun, aspect, rng, noise: Noise):
    """Puffy clouds facing the viewer, 1-3 of them. Each is a height field: round
    puffs as hemispheres (big and high in the middle, smaller to the sides, a
    few tiers), merged with a smooth max so creases stay soft, roughened by fbm
    and cut flat at the base; shaded with real normals against the light (the
    sun's side and above) - a cone field with a shifted-difference light looked
    like petals. Farther clouds are smaller and paler."""
    banks = int(rng.integers(1, 4))
    H = x.shape[0]
    for k in sorted(range(banks), reverse=True):
        far = k / max(1, banks - 1) if banks > 1 else 0.0
        span = rng.uniform(0.22, 0.36) * (1 - 0.45 * far)            # half-width, in heights
        base = rng.uniform(0.5, horizon - 0.07) - 0.14 * far
        cx = rng.uniform(0.22, 0.78)
        n = int(rng.integers(24, 40))
        acc = np.zeros_like(x)
        for _ in range(n):
            o = rng.uniform(-1, 1)
            centre = 1 - abs(o)
            r = span * (0.14 + 0.26 * centre) * rng.uniform(0.7, 1.2)
            px = cx + o * span / aspect
            tier = rng.uniform(0.0, 1.4) * centre ** 1.5
            py = base - r * (0.45 + tier)
            d2 = (((x - px) * aspect) ** 2 + (y - py) ** 2) / r ** 2
            hgt = np.sqrt(np.clip(1 - d2, 0, None)) * r
            acc += np.exp(hgt / (0.02 * span))                         # smooth max (log-sum-exp)
        height = np.log(np.maximum(acc, 1e-30)) * 0.02 * span
        height = np.clip(height - 0.02 * span * math.log(n), 0, None)
        detail = noise.fbm(x * aspect * 26 + 40 * k, y * 26, 5)
        height = height * (1 + 0.35 * detail)
        height *= smooth(base + 0.003, base - 0.015, y)                 # the flat base
        height = ndimage.gaussian_filter(height, H / 900)
        cov = smooth(0.0, 0.004 * (1 + span), height)
        gy, gx = np.gradient(height * H)
        nz = np.full_like(height, 1.0)
        norm = np.sqrt(gx ** 2 + gy ** 2 + nz ** 2)
        lx = np.tanh((sun[0] - cx) * 4) * 0.55
        light = np.array([lx, -0.75, 0.5], np.float32)
        light /= np.linalg.norm(light)
        lam = np.clip((-gx * light[0] - gy * light[1] + nz * light[2]) / norm, 0, 1)
        under = smooth(base - 0.3 * span, base, y)                       # bellies in shade
        lit = np.clip(0.25 + 0.85 * lam - 0.3 * under, 0, 1)
        col = mix(m["cloud_shade"], m["cloud_lit"], lit)
        rim = smooth(0.15, 0.0, height / max(1e-6, height.max())) * cov * 0.35
        col = mix(col, m["sun"], rim * np.exp(-((cx - sun[0]) * 2) ** 2))
        col = mix(col, m["haze"], 0.1 + 0.35 * far)
        img = mix(img, col, cov * (0.98 - 0.2 * far))
    return img


def stars(img_srgb: np.ndarray, rng, horizon: float, density: float = 1.0) -> np.ndarray:
    """Stars on an sRGB image at final size: power-law brightness, more of them
    higher up, a few tinted; drawn as tiny soft dots."""
    h, w = img_srgb.shape[:2]
    n = int(w * h / 900 * density)
    xs = rng.uniform(0, w, n)
    ys = h * horizon * (1 - np.sqrt(rng.uniform(0, 1, n)))       # denser toward the top
    mag = rng.pareto(2.2, n) * 0.25 + 0.15
    layer = np.zeros((h, w), np.float32)
    xi, yi = np.clip(xs.astype(int), 0, w - 1), np.clip(ys.astype(int), 0, h - 1)
    np.add.at(layer, (yi, xi), np.clip(mag, 0, 3))
    big = mag > 1.2
    glow = np.zeros_like(layer)
    np.add.at(glow, (yi[big], xi[big]), mag[big])
    s = h / 1080
    layer = ndimage.gaussian_filter(layer, 0.6 * s) * 6 + ndimage.gaussian_filter(glow, 2.5 * s) * 30
    tint = np.ones((h, w, 3), np.float32)
    tint[..., 2] += 0.08
    return np.clip(img_srgb + 255 * np.clip(layer, 0, 1.2)[..., None] * tint * 0.9, 0, 255)


def milky_way(img, x, y, horizon, aspect, rng, noise: Noise):
    """A faint diagonal band of warped noise, dust lanes darker."""
    ang = rng.uniform(-0.6, 0.6)
    cx, cy = rng.uniform(0.3, 0.7), rng.uniform(0.2, 0.4)
    dist = ((y - cy) * math.cos(ang) - (x - cx) * aspect * math.sin(ang) * 0.6)
    band = np.exp(-(dist / 0.12) ** 2)
    d = noise.warped(x * aspect * 9, y * 9, 6, warp=2.0)
    glow = np.clip(band * (0.55 + 0.45 * d), 0, 1) * 0.10
    lanes = np.clip(-noise.fbm(x * aspect * 14 + 50, y * 14, 5), 0, 1) * band * 0.04
    col = np.array([0.55, 0.5, 0.75], np.float32)
    above = smooth(horizon, horizon - 0.15, y)
    return img + ((glow - lanes) * above)[..., None] * col


def aurora(img, x, y, horizon, aspect, rng, noise: Noise):
    """Curtains: a wavy base line, light rising from it with vertical rays, green
    at the base fading to teal and violet at the top; added, not painted over."""
    n = img.shape[1]
    t = np.linspace(0, 1, n)
    base = (horizon - rng.uniform(0.2, 0.3)) + 0.12 * noise.fbm(t * 3.5, np.full(n, 3.0), 4)
    base = base[None, :]
    above = np.clip(base - y, 0, None)
    height = 0.22 + 0.08 * noise.fbm(t * 4 + 7, np.full(n, 5.0), 3)[None, :]
    curtain = np.exp(-above / height) * (y < base + 0.01) * smooth(base + 0.015, base - 0.01, y)
    rays = 0.5 + 0.5 * np.clip(noise.fbm(x * aspect * 30, y * 1.6, 4) * 1.3, -1, 1)
    bright = np.clip(0.5 + 0.9 * noise.fbm(x * aspect * 2.2 + 11, np.full_like(x, 2.0), 3), 0, 1.3)
    a = ndimage.gaussian_filter(np.clip(curtain * rays * bright, 0, 1), (1.0, 4.0 * x.shape[0] / 1080))
    k = np.clip(above / 0.25, 0, 1)
    green, teal, violet = (np.array(c, np.float32) for c in ((0.05, 0.9, 0.35), (0.05, 0.6, 0.7), (0.5, 0.2, 0.75)))
    col = mix(mix(green, teal, smooth(0, 0.5, k)), violet, smooth(0.5, 1, k))
    return img + (a * 0.8)[..., None] * col


def sea(img, m, x, y, horizon, sun, aspect, rng, noise: Noise):
    """Water below the horizon: the sky above mirrored, darkened and cooled,
    rippled sideways more near the viewer, and a glitter path under the sun."""
    h, w = img.shape[:2]
    below = y > horizon
    depth = np.clip((y - horizon) / (1 - horizon), 1e-4, 1)
    src_y = np.clip(horizon - (y - horizon) * 0.9, 0, horizon - 1e-3)
    ripple = noise.fbm(x * aspect * 3 / (depth + 0.05), np.log(depth + 1e-3) * 25, 4)
    src_x = np.clip(x + ripple * 0.004 * (0.3 + depth * 2), 0, 1 - 1e-6)
    refl = np.stack([ndimage.map_coordinates(img[..., c], [src_y * (h - 1), src_x * (w - 1)], order=1)
                     for c in range(3)], -1)
    water = mix(refl * 0.72, m["low"] * 0.6, 0.25 + 0.35 * depth)
    sparkle = np.clip(noise.fbm(x * aspect * 70 / (depth + 0.08), depth * 220, 3) * 1.4, 0, 1) ** 4
    path = np.exp(-(((x - sun[0]) * aspect) / (0.025 + 0.18 * depth)) ** 2)
    water = water + (sparkle * path * 0.9)[..., None] * m["sun"]
    line = np.exp(-(((y - horizon) * h) / 1.5) ** 2) * 0.15
    water = mix(water, m["haze"], line)
    return np.where(below[..., None], water, img)
