"""The `Text` label dataclass used to place a caption on a thumbnail."""

from __future__ import annotations

from dataclasses import dataclass

from amv.thumbnail.colors import YELLOW
from amv.thumbnail.fonts import LABEL_FONT


@dataclass
class Text:
    body: str
    x: int
    y: int
    an: int = 5
    size: int = 96
    colour: str = YELLOW
    angle: float = -3.0
    font: str = LABEL_FONT
    outline: float | None = None  # defaults to 12% of size
