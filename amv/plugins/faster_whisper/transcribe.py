"""The faster_whisper Transcriber: one model load for a batch of wavs."""

from __future__ import annotations

import json
import os

from amv.core import tools


def model_name(settings: dict) -> str:
    return os.environ.get("AMV_WHISPER_MODEL") or settings.get("model") or "large-v3"


def transcribe(wavs: list[str], settings: dict) -> dict[str, list[list]]:
    print(f"Transcribing {len(wavs)} dub segment(s) (faster-whisper {model_name(settings)})...", flush=True)
    done = tools.run("faster_whisper", model_name(settings), *wavs)
    if done.returncode != 0:
        raise SystemExit(f"dub transcription failed:\n{done.stderr[-2000:]}")
    return json.loads(done.stdout)
