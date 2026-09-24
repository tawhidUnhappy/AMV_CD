"""Calibrate a 'character on screen' detector.

Diary screens, scenery, signage and food inserts share one property: almost no
skin in frame. Anime faces cover a large area in warm, pale tones, so the skin
fraction should separate the shots worth cutting to from the ones that read as
dead air. Calibrated against picks classified by eye from the contact sheets.
"""

from __future__ import annotations

import numpy as np

from amv.core import paths
from amv.vision.decode import decode_tiny
from amv.vision.skin import skin_mask

# Judged from the current data/qa sheets.
BAD_TEXT = [1, 13, 25]
BAD_SCENERY = [11, 14, 27, 36, 30]
GOOD_FACES = [0, 3, 6, 10, 17, 20, 24, 26, 35, 37, 40]


def probe_color(path: str, start: float, duration: float) -> tuple[float, float]:
    rgb = decode_tiny(path, 96, 54, start=start, duration=max(duration, 0.4), fps=4, gpu=False).astype(np.int16)
    if len(rgb) == 0:
        return 0.0, 0.0
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    saturation = float(np.mean((mx - mn) / (mx + 1e-6)))
    return float(skin_mask(rgb).mean()), saturation


def main() -> None:
    slots = paths.load_slots()
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
