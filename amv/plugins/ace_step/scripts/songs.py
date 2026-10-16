"""One request -> songs on disk, with ACE-Step's handlers already loaded. With no
lyrics and not instrumental, the planner LM writes them first (create_sample)."""

from __future__ import annotations

import time


def write_lyrics(req: dict, llm) -> dict:
    """caption + lyrics + bpm/key/duration from the prompt alone."""
    from acestep.inference import create_sample

    made = create_sample(llm, query=req["prompt"], instrumental=False,
                         vocal_language=req.get("language") or None)
    if not made.success:
        raise SystemExit(f"ACE-Step could not write lyrics: {made.error}")
    return {"caption": made.caption or req["prompt"], "lyrics": made.lyrics,
            "bpm": req.get("bpm") or made.bpm, "key": req.get("key") or made.keyscale,
            "duration": req.get("duration") or made.duration,
            "language": req.get("language") or made.language}


def generate(req: dict, job: dict, cfg, dit, llm, lm: str) -> dict:
    from acestep.inference import GenerationConfig, GenerationParams, generate_music

    text = {"caption": req["prompt"], "lyrics": req.get("lyrics") or "", "bpm": req.get("bpm"),
            "key": req.get("key") or "", "duration": req.get("duration"), "language": req.get("language")}
    if not req.get("instrumental") and not text["lyrics"]:
        if not lm:
            raise SystemExit("No lyrics given and no planner LM loaded to write them (lm = none): "
                             "pass --lyrics, or --instrumental")
        text = write_lyrics(req, llm)

    turbo = "turbo" in (job.get("model") or "acestep-v15-turbo")
    params = GenerationParams(
        caption=text["caption"], lyrics="[Instrumental]" if req.get("instrumental") else text["lyrics"],
        instrumental=bool(req.get("instrumental")), vocal_language=text["language"] or "unknown",
        bpm=text["bpm"], keyscale=text["key"], duration=float(text["duration"] or -1),
        inference_steps=int(job.get("steps") or (8 if turbo else 50)),
        seed=int(req.get("seed", -1)), thinking=bool(lm))
    limit = cfg.max_batch_size_with_lm if lm else cfg.max_batch_size_without_lm
    count = max(1, min(int(req.get("count") or 1), limit))
    seed = int(req.get("seed", -1))
    config = GenerationConfig(batch_size=count, use_random_seed=seed < 0,
                              seeds=[seed + i for i in range(count)] if seed >= 0 else None,
                              audio_format=job.get("format") or "wav")
    start = time.time()
    result = generate_music(dit, llm, params, config, save_dir=req["out_dir"])
    if not result.success:
        raise SystemExit(f"ACE-Step generation failed: {result.error}")
    return {"files": [a["path"] for a in result.audios],
            "seeds": [a["params"].get("seed") for a in result.audios],
            "seconds": round(time.time() - start, 1), "count_capped_to": count,
            "caption": text["caption"], "lyrics": params.lyrics, "bpm": text["bpm"], "key": text["key"]}
