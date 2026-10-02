"""Voices only: the story/outro dialogue with the episode's own background
music and effects removed, so the Short's song is the only music under it.

Each dialogue clip is cut from the episode (with PAD s either side, so the
model has context at the edges), run through Demucs (Meta's open-source
music/audio separation model, github.com/facebookresearch/demucs) and only
the vocals stem is kept. Stems are cached in tmp/shorts/cache/vocals/ by
file|stream|start|length|model, so a re-render costs nothing.

Model: $AMV_DEMUCS_MODEL, else htdemucs_ft (the fine-tuned Hybrid
Transformer: four models, the cleanest vocals; ~4x the time of htdemucs,
seconds per clip on the GPU). Spec "dialogue_only": false keeps the full mix.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from amv.shorts import catalog

PAD = 1.0
SR = 44100
DIR = catalog.CACHE / "vocals"
RUN = ["uv", "run", "-q", "--no-project", "--python", "3.12", "--with", "demucs", "--with", "soundfile",
       "python", str(Path(__file__).with_name("vocals_worker.py"))]


def model_name() -> str:
    return os.environ.get("AMV_DEMUCS_MODEL", "htdemucs_ft")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """The tool env is cached after its first build; try it offline first
    (uv re-resolves every run and a slow PyPI made that fail), then online."""
    done = subprocess.run(args, capture_output=True, text=True, env={**os.environ, "UV_OFFLINE": "1"})
    if done.returncode != 0:
        done = subprocess.run(args, capture_output=True, text=True)
    return done


def isolate(clips: list[dict]) -> list[dict]:
    """The clips with file/stream/src pointing at their cached vocals stem."""
    DIR.mkdir(parents=True, exist_ok=True)
    model = model_name()
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
            done = _run([*RUN, model, *args])
            if done.returncode != 0:
                raise SystemExit(f"vocal separation failed:\n{done.stderr[-2000:]}")
        for _, _, _, wav in todo:
            wav.with_suffix(".part.wav").replace(wav)
    return out
