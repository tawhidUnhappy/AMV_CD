"""What each kind of plug-in describes. Every field that is code is a
reference ("module:attr", see _registry.resolve), so registering imports
nothing heavy.

    command      Command     - a `./amv.sh <name>` command
    tool         Tool        - an isolated uv environment a worker runs in
    separator    Separator   - pulls the voices out of a dialogue clip
    transcriber  Transcriber - word timings of spoken audio
    song_fx      SongFx      - a whole-song effect (slowed, nightcore, ...)
    video_fx     VideoFx     - a per-frame picture effect (outline, glow, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Ref = Any   # "package.module:attr", or the object itself


@dataclass(frozen=True)
class Command:
    """`./amv.sh <name>`: runs `module` as __main__ with the remaining args.
    `gpu` commands need torch in the project environment (AMV_FULL=1)."""

    name: str
    module: str
    help: str
    group: str = "extras"
    gpu: bool = False
    order: int = 100


@dataclass(frozen=True)
class Tool:
    """An isolated environment: `uv run --no-project --python <python>
    --with <each package>` - built on first use, cached by uv, never touching
    the project's own environment. `worker` is the script it runs."""

    name: str
    packages: tuple[str, ...]
    worker: str
    python: str = "3.12"
    order: int = 100


@dataclass(frozen=True)
class Separator:
    """Voices only. `isolate` is (clips, settings) -> clips: each clip dict
    ({"file", "stream", "src", "dur", ...}) pointed at a file holding only its
    voices. config.json "separator" picks one; settings come from
    config.json "separators": {name: {...}}."""

    name: str
    summary: str
    isolate: Ref
    order: int = 100


@dataclass(frozen=True)
class Transcriber:
    """Word timings. `transcribe` is (wav_paths, settings) ->
    {wav: [[start, end, word], ...]}, seconds from each file's start."""

    name: str
    summary: str
    transcribe: Ref
    order: int = 100


@dataclass(frozen=True)
class SongFx:
    """A whole-song effect, rendered once to a cached wav and analysed as the
    song from then on. `chain` is (sample_rate, settings) -> an ffmpeg -af
    chain; `label` goes in the description ("Slowed + Reverb edit")."""

    name: str
    label: str
    chain: Ref
    defaults: dict = field(default_factory=dict)
    order: int = 100


@dataclass(frozen=True)
class VideoFx:
    """A picture effect: `apply` is (frame float32 HxWx3, original uint8
    frame, settings, frame number) -> float32 frame. Effects run in `order`."""

    name: str
    summary: str
    apply: Ref
    defaults: dict = field(default_factory=dict)
    order: int = 100
