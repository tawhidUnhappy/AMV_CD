---
name: amv-lyric-sync
description: Transcribe an isolated vocal stem (Demucs + WhisperX) for word-accurate lyric timing in an AMV, and verify blocks land on singing with check_lyric_timing.py. Use when lyric text appears at the wrong time, transcription looks wrong, or you're setting up amv/isolate_vocals.py and amv/transcribe_song.py.
---

# AMV pipeline: lyric timing (transcribe the vocal stem)

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

**Whisper on a full music mix produces wrong and missing lyrics.** Measured on
one 3:19 track:

| | Full mix | Demucs vocal stem |
| --- | --- | --- |
| Aligned words | 222 | 287 |
| First sung line | **2.71s** (wrong) | **11.54s** (correct) |
| Whole lines dropped | 5 | 0 |

The full-mix pass invented a 0.02s-long word at 2.71s and smeared the next
across 3.3s of instrumental, so the opening block appeared **nine seconds
early**. It also silently dropped five entire lines and misheard others.
Demucs `htdemucs` costs ~8 seconds on a mid-range GPU. Always run it.

Run order: `amv/isolate_vocals.py` (Demucs → vocal stem) then
`amv/transcribe_song.py` (WhisperX on the stem → word timings).

Then **verify**: `check_lyric_timing.py` measures each displayed block against
energy in the vocal stem.

> Threshold trap: compute the vocal-active threshold as
> `floor + 0.10 * (peak - floor)` using percentiles 20 and 99. A high percentile
> of the whole stem (e.g. p82) sits *inside* the loud part of the singing —
> because the stem is mostly silence — and reports almost every block as
> failing. The first version of this check produced 16/17 false failures. Fix
> the metric before "fixing" timings that were already right.

Residual smear: if a first word still aligns absurdly long (>3s) with a low
score, anchor the block to the intelligible line with an explicit override. Text
arriving slightly late reads far better than text hanging seconds early.
Loudness cannot settle this — held notes sit over loud instrumental bars.

## Linux: VAD needs care (two failure modes, not one)

WhisperX's transcription pipeline runs voice-activity detection before ASR.
On Linux this hit two separate, easily-conflated failures — both silent or
near-silent (no Python traceback), so don't assume "it printed something
about cuDNN, that must be the cuDNN pin from amv-environment-setup" without
checking which one it actually is:

1. **Pyannote's default VAD needs onnxruntime-gpu**, which wants the *old
   split* cuDNN 8.x shared libraries (`libcudnn_ops_infer.so.8`, ...) by exact
   filename — unrelated to and unsatisfied by either torch's bundled cuDNN 9
   or ctranslate2's own bundled cuDNN 8 (a different, monolithic file).
   **Fix: use Silero VAD instead** — `whisperx.load_model(..., vad_method="silero")`.
   It's a plain torch model, needs none of that.
2. **ctranslate2's actual ASR inference *also* needs those same split cuDNN
   8.x libraries** (not just import-time capability — `ctranslate2.get_cuda_device_count()`
   succeeding proves nothing about whether a real transcribe pass will work).
   Without them the process **segfaults/aborts outright** (exit 139/134, no
   traceback) partway through the ASR pass — easy to blame on something else
   entirely since nothing prints a Python-level error.
   `amv/audio/torch_compat.py._ensure_cudnn8_libs()` downloads these directly
   from the `nvidia-cudnn-cu12==8.9.7.29` wheel into `.cudnn8/` in the project
   root (outside the uv-managed venv, since torch's Linux wheel hard-pins
   `nvidia-cudnn-cu12==9.x` — see amv-environment-setup) and stages them
   automatically on first use. One-time ~700MB download; the wheel is
   unusually large so a flaky connection can time out — retry, it resumes.

**Do not blindly `dlopen`/`RTLD_GLOBAL`-preload every `.so` in `nvidia/cublas/lib`
while working on this.** It also contains `libnvblas.so`, a transparent
BLAS-call interceptor — loading it globally activates that interception
process-wide, and without an `nvblas.conf` specifying a CPU fallback, any BLAS
call it intercepts **segfaults** (exit 139, no traceback). This looked
identical to failure #2 above in the log (both show up right after VAD, both
silent) but had nothing to do with cuDNN — it was this project's own earlier
shim being too broad. Only force-load files matching `libcudnn*`.

**Silero VAD's model comes from `torch.hub`, which validates the repo against
GitHub's API before using its cache** — on a rate-limited connection this
fails with `HTTPError 403` even though `trust_repo=True` is set (that only
skips the interactive confirmation prompt, not the validation call). Fix:
pre-seed the cache so `torch.hub.load`'s own `os.path.exists(repo_dir)` check
short-circuits before it ever reaches that API call:
`git clone --depth 1 https://github.com/snakers4/silero-vad.git ~/.cache/torch/hub/snakers4_silero-vad_master`.
