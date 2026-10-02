"""Optional effects for a Short - the song, and a light touch on the picture.
Both are plug-ins (amv/plugins/song_fx, amv/plugins/video_fx; add your own in
plugins/): this module only looks them up and applies them.

Song (spec "song_fx": NAME or {"kind": NAME, "rate": 0.8, ...}): rendered ONCE
  to a cached wav (tmp/shorts/cache/fx/) and used as the song from then on -
  so short-song's drop/beat analysis runs on the song you hear, and cuts stay
  on its beats. Dialogue clips are never touched.

Picture (spec "video_fx": [NAME, ...] or {NAME: {settings}, ...}): applied to
  the montage only (story scenes stay clean; "video_fx_scope": "all" to
  include them), to the picture before it is placed on its blurred fill.

    ./amv.sh plugins        # the installed effects
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from amv import plugins


def song_fx(song: Path, fx) -> Path:
    """The song with its effect, cached; the original when fx is empty."""
    from amv.shorts.catalog import CACHE, song_key

    if not fx:
        return song
    kind = fx if isinstance(fx, str) else fx["kind"]
    plug = plugins.get("song_fx", kind)
    settings = {**plug.defaults, **({k: v for k, v in fx.items() if k != "kind"} if isinstance(fx, dict) else {})}
    rate = settings.get("rate", 1.0)
    out = CACHE / "fx" / f"{song.stem[:40]}.{kind}.{rate:g}.{song_key(song)}.wav"
    if out.exists():
        return out
    sr = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                             "stream=sample_rate", "-of", "csv=p=0", str(song)],
                            capture_output=True, text=True, check=True).stdout.strip() or 44100)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(song), "-af", plugins.call(plug.chain, sr, settings),
                    "-ar", str(sr), str(tmp)], check=True)
    tmp.replace(out)
    return out


def song_fx_label(fx) -> str:
    """"Slowed + Reverb" - how the description names the edit ("" for none)."""
    if not fx:
        return ""
    kind = fx if isinstance(fx, str) else fx.get("kind")
    plug = plugins.find("song_fx", kind)
    return plug.label if plug else ""


def normalise(fx) -> dict:
    """[NAME, ...] or {NAME: {...}} -> {name: settings with defaults}, in run order."""
    if not fx:
        return {}
    items = {name: {} for name in fx} if isinstance(fx, list) else dict(fx)
    chosen = [(plugins.get("video_fx", name), cfg) for name, cfg in items.items()]
    chosen.sort(key=lambda pc: (pc[0].order, pc[0].name))
    return {plug.name: {**plug.defaults, **(cfg or {})} for plug, cfg in chosen}


def apply(frame: np.ndarray, fx: dict, n: int = 0) -> np.ndarray:
    """One picture through the effects, in their order."""
    if not fx:
        return frame
    f = frame.astype(np.float32)
    for name, settings in fx.items():
        f = plugins.call(plugins.get("video_fx", name).apply, f, frame, settings, n)
    return np.clip(f, 0, 255).astype(np.uint8)
