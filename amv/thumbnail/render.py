"""Render one `Thumb` composition to a JPEG via ffmpeg + libass."""

from __future__ import annotations

import subprocess
from pathlib import Path

from amv.core.config import ROOT
from amv.thumbnail.ass import build_ass
from amv.thumbnail.fonts import stage_fonts
from amv.thumbnail.layout import HEIGHT, WIDTH, Thumb


def render(thumb: Thumb, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = ROOT / "tmp" / "work"
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / f"thumb_{thumb.name}.ass"
    ass_path.write_text(build_ass(thumb), encoding="utf-8")

    fonts = stage_fonts()
    ass_arg = ass_path.resolve().as_posix().replace(":", "\\:")
    fonts_arg = fonts.resolve().as_posix().replace(":", "\\:")
    output = out_dir / f"{thumb.name}.jpg"

    if thumb.right_source is not None:
        # Side-by-side: two half-width crops with a hard divider.
        half = WIDTH // 2

        def panel(index: int, zoom: float, shift: float, vshift: float) -> str:
            w, h = int(WIDTH * zoom), int(HEIGHT * zoom)
            return (
                f"[{index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={half}:{HEIGHT}:(iw-{half})*{shift:.3f}:(ih-{HEIGHT})*{vshift:.3f},"
                f"{thumb.grade}"
            )

        graph = (
            f"{panel(0, thumb.left_zoom, thumb.left_shift, thumb.left_vshift)}[l];"
            f"{panel(1, thumb.right_zoom, thumb.right_shift, thumb.right_vshift)}[r];"
            f"[l][r]hstack=inputs=2,"
            f"drawbox=x={half - 4}:y=0:w=8:h={HEIGHT}:color=black@1:t=fill,"
            f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'[v]"
        )
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(thumb.source), "-i", str(thumb.right_source),
            "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "2", str(output),
        ]
    else:
        graph = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},{thumb.grade},"
            f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'"
        )
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(thumb.source),
            "-vf", graph, "-frames:v", "1", "-q:v", "2", str(output),
        ]
    subprocess.run(command, check=True)
    return output
