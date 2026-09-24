"""A library of series for a multi-show intro: every folder under a root is
one series, every video in it one episode - no subtitles, no config.json.

Per episode, one cached decode (8 fps, 48x27 grey; tmp/intro/library/) gives
everything the intro needs without looking at subtitles:

- motion: frame-to-frame change, and cuts (one big change);
- repeats: stretches whose frames also appear in 2+ other episodes of the
  same series. That is the OP, the ED, eyecatches, title cards and "last
  time" recaps - the footage an intro must not use, found by what it IS
  (repeated) rather than by what the subtitles around it look like, which
  missed a subtitled OP on the first intro.

    ./amv.sh intro --library /mnt/datadisk/anime --song track.wav
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from amv.vision.decode import decode_tiny

INDEX_FPS = 8
INDEX_W, INDEX_H = 48, 27
VIDEO_SUFFIXES = {".mkv", ".mp4", ".avi", ".webm", ".m4v"}
# Tried in order; the first that matches names the episode. Covers
# "..._S01_Ep20_...", "[S01] [E12] ...", "[SO] [06 - Title]", "08. Title",
# "Title_13_1080p".
EPISODE_PATTERNS = (
    r"[Ee]p(?:isode)?[ _.-]?(\d{1,3})(?!\d)",
    r"\[E(\d{1,3})\]",
    r"\[(\d{1,3}) - ",
    r"^(\d{1,3})\.\s",
    r"[ _](\d{1,3})[ _](?:\d{3,4}p|v\d)",
    r"(?<!\d)(\d{1,3})(?!\d)",
)
# Repeat detection: sampled at 1 fps on a 16x9 thumbnail (an OP is ~90 samples;
# at 2 fps and full index size a 23-episode series is ~5e12 multiply-adds), a
# frame "repeats" when a frame of another episode matches it this closely
# (correlation of mean-removed grey).
REPEAT_FPS = 1
REPEAT_TARGET_FPS = 4
REPEAT_CORR = 0.97
REPEAT_MIN_EPISODES = 2
# A repeat run shorter than this is a coincidence (two black frames, a
# static establishing shot reused once), not a sequence.
REPEAT_MIN_SECONDS = 4.0
REPEAT_PAD = 2.0


def episode_number(name: str) -> int | None:
    for pattern in EPISODE_PATTERNS:
        match = re.search(pattern, name)
        if match:
            return int(match.group(1))
    return None


@dataclass
class Episode:
    series: str
    number: int
    file: Path
    frames: np.ndarray | None = None  # (n, H, W) uint8 at INDEX_FPS
    repeats: list[tuple[float, float]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.series} {self.number:02d}"

    @property
    def duration(self) -> float:
        return len(self.frames) / INDEX_FPS if self.frames is not None else 0.0

    def diffs(self) -> np.ndarray:
        f = self.frames.astype(np.float32) / 255.0
        return np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))


def discover(root: Path) -> dict[str, list[Episode]]:
    series: dict[str, list[Episode]] = {}
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        episodes = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in VIDEO_SUFFIXES:
                number = episode_number(path.name)
                if number is not None:
                    episodes.append(Episode(folder.name, number, path))
        numbers = [e.number for e in episodes]
        if episodes and len(set(numbers)) == len(numbers):
            series[folder.name] = sorted(episodes, key=lambda e: e.number)
        elif episodes:
            print(f"skipping {folder.name}: episode numbers could not be told apart", flush=True)
    return series


def index(library: dict[str, list[Episode]], cache: Path, workers: int = 3) -> None:
    """Decode every episode once (cached), then find its repeats."""
    todo = [e for eps in library.values() for e in eps]

    def load(e: Episode) -> None:
        path = cache / e.series / f"{e.number:03d}.npy"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, decode_tiny(str(e.file), INDEX_W, INDEX_H, fps=INDEX_FPS, gray=True))
        e.frames = np.load(path)

    missing = [e for e in todo if not (cache / e.series / f"{e.number:03d}.npy").exists()]
    if missing:
        print(f"Indexing {len(missing)} episode(s) (once, cached in {cache}) - several minutes...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(load, todo))
    for name, episodes in library.items():
        find_repeats(episodes)
        covered = sum(b - a for e in episodes for a, b in e.repeats)
        print(f"  {name}: {len(episodes)} episodes, {covered / 60:.1f} min of repeated footage excluded", flush=True)


def _unit(frames: np.ndarray) -> np.ndarray:
    x = frames.reshape(len(frames), -1).astype(np.float32)
    x -= x.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(x, axis=1, keepdims=True)
    # Flat frames (black, white, one colour) match everything; never call
    # them repeats on their own - they get covered by the run around them.
    return np.where(norm > 30 * np.sqrt(x.shape[1] / 144), x / (norm + 1e-3), 0.0)


def find_repeats(episodes: list[Episode]) -> None:
    step = INDEX_FPS // REPEAT_FPS

    def thumb(frames: np.ndarray) -> np.ndarray:  # 48x27 -> 16x9 block means
        return frames.reshape(len(frames), 9, 3, 16, 3).mean(axis=(2, 4))

    samples = [_unit(thumb(e.frames[::step])) for e in episodes]
    # The other side is sampled finer: two episodes' copies of an OP start at
    # different sub-second offsets, and in a fast-cut OP a frame half a second
    # away is another shot - at 1 fps on both sides only the slow ED matched.
    targets = [_unit(thumb(e.frames[:: INDEX_FPS // REPEAT_TARGET_FPS])) for e in episodes]
    for i, e in enumerate(episodes):
        hits = np.zeros(len(samples[i]), np.int32)
        for j, other in enumerate(targets):
            if i == j or len(other) == 0:
                continue
            best = np.zeros(len(samples[i]), np.float32)
            for lo in range(0, len(other), 4096):
                best = np.maximum(best, (samples[i] @ other[lo:lo + 4096].T).max(axis=1))
            hits += best >= REPEAT_CORR
        repeated = hits >= REPEAT_MIN_EPISODES
        runs: list[tuple[float, float]] = []
        k = 0
        while k < len(repeated):
            if not repeated[k]:
                k += 1
                continue
            start = k
            gap = 0
            while k < len(repeated) and gap <= 2 * REPEAT_FPS:  # bridge 2s holes (flat frames)
                gap = 0 if repeated[k] else gap + 1
                k += 1
            end = k - gap
            if (end - start) / REPEAT_FPS >= REPEAT_MIN_SECONDS:
                runs.append((max(0.0, start / REPEAT_FPS - REPEAT_PAD), end / REPEAT_FPS + REPEAT_PAD))
        e.repeats = runs


def main() -> None:
    import argparse

    from amv.core import paths

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    library = discover(args.root)
    for name, eps in library.items():
        print(f"{name}: episodes {[e.number for e in eps]}")
    index(library, paths.INTRO / "library")
    for eps in library.values():
        for e in eps[:3]:
            print(f"  {e.key}: repeats {[(round(a), round(b)) for a, b in e.repeats]}")


if __name__ == "__main__":
    main()
