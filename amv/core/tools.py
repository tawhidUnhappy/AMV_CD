"""Running a `tool` plug-in: its worker script in its own isolated environment,
never the project's.

A package-list tool runs through `uv run --no-project --with ...`, built on first
use and cached by uv. uv re-resolves on every run, and a slow PyPI made that fail
even with every package cached, so each run is tried offline first, then online.

A tool that sets itself up (install / weights / interpreter, see _kinds.Tool) runs
on its own interpreter; `ensure` builds it and fetches its models first."""

from __future__ import annotations

import os
import subprocess

from amv import plugins
from amv.core import config


def settings(name: str) -> dict:
    """config.json "tools": {name: {...}}."""
    return config.load().plugin_settings("tool", name)


def command(name: str, *args: str) -> list[str]:
    tool = plugins.get("tool", name)
    if tool.interpreter:
        return [str(plugins.call(tool.interpreter, settings(name))), str(tool.worker), *args]
    cmd = ["uv", "run", "-q", "--no-project", "--python", tool.python]
    for package in tool.packages:
        cmd += ["--with", package]
    return [*cmd, "python", str(tool.worker), *args]


def ensure(name: str, force: bool = False, weights: bool = True) -> None:
    """Build a self-setup tool's environment and fetch its models; quick when done.
    A package-list tool needs nothing: uv builds it on first use."""
    tool = plugins.get("tool", name)
    if tool.install:
        plugins.call(tool.install, settings(name), force)
    if weights and tool.weights:
        plugins.call(tool.weights, settings(name))


def run(name: str, *args: str, live: bool = False) -> subprocess.CompletedProcess:
    """The worker's result (stdout captured, text). Not checked. `live` lets the
    worker's stderr (its progress) through to the terminal instead of capturing it."""
    cmd = command(name, *args)
    stderr = None if live else subprocess.PIPE
    if plugins.get("tool", name).interpreter:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=stderr, text=True)
    done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=stderr, text=True,
                          env={**os.environ, "UV_OFFLINE": "1"})
    if done.returncode != 0:
        done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=stderr, text=True)
    return done
