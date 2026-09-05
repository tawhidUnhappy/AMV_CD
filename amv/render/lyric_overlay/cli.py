"""Generate the burned-in lyric overlay as an ASS subtitle file."""

from __future__ import annotations

import argparse
from pathlib import Path

from amv.audio.lyrics import timed_phrases, validate
from amv.core import config
from amv.render.lyric_overlay.ass import build_ass

ROOT = config.ROOT
DEFAULT_OUT = ROOT / "tmp" / "work" / "lyrics.ass"


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
