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
from amv.core.ffmpeg_tools import BITMAP_SUBTITLE_CODECS, probe_duration, run, subtitle_stream_index
from amv.subs.ass_parser import episode_number, is_dialogue, parse_ass
from amv.subs.pgs_ocr import extract_events as extract_pgs_events

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
    parser.add_argument(
        "--episodes", default=None,
        help="Limit to these episode numbers, e.g. '1-5,10,15,20,24'. "
             "STRONGLY recommended when subtitles are PGS/bitmap: OCR is minutes "
             "per episode (a GPU model pass per line), not the near-free ffmpeg "
             "text-track conversion. Don't OCR the whole series — pick episodes "
             "from the story-arc plan you're mapping song sections onto (see "
             "amv-clip-selection) before running this. Ignored for text-subtitle "
             "releases, where extracting everything costs nothing.",
    )
    args = parser.parse_args()

    source = args.source or cfg.require_source()
    pattern = re.compile(args.episode_pattern, re.IGNORECASE)
    wanted = _parse_episode_ranges(args.episodes) if args.episodes else None

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
    if wanted is not None:
        episodes = [p for p in episodes if episode_number(p, pattern) in wanted]
        missing = wanted - {episode_number(p, pattern) for p in episodes}
        if missing:
            print(f"NOTE: --episodes asked for {sorted(missing)}, no matching file found", flush=True)

    if wanted is None and len(episodes) > 6:
        # Cheap probe (one episode) to decide whether a whole-series run is
        # about to be expensive. Releases are near-always uniform in codec
        # across episodes, so the first one is representative.
        _, probe_codec = subtitle_stream_index(episodes[0].resolve())
        if probe_codec in BITMAP_SUBTITLE_CODECS:
            print(
                f"WARNING: {len(episodes)} episodes with PGS/bitmap subtitles and no --episodes "
                f"filter — this OCRs every one of them (minutes per episode, not the near-free "
                f"text-track path). Pick episodes from your story-arc plan first: "
                f"--episodes '1-5,10,15,20,24'. See amv-clip-selection.",
                flush=True,
            )

    # Merge into any existing index rather than overwrite it, so running a
    # small --episodes subset (e.g. topping up OCR coverage) doesn't discard
    # episodes indexed in a previous run.
    index: dict = {"source": str(source), "episodes": []}
    by_episode: dict[int, dict] = {}
    if args.index.exists():
        try:
            previous = json.loads(args.index.read_text(encoding="utf-8"))
            by_episode = {e["episode"]: e for e in previous.get("episodes", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    for path in episodes:
        number = episode_number(path, pattern)
        assert number is not None
        stream, codec = subtitle_stream_index(path)
        if codec in BITMAP_SUBTITLE_CODECS:
            # Bitmap subtitles (PGS/VobSub) have no text for ffmpeg to convert
            # to ASS — decode + OCR instead. See amv/subs/pgs_ocr.py.
            sup_path = args.subs_dir / f"ep{number:02d}.sup"
            if args.overwrite or not sup_path.exists():
                run(
                    ["ffmpeg", "-hide_banner", "-y", "-i", str(path), "-map", f"0:s:{stream}", "-c:s", "copy",
                     str(sup_path)],
                    print_command=False,
                )
            ocr_work_dir = args.subs_dir / "ocr" / f"ep{number:02d}"
            events = extract_pgs_events(sup_path, number, ocr_work_dir)
            subs_source = str(sup_path)
        else:
            ass_path = args.subs_dir / f"ep{number:02d}.ass"
            if args.overwrite or not ass_path.exists():
                run(
                    ["ffmpeg", "-hide_banner", "-y", "-i", str(path), "-map", f"0:s:{stream}", "-c:s", "ass",
                     str(ass_path)],
                    print_command=False,
                )
            events = parse_ass(ass_path, number)
            subs_source = str(ass_path)
        dialogue = [e for e in events if is_dialogue(e)]
        # Sign/note events mark on-screen typesetting — diary screens, captions.
        # This release burns that typesetting in, so those spans are unusable as
        # footage and the selector needs them as avoid-zones.
        signs = [e for e in events if not is_dialogue(e)]
        duration = probe_duration(path)
        by_episode[number] = {
            "episode": number,
            "file": str(path),
            "duration": duration,
            "subs_source": subs_source,
            "event_count": len(events),
            "dialogue_count": len(dialogue),
            "events": [asdict(e) for e in dialogue],
            "signs": [asdict(e) for e in signs],
        }
        print(
            f"ep{number:02d}  {duration/60:5.1f}min  {len(events):4d} events  "
            f"{len(dialogue):4d} dialogue  {len(signs):3d} signs",
            flush=True,
        )

    index["episodes"] = [by_episode[n] for n in sorted(by_episode)]
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    total = sum(e["dialogue_count"] for e in index["episodes"])
    print(f"\nWrote {args.index}  ({len(index['episodes'])} episodes indexed, {total} dialogue events)", flush=True)


def _parse_episode_ranges(spec: str) -> set[int]:
    """Parse '1-5,10,15,20,24' into {1,2,3,4,5,10,15,20,24}."""
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(part))
    return result


if __name__ == "__main__":
    main()
