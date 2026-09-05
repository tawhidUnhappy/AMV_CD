"""Shared infrastructure: project configuration and ffmpeg/ffprobe helpers.

Everything else in the pipeline depends on this package; it must not import
from any other `amv` subpackage.
"""

from __future__ import annotations

from amv.core import config, ffmpeg_tools

__all__ = ["config", "ffmpeg_tools"]
