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
