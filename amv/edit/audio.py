"""The edit's sound: one window of the song. With "tail" it ends on the song's
instrumental (the mix minus its separated vocals) - a line that starts just before
the loop point would otherwise be cut mid-word every time the edit loops.
Envelopes for picture automation ("bass_zoom") come from the same window."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import numpy as np

from amv.core import paths

SR = 48000


def decode(file: str, start: float, seconds: float, sr: int = SR) -> np.ndarray:
    """(n, 2) float32 of the file from `start` for `seconds`."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.4f}", "-t", f"{seconds:.4f}", "-i", file,
                          "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    data = np.frombuffer(raw, np.float32).reshape(-1, 2)
    want = round(seconds * sr)
    return np.pad(data, ((0, max(0, want - len(data))), (0, 0)))[:want]


def vocals(song: str, start: float, seconds: float) -> np.ndarray:
    """The separated vocals of the window (the configured separator, cached)."""
    from amv.shorts.dub import separate

    pad = 1.0
    stem = separate([{"file": song, "stream": 0, "src": max(0.0, start - pad), "dur": seconds + 2 * pad}])[0]
    return decode(stem["file"], stem["src"] + min(pad, start), seconds)


def window(spec: dict, song: str, out_dir: Path) -> Path:
    """The edit's audio as a wav: the song window, its last part instrumental
    when spec "tail" = {"from": output seconds, "xfade": s}."""
    start, seconds, tail = float(spec.get("song_start", 0.0)), float(spec["seconds"]), spec.get("tail")
    key = hashlib.sha1(f"{song}|{start}|{seconds}|{tail}".encode()).hexdigest()[:12]
    out = out_dir / f"audio_{key}.wav"
    if out.exists():
        return out
    mix = decode(song, start, seconds)
    if tail:
        inst = mix - vocals(song, start, seconds)
        t0, xf = float(tail["from"]), float(tail.get("xfade", 0.06))
        n = np.arange(len(mix)) / SR
        w = np.clip((n - t0) / max(1e-3, xf), 0, 1)[:, None]
        mix = mix * (1 - w) + inst * w
    import soundfile as sf

    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), mix, SR, subtype="FLOAT")
    return out


def bass_envelope(wav: Path, fps: float, frames: int) -> np.ndarray:
    """0-1 per output frame: low-band loudness, fast attack and ~0.12 s release."""
    import librosa

    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    hop = 256
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    low = spec[librosa.fft_frequencies(sr=sr, n_fft=2048) < 130].sum(axis=0)
    db = librosa.amplitude_to_db(low, ref=np.max)
    e = np.clip((db + 30) / 30, 0, 1)
    t = np.arange(frames) / fps
    per = np.interp(t, np.arange(len(e)) * hop / sr, e)
    out, level, release = np.zeros(frames), 0.0, np.exp(-1 / (0.12 * fps))
    for i, v in enumerate(per):
        level = v if v > level else level * release
        out[i] = level
    return out


def cache_dir(name: str) -> Path:
    return paths.EDIT / name
