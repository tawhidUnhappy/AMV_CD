"""Candidate shots of one show for a Short, and sheets to choose them from.

A candidate is one whole shot - cut to cut, read off the library index
(amv.intro.library, 8 fps; cached) - so a pick can never straddle a cut.
Two sources, because neither alone finds a story edit:

- --find REGEX: shots around dialogue lines that match (the moment a
  character says "I'll kill you" is the moment worth cutting to);
- --motion N: the N busiest shots of the show (fights, spells, runs) -
  motion alone picks carriages and birds, so it is the filler, not the plan.

OP/ED/recaps (footage repeated across episodes), the first/last minutes,
amv/intro/blacklist.json and catalog rejects are kept out; a shot the catalog
knows is labelled "* <why>" on its row. Each row of a sheet is one shot:
start / middle / end, with the automatic 9:16 crop drawn in yellow, so a
shot whose subject falls outside the crop is seen before it is picked.

    ./amv.sh short-find Hell_Mode --find "level|skill|summon" --motion 30 --tag power

-> tmp/shorts/pool/<show>-<tag>.json and <show>-<tag>-NN.jpg. A shot's id
("08-1059.3" = episode 8, shot starting at 1059.3 s) is what a spec lists.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from amv.core import paths
from amv.intro import dialogue
from amv.intro.library import INDEX_FPS, Episode, discover, index
from amv.intro.library_select import HEAD_SKIP, INDEX_CUT, TAIL_SKIP, blacklist, blocked

LIBRARY = Path("/mnt/datadisk/anime")
SHORTS = paths.TMP / "shorts"
POOL = SHORTS / "pool"
MIN_SHOT = 0.7  # shorter than this is a flash frame or a smear, not a shot
DARK = 0.10  # mean luma below this reads as a gap on a phone
VERTICAL = 9 / 16
CROP_FRACTION = VERTICAL * 9 / 16  # a 9:16 crop is this much of a 16:9 frame's width


@dataclass
class Shot:
    id: str
    series: str
    episode: int
    file: str
    start: float
    end: float
    motion: float
    luma: float
    line: str = ""
    focus: float = 0.5  # crop centre, fraction of frame width

    @property
    def duration(self) -> float:
        return self.end - self.start


_LOAD = threading.Lock()


def load_show(series: str, root: str = str(LIBRARY)) -> tuple[Episode, ...]:
    with _LOAD:  # worker threads ask at once; index (and find repeats) once
        return _load_show(series, root)


@lru_cache(maxsize=2)
def _load_show(series: str, root: str) -> tuple[Episode, ...]:
    library = {series: discover(Path(root))[series]}
    index(library, paths.INTRO / "library")
    return tuple(library[series])


def shots_of(e: Episode) -> list[tuple[float, float, float, float]]:
    """(start, end, motion, luma) of every cut-to-cut shot of an episode.
    Index frame i shows ~i/8 s; the ends are pulled in by a frame each so a
    8 fps boundary never includes the neighbour's first frame."""
    diffs = e.diffs()
    cuts = [0, *(np.nonzero(diffs > INDEX_CUT)[0] + 1).tolist(), len(e.frames)]
    light = e.frames.mean(axis=(1, 2)) / 255.0
    out = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        start, end = a / INDEX_FPS + 0.125, b / INDEX_FPS - 0.125
        if end - start < MIN_SHOT:
            continue
        motion = float(diffs[a:b - 1].mean()) if b - 1 > a else 0.0
        out.append((round(start, 3), round(end, 3), motion, float(light[a:b].mean())))
    return out


def usable(e: Episode, start: float, end: float, luma: float, rejects: list[dict]) -> bool:
    if start < HEAD_SKIP or end > e.duration - TAIL_SKIP or luma < DARK:
        return False
    return not any(start < z1 and end > z0 for z0, z1 in blocked(e, rejects))


def shot_at(series: str, episode: int, t: float) -> Shot:
    """The shot of an episode that contains time t (a spec's id resolves here)."""
    e = next(x for x in load_show(series) if x.number == episode)
    for start, end, motion, luma in shots_of(e):
        if start - 0.2 <= t <= end:
            return Shot(f"{episode:02d}-{start:.1f}", series, episode, str(e.file), start, end, motion, luma)
    raise SystemExit(f"{series} ep {episode}: no shot at {t}s")


