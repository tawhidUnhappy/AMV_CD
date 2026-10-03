"""The demucs Separator: each dialogue clip through Demucs (Meta's
open-source music/audio separation model, github.com/facebookresearch/demucs),
only the vocals stem kept (cut + cache: amv.audio.stems).

Model: $AMV_DEMUCS_MODEL, else settings "model", else htdemucs_ft (the
fine-tuned Hybrid Transformer: four models; vocals SDR 10.8 on MUSDB).
"""

from __future__ import annotations

import os

from amv.audio import stems


def model_name(settings: dict) -> str:
    return os.environ.get("AMV_DEMUCS_MODEL") or settings.get("model") or "htdemucs_ft"


def isolate(clips: list[dict], settings: dict) -> list[dict]:
    """The clips with file/stream/src pointing at their cached vocals stem."""
    model = model_name(settings)
    return stems.isolate(clips, "demucs", model, f"Demucs {model}", (model,))
