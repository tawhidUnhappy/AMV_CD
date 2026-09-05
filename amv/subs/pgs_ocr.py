"""Turn a PGS (bitmap) subtitle track into timed dialogue text via OCR.

This release's episodes carry PGS subtitles — pre-rendered bitmaps, not
text — so extract_subs.py's normal `-c:s ass` conversion has nothing to
parse. pgs.py decodes the bitmaps; this module crops each one and hands the
crops to LightOnOCR-2-1B, returning ass_parser.SceneEvent-shaped events so
the rest of the pipeline (clip selection, etc.) doesn't need to know the
source subtitle track was an image format.

LightOnOCR-2-1B runs directly in this venv — no isolated environment needed
(see amv-environment-setup for why that was a real concern with the model
originally tried here, DeepSeek-OCR-2, and wasn't with this one).

PGS carries no speaker names, so `speaker` is always "".
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor

from amv.subs.ass_parser import SceneEvent
from amv.subs.pgs import decode_sup

MODEL_NAME = "lightonai/LightOnOCR-2-1B"
# A subtitle line is a handful of words; capping generation short is what
# keeps the model from occasionally running on past the real line into
# invented continuation text (seen at higher caps) rather than stopping.
MAX_NEW_TOKENS = 48


@lru_cache(maxsize=1)
def _load_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    print(f"Loading {MODEL_NAME} onto {device}...", file=sys.stderr, flush=True)
    model = LightOnOcrForConditionalGeneration.from_pretrained(MODEL_NAME, torch_dtype=dtype).to(device)
    model.eval()
    processor = LightOnOcrProcessor.from_pretrained(MODEL_NAME)
    return model, processor, device, dtype


def _flatten(bmp) -> Image.Image:
    """Composite the RGBA subtitle bitmap onto black.

    Just a flatten — no blur/resize needed. Unlike the model originally
    tried here, this one handles this release's dithered anti-aliasing (a
    comb pattern through glyph strokes, visible at full zoom) and arbitrarily
    wide/thin crops correctly without help; its own processor resizes to fit
    its longest-edge budget.
    """
    image = Image.fromarray(bmp.image, "RGBA")
    flat = Image.new("RGB", image.size, (0, 0, 0))
    flat.paste(image, mask=image.split()[3])
    return flat


def _ocr_one(image: Image.Image) -> str:
    model, processor, device, dtype = _load_model()
    conversation = [{"role": "user", "content": [{"type": "image", "image": image}]}]
    inputs = processor.apply_chat_template(
        conversation, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt"
    )
    inputs = {k: (v.to(device=device, dtype=dtype) if v.is_floating_point() else v.to(device))
              for k, v in inputs.items()}
    with torch.inference_mode():
        output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
    text = processor.decode(output_ids[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    # A subtitle line is one block; a blank line marks where invented
    # continuation text (if any) starts.
    return text.split("\n\n")[0].strip()


def _is_signage_frame(bmp, threshold: float = 0.35) -> bool:
    """Heuristic: a bitmap that's mostly opaque (not sparse text strokes) is
    probably a full or near-full graphic (an on-screen sign), not a subtitle
    line. See amv-clip-selection: burned-in signage can't be told apart from
    footage by pixel stats alone, but *this* bitmap-vs-line distinction is
    just "how much of this small crop is filled in" and is far less noisy."""
    alpha = bmp.image[..., 3].astype(np.float32) / 255.0
    return bool(alpha.mean() > threshold)


def _looks_like_garbage(text: str) -> bool:
    """Reject OCR output that's a decode loop rather than a real subtitle
    line. Cheap safety net kept from the previous OCR engine; not something
    this model has been observed to do, but costs nothing to keep checking."""
    if len(text) > 200:
        return True
    words = text.lower().split()
    if len(words) >= 6:
        most_common = max((words.count(w) for w in set(words)), default=0)
        if most_common / len(words) > 0.4:
            return True
    return False


def extract_events(sup_path: Path, episode: int) -> list[SceneEvent]:
    bitmaps = decode_sup(sup_path)
    if not bitmaps:
        return []
    print(f"  ep{episode:02d}: OCR'ing {len(bitmaps)} subtitle bitmaps...", file=sys.stderr, flush=True)

    events = []
    for bmp in bitmaps:
        text = _ocr_one(_flatten(bmp)).strip()
        if not text or _looks_like_garbage(text):
            continue
        events.append(
            SceneEvent(
                episode=episode,
                start=bmp.start,
                end=bmp.end,
                text=text,
                style="Sign" if _is_signage_frame(bmp) else "Dialogue",
                speaker="",
            )
        )
    return events