def crop_x(file: str, start: float, end: float) -> float:
    from amv.shorts.catalog import cached

    return cached("crop_x", f"{file}|{start:.3f}|{end:.3f}", lambda: _crop_x(file, start, end))


def _crop_x(file: str, start: float, end: float) -> float:
    """Where to centre a 9:16 crop of a 16:9 shot: the crop-wide band of
    columns holding the most detail (edge strength plus strong colour, skin counted extra),
    summed over three frames. A centroid of the same weights lands BETWEEN
    two eyes or two characters - on a nose or on sky - which is exactly what
    a narrow crop must not do; the best band commits to one of them."""
    from amv.vision.decode import decode_tiny
    from amv.vision.skin import skin_mask

    W, H = 96, 54
    band = round(W * CROP_FRACTION)
    profile = np.zeros(W, np.float32)
    for k in (0.15, 0.5, 0.85):
        rgb = decode_tiny(file, W, H, start=start + (end - start) * k, duration=0.05, gpu=False)
        if len(rgb) == 0:
            continue
        frame = rgb[0].astype(np.float32)
        grey = frame.mean(axis=2)
        edges = np.abs(np.diff(grey, axis=1, prepend=grey[:, :1])) + np.abs(np.diff(grey, axis=0, prepend=grey[:1]))
        sat = (frame.max(axis=2) - frame.min(axis=2)) / (frame.max(axis=2) + 1.0)
        # a glowing eye or a spell has few edges but stands out by colour
        weight = (edges + 60.0 * np.clip(sat - 0.35, 0, None)) * (1.0 + 1.5 * skin_mask(frame.astype(np.int16)))
        profile += weight.sum(axis=0)
    if not profile.any():
        return 0.5
    sums = np.convolve(profile, np.ones(band), mode="valid")
    # Ties (a flat frame) resolve toward the middle.
    sums = sums * (1 - 0.15 * np.abs(np.arange(len(sums)) + band / 2 - W / 2) / W)
    return round(float((np.argmax(sums) + band / 2) / W), 3)


def candidates(series: str, find: str | None, motion: int, per_line: int = 2,
               only: set[int] | None = None) -> list[Shot]:
    episodes = [e for e in load_show(series) if not only or e.number in only]
    rejects = blacklist()
    found: dict[str, Shot] = {}
    lines = dialogue.load({series: list(episodes)}) if find else {}
    pattern = re.compile(find, re.IGNORECASE) if find else None
    for e in episodes:
        shots = [s for s in shots_of(e) if usable(e, s[0], s[1], s[3], rejects)]
        if pattern:
            for ln in lines.get((series, e.number), []):
                if not pattern.search(ln["text"]):
                    continue
                near = [s for s in shots if s[0] < ln["end"] + 1.5 and s[1] > ln["start"] - 0.5]
                for start, end, mot, luma in sorted(near, key=lambda s: -s[2])[:per_line]:
                    sid = f"{e.number:02d}-{start:.1f}"
                    found.setdefault(sid, Shot(sid, series, e.number, str(e.file), start, end, mot, luma,
                                               re.sub(r"\s+", " ", ln["text"])[:70]))
    if motion:
        busy = [(mot, e, start, end, luma) for e in episodes for start, end, mot, luma in shots_of(e)
                if usable(e, start, end, luma, rejects) and end - start >= 1.0]
        for mot, e, start, end, luma in sorted(busy, key=lambda b: -b[0])[:motion]:
            sid = f"{e.number:02d}-{start:.1f}"
            found.setdefault(sid, Shot(sid, series, e.number, str(e.file), start, end, mot, luma))
    from amv.shorts import catalog

    known = catalog.shots(series)
    skip = catalog.rejected(series, vertical=True)
    shots = sorted((s for s in found.values() if s.id not in skip),
                   key=lambda s: (s.episode, s.start))
    for s in shots:  # what an earlier session learned about a shot goes on its row
        if known.get(s.id, {}).get("why"):
            s.line = f"* {known[s.id]['why']}"[:70]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for s, x in zip(shots, ex.map(lambda s: crop_x(s.file, s.start, s.end), shots), strict=True):
            s.focus = x
    return shots


