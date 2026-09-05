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

## PGS subtitle OCR (same venv — no isolation needed)

Some releases carry PGS/VobSub **bitmap** subtitles instead of text (see
[amv-clip-selection](../amv-clip-selection/SKILL.md)) — ffmpeg's normal
`-c:s ass` conversion has nothing to parse, so `amv/subs/pgs.py` decodes the
bitmaps directly and `amv/subs/pgs_ocr.py` OCRs the crops with
**LightOnOCR-2-1B** (`lightonai/LightOnOCR-2-1B`, Apache-2.0), loaded and run
in-process — no subprocess, no second venv.

An earlier version of this used DeepSeek-OCR-2 in an isolated `.venv-ocr/`
(that model pinned `transformers==4.46.3`, conflicting with the newer
transformers whisperx/pyannote need here). LightOnOCR-2-1B needs
`transformers>=5.0` — already what this project's main `.venv` runs — so that
whole isolation problem doesn't exist for this model; it's just another
import. Concretely better too, not merely simpler to install: on the same
crops, LightOnOCR-2-1B was faster (~2.4 min for a 346-line episode vs ~24 min)
*and* correct on inputs that broke DeepSeek-OCR-2 (a wide/thin crop that made
DeepSeek hallucinate a fabricated table came out as a plausible dialogue line
here), all without the blur/resize preprocessing DeepSeek-OCR-2 needed to
handle this release's dithered anti-aliasing at all.

**Budget real time for it anyway: OCR is still real GPU work, not free like
text-track extraction** — expect single-digit minutes per episode, so a full
season is well under an hour, not instant. See
[amv-clip-selection](../amv-clip-selection/SKILL.md#pgs-ocr-takes-real-gpu-time--extract-the-full-series-anyway)
for why extracting the whole series (not a guessed subset) is worth that time.

Things worth knowing if you touch `amv/subs/pgs_ocr.py`:

- Cap `max_new_tokens` short (48 here) for a subtitle-line-length generation.
  Without a cap the model occasionally runs on past the real line into
  invented continuation text; the code also truncates at the first blank line
  as a second line of defense.
- Load once and cache (`functools.lru_cache` on the loader) — `extract_subs.py`
  calls into this per episode, and reloading a ~2GB model 24 times would waste
  most of the time this switch saved.
- The `_looks_like_garbage()` repeated-word filter carried over from the
  DeepSeek-OCR-2 version is kept as a cheap safety net even though this model
  hasn't been observed to loop the way DeepSeek-OCR-2 did.

## Windows / PowerShell notes

- `Set-Content -Encoding utf8` writes a **BOM**, which ffmpeg's concat demuxer
  rejects (`unknown keyword '\ufeffile'`). Use `-Encoding ascii`.
- PowerShell stringifies `5.0` as `"5"` — filenames built from floats will not
  match what you expect.
- The `tile` filter needs one input stream with N frames, not N inputs; feed it
  via the concat demuxer.
- Wildcard deletes may be blocked by the harness; delete directories or use
  fresh output paths.
