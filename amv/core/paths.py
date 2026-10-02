"""Every file the pipeline generates or keeps, in one place.

Generated files live under workspace/tmp/ (deleting it is a clean slate), and each
stage reads what an earlier one wrote - so a path spelled out in two modules
is a path that can drift apart. Modules import these names instead of
joining a tmp path themselves.

Your own work (specs, picks, the catalog) lives under workspace/global/ -
gitignored; config.json "workspace_dir" moves the whole workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

from amv.core.config import load

TMP = load().tmp_dir
GLOBAL = load().global_dir

# Shorts (amv.shorts): your specs and what earlier builds learned
SHORT_SPECS = GLOBAL / "shorts" / "specs"
SHORTS_CATALOG = GLOBAL / "shorts" / "catalog"

# Intros (amv.intro): hand-picked shot lists, montage/remake specs, rejects
INTRO_PICKS = GLOBAL / "intro" / "picks"
INTRO_MONTAGES = GLOBAL / "intro" / "montages"
INTRO_REMAKES = GLOBAL / "intro" / "remakes"
INTRO_BLACKLIST = GLOBAL / "intro" / "blacklist.json"

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
    """The slots of an EDL (workspace/tmp/edl.json unless told otherwise)."""
    return json.loads((path or EDL).read_text(encoding="utf-8"))["slots"]


def load_scene_index(path: Path | None = None) -> dict[int, dict]:
    """The subtitle scene index, keyed by episode number."""
    index = json.loads((path or SCENE_INDEX).read_text(encoding="utf-8"))
    return {episode["episode"]: episode for episode in index["episodes"]}
