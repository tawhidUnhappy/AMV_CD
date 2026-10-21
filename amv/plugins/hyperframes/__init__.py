"""HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0): HTML + CSS +
GSAP compositions rendered to video by headless Chrome + FFmpeg, built for
agents. AMV_CD writes a composition (e.g. a lyric video) and this renders it.
Its agent skills live in .claude/skills/ (hyperframes, hyperframes-core,
hyperframes-animation, music-to-video, ...).

    setup.py   the pinned CLI (npm), Chrome Headless Shell, GSAP, the repo clone

Settings, config.json "tools": {"hyperframes": {...}}:
    dir       CLI install folder (default workspace/tools/hyperframes-cli)
    repo      repo clone - docs, registry blocks (default workspace/tools/hyperframes)
    version   CLI version (default setup.VERSION)
    node      folder holding the node binary (default: found on PATH, else the snap's)
"""

from pathlib import Path

from amv.plugins import Tool, register

register("tool", Tool("hyperframes", (), worker=str(Path(__file__).with_name("setup.py")),
                      install="amv.plugins.hyperframes.setup:install"))
