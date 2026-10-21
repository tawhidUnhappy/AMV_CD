"""Forced alignment of known words to audio. Runs in the forced_align tool env.

    python worker.py job.json

job.json: {"wav": path, "out": path, "segments": [{"key", "t0", "t1", "words": [...]}]}
-> out: {key: [[start, end, score], ...] per word, seconds in the file} (a word
that cannot be spelled in the model's alphabet gets null)."""

from __future__ import annotations

import json
import re
import sys

import numpy as np
import soundfile as sf
import torch
import torchaudio


def main() -> None:
    job = json.loads(open(sys.argv[1], encoding="utf-8").read())
    bundle = torchaudio.pipelines.MMS_FA
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = bundle.get_model(with_star=False).to(dev).eval()
    tokenizer, aligner = bundle.get_tokenizer(), bundle.get_aligner()
    alphabet = set(bundle.get_dict()) - {"-", "*"}
    data, sr = sf.read(job["wav"], dtype="float32", always_2d=True)
    wave = torch.from_numpy(data.mean(axis=1))
    if sr != bundle.sample_rate:
        wave = torchaudio.functional.resample(wave, sr, bundle.sample_rate)
    sr = bundle.sample_rate
    out = {}
    for seg in job["segments"]:
        a, b = max(0, int(seg["t0"] * sr)), min(len(wave), int(seg["t1"] * sr))
        clean = [re.sub(r"[^a-z']", "", w.lower()) for w in seg["words"]]
        keep = [i for i, w in enumerate(clean) if w and set(w) <= alphabet]
        if b - a < sr // 4 or not keep:
            out[seg["key"]] = None
            continue
        with torch.inference_mode():
            emission, _ = model(wave[a:b][None].to(dev))
        spans = aligner(emission[0], tokenizer([clean[i] for i in keep]))
        per_frame = (b - a) / emission.shape[1] / sr
        words = [None] * len(clean)
        for i, sp in zip(keep, spans):
            score = float(np.mean([t.score for t in sp]))
            words[i] = [round(seg["t0"] + sp[0].start * per_frame, 3), round(seg["t0"] + sp[-1].end * per_frame, 3),
                        round(score, 3)]
        out[seg["key"]] = words
    open(job["out"], "w", encoding="utf-8").write(json.dumps(out))


if __name__ == "__main__":
    main()
