"""Cross-correlate the rendered audio against the source mp3.

Confirms whether the muxed track sits where the lyric timings assume, or whether
mp3 decoder delay / AAC priming shifted it. Any real offset here would push the
whole overlay off the vocal.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from amv.core import config

ROOT = config.ROOT
SR = 8000


def decode(path: Path, seconds: float) -> np.ndarray:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-t", f"{seconds}",
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(result.stdout, dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=ROOT / "data" / "out" / "amv.mp4")
    parser.add_argument("--song", type=Path, default=None,
                        help="reference track (default: song from config.json)")
    parser.add_argument("--window", type=float, default=45.0)
    args = parser.parse_args()

    a = decode(args.song or config.load().require_song(), args.window)
    b = decode(args.video, args.window)
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]

    # Envelope correlation is robust to the codec change between the two.
    def envelope(x: np.ndarray) -> np.ndarray:
        hop = 64
        frames = x[: (x.size // hop) * hop].reshape(-1, hop)
        env = np.abs(frames).mean(axis=1)
        return (env - env.mean()) / (env.std() + 1e-9)

    ea, eb = envelope(a), envelope(b)
    max_lag = int(3.0 * SR / 64)
    corr = np.correlate(eb, ea[max_lag:-max_lag], mode="valid")
    lag_frames = int(np.argmax(corr)) - max_lag
    lag_seconds = lag_frames * 64 / SR

    print(f"samples compared : {n} ({n / SR:.1f}s)")
    print(f"peak correlation : lag {lag_frames} frames = {lag_seconds:+.3f}s")
    print("  (positive = rendered audio is LATE relative to the source mp3)")
    if abs(lag_seconds) < 0.03:
        print("  -> audio is aligned; any perceived lag is editorial, not a mux offset")
    else:
        print("  -> real offset, lyric timings need shifting by this amount")


if __name__ == "__main__":
    main()
