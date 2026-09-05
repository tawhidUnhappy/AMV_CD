"""Build the burned-in lyric overlay ASS document text.

Style follows the reference look: a stacked 2-3 line block in uppercase Kranky,
white with a heavy drop shadow, with exactly one word per phrase in red. Blocks
sit off-centre and move around the frame between lines rather than sitting in a
fixed subtitle position. Where each block sits comes from positioning.py.
"""

from __future__ import annotations

from amv.audio.lyrics import TimedPhrase
from amv.core import config
from amv.render.lyric_overlay.positioning import LEAD_IN, choose_positions

_CFG = config.load()
WIDTH, HEIGHT = _CFG.width, _CFG.height
# Font comes from config.json. Prefer a solid, high-contrast face: an *outline*
# typeface (hollow strokes) washes out completely over footage — see the skill
# notes. The file is copied into assets/ so libass resolves it through
# `fontsdir` rather than depending on system font configuration.
FONT_NAME = _CFG.lyric_font_family
FONT_BOLD = -1 if _CFG.lyric_font_bold else 0

# ASS colours are &HAABBGGRR — byte order is reversed from hex RGB.
WHITE = "&H00F2F2F2&"
RED = "&H002222CC&"  # rgb(204, 34, 34)

# Blocks resolve out of a haze instead of hard-cutting in; a little blur is kept
# at rest so the edges stay soft now that the drop shadow is gone.
ENTRY_BLUR = 12
REST_BLUR = 0.9
EXIT_BLUR = 9


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def font_size(phrase: TimedPhrase) -> int:
    """Pick the largest size that still clears the safe margins.

    The reference sets lyrics big enough to dominate the frame; the first pass
    was roughly half this and read as ordinary subtitles.
    """
    longest = max(len(line) for line in phrase.lines)
    if longest <= 10:
        size = 162
    elif longest <= 15:
        size = 140
    elif longest <= 19:
        size = 118
    elif longest <= 23:
        size = 100
    else:
        size = 94
    if len(phrase.lines) >= 3:
        size = min(size, 106)
    return size


def render_line(line: str, emphasis: str | None, colour: str | None = None) -> str:
    """Colour the whole line white, except the one emphasis word in red.

    `colour` overrides every word, used for the offset ghost layer.
    """
    if colour is not None:
        return line
    if not emphasis or emphasis not in line.split():
        return line
    parts = []
    for word in line.split():
        if word == emphasis:
            # Scale the red word up slightly so it reads as the hit.
            parts.append(f"{{\\c{RED}\\fscx116\\fscy116}}{word}{{\\c{WHITE}\\fscx100\\fscy100}}")
        else:
            parts.append(word)
    return " ".join(parts)


def build_ass(phrases: list[TimedPhrase]) -> str:
    positions = choose_positions(phrases)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,{FONT_NAME},140,{WHITE},{WHITE},&H000A0A0A&,&H00000000&,{FONT_BOLD},0,0,0,100,100,2,0,1,3.5,0,5,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for i, (phrase, position) in enumerate(zip(phrases, positions)):
        size = font_size(phrase)
        # Hold the block a touch past the vocal so it does not snap away, but
        # never into the next one — two blocks on screen at once reads as a bug.
        end = phrase.end + 0.28
        if i + 1 < len(phrases):
            end = min(end, phrases[i + 1].start - 0.06)
        end = max(end, phrase.end)

        # Lead the vocal slightly: text that appears exactly on the syllable has
        # to be read before it registers, which is what made the edit feel late.
        start = max(0.0, phrase.start - LEAD_IN)
        if i > 0:
            start = max(start, phrases[i - 1].end + 0.02)

        # Drift up into place. \move rules out \pos, so placement rides on it.
        rise = 18
        settle_ms = 340
        place = (
            f"\\an{position.an}\\move({position.x},{position.y + rise},{position.x},{position.y},0,{settle_ms})"
            f"\\fs{size}\\frz{position.angle}"
        )

        # Layer 0: an offset red ghost that resolves into the white text — a
        # chromatic split, which reads as unease rather than as a render fault.
        if phrase.emphasis:
            ghost_body = "\\N".join(render_line(line, None, colour=RED) for line in phrase.lines)
            ghost = (
                f"{{\\an{position.an}\\pos({position.x - 7},{position.y - 4})\\fs{size}"
                f"\\frz{position.angle}\\c{RED}\\alpha&H70&\\blur9"
                f"\\t(0,420,\\alpha&HFF&\\blur14)}}"
            )
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(min(start + 0.75, end))},Lyric,,0,0,0,,{ghost}{ghost_body}"
            )

        # Layer 1: the text itself — resolves out of a haze on entry and
        # dissolves back into one on exit, rather than just cutting away.
        body = "\\N".join(render_line(line, phrase.emphasis) for line in phrase.lines)
        span_ms = int((end - start) * 1000)
        settle = min(300, max(140, span_ms // 4))
        exit_ms = min(340, max(120, span_ms // 4))
        exit_start = max(settle + 40, span_ms - exit_ms)
        override = (
            f"{{{place}\\c{WHITE}\\blur{ENTRY_BLUR}"
            f"\\t(0,{settle},\\blur{REST_BLUR})"
            f"\\t({exit_start},{span_ms},\\blur{EXIT_BLUR})"
            f"\\fad(140,240)}}"
        )
        lines.append(
            f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Lyric,,0,0,0,,{override}{body}"
        )
    return "\n".join(lines) + "\n"
