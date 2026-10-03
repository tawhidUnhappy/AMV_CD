"""The ensemble Separator: each member separator's stems, averaged."""

from __future__ import annotations

import hashlib

import numpy as np
import soundfile as sf

from amv.audio import stems

MEMBERS = {"roformer": 3.0, "demucs": 1.0}


def isolate(clips: list[dict], settings: dict) -> list[dict]:
    from amv import plugins
    from amv.core.config import load

    cfg = load()
    members = {k: float(v) for k, v in (settings.get("members") or MEMBERS).items()}
    runs = {name: plugins.call(plugins.get("separator", name).isolate, [dict(c) for c in clips],
                               cfg.plugin_settings("separator", name)) for name in members}
    total = sum(members.values())
    out = []
    for i in range(len(clips)):
        parts = {name: runs[name][i] for name in members}
        key = "|".join(f"{n}:{w:g}:{parts[n]['file']}" for n, w in members.items())
        wav = stems.DIR / ("ens_" + hashlib.sha1(key.encode()).hexdigest()[:16] + ".wav")
        first = parts[next(iter(members))]
        if not wav.exists():
            acc = None
            for name, w in members.items():  # every member's stem cut the same way (amv.audio.stems)
                data, sr = sf.read(parts[name]["file"], dtype="float32", always_2d=True)
                if acc is not None:
                    data = np.pad(data, ((0, max(0, len(acc) - len(data))), (0, 0)))[:len(acc)]
                acc = data * w if acc is None else acc + data * w
            sf.write(str(wav.with_suffix(".part.wav")), acc / total, sr, subtype="FLOAT")
            wav.with_suffix(".part.wav").replace(wav)
        out.append({**first, "file": str(wav)})
    return out
