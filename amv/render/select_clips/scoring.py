"""Usability gating, theme scoring, and the tiny-decode visual metrics.

Split out of the selection CLI so the "how good is this window" scoring is
separate from the "which windows do we even consider" candidate building.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from amv.render.select_clips.themes import BLACKLIST
from amv.vision.decode import decode_tiny, grid_signature, luma
from amv.vision.skin import skin_mask

if TYPE_CHECKING:
    from amv.render.select_clips.candidates import Candidate

# Ceiling on the match-cut term, in the same units as the visual score
# (which spans roughly 0-40).
MATCH_WEIGHT = 14.0


@dataclass
class ShotProbe:
    """Everything the tiny decode measures about one candidate window."""

    brightness: float = 0.0
    contrast: float = 0.0
    motion: float = 0.0
    skin: float = 0.0
    #: Coarse luma grid over the opening / closing frames, for match cutting.
    head_sig: list[float] = field(default_factory=list)
    tail_sig: list[float] = field(default_factory=list)
    head_motion: float = 0.0
    tail_motion: float = 0.0

# Trim episode head/tail: studio logos, "previously on", and — the big one —
# the post-ED "Murmur's Counseling Room" omake plus the next-episode preview,
# which together occupy roughly the last minute and a half. A 25s tail let SD
# comedy segments and title cards into the edit.
HEAD_SKIP = 12.0
TAIL_SKIP = 95.0
# A dialogue-free stretch this long is the OP or ED credit sequence.
CREDITS_GAP = 80.0
# Keep picks apart so the same shot never appears twice.
MIN_SEPARATION = 9.0

WORD_RE = re.compile(r"[a-z']+")


def credits_zones(episode: dict) -> list[tuple[float, float]]:
    """OP/ED spans, found as very long dialogue-free stretches."""
    zones: list[tuple[float, float]] = []
    events = episode["events"]
    for prev, nxt in zip(events, events[1:]):
        if nxt["start"] - prev["end"] >= CREDITS_GAP:
            zones.append((prev["end"], nxt["start"]))
    return zones


# Song zones: a subtitled OP/ED has no dialogue-free gap for credits_zones to
# find (this release subtitles the opening song's lyrics), but its lines
# repeat from episode to episode where dialogue does not. Measured on
# Mushoku Tensei S1: word 3-grams shared with 2+ other episodes, on lines
# held 4s+ on average, found the OP in 14 of 24 episodes and the ED in 22;
# 4-grams missed ep12's OP, whose OCR differs from episode to episode.
SONG_NGRAM = 3
SONG_MIN_LINES = 3
SONG_MIN_SPAN = 30.0
SONG_MIN_LINE_SECONDS = 4.0
SONG_LINE_GAP = 25.0
# The picture runs before the first sung line and after the last.
SONG_PAD_BEFORE, SONG_PAD_AFTER = 12.0, 18.0


def _grams(text: str) -> set[str]:
    words = WORD_RE.findall(text.lower().replace("'", ""))
    return {" ".join(words[i:i + SONG_NGRAM]) for i in range(len(words) - SONG_NGRAM + 1)}


def song_zones(episodes: dict[int, dict]) -> dict[int, list[tuple[float, float]]]:
    """OP/ED spans found as runs of subtitle lines repeated across episodes.

    Complements credits_zones rather than replacing it: an unsubtitled song is
    a gap, a subtitled one is a repeat, and a release can have both. A false
    positive only costs a few candidate windows."""
    seen_in: dict[str, set[int]] = {}
    for number, episode in episodes.items():
        for event in episode["events"]:
            for gram in _grams(event["text"]):
                seen_in.setdefault(gram, set()).add(number)

    zones: dict[int, list[tuple[float, float]]] = {}
    for number, episode in episodes.items():
        runs: list[list[dict]] = []
        for event in episode["events"]:
            grams = _grams(event["text"])
            shared = sum(1 for g in grams if len(seen_in[g] - {number}) >= 2)
            if len(grams) < 2 or shared / len(grams) < 0.5:
                continue
            if runs and event["start"] - runs[-1][-1]["end"] < SONG_LINE_GAP:
                runs[-1].append(event)
            else:
                runs.append([event])
        zones[number] = [
            (run[0]["start"] - SONG_PAD_BEFORE, run[-1]["end"] + SONG_PAD_AFTER)
            for run in runs
            if len(run) >= SONG_MIN_LINES
            and run[-1]["end"] - run[0]["start"] >= SONG_MIN_SPAN
            and sum(e["end"] - e["start"] for e in run) / len(run) >= SONG_MIN_LINE_SECONDS
        ]
    return zones


def usable(episode: dict, start: float, duration: float, zones: list[tuple[float, float]]) -> bool:
    end = start + duration
    if start < HEAD_SKIP or end > episode["duration"] - TAIL_SKIP:
        return False
    number = episode["episode"]
    for ep, b_start, b_end in BLACKLIST:
        if ep == number and start < b_end and end > b_start:
            return False
    return not any(start < z_end and end > z_start for z_start, z_end in zones)


def is_diary_reading(event: dict) -> bool:
    """Lines that quote a diary entry play over a full-screen phone graphic.

    That typesetting is burned into this release, so those shots are a wall of
    text — useless as footage and unreadable once graded and overlaid.
    """
    text = event["text"]
    return '"' in text or text.startswith("(") or "「" in text


def theme_score(event: dict, keywords: tuple[str, ...], speaker: str | None) -> float:
    score = 0.0
    words = set(WORD_RE.findall(event["text"].lower()))
    hits = sum(1 for k in keywords if k in words)
    score += hits * 3.0
    # Substring fallback catches inflections ("killed" for "kill").
    lowered = event["text"].lower()
    score += sum(0.8 for k in keywords if k not in words and k in lowered)
    if speaker and event["speaker"] == speaker:
        score += 2.5
    return score


def probe_stats(path: str, start: float, duration: float) -> ShotProbe:
    """Decode the window tiny and measure brightness, contrast, motion, skin
    and the head/tail signatures match_score compares.

    A 96x54 8fps RGB stream is enough to tell a black frame from a face and a
    static shot from a fight, at a fraction of the cost of a real decode.

    `skin` is the fraction of warm, pale, R>G>B pixels — a rough stand-in for
    "a character is on screen". Calibration showed it separates character shots
    (mean 0.30) from scenery and text screens (mean 0.15) on average, but the
    tails overlap: warm food reads as skin, and an unlit night shot reads as
    none. It is therefore weighted, never used as a gate.
    """
    rgb = decode_tiny(path, 96, 54, start=start, duration=duration, fps=8)
    count = len(rgb)
    if count < 2:
        return ShotProbe()
    frames = luma(rgb)
    motion = float(np.abs(np.diff(frames, axis=0)).mean())

    # How the shot opens and how it closes, for match cutting (see
    # match_score). A cut reads as continuous when the outgoing frame and the
    # incoming one agree about where the light and the mass sit, so the
    # signature is a coarse GRID of the frame rather than a single average:
    # two shots can share a mean brightness while looking nothing alike.
    span = max(1, round(count * 0.3))
    head, tail = frames[:span], frames[-span:]
    head_motion = float(np.abs(np.diff(head, axis=0)).mean()) if span > 1 else motion
    tail_motion = float(np.abs(np.diff(tail, axis=0)).mean()) if span > 1 else motion
    return ShotProbe(
        brightness=float(frames.mean()),
        contrast=float(frames.std()),
        motion=motion,
        skin=float(skin_mask(rgb.astype(np.int16)).mean()),
        head_sig=grid_signature(head),
        tail_sig=grid_signature(tail),
        head_motion=head_motion,
        tail_motion=tail_motion,
    )


def match_score(prev: "Candidate | None", cand: "Candidate") -> float:
    """How well `cand` cuts on from `prev` — the match-cut term.

    Continuity editing says a cut disappears when the incoming shot picks up
    what the outgoing one put down: comparable composition, comparable light,
    comparable energy. Cutting from a bright wide to a dark close-up, or from
    a fast pan to a locked-off frame, announces itself as a cut.

    So this compares the END of the previous shot with the START of this one:
      - graphic match — how closely the two coarse luma grids agree, which
        stands in for "the mass is in the same part of frame";
      - light match   — how close the two average brightnesses are;
      - energy match  — whether motion carries across rather than stalling.

    Returns roughly 0 (jarring) to MATCH_WEIGHT (seamless).
    """
    import numpy as np

    if prev is None or not prev.tail_sig or not cand.head_sig:
        return 0.0
    tail = np.array(prev.tail_sig, dtype=np.float32)
    head = np.array(cand.head_sig, dtype=np.float32)

    # RMS difference across the grid, 0 (identical) to ~1 (inverse).
    graphic = float(np.sqrt(((tail - head) ** 2).mean()))
    light = abs(float(tail.mean()) - float(head.mean()))
    energy = abs(prev.tail_motion - cand.head_motion)

    score = 0.0
    score += 0.55 * max(0.0, 1.0 - graphic / 0.28)
    score += 0.25 * max(0.0, 1.0 - light / 0.22)
    score += 0.20 * max(0.0, 1.0 - energy / 0.05)
    return MATCH_WEIGHT * score


# Minimum source brightness a window may have and still be selectable.
#
# This gate is measured on *ungraded* source, but what matters is how the shot
# looks after the grade, which darkens (contrast 1.17 plus an S-curve). At the
# old 0.10 floor, shots passing at 0.10-0.14 landed under 0.08 once graded:
# with story-ordered selection pulling the montages into the darker back half
# of the season, near-black runtime hit 14.5% against a ~4% target, and
# lifting the grade to compensate barely moved it (14.5% -> 14.0%) because the
# footage itself is dark. Rejecting it here works; rescuing it later does not.
MIN_BRIGHTNESS = 0.16


def visual_score(brightness: float, contrast: float, motion: float, skin: float, want_motion: bool) -> float:
    # Reject fades to black/white outright — they read as a dropout mid-cut.
    if brightness < MIN_BRIGHTNESS or brightness > 0.92:
        return -50.0
    if contrast < 0.055:
        return -25.0
    score = 0.0
    # Mid-range exposure is what grades best once crushed to grayscale.
    score += 6.0 * (1.0 - min(1.0, abs(brightness - 0.45) / 0.45))
    score += 10.0 * min(1.0, contrast / 0.22)
    # Break slots want kinetic footage; lyric slots want a readable, calmer
    # frame the text can sit on top of.
    if want_motion:
        score += 16.0 * min(1.0, motion / 0.055)
        score += 7.0 * min(1.0, skin / 0.30)
    else:
        score += 9.0 * min(1.0, motion / 0.030)
        if motion > 0.10:
            score -= 6.0
        # Lyric lines want a face to land on, so weight character presence harder.
        score += 14.0 * min(1.0, skin / 0.30)
    return score
