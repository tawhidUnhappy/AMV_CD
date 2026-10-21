"""What each kind of plug-in describes. Every field that is code is a
reference ("module:attr", see _registry.resolve), so registering imports
nothing heavy.

    command      Command     - a `./amv.sh <name>` command
    tool         Tool        - an isolated uv environment a worker runs in
    song_generator SongGenerator - makes a new song from a prompt (+ lyrics)
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
    the project's own environment. `worker` is the path of the script it runs.

    A tool that cannot be a package list (its own repo, lock file, weights)
    sets itself up instead, like remanga's tools: `install` is (settings,
    force) -> None and builds its environment, `weights` is (settings) -> None
    and fetches its models, `interpreter` is (settings) -> Path of the python
    the worker runs on. Each is quick when already done. Settings come from
    config.json "tools": {name: {...}}; `./amv.sh tool-setup` runs both."""

    name: str
    packages: tuple[str, ...]
    worker: str
    python: str = "3.12"
    order: int = 100
    install: Ref = None
    weights: Ref = None
    interpreter: Ref = None
    index: str = ""          # an extra package index (e.g. PyTorch's CUDA wheels), searched with PyPI


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


@dataclass(frozen=True)
class SongGenerator:
    """A new song from a description. `generate` is (request, settings) ->
    {"files": [paths], ...}; request holds prompt, lyrics, instrumental,
    duration, bpm, key, language, count, seed and out_dir (amv.audio.song_gen).
    config.json "song_generator" picks one; settings come from
    config.json "song_generators": {name: {...}}."""

    name: str
    summary: str
    generate: Ref
    order: int = 100
