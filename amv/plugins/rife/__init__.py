"""RIFE frame interpolation (github.com/nihui/rife-ncnn-vulkan, MIT): smooth slow motion
for velocity edits and speed ramps - what Twixtor does in After Effects. A Vulkan
binary, no Python environment; anime-aware use is in interp.py.

    setup.py   download + unpack the pinned release into workspace/tools/rife
    interp.py  slow_clip(): a source window -> an N x slower clip (held frames dropped
               first, cuts never blended), cached under workspace/tmp/interp/

Settings, config.json "tools": {"rife": {"dir": ..., "model": "rife-v4.6", "gpu": 0}}."""

from pathlib import Path

from amv.plugins import Tool, register

register("tool", Tool("rife", (), worker=str(Path(__file__).with_name("interp.py")),
                      install="amv.plugins.rife.setup:install"))
