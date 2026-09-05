"""Extract the embedded English ASS track from every episode and index its events.

The subtitle track is the pipeline's map of where things *happen* in the source:
each dialogue event is a timestamped, text-labelled moment, which is what the
clip picker searches over instead of blind-sampling the episodes.

ASS parsing itself lives in amv/subs/ass_parser.py; this module is the
episode-discovery and indexing CLI built on top of it.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

from amv.core import config
from amv.core.ffmpeg_tools import probe_duration, run, subtitle_stream_index
from amv.subs.ass_parser import episode_number, is_dialogue, parse_ass

ROOT = config.ROOT
DEFAULT_SUBS_DIR = ROOT / "tmp" / "subs"
DEFAULT_INDEX = ROOT / "tmp" / "subs" / "scene_index.json"

VIDEO_EXTENSIONS = ("*.mkv", "*.mp4", "*.m4v", "*.avi", "*.ts")


def main() -> None:
    cfg = config.load()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None,
                        help="episode directory (default: source_dir from config.json)")
    parser.add_argument("--episode-pattern", default=cfg.episode_pattern,
                        help="regex with one capture group for the episode number")
    parser.add_argument("--subs-dir", type=Path, default=DEFAULT_SUBS_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source = args.source or cfg.require_source()
    pattern = re.compile(args.episode_pattern, re.IGNORECASE)

    args.subs_dir.mkdir(parents=True, exist_ok=True)
    found = [p for ext in VIDEO_EXTENSIONS for p in source.glob(ext)]
    episodes = sorted(
        (p for p in found if episode_number(p, pattern) is not None),
        key=lambda p: episode_number(p, pattern) or 0,
    )
    if not episodes:
        raise SystemExit(
            f"No episodes matched in {source}\n"
            f"  files seen: {len(found)}\n"
            f"  pattern   : {args.episode_pattern}\n"
            f"Adjust 'episode_pattern' in config.json to match your filenames."
        )

    index: dict = {"source": str(source), "episodes": []}
    for path in episodes:
        number = episode_number(path, pattern)
        assert number is not None
        ass_path = args.subs_dir / f"ep{number:02d}.ass"
        if args.overwrite or not ass_path.exists():
            stream = subtitle_stream_index(path)
            run(
                ["ffmpeg", "-hide_banner", "-y", "-i", str(path), "-map", f"0:s:{stream}", "-c:s", "ass", str(ass_path)],
                print_command=False,
            )
        events = parse_ass(ass_path, number)
        dialogue = [e for e in events if is_dialogue(e)]
        # Sign/note events mark on-screen typesetting — diary screens, captions.
        # This release burns that typesetting in, so those spans are unusable as
        # footage and the selector needs them as avoid-zones.
        signs = [e for e in events if not is_dialogue(e)]
        duration = probe_duration(path)
        index["episodes"].append(
            {
                "episode": number,
                "file": str(path),
                "duration": duration,
                "ass": str(ass_path),
                "event_count": len(events),
                "dialogue_count": len(dialogue),
                "events": [asdict(e) for e in dialogue],
                "signs": [asdict(e) for e in signs],
            }
        )
        print(
            f"ep{number:02d}  {duration/60:5.1f}min  {len(events):4d} events  "
            f"{len(dialogue):4d} dialogue  {len(signs):3d} signs",
            flush=True,
        )

    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    total = sum(e["dialogue_count"] for e in index["episodes"])
    print(f"\nWrote {args.index}  ({len(index['episodes'])} episodes, {total} dialogue events)", flush=True)


if __name__ == "__main__":
    main()
