"""YouTube thumbnail composition: real frames, ASS-drawn text/arrows/bubbles.

- `colors` / `fonts`: shared ASS colour constants and font staging.
- `shapes`: the `Arrow` / `Bubble` drawing-command dataclasses.
- `text`: the `Text` caption dataclass.
- `layout`: the `Thumb` composition dataclass, face-finding, and the house
  presets (`thumbnails()`).
- `ass`: builds the ASS document text for one `Thumb`.
- `render`: runs ffmpeg+libass to turn a `Thumb` into a JPEG.
- `cli`: the `python -m amv.thumbnail` entry point.
"""

from __future__ import annotations

from amv.thumbnail.cli import main
from amv.thumbnail.layout import Thumb, face_targets, thumbnails
from amv.thumbnail.render import render
from amv.thumbnail.shapes import Arrow, Bubble
from amv.thumbnail.text import Text

__all__ = ["main", "Thumb", "face_targets", "thumbnails", "render", "Arrow", "Bubble", "Text"]
