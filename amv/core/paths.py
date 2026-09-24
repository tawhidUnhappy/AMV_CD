"""Every file the pipeline generates, in one place.

All of it lives under tmp/ in the project folder (deleting tmp/ is a clean
slate), and each stage reads what an earlier one wrote - so a path spelled out
in two modules is a path that can drift apart. Modules import these names
instead of joining ROOT / "tmp" / ... themselves.
"""

from __future__ import annotations

import json
from pathlib import Path

from amv.core.config import ROOT

TMP = ROOT / "tmp"

# Song analysis (amv.audio)
SONG_DIR = TMP / "song"
VOCALS = SONG_DIR / "vocals.wav"
TRANSCRIPT = SONG_DIR / "transcript_vocals.json"
TRANSCRIPT_MIX = SONG_DIR / "transcript.json"
WORDS = SONG_DIR / "words_vocals.txt"
BEATS = SONG_DIR / "beats.json"

# Source analysis (amv.subs)
SUBS_DIR = TMP / "subs"
SCENE_INDEX = SUBS_DIR / "scene_index.json"

# The edit and its render (amv.render)
EDL = TMP / "edl.json"
WORK = TMP / "work"
CLIPS = TMP / "clips"
LYRICS_ASS = WORK / "lyrics.ass"
OUT = TMP / "out"
VIDEO = OUT / "amv.mp4"
THUMBNAILS = OUT / "thumbnails"

# Review material (amv.vision, amv.render.*_preview)
QA = TMP / "qa"

# The channel intro (amv.intro), kept apart from the full AMV's files
INTRO = TMP / "intro"


def load_slots(path: Path | None = None) -> list[dict]:
    """The slots of an EDL (tmp/edl.json unless told otherwise)."""
    return json.loads((path or EDL).read_text(encoding="utf-8"))["slots"]


def load_scene_index(path: Path | None = None) -> dict[int, dict]:
    """The subtitle scene index, keyed by episode number."""
    index = json.loads((path or SCENE_INDEX).read_text(encoding="utf-8"))
    return {episode["episode"]: episode for episode in index["episodes"]}
