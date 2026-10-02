"""The demucs Separator. Each dialogue clip is cut from the episode (with PAD s either side, so the
model has context at the edges), run through Demucs (Meta's open-source
music/audio separation model, github.com/facebookresearch/demucs) and only
the vocals stem is kept. Stems are cached in workspace/tmp/shorts/cache/vocals/ by
file|stream|start|length|model, so a re-render costs nothing.

Model: $AMV_DEMUCS_MODEL, else settings "model", else htdemucs_ft (the
fine-tuned Hybrid Transformer: four models, the cleanest vocals; ~4x the
time of htdemucs, seconds per clip on the GPU).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from amv.core import paths, tools

PAD = 1.0
SR = 44100
DIR = paths.TMP / "shorts" / "cache" / "vocals"


def model_name(settings: dict) -> str:
    return os.environ.get("AMV_DEMUCS_MODEL") or settings.get("model") or "htdemucs_ft"


def isolate(clips: list[dict], settings: dict) -> list[dict]:
    """The clips with file/stream/src pointing at their cached vocals stem."""
    DIR.mkdir(parents=True, exist_ok=True)
    model = model_name(settings)
    out, todo = [], []
    for c in clips:
        t0 = max(0.0, c["src"] - PAD)
        length = c["src"] - t0 + c["dur"] + 0.2 + PAD
        key = f"{c['file']}|{c['stream']}|{t0:.3f}|{length:.3f}|{model}"
        wav = DIR / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".wav")
        if not wav.exists():
            todo.append((c, t0, length, wav))
        out.append({**c, "file": str(wav), "stream": 0, "src": round(c["src"] - t0, 3)})
    if todo:
        with tempfile.TemporaryDirectory() as tmp:
            args = []
            for k, (c, t0, length, wav) in enumerate(todo):
                raw = Path(tmp) / f"{k}.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{length:.3f}",
                                "-i", c["file"], "-map", f"0:a:{c['stream']}", "-ac", "2", "-ar", str(SR),
                                str(raw)], check=True)
                args += [str(raw), str(wav.with_suffix(".part.wav"))]
            print(f"Separating voices from {len(todo)} dialogue clip(s) (Demucs {model})...", flush=True)
            done = tools.run("demucs", model, *args)
            if done.returncode != 0:
                raise SystemExit(f"vocal separation failed:\n{done.stderr[-2000:]}")
        for _, _, _, wav in todo:
            wav.with_suffix(".part.wav").replace(wav)
    return out
