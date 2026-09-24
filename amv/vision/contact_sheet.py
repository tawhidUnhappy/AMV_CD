"""Render contact sheets of every chosen clip so the edit can be eyeballed.

Catches what the numeric scores cannot: end-credit text, next-episode previews,
eyecatch cards, or a shot that is simply the wrong character.
"""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from amv.core import paths


def grab(slot: dict, path: Path, label: str, width: int = 320, fontsize: int = 14) -> Path:
    """One labelled frame from the middle of a slot's source window."""
    midpoint = slot["start"] + slot["duration"] / 2
    pad = max(3, fontsize // 4)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-ss", f"{midpoint:.3f}", "-i", slot["file"],
            "-frames:v", "1", "-vf", f"scale={width}:-1,drawtext=text='{label}'"
            f":fontcolor=yellow:fontsize={fontsize}:x={pad + 1}:y={pad + 1}:box=1:boxcolor=black@0.6:boxborderw={pad}",
            str(path),
        ],
        check=False,
        capture_output=True,
    )
    return path


def grab_all(slots: list[dict], frames_dir: Path, label, width: int = 320, fontsize: int = 14,
             workers: int = 8) -> list[Path]:
    """A frame per slot, named by slot index; returns the ones that came out."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    digits = 3 if len(slots) > 99 else 2
    jobs = [(slot, frames_dir / f"{slot['index']:0{digits}d}.jpg") for slot in slots]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda job: grab(job[0], job[1], label(job[0]), width, fontsize), jobs))
    missing = [p.name for _, p in jobs if not p.exists()]
    if missing:
        print(f"WARNING: {len(missing)} frames failed: {missing[:8]}", flush=True)
    return [p for _, p in jobs if p.exists()]


def tile(frames: list[Path], sheet: Path, cols: int, cell: tuple[int, int] | None = (320, 180),
         padding: int = 4, color: str = "0x202020") -> Path:
    """Lay frames out in a grid of `cols` columns, each scaled to `cell`
    (or left at its own size with cell=None)."""
    rows = max(1, -(-len(frames) // cols))
    listing = sheet.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in frames), encoding="utf-8")
    scale = f"scale={cell[0]}:{cell[1]}," if cell else ""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-vf", f"{scale}tile={cols}x{rows}:padding={padding}:color={color}", "-frames:v", "1", str(sheet),
        ],
        check=True,
    )
    return sheet


def _label(slot: dict) -> str:
    return f"{slot['index']:03d} ep{slot['episode']:02d} {slot['section']}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edl", type=Path, default=paths.EDL)
    parser.add_argument("--out", type=Path, default=paths.QA)
    parser.add_argument("--per-sheet", type=int, default=42)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    made = grab_all(paths.load_slots(args.edl), args.out / "frames", _label, workers=args.workers)
    for sheet_index in range(0, len(made), args.per_sheet):
        chunk = made[sheet_index : sheet_index + args.per_sheet]
        sheet = tile(chunk, args.out / f"sheet_{sheet_index // args.per_sheet:02d}.jpg", cols=6)
        print(f"Wrote {sheet}", flush=True)


if __name__ == "__main__":
    main()
