"""Apply the current grade to a spread of real EDL frames, for quick tuning.

Far cheaper than a full re-render when the only question is how the colour
correction looks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from amv.core.config import ROOT
from amv.render.grade import GRADE

OUT = ROOT / "tmp" / "qa" / "grade"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--raw", action="store_true", help="also render ungraded source for comparison")
    args = parser.parse_args()

    slots = json.loads((ROOT / "tmp" / "edl.json").read_text(encoding="utf-8"))["slots"]
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

    listing = OUT / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in tiles), encoding="ascii")
    columns = 4 if not args.raw else 4
    rows = max(1, (len(tiles) + columns - 1) // columns)
    sheet = ROOT / "tmp" / "qa" / "grade_check.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", f"tile={columns}x{rows}:padding=5:color=0x141414", "-frames:v", "1", str(sheet)],
        check=True,
    )
    print(f"Wrote {sheet}")


if __name__ == "__main__":
    main()
