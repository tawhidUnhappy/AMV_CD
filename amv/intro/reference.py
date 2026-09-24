"""Find where every frame of a reference video comes from in the episodes.

For remaking an existing intro (amv.intro.remake): given a video that was cut
from this series, this names the episode frame behind each of its frames.

1. Coarse: every episode decoded at 8 fps, 48x27 grey (cached in
   tmp/intro/index/), and each reference frame at 10 fps correlated against
   all of it - one matrix product per episode.
2. Fine: around each coarse hit, the episode decoded at its full frame rate
   exactly the way remake.py fetches frames (CPU decode, seek half a frame
   before frame n0), so frame k of that decode IS frame n0 + k. Matching with
   a different decoder or seek put frames one off: NVDEC and the CPU decoder
   land on different first frames after the same seek.

Correlation is on mean-removed, normalised grey frames with a corner masked
(a channel watermark), so brightness and contrast changes do not break a
match. A reference frame with no good match (< ~0.95) is an effect, a
composite or footage from elsewhere - remake plans handle those by hand.

    ./amv.sh reference VIDEO --seconds 11
"""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from amv.core import paths
from amv.intro.remake import SOURCE_FPS, episode_files
from amv.vision.decode import decode_tiny

INDEX_FPS = 8
COARSE = (48, 27)
FINE = (64, 36)
# Seconds of episode decoded either side of a coarse hit.
WINDOW_PAD = 1.5


def masked_unit(frames: np.ndarray, mask: np.ndarray) -> np.ndarray:
    x = frames.reshape(len(frames), -1).astype(np.float32)[:, mask.ravel()]
    x -= x.mean(axis=1, keepdims=True)
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-3)


def corner_mask(width: int, height: int, corner: str | None) -> np.ndarray:
    mask = np.ones((height, width), bool)
    if corner:
        h, w = max(1, round(height * 0.22)), max(1, round(width * 0.17))
        rows = slice(0, h) if corner[0] == "t" else slice(height - h, height)
        cols = slice(width - w, width) if corner[1] == "r" else slice(0, w)
        mask[rows, cols] = False
    return mask


def coarse_index(files: dict[int, Path], cache: Path) -> dict[int, np.ndarray]:
    cache.mkdir(parents=True, exist_ok=True)

    def one(ep: int) -> np.ndarray:
        path = cache / f"ep{ep:02d}.npy"
        if not path.exists():
            np.save(path, decode_tiny(str(files[ep]), *COARSE, fps=INDEX_FPS, gray=True))
        return np.load(path)

    missing = [ep for ep in files if not (cache / f"ep{ep:02d}.npy").exists()]
    if missing:
        print(f"Indexing {len(missing)} episode(s) at {INDEX_FPS} fps (once, cached in {cache})...", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        return dict(zip(files, ex.map(one, files), strict=True))


def coarse_hits(video: Path, seconds: float, index: dict[int, np.ndarray], corner: str | None):
    mask = corner_mask(*COARSE, corner)
    ref = masked_unit(decode_tiny(str(video), *COARSE, start=0, duration=seconds, fps=10, gray=True), mask)
    best = np.full(len(ref), -2.0)
    hits: list[tuple[int, float] | None] = [None] * len(ref)
    for ep, frames in index.items():
        corr = ref @ masked_unit(frames, mask).T
        j = corr.argmax(axis=1)
        c = corr[np.arange(len(ref)), j]
        for i in np.where(c > best)[0]:
            best[i], hits[i] = c[i], (ep, j[i] / INDEX_FPS)
    return [(h, float(b)) for h, b in zip(hits, best, strict=True)]


def windows(hits, min_corr: float = 0.9) -> list[tuple[int, float, float]]:
    """Episode stretches worth decoding in full: good coarse hits, merged."""
    spans: dict[int, list[list[float]]] = {}
    for hit, corr in hits:
        if hit is None or corr < min_corr:
            continue
        ep, t = hit
        lo, hi = max(0.0, t - WINDOW_PAD), t + WINDOW_PAD
        group = spans.setdefault(ep, [])
        for span in group:
            if lo <= span[1] and hi >= span[0]:
                span[0], span[1] = min(span[0], lo), max(span[1], hi)
                break
        else:
            group.append([lo, hi])
    return [(ep, lo, hi) for ep, group in spans.items() for lo, hi in group]


def fine_map(video: Path, seconds: float, files: dict[int, Path], spans, corner: str | None) -> list[dict]:
    mask = corner_mask(*FINE, corner)
    ref_frames = decode_tiny(str(video), *FINE, start=0, duration=seconds, gray=True, gpu=False)
    ref = masked_unit(ref_frames, mask)
    best = [{"ep": None, "n": None, "corr": -2.0} for _ in range(len(ref))]
    for ep, lo, hi in spans:
        n0 = math.ceil(lo * SOURCE_FPS)
        frames = decode_tiny(str(files[ep]), *FINE, start=(n0 - 0.5) / SOURCE_FPS, duration=hi - lo, gray=True,
                             gpu=False)
        corr = ref @ masked_unit(frames, mask).T
        k = corr.argmax(axis=1)
        for i, (kk, c) in enumerate(zip(k, corr[np.arange(len(ref)), k], strict=True)):
            if c > best[i]["corr"]:
                best[i] = {"ep": ep, "n": int(n0 + kk), "corr": round(float(c), 4)}
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--seconds", type=float, default=11.0)
    parser.add_argument("--watermark", choices=["tr", "tl", "br", "bl"], default="tr",
                        help="corner to ignore (a channel logo); default top right")
    parser.add_argument("--out", type=Path, default=paths.INTRO / "reference_map.json")
    args = parser.parse_args()

    files = episode_files()
    index = coarse_index(files, paths.INTRO / "index")
    hits = coarse_hits(args.video, args.seconds, index, args.watermark)
    spans = windows(hits)
    print(f"{len(spans)} episode stretch(es) to match frame by frame", flush=True)
    frames = fine_map(args.video, args.seconds, files, spans, args.watermark)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"video": str(args.video), "frames": frames}, indent=0),
                        encoding="utf-8")
    weak = sum(1 for f in frames if f["corr"] < 0.95)
    print(f"Wrote {args.out}: {len(frames)} frames, {weak} with no close match (effects/composites)", flush=True)


if __name__ == "__main__":
    main()
