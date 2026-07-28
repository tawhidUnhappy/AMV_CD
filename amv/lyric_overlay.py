"""Generate the burned-in lyric overlay as an ASS subtitle file.

Style follows the reference look: a stacked 2-3 line block in uppercase Kranky,
white with a heavy drop shadow, with exactly one word per phrase in red. Blocks
sit off-centre and move around the frame between lines rather than sitting in a
fixed subtitle position.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from amv import config
from amv.lyrics import TimedPhrase, timed_phrases, validate

ROOT = config.ROOT
DEFAULT_OUT = ROOT / "data" / "work" / "lyrics.ass"

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

# Text appears this far ahead of the syllable so it is readable on the beat.
LEAD_IN = 0.18
# Blocks resolve out of a haze instead of hard-cutting in; a little blur is kept
# at rest so the edges stay soft now that the drop shadow is gone.
ENTRY_BLUR = 12
REST_BLUR = 0.9
EXIT_BLUR = 9


@dataclass(frozen=True)
class Position:
    """Where a lyric block sits. `an` picks which corner `pos` anchors."""

    an: int
    x: int
    y: int
    angle: float = 0.0


# Off-centre placements, matching how the reference moves text around the frame.
POSITIONS: tuple[Position, ...] = (
    Position(6, 1815, 395, -1.2),   # right, upper-middle
    Position(4, 115, 470, 1.0),     # left, middle
    Position(4, 140, 775, -0.8),    # lower left
    Position(6, 1790, 745, 1.2),    # lower right
    Position(4, 125, 300, 0.8),     # upper left
    Position(6, 1800, 560, -1.0),   # right, middle
)


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


PROBE_W, PROBE_H = 96, 54


def column_skin(slot: dict):
    """Per-column skin mass for one shot, as a length-PROBE_W array.

    Reuses the skin heuristic from clip selection as a stand-in for "where the
    character is in frame".
    """
    import subprocess

    import numpy as np

    command = [
        "ffmpeg", "-v", "error", "-ss", f"{slot['start']:.3f}", "-t", f"{max(slot['duration'], 0.5):.3f}",
        "-i", slot["file"], "-vf", f"scale={PROBE_W}:{PROBE_H},fps=4,format=rgb24", "-f", "rawvideo", "-",
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    frame_size = PROBE_W * PROBE_H * 3
    count = len(result.stdout) // frame_size
    if count == 0:
        return np.zeros(PROBE_W)
    rgb = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = rgb.reshape(count, PROBE_H, PROBE_W, 3).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    skin = (r > 110) & (g > 70) & (b > 50) & (r > g) & (g >= b) & ((mx - mn) > 14) & ((r - b) > 18) & (r < 252)
    return skin.mean(axis=(0, 1))


def clearest_side(slots: list[dict]) -> str:
    """Side of frame to put text on, considering EVERY shot the phrase covers.

    A lyric block routinely spans several cuts, and the character is somewhere
    different in each. Sampling only the first shot placed text clear of that
    one face and straight across the next — which is exactly the bug this
    aggregates away. Skin mass is summed over all covered shots, so the chosen
    side is the one that stays clear for the whole time the block is up.
    """
    import numpy as np

    if not slots:
        return "left"
    total = np.zeros(PROBE_W)
    for slot in slots:
        total = total + column_skin(slot)
    third = PROBE_W // 3
    left, right = float(total[:third].sum()), float(total[-third:].sum())
    # Text goes opposite the subject; ties default to the left.
    return "left" if right > left else "right"


def choose_positions(phrases: list[TimedPhrase], edl: Path | None = None) -> list[Position]:
    """Place each block away from the subject, varying height for rhythm."""
    slots: list[dict] = []
    path = edl or ROOT / "data" / "edl.json"
    if path.exists():
        slots = json.loads(path.read_text(encoding="utf-8"))["slots"]

    def slots_spanning(start: float, end: float) -> list[dict]:
        return [s for s in slots if s["out_start"] < end and s["out_end"] > start]

    left_side = [p for p in POSITIONS if p.an == 4]
    right_side = [p for p in POSITIONS if p.an == 6]

    chosen: list[Position] = []
    counters = {"left": 0, "right": 0}
    for phrase in phrases:
        # The block is on screen slightly before and after the vocal, so judge
        # every shot in that whole window, not just the one at its start.
        covered = slots_spanning(phrase.start - LEAD_IN, phrase.end + 0.3)
        side = clearest_side(covered)
        bank = left_side if side == "left" else right_side
        candidate = bank[counters[side] % len(bank)]
        counters[side] += 1
        if chosen and candidate == chosen[-1]:
            candidate = bank[counters[side] % len(bank)]
            counters[side] += 1
        chosen.append(candidate)
    return chosen


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    validate()
    every = timed_phrases()
    # Only the curated hooks get text; the rest of the song plays on footage
    # alone, which is how AMVs use lyrics.
    phrases = [p for p in every if p.show]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_ass(phrases), encoding="utf-8")
    print(f"Wrote {args.out}  ({len(phrases)} of {len(every)} phrases shown)")
    for p in phrases:
        print(f"  [{p.start:7.2f} -> {p.end:7.2f}] {' / '.join(p.lines)}")


if __name__ == "__main__":
    main()
