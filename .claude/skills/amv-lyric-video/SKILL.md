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

## 0. Golden rules

1. **Transcribe an isolated vocal stem, never the full mix.** This is the single
   highest-impact step. See §3.
2. **Cuts go on beats. Lyric text goes on the vocal.** Two separate clocks.
3. **Look at the output.** Every quality problem in this project was found by
   rendering frames and looking, not by reasoning. Build contact sheets.
4. **Measure before tuning.** Exposure, sync and timing all had numeric checks
   that overturned a guess.
5. **A failed detector is a result.** Two detectors here did not work. They are
   documented so nobody rebuilds them.

## 0.5 Make it configurable from the start

Put `source_dir`, `episode_pattern`, `song`, font and output format in a
`config.json` read by one module, and default every CLI flag from it. Hardcoding
a media path into each script means the project only ever works for one person
on one machine, and untangling it later touches every file.

Likewise: locate site-packages via `sysconfig`, not a literal `.venv/Lib/...`,
and look up system fonts through a per-platform directory list rather than
`C:/Windows/Fonts`.

## 1. Environment (Windows + NVIDIA)

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

## 2. Pipeline order

```bash
export PYTHONPATH=.                    # Windows: $env:PYTHONPATH="."
uv run python amv/isolate_vocals.py    # Demucs -> vocal stem (~8s on a 3060)
uv run python amv/transcribe_song.py   # WhisperX on the stem -> word timings
uv run python amv/beats.py             # librosa -> beat grid
uv run python amv/extract_subs.py      # episodes -> subtitles + scene index
uv run python amv/select_clips.py --candidates 8    # -> data/edl.json
uv run python amv/contact_sheet.py     # QA — REVIEW THIS BEFORE RENDERING
uv run python amv/lyric_overlay.py     # -> lyrics.ass   (reads edl.json!)
uv run python amv/render.py            # -> final mp4
uv run python amv/check_lyric_timing.py  # verify text sits over singing
```

Ordering traps: `lyric_overlay.py` reads `data/edl.json`, so it must run *after*
`select_clips.py`. Re-running `select_clips.py` invalidates lyric placement.

## 3. Lyric timing — transcribe the vocal stem

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

## 4. Cuts — beat grid, not vocal onsets

If the edit "doesn't click", **check sync numerically before assuming a bug.**
`check_sync.py` cross-correlates rendered audio against the source; this project
measured **+0.000s**. The looseness was editorial: cuts sat on vocal onsets and
a flat 0.75s grid.

Fix: `librosa.beat.beat_track` (one track measured 172.27 BPM, 0.348s spacing,
std 0.011s), then snap every proposed cut to the nearest beat within ~half a
beat interval. Result there: all 154 cuts within 0.0000s of a beat. Also give
lyric blocks a **~0.18s lead-in** so they are readable *on* the beat rather than
starting at it.

Note that `beat_track` often locks onto a subdivision (172 BPM is likely 86 BPM
counted in eighths). That is fine — any consistent subdivision is a valid grid;
just choose the cut spacing as a multiple of it.

Because text timing comes from the vocal alignment and cuts come from the beat
grid, snapping cuts never desyncs the words.

**Frame-exactness.** Rendering N clips with `-t <seconds>` lets each round down
to a whole frame; 154 clips drifted **1.6s early** and `-shortest` truncated the
song. Quantise slot boundaries to frame indices on the shared timeline and
render exact counts with `-frames:v`. Residual: 8ms.

## 5. Clip selection

Use the episode's **embedded subtitle track** as the index of where things
happen. A 26-episode season yielded ~7,850 timestamped, text-labelled,
speaker-labelled moments to search over instead of sampling blind.

(If a release has no text subtitle track, this whole approach is unavailable and
you fall back to scene detection plus much heavier visual QA.)

### Subtitle extraction traps

- **Take the `Format:` line from `[Events]`, not the first one.** In ASS,
  `[V4+ Styles]` has its own `Format:` with a different column set. Parsing
  Dialogue rows against it silently yields **zero** events — a bug that looks
  like "the file has no subtitles".
- Speaker names are often present but abbreviated (three-letter tags). Dump the
  distribution first; they are gold for character-targeted selection.
- Some releases **burn typesetting into the video** (on-screen text, phone or
  computer screens). No subtitle data marks these. See §5.3.
- Prefer an English *text* track (`ass`/`subrip`); bitmap tracks (PGS/VobSub)
  carry no parsable text.

### 5.1 What works

- **Story arc**: map each song section to an episode range so the edit walks the
  series forward instead of shuffling uniformly.
- **Theme match**: score subtitle text against per-lyric keywords + a preferred
  speaker.
- **Visual probe**: decode each shortlisted window tiny (96x54 RGB, 8fps) and
  score brightness, contrast, motion and skin fraction. Rejects black frames,
  fades and static talking heads cheaply.

