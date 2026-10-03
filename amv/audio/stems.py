"""Cut dialogue clips out of their episodes and run a separator tool over
them, caching each voices stem - shared by the separator plug-ins.

Each clip is cut with PAD s either side (context for the model at the
edges) and its stem cached in workspace/tmp/shorts/cache/vocals/ by
file|stream|start|length|model, so a re-render costs nothing.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from amv.core import paths, tools

PAD = 1.0
SR = 44100
DIR = paths.TMP / "shorts" / "cache" / "vocals"


def isolate(clips: list[dict], tool: str, model: str, label: str, tool_args: tuple[str, ...] = ()) -> list[dict]:
    """The clips with file/stream/src pointing at their cached voices stem.
    The tool's worker is called as: worker *tool_args in1.wav out1.wav ..."""
    DIR.mkdir(parents=True, exist_ok=True)
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
            print(f"Separating voices from {len(todo)} dialogue clip(s) ({label})...", flush=True)
            done = tools.run(tool, *tool_args, *args)
            if done.returncode != 0:
                raise SystemExit(f"vocal separation failed:\n{done.stderr[-3000:]}")
        for _, _, _, wav in todo:
            wav.with_suffix(".part.wav").replace(wav)
    return out
