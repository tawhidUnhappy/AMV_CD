"""Quick look at word-timing quality and instrumental gaps in the song transcript."""

from __future__ import annotations

import json

from amv.core.config import ROOT


def main() -> None:
    data = json.loads((ROOT / "data" / "song" / "transcript.json").read_text(encoding="utf-8"))
    segments = data["segments"]
    words = [w for s in segments for w in s.get("words", [])]
    missing = [w for w in words if "start" not in w or "end" not in w]

    print(f"duration : {data['duration']:.2f}s")
    print(f"segments : {len(segments)}")
    print(f"words    : {len(words)}  (missing timestamps: {len(missing)})")
    if missing:
        print("  " + ", ".join(repr(w["word"]) for w in missing[:20]))

    print("\nfirst words:")
    for w in words[:12]:
        print(f"  {w.get('start', -1):7.2f} -> {w.get('end', -1):7.2f}  {w['word']!r}")

    print("\ninstrumental gaps (>3.5s):")
    prev = 0.0
    for seg in segments:
        if seg["start"] - prev > 3.5:
            print(f"  {prev:7.2f} -> {seg['start']:7.2f}   ({seg['start'] - prev:5.2f}s)")
        prev = seg["end"]
    tail = data["duration"] - prev
    if tail > 3.5:
        print(f"  {prev:7.2f} -> {data['duration']:7.2f}   ({tail:5.2f}s)  [outro]")


if __name__ == "__main__":
    main()