### 5.2 What does NOT work

- **"Dialogue-free gaps are action."** They are not — they are *establishing
  shots*: streets, trees, signage, an air conditioner. Anchor clips to
  **named main-cast dialogue** instead and let the motion score find the kinetic
  ones.
- **Edge-density to detect burned-in text screens.** Measured: good frames
  0.099–0.201, text screens 0.113–0.322. The distributions overlap; there is no
  usable threshold. Do not rebuild this.
- **Skin fraction as a hard gate.** Character shots averaged 0.30 vs 0.15 for
  scenery — a real signal, but the tails overlap badly (warm food reads as skin;
  an unlit night shot reads as none). Use it as a **weight, never a gate**.

### 5.3 Structural avoidance beats detection

Since the text-screen detector failed, avoid those shots structurally:

- Skip subtitle lines that quote on-screen text (`"`, `(`, `「`) — those play
  over a full-screen graphic.
- Anchor to named main-cast speakers.
- **Trim the episode tail hard.** Post-ED omake segments, next-episode previews
  and credits commonly occupy the **last 60–90 seconds**. A 25s tail trim let
  SD-comedy title cards into the edit; ≥95s fixed it. Check your own release.
- Detect OP/ED as dialogue-free gaps ≥80s and exclude them. Expect this to find
  only one of the two in some episodes (dialogue over the ED breaks the gap) —
  the tail trim is the backstop.
- Keep a `BLACKLIST` of `(episode, start, end)` regions rejected on sight.
  Fanservice/bath scenes and remaining text screens need this — no metric
  catches them reliably, and the cost of one slipping into a published video is
  much higher than the cost of a manual list.

## 6. Grade

- Colour: cool the shadows, keep midtones and highlights **near neutral**, small
  saturation lift, S-curve contrast, vignette.
- **Do not warm the highlights** on a sunset-heavy source — it stacks on top of
  the existing warmth and washes the whole video orange.
- Tune on stills (`grade_preview.py` grades real frames), never by re-rendering.
- **Re-measure exposure after grading.** The first grade put 15.3% of runtime
  under 0.12 luma and 7.3% near-black, swallowing whole shots. Target roughly
  <8% and <4%. Remember to subtract *intentional* darkness (fades, dips) before
  concluding the grade is wrong.

### Radial focus blur

`split` → `gblur` → `maskedmerge` against a smoothstep mask written as a binary
PGM. Two traps:

- Apply it **before** burning subtitles, or the text blurs at the edges too.
- A `-loop 1` image input never ends, so the filtergraph pads the video out to
  the audio length. Cap the output with `-frames:v`.

## 7. Lyric typography (ASS / libass)

Render lyrics as an ASS file burned with the `subtitles` filter. libass gives
rotation, per-word colour, vector shapes and a real animation engine — **no GIF
or APNG is needed or wanted** for "animated text".

- ASS colours are `&HAABBGGRR` — byte order reversed from hex RGB.
- **Check whether the font is an outline face.** One display font looked fine
  small but is hollow-stroked; over footage it washed out completely. Zoom to
  100% and look, or run a `font_compare` render. A solid high-contrast serif
  reads far better over busy video.
- Copy the font into an `assets/` dir and pass `fontsdir=` so lookup does not
  depend on system font configuration.
- Sizing: pick per-phrase from the longest line length. Text that looks right in
  a code review is usually **half** the size it should be — the reference AMV
  look is big.
- Animation: `\blur` in/out via `\t()` to materialise out of haze; `\move` to
  drift into place (note `\move` and `\pos` are mutually exclusive); an offset
  red ghost layer that fades = chromatic-split unease.
- Clamp each block's hold against the next block's start, or two lyrics overlap.

### Placement — the face-collision bug

**Never centre lyric text.** It lands on faces. Place it on the side of frame
opposite the subject, using per-column skin mass.

> **Bug worth avoiding:** a lyric block routinely spans **several cuts**, and the
> character is somewhere different in each. Sampling only the *first* shot
> places text clear of that one face and straight across the next. Aggregate
> skin mass over **every slot the block is on screen for**, including the
> lead-in and hold, then pick the side that stays clear for the whole duration.

Even aggregated this is approximate. **Verify on a contact sheet of frames
sampled while text is up** — sample near each block's *end*, where a later cut
may have swapped the shot out from under it. Random frames will not find this
bug.

Measured outcome here: aggregating took collisions from frequent to 2 of 17.
The two that remain are the honest limits of the approach:

- **Shots within one block disagree** — the subject is left in one and right in
  the next, so no single side is clear for the whole block. Either accept it or
  split the block so each half is placed independently.
- **Extreme close-ups fill the frame** — there is no empty side at all. A
  reasonable extension is to detect "both sides occupied" and fall back to the
  top or bottom band, which is usually calmer than the centre.

