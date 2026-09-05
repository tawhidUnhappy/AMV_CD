"""Lyric overlay generation: ASS text/animation styling plus block placement.

`positioning` picks where each block sits (clear of the on-screen subject,
via the shared `amv.vision.skin` heuristic); `ass` builds the ASS document
text; `cli` is the `python -m amv.render.lyric_overlay` entry point.
"""

from __future__ import annotations

from amv.render.lyric_overlay.ass import build_ass
from amv.render.lyric_overlay.cli import main
from amv.render.lyric_overlay.positioning import Position, choose_positions

__all__ = ["build_ass", "main", "Position", "choose_positions"]
