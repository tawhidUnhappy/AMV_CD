"""The roformer Separator: an ensemble of RoFormer vocal models, their
vocals averaged sample by sample (the models are phase-coherent, so the
average keeps the voice and halves each model's own bleed)."""

from __future__ import annotations

import os

from amv.audio import stems
from amv.core import paths

# The top of audio-separator's vocal ranking (MUSDB vocals SDR):
# Kim's Mel-Band RoFormer 12.6, unwa's Big Beta 4 12.5, BS-RoFormer viperx-1296 12.1.
MODELS = ("vocals_mel_band_roformer.ckpt", "melband_roformer_big_beta4.ckpt",
          "model_bs_roformer_ep_368_sdr_12.9628.ckpt")
MODEL_DIR = paths.TMP / "models" / "audio-separator"


def models(settings: dict) -> list[str]:
    env = os.environ.get("AMV_ROFORMER_MODELS")
    return env.split(",") if env else list(settings.get("models") or MODELS)


def isolate(clips: list[dict], settings: dict) -> list[dict]:
    names = models(settings)
    overlap = str(int(settings.get("overlap", 8)))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    key = "+".join(names) + f"@o{overlap}"
    return stems.isolate(clips, "audio_separator", key, f"RoFormer x{len(names)}",
                         (str(MODEL_DIR), overlap, ",".join(names)))
