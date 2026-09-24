"""Make a short channel intro from the series and the opening of a song.

    uv run python -m amv.intro --song "path/to/track.wav" --seconds 11

Plans cuts from the song (a calm swell, then a cut per beat from the
orchestra's entrance), picks a shot per slot, writes a contact sheet to look
at, and renders tmp/intro/intro.mp4. Everything lands in tmp/intro/.

The picks are in tmp/intro/edl.json. To change a shot: reject its region with
--skip EP:START-END (repeatable) and run again, or edit the JSON by hand and
run with --render-only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from amv.core import config, paths
from amv.vision.contact_sheet import grab_all, tile


def contact_sheet(slots: list[dict], out: Path) -> Path:
    frames = grab_all(slots, out.parent / "frames",
                      lambda s: f"{s['index']:02d} {s['kind']} ep{s['episode']:02d} {s['start']:.1f}s",
                      width=480, fontsize=18)
    return tile(frames, out, cols=4, cell=(480, 270))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--song", type=Path, default=None, help="default: song from config.json")
    parser.add_argument("--seconds", type=float, default=11.0, help="intro length, taken from the song's start")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--candidates", type=int, default=60, help="windows probed per slot")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--skip", action="append", default=[], metavar="EP:START-END",
                        help="reject a region of an episode, e.g. 5:600-640")
    parser.add_argument("--render-only", action="store_true", help="render tmp/intro/edl.json as it stands")
    parser.add_argument("--out", type=Path, default=paths.INTRO / "intro.mp4")
    args = parser.parse_args()

    from amv.intro.render import render

    edl_path = paths.INTRO / "edl.json"
    paths.INTRO.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
    else:
        from amv.intro.plan import plan
        from amv.intro.select import select
        from amv.render.select_clips import scoring

        for item in args.skip:
            ep, _, span = item.partition(":")
            lo, _, hi = span.partition("-")
            scoring.BLACKLIST = (*scoring.BLACKLIST, (int(ep), float(lo), float(hi)))

        song = (args.song or config.load().require_song()).resolve()
        slots, info = plan(song, args.seconds)
        print(f"tempo {info['tempo']:.1f} BPM, orchestra enters at "
              f"{info['entrance'] if info['entrance'] is not None else '-'}s, {len(slots)} shots", flush=True)
        episodes = paths.load_scene_index()
        picks = select(slots, episodes, args.seed, args.candidates, args.workers, paths.INTRO / "motion")
        edl = {"song": str(song), "seconds": args.seconds, "plan": info, "slots": picks}
        edl_path.write_text(json.dumps(edl, indent=1), encoding="utf-8")
        print(f"Wrote {edl_path}", flush=True)

    print(f"Contact sheet: {contact_sheet(edl['slots'], paths.INTRO / 'sheet.jpg')}", flush=True)
    render(edl["slots"], Path(edl["song"]), float(edl["seconds"]), paths.INTRO, args.out)


if __name__ == "__main__":
    main()
