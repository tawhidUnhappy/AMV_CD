"""ASS drawing-command shapes: the block arrow and the speech bubble.

Text and arrows are drawn through libass, which gives rotation, thick outlines
and vector shapes in a single pass — ffmpeg's drawtext cannot rotate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from amv.thumbnail.colors import YELLOW


@dataclass
class Arrow:
    """Fat block arrow.

    Give it `from_xy` (usually the label) and `to_xy` (the thing it names) and
    the position and angle are computed. Hand-guessing `x/y/angle` is what put
    the first batch of arrows on the wrong side of the frame and pointing at the
    back of a character's head — use `face_targets()` to find the real subject.
    """

    from_xy: tuple[int, int] | None = None
    to_xy: tuple[int, int] | None = None
    #: Fraction of the way from `from_xy` to `to_xy` at which to sit.
    along: float = 0.55
    #: Explicit placement, only for cases with no sensible target.
    x: int = 0
    y: int = 0
    angle: float = 0.0
    scale: float = 1.0
    colour: str = YELLOW

    def resolve(self) -> tuple[int, int, float]:
        if self.from_xy is None or self.to_xy is None:
            return self.x, self.y, self.angle
        fx, fy = self.from_xy
        tx, ty = self.to_xy
        px = int(fx + (tx - fx) * self.along)
        py = int(fy + (ty - fy) * self.along)
        angle = math.degrees(math.atan2(ty - fy, tx - fx))
        return px, py, angle


@dataclass
class Bubble:
    """Dark speech bubble sized to the text that sits on it."""

    x: int
    y: int
    width: int
    height: int
    tail_dx: int = 120
    tail_dy: int = 90
    angle: float = 0.0
    fill: str = "&H00101010&"


def arrow_shape(scale: float) -> str:
    """A chunky right-pointing arrow as ASS drawing commands."""
    s = scale
    pts = [(0, -18), (52, -18), (52, -40), (104, 0), (52, 40), (52, 18), (0, 18)]
    body = " ".join(f"l {int(x * s)} {int(y * s)}" for x, y in pts[1:])
    return f"m {int(pts[0][0] * s)} {int(pts[0][1] * s)} {body}"


def bubble_shape(bubble: Bubble) -> str:
    """Rounded speech bubble with a tail, in absolute screen coordinates.

    Drawn absolutely and anchored with \\an7\\pos(0,0): ASS centres a drawing by
    its *bounding box*, so a long tail under an \\an5 anchor drags the whole
    bubble off its intended spot.
    """
    left, right = bubble.x - bubble.width // 2, bubble.x + bubble.width // 2
    top, bottom = bubble.y - bubble.height // 2, bubble.y + bubble.height // 2
    r = min(46, bubble.height // 4, bubble.width // 4)
    tx, ty = bubble.x + bubble.tail_dx, bubble.y + bubble.tail_dy
    return (
        f"m {left + r} {top} "
        f"l {right - r} {top} b {right} {top} {right} {top} {right} {top + r} "
        f"l {right} {bottom - r} b {right} {bottom} {right} {bottom} {right - r} {bottom} "
        f"l {tx + 45} {bottom} l {tx} {ty} l {tx - 55} {bottom} "
        f"l {left + r} {bottom} b {left} {bottom} {left} {bottom} {left} {bottom - r} "
        f"l {left} {top + r} b {left} {top} {left} {top} {left + r} {top}"
    )
