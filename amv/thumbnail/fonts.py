"""Font family names and staging (copying installed fonts into a private fontsdir)."""

from __future__ import annotations

import shutil
from pathlib import Path

from amv.core import config

ROOT = config.ROOT
FONT_DIR = ROOT / "data" / "work" / "thumbfonts"

# Families libass will be asked for. Whatever font files are found on this
# machine get staged into a private fontsdir; if a family is missing, libass
# substitutes and the thumbnail still renders (just in a different face).
LABEL_FONT = "Arial Black"
BRUSH_FONT = "Edo"

# Candidate filenames per family, searched across the platform's font dirs.
FONT_FILES: dict[str, tuple[str, ...]] = {
    LABEL_FONT: ("ariblk.ttf", "Arial Black.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"),
    BRUSH_FONT: ("edo.ttf", "edosz.ttf"),
}


def stage_fonts() -> Path:
    """Copy whatever label/brush fonts exist on this machine into a fontsdir."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []
    for family, names in FONT_FILES.items():
        found = config.find_font(*names)
        if found is not None:
            shutil.copy(found, FONT_DIR / found.name)
            staged.append(f"{family} -> {found.name}")
        else:
            print(f"NOTE: no font file found for {family!r}; libass will substitute", flush=True)
    lyric_font = config.load().lyric_font_file
    if lyric_font.is_file():
        shutil.copy(lyric_font, FONT_DIR / lyric_font.name)
    if staged:
        print("  fonts: " + ", ".join(staged), flush=True)
    return FONT_DIR
