"""Measure luma across the rendered AMV to find over-crushed stretches.

The selector gates on *source* brightness, but the grade (S-curve, negative
brightness, vignette) darkens everything after that, so footage that passed can
still land near-black in the final render.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from amv.core.config import ROOT

DEFAULT = ROOT / "data" / "out" / "amv.mp4"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT)
    parser.add_argument("--fps", type=float, default=2.0)
    args = parser.parse_args()

    width, height = 96, 54
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(args.video),
         "-vf", f"scale={width}:{height},fps={args.fps},format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    )
    frame_size = width * height
    count = len(result.stdout) // frame_size
    frames = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    frames = frames.reshape(count, height, width).astype(np.float32) / 255.0
    luma = frames.mean(axis=(1, 2))

    print(f"{count} sampled frames over {count / args.fps:.1f}s")
    print(f"mean {luma.mean():.3f}  median {np.median(luma):.3f}  p10 {np.percentile(luma, 10):.3f}"
          f"  p90 {np.percentile(luma, 90):.3f}")
    for threshold in (0.08, 0.12, 0.16, 0.20):
        share = float((luma < threshold).mean())
        print(f"  below {threshold:.2f}: {share * 100:5.1f}% of runtime")

    print("\nstretches under 0.12 lasting >= 1s:")
    dark = luma < 0.12
    start = None
    for i, flag in enumerate(dark):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if (i - start) / args.fps >= 1.0:
                print(f"  {start / args.fps:6.1f}s -> {i / args.fps:6.1f}s  ({(i - start) / args.fps:4.1f}s)")
            start = None
    if start is not None and (count - start) / args.fps >= 1.0:
        print(f"  {start / args.fps:6.1f}s -> {count / args.fps:6.1f}s  (tail)")


if __name__ == "__main__":
    main()
