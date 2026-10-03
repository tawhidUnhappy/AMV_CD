"""RoFormer vocal separators (BS-RoFormer / Mel-Band RoFormer, through
python-audio-separator, github.com/nomadkaraoke/python-audio-separator):
the strongest open vocal models - vocals SDR 12.1-12.6 against 10.8 for
Demucs htdemucs_ft. Several models are run and their vocals averaged (an
ensemble), which cuts each model's own artefacts. Runs in its own uv
environment (torch + audio-separator); weights are downloaded once into
workspace/tmp/models/audio-separator/.

    separate.py   the Separator (cut + cache: amv.audio.stems)
    worker.py     the worker

Settings (config.json "separators": {"roformer": {...}}):
    models    model file names (audio-separator --list_models --list_filter=vocals);
              default: separate.MODELS
    overlap   chunk overlap (default 8; higher = slower, smoother seams)
"""

from pathlib import Path

from amv.plugins import Separator, Tool, register

register("tool", Tool("audio_separator", ("audio-separator[gpu]", "audioread", "soundfile"),
                      worker=str(Path(__file__).with_name("worker.py"))))
register("separator", Separator("roformer", "RoFormer vocals ensemble (Mel-Band + BS-RoFormer)",
                                "amv.plugins.roformer.separate:isolate", order=10))
