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
from amv.thumbnail.colors import WHITE
from amv.thumbnail.fonts import BRUSH_FONT
from amv.thumbnail.shapes import Arrow, Bubble
from amv.thumbnail.text import Text

ROOT = config.ROOT
CAND = ROOT / "data" / "qa" / "thumbcand"
OUT_DIR = ROOT / "data" / "out" / "thumbnails"

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
    return [
        # 1. label-arrow, two labels — the proven house variant. cand04 has both
        # characters facing camera; cand00 showed Yuno from behind, so the
        # YANDERE label pointed at the back of her head.
        Thumb(
            name="01_label_arrow",
            source=CAND / "cand04.png",
            texts=[
                Text("HER\nOBSESSION", 250, 130, an=5, size=88, angle=-4.0),
                Text("YANDERE", 1000, 150, an=5, size=104, angle=3.0),
            ],
            # Targets read off the rendered frame, not guessed: Yuki's face sits
            # at ~(310,265) and Yuno's at ~(1040,355). The angle follows.
            arrows=[
                Arrow(from_xy=(250, 200), to_xy=(310, 265), along=0.75, scale=1.0),
                Arrow(from_xy=(1000, 215), to_xy=(1040, 350), along=0.72, scale=1.0),
            ],
        ),
        # 2. bubble — a line pulled straight from the song, in a dark bubble
        # with white brush text.
        Thumb(
            name="02_bubble",
            source=CAND / "cand05.png",
            bubbles=[Bubble(x=330, y=215, width=560, height=250, tail_dx=150, tail_dy=215, angle=-3.0)],
            texts=[
                Text("AM I A\nMONSTER?", 330, 200, an=5, size=96, colour=WHITE, angle=-3.0,
                     font=BRUSH_FONT, outline=0),
                Text("MIRAI NIKKI AMV", 300, 650, an=5, size=58, angle=-2.0),
            ],
        ),
        # 3. split — two frames, a label under each, badge top-centre.
        Thumb(
            name="03_split",
            # cand09 framed Yuno too high to survive a half-width crop — her
            # face kept landing above the cut. cand05 centres her instead.
            source=CAND / "cand05.png",
            right_source=CAND / "cand07.png",
            left_zoom=1.15,
            left_shift=0.52,
            left_vshift=0.30,
            right_zoom=1.05,
            right_shift=0.55,
            right_vshift=0.35,
            texts=[
                Text("MIRAI NIKKI", 640, 68, an=5, size=58, colour=WHITE, angle=0.0),
                Text("THE STALKER", 320, 630, an=5, size=76, angle=-3.0),
                Text("THE PREY", 960, 630, an=5, size=76, angle=3.0),
            ],
        ),
    ]
