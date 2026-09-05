"""Shared 'is this pixel skin' heuristic.

Anime skin renders as bright, warm, R > G > B with a modest tonal spread.
Calibrated (see calibrate_skin.py) to separate character shots from scenery
and text screens on average, though the tails overlap: warm food reads as
skin, and an unlit night shot reads as none. Used as a weighted signal, never
a hard gate, everywhere it appears: clip selection, lyric-block placement,
thumbnail face-finding, and the calibration script itself.

Kept as one function so the four call sites cannot drift apart from each
other.
"""

from __future__ import annotations

import numpy as np


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Boolean skin mask for an (..., 3) RGB array (any integer dtype).

    Callers should pass a wide-enough dtype (int16 or better) so `r - b` and
    `mx - mn` do not wrap; raw `uint8` frames straight off ffmpeg must be cast
    first.
    """
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    return (r > 110) & (g > 70) & (b > 50) & (r > g) & (g >= b) & ((mx - mn) > 14) & ((r - b) > 18) & (r < 252)


def skin_fraction(rgb: np.ndarray) -> float:
    """Fraction of pixels in an (..., 3) RGB array classified as skin."""
    return float(skin_mask(rgb.astype(np.int16)).mean())
