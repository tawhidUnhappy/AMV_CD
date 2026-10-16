"""ACE-Step 1.5's setup: its own repo, environment and models, all in one folder.

    <dir>/src          github.com/ace-step/ACE-Step-1.5 at a pinned commit
    <dir>/venv         `uv sync --frozen` of that repo's own lock (torch cu128, nano-vllm)
    <dir>/checkpoints  the models (main ~10 GB: turbo DiT, VAE, text encoder, 1.7B LM)

<dir> is workspace/tools/ace_step unless config.json "tools": {"ace_step": {"dir": ...}}.
`ref` there pins another commit. Runs from `./amv.sh tool-setup ace_step` and on first
use; on its own too: python -m amv.plugins.ace_step.setup [--force] [--no-weights]."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = "https://github.com/ace-step/ACE-Step-1.5"
REF = "ca1e85fe9430179831e6bc6be790c332190a3866"   # 2026-08-29, the commit this was built against
MARKER = ".amv-tool.json"


def home(settings: dict) -> Path:
    if settings.get("dir"):
        return Path(os.path.expandvars(settings["dir"])).expanduser()
    from amv.core import paths

    return paths.TOOLS / "ace_step"


def ref(settings: dict) -> str:
    return settings.get("ref") or REF


def checkpoints(settings: dict) -> Path:
    return home(settings) / "checkpoints"


def interpreter(settings: dict) -> Path:
    venv = home(settings) / "venv"
    for candidate in (venv / "bin" / "python", venv / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    raise SystemExit(f"ACE-Step is not installed ({venv} missing): ./amv.sh tool-setup ace_step")


def _say(message: str) -> None:
    print(f"[ace_step] {message}", flush=True)


def _run(cmd: list[str], **kw) -> None:
    subprocess.run(cmd, check=True, **kw)


def _marker(settings: dict) -> dict:
    try:
        return json.loads((home(settings) / "venv" / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def install(settings: dict, force: bool = False) -> None:
    """Clone (or move) the repo to the pinned commit, then sync its environment."""
    if not force and _marker(settings).get("ref") == ref(settings):
        return
    for exe in ("git", "uv"):
        if not shutil.which(exe):
            raise SystemExit(f"ACE-Step setup needs {exe} on PATH")
    src, venv = home(settings) / "src", home(settings) / "venv"
    if not (src / ".git").is_dir():
        _say(f"cloning {REPO} -> {src}")
        src.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", REPO, str(src)])
    _run(["git", "-C", str(src), "fetch", "-q", "origin", ref(settings)])
    _run(["git", "-C", str(src), "checkout", "-q", "--force", ref(settings)])
    _say(f"building its environment in {venv} (torch + CUDA, several GB, one time)")
    _run(["uv", "sync", "--frozen", "--no-dev", "--project", str(src)],
         env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv)})
    (venv / MARKER).write_text(json.dumps({"ref": ref(settings)}) + "\n", encoding="utf-8")
    _say("environment ready")


def weights(settings: dict) -> None:
    """The main model and the LM the song generator will use (auto = by GPU tier)."""
    from amv import plugins
    from amv.core import config

    gen = config.load().plugin_settings("song_generator", "ace_step")
    job = {"checkpoints": str(checkpoints(settings)), "src": str(home(settings) / "src"),
           "model": gen.get("model") or "acestep-v15-turbo", "lm": gen.get("lm") or "auto"}
    worker = plugins.get("tool", "ace_step").worker
    _run([str(interpreter(settings)), str(worker), "download", json.dumps(job)])


def main() -> None:
    import argparse

    from amv.core import tools

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-sync the environment even if current")
    parser.add_argument("--no-weights", action="store_true", help="environment only, no model download")
    args = parser.parse_args()
    tools.ensure("ace_step", force=args.force, weights=not args.no_weights)


if __name__ == "__main__":
    main()
