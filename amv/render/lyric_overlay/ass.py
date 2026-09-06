"""Build the burned-in lyric overlay ASS document text.

Classic fansub-subtitle styling: a stacked 2-3 line block in uppercase, warm
yellow-amber with a black outline and a light drop shadow, sitting in a fixed
position at the bottom of frame, with exactly one word per phrase in red.

This replaced a title-card look (94-162px white text moving between six
off-centre anchors at slight angles). That version competed with the footage
instead of accompanying it — the words became the composition and the shot
played behind them. Subtitle scale keeps the eye on the animation.

Where each block sits comes from positioning.py.
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
#
# Warm yellow-orange as the body colour, the classic fansub tint: it separates
# from anime's usual palette (skin, sky, foliage) without the glare of pure
# white, and it reads as "subtitle" rather than as "title card".
AMBER = "&H0000B4FF&"   # rgb(255, 180, 0)
WHITE = "&H00F2F2F2&"
RED = "&H002222CC&"     # rgb(204, 34, 34)

# Blocks soften in and out rather than hard-cutting, but only just — an
# earlier version resolved them out of a heavy haze (entry 12, exit 9), which
# on a burned-in 1080p overlay reads as out-of-focus text rather than as an
# effect. Rest blur stays low enough that the glyph edges are genuinely crisp
# while the block is being read.
ENTRY_BLUR = 3
REST_BLUR = 0.4
EXIT_BLUR = 3


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def font_size(phrase: TimedPhrase) -> int:
    """Subtitle-scale sizing: readable, but never competing with the picture.

    An earlier pass ran 94-162px, sized to dominate the frame the way a
    lyric-video title card does. Over actual footage that buried the shot —
    the words became the composition and the animation played behind them.

    Sizes here are measured off the reference AMV rather than guessed: a
    21-character line there spans ~467px of a 1920-wide frame, i.e. ~22px of
    advance per character, which for a bold narrow sans is a ~46px face. The
    range below sits either side of that.
    """
    longest = max(len(line) for line in phrase.lines)
    if longest <= 15:
        size = 52
    elif longest <= 22:
        size = 48
    elif longest <= 30:
        size = 46
    else:
        size = 42
    if len(phrase.lines) >= 3:
        size = min(size, 42)
    return size


def render_line(line: str, emphasis: str | None, colour: str | None = None) -> str:
    """Colour the whole line amber, except the one emphasis word in red.

    `colour` overrides every word.
    """
    if colour is not None:
        return line
    if not emphasis or emphasis not in line.split():
        return line
    parts = []
    for word in line.split():
        if word == emphasis:
            # Scale the red word up slightly so it reads as the hit. Kept
            # modest at subtitle size — the old 116% was tuned for 140px text
            # and makes a 54px line visibly ragged.
            parts.append(f"{{\\c{RED}\\fscx108\\fscy108}}{word}{{\\c{AMBER}\\fscx100\\fscy100}}")
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
Style: Lyric,{FONT_NAME},48,{AMBER},{AMBER},&H00101010&,&H00000000&,{FONT_BOLD},0,0,0,100,100,3,0,1,2.0,0.9,2,80,80,52,1

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
        rise = 6
        settle_ms = 340
        place = (
            f"\\an{position.an}\\move({position.x},{position.y + rise},{position.x},{position.y},0,{settle_ms})"
            f"\\fs{size}\\frz{position.angle}"
        )

        # The offset red "chromatic split" ghost layer that used to sit under
        # every emphasis block is gone. It drew a second, blurred, offset copy
        # of the text — on this track it read as a rendering fault rather than
        # as unease, and it was the loudest part of the "text looks messy"
        # problem. The emphasis word still carries red inline (render_line).

        # The text itself — softens in on entry and back out on exit, rather
        # than just cutting away.
        body = "\\N".join(render_line(line, phrase.emphasis) for line in phrase.lines)
        span_ms = int((end - start) * 1000)
        settle = min(300, max(140, span_ms // 4))
        exit_ms = min(340, max(120, span_ms // 4))
        exit_start = max(settle + 40, span_ms - exit_ms)
        override = (
            f"{{{place}\\c{AMBER}\\blur{ENTRY_BLUR}"
            f"\\t(0,{settle},\\blur{REST_BLUR})"
            f"\\t({exit_start},{span_ms},\\blur{EXIT_BLUR})"
            f"\\fad(140,240)}}"
        )
        lines.append(
            f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Lyric,,0,0,0,,{override}{body}"
        )
    return "\n".join(lines) + "\n"
