"""Optional effects for a Short: the song, and a light touch on the picture.

Song (spec "song_fx": "slowed_reverb" | "nightcore" | "slowed" | "sped_up"):
  rendered ONCE to a cached wav (tmp/shorts/cache/fx/) and used as the song
  from then on - so short-song's drop/beat analysis runs on the song you
  hear, and cuts stay on its beats. Dialogue clips are never touched.
    slowed_reverb  0.85x speed and pitch, a hall reverb (the "slowed + reverb" edit sound)
    slowed         0.85x, no reverb
    nightcore      1.25x speed and pitch
    sped_up        1.15x
  "song_fx" may also be {"kind": ..., "rate": 0.8} to set the speed.

Picture (spec "video_fx": ["outline", "glow", "grain"] or {"outline": {...}, ...}):
  applied to the montage only (story scenes stay clean; "video_fx_scope":
  "all" to include them), to the picture before it is placed on its blurred
  fill. All light - they must not fight the edit's own flashes and punches.
    outline  a soft glowing line along strong edges (characters' line art),
             {"color": [r, g, b], "strength": 0-1, "width": px}
    glow     bloom: bright areas bleed light, {"strength": 0-1}
    grain    film grain, {"amount": 0-20}
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SONG_FX = {"slowed_reverb": (0.85, True), "slowed": (0.85, False), "nightcore": (1.25, False),
           "sped_up": (1.15, False)}
DEFAULTS = {"outline": {"color": [255, 255, 255], "strength": 0.55, "width": 3},
            "glow": {"strength": 0.35}, "grain": {"amount": 7}}


def song_fx(song: Path, fx) -> Path:
    """The song with its effect, cached; the original when fx is empty."""
    from amv.shorts.catalog import CACHE, song_key

    if not fx:
        return song
    kind = fx if isinstance(fx, str) else fx["kind"]
    if kind not in SONG_FX:
        raise SystemExit(f"song_fx {kind!r}: use one of {sorted(SONG_FX)}")
    rate, reverb = SONG_FX[kind]
    if isinstance(fx, dict) and fx.get("rate"):
        rate = float(fx["rate"])
    out = CACHE / "fx" / f"{song.stem[:40]}.{kind}.{rate:g}.{song_key(song)}.wav"
    if out.exists():
        return out
    sr = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                             "stream=sample_rate", "-of", "csv=p=0", str(song)],
                            capture_output=True, text=True, check=True).stdout.strip() or 44100)
    # asetrate changes speed AND pitch together - the slowed/nightcore sound,
    # unlike atempo which keeps the pitch.
    chain = f"asetrate={round(sr * rate)},aresample={sr}"
    if reverb:
        chain += ",aecho=0.8:0.85:50|95|160|240:0.35|0.27|0.2|0.13,volume=0.9"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(song), "-af", chain, "-ar", str(sr), str(tmp)],
                   check=True)
    tmp.replace(out)
    return out


def normalise(fx) -> dict:
    """["outline", "grain"] or {"outline": {...}} -> {name: settings with defaults}."""
    if not fx:
        return {}
    items = {name: {} for name in fx} if isinstance(fx, list) else dict(fx)
    out = {}
    for name, cfg in items.items():
        if name not in DEFAULTS:
            raise SystemExit(f"video_fx {name!r}: use any of {sorted(DEFAULTS)}")
        out[name] = {**DEFAULTS[name], **(cfg or {})}
    return out


def apply(frame: np.ndarray, fx: dict, n: int = 0) -> np.ndarray:
    """One picture through the effects, in a fixed order: outline, glow, grain."""
    if not fx:
        return frame
    f = frame.astype(np.float32)
    if "outline" in fx:
        o = fx["outline"]
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
        f = f * (1 - a) + colour * a  # a soft line over the edge
    if "glow" in fx:
        img = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
        luma = np.asarray(img.convert("L"), np.float32) / 255.0
        bright = np.asarray(img, np.float32) * np.clip((luma - 0.62) / 0.38, 0, 1)[..., None]
        bloom = np.asarray(Image.fromarray(bright.astype(np.uint8)).filter(ImageFilter.GaussianBlur(14)), np.float32)
        f = 255 - (255 - f) * (255 - bloom * float(fx["glow"]["strength"])) / 255  # screen blend
    if "grain" in fx:
        rng = np.random.default_rng(n)
        noise = rng.normal(0, float(fx["grain"]["amount"]), frame.shape[:2]).astype(np.float32)[..., None]
        f = f + noise
    return np.clip(f, 0, 255).astype(np.uint8)
