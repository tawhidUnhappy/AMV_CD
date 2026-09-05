"""Turn a PGS (bitmap) subtitle track into timed dialogue text via OCR.

This release's episodes carry PGS subtitles — pre-rendered bitmaps, not
text — so extract_subs.py's normal `-c:s ass` conversion has nothing to
parse. pgs.py decodes the bitmaps; this module crops each one, hands the
crops to DeepSeek-OCR-2 (running in its own venv — see tools/deepseek_ocr/,
and amv-environment-setup for why it's isolated), and returns
ass_parser.SceneEvent-shaped events so the rest of the pipeline (clip
selection, etc.) doesn't need to know the source subtitle track was an
image format.

PGS carries no speaker names, so `speaker` is always "".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from amv.core.config import ROOT
from amv.subs.ass_parser import SceneEvent
from amv.subs.pgs import decode_sup

OCR_VENV_PYTHON = ROOT / ".venv-ocr" / "bin" / "python"
OCR_SCRIPT = ROOT / "tools" / "deepseek_ocr" / "run_ocr.py"

# DeepSeek-OCR-2's crop_mode only skips its document-tiling path (built for
# multi-page scans, and badly suited to a single wide/thin subtitle strip —
# it hallucinates fabricated tables on one) when both dimensions are <=768;
# its own global-view resize+pad already handles arbitrary source sizes, so
# there's nothing to gain by upscaling small crops — only downscale if a
# subtitle bitmap happens to exceed this (some run past 1000px wide at
# 1080p).
MAX_DIM = 768


def _crop_path(work_dir: Path, episode: int, index: int) -> Path:
    return work_dir / f"ep{episode:02d}_{index:04d}.png"


def _save_crops(bitmaps, episode: int, work_dir: Path) -> list[dict]:
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, bmp in enumerate(bitmaps):
        image = Image.fromarray(bmp.image, "RGBA")
        # Flatten onto black: OCR wants a flat image, and PGS subtitles are
        # near-white text meant to sit over video, so black keeps contrast.
        flat = Image.new("RGB", image.size, (0, 0, 0))
        flat.paste(image, mask=image.split()[3])
        # This release's PGS mux dithers anti-aliasing as an alternating-row
        # comb pattern rather than true alpha gradients (visible as horizontal
        # "teeth" through glyph strokes at full zoom). A light vertical blur
        # merges the dither rows back into a smooth edge before OCR sees it.
        flat = flat.filter(ImageFilter.GaussianBlur(radius=1.2))
        scale = min(1.0, MAX_DIM / flat.width, MAX_DIM / flat.height)
        if scale < 1.0:
            flat = flat.resize((max(1, int(flat.width * scale)), max(1, int(flat.height * scale))), Image.LANCZOS)
        path = _crop_path(work_dir, episode, i)
        flat.save(path)
        manifest.append({"id": path.stem, "path": str(path)})
    return manifest


SETUP_SCRIPT = ROOT / "tools" / "deepseek_ocr" / "setup.sh"


def _ensure_ocr_venv() -> None:
    """Build .venv-ocr on first use instead of making every fresh clone run
    a manual setup step before OCR extraction works."""
    if OCR_VENV_PYTHON.exists():
        return
    print("OCR venv not found — building it now via tools/deepseek_ocr/setup.sh "
          "(one-time; downloads torch+transformers into an isolated venv)...", file=sys.stderr, flush=True)
    subprocess.run(["bash", str(SETUP_SCRIPT)], check=True, cwd=str(ROOT))
    if not OCR_VENV_PYTHON.exists():
        raise SystemExit(f"{SETUP_SCRIPT} ran but {OCR_VENV_PYTHON} still doesn't exist.")


def _run_ocr(manifest: list[dict], work_dir: Path) -> dict[str, str]:
    _ensure_ocr_venv()
    manifest_path = work_dir / "manifest.json"
    results_path = work_dir / "results.jsonl"
    manifest_path.write_text(json.dumps({"images": manifest}), encoding="utf-8")
    subprocess.run(
        [str(OCR_VENV_PYTHON), str(OCR_SCRIPT), str(manifest_path), str(results_path)],
        check=True,
        cwd=str(ROOT),
    )
    results: dict[str, str] = {}
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            results[row["id"]] = row["text"]
    return results


def _is_signage_frame(bmp, threshold: float = 0.35) -> bool:
    """Heuristic: a bitmap that's mostly opaque (not sparse text strokes) is
    probably a full or near-full graphic (an on-screen sign), not a subtitle
    line. See amv-clip-selection: burned-in signage can't be told apart from
    footage by pixel stats alone, but *this* bitmap-vs-line distinction is
    just "how much of this small crop is filled in" and is far less noisy."""
    alpha = bmp.image[..., 3].astype(np.float32) / 255.0
    return bool(alpha.mean() > threshold)


def _looks_like_garbage(text: str) -> bool:
    """Reject OCR output that's a decode loop rather than a real subtitle line.

    Seen on the shortest/widest crops (heavily downscaled to fit the model's
    768px tiling limit — see MAX_DIM): the model gets stuck repeating one
    token, e.g. "math, math, math, math, ...". A real subtitle line is short
    and doesn't hammer the same word.
    """
    if len(text) > 200:
        return True
    words = text.lower().split()
    if len(words) >= 6:
        most_common = max((words.count(w) for w in set(words)), default=0)
        if most_common / len(words) > 0.4:
            return True
    return False


def extract_events(sup_path: Path, episode: int, work_dir: Path) -> list[SceneEvent]:
    bitmaps = decode_sup(sup_path)
    if not bitmaps:
        return []
    manifest = _save_crops(bitmaps, episode, work_dir)
    print(f"  ep{episode:02d}: OCR'ing {len(manifest)} subtitle bitmaps...", file=sys.stderr, flush=True)
    texts = _run_ocr(manifest, work_dir)

    events = []
    for bmp, entry in zip(bitmaps, manifest):
        text = texts.get(entry["id"], "").strip()
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
