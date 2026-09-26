"""The part of a track a Short uses: a few seconds of build, the drop, and the
bass hits after it - read off the audio, no hand timing.

The drop is the biggest rise in the low band (< 150 Hz): the mean bass level
of the next 2 s against the 2 s before. Phonk/funk edits drop out of a
near-silent gap or a thin build, so that rise is 15-35 dB where a verse-to-
chorus change is < 10. The hit grid is the bass onsets from the drop on,
snapped to the beat period (the 808s land on or near it); "accents" are the
strongest of them, where punches and shakes go.

    ./amv.sh short-song "path/to/track.mp3" [--seconds 24] [--build 7]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 22050
HOP = 512


@dataclass
class SongWindow:
    song: str
    start: float  # where in the track the Short begins
    drop: float  # song time of the drop
    end: float
    period: float  # beat period, seconds
    hits: list[float] = field(default_factory=list)  # song times of bass hits, drop onwards
    accents: list[float] = field(default_factory=list)  # the strongest hits
    build_beats: list[float] = field(default_factory=list)  # beats before the drop

    @property
    def seconds(self) -> float:
        return round(self.end - self.start, 3)

    def as_dict(self) -> dict:
        return {**asdict(self), "seconds": self.seconds}


def analyse(song: Path) -> dict:
    return _analyse(str(song))


@lru_cache(maxsize=4)
def _analyse(song: str) -> dict:
    """librosa's view of a track, cached on disk per file version
    (tmp/shorts/cache/song_*.npz) - ~10 s saved per call."""
    from amv.shorts.catalog import CACHE, song_key

    path = CACHE / f"song_{song_key(Path(song))}.npz"
    if path.exists():
        z = np.load(path)
        return {"duration": float(z["duration"]), "bass": z["bass"], "env": z["env"], "onsets": z["onsets"],
                "tempo": float(z["tempo"]), "beats": z["beats"].tolist()}
    a = _librosa(song)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(path, **{k: np.asarray(v) for k, v in a.items()})
    return a


def _librosa(song: str) -> dict:
    import librosa

    y, _ = librosa.load(song, sr=SR, mono=True)
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    bass_db = librosa.amplitude_to_db(spec[freqs < 150])
    bass = 20 * np.log10(spec[freqs < 150].mean(axis=0) + 1e-6)
    env = librosa.onset.onset_strength(S=bass_db, sr=SR, hop_length=HOP)
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, units="frames")
    tempo, beats = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, units="time")
    return {"duration": len(y) / SR, "bass": bass, "env": env, "onsets": onsets,
            "tempo": float(np.atleast_1d(tempo)[0]), "beats": [float(b) for b in beats]}


def find_drops(song: Path, top: int = 5) -> list[tuple[float, float]]:
    """(time, rise dB) of the biggest bass rises, strongest first, >= 4 s apart."""
    a = _analyse(str(song))
    bass, fps = a["bass"], SR / HOP
    span = int(2 * fps)
    rises = np.full(len(bass), -99.0)
    for i in range(span, len(bass) - span):
        rises[i] = bass[i:i + span].mean() - bass[i - span:i].mean()
    picked: list[tuple[float, float]] = []
    for i in np.argsort(rises)[::-1]:
        t = i / fps
        if t < 4 or t > a["duration"] - 12:
            continue
        if all(abs(t - p) > 4 for p, _ in picked):
            picked.append((t, float(rises[i])))
        if len(picked) == top:
            break
    return picked


def _onset_time(a: dict, near: float, within: float = 0.35) -> float:
    """The strongest bass onset within `within` s of `near` (the rise's
    2 s means smear the exact instant)."""
    fps = SR / HOP
    best, score = near, -1.0
    for f in a["onsets"]:
        t = f / fps
        if abs(t - near) <= within and a["env"][f] > score:
            best, score = t, float(a["env"][f])
    return best


def window(song: Path, seconds: float = 24.0, build: float = 7.0, drop: float | None = None) -> SongWindow:
    """The Short's stretch of the track: `build` s before the drop, `seconds` in all."""
    a = _analyse(str(song))
    fps = SR / HOP
    if drop is None:
        drop = find_drops(song, top=1)[0][0]
    drop = _onset_time(a, drop)
    start = max(0.0, drop - build)
    end = min(a["duration"] - 0.5, start + seconds)
    period = 60.0 / a["tempo"]
    # Slowed phonk often tracks at double time; a cut every beat under ~0.3 s
    # is flicker, so read the grid at the half tempo then.
    while period < 0.36:
        period *= 2
    strength = {round(f / fps, 3): float(a["env"][f]) for f in a["onsets"]}
    # Hits: walk the beat grid from the drop, taking the onset nearest each beat.
    hits, t = [], drop
    while t < end - 0.2:
        near = [(abs(o - t), o) for o in strength if abs(o - t) < period * 0.3]
        hits.append(min(near)[1] if near else round(t, 3))
        t = hits[-1] + period
    level = np.percentile([strength.get(h, 0.0) for h in hits], 75) if hits else 0
    accents = [h for h in hits if strength.get(h, 0.0) >= level and strength.get(h, 0.0) > 0]
    build_beats = [round(b, 3) for b in a["beats"] if start < b < drop - 0.1]
    return SongWindow(str(song), round(start, 3), round(drop, 3), round(end, 3), round(period, 4),
                      hits, accents, build_beats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("song", type=Path)
    parser.add_argument("--seconds", type=float, default=24.0)
    parser.add_argument("--build", type=float, default=7.0, help="seconds before the drop")
    parser.add_argument("--drop", type=float, default=None, help="song time of the drop (default: found)")
    args = parser.parse_args()
    for t, rise in find_drops(args.song):
        print(f"bass rise at {t:6.2f}s  +{rise:.1f} dB")
    from amv.shorts.catalog import record_song

    a = analyse(args.song)
    record_song(args.song, find_drops(args.song), a["tempo"], a["duration"])
    w = window(args.song, args.seconds, args.build, args.drop)
    print(json.dumps(w.as_dict(), indent=1))


if __name__ == "__main__":
    main()
