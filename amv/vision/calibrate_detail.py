"""Calibrate a text-screen detector against frames judged by eye.

The release burns its diary/phone typesetting into the video, so no subtitle
data marks those spans. Dense small text has far more fine-scale edge energy
than anime line art, which is smooth between sparse contours — this measures
that gap on known-good and known-bad picks before a threshold is chosen.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np

from amv.core.config import ROOT

# Slot indices classified from the QA contact sheets.
TEXT_SCREENS = [1, 2, 9, 19, 25]
SCENERY = [85, 92, 104, 110, 112, 113]
GOOD = [3, 6, 10, 11, 13, 89, 97, 107, 111, 121]


def detail_ratio(path: str, start: float, duration: float) -> tuple[float, float]:
    """Fraction of pixels sitting on a strong edge, plus histogram bimodality."""
    width, height = 256, 144
    command = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(duration, 0.4):.3f}", "-i", path,
        "-vf", f"scale={width}:{height},fps=4,format=gray", "-f", "rawvideo", "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    frame_size = width * height
    count = len(result.stdout) // frame_size
    if count == 0:
        return 0.0, 0.0
    frames = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    frames = frames.reshape(count, height, width).astype(np.float32) / 255.0
    gx = np.abs(np.diff(frames, axis=2))[:, :-1, :]
    gy = np.abs(np.diff(frames, axis=1))[:, :, :-1]
    grad = np.maximum(gx, gy)
    edge_fraction = float((grad > 0.10).mean())
    # Text pages are strongly bimodal: a bright page and dark glyphs.
    hist = np.histogram(frames, bins=16, range=(0, 1))[0].astype(np.float64)
    hist /= hist.sum() + 1e-9
    bimodality = float(np.sort(hist)[-2:].sum())
    return edge_fraction, bimodality


def main() -> None:
    slots = json.loads((ROOT / "data" / "edl.json").read_text(encoding="utf-8"))["slots"]
    by_index = {s["index"]: s for s in slots}

    for label, indices in [("TEXT SCREEN", TEXT_SCREENS), ("SCENERY", SCENERY), ("GOOD", GOOD)]:
        print(f"\n{label}")
        values = []
        for i in indices:
            slot = by_index[i]
            edge, bim = detail_ratio(slot["file"], slot["start"], slot["duration"])
            values.append(edge)
            print(f"  slot {i:3d} ep{slot['episode']:02d}  edge={edge:.4f}  bimodal={bim:.3f}  motion={slot['motion']:.4f}")
        print(f"  -> edge mean {np.mean(values):.4f}  min {min(values):.4f}  max {max(values):.4f}")


if __name__ == "__main__":
    main()
