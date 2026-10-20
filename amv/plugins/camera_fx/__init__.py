"""Camera effects for edits (AMV_EDITING_GUIDE.md sections 6-7): continuous shake,
blur accents and exposure flashes, as video_fx plug-ins ("fx" events in an edit spec
set "amount" per frame, so each can hit on a beat and decay).

    shake     wiggle with a posterize-time feel: offset {"px"}, rotation {"rot"} degrees,
              re-rolled every {"hold"} frames; edges are mirrored (the motion-tile trick),
              so no black border ever shows
    blur      gaussian blur up to {"radius"} px (blur transitions, lens-blur accents)
    exposure  brighter by {"stops"} with bloom on the highlights (flash frames)
"""

from amv.plugins import VideoFx, register

_FX = (
    ("shake", "posterized wiggle, mirrored edges", {"px": 36, "rot": 2.5, "hold": 2, "zoom": 0.03}, 30),
    ("blur", "gaussian blur accent", {"radius": 18}, 31),
    ("exposure", "exposure push + bloom", {"stops": 1.6, "bloom": 0.6}, 32),
)
for _name, _summary, _defaults, _order in _FX:
    register("video_fx", VideoFx(_name, _summary, f"amv.plugins.camera_fx.effects:{_name}",
                                 {"amount": 1.0, **_defaults}, order=_order))
