"""Dump the aligned word stream so lyric phrases can be written against real timings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from amv.core.config import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, default=ROOT / "tmp" / "song" / "transcript_vocals.json")
    parser.add_argument("--out", type=Path, default=ROOT / "tmp" / "song" / "words_vocals.txt")
    args = parser.parse_args()

    data = json.loads(args.transcript.read_text(encoding="utf-8"))
    words = [w for s in data["segments"] for w in s.get("words", [])]
    lines = [f"{i:3d}  {w['start']:7.2f} {w['end']:7.2f}  {w['word']}" for i, w in enumerate(words)]
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(words)} words -> {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
