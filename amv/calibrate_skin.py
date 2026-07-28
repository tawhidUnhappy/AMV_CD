"""Calibrate a 'character on screen' detector.

Diary screens, scenery, signage and food inserts share one property: almost no
skin in frame. Anime faces cover a large area in warm, pale tones, so the skin
fraction should separate the shots worth cutting to from the ones that read as
dead air. Calibrated against picks classified by eye from the contact sheets.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# Judged from the current data/qa sheets.
BAD_TEXT = [1, 13, 25]
BAD_SCENERY = [11, 14, 27, 36, 30]
GOOD_FACES = [0, 3, 6, 10, 17, 20, 24, 26, 35, 37, 40]


def probe_color(path: str, start: float, duration: float) -> tuple[float, float]:
    width, height, fps = 96, 54, 4
    command = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{max(duration, 0.4):.3f}", "-i", path,
        "-vf", f"scale={width}:{height},fps={fps},format=rgb24", "-f", "rawvideo", "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    frame_size = width * height * 3
    count = len(result.stdout) // frame_size
    if count == 0:
        return 0.0, 0.0
    data = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = data.reshape(count, height, width, 3).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    # Anime skin: bright, warm, R > G > B, with a modest spread.
    skin = (r > 110) & (g > 70) & (b > 50) & (r > g) & (g >= b) & ((mx - mn) > 14) & ((r - b) > 18) & (r < 252)
    saturation = float(np.mean((mx - mn) / (mx + 1e-6)))
    return float(skin.mean()), saturation


def main() -> None:
    slots = json.loads((ROOT / "data" / "edl.json").read_text(encoding="utf-8"))["slots"]
    by_index = {s["index"]: s for s in slots}
    for label, indices in [("TEXT SCREEN", BAD_TEXT), ("SCENERY/INSERT", BAD_SCENERY), ("CHARACTER", GOOD_FACES)]:
        print(f"\n{label}")
        values = []
        for i in indices:
            slot = by_index[i]
            skin, sat = probe_color(slot["file"], slot["start"], slot["duration"])
            values.append(skin)
            print(f"  slot {i:3d} ep{slot['episode']:02d}  skin={skin:.4f}  sat={sat:.3f}")
        print(f"  -> skin mean {np.mean(values):.4f}  min {min(values):.4f}  max {max(values):.4f}")


if __name__ == "__main__":
    main()
