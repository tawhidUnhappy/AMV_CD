"""Burn one lyric block in several candidate fonts for a side-by-side look.

Always do this before committing to a lyric font. An *outline* face — thin
hollow strokes — can look fine in a specification and wash out completely over
busy footage. Candidates that are not installed are skipped.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from amv import config

ROOT = config.ROOT
WORK = ROOT / "data" / "qa" / "fonts"
WHITE = "&H00F2F2F2&"
RED = "&H002222CC&"

# (label, family as libass sees it, candidate filenames, bold flag). Entries
# whose font is not installed are skipped, so this works on any machine.
CANDIDATES: list[tuple[str, str, tuple[str, ...], int]] = [
    ("Georgia Bold", "Georgia", ("georgiab.ttf",), -1),
    ("Times New Roman Bold", "Times New Roman", ("timesbd.ttf", "LiberationSerif-Bold.ttf"), -1),
    ("Impact", "Impact", ("impact.ttf",), 0),
    ("DejaVu Serif Bold", "DejaVu Serif", ("DejaVuSerif-Bold.ttf",), -1),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=ROOT / "data" / "out" / "amv.mp4")
    parser.add_argument("--at", type=float, default=14.2, help="timestamp to grab the backdrop from")
    args = parser.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    fonts_dir = WORK / "fonts"
    fonts_dir.mkdir(exist_ok=True)

    available: list[tuple[str, str, int]] = []
    for label, family, names, bold in CANDIDATES:
        found = config.find_font(*names)
        if found is None:
            print(f"skipping {label}: not installed", flush=True)
            continue
        shutil.copy(found, fonts_dir / found.name)
        available.append((label, family, bold))
    if not available:
        raise SystemExit("None of the candidate fonts are installed on this machine.")

    if not args.video.is_file():
        raise SystemExit(f"No video to sample from: {args.video}")
    frame = WORK / "base.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{args.at}", "-i", str(args.video),
         "-frames:v", "1", str(frame)],
        check=True,
    )

    tiles = []
    for index, (label, family, bold) in enumerate(available):
        ass = WORK / f"try_{index}.ass"
        ass.write_text(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n"
            "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,"
            " BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,"
            " BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: T,{family},118,{WHITE},{WHITE},&H000A0A0A&,&H00000000&,{bold},0,0,0,"
            "100,100,2,0,1,3.5,0,5,60,60,60,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,{\\an5\\pos(960,430)}IN YOUR "
            f"{{\\c{RED}}}MIRROR{{\\c{WHITE}}}\\NI LOOK UNSUNG\n"
            "Dialogue: 0,0:00:00.00,0:00:10.00,T,,0,0,0,,"
            "{\\an5\\pos(960,880)\\fs54\\c&H0060E0F0&}" + label + "\n",
            encoding="utf-8",
        )
        out = WORK / f"tile_{index}.jpg"
        ass_arg = ass.resolve().as_posix().replace(":", "\\:")
        fonts_arg = fonts_dir.resolve().as_posix().replace(":", "\\:")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(frame),
             "-vf", f"subtitles='{ass_arg}':fontsdir='{fonts_arg}',scale=960:540",
             "-frames:v", "1", str(out)],
            check=True,
        )
        tiles.append(out)

    listing = WORK / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in tiles), encoding="ascii")
    sheet = ROOT / "data" / "qa" / "font_compare.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-vf", "tile=2x2:padding=6:color=0x101010", "-frames:v", "1", str(sheet)],
        check=True,
    )
    print(f"Wrote {sheet}")


if __name__ == "__main__":
    main()
