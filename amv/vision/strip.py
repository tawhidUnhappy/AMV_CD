"""The start, middle and end of every slot of an EDL, one row per slot.

A contact sheet shows one frame per shot, which misses what happens inside
it: credit text fading in at the start, a cut or a dissolve halfway, a pan
that ends somewhere it should not. This is the check that caught an opening-
credits shot and an off-tone pan in the intro.

    ./amv.sh strip                          # tmp/intro/edl.json
    ./amv.sh strip --edl tmp/edl.json --slots 0-20
"""

from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from amv.core import paths
from amv.vision.compare import frame_list
from amv.vision.contact_sheet import tile

POINTS = (0.05, 0.5, 0.95)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edl", type=Path, default=paths.INTRO / "edl.json")
    parser.add_argument("--slots", default="", help="which slots, e.g. 0-20 (default all)")
    parser.add_argument("--out", type=Path, default=paths.QA / "strip.jpg")
    args = parser.parse_args()

    slots = paths.load_slots(args.edl)
    if args.slots:
        wanted = set(frame_list(args.slots))
        slots = [s for s in slots if s["index"] in wanted]
    work = args.out.parent / "strip_frames"
    work.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s in slots:
        for k, f in enumerate(POINTS):
            label = f"{s['index']} ep{s['episode']:02d} {s['start'] + s['duration'] * f:.1f}s"
            jobs.append((s["file"], s["start"] + s["duration"] * f, label, work / f"{s['index']:03d}_{k}.jpg"))

    def grab(job: tuple[str, float, str, Path]) -> Path:
        file, at, label, out = job
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", file, "-frames:v", "1", "-vf",
                        f"scale=426:240,drawtext=text='{label}':fontcolor=yellow:fontsize=14:x=4:y=4"
                        ":box=1:boxcolor=black@0.6", str(out)], check=True)
        return out

    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(grab, jobs))
    print(f"Wrote {tile(frames, args.out, cols=len(POINTS), cell=None, padding=3)}  ({len(slots)} slots)")


if __name__ == "__main__":
    main()
