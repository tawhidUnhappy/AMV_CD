"""Centralized torch device selection and CUDA memory hygiene.

Both isolate_vocals.py (Demucs) and transcribe_song.py (WhisperX) used to each
hardcode `--device cuda` and simply trust the caller to know better - on a
machine without a usable CUDA install that dies deep inside the model load
instead of failing predictably. Centralizing the choice here means the
fallback logic (and any future device-selection tweaks) lives in one place
instead of drifting between the two scripts.
"""

from __future__ import annotations


def select_device(preferred: str = "cuda") -> str:
    """Return `preferred` if it is actually usable, else fall back to CPU.

    Only "cuda" is checked against `torch.cuda.is_available()` - anything else
    the caller passes explicitly (e.g. "cpu") is returned unchanged.
    """
    if preferred != "cuda":
        return preferred

    import torch

    if torch.cuda.is_available():
        return "cuda"
    print("CUDA not available, falling back to CPU", flush=True)
    return "cpu"


def release_cuda_memory(device: str) -> None:
    """Free cached CUDA allocations between GPU stages of a long-lived process.

    A single `uv run` invocation only ever runs one model here, but keeping
    this as a named, reusable step means a future pipeline that chains
    Demucs -> WhisperX in one process (rather than two separate CLI
    invocations) does not have to rediscover the OOM this avoids.
    """
    if device != "cuda":
        return
    import gc

    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
