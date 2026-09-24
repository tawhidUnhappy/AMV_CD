---
name: amv-lyric-video
description: Build a beat-synced anime music video with burned-in lyrics from local episode files and a song, using uv + ffmpeg + WhisperX + Demucs + librosa. Covers vocal-stem transcription, subtitle-driven clip selection, beat-snapped cutting, colour grading, ASS lyric overlays, and YouTube thumbnails/titles. Use when asked to make an AMV, a lyric video, or a music-video edit from local anime/video sources.
---

# AMV / lyric-video pipeline

How to build a beat-synced music video with burned-in lyrics from a folder of
episode files and a song. Read this before rebuilding anything — most of it was
learned the hard way, and several "obvious" approaches are documented here
**because they failed**.

A working implementation of everything below lives alongside this file (`amv/`,
driven by `config.json`). Numbers quoted as evidence come from one real build:
a 26-episode series cut to a 3:19 track. Treat them as calibration, not as
constants for your own material.

For how to run things, the code map and the check tools, load
[amv-ops](../amv-ops/SKILL.md) first. This skill is the pipeline's entry point; each pipeline stage has its own skill with the
details, traps and measured numbers. Load the one for the stage you're
actually touching:

| Stage | Skill |
| --- | --- |
| First-time setup, dependency pins, torch/cuDNN shims, PowerShell gotchas | [amv-environment-setup](../amv-environment-setup/SKILL.md) |
| Vocal isolation + WhisperX transcription for lyric timing | [amv-lyric-sync](../amv-lyric-sync/SKILL.md) |
| Beat grid detection and frame-exact cut timing | [amv-beat-cutting](../amv-beat-cutting/SKILL.md) |
| Subtitle-driven clip selection, avoiding filler/text screens | [amv-clip-selection](../amv-clip-selection/SKILL.md) |
| Colour grade, exposure check, focus blur, transitions | [amv-grade-and-transitions](../amv-grade-and-transitions/SKILL.md) |
| ASS/libass lyric overlay styling and face-avoiding placement | [amv-lyric-typography](../amv-lyric-typography/SKILL.md) |
| YouTube thumbnails (arrows/bubbles), titles, credits | [amv-thumbnails-and-titles](../amv-thumbnails-and-titles/SKILL.md) |

## Golden rules

1. **Transcribe an isolated vocal stem, never the full mix.** This is the single
   highest-impact step. See [amv-lyric-sync](../amv-lyric-sync/SKILL.md).
2. **Cuts go on beats. Lyric text goes on the vocal.** Two separate clocks.
3. **Look at the output.** Every quality problem in this project was found by
   rendering frames and looking, not by reasoning. Build contact sheets.
4. **Measure before tuning.** Exposure, sync and timing all had numeric checks
   that overturned a guess.
5. **A failed detector is a result.** Two detectors here did not work. They are
   documented so nobody rebuilds them.

## Pipeline order

```bash
AMV_FULL=1 ./amv.sh vocals       # Demucs -> vocal stem (~8s on a 3060)
AMV_FULL=1 ./amv.sh transcribe   # WhisperX on the stem -> word timings
./amv.sh beats                   # librosa -> beat grid
AMV_FULL=1 ./amv.sh subs         # episodes -> subtitles + scene index
./amv.sh select --candidates 8   # -> tmp/edl.json
./amv.sh sheet                   # QA — REVIEW THIS BEFORE RENDERING
./amv.sh lyrics                  # -> tmp/work/lyrics.ass   (reads edl.json!)
./amv.sh render                  # -> tmp/out/amv.mp4
./amv.sh check-timing            # verify text sits over singing
```

Ordering traps: `lyric_overlay` reads `tmp/edl.json`, so it must run *after*
`select_clips`. Re-running `select_clips` invalidates lyric placement.

Every generated path is defined once, in `amv/core/paths.py` — import from
there rather than joining `ROOT / "tmp" / ...` in a new module.

A short channel intro (no lyrics) is its own command, `python -m amv.intro`
— see the README.

## Verification scripts to build

Each of these caught a real defect:

| Script | Catches |
| --- | --- |
| `contact_sheet.py` | wrong/ugly/off-tone footage — the biggest win |
| `check_lyric_timing.py` | text not over singing |
| `check_sync.py` | genuine A/V offset vs editorial looseness |
| `check_exposure.py` | over-crushed grade |
| `grade_preview.py` | grade tuning without a full render |
