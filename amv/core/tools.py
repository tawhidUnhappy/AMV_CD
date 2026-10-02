"""Running a `tool` plug-in: its worker script in its own isolated uv
environment (`uv run --no-project --with ...`), built on first use and cached
by uv - never the project's environment.

uv re-resolves on every run, and a slow PyPI made that fail even with every
package cached, so each run is tried offline first, then online."""

from __future__ import annotations

import os
import subprocess

from amv import plugins


def command(name: str, *args: str) -> list[str]:
    tool = plugins.get("tool", name)
    cmd = ["uv", "run", "-q", "--no-project", "--python", tool.python]
    for package in tool.packages:
        cmd += ["--with", package]
    return [*cmd, "python", str(tool.worker), *args]


def run(name: str, *args: str) -> subprocess.CompletedProcess:
    """The worker's result (stdout/stderr captured, text). Not checked."""
    cmd = command(name, *args)
    done = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "UV_OFFLINE": "1"})
    if done.returncode != 0:
        done = subprocess.run(cmd, capture_output=True, text=True)
    return done
