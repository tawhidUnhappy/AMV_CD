"""Fill every timeline slot with a source moment and write the EDL."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from amv.core import config
from amv.render.select_clips.candidates import Candidate, build_candidates
from amv.render.select_clips.scoring import MIN_SEPARATION, credits_zones, probe_stats, visual_score
from amv.render.timeline import build_slots

ROOT = config.ROOT
SCENE_INDEX = ROOT / "tmp" / "subs" / "scene_index.json"
EDL_PATH = ROOT / "tmp" / "edl.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=int, default=6, help="windows shortlisted per slot")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--out", type=Path, default=EDL_PATH)
    args = parser.parse_args()

    index = json.loads(SCENE_INDEX.read_text(encoding="utf-8"))
    episodes = {e["episode"]: e for e in index["episodes"]}
    # Episode 6 is a 2.8min special, too short to hold a usable arc position.
    episodes = {n: e for n, e in episodes.items() if e["duration"] > 600}
    zones = {n: credits_zones(e) for n, e in episodes.items()}
    for n, z in sorted(zones.items()):
        spans = ", ".join(f"{a/60:.1f}-{b/60:.1f}min" for a, b in z)
        print(f"  ep{n:02d} credits: {spans or '(none found)'}", flush=True)

    rng = np.random.default_rng(args.seed)
    slots = build_slots()
    print(f"\nFilling {len(slots)} slots...", flush=True)

    # Break slots need a wider shortlist: they are picked almost purely on
    # motion, so more windows means a better chance of genuinely kinetic footage.
    all_candidates: list[list[Candidate]] = [
        build_candidates(slot, episodes, zones, rng, args.candidates * (2 if slot.kind == "break" else 1))
        for slot in slots
    ]

    flat = [(i, c) for i, group in enumerate(all_candidates) for c in group]
    print(f"Scoring {len(flat)} candidate windows...", flush=True)

    def score_one(item: tuple[int, Candidate]) -> None:
        i, cand = item
        want_motion = slots[i].kind == "break"
        cand.brightness, cand.contrast, cand.motion, cand.skin = probe_stats(cand.file, cand.start, cand.duration)
        cand.visual_score = visual_score(cand.brightness, cand.contrast, cand.motion, cand.skin, want_motion)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(score_one, flat))

    chosen: list[Candidate] = []
    used: list[tuple[int, float]] = []
    for group in all_candidates:
        group.sort(key=lambda c: -c.total)
        pick = None
        for cand in group:
            clash = any(ep == cand.episode and abs(pos - cand.start) < MIN_SEPARATION for ep, pos in used)
            if not clash and cand.visual_score > -20:
                pick = cand
                break
        if pick is None:
            pick = group[0]
        used.append((pick.episode, pick.start))
        chosen.append(pick)

    edl = {
        "song": str(config.load().song),
        "slots": [
            {
                "index": slot.index,
                "out_start": round(slot.start, 3),
                "out_end": round(slot.end, 3),
                "duration": round(slot.duration, 3),
                "section": slot.section,
                "kind": slot.kind,
                "lyric": slot.lyric,
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(cand).items()},
            }
            for slot, cand in zip(slots, chosen)
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(edl, indent=1), encoding="utf-8")

    rejected = sum(1 for c in chosen if c.visual_score <= -20)

    print(f"\nWrote {args.out}")
    print(f"episodes used: {dict(sorted(Counter(c.episode for c in chosen).items()))}")
    print(f"sources: {dict(Counter(c.note.split(':')[0] for c in chosen))}")
    print(f"slots still on a poor-visual window: {rejected}")


if __name__ == "__main__":
    main()
