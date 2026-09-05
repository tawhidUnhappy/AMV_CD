"""Build the ASS document text for one thumbnail's text/arrow/bubble overlay."""

from __future__ import annotations

from amv.thumbnail.colors import BLACK, WHITE, YELLOW
from amv.thumbnail.fonts import LABEL_FONT
from amv.thumbnail.layout import HEIGHT, WIDTH, Thumb
from amv.thumbnail.shapes import arrow_shape, bubble_shape


def build_ass(thumb: Thumb) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: L,{LABEL_FONT},96,{YELLOW},{YELLOW},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,11,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = [header]
    for bubble in thumb.bubbles:
        rows.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\org({bubble.x},{bubble.y})\\frz{-bubble.angle}\\c{bubble.fill}"
            f"\\3c{WHITE}\\bord5\\shad0\\p1}}{bubble_shape(bubble)}{{\\p0}}"
        )
    for arrow in thumb.arrows:
        # Drawings honour \frz, so one shape serves every direction.
        ax, ay, angle = arrow.resolve()
        rows.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an5\\pos({ax},{ay})\\frz{-angle}\\c{arrow.colour}"
            f"\\3c{BLACK}\\bord6\\p1}}{arrow_shape(arrow.scale)}{{\\p0}}"
        )
    for text in thumb.texts:
        outline = text.outline if text.outline is not None else round(text.size * 0.12, 1)
        body = text.body.replace("\n", "\\N")
        rows.append(
            f"Dialogue: 1,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an{text.an}\\pos({text.x},{text.y})\\fn{text.font}\\fs{text.size}"
            f"\\frz{-text.angle}\\c{text.colour}\\3c{BLACK}\\bord{outline}\\shad0}}{body}"
        )
    return "\n".join(rows) + "\n"
