"""Clip selection: fills every timeline slot with a scored source moment.

Split into `themes` (hand-tuned keyword/speaker/blacklist data), `scoring`
(usability gating, theme scoring, tiny-decode visual metrics) and
`candidates` (the per-slot shortlist builder), with `cli` as the
`python -m amv.render.select_clips` entry point tying them together.
"""

from __future__ import annotations

from amv.render.select_clips.candidates import Candidate, build_candidates
from amv.render.select_clips.cli import main

__all__ = ["Candidate", "build_candidates", "main"]
