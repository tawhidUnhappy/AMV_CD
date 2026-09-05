---
name: amv-environment-setup
description: Set up the Windows + NVIDIA uv environment and config.json for the AMV lyric-video pipeline (torch/cuDNN/ctranslate2 pins, torch_compat shims, PowerShell gotchas). Use before running any amv/ script for the first time, when dependency install fails, or when torch.load/DLL errors appear.
---

# AMV pipeline: environment setup

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline. Read that
skill first for the overall picture; this one covers just getting the
environment working.

## Make it configurable from the start

Put `source_dir`, `episode_pattern`, `song`, font and output format in a
`config.json` read by one module, and default every CLI flag from it. Hardcoding
a media path into each script means the project only ever works for one person
on one machine, and untangling it later touches every file.

Likewise: locate site-packages via `sysconfig`, not a literal `.venv/Lib/...`,
and look up system fonts through a per-platform directory list rather than
`C:/Windows/Fonts`.

## Environment (Windows + Linux, NVIDIA)

`uv init`, then these pins — each one blocks the pipeline if wrong:

| Pin | Reason |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in setuptools 81 |
| `nvidia-cudnn-cu12>=8.9,<9 ; sys_platform == 'win32'` | ctranslate2 4.4 links cuDNN **8**, which only the Windows torch wheel leaves room for — the Linux wheel hard-pins cuDNN 9 itself, so this pin is Windows-only or the dependency set is unresolvable |
| torch from `https://download.pytorch.org/whl/cu124` | GPU WhisperX/Demucs |
| `[tool.uv] environments = ["sys_platform == 'win32'", "sys_platform == 'linux'"]` | Restrict the resolver to the two platforms this is actually tested on |

Runtime shims live in `amv/audio/torch_compat.py`, called once via `patch()`
before any GPU work:

- **cuDNN on the shared-library path.** Windows: `os.add_dll_directory(<site-packages>/nvidia/cudnn/bin)`
  before `import ctranslate2` (torch's own cuDNN 9 in `torch/lib` is registered
  automatically; ctranslate2's bundled cuDNN 8 is not). Linux: the equivalent
  via `LD_LIBRARY_PATH` + `ctypes.CDLL(..., RTLD_GLOBAL)` — note Linux gets
  cuDNN **9** from torch itself (see the pin above), not 8.
- **ctranslate2's executable-stack ELF flag.** Linux only. The shipped wheel's
  `libctranslate2*.so` has `GNU_STACK` marked executable — a harmless build
  default that recent kernels refuse to load (`cannot enable executable stack
  as shared object requires`). `patch()` clears that one flag in-place before
  the import; self-healing, so a fresh `uv sync` on a new machine needs no
  manual fix.
- **torch 2.6 `weights_only` flip.** The pyannote VAD checkpoint fails the safe
  unpickler. Retry with `weights_only=False` **and `args[0].seek(0)` first** —
  lightning passes an open file handle that the failed attempt leaves consumed.
  Do not chase the allowlist; the required globals differ per release.

All pipeline output (vocal stem, transcript, subtitle index, EDL, QA sheets,
rendered video) lives under `tmp/` in the project root — delete it to reset.

## A second, isolated venv for PGS subtitle OCR

Some releases carry PGS/VobSub **bitmap** subtitles instead of text (see
[amv-clip-selection](../amv-clip-selection/SKILL.md)) — ffmpeg's normal
`-c:s ass` conversion has nothing to parse, so `amv/subs/pgs.py` decodes the
bitmaps directly and `amv/subs/pgs_ocr.py` OCRs the crops with
DeepSeek-OCR-2.

That model's tested stack pins `transformers==4.46.3`, which conflicts with
the newer transformers whisperx/pyannote need in the main `.venv`. Rather than
fight that version conflict, it gets its own venv, `.venv-ocr/`, built by
`tools/deepseek_ocr/setup.sh` and invoked as a subprocess from
`amv/subs/pgs_ocr.py` — `_ensure_ocr_venv()` runs that script automatically on
first use, so nothing needs to be set up by hand. Both venvs live inside the
project folder; the project stays self-contained to `AMV_CD/` either way.

**Before running it: OCR is minutes per episode, not free like text-track
extraction.** Always pick episodes with `extract_subs.py --episodes` instead
of OCR'ing a whole PGS-subtitled series — see
[amv-clip-selection](../amv-clip-selection/SKILL.md#pgs-ocr-is-expensive--dont-run-it-on-the-whole-series).

DeepSeek-OCR-2 quirks worth knowing if you touch `tools/deepseek_ocr/run_ocr.py`:

- Load the model straight into bf16 (`torch_dtype=torch.bfloat16,
  low_cpu_mem_usage=True`) — the default fp32 load followed by
  `.cuda().to(bfloat16)` transiently doubles VRAM use (~13.5GB for this model)
  while the fp32 copy still exists, which doesn't fit a 12GB card.
- `model.infer()` only *returns* the decoded text when called with
  `eval_mode=True`; otherwise it streams to stdout and returns `None` (it's
  built for a human watching a demo, not a script capturing output).
- Its `crop_mode=True` default (needed — the alternative hits an unrelated bug,
  an `UnboundLocalError` on `param_img` in `deepencoderv2.py`, for any
  `image_size` other than 768/1024) tiles the image into a multi-page-scan
  layout whenever either dimension exceeds 768px. A subtitle line is a wide,
  thin strip, not a document — tiled that way, the model hallucinates
  fabricated document content (tables, unrelated text) instead of OCR'ing the
  line. Fix: keep crops within 768x768 (downscale only, never upscale) so
  `crop_ratio` stays `[1, 1]` and tiling never triggers.
- Even with the sizing fixed, the model occasionally free-runs into a
  repeated-token loop on very short/heavily-downscaled crops (e.g. `"math,
  math, math, ..."`). `pgs_ocr._looks_like_garbage()` rejects output that's
  implausibly long or dominated by one repeated word rather than trying to
  prevent every such loop at generation time.

## Windows / PowerShell notes

- `Set-Content -Encoding utf8` writes a **BOM**, which ffmpeg's concat demuxer
  rejects (`unknown keyword '\ufeffile'`). Use `-Encoding ascii`.
- PowerShell stringifies `5.0` as `"5"` — filenames built from floats will not
  match what you expect.
- The `tile` filter needs one input stream with N frames, not N inputs; feed it
  via the concat demuxer.
- Wildcard deletes may be blocked by the harness; delete directories or use
  fresh output paths.
