"""The intro's cut plan, read off the opening of the song.

An orchestral opening is two things: a quiet swell, then the moment the
orchestra comes in. The swell gets a couple of long, calm shots; from the
entrance on the cuts land on the beat, so the picture speeds up exactly when
the music does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from amv.audio.beats import detect, extend_grid

# How loud the music must jump, in dB, for a beat to count as the entrance:
# the next half second against the second and a half before it.
ENTRANCE_JUMP_DB = 8.0
# The swell is split into shots of about this long.
CALM_SHOT_SECONDS = 2.8
# The shortest shot the drive may cut to. The same floor as the full AMV
# (amv.render.timeline.MIN_SHOT): anime is drawn on twos and threes, and a shot
# under ~1s holds too few drawings to read as motion - it reads as stutter.
# So the drive cuts every N beats, the smallest N that clears this.
MIN_DRIVE_SHOT = 1.05


@dataclass
class IntroSlot:
    index: int
    out_start: float
    out_end: float
    kind: str  # "calm" (the swell) or "drive" (from the entrance on)

    @property
    def duration(self) -> float:
        return self.out_end - self.out_start

    def as_dict(self) -> dict:
        return {**asdict(self), "duration": round(self.duration, 4)}


def loudness_db(song: Path, seconds: float, hop: float = 0.1) -> tuple[np.ndarray, float]:
    import librosa

    y, sr = librosa.load(str(song), sr=22050, mono=True, duration=seconds + 1.0)
    hop_length = int(sr * hop)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    return 20 * np.log10(rms + 1e-6), hop


def find_entrance(beats: list[float], db: np.ndarray, hop: float, seconds: float) -> float | None:
    """The first beat where the music jumps by ENTRANCE_JUMP_DB - where the
    orchestra comes in. None when the opening never jumps (a track that starts
    at full strength)."""
    for beat in beats:
        if beat < 1.5 or beat > seconds - 1.0:
            continue
        i = int(round(beat / hop))
        before = db[max(0, i - 15):max(1, i - 1)]
        after = db[i:i + 5]
        # A jump out of near-silence is the track fading in, not an entrance.
        if before.size and after.size and before.min() > -60 and after.mean() - before.mean() >= ENTRANCE_JUMP_DB:
            return beat
    return None


def plan(song: Path, seconds: float) -> tuple[list[IntroSlot], dict]:
    beat_data = detect(song)
    beats = [b for b in extend_grid(beat_data["beats"], beat_data["duration"]) if 0.0 < b < seconds]
    db, hop = loudness_db(song, seconds)
    entrance = find_entrance(beats, db, hop, seconds)

    cuts: list[float] = []
    calm_end = entrance if entrance is not None else 0.0
    calm_shots = max(1, round(calm_end / CALM_SHOT_SECONDS)) if entrance is not None else 0
    for k in range(1, calm_shots):
        target = calm_end * k / calm_shots
        cuts.append(min((b for b in beats if b < calm_end), key=lambda b: abs(b - target)))
    if entrance is not None:
        cuts.append(entrance)
    drive = [b for b in beats if b > calm_end + 0.3]
    if len(drive) > 1:
        period = float(np.median(np.diff(drive)))
        drive = drive[int(np.ceil(MIN_DRIVE_SHOT / period)) - 1 :: int(np.ceil(MIN_DRIVE_SHOT / period))]
    cuts += drive
    while cuts and seconds - cuts[-1] < MIN_DRIVE_SHOT:
        cuts.pop()

    edges = [0.0, *sorted(set(round(c, 4) for c in cuts)), seconds]
    slots = [
        IntroSlot(i, edges[i], edges[i + 1], "calm" if entrance is not None and edges[i] < entrance else "drive")
        for i in range(len(edges) - 1)
    ]
    info = {"tempo": beat_data["tempo"], "entrance": entrance, "beats": [round(b, 3) for b in beats]}
    return slots, info
