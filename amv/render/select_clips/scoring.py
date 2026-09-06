"""Usability gating, theme scoring, and the tiny-decode visual metrics.

Split out of the selection CLI so the "how good is this window" scoring is
separate from the "which windows do we even consider" candidate building.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from amv.render.select_clips.themes import BLACKLIST
from amv.vision.skin import skin_mask

if TYPE_CHECKING:
    from amv.render.select_clips.candidates import Candidate

# Coarse grid the head/tail composition signature is reduced to. Deliberately
# tiny: the question is "is the mass in the same part of frame", not "are
# these the same picture", and a fine grid would only ever match a shot
# against itself.
SIG_ROWS, SIG_COLS = 3, 4
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
    """Decode the window tiny and return (brightness, contrast, motion, skin).

    A 96x54 8fps RGB stream is enough to tell a black frame from a face and a
    static shot from a fight, at a fraction of the cost of a real decode.

    `skin` is the fraction of warm, pale, R>G>B pixels — a rough stand-in for
    "a character is on screen". Calibration showed it separates character shots
    (mean 0.30) from scenery and text screens (mean 0.15) on average, but the
    tails overlap: warm food reads as skin, and an unlit night shot reads as
    none. It is therefore weighted, never used as a gate.
    """
    width, height, fps = 96, 54, 8
    filters = f"scale={width}:{height},fps={fps},format=rgb24"
    gpu_command = [
        "ffmpeg", "-hwaccel", "cuda", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", path,
        "-vf", filters, "-f", "rawvideo", "-",
    ]
    cpu_command = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", path,
        "-vf", filters, "-f", "rawvideo", "-",
    ]
    try:
        result = subprocess.run(gpu_command, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        # NVDEC can refuse a handful of streams a software decoder tolerates
        # (an odd profile/level, a corrupt-ish GOP); fall back per-window
        # rather than let one bad clip zero out its whole probe.
        try:
            result = subprocess.run(cpu_command, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            return ShotProbe()
    frame_size = width * height * 3
    count = len(result.stdout) // frame_size
    if count < 2:
        return ShotProbe()
    rgb = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = rgb.reshape(count, height, width, 3).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    skin = skin_mask(rgb)

    luma = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32) / 255.0
    brightness = float(luma.mean())
    contrast = float(luma.std())
    motion = float(np.abs(np.diff(luma, axis=0)).mean())

    # How the shot opens and how it closes, for match cutting (see
    # match_score). A cut reads as continuous when the outgoing frame and the
    # incoming one agree about where the light and the mass sit, so the
    # signature is a coarse GRID of the frame rather than a single average:
    # two shots can share a mean brightness while looking nothing alike.
    span = max(1, round(count * 0.3))
    head, tail = luma[:span], luma[-span:]

    def signature(block) -> np.ndarray:
        frame = block.mean(axis=0)
        rows = np.array_split(frame, SIG_ROWS, axis=0)
        cells = [c.mean() for row in rows for c in np.array_split(row, SIG_COLS, axis=1)]
        return np.array(cells, dtype=np.float32)

    head_motion = float(np.abs(np.diff(head, axis=0)).mean()) if span > 1 else motion
    tail_motion = float(np.abs(np.diff(tail, axis=0)).mean()) if span > 1 else motion
    return ShotProbe(
        brightness=brightness,
        contrast=contrast,
        motion=motion,
        skin=float(skin.mean()),
        head_sig=signature(head).tolist(),
        tail_sig=signature(tail).tolist(),
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
