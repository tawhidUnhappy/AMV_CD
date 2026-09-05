"""Subtitle extraction/indexing and QA tools for the song<->footage sync.

`ass_parser` holds the ASS-format knowledge; `extract_subs` is the CLI that
turns embedded subtitle tracks into `data/subs/scene_index.json`. The rest are
standalone diagnostic scripts (sync offset, lyric-timing, transcript/word
inspection) run individually, so nothing is re-exported here.
"""

from __future__ import annotations
