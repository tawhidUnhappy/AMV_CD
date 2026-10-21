"""The pieces of a lyric video's picture, drawn once: the background, lyric
text blocks (white fill, dark rim, soft drop shadow), sparkles, the title card
and the subscribe card. render.py composites them per frame.

Every size is measured off a 1080p reference ("lyrics channel" style) and
scaled by H/1080, so any output size keeps the same look."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from scipy import ndimage

# Lyric text (1080p reference): cap height 111 px, line pitch 126 px, block
# centred; a line wider than WRAP_W of the frame splits into balanced lines.
CAP = 111 / 1080
PITCH = 126 / 111
WRAP_W = 0.78
MAX_W = 0.9
# The rim + shadow: a dark halo all round each letter, heavier down-right.
RIM = 1.6 / 1080
SHADOW_OFFSET = (3.0 / 1080, 4.0 / 1080)
SHADOW_SPREAD = 2.5 / 1080
SHADOW_BLUR = 4.5 / 1080
SHADOW_COLOR = (24, 12, 40)
SHADOW_OPACITY = 0.9


@dataclass
class Sprite:
    """Premultiplied RGBA patch: rgb (h, w, 3) float32 already times alpha, a (h, w) float32."""
    rgb: np.ndarray
    a: np.ndarray
    x: int
    y: int


def background(path: Path, w: int, h: int) -> np.ndarray:
    """The image cover-scaled and centre-cropped to w x h, float32 RGB."""
    img = ImageOps.fit(Image.open(path).convert("RGB"), (w, h), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32)


@dataclass
class Face:
    """A font plus letter spacing (px), measured and drawn the same way."""
    font: ImageFont.FreeTypeFont
    track: float = 0.0

    def getlength(self, text: str) -> float:
        return self.font.getlength(text) + self.track * max(0, len(text) - 1)

    def getbbox(self, text: str):
        return self.font.getbbox(text)

    def draw(self, d: ImageDraw.ImageDraw, x: float, y: float, text: str, fill) -> None:
        if not self.track:
            d.text((x, y), text, font=self.font, fill=fill)
            return
        for ch in text:
            d.text((x, y), ch, font=self.font, fill=fill)
            x += self.font.getlength(ch) + self.track


def font_for_cap(path: Path, cap_px: float, track: float = 0.0) -> Face:
    """The font sized so its capital H is cap_px tall; track = letter spacing
    as a fraction of the cap height."""
    probe = ImageFont.truetype(str(path), 200)
    box = probe.getbbox("H")
    return Face(ImageFont.truetype(str(path), max(4, round(200 * cap_px / (box[3] - box[1])))), track * cap_px)


# A character the font has no glyph for falls back to these (Broday has no "…":
# "THREE… TWO… ONE…" rendered as "THREE   TWO   ONE").
FALLBACK = {"…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "‐": "-"}


def displayable(text: str, face: Face) -> str:
    """The text with every character the font lacks replaced by its FALLBACK
    (or dropped)."""
    font = face.font
    missing = (font.getbbox("\ue000"), font.getlength("\ue000"))
    out = []
    for ch in text:
        if ch.strip() and (font.getbbox(ch), font.getlength(ch)) == missing:
            ch = "".join(c for c in FALLBACK.get(ch, "") if (font.getbbox(c), font.getlength(c)) != missing)
        out.append(ch)
    return "".join(out)


def wrap(text: str, font: Face, max_w: float) -> list[str]:
    """One line if it fits, else the most balanced split into 2 (or 3) lines."""
    words = text.split()
    if font.getlength(text) <= max_w or len(words) < 2:
        return [text]
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        cost = max(font.getlength(a), font.getlength(b))
        if best is None or cost < best[0]:
            best = (cost, [a, b])
    if best[0] > max_w * 1.15 and len(words) >= 3:
        for i in range(1, len(words) - 1):
            for j in range(i + 1, len(words)):
                parts = [" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:])]
                cost = max(font.getlength(p) for p in parts)
                if cost < best[0]:
                    best = (cost, parts)
    return best[1]


def roughen(mask: np.ndarray, amount: float, wave: float, bold: float = 0.0, seed: int = 3) -> np.ndarray:
    """A hand-drawn look on a clean font: strokes thickened by `bold` px,
    corners rounded, the outline pushed in and out by `amount` px of smooth
    noise whose wavelength is ~`wave` px. The reference's letters wobble
    ~1.5 px @1080 over ~20 px stretches (a fifth of the cap height)."""
    if amount <= 0 and bold <= 0:
        return mask
    if bold > 0:
        mask = ndimage.grey_dilation(mask, footprint=_disk(bold))
    rng = np.random.default_rng(seed)
    soft = ndimage.gaussian_filter(mask, max(0.6, amount * 0.9))
    if amount > 0:
        dy = ndimage.gaussian_filter(rng.standard_normal(mask.shape), wave / 2.5)
        dx = ndimage.gaussian_filter(rng.standard_normal(mask.shape), wave / 2.5)
        k = amount / max(1e-6, float(np.hypot(dy.std(), dx.std())))
        yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]].astype(np.float32)
        soft = ndimage.map_coordinates(soft, [yy + dy * k, xx + dx * k], order=1)
    return np.clip((soft - 0.5) * 1.6 + 0.5, 0, 1).astype(np.float32)


def text_block(lines: list[str], font: Face, cap_px: float, pitch_px: float, h: int,
               fill=(255, 255, 255), rough: float = 0.0, bold: float = 0.0) -> Sprite:
    """Centred lines with the rim + soft shadow, as one premultiplied sprite
    (x/y = its top-left when the block's centre is at 0, 0). rough: hand-drawn
    edge wobble and bold: stroke thickening, both px @1080 (0 = the font as drawn)."""
    unit = h  # the 1080-relative constants are fractions of frame height
    pad = int(math.ceil((SHADOW_BLUR * 3 + SHADOW_SPREAD + max(SHADOW_OFFSET)) * unit + 4))
    widths = [font.getlength(t) for t in lines]
    W = int(max(widths)) + 2 * pad
    H = int(pitch_px * (len(lines) - 1) + cap_px * 1.6) + 2 * pad
    asc = font.getbbox("H")[1]
    mask = Image.new("L", (W, H))
    d = ImageDraw.Draw(mask)
    top = pad + cap_px * 0.3
    for i, (t, tw) in enumerate(zip(lines, widths)):
        font.draw(d, (W - tw) / 2, top + i * pitch_px - asc, t, 255)
    fillm = roughen(np.asarray(mask, dtype=np.float32) / 255, rough * unit / 1080, cap_px * 0.2, bold * unit / 1080)
    rim = ndimage.gaussian_filter(ndimage.grey_dilation(fillm, footprint=_disk(RIM * unit)), 0.6)
    sh = ndimage.grey_dilation(fillm, footprint=_disk(SHADOW_SPREAD * unit))
    sh = ndimage.shift(sh, (SHADOW_OFFSET[1] * unit, SHADOW_OFFSET[0] * unit), order=1)
    sh = ndimage.gaussian_filter(sh, SHADOW_BLUR * unit) * SHADOW_OPACITY
    dark = np.maximum(sh, rim * 0.9)
    color = np.array(fill, np.float32)[None, None, :]
    shade = np.array(SHADOW_COLOR, np.float32)[None, None, :]
    a = fillm + dark * (1 - fillm)
    rgb = color * fillm[..., None] + shade * (dark * (1 - fillm))[..., None]
    # The block's centre is the middle of the caps of the lines, not of the padded patch.
    cy = top + (pitch_px * (len(lines) - 1) + cap_px) / 2
    return _trim(Sprite(rgb, a, -W // 2, -int(round(cy))))


def _disk(r: float) -> np.ndarray:
    r = max(0.5, r)
    n = int(math.ceil(r))
    y, x = np.mgrid[-n:n + 1, -n:n + 1]
    return (x * x + y * y) <= r * r + 0.25


def _trim(s: Sprite) -> Sprite:
    ys, xs = np.nonzero(s.a > 1 / 512)
    if not len(ys):
        return s
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return Sprite(s.rgb[y0:y1, x0:x1].copy(), s.a[y0:y1, x0:x1].copy(), s.x + x0, s.y + y0)


def lyric_sprite(text: str, font_path: Path, w: int, h: int, rough: float = 0.0, bold: float = 0.0,
                 track: float = 0.0) -> Sprite:
    """A lyric line as the reference sets it: upper case, centred, wrapped."""
    cap = CAP * h
    font = font_for_cap(font_path, cap, track)
    lines = wrap(displayable(text.upper(), font), font, WRAP_W * w)
    widest = max(font.getlength(t) for t in lines)
    if widest > MAX_W * w:  # a single unbreakable run: shrink
        cap *= MAX_W * w / widest
        font = font_for_cap(font_path, cap, track)
    # a descender (Broday's comma drops 0.15 cap) must clear the next line's caps
    base = font.getbbox("H")[3]
    desc = max((font.getbbox(ch)[3] - base for t in lines[:-1] for ch in set(t) if ch.strip()), default=0)
    pitch = max(cap * PITCH, cap + desc + cap * 0.1)
    return text_block(lines, font, cap, pitch, h, rough=rough, bold=bold)


def title_sprite(title: str, artist: str, font_path: Path, w: int, h: int,
                 title_cap: float = 0.27, artist_cap: float = 0.072, max_w: float = 0.86, rough: float = 0.0,
                 bold: float = 0.0, track: float = 0.0) -> Sprite:
    """The opening title card / thumbnail text: the title huge, the artist under it."""
    cap = title_cap * h
    font = font_for_cap(font_path, cap, track)
    title, artist = displayable(title.upper(), font), displayable(artist.upper(), font)
    tw = font.getlength(title.upper())
    if tw > max_w * w:
        cap *= max_w * w / tw
        font = font_for_cap(font_path, cap, track)
    # bigger letters wobble a little more, not proportionally (that read as melting)
    big = text_block([title.upper()], font, cap, cap, h, rough=rough * math.sqrt(cap / (CAP * h)),
                     bold=bold * cap / (CAP * h))
    if not artist:
        return big
    acap = min(artist_cap * h, cap * 0.4)
    afont = font_for_cap(font_path, acap, track)
    if afont.getlength(artist.upper()) > max_w * w:
        acap *= max_w * w / afont.getlength(artist.upper())
        afont = font_for_cap(font_path, acap, track)
    k = max(0.5, acap / (CAP * h))
    small = text_block([artist.upper()], afont, acap, acap, h, rough=rough * k, bold=bold * k)
    gap = cap * 0.12
    # stack: title caps centred above, artist caps below, the pair centred on 0
    title_cy, artist_cy = -(acap + gap) / 2, (cap + gap) / 2
    return stack([(big, title_cy), (small, artist_cy)])


def stack(parts: list[tuple[Sprite, float]]) -> Sprite:
    x0 = min(s.x for s, _ in parts)
    y0 = min(int(round(s.y + cy)) for s, cy in parts)
    x1 = max(s.x + s.a.shape[1] for s, _ in parts)
    y1 = max(int(round(s.y + cy)) + s.a.shape[0] for s, cy in parts)
    rgb = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    a = np.zeros((y1 - y0, x1 - x0), np.float32)
    for s, cy in parts:
        ox, oy = s.x - x0, int(round(s.y + cy)) - y0
        sl = (slice(oy, oy + s.a.shape[0]), slice(ox, ox + s.a.shape[1]))
        rgb[sl] = s.rgb + rgb[sl] * (1 - s.a[..., None])
        a[sl] = s.a + a[sl] * (1 - s.a)
    return Sprite(rgb, a, x0, y0)


def blend(frame: np.ndarray, s: Sprite, cx: int, cy: int, opacity: float = 1.0) -> None:
    """Composite a premultiplied sprite onto a float32 frame in place, its
    origin at (cx, cy) (clipped to the frame)."""
    if opacity <= 0:
        return
    H, W = frame.shape[:2]
    x, y = cx + s.x, cy + s.y
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + s.a.shape[1]), min(H, y + s.a.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    sa = s.a[y0 - y:y1 - y, x0 - x:x1 - x]
    srgb = s.rgb[y0 - y:y1 - y, x0 - x:x1 - x]
    region = frame[y0:y1, x0:x1]
    if opacity < 1:
        sa = sa * opacity
        srgb = srgb * opacity
    region *= 1 - sa[..., None]
    region += srgb


# ---- sparkles: small white dots drifting up, twinkling ----------------------

def sparkles(n: int, w: int, h: int, seed: int = 7) -> list[dict]:
    """Particles of the reference: radius 1.2-3.6 px @1080, mostly bright, rising 15-50 px/s
    with a slight sideways drift, alpha twinkling, spread over the frame."""
    rng = np.random.default_rng(seed)
    u = h / 1080
    out = []
    for _ in range(n):
        out.append({
            "x": rng.uniform(0, w), "y": rng.uniform(0, h),
            "vy": -rng.uniform(15, 50) * u, "vx": rng.uniform(-8, 8) * u,
            "r": rng.choice([1.2, 1.6, 2.0, 2.5, 3.0, 3.6], p=[.2, .22, .22, .16, .12, .08]) * u,
            "tw": rng.uniform(0.3, 1.2), "ph": rng.uniform(0, 2 * math.pi), "base": rng.uniform(0.6, 1.0),
        })
    return out


def dot_sprite(r: float) -> Sprite:
    n = int(math.ceil(r * 3)) + 1
    y, x = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    d = np.sqrt(x * x + y * y)
    core = np.clip(r + 0.5 - d, 0, 1)
    glow = np.exp(-(d / (r * 1.8)) ** 2) * 0.35
    a = np.clip(core + glow, 0, 1)
    return Sprite(np.repeat(a[..., None] * 255, 3, axis=2), a, -n, -n)


def sparkle_frame(frame: np.ndarray, parts: list[dict], dots: dict, t: float) -> None:
    H, W = frame.shape[:2]
    for p in parts:
        y = (p["y"] + p["vy"] * t) % (H + 40) - 20
        x = (p["x"] + p["vx"] * t) % W
        alpha = p["base"] * (0.7 + 0.3 * math.sin(2 * math.pi * p["tw"] * t + p["ph"]))
        blend(frame, dots[p["r"]], int(round(x)), int(round(y)), alpha)


# ---- the subscribe card -------------------------------------------------------

CARD = (900, 190)        # 1080p reference size, bottom centre
CARD_BOTTOM = 70         # px above the frame's bottom edge
RED = (230, 0, 18)


def _round_rect(size, radius, fill) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=fill)
    return img


def avatar(logo: Path, d: int, focus=(0.5, 0.5), zoom: float = 1.0) -> Image.Image:
    """A round crop of the logo, centred on focus (fractions of the image),
    zoom > 1 crops closer."""
    img = Image.open(logo).convert("RGB")
    side = int(min(img.size) / max(1.0, zoom))
    cx, cy = focus[0] * img.width, focus[1] * img.height
    x0 = min(max(0, cx - side / 2), img.width - side)
    y0 = min(max(0, cy - side / 2), img.height - side)
    img = img.crop((int(x0), int(y0), int(x0) + side, int(y0) + side)).resize((d * 4, d * 4), Image.LANCZOS)
    m = Image.new("L", (d * 4, d * 4))
    ImageDraw.Draw(m).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    out = Image.new("RGBA", (d * 4, d * 4))
    out.paste(img, (0, 0), m)
    return out.resize((d, d), Image.LANCZOS)


def bell(size: int, filled: bool, color) -> Image.Image:
    """A notification bell (outline, or filled with ringing strokes)."""
    S = size * 4
    img = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(img)
    lw = max(2, S // 14)
    body = [(S * .5, S * .14), (S * .72, S * .3), (S * .74, S * .62), (S * .84, S * .74), (S * .16, S * .74),
            (S * .26, S * .62), (S * .28, S * .3)]
    if filled:
        d.polygon(body, fill=color)
        d.ellipse((S * .4, S * .74, S * .6, S * .9), fill=color)
        for side in (-1, 1):  # ringing strokes
            cx = S * .5 + side * S * .36
            d.arc((cx - S * .14, S * .2, cx + S * .14, S * .56), 300 if side > 0 else 120, 60 if side > 0 else 240,
                  fill=color, width=lw)
    else:
        d.line(body + [body[0]], fill=color, width=lw, joint="curve")
        d.arc((S * .4, S * .68, S * .6, S * .9), 0, 180, fill=color, width=lw)
    d.ellipse((S * .45, S * .07, S * .55, S * .17), fill=color)
    return img.resize((size, size), Image.LANCZOS)


def cursor(size: int) -> Image.Image:
    """A white arrow pointer with a black outline, tip at (0, 0)."""
    S = size * 4
    pts = [(0, 0), (0, S * .78), (S * .2, S * .6), (S * .33, S * .92), (S * .45, S * .87), (S * .32, S * .56),
           (S * .56, S * .56)]
    img = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=max(2, S // 22))
    return img.resize((size, size), Image.LANCZOS)


def card_states(channel: dict, ui_font: Path, h: int) -> dict:
    """The card in its three states (subscribe / subscribed / bell on) as RGBA
    images at output scale, plus where the button and bell sit on it."""
    u = h / 1080
    W, H = int(CARD[0] * u), int(CARD[1] * u)

    def font(px, weight):
        f = ImageFont.truetype(str(ui_font), max(6, int(px * u)))
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f

    name_f, tag_f, btn_f = font(46, "Medium"), font(24, "Regular"), font(26, "Medium")
    base = _round_rect((W, H), int(14 * u), (255, 255, 255, 255))
    av = int(130 * u)
    base.alpha_composite(avatar(Path(channel["logo"]), av, tuple(channel.get("focus", (0.5, 0.5))),
                                channel.get("zoom", 1.0)),
                         (int(30 * u), (H - av) // 2))
    d = ImageDraw.Draw(base)
    tx = int(30 * u + av + 26 * u)
    name = channel["name"]
    tagline = channel.get("tagline", "")
    ny = H / 2 - (30 * u if tagline else 0)
    d.text((tx, ny), name, font=name_f, fill=(15, 15, 15), anchor="lm")
    nx_end = tx + name_f.getlength(name)
    if channel.get("verified"):
        r = 11 * u
        cx, cy = nx_end + 12 * u + r, ny
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(96, 96, 96))
        d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .4), (cx + r * .5, cy - r * .35)], fill="white",
               width=max(1, int(3 * u)))
        nx_end = cx + r
    if tagline:
        d.text((tx, H / 2 + 26 * u), tagline, font=tag_f, fill=(110, 110, 110), anchor="lm")
    bw, bh = int(220 * u), int(58 * u)
    bx = int(max(nx_end + 40 * u, W - 30 * u - bw - 60 * u))
    by = (H - bh) // 2
    bell_size = int(44 * u)
    bell_xy = (int(bx + bw + 22 * u), (H - bell_size) // 2)

    def with_button(subscribed: bool, bell_on: bool) -> Image.Image:
        img = base.copy()
        dd = ImageDraw.Draw(img)
        if subscribed:
            dd.rounded_rectangle((bx, by, bx + bw, by + bh), int(4 * u), fill=(236, 236, 236))
            dd.text((bx + bw / 2, by + bh / 2), "SUBSCRIBED", font=btn_f, fill=(110, 110, 110), anchor="mm")
            img.alpha_composite(bell(bell_size, bell_on, (40, 40, 40, 255) if bell_on else (96, 96, 96, 255)),
                                bell_xy)
        else:
            dd.rounded_rectangle((bx, by, bx + bw, by + bh), int(4 * u), fill=RED)
            dd.text((bx + bw / 2, by + bh / 2), "SUBSCRIBE", font=btn_f, fill="white", anchor="mm")
        return img

    shadow = Image.new("RGBA", (W + int(60 * u), H + int(60 * u)))
    shadow.alpha_composite(_round_rect((W, H), int(14 * u), (0, 0, 0, 70)), (int(30 * u), int(36 * u)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12 * u))
    return {
        "size": (W, H), "shadow": shadow, "shadow_off": (int(-30 * u), int(-30 * u)),
        "subscribe": with_button(False, False), "subscribed": with_button(True, False),
        "bell_on": with_button(True, True),
        "button": (bx + bw / 2, by + bh / 2), "bell": (bell_xy[0] + bell_size / 2, bell_xy[1] + bell_size / 2),
        "cursor": cursor(int(44 * u)),
    }


def to_sprite(img: Image.Image, x: int = 0, y: int = 0) -> Sprite:
    a = np.asarray(img, dtype=np.float32)
    alpha = a[..., 3] / 255
    return Sprite(a[..., :3] * alpha[..., None], alpha, x, y)
