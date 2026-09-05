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

## Environment (Windows + NVIDIA)

`uv init`, then these pins — each one blocks the pipeline if wrong:

| Pin | Reason |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in setuptools 81 |
| `nvidia-cudnn-cu12>=8.9,<9` | ctranslate2 4.4 links cuDNN **8**; torch cu124 bundles only cuDNN 9 |
| torch from `https://download.pytorch.org/whl/cu124` | GPU WhisperX/Demucs |
| `[tool.uv] environments = ["sys_platform == 'win32'"]` | Otherwise the resolver also solves Linux, where torch hard-pins cudnn 9 and conflicts with the cuDNN 8 above |

Two runtime shims are required (`amv/torch_compat.py`):

- **cuDNN 8 on the DLL path.** `os.add_dll_directory(<site-packages>/nvidia/cudnn/bin)`
  *before* `import ctranslate2`. torch's own cuDNN 9 lives in `torch/lib` and is
  registered automatically; ctranslate2's is not.
- **torch 2.6 `weights_only` flip.** The pyannote VAD checkpoint fails the safe
  unpickler. Retry with `weights_only=False` **and `args[0].seek(0)` first** —
  lightning passes an open file handle that the failed attempt leaves consumed.
  Do not chase the allowlist; the required globals differ per release.

## Windows / PowerShell notes

- `Set-Content -Encoding utf8` writes a **BOM**, which ffmpeg's concat demuxer
  rejects (`unknown keyword '\ufeffile'`). Use `-Encoding ascii`.
- PowerShell stringifies `5.0` as `"5"` — filenames built from floats will not
  match what you expect.
- The `tile` filter needs one input stream with N frames, not N inputs; feed it
  via the concat demuxer.
- Wildcard deletes may be blocked by the harness; delete directories or use
  fresh output paths.
