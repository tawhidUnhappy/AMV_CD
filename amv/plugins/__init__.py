"""AMV_CD's plug-ins: everything that comes in more than one flavour is a
plug-in, registered under its kind and found through the registry - nothing
in the pipeline names a particular engine or effect.

    kind         what one is                                   built in
    command      a ./amv.sh command (Command)                  commands
    tool         an isolated uv environment (Tool)             demucs, faster_whisper
    separator    voices out of a dialogue clip (Separator)     demucs
    transcriber  word timings of speech (Transcriber)          faster_whisper
    song_fx      a whole-song effect (SongFx)                  song_fx: slowed_reverb, slowed, nightcore, sped_up
    video_fx     a picture effect (VideoFx)                    video_fx: outline, glow, grain

Each built-in is a folder here holding all of its own code; its __init__.py
only registers descriptions (_kinds.py) that name that code by reference.
A plug-in of your own is a .py file or package in the repo's top-level
plugins/ folder, or an installed package with an `amv.plugins` entry point -
see _loader.py and plugins/README.md. `./amv.sh plugins` lists them all."""

from __future__ import annotations

from amv.plugins._kinds import Command, Separator, SongFx, Tool, Transcriber, VideoFx
from amv.plugins._loader import failures, load
from amv.plugins._registry import KINDS, call, find, get, items, names, origin, register, resolve

__all__ = ["KINDS", "Command", "Separator", "SongFx", "Tool", "Transcriber", "VideoFx", "call", "failures",
           "find", "get", "items", "load", "names", "origin", "register", "resolve"]
