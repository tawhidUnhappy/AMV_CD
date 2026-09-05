"""Report speaker distribution and dialogue-free stretches in the scene index."""

from __future__ import annotations

import json
from collections import Counter

from amv.core.config import ROOT


def main() -> None:
    index = json.loads((ROOT / "tmp" / "subs" / "scene_index.json").read_text(encoding="utf-8"))
    speakers: Counter[str] = Counter()
    for ep in index["episodes"]:
        for event in ep["events"]:
            speakers[event["speaker"] or "(none)"] += 1

    print("top speakers:")
    for name, count in speakers.most_common(30):
        print(f"  {count:5d}  {name}")

    print("\ndialogue-free stretches >= 12s (action / atmosphere windows):")
    total = 0
    for ep in index["episodes"]:
        events = ep["events"]
        gaps = []
        for prev, nxt in zip(events, events[1:]):
            gap = nxt["start"] - prev["end"]
            if gap >= 12.0:
                gaps.append((prev["end"], nxt["start"], gap))
        total += len(gaps)
        if gaps:
            longest = max(gaps, key=lambda g: g[2])
            print(f"  ep{ep['episode']:02d}: {len(gaps):3d} gaps, longest {longest[2]:5.1f}s at {longest[0]:7.1f}s")
    print(f"  total: {total}")


if __name__ == "__main__":
    main()
