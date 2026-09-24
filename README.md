# AMV / lyric-video pipeline

Builds a beat-synced, colour-graded music video with burned-in lyrics from a
folder of episode files and a song.

Self-contained: the only external requirements are `ffmpeg`/`ffprobe` on PATH,
`uv`, and an NVIDIA GPU for the ML steps. Nothing outside this directory is
read except the media you point it at in `config.json`, and everything the
pipeline generates (vocal stem, transcript, subtitle index, EDL, QA sheets,
the rendered video) is written under `tmp/` inside this project folder — so
the whole thing is isolated to `AMV_CD/` plus its `.venv`, portable, and
deleting `tmp/` gets you back to a clean slate.

The reference build is a Mirai Nikki × "Black Salt Halo" AMV, but nothing about
the series or track is hard-coded.

## Quick start

```bash
uv sync
cp config.example.json config.json     # then edit it
```

`config.json` is the only file you need to touch:

| Key | Meaning |
| --- | --- |
| `source_dir` | folder of episode video files |
| `episode_pattern` | regex with one capture group for the episode number |
| `song` | the track to cut to |
| `lyric_font_file` / `lyric_font_family` | font for burned-in lyrics |
| `width` / `height` / `fps` | output format |

Paths may be absolute or relative to the project root; `~` and environment
variables are expanded. Every value can also be overridden per-run with a
command-line flag. `uv run python -m amv.core.config` prints what resolved.

## Running the pipeline

```bash
uv run python -m amv.audio.isolate_vocals     # Demucs -> vocal stem
uv run python -m amv.audio.transcribe_song    # WhisperX -> word-level timings
uv run python -m amv.audio.beats              # librosa -> beat grid
uv run python -m amv.subs.extract_subs        # episodes -> subtitles + scene index
uv run python -m amv.render.select_clips --candidates 8
uv run python -m amv.vision.contact_sheet     # REVIEW THIS before rendering
uv run python -m amv.render.lyric_overlay     # -> lyrics.ass  (needs the EDL)
uv run python -m amv.render.pipeline          # -> tmp/out/amv.mp4
```

`lyric_overlay` reads `tmp/edl.json`, so run it *after* `select_clips`.

### Adapting to your own song

`amv/audio/lyrics.py` holds the lyric plan: phrases mapped to word-index ranges
in the transcript, with line breaks, a red emphasis word, and a `show` flag.
Rebuild it for a new track by dumping the aligned words
(`amv/subs/dump_words.py`) and writing phrases against them. `validate()`
guards against index drift.

## How it works

- **Song side** — Demucs separates the vocal, WhisperX transcribes and
  force-aligns it to word level, librosa finds the beat grid.
- **Source side** — each episode's embedded subtitle track is extracted and
  parsed into thousands of timestamped, speaker-labelled moments. The clip
  picker searches those instead of sampling blind.
- **Timeline** — cuts are proposed from the lyric structure, then **snapped to
  the beat grid**. Lyric text timing comes from the vocal alignment, so the two
  never fight.
- **Selection** — a per-section episode range walks the story forward; lyric
  slots match subtitle text against keywords and a preferred speaker; a small
  decoded probe scores brightness, contrast, motion and skin fraction to reject
  black frames, fades and static shots.
- **Render** — three passes: grade every clip, concatenate by stream copy, then
  one pass for radial focus + lyric burn + audio mux.

## Verification

Each of these caught a real defect; run them after changes:

| Script | Catches |
| --- | --- |
| `amv.vision.contact_sheet` | wrong, ugly or off-tone footage — the biggest win |
| `amv.subs.check_lyric_timing` | lyric text not sitting over singing |
| `amv.subs.check_sync` | genuine A/V offset vs merely loose editing |
| `amv.vision.check_exposure` | an over-crushed grade |
| `amv.render.grade_preview` | grade tuning without a full re-render |
| `amv.render.font_compare` | outline fonts that wash out over footage |

## Extras

- `amv/thumbnail/` composes YouTube thumbnails from real frames (three
  layouts: label-arrow, speech bubble, split). No image generation. Run with
  `uv run python -m amv.thumbnail`.
- `amv/vision/thumb_candidates.py` pulls strong frames to choose from.

### Channel intro

A short, lyric-free intro cut to the opening of any track:

```bash
uv run python -m amv.intro --song "path/to/track.wav" --seconds 11
```

It reads the song's opening as a quiet swell followed by the moment the music
comes in, and cuts to that: two calm, wide shots over the swell, a white
flash where the music enters, then a cut every couple of beats. The swell's
shots come from the dialogue-free stretches (establishing shots). The drive
section uses the busiest cut-free windows from a per-episode motion map,
which is built once and cached in `tmp/intro/motion/`. Output goes to
`tmp/intro/`: `intro.mp4`, `edl.json` and `sheet.jpg`. **Look at the sheet.**
To swap out a shot, reject its region with `--skip EP:START-END` and run
again, or edit `edl.json` by hand and run with `--render-only`. It needs the
scene index from `amv.subs.extract_subs`, but nothing from the lyric stages.

### Remaking an existing intro

To reproduce an intro someone cut from this series, frame for frame:

```bash
uv run python -m amv.intro.reference "their_video.mp4" --seconds 11   # -> tmp/intro/reference_map.json
# write tmp/intro/remake_plan.json from the map (see amv/intro/remake.py)
uv run python -m amv.intro.remake                                      # -> tmp/intro/remake.mp4
```

`reference` finds the episode frame behind every frame of the video. It
first searches a coarse 8 fps index of every episode (built once, cached in
`tmp/intro/index/`), then matches frame by frame around each hit. Frames
with no close match are the effects, composites or footage from outside
these episodes. The plan fills those in by hand from a small effect
vocabulary: `zoom_blur`, `white_burst`, a `punch` zoom with an `rgb` split,
a per-channel colour `grade`, and a fading `caption`. `remake` then renders
the plan with the song laid under it.

## Environment notes (Windows + NVIDIA)

Four pins in `pyproject.toml` are load-bearing:

| Pin | Reason |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in 81 |
| `nvidia-cudnn-cu12>=8.9,<9` | ctranslate2 4.4 links cuDNN 8; torch bundles only cuDNN 9 |
| torch from the cu124 index | GPU WhisperX / Demucs |
| `environments = ["sys_platform == 'win32'"]` | otherwise the resolver also solves Linux, where torch hard-pins cudnn 9 and conflicts |

`amv/audio/torch_compat.py` adds two runtime shims: it puts the pip-installed
cuDNN 8 on the DLL search path before `ctranslate2` imports, and it works
around torch 2.6's `weights_only` default for the pyannote VAD checkpoint.
`amv/audio/device.py` centralizes CUDA-vs-CPU device selection and cache
cleanup for both GPU stages (Demucs, WhisperX).

## Design notes

The full write-up — including the approaches that **failed** and should not be
retried — is in `.claude/skills/amv-lyric-video/SKILL.md`. Highlights:

- **Transcribe an isolated vocal stem, never the full mix.** On the mix, Whisper
  placed the opening line 9s early and silently dropped five whole lines.
- **Cuts drift if rendered by duration.** 154 clips each rounding down to a
  whole frame drifted the edit 1.6s early; slot edges are quantised to frame
  indices and rendered with `-frames:v`.
- **Two detectors were tried and rejected on measured evidence**: edge density
  for burned-in text screens, and skin density for thumbnail face-aiming. Both
  are kept in the repo as calibration evidence so nobody rebuilds them.
- **Lyric text is placed opposite the subject**, aggregated over every shot the
  block spans — sampling only the first shot puts text on the next face.
