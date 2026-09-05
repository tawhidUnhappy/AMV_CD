"""OCR a batch of subtitle-bitmap crops with DeepSeek-OCR-2.

Runs inside its own venv (AMV_CD/.venv-ocr), invoked as a subprocess from
amv/subs/pgs_ocr.py in the main venv. Isolated because DeepSeek-OCR-2's
published, tested stack pins transformers==4.46.3, which conflicts with the
newer transformers whisperx/pyannote need in the main environment — two
venvs inside this one project folder rather than one shared, conflicting
dependency set.

Usage: python run_ocr.py <manifest.json> <results.json>

manifest.json: {"images": [{"id": "...", "path": "..."}, ...]}
results.json:  {"id": "...", "text": "..."}, one per input image, written
incrementally so a crash partway through doesn't lose completed work.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MODEL_NAME = "deepseek-ai/DeepSeek-OCR-2"
PROMPT = "<image>\nFree OCR. "


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <manifest.json> <results.json>")
    manifest_path, results_path = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    images: list[dict] = manifest["images"]

    # Resume support: skip images already OCR'd from a previous, interrupted run.
    done: dict[str, str] = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row["text"]
    pending = [im for im in images if im["id"] not in done]
    print(f"{len(done)} already done, {len(pending)} remaining", flush=True)
    if not pending:
        return

    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    # Load straight into bf16 on the GPU: the default fp32 load followed by
    # .cuda().to(bfloat16) transiently doubles VRAM use (~13.5GB for this
    # model) while the fp32 copy still exists, which doesn't fit a 12GB card.
    model = AutoModel.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    model = model.eval().cuda()

    out_dir = results_path.parent / "_infer_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(results_path, "a", encoding="utf-8") as out_f:
        for i, im in enumerate(pending):
            try:
                # The model's vision tower only supports the query counts that
                # come from its one declared candidate resolution (1024x1024,
                # crop_mode's default) — any other base_size/image_size combo
                # (e.g. a smaller one that seemed more sensible for a small
                # cropped subtitle line) hits an unhandled branch in its own
                # deepencoderv2.py and throws an UnboundLocalError. Use its
                # actual defaults rather than second-guessing them.
                # eval_mode=True is what actually makes infer() *return* the
                # decoded text — the default path only streams it to stdout
                # and returns None (it's built for a human watching a demo).
                text = model.infer(
                    tokenizer,
                    prompt=PROMPT,
                    image_file=im["path"],
                    output_path=str(out_dir),
                    save_results=False,
                    eval_mode=True,
                )
                text = (text or "").strip()
            except Exception as exc:  # noqa: BLE001 - one bad crop shouldn't kill the batch
                print(f"WARNING: OCR failed for {im['id']}: {exc}", flush=True)
                text = ""
            out_f.write(json.dumps({"id": im["id"], "text": text}, ensure_ascii=False) + "\n")
            out_f.flush()
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(pending)}", flush=True)

    print(f"done: {len(pending)} images OCR'd", flush=True)


if __name__ == "__main__":
    main()
