"""Compare two videos frame by frame: how alike every frame is, and a sheet of
the frames you name, A above B.

    ./amv.sh compare reference.mp4 tmp/intro/remake.mp4 --seconds 11 --frames 200-215,284,300
    ./amv.sh compare a.mp4 b.mp4 --video            # also a side-by-side mp4

Likeness is the correlation of mean-removed grey 64x36 frames (1.0 = same
picture; brightness and contrast do not count), with an optional corner
masked for a channel logo. It says nothing on near-black frames - two black
frames can score 0.4 - so look at the sheet before chasing a number.
Both videos are decoded at their own frame rate, frame i against frame i.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from amv.core import paths
from amv.vision.decode import decode_tiny


def frame_list(text: str) -> list[int]:
    out: list[int] = []
    for part in filter(None, text.split(",")):
        lo, _, hi = part.partition("-")
        out += range(int(lo), int(hi or lo) + 1)
    return out


def likeness(a: Path, b: Path, seconds: float | None, corner: str | None) -> np.ndarray:
    from amv.intro.reference import corner_mask, masked_unit

    fa = decode_tiny(str(a), 64, 36, start=0, duration=seconds, gray=True, gpu=False)
    fb = decode_tiny(str(b), 64, 36, start=0, duration=seconds, gray=True, gpu=False)
    n = min(len(fa), len(fb))
    if len(fa) != len(fb):
        print(f"note: {a.name} has {len(fa)} frames, {b.name} has {len(fb)}; comparing the first {n}")
    mask = corner_mask(64, 36, corner)
    return (masked_unit(fa[:n], mask) * masked_unit(fb[:n], mask)).sum(axis=1)


def sheet(a: Path, b: Path, frames: list[int], out: Path, width: int = 320) -> Path:
    rows = []
    for label, video in (("a", a), ("b", b)):
        select = "+".join(f"eq(n,{i})" for i in frames)
        row = out.with_name(f"{out.stem}_{label}.png")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
             # Label before selecting, so %{n} is the frame's number in the video.
             f"drawtext=text='{label} %{{n}}':fontcolor=yellow:fontsize=48:x=12:y=12:box=1:boxcolor=black@0.6,"
             f"select='{select}',scale={width}:-2,tile={len(frames)}x1:padding=2",
             "-fps_mode", "passthrough", "-frames:v", "1", str(row)], check=True)
        rows.append(row)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(rows[0]), "-i", str(rows[1]),
                    "-filter_complex", "vstack", str(out)], check=True)
    return out


def side_by_side(a: Path, b: Path, seconds: float | None, out: Path) -> Path:
    span = ["-t", f"{seconds:.3f}"] if seconds else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(a), "-i", str(b), "-filter_complex",
         "[0:v]scale=960:-2,drawtext=text='A':fontcolor=yellow:fontsize=28:x=10:y=10[l];"
         "[1:v]scale=960:-2,drawtext=text='B':fontcolor=yellow:fontsize=28:x=10:y=10[r];[l][r]hstack[v]",
         "-map", "[v]", "-map", "1:a?", "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac",
         *span, str(out)], check=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--seconds", type=float, default=None, help="compare only the first N seconds")
    parser.add_argument("--frames", default="", help="frames for the sheet, e.g. 200-215,284")
    parser.add_argument("--watermark", choices=["tr", "tl", "br", "bl"], default=None,
                        help="corner to ignore in the likeness")
    parser.add_argument("--below", type=float, default=0.97, help="list frames less alike than this")
    parser.add_argument("--video", action="store_true", help="also write a side-by-side mp4")
    parser.add_argument("--out", type=Path, default=paths.QA / "compare.png")
    args = parser.parse_args()

    corr = likeness(args.a, args.b, args.seconds, args.watermark)
    weak = [(i, round(float(c), 2)) for i, c in enumerate(corr) if c < args.below]
    print(f"{len(corr)} frames  median {np.median(corr):.4f}  mean {corr.mean():.4f}  "
          f"{len(weak)} below {args.below}")
    if weak:
        print("  " + ", ".join(f"{i}:{c}" for i, c in weak[:80]) + (" ..." if len(weak) > 80 else ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames = frame_list(args.frames) or [i for i, _ in weak[:12]]
    if frames:
        print(f"Wrote {sheet(args.a, args.b, frames, args.out)}")
    if args.video:
        print(f"Wrote {side_by_side(args.a, args.b, args.seconds, args.out.with_suffix('.mp4'))}")


if __name__ == "__main__":
    main()