## 8. Lyrics on some lines only

Text on every line reads as a subtitle track, not an AMV. Put text on roughly
**one third** of phrases — the hooks and the striking images — and let the rest
play on footage. Keep *all* phrases timed (the cut structure follows the whole
song) and gate display behind a `show` flag.

## 9. Transitions

- Hard cuts on the beat *inside* a section — that is what gives an AMV drive.
- A short dip to black (~0.2s out + 0.2s in) **only at section handovers**.
- Global fade from black (~1.5s) and to black (~3.5s).

## 10. Thumbnails

Compose from **real frames** — no image generation. 1280x720. Draw text, arrows
and speech bubbles through libass (ffmpeg's `drawtext` cannot rotate).

House style (calibrate against the user's own examples first): ALL-CAPS yellow
`#FFE600`, black stroke ~12% of font size, slight tilt, fat block arrows,
bottom-right kept clear for YouTube's duration overlay.

### The arrow bug — and why auto-aiming failed

Two separate mistakes produced arrows pointing at nothing:

1. **Frame choice.** The first pass labelled `YANDERE` over a frame where the
   character faced *away* — the arrow pointed at the back of her head. Pick a
   frame where the subject faces camera *before* writing labels.
2. **Guessed coordinates.** Arrows were hand-placed as `(x, y, angle)`. Guessing
   an angle from imagination puts arrows beside, past, or through the subject.

**Fix:** specify `from_xy` (the label) and `to_xy` (the thing being named); the
position and angle are computed with `atan2`. Read `to_xy` off the rendered
image.

**Auto-detection does not work on warm sources.** A skin-density peak finder
lands on tatami mats, wood panelling and sunset walls, which all satisfy the
skin predicate. Centroids are worse still — they get dragged toward torso and
limbs and land on a character's chest or on empty space between two people. Use
detection only as a hint on cool/dark frames, and **always verify by rendering
the thumbnail and looking at it.**

Note the same skin heuristic *is* good enough for the coarser
left-vs-right question in lyric placement (§7). Precision requirements differ:
"which half of frame" tolerates noise that "point an arrow at this face" does
not.

### Bubble preset trap

ASS centres a `\p1` drawing by its **bounding box**. A speech-bubble tail
extends the bbox downward, so an `\an5` anchor drags the whole bubble off
position. Draw bubbles in **absolute screen coordinates** with `\an7\pos(0,0)`,
and use `\org(cx,cy)` if you want rotation.

### Split-layout crop

A half-width crop of a 16:9 frame has **horizontal slack only**. If the subject
sits high in frame their face is cut off and no horizontal shift helps. Zoom in
first to create vertical slack, expose both `shift` and `vshift`, or pick a
frame with a centred subject. Two rounds of offset-guessing here were wasted —
swapping to a well-centred frame took one.

## 11. Titles and description

**If the user has shipped titles or thumbnails before, read those first and
match them.** They encode preferences no style guide will tell you. Ask where
they are if it is not obvious.

Absent a house style, a workable default: Title Case, 65–97 characters, 0–3
ALL-CAPS emphasis words, at most one `!`/`?`, no emoji, ending with
`- <Series> AMV`.

**Never invent a credit.** If the song's artist is not identifiable from the
file, leave an explicit `<ARTIST>` placeholder and say so. A fabricated credit
gets published as fact.

Calibration rule: validate any new lint against the user's real shipped work
before committing thresholds. A check that nags about known-good output trains
everyone to ignore it.

## 12. Verification scripts to build

Each of these caught a real defect:

| Script | Catches |
| --- | --- |
| `contact_sheet.py` | wrong/ugly/off-tone footage — the biggest win |
| `check_lyric_timing.py` | text not over singing |
| `check_sync.py` | genuine A/V offset vs editorial looseness |
| `check_exposure.py` | over-crushed grade |
| `grade_preview.py` | grade tuning without a full render |

## 12.5 Attribution and safety

- **Never invent a credit.** If the song's artist is not identifiable from the
  file, leave a visible `<ARTIST>` placeholder and say so. A fabricated credit
  gets published as fact.
- Include a fair-use / non-profit note and credit the studio and artist.
- Do not commit the source video, the song, the separated stem, or licensed
  fonts. `.gitignore` should cover `data/` and the media extensions in
  `assets/`; verify with `git check-ignore -v <file>`.

## 13. Windows / PowerShell notes

- `Set-Content -Encoding utf8` writes a **BOM**, which ffmpeg's concat demuxer
  rejects (`unknown keyword '\ufeffile'`). Use `-Encoding ascii`.
- PowerShell stringifies `5.0` as `"5"` — filenames built from floats will not
  match what you expect.
- The `tile` filter needs one input stream with N frames, not N inputs; feed it
  via the concat demuxer.
- Wildcard deletes may be blocked by the harness; delete directories or use
  fresh output paths.
