"""Which ACE-Step models to load and how, from the GPU's size (ACE-Step's own tiers:
docs/en/GPU_COMPATIBILITY.md), and fetching any that are missing. Runs in ACE-Step's
environment, so it imports acestep, never amv."""

from __future__ import annotations

from pathlib import Path


def gpu():
    """ACE-Step's tier for this GPU, made the process-wide one its handlers read."""
    from acestep.gpu_config import get_gpu_config, set_global_gpu_config

    cfg = get_gpu_config()
    set_global_gpu_config(cfg)
    return cfg


def lm_name(job: dict, cfg) -> str:
    """'' = no planner LM (the DiT alone, no lyric writing)."""
    want = (job.get("lm") or "auto").strip()
    if want == "none":
        return ""
    if want == "auto":
        return cfg.recommended_lm_model or ""
    return want


def ensure(job: dict, cfg) -> str:
    """Download the main model, the chosen DiT and LM if missing. Returns the LM name."""
    from acestep.model_downloader import (SUBMODEL_REGISTRY, check_main_model_exists, check_model_exists,
                                          ensure_dit_model, ensure_lm_model, ensure_main_model)

    ckpt = Path(job["checkpoints"])
    ckpt.mkdir(parents=True, exist_ok=True)
    steps = []
    if not check_main_model_exists(ckpt):
        steps.append(("main model (~10 GB)", lambda: ensure_main_model(ckpt)))
    model = job.get("model") or "acestep-v15-turbo"
    if not check_model_exists(model, ckpt) and model in SUBMODEL_REGISTRY:
        steps.append((model, lambda: ensure_dit_model(model, ckpt)))
    lm = lm_name(job, cfg)
    if lm and not check_model_exists(lm, ckpt):
        steps.append((lm, lambda: ensure_lm_model(lm, checkpoints_dir=ckpt)))
    for what, fetch in steps:
        print(f"[ace_step] downloading {what}...", flush=True)
        ok, message = fetch()
        if not ok:
            raise SystemExit(f"download failed ({what}): {message}")
    return lm


def load(job: dict, cfg, lm: str):
    """The DiT and (if any) LM handlers, set up for this GPU tier."""
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler

    dit, llm = AceStepHandler(), LLMHandler()
    status, ok = dit.initialize_service(
        project_root=job["src"], config_path=job.get("model") or "acestep-v15-turbo", device="auto",
        offload_to_cpu=cfg.offload_to_cpu_default, offload_dit_to_cpu=cfg.offload_dit_to_cpu_default,
        quantization="int8_weight_only" if cfg.quantization_default else None)
    if not ok:
        raise SystemExit(f"ACE-Step DiT failed to load: {status}")
    if lm:
        backend = job.get("backend") or "auto"
        status, ok = llm.initialize(
            checkpoint_dir=job["checkpoints"], lm_model_path=lm, device="auto",
            backend=cfg.recommended_backend if backend == "auto" else backend,
            offload_to_cpu=cfg.offload_to_cpu_default)
        if not ok:
            raise SystemExit(f"ACE-Step LM {lm} failed to load: {status}")
    return dit, llm
