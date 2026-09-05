"""Pull candidate thumbnail frames from the strongest shots in the EDL.

Thumbnails come from the *original* footage, not the graded render — the video
is deliberately cool and vignetted, which is the opposite of what reads at
120px in a YouTube sidebar.
"""

from __future__ import annotations

import argparse
import json
import subprocess

from amv.core.config import ROOT
OUT = ROOT / "tmp" / "qa" / "thumbcand"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--min-skin", type=float, default=0.22)
    args = parser.parse_args()

    slots = json.loads((ROOT / "tmp" / "edl.json").read_text(encoding="utf-8"))["slots"]
    # Big faces, bright and punchy: high skin fraction plus strong contrast.
    ranked = sorted(
        (s for s in slots if s.get("skin", 0) >= args.min_skin and s.get("brightness", 0) > 0.18),
        key=lambda s: -(s.get("skin", 0) * 2 + s.get("contrast", 0)),
    )[: args.count]

    OUT.mkdir(parents=True, exist_ok=True)
    tiles = []
    for i, slot in enumerate(ranked):
        mid = slot["start"] + slot["duration"] / 2
        full = OUT / f"cand{i:02d}.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.3f}", "-i", slot["file"],
             "-frames:v", "1", "-vf", "scale=1280:720", str(full)],
            check=True,
        )
        tile = OUT / f"t{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(full), "-vf",
             f"scale=440:248,drawtext=text='{i:02d} ep{slot['episode']:02d}':fontcolor=yellow:fontsize=22"
             ":x=6:y=6:box=1:boxcolor=black@0.7:boxborderw=4", str(tile)],
            check=True,
        )
        tiles.append(tile)
        print(f"  cand{i:02d}  ep{slot['episode']:02d} @{mid:7.1f}s  skin={slot.get('skin', 0):.3f}")

    listing = OUT / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in tiles), encoding="ascii")
    sheet = ROOT / "tmp" / "qa" / "thumb_candidates.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", "tile=4x3:padding=5:color=0x141414", "-frames:v", "1", str(sheet)],
        check=True,
    )
    print(f"\nWrote {sheet}")


if __name__ == "__main__":
    main()
