"""One entry point for every stage and tool: `python -m amv <command> [args]`.

    ./amv.sh list                 # every command, grouped, with what it needs
    ./amv.sh select --candidates 8
    ./amv.sh remake --spec amv/intro/remakes/mushoku_ep1_recap.json

Each command is a module with its own --help; this only finds it and runs it
as __main__, so `python -m amv.render.pipeline` still works the same.
Commands marked "gpu" import torch (Demucs, WhisperX, the PGS OCR model) and
need the full environment (`uv sync`); ./amv.sh runs everything else in a
small cached environment of numpy/librosa/pillow/scipy.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
import warnings

# name: (module, needs the gpu environment, one line)
COMMANDS: dict[str, tuple[str, bool, str]] = {
    # song
    "vocals": ("amv.audio.isolate_vocals", True, "Demucs -> tmp/song/vocals.wav"),
    "transcribe": ("amv.audio.transcribe_song", True, "WhisperX word timings of the vocal stem"),
    "beats": ("amv.audio.beats", False, "librosa beat grid -> tmp/song/beats.json"),
    "words": ("amv.subs.dump_words", False, "numbered transcript words, for writing amv/audio/lyrics.py"),
    # source
    "subs": ("amv.subs.extract_subs", True, "episode subtitles (OCR for bitmap tracks) -> scene index"),
    # the edit
    "timeline": ("amv.render.timeline", False, "print the cut schedule"),
    "select": ("amv.render.select_clips", False, "fill every slot -> tmp/edl.json"),
    "lyrics": ("amv.render.lyric_overlay", False, "lyric overlay -> tmp/work/lyrics.ass (reads the EDL)"),
    "render": ("amv.render.pipeline", False, "grade, join, burn lyrics, mux -> tmp/out/amv.mp4"),
    # look at it
    "sheet": ("amv.vision.contact_sheet", False, "contact sheets of an EDL (one frame per slot)"),
    "strip": ("amv.vision.strip", False, "start/middle/end of every slot of an EDL, one row each"),
    "compare": ("amv.vision.compare", False, "two videos frame by frame: correlation report + sheet"),
    "exposure": ("amv.vision.check_exposure", False, "near-black / blown runtime of a render"),
    "grade-preview": ("amv.render.grade_preview", False, "graded vs raw frames, no render"),
    "fonts": ("amv.render.font_compare", False, "candidate lyric fonts over a real frame"),
    "check-timing": ("amv.subs.check_lyric_timing", False, "does the lyric text sit over singing"),
    "check-sync": ("amv.subs.check_sync", False, "A/V offset of a render against the song"),
    # extras
    "thumbs": ("amv.thumbnail", False, "YouTube thumbnails from real frames"),
    "thumb-candidates": ("amv.vision.thumb_candidates", False, "strong frames to build thumbnails from"),
    "intro": ("amv.intro", False, "a new short intro cut to the opening of a track"),
    "reference": ("amv.intro.reference", False, "which episode frame is behind every frame of a video"),
    "remake": ("amv.intro.remake", False, "render a remake of an existing intro from a spec or plan"),
    "dialogue": ("amv.intro.dialogue", False, "every show's subtitle lines, cached; --find REGEX to search them"),
    "montage": ("amv.intro.montage", False, "render an editor-style montage from a shot list (dissolves, punches)"),
    # upkeep
    "config": ("amv.core.config", False, "print the resolved config.json"),
    "regress": ("amv.core.regress", False, "snapshot / check pipeline outputs around a refactor"),
}


def usage() -> str:
    width = max(map(len, COMMANDS))
    lines = ["usage: python -m amv <command> [args]   (each command has --help)", ""]
    for name, (module, gpu, text) in COMMANDS.items():
        lines.append(f"  {name:<{width}}  {'gpu ' if gpu else '    '}{text}  [{module}]")
    lines += ["", "gpu = needs the full environment: `uv sync`, then AMV_FULL=1 ./amv.sh <command>"]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("list", "-h", "--help", "help"):
        print(usage())
        return
    name = sys.argv[1]
    if name not in COMMANDS:
        raise SystemExit(f"unknown command {name!r}\n\n{usage()}")
    module, gpu, _ = COMMANDS[name]
    if gpu and importlib.util.find_spec("torch") is None:
        raise SystemExit(f"'{name}' needs torch, which this environment does not have.\n"
                         "Run `uv sync` once, then: AMV_FULL=1 ./amv.sh " + " ".join(sys.argv[1:]))
    sys.argv = [f"amv {name}", *sys.argv[2:]]
    # runpy warns when the module was already imported as a dependency (e.g.
    # amv.core.config); running it again as __main__ is exactly what we want.
    warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
