"""Which way a shot moves, at its start and at its end - for cutting so that
movement carries across the cut (a pan left into a pan left, a rush toward
the camera into a push in), the way a hand-cut AMV flows.

Global motion per frame pair by phase correlation on small grey frames
(numpy FFT, no dependencies): the shift that best maps one frame onto the
next. That is the camera's (or a large subject's) movement; small moving
subjects barely move it. Sign convention: +x = the picture content moves
right, +y = down, in fractions of the frame width/height per second.

    ./amv.sh flow POOL.json      # adds head/tail motion and focal point to every entry
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from amv.vision.decode import decode_tiny

W, H = 128, 72
SOURCE_FPS = 24000 / 1001


def _shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """(dx, dy, confidence) that moves frame a onto frame b."""
    window = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa, fb = np.fft.fft2((a - a.mean()) * window), np.fft.fft2((b - b.mean()) * window)
    cross = fb * np.conj(fa)
    cross /= np.abs(cross) + 1e-9
    corr = np.fft.ifft2(cross).real
    y, x = np.unravel_index(np.argmax(corr), corr.shape)
    peak = float(corr[y, x])
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return float(x), float(y), peak


def motion(file: str, start: float, duration: float) -> dict:
    """Per-second global motion over the first and last 40% of a window."""
    frames = decode_tiny(file, W, H, start=start, duration=duration, gray=True, gpu=False).astype(np.float32)
    if len(frames) < 3:
        return {"head": [0.0, 0.0], "tail": [0.0, 0.0], "strength": 0.0}
    steps = [_shift(a, b) for a, b in zip(frames, frames[1:], strict=False)]
    # Only confident estimates count: a flash or a fade matches nothing.
    vec = np.array([(dx / W * SOURCE_FPS, dy / H * SOURCE_FPS) if c > 0.08 else (0.0, 0.0) for dx, dy, c in steps])
    k = max(1, round(len(vec) * 0.4))
    head, tail = vec[:k].mean(axis=0), vec[-k:].mean(axis=0)
    return {"head": [round(float(v), 3) for v in head], "tail": [round(float(v), 3) for v in tail],
            "strength": round(float(np.linalg.norm(vec, axis=1).mean()), 3)}


def focus(file: str, at: float) -> list[float]:
    """Where the eye goes in the frame at `at`, as (x, y) fractions: the
    centroid of skin (faces, hands) when there is enough of it, else of
    local contrast (the busiest part of the picture) - for keeping the
    viewer's focal point in place across a cut (eye trace)."""
    from amv.vision.skin import skin_mask

    rgb = decode_tiny(file, 64, 36, start=at, duration=0.05, gpu=False)
    if len(rgb) == 0:
        return [0.5, 0.5]
    frame = rgb[0].astype(np.int16)
    ys, xs = np.mgrid[0:36, 0:64]
    skin = skin_mask(frame).astype(np.float32)
    if skin.mean() > 0.03:
        weight = skin
    else:
        grey = frame.mean(axis=2)
        weight = np.abs(grey - np.median(grey)) ** 2
    total = weight.sum() + 1e-6
    return [round(float((weight * xs).sum() / total / 63), 3), round(float((weight * ys).sum() / total / 35), 3)]


def direction(v: list[float]) -> str:
    x, y = v
    if abs(x) < 0.03 and abs(y) < 0.03:
        return "still"
    return ("right" if x > 0 else "left") if abs(x) >= abs(y) else ("down" if y > 0 else "up")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pool", type=Path, help="JSON list of {id, file, start, duration}")
    args = parser.parse_args()
    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    def measure(e: dict) -> dict:
        m = motion(e["file"], e["start"], e["duration"])
        m["focus_head"] = focus(e["file"], e["start"] + 0.02)
        m["focus_tail"] = focus(e["file"], e["start"] + e["duration"] - 0.06)
        return m

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(measure, pool))
    for e, m in zip(pool, results, strict=True):
        e.update(m)
        print(f"{e['id']:22s} head {direction(m['head']):5s} {m['head']}  tail {direction(m['tail']):5s} {m['tail']}"
              f"  strength {m['strength']}  focus {m['focus_head']} -> {m['focus_tail']}")
    args.pool.write_text(json.dumps(pool, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
