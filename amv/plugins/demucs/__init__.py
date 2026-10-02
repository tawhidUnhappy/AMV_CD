"""Demucs - Meta's open-source music/audio source separation
(github.com/facebookresearch/demucs): keeps only the voices of a dialogue
clip, so a Short's song is the only music under the story. Runs in its own
uv environment (torch + demucs).

    separate.py   the Separator (cut, separate, cache)
    worker.py     the worker

Settings (config.json "separators": {"demucs": {...}}):
    model   htdemucs_ft (default: four fine-tuned models, the cleanest
            vocals), htdemucs (4x faster), mdx_extra, ... ($AMV_DEMUCS_MODEL
            overrides)"""

from pathlib import Path

from amv.plugins import Separator, Tool, register

# Python 3.12: demucs' lameenc dependency has no cp311 wheel on PyPI.
register("tool", Tool("demucs", ("demucs", "soundfile"), worker=str(Path(__file__).with_name("worker.py"))))
register("separator", Separator("demucs", "Demucs vocals stem (htdemucs_ft)",
                                "amv.plugins.demucs.separate:isolate"))
