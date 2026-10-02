"""Demucs over a list of wav files -> the vocals stem of each (wav beside it).

Runs in its own cached tool environment (see amv.shorts.vocals.RUN): torch +
demucs, separate from the light env. Reads/writes with soundfile, not
torchaudio's I/O (its backends vary by version).

    python vocals_worker.py MODEL in1.wav out1.wav in2.wav out2.wav ...
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("TQDM_DISABLE", "1")


def main() -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    name, pairs = sys.argv[1], sys.argv[2:]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = get_model(name)
    model.to(device).eval()
    vocals = model.sources.index("vocals")
    for src, dst in zip(pairs[::2], pairs[1::2], strict=True):
        data, sr = sf.read(src, dtype="float32", always_2d=True)
        if sr != model.samplerate:
            raise SystemExit(f"{src}: {sr} Hz, the model wants {model.samplerate}")
        wav = torch.from_numpy(np.ascontiguousarray(data.T))
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        with torch.inference_mode():
            stems = apply_model(model, ((wav - mean) / std)[None], device=device, shifts=1, split=True,
                                overlap=0.25, progress=False)
        out = (stems[0, vocals] * std + mean).cpu().numpy().T
        sf.write(dst, out, sr, subtype="FLOAT")
        print(dst, flush=True)
    if device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
