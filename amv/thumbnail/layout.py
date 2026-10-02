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

from amv.core import paths
from amv.thumbnail.shapes import Arrow, Bubble
from amv.thumbnail.text import Text

CAND = paths.QA / "thumbcand"
OUT_DIR = paths.THUMBNAILS

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
    """The active project's thumbnails (amv.core.project: "thumbnails").

    Each: {"name", "source": a frame in tmp/qa/thumbcand/ (./amv.sh
    thumb-candidates) or a path, "texts": [{"text", "x", "y", "an", "size",
    "colour": yellow|white|red|black or "&H..&", "angle"}], optional "arrows" /
    "bubbles" (Arrow / Bubble fields), "right_source" and the Thumb framing
    fields}. Positions are 1280x720 - read them off a render, don't guess.
    """
    from amv.core import project
    from amv.thumbnail import colors

    named = {k.lower(): v for k, v in vars(colors).items() if isinstance(v, str) and v.startswith("&H")}
    out = []
    for t in project.required("thumbnails"):
        extra = {k: v for k, v in t.items() if k not in ("name", "source", "texts", "arrows", "bubbles", "right_source")}
        texts = [Text(x["text"], x["x"], x["y"], **{k: (named.get(v, v) if k == "colour" else v)
                                                     for k, v in x.items() if k not in ("text", "x", "y")})
                 for x in t.get("texts", [])]
        out.append(Thumb(name=t["name"], source=_frame(t["source"]), texts=texts,
                         arrows=[Arrow(**a) for a in t.get("arrows", [])],
                         bubbles=[Bubble(**b) for b in t.get("bubbles", [])],
                         right_source=_frame(t["right_source"]) if t.get("right_source") else None, **extra))
    return out


def _frame(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() else CAND / name
