"""Verify each displayed lyric block sits over actual singing.

The earlier plan (transcribed from the full mix) put "I WOKE UP" on screen at
2.53s when the line is sung at 11.54s. This checks every shown block against
energy in the isolated vocal stem, so that class of error cannot ship silently.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from amv.lyrics import ROOT, timed_phrases

VOCALS = ROOT / "data" / "song" / "vocals.wav"
SR = 8000


def envelope(path: Path) -> np.ndarray:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    hop = SR // 100  # 10ms frames
    usable = samples[: (samples.size // hop) * hop].reshape(-1, hop)
    return np.abs(usable).mean(axis=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocals", type=Path, default=VOCALS)
    parser.add_argument("--lead-in", type=float, default=0.18)
    args = parser.parse_args()

    env = envelope(args.vocals)
    # The stem is mostly silence between lines, so a high percentile of the
    # whole track sits *inside* the loud part of the singing and marks almost
    # everything "quiet". Scale between the silence floor and a robust peak.
    floor = float(np.percentile(env, 20))
    peak = float(np.percentile(env, 99))
    threshold = floor + 0.10 * (peak - floor)
    phrases = [p for p in timed_phrases() if p.show]

    print(f"envelope floor {floor:.5f}  peak {peak:.5f}  -> threshold {threshold:.5f}\n")
    bad = 0
    for p in phrases:
        lo = int(max(0.0, p.start - args.lead_in) * 100)
        hi = min(len(env), int(p.end * 100))
        window = env[lo:hi]
        active = float((window > threshold).mean()) if window.size else 0.0
        # Where singing actually begins relative to the block appearing.
        voiced = np.flatnonzero(window > threshold)
        onset = (voiced[0] / 100.0 - args.lead_in) if voiced.size else float("nan")
        flag = "ok " if active >= 0.55 else "LOW"
        if active < 0.55:
            bad += 1
        print(f"  {flag} {p.start:7.2f}->{p.end:6.2f}  vocal {active * 100:5.1f}%  "
              f"onset {onset:+.2f}s  {' / '.join(p.lines)}")

    print(f"\n{len(phrases)} blocks shown, {bad} with weak vocal coverage")
    if bad == 0:
        print("every displayed line sits over singing")


if __name__ == "__main__":
    main()
