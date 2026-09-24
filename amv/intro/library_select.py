"""Shots for a multi-show intro: one series per slot where there are enough
series, the best arrangement of them over the whole intro.

No subtitles: candidates come from the library index (amv.intro.library) -
calm slots take gently moving, well-lit, cut-free windows; drive slots the
busiest cut-free windows - with the repeats (OP/ED/eyecatch/recap), the first
and last minutes and the blacklist kept out. The best few per (slot, series)
are probed at full frame rate (amv.intro.select.probe: exact motion and the
cut check), then every assignment of series to slots is scored (shot scores
plus the match-cut term between neighbours) and the best one wins.
"""

from __future__ import annotations

import itertools
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from amv.intro.library import INDEX_FPS, Episode
from amv.intro.plan import IntroSlot
from amv.intro.select import Shot, probe, score
from amv.render.select_clips.scoring import match_score

# Cold opens are fine, but the first seconds are often a studio card and the
# last minute a next-episode preview.
HEAD_SKIP = 10.0
TAIL_SKIP = 90.0
# A map frame changing this much (48x27 grey at 8 fps, 0-1) is a hard cut.
INDEX_CUT = 0.13
BLACKLIST_FILE = Path(__file__).with_name("blacklist.json")


def blacklist() -> list[dict]:
    """Regions rejected on sight, per series (amv/intro/blacklist.json)."""
    return json.loads(BLACKLIST_FILE.read_text(encoding="utf-8")) if BLACKLIST_FILE.exists() else []


def blocked(e: Episode, rejects: list[dict]) -> list[tuple[float, float]]:
    zones = list(e.repeats)
    zones += [(r["start"], r["end"]) for r in rejects if r["series"] == e.series and r["episode"] == e.number]
    return zones


def windows(e: Episode, duration: float, kind: str, rejects: list[dict], keep: int) -> list[Shot]:
    """The most promising windows of one episode for one slot, from the index alone."""
    diffs = e.diffs()
    span = max(2, int(np.ceil(duration * INDEX_FPS)))
    if len(diffs) <= span + 1:
        return []
    win = np.lib.stride_tricks.sliding_window_view(diffs, span)
    no_cut = win.max(axis=1) < INDEX_CUT
    motion = win.mean(axis=1)
    light = np.lib.stride_tricks.sliding_window_view(e.frames.mean(axis=(1, 2)) / 255.0, span)[: len(win)].mean(axis=1)
    if kind == "calm":
        # Gentle, sustained movement (a pan, drifting light) on a mid-bright frame.
        value = np.where((motion > 0.004) & (motion < 0.03), 1.0 - np.abs(motion - 0.012) / 0.02, 0.0)
        value = value * (1.0 - np.clip(np.abs(light - 0.45) / 0.35, 0, 1))
    else:
        # Motion, weighted up where it is local (action, not a pan) and where
        # the light swings (flashes, magic).
        frames = e.frames.astype(np.float32) / 255.0
        change = np.abs(np.diff(frames, axis=0))
        local = change.std(axis=(1, 2)) / (change.mean(axis=(1, 2)) + 1e-3)
        local_w = np.lib.stride_tricks.sliding_window_view(local, span).mean(axis=1)
        swing = np.lib.stride_tricks.sliding_window_view(frames.mean(axis=(1, 2)), span + 1)[: len(win)].std(axis=1)
        value = motion * (0.5 + np.clip(local_w, 0, 2)) * (1 + 10 * swing) * (light > 0.16) * (light < 0.9)
    value = np.where(no_cut, value, 0.0)
    starts = (np.arange(len(win)) + 1) / INDEX_FPS
    ok = (starts >= HEAD_SKIP) & (starts + duration <= e.duration - TAIL_SKIP)
    for a, b in blocked(e, rejects):
        ok &= ~((starts < b) & (starts + duration > a))
    value = np.where(ok, value, 0.0)
    found: list[Shot] = []
    for i in np.argsort(-value):
        if value[i] <= 0 or len(found) >= keep:
            break
        if any(abs(f.start - starts[i]) < 6 for f in found):
            continue
        shot = Shot(e.number, str(e.file), float(starts[i]), duration, kind)
        shot.series = e.series  # type: ignore[attr-defined]
        shot.prior = float(value[i])  # type: ignore[attr-defined]
        found.append(shot)
    return found


def spectacle(shot: Shot, kind: str) -> float:
    """What makes a shot worth a place in a channel intro, on top of the
    exposure/motion score: colour always; for the calm swell, wide scenery
    over people talking; for the drive, action (local motion, flashes) over
    camera pans across crowds - which is what motion alone picked first."""
    value = score(shot, kind)
    if value <= -50:
        return value
    value += 12.0 * min(1.0, shot.saturation / 0.45)
    if kind == "calm":
        value += 8.0 * (1.0 - min(1.0, shot.skin / 0.25))
    else:
        value += 10.0 * min(1.0, max(0.0, shot.concentration - 0.8) / 1.2)
        value += 10.0 * min(1.0, shot.flash / 0.05)
    return value


