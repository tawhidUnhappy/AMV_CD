"""Build the cut schedule: a continuous list of slots covering the whole song.

Cuts land on lyric boundaries so the edit breathes with the vocal, and the
instrumental breaks get rapid-fire cuts for energy. Each slot is later filled
with a source moment by amv/select_clips.py.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from amv.lyrics import song_duration, timed_phrases, validate

# Per-section story arc. Mirai Nikki builds chronologically, so walking the
# episode range forward across the song gives the AMV a shape instead of a
# uniform shuffle.
SECTION_EPISODES: dict[str, tuple[int, int]] = {
    "intro": (1, 3),
    "verse": (1, 5),
    "prechorus": (3, 9),
    "chorus": (4, 11),
    "verse2": (8, 15),
    "prechorus2": (11, 17),
    "chorus2": (12, 19),
    "bridge": (17, 24),
    "finale": (22, 26),
    "outro": (24, 26),
    # One entry per real instrumental break, walking the arc forward with the
    # song. There are seven; clamping them onto fewer labels lumped half the
    # montage into a single episode range.
    "break1": (3, 6),
    "break2": (5, 10),
    "break3": (8, 13),
    "break4": (11, 16),
    "break5": (15, 20),
    "break6": (18, 23),
    "break7": (21, 26),
    "lull": (1, 26),
}

# Longest a single shot may hold before it is split into multiple cuts.
MAX_SHOT = 3.2
# Rapid-cut pace inside instrumental breaks.
BREAK_CUT = 0.75
MIN_SHOT = 0.42
# How far a cut may be nudged to land on a beat. The grid is ~0.348s, so half
# an interval is enough to reach the nearest beat from anywhere.
SNAP_TOLERANCE = 0.19


@dataclass
class Slot:
    index: int
    start: float
    end: float
    section: str
    kind: str  # "lyric" or "break"
    lyric: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


def _split_span(start: float, end: float, target: float) -> list[tuple[float, float]]:
    """Divide a span into equal pieces no longer than `target`."""
    total = end - start
    if total <= 0:
        return []
    # ceil, not round: `target` is a ceiling, so a 4.7s span at target 3.2 must
    # become two cuts rather than staying one over-long shot.
    count = max(1, math.ceil(total / target - 1e-9))
    while count > 1 and total / count < MIN_SHOT:
        count -= 1
    step = total / count
    return [(start + i * step, start + (i + 1) * step) for i in range(count)]


def beat_grid(duration: float) -> list[float]:
    """The song's beat times, padded to cover the whole track."""
    from amv.beats import extend_grid, load

    return extend_grid(load(), duration)


def snap(time: float, grid: list[float], tolerance: float = SNAP_TOLERANCE) -> float:
    """Pull a cut onto the nearest beat when one is close enough."""
    if not grid:
        return time
    index = bisect.bisect_left(grid, time)
    best = time
    best_delta = tolerance
    for candidate in grid[max(0, index - 1) : index + 2]:
        delta = abs(candidate - time)
        if delta < best_delta:
            best, best_delta = candidate, delta
    return best


def build_beat_slots() -> list[Slot]:
    """Lay out cuts on the beat grid.

    Cut points are proposed from the lyric structure, then snapped to beats.
    Lyric *text* timing is generated separately from the vocal alignment, so
    moving a cut by up to ~0.17s never pulls the words off the singing.
    """
    validate()
    phrases = timed_phrases()
    duration = song_duration()
    grid = beat_grid(duration)

    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for phrase in phrases:
        if phrase.start - cursor >= 3.0:
            gaps.append((cursor, phrase.start))
        cursor = phrase.end
    break_section = {start: f"break{i + 1}" for i, (start, _) in enumerate(gaps)}

    # Propose cut points, then let the grid decide exactly where they land.
    proposed: list[float] = [0.0, duration]
    cursor = 0.0
    for phrase in phrases:
        if phrase.start > cursor:
            span = phrase.start - cursor
            step = BREAK_CUT if span >= 3.0 else span
            proposed.extend(a for a, _ in _split_span(cursor, phrase.start, step))
        proposed.extend(a for a, _ in _split_span(phrase.start, phrase.end, MAX_SHOT))
        cursor = phrase.end
    if duration > cursor:
        proposed.extend(a for a, _ in _split_span(cursor, duration, 2.4))

    cuts: list[float] = []
    for time in sorted(set(proposed)):
        snapped = snap(time, grid)
        if not cuts or snapped - cuts[-1] >= MIN_SHOT:
            cuts.append(snapped)
    if cuts[-1] < duration - 1e-6:
        if duration - cuts[-1] < MIN_SHOT:
            cuts[-1] = duration
        else:
            cuts.append(duration)

    def describe(midpoint: float) -> tuple[str, str, str]:
        for phrase in phrases:
            if phrase.start <= midpoint < phrase.end:
                section = phrase.section
                if section in {"verse", "prechorus", "chorus"} and phrase.start > 60:
                    section = f"{section}2"
                return section, "lyric", " / ".join(phrase.lines)
        for start, end in gaps:
            if start <= midpoint < end:
                return break_section[start], "break", ""
        if midpoint >= phrases[-1].end:
            return "outro", "break", ""
        # A short lull between two lines belongs to the section around it.
        following = next((p for p in phrases if p.start > midpoint), phrases[-1])
        section = following.section
        if section in {"verse", "prechorus", "chorus"} and following.start > 60:
            section = f"{section}2"
        return section, "break", ""

    slots: list[Slot] = []
    for start, end in zip(cuts, cuts[1:]):
        section, kind, lyric = describe((start + end) / 2)
        slots.append(Slot(len(slots), start, end, section, kind, lyric))
    return slots


