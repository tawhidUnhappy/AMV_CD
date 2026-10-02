"""An example drop-in plug-in: a picture effect for Shorts. Rename it without
the leading "_" to load it, then use it in a spec: "video_fx": ["vignette"].

A plug-in registers itself on import; `./amv.sh plugins` shows it."""

import numpy as np

from amv.plugins import VideoFx, register


def vignette(f: np.ndarray, frame: np.ndarray, settings: dict, n: int) -> np.ndarray:
    h, w = f.shape[:2]
    y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
    fall = 1 - float(settings["strength"]) * np.clip(np.sqrt(x * x + y * y) - 0.4, 0, 1)
    return f * fall[..., None]


register("video_fx", VideoFx("vignette", "darker corners", vignette, {"strength": 0.5}, order=50))
