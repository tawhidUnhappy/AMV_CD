"""Burn one lyric block in several candidate fonts for a side-by-side look.

Kranky turned out to be an outline face — thin hollow strokes that read washed
out over busy footage. This renders the same phrase in the locally installed
alternatives so the choice can be made by eye.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "qa" / "fonts"
WHITE = "&H00F2F2F2&"
RED = "&H002222CC&"

SYSTEM_FONTS = Path("C:/Windows/Fonts")
USER_FONTS = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"

# (label, font family as libass sees it, source file, bold flag)
CANDIDATES = [
    ("Kranky (current)", "Kranky", USER_FONTS / "Kranky-Regular.ttf", 0),
    ("Georgia Bold", "Georgia", SYSTEM_FONTS / "georgiab.ttf", -1),
    ("Times New Roman Bold", "Times New Roman", SYSTEM_FONTS / "timesbd.ttf", -1),
    ("Impact", "Impact", SYSTEM_FONTS / "impact.ttf", 0),
]


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    fonts_dir = WORK / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    for _, _, source, _ in CANDIDATES:
        if source.exists():
            shutil.copy(source, fonts_dir / source.name)

    frame = WORK / "base.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", "14.2", "-i", str(ROOT / "data/out/preview.mp4"),
         "-frames:v", "1", str(frame)],
        check=True,
    )

    tiles = []
    for index, (label, family, _, bold) in enumerate(CANDIDATES):
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
