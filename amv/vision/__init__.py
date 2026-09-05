"""Frame-level analysis: shared colour heuristics plus QA/calibration scripts.

`skin.py` is the one heuristic (skin-tone detection) reused by clip selection,
lyric-block placement and thumbnail face-finding, kept here so those three
call sites can't drift apart. Everything else is a standalone diagnostic
script run individually, so nothing else is re-exported.
"""

from __future__ import annotations
