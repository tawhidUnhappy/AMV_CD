"""Build the cut schedule: a continuous list of slots covering the whole song.

Cuts land on lyric boundaries so the edit breathes with the vocal, and the
instrumental breaks get rapid-fire cuts for energy. Each slot is later filled
with a source moment by amv/render/select_clips.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from amv.audio.lyrics import song_duration, timed_phrases, validate

# Per-section story arc, deliberately curated against Mushoku Tensei S1's
# real chronology rather than an even split of 24 episodes -- see
# amv-clip-selection for the narrative reasoning behind each range. Rip A
# (unsuffixed sections) plays first and closes unresolved ("...why"); rip B
# ("_2" sections) plays second and closes on the title hook. The arc walks
# forward across BOTH passes, so the story keeps advancing into rip B rather
# than restarting -- see amv/audio/lyrics.py for why the song itself repeats.
SECTION_EPISODES: dict[str, tuple[int, int]] = {
    # Rip A: birth, early identity confusion, first loss and isolation.
    "intro": (1, 1),           # birth/rebirth -- "lost in my head again"
    "verse1": (1, 3),          # first days in the new life
    "prechorus": (2, 4),
    "chorus1": (3, 6),         # early magic training under Roxy
    "verse2": (5, 8),          # isolation, guilt over the old life
    "chorus2": (7, 10),        # leads into the family rupture
    # Rip B: the journey -- literal demons, real growth, real resolution.
    "intro2": (10, 12),        # the family splits; the journey begins
    "verse1_2": (11, 14),
    "prechorus2": (13, 16),
    "chorus1_2": (15, 18),     # danger on the road, the Superd arc
    "verse2_2": (17, 20),      # hardship, what he's carrying
    "chorus2_2": (20, 24),     # growth and resolution -- the closing hook
    # Instrumental breaks, one entry per real gap (there are six, not the
    # four in the previous song order -- this song has three separate
    # instrumental stretches around its "yeah, yeah" bridge, not one).
    "break1": (1, 1),          # opening: see OPEN_CUT below -- kept calm on purpose
    "break2": (5, 7),          # mid rip A, between chorus 1 and verse 2
    "break3": (8, 9),          # rip A trailing off into the bridge
    "break4": (9, 10),         # the bridge itself -- the hinge into rip B
    "break5": (10, 11),        # short breath just before rip B's intro
    "break6": (22, 23),        # rip B's final instrumental before the fade
    "bridge": (9, 11),        # the "yeah, yeah" ad-lib between the two rips
    "lull": (1, 24),
}

# Cut pacing, in seconds. The detected beat grid is ~0.418s, but that is a
# subdivision lock: the track is really ~68 BPM (0.836s), and beat_track found
# the eighths. Cutting on every grid unit therefore machine-guns a slow,
# sombre song. These are all multiples of the grid instead (see
# amv-beat-cutting: any consistent subdivision is valid, pick the cut spacing
# as a multiple of it).
#
# The floor matters more than usual here because the source is anime, which is
# animated on twos or threes — 8-12 unique drawings a second. An earlier
# 0.42s floor meant shots holding only 4-5 distinct drawings, and cutting that
# fast between them reads as stutter rather than as energy. 1.05s (~25 frames)
# gives every shot enough drawings to register as motion.
MAX_SHOT = 4.6          # ~11 grid units; lets an emotional line linger
BREAK_CUT = 1.67        # 4 grid units — instrumental breaks still cut faster
MIN_SHOT = 1.05         # ~2.5 grid units
TAIL_CUT = 3.34         # 8 grid units — the closing instrumental breathes
# The very first gap (before any vocal) used BREAK_CUT like every other
# instrumental, which for this song's 8.1s intro meant ~5 hard cuts of
# unrelated establishing shots in the first moment a viewer sees the edit --
# read as channel-surfing before the video had even started. An opener needs
# to earn the cut, not spend its only impression proving the edit can cut
# fast. One slower target instead: 1-2 shots, letting the viewer settle into
# the tone before BREAK_CUT's energy kicks in at the first real break.
OPEN_CUT = 4.2
# How far a cut may be nudged to land on a beat. The grid is ~0.418s, so half
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
    from amv.audio.beats import extend_grid, load

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
            if span < 3.0:
                step = span
            elif cursor == 0.0:
                step = OPEN_CUT
            else:
                step = BREAK_CUT
            proposed.extend(a for a, _ in _split_span(cursor, phrase.start, step))
        proposed.extend(a for a, _ in _split_span(phrase.start, phrase.end, MAX_SHOT))
        cursor = phrase.end
    if duration > cursor:
        proposed.extend(a for a, _ in _split_span(cursor, duration, TAIL_CUT))

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
                return phrase.section, "lyric", " / ".join(phrase.lines)
        for start, end in gaps:
            if start <= midpoint < end:
                return break_section[start], "break", ""
        if midpoint >= phrases[-1].end:
            return "chorus2_2", "break", ""
        # A short lull between two lines belongs to the section around it.
        following = next((p for p in phrases if p.start > midpoint), phrases[-1])
        return following.section, "break", ""

    slots: list[Slot] = []
    for start, end in zip(cuts, cuts[1:]):
        section, kind, lyric = describe((start + end) / 2)
        slots.append(Slot(len(slots), start, end, section, kind, lyric))
    return slots


def build_slots() -> list[Slot]:
    try:
        return build_beat_slots()
    except FileNotFoundError:
        print("WARNING: no beat grid found (run amv/audio/beats.py); falling back to vocal-onset cuts", flush=True)
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
            section = break_section.get(start, "break1")
            target = OPEN_CUT if start == 0.0 else BREAK_CUT
        else:
            # A short lull between two lyric lines is still inside that part of
            # the story, so it draws from the same episodes rather than the
            # whole series.
            section, target = neighbour, span
        for a, b in _split_span(start, end, target):
            slots.append(Slot(len(slots), a, b, section, "break"))

    for phrase in phrases:
        section = phrase.section
        if phrase.start > cursor:
            add_break(cursor, phrase.start, section)
        for a, b in _split_span(phrase.start, phrase.end, MAX_SHOT):
            slots.append(Slot(len(slots), a, b, section, "lyric", " / ".join(phrase.lines)))
        cursor = phrase.end

    if duration > cursor:
        # Final instrumental tail: let it breathe rather than machine-gun it.
        for a, b in _split_span(cursor, duration, TAIL_CUT):
            slots.append(Slot(len(slots), a, b, "chorus2_2", "break"))

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
