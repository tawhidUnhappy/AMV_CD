"""Parse an embedded ASS subtitle track into dialogue/sign events.

Split out of extract_subs.py so the ASS-format knowledge (dialogue vs sign
classification, inline override stripping) stands on its own, separate from
the episode-discovery/indexing CLI that uses it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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


def episode_number(path: Path, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(path.name)
    return int(match.group(1)) if match else None
