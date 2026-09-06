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


# Two placements, both centred, no rotation.
#
# An earlier version scattered blocks across six off-centre anchors at ±1°
# angles and cycled heights within a side "for rhythm". On a slow, sombre
# lyric track that reads as chaotic: the eye has to re-find the text on every
# block, and tilted text over anime linework looks like a mistake rather than
# a choice. A lyric video wants the words in the same place every time, so the
# viewer reads them without looking for them.
#
# Bottom-centre is the default and wins nearly always — anime framing puts
# faces in the upper-middle. Top-centre is the escape hatch for the shots
# where the subject genuinely sits low in frame.
BOTTOM_CENTRE = Position(2, 960, 940)
TOP_CENTRE = Position(8, 960, 140)
POSITIONS: tuple[Position, ...] = (BOTTOM_CENTRE, TOP_CENTRE)


def row_skin(slot: dict):
    """Per-row skin mass for one shot, as a length-PROBE_H array.

    Reuses the skin heuristic from amv.vision.skin as a stand-in for "where
    the character is in frame". Rows, not columns, because placement is now
    a top-vs-bottom decision (see POSITIONS).
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
        return np.zeros(PROBE_H)
    rgb = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = rgb.reshape(count, PROBE_H, PROBE_W, 3).astype(np.int16)
    skin = skin_mask(rgb)
    return skin.mean(axis=(0, 2))


def clearest_band(slots: list[dict]) -> str:
    """Band of frame to put text in, considering EVERY shot the phrase covers.

    A lyric block routinely spans several cuts, and the character is somewhere
    different in each. Sampling only the first shot placed text clear of that
    one face and straight across the next — which is exactly the bug this
    aggregates away. Skin mass is summed over all covered shots, so the chosen
    band is the one that stays clear for the whole time the block is up.

    Biased toward the bottom: moving the text is more disruptive than a
    partial overlap, so the top is only chosen when the bottom is clearly
    the busier band.
    """
    import numpy as np

    if not slots:
        return "bottom"
    total = np.zeros(PROBE_H)
    for slot in slots:
        total = total + row_skin(slot)
    third = PROBE_H // 3
    top, bottom = float(total[:third].sum()), float(total[-third:].sum())
    return "top" if bottom > top * 1.6 else "bottom"


def choose_positions(phrases: list, edl: Path | None = None) -> list[Position]:
    """Place every block bottom-centre, lifting to the top only when needed."""
    slots: list[dict] = []
    path = edl or ROOT / "tmp" / "edl.json"
    if path.exists():
        slots = json.loads(path.read_text(encoding="utf-8"))["slots"]

    def slots_spanning(start: float, end: float) -> list[dict]:
        return [s for s in slots if s["out_start"] < end and s["out_end"] > start]

    chosen: list[Position] = []
    for phrase in phrases:
        # The block is on screen slightly before and after the vocal, so judge
        # every shot in that whole window, not just the one at its start.
        covered = slots_spanning(phrase.start - LEAD_IN, phrase.end + 0.3)
        chosen.append(TOP_CENTRE if clearest_band(covered) == "top" else BOTTOM_CENTRE)
    return chosen