THUMB_W, THUMB_H = 320, 180


def grab(file: str, t: float) -> Image.Image:
    import subprocess

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", file, "-frames:v", "1", "-an", "-sn",
                          "-vf", f"scale={THUMB_W}:{THUMB_H},format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    if len(raw) < THUMB_W * THUMB_H * 3:
        return Image.new("RGB", (THUMB_W, THUMB_H))
    return Image.frombuffer("RGB", (THUMB_W, THUMB_H), raw[: THUMB_W * THUMB_H * 3])


def sheets(shots: list[Shot], stem: Path, per_sheet: int = 20, crop_x: dict | None = None) -> list[Path]:
    """Two shots per row, start/middle/end each, crop box drawn."""
    font = ImageFont.load_default(size=15)
    crop_w = THUMB_H * VERTICAL

    def row(s: Shot) -> Image.Image:
        img = Image.new("RGB", (THUMB_W * 3, THUMB_H), "black")
        x = (crop_x or {}).get(s.id, s.focus)
        for k, frac in enumerate((0.1, 0.5, 0.9)):
            thumb = grab(s.file, s.start + s.duration * frac)
            d = ImageDraw.Draw(thumb)
            cx = min(max(x * THUMB_W, crop_w / 2), THUMB_W - crop_w / 2)
            d.rectangle([cx - crop_w / 2, 0, cx + crop_w / 2, THUMB_H - 1], outline=(255, 230, 0), width=2)
            img.paste(thumb, (k * THUMB_W, 0))
        d = ImageDraw.Draw(img)
        label = f"{s.id}  {s.duration:.1f}s  m{s.motion * 100:.1f}"
        d.text((5, 3), label, fill="yellow", font=font, stroke_width=2, stroke_fill="black")
        if s.line:
            d.text((5, THUMB_H - 20), s.line, fill="white", font=font, stroke_width=2, stroke_fill="black")
        return img

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(row, shots))
    out = []
    for n in range(0, len(rows), per_sheet):
        chunk = rows[n:n + per_sheet]
        sheet = Image.new("RGB", (THUMB_W * 6 + 10, THUMB_H * ((len(chunk) + 1) // 2)), (40, 40, 40))
        for k, r in enumerate(chunk):
            sheet.paste(r, ((k % 2) * (THUMB_W * 3 + 10), (k // 2) * THUMB_H))
        path = stem.with_name(f"{stem.name}-{n // per_sheet:02d}.jpg")
        sheet.save(path, quality=88)
        out.append(path)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("series", help="a folder name under the library, e.g. Re_Zero")
    parser.add_argument("--find", default=None, help="regex over the dialogue (case-insensitive)")
    parser.add_argument("--motion", type=int, default=0, help="also the N busiest shots")
    parser.add_argument("--episodes", default=None, help="only these, e.g. 3-8 or 1,4,12")
    parser.add_argument("--tag", default="pool")
    args = parser.parse_args()
    keep: set[int] = set()
    for part in (args.episodes or "").split(","):
        if part:
            a, _, b = part.partition("-")
            keep.update(range(int(a), int(b or a) + 1))
    shots = candidates(args.series, args.find, args.motion, only=keep or None)
    POOL.mkdir(parents=True, exist_ok=True)
    stem = POOL / f"{args.series}-{args.tag}"
    stem.with_suffix(".json").write_text(json.dumps([asdict(s) for s in shots], indent=1), encoding="utf-8")
    for s in shots:
        print(f"{s.id:10s} {s.duration:4.1f}s motion {s.motion * 100:4.1f} luma {s.luma:.2f} x {s.focus:.2f}  {s.line}")
    for path in sheets(shots, stem):
        print(f"Wrote {path}")
    print(f"{len(shots)} shots -> {stem.with_suffix('.json')}")


if __name__ == "__main__":
    main()
