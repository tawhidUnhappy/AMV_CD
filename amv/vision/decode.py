"""Decode a stretch of an episode tiny, for measuring rather than looking.

A 96x54 (or smaller) frame is enough to tell a black frame from a face and a
static shot from a fight, at a fraction of the cost of a real decode. Clip
scoring, the intro's shot probe and its motion map all read footage this way.
"""

from __future__ import annotations

import subprocess

import numpy as np

# Coarse grid a frame is reduced to for match cutting (see
# amv.render.select_clips.scoring.match_score). Deliberately tiny: the question
# is "is the mass in the same part of frame", not "are these the same picture",
# and a fine grid would only ever match a shot against itself.
SIG_ROWS, SIG_COLS = 3, 4


def decode_tiny(path: str, width: int, height: int, *, start: float | None = None, duration: float | None = None,
                fps: float | None = None, gray: bool = False, gpu: bool = True) -> np.ndarray:
    """Frames as uint8, shape (n, height, width, 3) - or (n, height, width)
    with `gray`. Empty (n == 0) when neither decoder could read it.

    NVDEC first (unless `gpu` is off); it refuses a handful of streams a
    software decoder tolerates (an odd profile/level, a corrupt-ish GOP), so
    each call falls back to the CPU on its own rather than letting one bad clip
    zero out a whole run.
    """
    seek = [] if start is None else ["-ss", f"{start:.3f}"]
    span = [] if duration is None else ["-t", f"{duration:.3f}"]
    filters = ([f"fps={fps}"] if fps else []) + [f"scale={width}:{height}", "format=gray" if gray else "format=rgb24"]
    # Without an fps filter every decoded frame is wanted exactly once. The
    # default constant-rate output duplicates a frame to cover a start offset
    # (these releases start at 7ms), which shifts every frame after it by one.
    timing = [] if fps else ["-fps_mode", "passthrough"]
    tail = [*seek, *span, "-i", path, "-an", "-sn", "-vf", ",".join(filters), *timing, "-f", "rawvideo", "-"]
    data = b""
    decoders = [["ffmpeg", "-hwaccel", "cuda", "-v", "error"]] if gpu else []
    for prefix in [*decoders, ["ffmpeg", "-v", "error"]]:
        result = subprocess.run([*prefix, *tail], capture_output=True, check=False)
        if result.returncode == 0:
            data = result.stdout
            break
    channels = 1 if gray else 3
    frame_size = width * height * channels
    count = len(data) // frame_size
    shape = (count, height, width) if gray else (count, height, width, 3)
    return np.frombuffer(data[: count * frame_size], dtype=np.uint8).reshape(shape)


def luma(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luma, 0-1 float32, from uint8 RGB frames."""
    rgb = rgb.astype(np.int16)
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float32) / 255.0


def grid_signature(frames: np.ndarray) -> list[float]:
    """The average of a block of luma frames, reduced to SIG_ROWS x SIG_COLS."""
    frame = frames.mean(axis=0)
    rows = np.array_split(frame, SIG_ROWS, axis=0)
    return [float(cell.mean()) for row in rows for cell in np.array_split(row, SIG_COLS, axis=1)]