def select(slots: list[IntroSlot], library: dict[str, list[Episode]], per_cell: int = 8,
           workers: int = 6) -> list[dict]:
    rejects = blacklist()
    names = sorted(library)
    cells: dict[tuple[int, str], list[Shot]] = {}
    for slot in slots:
        for name in names:
            pool: list[Shot] = []
            for e in library[name]:
                pool += windows(e, slot.duration, slot.kind, rejects, keep=3)
            # Rank on the index's own estimate across all episodes (at most 3 each).
            pool.sort(key=lambda s: -s.prior)
            cells[(slot.index, name)] = pool[: per_cell * 3]
    flat = [s for group in cells.values() for s in group]
    print(f"Probing {len(flat)} candidate windows across {len(names)} series...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(probe, flat))
    best: dict[tuple[int, str], Shot | None] = {}
    for (index, name), group in cells.items():
        kind = slots[index].kind
        for s in group:
            s.score = spectacle(s, kind)
        good = [s for s in group if s.score > -50]
        best[(index, name)] = max(good, key=lambda s: s.score) if good else None

    # Every way of giving each slot a different series (or, with fewer series
    # than slots, series may repeat but never back to back).
    distinct = len(names) >= len(slots)
    options = itertools.permutations(names, len(slots)) if distinct else itertools.product(names, repeat=len(slots))
    top, top_value = None, -1e9
    for order in options:
        if not distinct and any(a == b for a, b in zip(order, order[1:], strict=False)):
            continue
        shots = [best[(slot.index, name)] for slot, name in zip(slots, order, strict=True)]
        if any(s is None for s in shots):
            continue
        value = sum(s.score for s in shots) + 0.5 * sum(
            match_score(a, b) for a, b in zip(shots, shots[1:], strict=False))
        if value > top_value:
            top, top_value = shots, value
    if top is None:
        raise SystemExit("No arrangement has a usable shot in every slot - index more series or loosen the plan")
    for slot, s in zip(slots, top, strict=True):
        print(f"  slot {slot.index:2d} {slot.kind:5s} {slot.out_start:6.2f}-{slot.out_end:6.2f}  "
              f"{s.series} ep{s.episode:02d} @{s.start:8.2f}  score {s.score:5.1f}  motion {s.motion:.3f}", flush=True)
    return [{**slot.as_dict(), "series": s.series, "episode": s.episode, "file": s.file, "start": round(s.start, 3),
             "note": s.note, "probe": {k: round(v, 4) for k, v in asdict(s).items()
                                       if k in ("brightness", "contrast", "motion", "skin", "score")}}
            for slot, s in zip(slots, top, strict=True)]


GALLERY_SECONDS = {"calm": 2.9, "drive": 1.4}


def gallery(library: dict[str, list[Episode]], out_dir: Path, per_series: int = 10, workers: int = 6) -> Path:
    """The best-scoring windows of every series, for choosing by eye.

    Scores find shots that are well lit, moving and cut-free; they cannot
    tell a striking shot from a door opening (the first automatic pick had
    both). So the last step is a person - or Claude - looking: one sheet per
    (kind, series), each candidate as start/middle/end with its id, written
    to tmp/intro/gallery/, and the ids go in a picks file (see --picks).
    """
    from amv.vision.contact_sheet import tile

    rejects = blacklist()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for kind, seconds in GALLERY_SECONDS.items():
        for name in sorted(library):
            pool: list[Shot] = []
            for e in library[name]:
                pool += windows(e, seconds, kind, rejects, keep=3)
            pool.sort(key=lambda s: -s.prior)
            pool = pool[: per_series * 4]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(probe, pool))
            for s in pool:
                s.score = spectacle(s, kind)
            ranked = sorted((s for s in pool if s.score > -50), key=lambda s: -s.score)[:per_series]
            frames = []
            for k, s in enumerate(ranked):
                cid = f"{kind[0]}-{name}-{k:02d}"
                entries.append({"id": cid, "kind": kind, "series": name, "episode": s.episode, "file": s.file,
                                "start": round(s.start, 3), "duration": seconds, "score": round(s.score, 1)})
                for j, f in enumerate((0.05, 0.5, 0.95)):
                    path = out_dir / "frames" / f"{cid}_{j}.jpg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    label = f"{cid} ep{s.episode:02d} {s.start + seconds * f:.1f}s"
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s.start + seconds * f:.3f}", "-i", s.file,
                                    "-frames:v", "1", "-vf", f"scale=320:180,drawtext=text='{label}':fontcolor=yellow"
                                    ":fontsize=13:x=3:y=3:box=1:boxcolor=black@0.6", str(path)], check=True)
                    frames.append(path)
            if frames:
                tile(frames, out_dir / f"{kind}_{name}.jpg", cols=6, cell=None, padding=2)
            print(f"  {kind:5s} {name}: {len(ranked)} candidates", flush=True)
    listing = out_dir / "gallery.json"
    listing.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    return listing


def from_picks(slots: list[IntroSlot], picks: list, gallery_file: Path) -> list[dict]:
    """Slots filled with hand-picked gallery ids, in slot order."""
    entries = {e["id"]: e for e in json.loads(gallery_file.read_text(encoding="utf-8"))}
    if len(picks) != len(slots):
        raise SystemExit(f"{len(picks)} picks for {len(slots)} slots")
    out = []
    for slot, pick in zip(slots, picks, strict=True):
        # A pick is an id, or {"id": ..., "shift": seconds} to start later
        # inside the window (e.g. past a dissolve at its head).
        shift = 0.0
        if isinstance(pick, dict):
            pick, shift = pick["id"], float(pick.get("shift", 0.0))
        e = entries[pick]
        if shift:
            from amv.intro.select import probe as _probe

            moved = _probe(Shot(e["episode"], e["file"], e["start"] + shift, slot.duration, "shifted"))
            if moved.has_cut:
                raise SystemExit(f"{pick} shifted by {shift}s runs into a cut")
            e = {**e, "start": round(e["start"] + shift, 3), "duration": slot.duration}
        if e["kind"] != slot.kind or e["duration"] + 1e-6 < slot.duration:
            raise SystemExit(f"{pick} is a {e['kind']} window of {e['duration']}s; slot {slot.index} needs "
                             f"{slot.kind} for {slot.duration:.2f}s")
        out.append({**slot.as_dict(), "series": e["series"], "episode": e["episode"], "file": e["file"],
                    "start": e["start"], "note": f"picked {pick}"})
    return out
