"""Separate the vocal stem with Demucs before transcription.

Whisper on a full mix produced misaligned and missing lyrics: the opening "I"
landed at 2.71s with a 0.02s duration and "woke" stretched across 3.3s of
instrumental, so the first block appeared long before it is sung. Running ASR on
an isolated vocal removes the instrumentation that causes both failures.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from amv.core import config

ROOT = config.ROOT
DEFAULT_OUT = ROOT / "tmp" / "song" / "vocals.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song", type=Path, default=None,
                        help="input track (default: song from config.json)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    song = args.song or config.load().require_song()

    from amv.audio import torch_compat
    from amv.audio.device import release_cuda_memory, select_device

    torch_compat.patch()

    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    device = select_device(args.device)

    model = get_model(args.model)
    model.to(device).eval()
    print(f"{args.model}: sources={model.sources} sr={model.samplerate} device={device}", flush=True)

    waveform, sample_rate = torchaudio.load(str(song))
    if sample_rate != model.samplerate:
        waveform = torchaudio.functional.resample(waveform, sample_rate, model.samplerate)
    if waveform.shape[0] == 1:
        waveform = waveform.repeat(2, 1)

    # Demucs expects (batch, channels, samples) normalised per track.
    reference = waveform.mean(0)
    mean, std = reference.mean(), reference.std()
    normalised = (waveform - mean) / (std + 1e-8)

    # inference_mode is strictly stronger than no_grad (also disables version
    # counter bookkeeping) and this is a pure forward pass, never backward.
    with torch.inference_mode():
        stems = apply_model(
            model,
            normalised[None].to(device),
            device=device,
            split=True,
            overlap=0.25,
            progress=True,
        )[0]
    stems = stems * std + mean

    # This is the one CPU round-trip that has to happen: torchaudio.save needs
    # a CPU tensor. Everything upstream of it stays on-device.
    vocals = stems[model.sources.index("vocals")].cpu()
    samplerate = model.samplerate
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(args.out), vocals, samplerate)

    # Release the Demucs weights/activations before any later GPU stage in this
    # process (e.g. a caller chaining straight into transcribe_song.main()).
    del model, stems
    release_cuda_memory(device)

    peak = float(vocals.abs().max())
    print(f"\nWrote {args.out}  ({vocals.shape[1] / samplerate:.2f}s, peak {peak:.3f})", flush=True)


if __name__ == "__main__":
    main()
