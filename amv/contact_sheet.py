"""Render contact sheets of every chosen clip so the edit can be eyeballed.

Catches what the numeric scores cannot: end-credit text, next-episode previews,
eyecatch cards, or a shot that is simply the wrong character.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDL_PATH = ROOT / "data" / "edl.json"
OUT_DIR = ROOT / "data" / "qa"


def grab(args: tuple[dict, Path]) -> None:
    slot, path = args
    midpoint = slot["start"] + slot["duration"] / 2
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-ss", f"{midpoint:.3f}", "-i", slot["file"],
            "-frames:v", "1", "-vf", "scale=320:-1,drawtext=text='" + _label(slot) + "'"
            ":fontcolor=yellow:fontsize=14:x=4:y=4:box=1:boxcolor=black@0.6:boxborderw=3",
            str(path),
        ],
        check=False,
        capture_output=True,
    )


def _label(slot: dict) -> str:
    return f"{slot['index']:03d} ep{slot['episode']:02d} {slot['section']}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edl", type=Path, default=EDL_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--per-sheet", type=int, default=42)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    slots = json.loads(args.edl.read_text(encoding="utf-8"))["slots"]
    frames_dir = args.out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    jobs = [(slot, frames_dir / f"{slot['index']:03d}.jpg") for slot in slots]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(grab, jobs))

    missing = [p.name for _, p in jobs if not p.exists()]
    if missing:
        print(f"WARNING: {len(missing)} frames failed: {missing[:8]}", flush=True)

    made = [p for _, p in jobs if p.exists()]
    for sheet_index in range(0, len(made), args.per_sheet):
        chunk = made[sheet_index : sheet_index + args.per_sheet]
        listing = args.out / f"list_{sheet_index // args.per_sheet:02d}.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunk), encoding="utf-8")
        sheet = args.out / f"sheet_{sheet_index // args.per_sheet:02d}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                "-vf", "scale=320:180,tile=6x7:padding=4:color=0x202020", "-frames:v", "1", str(sheet),
            ],
            check=True,
        )
        print(f"Wrote {sheet}", flush=True)


if __name__ == "__main__":
    main()
