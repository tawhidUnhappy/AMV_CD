"""Glitch picture effects (video_fx plug-ins) for effect-heavy edits
(`./amv.sh edit`) - and usable in a Short's "video_fx" like any other.

Every one takes an "amount" 0-1 (the edit sets it per frame from its fx
events, so an effect can hit on a beat and decay) plus its own settings.
The random ones re-roll every `hold` frames (2 at 60 fps reads as digital
stutter, not noise).

    rgb_split  R and B pulled apart sideways, {"px": max pixels}
    slice      horizontal bands torn sideways, {"bands", "shift": max px, "hold"}
    blocks     macroblock corruption: blocks displaced, channel-swapped, {"size", "hold"}
    chroma     radial chromatic aberration (lens-style fringes), {"scale"}
    scanlines  CRT lines and a rolling bright bar, {"period"}
    invert     colour negative
    pixelate   mosaic, {"size": block px at amount 1}
    posterize  colour banding, {"levels" at amount 1}
"""

from amv.plugins import VideoFx, register

_FX = (
    ("rgb_split", "R/B channels pulled apart sideways", {"px": 36}, 20),
    ("slice", "horizontal bands torn sideways", {"bands": 14, "shift": 160, "hold": 2}, 21),
    ("blocks", "macroblock corruption", {"size": 64, "hold": 2}, 22),
    ("chroma", "radial chromatic aberration", {"scale": 0.035}, 23),
    ("pixelate", "mosaic", {"size": 48}, 24),
    ("posterize", "colour banding", {"levels": 3}, 25),
    ("invert", "colour negative", {}, 26),
    ("scanlines", "CRT lines + rolling bar", {"period": 4}, 27),
)
for _name, _summary, _defaults, _order in _FX:
    register("video_fx", VideoFx(_name, _summary, f"amv.plugins.glitch_fx.effects:{_name}",
                                 {"amount": 1.0, **_defaults}, order=_order))
