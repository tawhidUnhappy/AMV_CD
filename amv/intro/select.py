"""Pick a shot for every slot of the intro plan.

Reuses the main pipeline's gates (head/tail trim, OP/ED zones - the lyric
repeat detector as well as the gap one - BLACKLIST) and its match-cut term, with two differences an intro
needs:

- The swell wants calm, wide, well-lit shots - so it draws from the
  dialogue-free gaps the main picker avoids (those ARE the establishing
  shots, which is what an opening is). The drive wants motion, and takes
  the busiest seconds of a per-episode motion map.
- The drive cuts on the beat, where one hard cut inside a shot reads as a
  double cut. So the probe decodes every frame, not 8 per second, and
  rejects any window with a scene change inside it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from amv.intro.plan import IntroSlot
from amv.render.select_clips.scoring import (
    MIN_BRIGHTNESS,
    credits_zones,
    song_zones,
    match_score,
    usable,
    visual_score,
)
from amv.vision.decode import decode_tiny, grid_signature, luma
from amv.vision.skin import skin_mask

# A frame-to-frame luma change this big (0-1) is a hard cut inside the window.
CUT_DIFF = 0.09
# Two picks from one episode must be at least this far apart.
MIN_SEPARATION = 20.0
PROBE_W, PROBE_H = 64, 36
# Below this mean frame change a drive shot is a still.
DRIVE_MIN_MOTION = 0.015


@dataclass
class Shot:
    episode: int
    file: str
    start: float
    duration: float
    note: str
    brightness: float = 0.0
    contrast: float = 0.0
    motion: float = 0.0
    skin: float = 0.0
    has_cut: bool = False
    score: float = -99.0
    head_sig: list[float] = field(default_factory=list)
    tail_sig: list[float] = field(default_factory=list)
    head_motion: float = 0.0
    tail_motion: float = 0.0
    #: Spectacle measures (see amv.intro.library_select.spectacle): colour,
    #: how local the motion is (action moves part of the frame, a pan moves
    #: all of it), and brightness swings (flashes, magic, impacts).
    saturation: float = 0.0
    concentration: float = 0.0
    flash: float = 0.0


def probe(shot: Shot) -> Shot:
    """Every frame, tiny: exposure, motion, skin, the cut check and the
    head/tail signatures match_score compares."""
    rgb = decode_tiny(shot.file, PROBE_W, PROBE_H, start=shot.start, duration=shot.duration)
    count = len(rgb)
    if count < 4:
        return shot
    frames = luma(rgb)
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    shot.brightness, shot.contrast = float(frames.mean()), float(frames.std())
    shot.motion, shot.skin = float(diffs.mean()), float(skin_mask(rgb.astype(np.int16)).mean())
    shot.has_cut = bool((diffs > CUT_DIFF).any())
    change = np.abs(np.diff(frames, axis=0))
    shot.concentration = float((change.std(axis=(1, 2)) / (change.mean(axis=(1, 2)) + 1e-3)).mean())
    shot.flash = float(frames.mean(axis=(1, 2)).std())
    rgbf = rgb.astype(np.float32)
    shot.saturation = float(((rgbf.max(axis=-1) - rgbf.min(axis=-1)) / (rgbf.max(axis=-1) + 1.0)).mean())
    span = max(2, round(count * 0.3))
    shot.head_sig, shot.tail_sig = grid_signature(frames[:span]), grid_signature(frames[-span:])
    shot.head_motion, shot.tail_motion = float(diffs[: span - 1].mean()), float(diffs[-(span - 1):].mean())
    return shot


MAP_FPS = 6
MAP_W, MAP_H = 32, 18
# A map frame changing this much (32x18 luma, 0-1) is a hard cut.
MAP_CUT = 0.12


def motion_map(episode: dict, cache: Path) -> np.ndarray:
    """Frame-to-frame change at MAP_FPS over a whole episode, decoded tiny and
    cached: entry i is the change from frame i to i+1.

    Anime holds most frames still, so guessing windows from dialogue finds
    motion about one time in twenty; this map finds where the action IS. It is
    per frame, not per second, because the busiest seconds of a series are
    montages - a second's average cannot tell sustained motion from three
    hard cuts."""
    path = cache / f"ep{episode['episode']:02d}.npy"
    if path.exists():
        return np.load(path)
    frames = decode_tiny(episode["file"], MAP_W, MAP_H, fps=MAP_FPS, gray=True)
    diffs = np.abs(np.diff(frames.astype(np.float32) / 255.0, axis=0)).mean(axis=(1, 2)).astype(np.float32)
    cache.mkdir(parents=True, exist_ok=True)
    np.save(path, diffs)
    return diffs


def calm_score(shot: Shot) -> float:
    """A wide, well-lit, gently moving shot: a slow pan or drifting clouds,
    not a locked-off frame and not action."""
    if shot.brightness < MIN_BRIGHTNESS or shot.brightness > 0.9 or shot.contrast < 0.06:
        return -50.0
    score = 10.0 * min(1.0, shot.contrast / 0.22)
    score += 8.0 * (1.0 - min(1.0, abs(shot.brightness - 0.48) / 0.4))
    score += 8.0 * min(1.0, shot.motion / 0.010)
    score -= 12.0 * min(1.0, max(0.0, shot.motion - 0.035) / 0.035)
    return score


def score(shot: Shot, kind: str) -> float:
    if shot.has_cut or shot.contrast == 0.0:
        return -99.0
    if kind == "drive" and shot.motion < DRIVE_MIN_MOTION:
        # A still frame for a beat reads as the edit stalling.
        return -60.0
    value = calm_score(shot) if kind == "calm" else visual_score(
        shot.brightness, shot.contrast, shot.motion, shot.skin, want_motion=True)
    return value


def episode_window(slot: IntroSlot, slots: list[IntroSlot], episodes: list[int]) -> list[int]:
    """The story walks forward: slot i draws from its share of the series,
    with a little overlap either side."""
    n, total = len(slots), len(episodes)
    lo = int(slot.index / n * total)
    hi = int((slot.index + 1) / n * total)
    return episodes[max(0, lo - 1):min(total, hi + 2)]


def candidates(slot: IntroSlot, pool: list[dict], zones: dict, rng: np.random.Generator, limit: int,
               maps: dict[int, np.ndarray]) -> list[Shot]:
    duration = slot.duration
    found: list[Shot] = []
    if slot.kind == "calm":
        for ep in pool:
            events = ep["events"]
            for prev, nxt in zip(events, events[1:], strict=False):
                gap_start, gap_end = prev["end"] + 0.4, nxt["start"] - 0.2
                if gap_end - gap_start < duration + 0.5:
                    continue
                for start in np.arange(gap_start, gap_end - duration, max(duration, 3.0)):
                    if usable(ep, float(start), duration, zones[ep["episode"]]):
                        found.append(Shot(ep["episode"], ep["file"], float(start), duration, "gap"))
    else:
        # The windows with the most sustained motion and no cut in them
        # (one map frame over MAP_CUT is a cut), a few seconds apart so one
        # fight does not fill the shortlist. The exact probe checks again at
        # full frame rate.
        span = int(np.ceil(duration * MAP_FPS))
        busy: list[tuple[float, dict, float]] = []
        for ep in pool:
            diffs = maps[ep["episode"]]
            if len(diffs) <= span:
                continue
            windows = np.lib.stride_tricks.sliding_window_view(diffs, span)
            ok = windows.max(axis=1) < MAP_CUT
            means = np.where(ok, windows.mean(axis=1), 0.0)
            for i in np.argsort(-means)[: limit * 20]:
                if means[i] <= 0:
                    break
                busy.append((float(means[i]), ep, (i + 1) / MAP_FPS))
        busy.sort(key=lambda item: -item[0])
        for _, ep, start in busy:
            if len(found) >= limit:
                break
            if any(f.episode == ep["episode"] and abs(f.start - start) < 4 for f in found):
                continue
            if usable(ep, start, duration, zones[ep["episode"]]):
                found.append(Shot(ep["episode"], ep["file"], start, duration, "motion"))
    if slot.kind == "drive":
        return found[:limit]
    rng.shuffle(found)
    return found[:limit]


def select(slots: list[IntroSlot], episodes: dict[int, dict], seed: int, limit: int, workers: int,
           cache: Path) -> list[dict]:
    rng = np.random.default_rng(seed)
    numbers = sorted(episodes)
    songs = song_zones(episodes)
    zones = {n: credits_zones(ep) + songs[n] for n, ep in episodes.items()}
    missing = [n for n in numbers if not (cache / f"ep{n:02d}.npy").exists()]
    if missing:
        print(f"Mapping motion in {len(missing)} episode(s) (once, cached in {cache})...", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        maps = dict(zip(numbers, ex.map(lambda n: motion_map(episodes[n], cache), numbers), strict=True))
    shortlist: list[list[Shot]] = []
    for slot in slots:
        pool = [episodes[n] for n in episode_window(slot, slots, numbers)]
        shortlist.append(candidates(slot, pool, zones, rng, limit, maps))
    flat = [s for group in shortlist for s in group]
    print(f"Probing {len(flat)} candidate windows...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(probe, flat))

    picks: list[Shot] = []
    for slot, group in zip(slots, shortlist, strict=True):
        for shot in group:
            shot.score = score(shot, slot.kind)
        prev = picks[-1] if picks else None

        def total(shot: Shot, prev: Shot | None = prev) -> float:
            if shot.score <= -50:
                return -999.0
            if any(p.episode == shot.episode and abs(p.start - shot.start) < MIN_SEPARATION for p in picks):
                return -999.0
            repeat = 4.0 * sum(1 for p in picks if p.episode == shot.episode)
            return shot.score + 0.5 * match_score(prev, shot) - repeat

        best = max(group, key=total)
        if total(best) <= -999:
            raise SystemExit(f"No usable shot for slot {slot.index} - raise --candidates")
        picks.append(best)
        print(f"  slot {slot.index:2d} {slot.kind:5s} {slot.out_start:6.2f}-{slot.out_end:6.2f}  ep{best.episode:02d} "
              f"@{best.start:8.2f}  score {best.score:5.1f}  motion {best.motion:.3f}  {best.note}", flush=True)

    return [{**slot.as_dict(), "episode": shot.episode, "file": shot.file, "start": round(shot.start, 3),
             "note": shot.note, "probe": {k: round(v, 4) for k, v in asdict(shot).items()
                                          if k in ("brightness", "contrast", "motion", "skin", "score")}}
            for slot, shot in zip(slots, picks, strict=True)]
