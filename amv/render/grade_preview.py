"""Apply the current grade to a spread of real EDL frames, for quick tuning.

Far cheaper than a full re-render when the only question is how the colour
correction looks.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from amv.core import paths
from amv.render.grade import GRADE
from amv.vision.contact_sheet import tile

OUT = paths.QA / "grade"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--raw", action="store_true", help="also render ungraded source for comparison")
    args = parser.parse_args()

    slots = paths.load_slots()
    step = max(1, len(slots) // args.count)
    picks = slots[::step][: args.count]

    OUT.mkdir(parents=True, exist_ok=True)
    tiles: list[Path] = []
    for i, slot in enumerate(picks):
        mid = slot["start"] + slot["duration"] / 2
        graded = OUT / f"g{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", slot["file"],
             "-frames:v", "1", "-vf", f"{GRADE},scale=640:360", str(graded)],
            check=True,
        )
        tiles.append(graded)
        if args.raw:
            raw = OUT / f"r{i:02d}.jpg"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", slot["file"],
                 "-frames:v", "1", "-vf", "scale=640:360", str(raw)],
                check=True,
            )
            tiles.append(raw)

    sheet = tile(tiles, paths.QA / "grade_check.jpg", cols=4, cell=None, padding=5, color="0x141414")
    print(f"Wrote {sheet}")


if __name__ == "__main__":
    main()
