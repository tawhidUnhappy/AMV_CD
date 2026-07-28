"""Dump the aligned word stream so lyric phrases can be written against real timings."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    data = json.loads((ROOT / "data" / "song" / "transcript.json").read_text(encoding="utf-8"))
    words = [w for s in data["segments"] for w in s.get("words", [])]
    out = ROOT / "data" / "song" / "words.txt"
    lines = [f"{i:3d}  {w['start']:7.2f} {w['end']:7.2f}  {w['word']}" for i, w in enumerate(words)]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(words)} words -> {out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
