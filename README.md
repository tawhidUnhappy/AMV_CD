# AMV / lyric-video pipeline

Builds a beat-synced, colour-graded music video with burned-in lyrics from a
folder of episode files and a song.

Self-contained: the only external requirements are `ffmpeg`/`ffprobe` on PATH,
`uv`, and an NVIDIA GPU for the ML steps. Nothing outside this directory is
read except the media you point it at in `config.json`.

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
command-line flag. `uv run python amv/config.py` prints what resolved.

## Running the pipeline

```bash
export PYTHONPATH=.          # Windows: $env:PYTHONPATH="."
uv run python amv/isolate_vocals.py    # Demucs -> vocal stem
uv run python amv/transcribe_song.py   # WhisperX -> word-level timings
uv run python amv/beats.py             # librosa -> beat grid
uv run python amv/extract_subs.py      # episodes -> subtitles + scene index
uv run python amv/select_clips.py --candidates 8
uv run python amv/contact_sheet.py     # REVIEW THIS before rendering
uv run python amv/lyric_overlay.py     # -> lyrics.ass  (needs the EDL)
uv run python amv/render.py            # -> data/out/amv.mp4
```

`lyric_overlay.py` reads `data/edl.json`, so run it *after* `select_clips.py`.

### Adapting to your own song

`amv/lyrics.py` holds the lyric plan: phrases mapped to word-index ranges in the
transcript, with line breaks, a red emphasis word, and a `show` flag. Rebuild it
for a new track by dumping the aligned words (`amv/dump_words.py`) and writing
phrases against them. `validate()` guards against index drift.

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
| `contact_sheet.py` | wrong, ugly or off-tone footage — the biggest win |
| `check_lyric_timing.py` | lyric text not sitting over singing |
| `check_sync.py` | genuine A/V offset vs merely loose editing |
| `check_exposure.py` | an over-crushed grade |
| `grade_preview.py` | grade tuning without a full re-render |
| `font_compare.py` | outline fonts that wash out over footage |

## Extras

- `amv/thumbnail.py` composes YouTube thumbnails from real frames (three
  layouts: label-arrow, speech bubble, split). No image generation.
- `amv/thumb_candidates.py` pulls strong frames to choose from.

## Environment notes (Windows + NVIDIA)

Four pins in `pyproject.toml` are load-bearing:

| Pin | Reason |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in 81 |
| `nvidia-cudnn-cu12>=8.9,<9` | ctranslate2 4.4 links cuDNN 8; torch bundles only cuDNN 9 |
| torch from the cu124 index | GPU WhisperX / Demucs |
| `environments = ["sys_platform == 'win32'"]` | otherwise the resolver also solves Linux, where torch hard-pins cudnn 9 and conflicts |

`amv/torch_compat.py` adds two runtime shims: it puts the pip-installed cuDNN 8
on the DLL search path before `ctranslate2` imports, and it works around torch
2.6's `weights_only` default for the pyannote VAD checkpoint.

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
