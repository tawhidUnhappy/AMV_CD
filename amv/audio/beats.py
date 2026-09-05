"""Detect the beat grid of the song so cuts can land on it.

The first edit placed cuts on vocal onsets and a flat 0.75s grid through the
instrumental breaks. Audio sync measured clean (0.000s offset), so the loose
feel was editorial: cuts sitting a fraction off the beat read as late even when
nothing is actually delayed. This gives the timeline a real grid to snap to.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from amv.core import config

ROOT = config.ROOT
DEFAULT_OUT = ROOT / "tmp" / "song" / "beats.json"


def detect(song: Path, tightness: float = 100.0) -> dict:
    import librosa

    y, sr = librosa.load(str(song), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, trim=False, tightness=tightness)
    beats = librosa.frames_to_time(beat_frames, sr=sr).astype(float)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
    strengths = np.interp(beats, onset_times, onset_env)

    tempo_value = float(np.atleast_1d(tempo)[0])
    return {
        "song": str(song),
        "tempo": tempo_value,
        "duration": float(len(y) / sr),
        "beats": [round(float(b), 4) for b in beats],
        "strengths": [round(float(s), 4) for s in strengths],
    }


def load(path: Path | None = None) -> list[float]:
    path = path or DEFAULT_OUT
    return json.loads(path.read_text(encoding="utf-8"))["beats"]


def extend_grid(beats: list[float], duration: float) -> list[float]:
    """Pad the grid to the ends of the track using the median beat period.

    beat_track can start late and stop before the outro; slots there still need
    something to snap to.
    """
    if len(beats) < 2:
        return beats
    period = float(np.median(np.diff(beats)))
    grid = list(beats)
    while grid[0] - period > 0:
        grid.insert(0, grid[0] - period)
    while grid[-1] + period < duration:
        grid.append(grid[-1] + period)
    return grid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", type=Path, default=None,
                        help="track to analyse (default: song from config.json)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = detect(args.song or config.load().require_song())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1), encoding="utf-8")

    beats = data["beats"]
    diffs = np.diff(beats)
    print(f"tempo   : {data['tempo']:.2f} BPM")
    print(f"beats   : {len(beats)} from {beats[0]:.2f}s to {beats[-1]:.2f}s")
    print(f"interval: median {np.median(diffs):.4f}s  std {np.std(diffs):.4f}s")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
