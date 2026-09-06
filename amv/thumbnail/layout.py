"""The `Thumb` composition dataclass, face-finding, and the house presets.

House style used here: big ALL-CAPS yellow #FFE600 labels, black stroke ~12% of
font size, slight tilt, fat block arrows pointing at the character each label
names, and the bottom-right corner left clear for YouTube's duration overlay.
If you have your own reference thumbnails, calibrate against those first.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from amv.core import config
from amv.thumbnail.colors import RED, WHITE, YELLOW
from amv.thumbnail.shapes import Arrow, Bubble
from amv.thumbnail.text import Text

ROOT = config.ROOT
CAND = ROOT / "tmp" / "qa" / "thumbcand"
OUT_DIR = ROOT / "tmp" / "out" / "thumbnails"

WIDTH, HEIGHT = 1280, 720


@dataclass
class Thumb:
    name: str
    source: Path
    texts: list[Text] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)
    bubbles: list[Bubble] = field(default_factory=list)
    #: Optional second frame for the side-by-side split layout.
    right_source: Path | None = None
    #: Zoom and horizontal framing per split panel. A half-width crop of a 16:9
    #: frame has only horizontal slack, so zoom in first to place a face.
    left_zoom: float = 1.0
    left_shift: float = 0.5    # 0 = crop hard left, 1 = hard right
    left_vshift: float = 0.5   # 0 = crop hard top, 1 = hard bottom
    right_zoom: float = 1.0
    right_shift: float = 0.5
    right_vshift: float = 0.5
    #: Extra punch so the thumbnail reads at sidebar size.
    grade: str = "eq=contrast=1.10:saturation=1.25:brightness=0.02,unsharp=5:5:0.6:5:5:0.0"


def face_targets(image: Path, halves: int = 2) -> list[tuple[int, int]]:
    """Best-effort face position per vertical band, in 1280x720 coordinates.

    UNRELIABLE ON WARM SOURCES — do not trust it blind. Tan interiors, wood
    panelling and sunset light all satisfy the skin predicate, so the density
    peak lands on a wall. It works on frames with cool or dark backgrounds and
    is useless on warm ones.

    Treat the output as a hint, set `Arrow.to_xy` from what you actually see in
    the rendered thumbnail, and verify by looking at the result either way.
    """
    import numpy as np

    from amv.vision.skin import skin_mask

    w, h = 128, 72
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(image),
         "-vf", f"scale={w}:{h},format=rgb24", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    )
    rgb = np.frombuffer(result.stdout[: w * h * 3], dtype=np.uint8).reshape(h, w, 3).astype(np.int16)
    skin = skin_mask(rgb).astype(np.float32)

    # Densest compact patch, not the centroid: a centroid is dragged toward
    # arms and torso and lands on a character's chest or on empty background
    # between two people. A face is the tightest concentration of skin, so a
    # box-sum peak finds it far more reliably.
    box = 11
    kernel = np.ones((box, box), dtype=np.float32)
    padded = np.pad(skin, box // 2, mode="constant")
    density = np.zeros_like(skin)
    for dy in range(box):
        for dx in range(box):
            density += padded[dy : dy + h, dx : dx + w] * kernel[dy, dx]

    targets: list[tuple[int, int]] = []
    band = w // halves
    for i in range(halves):
        lo, hi = i * band, (i + 1) * band
        chunk = density[:, lo:hi]
        if chunk.max() < box:  # too little skin to call a face
            continue
        py, px = np.unravel_index(int(np.argmax(chunk)), chunk.shape)
        targets.append((int((px + lo) / w * WIDTH), int(py / h * HEIGHT)))
    return targets


def thumbnails() -> list[Thumb]:
    """Mushoku Tensei x "Who I Am Anymore".

    cand01 is the frame this is built around: Rudeus in profile hard left,
    facing right across an open desert horizon. Two things make it work as a
    thumbnail — the right two-thirds is empty enough to carry text without
    covering anything, and his eyeline runs *into* that space, so the reader's
    eye follows him to the words instead of away from them.

    Text sits right of centre, white with the single payoff word in red, and
    stops well above the bottom-right corner so YouTube's duration chip has
    somewhere to land.
    """
    return [
        Thumb(
            name="01_who_am_i",
            source=CAND / "cand01.png",
            texts=[
                # Positions read off the rendered 1280x720 frame: Rudeus's head
                # runs to about x=700, so the block is centred at x=980 and
                # clears him at every size below.
                Text("WHO AM I", 980, 232, an=5, size=112, colour=WHITE, angle=-3.0),
                Text("ANYMORE", 980, 358, an=5, size=124, colour=RED, angle=-3.0),
                Text("MUSHOKU TENSEI AMV", 980, 470, an=5, size=40, colour=YELLOW, angle=-3.0),
            ],
        ),
    ]
