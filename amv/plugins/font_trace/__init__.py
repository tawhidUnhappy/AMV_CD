"""font_trace: glyph bitmaps -> an .otf (potracer + fontTools), for
`./amv.sh font-trace` (amv.lyric_video.trace_font). Runs in its own uv
environment; the glyphs themselves are cut out of video frames in the light
environment and handed over as one .npz.

    worker.py   job.json -> vectorised CFF font"""

from pathlib import Path

from amv.plugins import Tool, register

register("tool", Tool("font_trace", ("potracer", "fonttools", "numpy"),
                      worker=str(Path(__file__).with_name("worker.py"))))
