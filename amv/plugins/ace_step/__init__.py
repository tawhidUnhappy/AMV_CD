"""ACE-Step 1.5 (github.com/ace-step/ACE-Step-1.5, MIT): full songs with vocals and
lyrics in 50+ languages, or instrumentals, from a text prompt - seconds per song on a
24 GB card, and it fits a 12 GB one (INT8 + CPU offload, picked by GPU tier).

    setup.py      its repo, environment and models (workspace/tools/ace_step)
    generate.py   the SongGenerator
    scripts/      the worker, run in ACE-Step's own environment

Settings, config.json "tools": {"ace_step": {...}} (where it lives):
    dir       install folder (default workspace/tools/ace_step)
    ref       ACE-Step commit (default setup.REF)
config.json "song_generators": {"ace_step": {...}} (how it generates):
    model     DiT: acestep-v15-turbo (default, 8 steps), -sft / -base (50 steps, slower)
    lm        planner LM: auto (by GPU tier: 0.6B up to 12 GB, 1.7B above), none, or a
              name (acestep-5Hz-lm-0.6B / -1.7B / -4B)
    backend   LM backend: auto (vllm on CUDA), vllm or pt
    steps     diffusion steps (default: 8 turbo, 50 others)
    guidance, adg, shift, dcw
              non-turbo quality knobs (default 7.0, false, 1.0, false; all on at once broke the
              singing, 2026-10-22 - try one at a time: song-gen --opt adg=true ...)
    format    wav (default), flac or mp3
"""

from pathlib import Path

from amv.plugins import SongGenerator, Tool, register

register("tool", Tool("ace_step", (), worker=str(Path(__file__).parent / "scripts" / "worker.py"),
                      install="amv.plugins.ace_step.setup:install",
                      weights="amv.plugins.ace_step.setup:weights",
                      interpreter="amv.plugins.ace_step.setup:interpreter"))
register("song_generator", SongGenerator("ace_step", "ACE-Step 1.5: songs with vocals or instrumentals",
                                         "amv.plugins.ace_step.generate:generate"))
