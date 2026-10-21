"""The ace_step SongGenerator: one request -> a job file -> the worker, in ACE-Step's
own environment (set up first if needed) -> the result it writes."""

from __future__ import annotations

import json
from pathlib import Path

from amv.core import tools
from amv.plugins.ace_step import setup


def generate(request: dict, settings: dict) -> dict:
    tools.ensure("ace_step")
    where = tools.settings("ace_step")
    out_dir = Path(request["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    job = {"checkpoints": str(setup.checkpoints(where)), "src": str(setup.home(where) / "src"),
           "result": str(out_dir / "result.json"), "request": {**request, "out_dir": str(out_dir)},
           **{k: settings[k] for k in ("model", "lm", "backend", "steps", "format", "guidance", "adg", "shift", "dcw")
              if settings.get(k) is not None and settings.get(k) != ""}}
    job_file = out_dir / "job.json"
    job_file.write_text(json.dumps(job, indent=1), encoding="utf-8")
    done = tools.run("ace_step", "generate", str(job_file), live=True)
    result = Path(job["result"])
    if done.returncode != 0 or not result.is_file():
        raise SystemExit(f"ACE-Step failed (exit {done.returncode}); its output is above")
    return json.loads(result.read_text(encoding="utf-8"))
