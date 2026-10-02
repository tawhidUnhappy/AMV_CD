"""Picture effects for a Short (spec "video_fx": [NAME, ...] or {NAME:
{settings}}), applied to the montage (story scenes stay clean unless
"video_fx_scope": "all"), lightly - they must not fight the edit's own
flashes and punches. They run in `order`: outline, glow, grain.

    outline  a soft glowing line along strong edges, {"color": [r,g,b], "strength": 0-1, "width": px}
    glow     bloom: bright areas bleed light, {"strength": 0-1}
    grain    film grain, {"amount": 0-20}"""

from amv.plugins import VideoFx, register

register("video_fx", VideoFx("outline", "glowing line along strong edges", "amv.plugins.video_fx.effects:outline",
                             {"color": [255, 255, 255], "strength": 0.55, "width": 3}, order=1))
register("video_fx", VideoFx("glow", "bloom on bright areas", "amv.plugins.video_fx.effects:glow",
                             {"strength": 0.35}, order=2))
register("video_fx", VideoFx("grain", "film grain", "amv.plugins.video_fx.effects:grain", {"amount": 7}, order=3))
