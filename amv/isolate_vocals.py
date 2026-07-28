"""Separate the vocal stem with Demucs before transcription.

Whisper on a full mix produced misaligned and missing lyrics: the opening "I"
landed at 2.71s with a 0.02s duration and "woke" stretched across 3.3s of
instrumental, so the first block appeared long before it is sung. Running ASR on
an isolated vocal removes the instrumentation that causes both failures.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SONG = ROOT / "assets" / "black_salt_halo.mp3"
DEFAULT_OUT = ROOT / "data" / "song" / "vocals.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", type=Path, default=DEFAULT_SONG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    from amv import torch_compat

    torch_compat.patch()

    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model(args.model)
    model.to(args.device).eval()
    print(f"{args.model}: sources={model.sources} sr={model.samplerate}", flush=True)

    waveform, sample_rate = torchaudio.load(str(args.song))
    if sample_rate != model.samplerate:
        waveform = torchaudio.functional.resample(waveform, sample_rate, model.samplerate)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)

    # Demucs expects (batch, channels, samples) normalised per track.
    reference = waveform.mean(0)
    mean, std = reference.mean(), reference.std()
    normalised = (waveform - mean) / (std + 1e-8)

    with torch.no_grad():
        stems = apply_model(
            model,
            normalised[None].to(args.device),
            device=args.device,
            split=True,
            overlap=0.25,
            progress=True,
        )[0]
    stems = stems * std + mean

    vocals = stems[model.sources.index("vocals")].cpu()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(args.out), vocals, model.samplerate)

    peak = float(vocals.abs().max())
    print(f"\nWrote {args.out}  ({vocals.shape[1] / model.samplerate:.2f}s, peak {peak:.3f})", flush=True)


if __name__ == "__main__":
    main()
