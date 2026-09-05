#!/usr/bin/env bash
# Set up the isolated venv DeepSeek-OCR-2 runs in.
#
# DeepSeek-OCR-2's tested/working stack pins transformers==4.46.3, which
# conflicts with the newer transformers the main .venv needs for
# whisperx/pyannote (amv-environment-setup has the details). Rather than
# fight that version conflict, OCR gets its own venv here — run this once
# (or again to rebuild it) from the project root:
#
#   bash tools/deepseek_ocr/setup.sh
#
# amv/subs/pgs_ocr.py invokes this venv's python as a subprocess; nothing
# else in the main pipeline imports from it directly.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."  # -> project root

uv venv .venv-ocr --python 3.12
# torch/torchvision from the CUDA index (must match the version DeepSeek-OCR-2
# was tested against); everything else from PyPI proper — mixing them in one
# `uv pip install` call makes uv resolve non-torch packages against the CUDA
# index too and fail to find them there.
uv pip install --python .venv-ocr/bin/python \
  "torch==2.6.0" "torchvision==0.21.0" \
  --index-url https://download.pytorch.org/whl/cu124
uv pip install --python .venv-ocr/bin/python \
  "transformers==4.46.3" "tokenizers==0.20.3" einops addict easydict pillow "numpy<2.3" accelerate

echo
echo "Done. First real use of amv.subs.pgs_ocr (or a manual run of"
echo "tools/deepseek_ocr/run_ocr.py) downloads the ~6.8GB DeepSeek-OCR-2"
echo "weights from Hugging Face and caches them under ~/.cache/huggingface."
