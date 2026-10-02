"""One entry point for every stage and tool: `python -m amv <command> [args]`.

    ./amv.sh list                 # every command, grouped, with what it needs
    ./amv.sh select --candidates 8
    ./amv.sh remake --spec global/intro/remakes/NAME.json

Commands are `command` plug-ins (amv/plugins/commands/, or your own in
plugins/ - see amv.plugins). Each is a module with its own --help; this only
finds it and runs it as __main__, so `python -m amv.render.pipeline` still
works the same. Commands marked "gpu" import torch (Demucs, WhisperX, the PGS
OCR model) and need the full environment (`uv sync`); ./amv.sh runs
everything else in a small cached environment of numpy/librosa/pillow/scipy.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
import warnings

from amv import plugins

def usage() -> str:
    commands = plugins.items("command")
    width = max(len(c.name) for c in commands)
    lines = ["usage: python -m amv <command> [args]   (each command has --help)"]
    group = None
    for c in commands:
        if c.group != group:
            group = c.group
            lines += ["", f"  {group}"]
        lines.append(f"  {c.name:<{width}}  {'gpu ' if c.gpu else '    '}{c.help}  [{c.module}]")
    lines += ["", "gpu = needs the full environment: `uv sync`, then AMV_FULL=1 ./amv.sh <command>"]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("list", "-h", "--help", "help"):
        print(usage())
        return
    name = sys.argv[1]
    command = plugins.find("command", name)
    if command is None:
        raise SystemExit(f"unknown command {name!r}\n\n{usage()}")
    module, gpu = command.module, command.gpu
    if gpu and importlib.util.find_spec("torch") is None:
        raise SystemExit(f"'{name}' needs torch, which this environment does not have.\n"
                         "Run `uv sync` once, then: AMV_FULL=1 ./amv.sh " + " ".join(sys.argv[1:]))
    sys.argv = [f"amv {name}", *sys.argv[2:]]
    # runpy warns when the module was already imported as a dependency (e.g.
    # amv.core.config); running it again as __main__ is exactly what we want.
    warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
