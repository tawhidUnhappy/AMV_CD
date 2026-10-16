"""ACE-Step worker, run in ACE-Step's own environment (amv/plugins/ace_step/setup.py).

    python worker.py download '{"checkpoints": ..., "src": ..., "model": ..., "lm": ...}'
    python worker.py generate JOB.json      (job + "request"; the result goes to job["result"])

ACE-Step prints to stdout itself, so the result is written to a file, not stdout.
Progress goes to the terminal."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # models.py, songs.py beside this file


def setup_env(job: dict) -> None:
    """Point ACE-Step at our model folder; run from its own repo so nothing it
    writes beside itself lands elsewhere."""
    os.environ["ACESTEP_CHECKPOINTS_DIR"] = job["checkpoints"]
    os.environ["ACESTEP_PROJECT_ROOT"] = job["src"]
    os.chdir(job["src"])


def peak_ram_gb() -> float | None:
    try:
        import resource   # not on Windows
    except ImportError:
        return None
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 2)   # KiB on Linux


def main() -> None:
    mode, arg = sys.argv[1], sys.argv[2]
    job = json.loads(arg) if mode == "download" else json.loads(Path(arg).read_text(encoding="utf-8"))
    setup_env(job)
    import models

    cfg = models.gpu()
    lm = models.ensure(job, cfg)
    print(f"[ace_step] GPU tier {cfg.tier} ({cfg.gpu_memory_gb:.1f} GB): LM {lm or 'none'}, "
          f"offload {cfg.offload_to_cpu_default}/{cfg.offload_dit_to_cpu_default}, "
          f"int8 {cfg.quantization_default}", flush=True)
    if mode == "download":
        return

    import songs
    import torch

    start = time.time()
    dit, llm = models.load(job, cfg, lm)
    load_s = time.time() - start
    out = songs.generate(job["request"], job, cfg, dit, llm, lm)
    out.update(tier=cfg.tier, lm=lm, model=job.get("model") or "acestep-v15-turbo", load_seconds=round(load_s, 1),
               peak_vram_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else 0,
               peak_ram_gb=peak_ram_gb())
    Path(job["result"]).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
