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

# Story-continuity weighting (see the pick loop in main()).
# Episodes run ~1422s, so 2000 per episode index keeps positions ordered
# across episode boundaries without overlapping.
EPISODE_STRIDE = 2000.0
# Calibrated against the real score spread rather than guessed: totals run
# ~6-42 and are dominated by the visual term (5.6-38.7), with theme matching
# contributing only 0.5-3.0. A first pass at 18.0 left 23% of within-section
# transitions still running backwards, because a slightly prettier shot
# outscored the penalty. At 30 — comparable to the whole visual range —
# going backwards only wins when the forward alternatives are genuinely poor,
# which is the intended escape hatch rather than the common case.
BACKWARD_PENALTY = 30.0
# Raised alongside a much tighter decay below: consecutive shots pulled from
# the same scene cut together smoothly, while two equally good shots from
# opposite ends of the season cut like a channel change no matter how well
# each one scores on its own. Per amv-grade-and-transitions the cuts
# themselves stay hard and on the beat — that is what gives an AMV its drive —
# so the smoothness has to come from *placement*, not from softening the cut.
FORWARD_BONUS = 20.0
# Seconds of forward travel at which the "same scene" bonus has decayed to
# ~1/e. At 900 this was loose enough that a jump halfway across a season
# scored nearly as well as staying in the scene; 250 is roughly a scene's
# length, so neighbouring moments win decisively.
NEAR_SCALE = 250.0


def story_position(cand: Candidate) -> float:
    """Where a candidate sits on the whole-series timeline, in seconds."""
    return cand.episode * EPISODE_STRIDE + cand.start


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
    # Story cursor: how far into the series the edit has walked so far.
    #
    # Without this, each slot independently took its best-scoring window, so
    # the source timeline lurched backwards constantly (ep01@843s, then
    # ep01@304s, then ep02@461s, then ep01@687s...). Individually fine shots,
    # but consecutively they read as a shuffle rather than as a story.
    # Preferring windows that sit *after* the previous pick makes successive
    # shots advance through the series, so the edit narrates instead of
    # sampling. The cursor resets at each section boundary because sections
    # already step forward through their own episode ranges (SECTION_EPISODES)
    # — carrying an advanced cursor across would starve the new range.
    cursor = float("-inf")
    current_section: str | None = None
    for slot, group in zip(slots, all_candidates):
        if slot.section != current_section:
            current_section = slot.section
            cursor = float("-inf")

        def continuity(cand: Candidate, cursor: float = cursor) -> float:
            delta = story_position(cand) - cursor
            if delta < 0:
                return -BACKWARD_PENALTY
            # A short hop forward often lands in the same scene, which cuts
            # together far better than a jump across half a season.
            return FORWARD_BONUS * np.exp(-delta / NEAR_SCALE)

        group.sort(key=lambda c: -(c.total + continuity(c)))
        pick = None
        for cand in group:
            clash = any(ep == cand.episode and abs(pos - cand.start) < MIN_SEPARATION for ep, pos in used)
            if not clash and cand.visual_score > -20:
                pick = cand
                break
        if pick is None:
            pick = group[0]
        used.append((pick.episode, pick.start))
        cursor = story_position(pick)
        chosen.append(pick)

    # Play each run of instrumental-break shots in chronological order.
    #
    # The continuity weighting above can only prefer a forward window if the
    # slot's shortlist happens to contain one, which left ~20% of transitions
    # still running backwards. Break slots carry no lyric, so nothing pairs a
    # specific shot to a specific slot — the run can simply be re-ordered
    # after the fact, which makes the montage strictly chronological instead
    # of merely biased that way. Lyric slots are deliberately left alone:
    # their footage was matched to the words, and resorting them would trade
    # the thing that makes the edit mean something for tidier chronology.
    start = 0
    while start < len(slots):
        if slots[start].kind != "break":
            start += 1
            continue
        end = start
        while (end < len(slots) and slots[end].kind == "break"
               and slots[end].section == slots[start].section):
            end += 1
        chosen[start:end] = sorted(chosen[start:end], key=story_position)
        start = end

    # Duration belongs to the slot, not to the shot, so re-stamp it after
    # reordering — a shot picked for a 1.3s slot that now lands on a 2.6s one
    # would otherwise carry the short length into the render and come up
    # frames short.
    for slot, cand in zip(slots, chosen):
        cand.duration = round(slot.duration, 3)

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