def build_slots() -> list[Slot]:
    try:
        return build_beat_slots()
    except FileNotFoundError:
        print("WARNING: no beat grid found (run amv/beats.py); falling back to vocal-onset cuts", flush=True)
    validate()
    phrases = timed_phrases()
    duration = song_duration()

    # Number the real instrumental breaks in song order so each maps to its own
    # stretch of the episode arc, instead of every later break collapsing onto
    # the same label.
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for phrase in phrases:
        if phrase.start - cursor >= 3.0:
            gaps.append((cursor, phrase.start))
        cursor = phrase.end
    break_section = {start: f"break{i + 1}" for i, (start, _) in enumerate(gaps)}

    slots: list[Slot] = []
    cursor = 0.0

    def add_break(start: float, end: float, neighbour: str) -> None:
        span = end - start
        if span <= 0:
            return
        if span >= 3.0:
            section, target = break_section.get(start, "break1"), BREAK_CUT
        else:
            # A short lull between two lyric lines is still inside that part of
            # the story, so it draws from the same episodes rather than the
            # whole series.
            section, target = neighbour, span
        for a, b in _split_span(start, end, target):
            slots.append(Slot(len(slots), a, b, section, "break"))

    for phrase in phrases:
        section = phrase.section
        # Distinguish repeated sections so the arc keeps moving forward.
        if section in {"verse", "prechorus", "chorus"} and phrase.start > 60:
            section = f"{section}2"
        if phrase.start > cursor:
            add_break(cursor, phrase.start, section)
        for a, b in _split_span(phrase.start, phrase.end, MAX_SHOT):
            slots.append(Slot(len(slots), a, b, section, "lyric", " / ".join(phrase.lines)))
        cursor = phrase.end

    if duration > cursor:
        # Final instrumental tail: let it breathe rather than machine-gun it.
        for a, b in _split_span(cursor, duration, 2.4):
            slots.append(Slot(len(slots), a, b, "outro", "break"))

    slots = _absorb_slivers(slots)
    for i, slot in enumerate(slots):
        slot.index = i
    return slots


def _absorb_slivers(slots: list[Slot]) -> list[Slot]:
    """Fold sub-MIN_SHOT slots into a neighbour.

    The timeline has to stay gapless — clips are concatenated — so a sliver is
    merged into the adjacent slot rather than dropped.
    """
    merged: list[Slot] = []
    for slot in slots:
        if slot.duration < MIN_SHOT and merged:
            merged[-1].end = slot.end
            continue
        merged.append(slot)
    # A sliver in first position has no predecessor to fold into; give it to the
    # following slot instead.
    while len(merged) > 1 and merged[0].duration < MIN_SHOT:
        merged[1].start = merged[0].start
        merged.pop(0)
    return merged


def main() -> None:
    slots = build_slots()
    total = sum(s.duration for s in slots)
    print(f"{len(slots)} slots, {total:.2f}s total (song {song_duration():.2f}s)\n")
    for s in slots:
        label = s.lyric or "-"
        print(f"{s.index:3d} [{s.start:7.2f} -> {s.end:7.2f}] {s.duration:4.2f}s {s.kind:6s} {s.section:10s} {label}")
    from collections import Counter

    print("\nper-section slot counts:", dict(Counter(s.section for s in slots)))
    print(f"shortest {min(s.duration for s in slots):.2f}s  longest {max(s.duration for s in slots):.2f}s")


if __name__ == "__main__":
    main()
