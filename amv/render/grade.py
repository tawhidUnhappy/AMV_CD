"""The colour grade filter chain and the radial-focus mask used to apply it.

Split out of render.py so the "what does the picture look like" knowledge
(grade, focus falloff) is separate from the "how do the clips get encoded and
stitched together" pipeline mechanics in pipeline.py.
"""

from __future__ import annotations

from pathlib import Path

from amv.core import config

_CFG = config.load()
WIDTH, HEIGHT = _CFG.width, _CFG.height
FPS = _CFG.fps

# Colour grade (this replaced the earlier full grayscale pass): cool the
# shadows, warm the highlights, lift saturation a little and hold an S-curve for
# contrast.
#
# Shadow handling was re-tuned after check_exposure measured 16.8% of runtime
# below 0.12 luma (target ~8%) on this footage — dropped the brightness/gamma
# darkening (brightness=-0.014, gamma=0.96) that stacked on top of an
# already-dark source (a lot of night/cave footage, matching the song's "in
# the dead of night" section), and raised the curve's shadow point
# (0.20/0.085 -> 0.20/0.12) so shadow detail survives instead of crushing
# further. Contrast/saturation/highlight curve unchanged.
GRADE = (
    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={WIDTH}:{HEIGHT},setsar=1,"
    "eq=contrast=1.17:saturation=1.05,"
    # Cool the shadows and keep midtones/highlights close to neutral. Warming
    # the highlights washed the whole video orange — this source is full of
    # sunset scenes and the push stacked on top of them.
    "colorbalance=rs=-0.075:gs=-0.02:bs=0.11:rm=-0.015:gm=0:bm=0.025:"
    "rh=0.015:gh=0:bh=-0.015,"
    "curves=master='0/0 0.20/0.12 0.5/0.51 0.85/0.94 1/1',"
    "vignette=angle=PI/5,"
    "unsharp=5:5:0.32:5:5:0.0,"
    f"fps={FPS},format=yuv420p"
)

# Length of the dip-to-black used where one song section hands over to the next.
SECTION_DIP = 0.20
# Open from black and close to black; the outro instrumental carries the exit.
OPEN_FADE = 1.6
CLOSE_FADE = 3.5

# Radial focus: a sharp circle in the middle falling off to blurred edges.
# Radii are in units of half-frame-height, so 1.0 reaches the top/bottom edge
# and the corners sit at ~2.06 — that keeps the clear area a true circle on a
# 16:9 frame rather than an ellipse.
#
# Pulled way back from an earlier, much heavier setting (inner 0.82, outer
# 1.62, sigma 13). That began softening well inside the frame, so anything
# framed off-centre — which in anime is most faces — sat in the blurred ring,
# and at sigma 13 it read as an out-of-focus render rather than as depth.
# Now the clear circle extends past the top and bottom edges entirely and only
# the extreme corners get a gentle falloff; the vignette does the rest of the
# edge shaping.
FOCUS_INNER = 1.30
FOCUS_OUTER = 2.10
BLUR_SIGMA = 5


def clip_filter(fade_in: bool, fade_out: bool, duration: float) -> str:
    """Grade chain for one clip, plus a dip to black at section handovers.

    Cuts inside a section stay hard and on the beat — that is what gives an AMV
    its drive. Only the section changes get a transition.
    """
    chain = GRADE
    if fade_in:
        chain += f",fade=t=in:st=0:d={SECTION_DIP}"
    if fade_out:
        chain += f",fade=t=out:st={max(0.0, duration - SECTION_DIP):.3f}:d={SECTION_DIP}"
    return chain


def write_focus_mask(path: Path) -> Path:
    """Write the radial mask as a binary PGM.

    A greyscale image input costs one decode; generating the same gradient with
    `geq` would evaluate a per-pixel expression across every frame.
    Black in the centre keeps the sharp source, white at the edges takes the
    blurred copy.
    """
    import numpy as np

    ys = (np.arange(HEIGHT) - (HEIGHT - 1) / 2) / (HEIGHT / 2)
    xs = (np.arange(WIDTH) - (WIDTH - 1) / 2) / (HEIGHT / 2)
    radius = np.hypot(xs[None, :], ys[:, None])

    ramp = (radius - FOCUS_INNER) / (FOCUS_OUTER - FOCUS_INNER)
    ramp = np.clip(ramp, 0.0, 1.0)
    # Smoothstep, so the transition has no visible banding edge.
    mask = ramp * ramp * (3.0 - 2.0 * ramp)

    data = (mask * 255.0 + 0.5).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(f"P5\n{WIDTH} {HEIGHT}\n255\n".encode("ascii"))
        f.write(data.tobytes())
    return path
