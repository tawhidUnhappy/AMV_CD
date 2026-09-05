"""Choose where each lyric block sits, keeping clear of the subject's face.

Split out of the ASS-generation code so "where does the text go" (which needs
the EDL and the shared skin heuristic) is separate from "what does the text
look like" (ass.py).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from amv.core.config import ROOT

# Text appears this far ahead of the syllable so it is readable on the beat.
LEAD_IN = 0.18

PROBE_W, PROBE_H = 96, 54


@dataclass(frozen=True)
class Position:
    """Where a lyric block sits. `an` picks which corner `pos` anchors."""

    an: int
    x: int
    y: int
    angle: float = 0.0


# Off-centre placements, matching how the reference moves text around the frame.
POSITIONS: tuple[Position, ...] = (
    Position(6, 1815, 395, -1.2),   # right, upper-middle
    Position(4, 115, 470, 1.0),     # left, middle
    Position(4, 140, 775, -0.8),    # lower left
    Position(6, 1790, 745, 1.2),    # lower right
    Position(4, 125, 300, 0.8),     # upper left
    Position(6, 1800, 560, -1.0),   # right, middle
)


def column_skin(slot: dict):
    """Per-column skin mass for one shot, as a length-PROBE_W array.

    Reuses the skin heuristic from amv.vision.skin as a stand-in for "where
    the character is in frame".
    """
    import numpy as np

    from amv.vision.skin import skin_mask

    command = [
        "ffmpeg", "-v", "error", "-ss", f"{slot['start']:.3f}", "-t", f"{max(slot['duration'], 0.5):.3f}",
        "-i", slot["file"], "-vf", f"scale={PROBE_W}:{PROBE_H},fps=4,format=rgb24", "-f", "rawvideo", "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    frame_size = PROBE_W * PROBE_H * 3
    count = len(result.stdout) // frame_size
    if count == 0:
        return np.zeros(PROBE_W)
    rgb = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = rgb.reshape(count, PROBE_H, PROBE_W, 3).astype(np.int16)
    skin = skin_mask(rgb)
    return skin.mean(axis=(0, 1))


def clearest_side(slots: list[dict]) -> str:
    """Side of frame to put text on, considering EVERY shot the phrase covers.

    A lyric block routinely spans several cuts, and the character is somewhere
    different in each. Sampling only the first shot placed text clear of that
    one face and straight across the next — which is exactly the bug this
    aggregates away. Skin mass is summed over all covered shots, so the chosen
    side is the one that stays clear for the whole time the block is up.
    """
    import numpy as np

    if not slots:
        return "left"
    total = np.zeros(PROBE_W)
    for slot in slots:
        total = total + column_skin(slot)
    third = PROBE_W // 3
    left, right = float(total[:third].sum()), float(total[-third:].sum())
    # Text goes opposite the subject; ties default to the left.
    return "left" if right > left else "right"


def choose_positions(phrases: list, edl: Path | None = None) -> list[Position]:
    """Place each block away from the subject, varying height for rhythm."""
    slots: list[dict] = []
    path = edl or ROOT / "data" / "edl.json"
    if path.exists():
        slots = json.loads(path.read_text(encoding="utf-8"))["slots"]

    def slots_spanning(start: float, end: float) -> list[dict]:
        return [s for s in slots if s["out_start"] < end and s["out_end"] > start]

    left_side = [p for p in POSITIONS if p.an == 4]
    right_side = [p for p in POSITIONS if p.an == 6]

    chosen: list[Position] = []
    counters = {"left": 0, "right": 0}
    for phrase in phrases:
        # The block is on screen slightly before and after the vocal, so judge
        # every shot in that whole window, not just the one at its start.
        covered = slots_spanning(phrase.start - LEAD_IN, phrase.end + 0.3)
        side = clearest_side(covered)
        bank = left_side if side == "left" else right_side
        candidate = bank[counters[side] % len(bank)]
        counters[side] += 1
        if chosen and candidate == chosen[-1]:
            candidate = bank[counters[side] % len(bank)]
            counters[side] += 1
        chosen.append(candidate)
    return chosen
