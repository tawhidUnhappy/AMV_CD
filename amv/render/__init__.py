"""The editing/rendering side of the pipeline.

`timeline` builds the cut schedule, `select_clips` fills it from the source
footage, `lyric_overlay` builds the burned-in ASS lyrics, `grade` holds the
colour-grade/focus-mask filter knowledge, and `pipeline` is the
encode/concat/mux CLI (`python -m amv.render.pipeline`) that ties grading and
the EDL together into the final video. `grade_preview` and `font_compare` are
standalone tuning scripts.
"""

from __future__ import annotations
