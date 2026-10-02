"""Per-lyric keyword search terms, named speakers and the regions rejected on
sight - the active project's (amv.core.project: "themes", "main_speakers",
"blacklist"), kept apart from the scoring/candidate code that consumes them.

THEMES keys are the joined display lines of the lyric plan. Choose search
terms against the real dialogue (workspace/tmp/subs/scene_index.json), not synonyms.
An empty MAIN_SPEAKERS means "any dialogue line" (bitmap/OCR subtitles carry
no speaker names).
"""

from __future__ import annotations

from amv.core import project

_PROJECT = project.optional()

MAIN_SPEAKERS: set[str] = set(_PROJECT.get("main_speakers", []))

# (episode, start, end)
BLACKLIST: tuple[tuple[int, float, float], ...] = tuple(
    (int(r["episode"]), float(r["start"]), float(r["end"])) for r in _PROJECT.get("blacklist", []))

THEMES: dict[str, tuple[tuple[str, ...], str | None]] = {
    line: (tuple(t.get("keywords", ())), t.get("speaker")) for line, t in _PROJECT.get("themes", {}).items()}
