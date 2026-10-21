"""HyperFrames set up remanga-style: a pinned CLI in its own npm folder, the
Chrome it renders with, GSAP copied locally (compositions must not fetch at
render time), and the repo clone for docs and registry blocks. `cli()` runs it."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from amv.core import paths

VERSION = "0.8.184"
GSAP = "3.14.2"
REPO = "https://github.com/heygen-com/hyperframes.git"


def _settings() -> dict:
    from amv.core.config import load

    return load().plugin_settings("tool", "hyperframes")


def home(settings: dict | None = None) -> Path:
    s = settings if settings is not None else _settings()
    return Path(s["dir"]) if s.get("dir") else paths.TOOLS / "hyperframes-cli"


def node_dir(settings: dict | None = None) -> Path:
    """The folder of a node binary that answers --version. The snap's wrapper
    (/snap/bin/node) printed nothing in a sandboxed shell; its real binary works."""
    s = settings if settings is not None else _settings()
    candidates = [Path(s["node"])] if s.get("node") else []
    found = shutil.which("node")
    if found:
        candidates.append(Path(found).parent)
    candidates.append(Path("/snap/node/current/bin"))
    for d in candidates:
        try:
            out = subprocess.run([str(d / "node"), "--version"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.startswith("v") and int(out[1:].split(".")[0]) >= 22:
            return d
    raise SystemExit("HyperFrames needs Node.js 22+: install it, or set config.json tools.hyperframes.node")


def env(settings: dict | None = None) -> dict:
    return {**os.environ, "PATH": f"{node_dir(settings)}{os.pathsep}{os.environ.get('PATH', '')}",
            "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}


def gsap_file(settings: dict | None = None) -> Path:
    return home(settings) / "node_modules" / "gsap" / "dist" / "gsap.min.js"


def install(settings: dict, force: bool = False) -> None:
    d = home(settings)
    d.mkdir(parents=True, exist_ok=True)
    version = settings.get("version", VERSION)
    cli_pkg = d / "node_modules" / "hyperframes" / "package.json"
    have = cli_pkg.exists() and f'"version": "{version}"' in cli_pkg.read_text(encoding="utf-8")
    if force or not have or not gsap_file(settings).exists():
        if not (d / "package.json").exists():
            (d / "package.json").write_text('{"name": "amv-hyperframes", "private": true}\n', encoding="utf-8")
        print(f"Installing hyperframes@{version} + gsap@{GSAP} in {d}", flush=True)
        subprocess.run([str(node_dir(settings) / "npm"), "install", "--no-fund", "--no-audit",
                        f"hyperframes@{version}", f"gsap@{GSAP}"], cwd=d, env=env(settings), check=True)
    subprocess.run([*cli_cmd(settings), "browser", "ensure"], cwd=d, env=env(settings), check=True,
                   stdout=subprocess.DEVNULL)
    repo = Path(settings["repo"]) if settings.get("repo") else paths.TOOLS / "hyperframes"
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, str(repo)], check=True)


def cli_cmd(settings: dict | None = None) -> list[str]:
    return [str(node_dir(settings) / "node"), str(home(settings) / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs")]


def cli(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run `hyperframes ARGS` (set up on first use), output passed through."""
    s = _settings()
    if not (home(s) / "node_modules" / "hyperframes").exists() or not gsap_file(s).exists():
        install(s)
    return subprocess.run([*cli_cmd(s), *args], cwd=cwd, env=env(s), check=check)
