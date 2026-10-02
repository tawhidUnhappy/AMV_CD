"""faster-whisper: word timings of spoken audio - what the English dub of a
story scene says, and where (amv.shorts.dub). Runs in its own uv environment.

    transcribe.py   the Transcriber
    worker.py       the worker (CTranslate2, no torch)

Settings (config.json "transcribers": {"faster_whisper": {...}}):
    model   a local CTranslate2 model folder or a Hub name (default large-v3;
            $AMV_WHISPER_MODEL overrides)"""

from pathlib import Path

from amv.plugins import Tool, Transcriber, register

register("tool", Tool("faster_whisper", ("faster-whisper", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"),
                      worker=str(Path(__file__).with_name("worker.py"))))
register("transcriber", Transcriber("faster_whisper", "faster-whisper large-v3, word timestamps",
                                    "amv.plugins.faster_whisper.transcribe:transcribe"))
