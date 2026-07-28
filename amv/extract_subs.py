"""Extract the embedded English ASS track from every episode and index its events.

The subtitle track is the pipeline's map of where things *happen* in the source:
each dialogue event is a timestamped, text-labelled moment, which is what the
clip picker searches over instead of blind-sampling the episodes.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from amv.ffmpeg_tools import probe_duration, run, subtitle_stream_index

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path(r"C:\Users\voidn\OneDrive\Documents\Future dairy - Season 1")
DEFAULT_SUBS_DIR = ROOT / "data" / "subs"
DEFAULT_INDEX = ROOT / "data" / "subs" / "scene_index.json"

EPISODE_RE = re.compile(r"Ep-(\d+)")

# ASS inline override blocks {\pos(..)} / {\an8} etc, and drawing commands.
ASS_TAG_RE = re.compile(r"\{[^}]*\}")
ASS_DRAW_RE = re.compile(r"\bm\s+-?\d+\s+-?\d+\s+[lbm]\s", re.IGNORECASE)

# Styles that are signs/titles/credits rather than spoken dialogue. These carry
# no performance, so they make poor AMV cut targets.
NON_DIALOGUE_STYLE_HINTS = ("sign", "title", "caption", "note", "op", "ed", "song", "karaoke", "credit", "staff")


@dataclass
class SceneEvent:
    episode: int
    start: float
    end: float
    text: str
    style: str
    speaker: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_ass_time(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_ass_text(raw: str) -> str:
    text = ASS_TAG_RE.sub("", raw)
    text = text.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_ass(path: Path, episode: int) -> list[SceneEvent]:
    events: list[SceneEvent] = []
    fields: list[str] = []
    section = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()
            continue
        # [V4+ Styles] carries its own Format: line with a different column set,
        # so only the one inside [Events] describes Dialogue rows.
        if stripped.startswith("Format:") and section == "[events]":
            fields = [f.strip() for f in stripped[len("Format:"):].split(",")]
            continue
        if not stripped.startswith("Dialogue:") or not fields:
            continue
        # Only the final field (Text) may contain commas.
        values = stripped[len("Dialogue:"):].split(",", len(fields) - 1)
        if len(values) != len(fields):
            continue
        row = {name: value.strip() for name, value in zip(fields, values)}
        text = clean_ass_text(row.get("Text", ""))
        if not text or ASS_DRAW_RE.search(text):
            continue
        try:
            start = parse_ass_time(row["Start"])
            end = parse_ass_time(row["End"])
        except (KeyError, ValueError):
            continue
        if end <= start:
            continue
        events.append(
            SceneEvent(
                episode=episode,
                start=start,
                end=end,
                text=text,
                style=row.get("Style", ""),
                speaker=row.get("Name", ""),
            )
        )
    events.sort(key=lambda e: e.start)
    return events


def is_dialogue(event: SceneEvent) -> bool:
    style = event.style.lower()
    if any(hint in style for hint in NON_DIALOGUE_STYLE_HINTS):
        return False
    # Fully-uppercase short strings in this release are almost always signage.
    letters = [c for c in event.text if c.isalpha()]
    if len(letters) > 3 and all(c.isupper() for c in letters):
        return False
    return True


def episode_number(path: Path) -> int | None:
    match = EPISODE_RE.search(path.name)
    return int(match.group(1)) if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--subs-dir", type=Path, default=DEFAULT_SUBS_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    args.subs_dir.mkdir(parents=True, exist_ok=True)
    episodes = sorted(
        (p for p in args.source.glob("*.mkv") if episode_number(p) is not None),
        key=lambda p: episode_number(p) or 0,
    )
    if not episodes:
        raise SystemExit(f"No episodes found in {args.source}")

    index: dict = {"source": str(args.source), "episodes": []}
    for path in episodes:
        number = episode_number(path)
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
