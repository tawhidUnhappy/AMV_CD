---
name: amv-lyric-video
description: Build a beat-synced anime music video with burned-in lyrics from local episode files and a song, using uv + ffmpeg + WhisperX + Demucs + librosa. Covers vocal-stem transcription, subtitle-driven clip selection, beat-snapped cutting, colour grading, ASS lyric overlays, and YouTube thumbnails/titles. Use when asked to make an AMV, a lyric video, or a music-video edit from local anime/video sources.
---

# AMV / lyric-video pipeline

Reference implementation: `D:\AMV_CD` (Mirai Nikki S1 x "Black Salt Halo").
Read this before rebuilding anything — most of it was learned the hard way and
several "obvious" approaches are documented here **because they failed**.

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

## 1. Environment (Windows + NVIDIA)

`uv init`, then these pins — each one blocks the pipeline if wrong:

| Pin | Reason |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in setuptools 81 |
| `nvidia-cudnn-cu12>=8.9,<9` | ctranslate2 4.4 links cuDNN **8**; torch cu124 bundles only cuDNN 9 |
| torch from `https://download.pytorch.org/whl/cu124` | GPU WhisperX/Demucs |
| `[tool.uv] environments = ["sys_platform == 'win32'"]` | Otherwise the resolver also solves Linux, where torch hard-pins cudnn 9 and conflicts with the cuDNN 8 above |

Two runtime shims are required (`amv/torch_compat.py`):

- **cuDNN 8 on the DLL path.** `os.add_dll_directory(.venv/Lib/site-packages/nvidia/cudnn/bin)`
  *before* `import ctranslate2`. torch's own cuDNN 9 lives in `torch/lib` and is
  registered automatically; ctranslate2's is not.
- **torch 2.6 `weights_only` flip.** The pyannote VAD checkpoint fails the safe
  unpickler. Retry with `weights_only=False` **and `args[0].seek(0)` first** —
  lightning passes an open file handle that the failed attempt leaves consumed.
  Do not chase the allowlist; the required globals differ per release.

## 2. Pipeline order

```powershell
$env:PYTHONPATH="<project>"
uv run python amv\isolate_vocals.py      # Demucs -> vocals.wav      (~8s on a 3060)
uv run python amv\transcribe_song.py --audio data\song\vocals.wav `
    --out data\song\transcript_vocals.json
uv run python amv\beats.py               # librosa -> beat grid
uv run python amv\extract_subs.py        # episodes -> ASS + scene index
uv run python amv\select_clips.py --candidates 8    # -> data/edl.json
uv run python amv\contact_sheet.py       # QA — REVIEW THIS BEFORE RENDERING
uv run python amv\lyric_overlay.py       # -> lyrics.ass   (reads edl.json!)
uv run python amv\render.py              # -> final mp4
uv run python amv\check_lyric_timing.py  # verify text sits over singing
```

Ordering traps: `lyric_overlay.py` reads `data/edl.json`, so it must run *after*
`select_clips.py`. Re-running `select_clips.py` invalidates lyric placement.

## 3. Lyric timing — transcribe the vocal stem

**Whisper on a full music mix produces wrong and missing lyrics.** Measured on
this project:

| | Full mix | Demucs vocal stem |
| --- | --- | --- |
| Aligned words | 222 | 287 |
| First line "I woke up" | **2.71s** (wrong) | **11.54s** (correct) |
| Whole lines dropped | 5 | 0 |

The full-mix pass invented a 0.02s-long "I" at 2.71s and smeared "woke" across
3.3s of instrumental, so the opening block appeared **nine seconds early**. It
also silently dropped five entire lines and misheard others ("pierce"→"kiss",
"back room"→"background"). Demucs `htdemucs` costs ~8 seconds. Always run it.

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

Fix: `librosa.beat.beat_track` (this song: 172.27 BPM, 0.348s, std 0.011s), then
snap every proposed cut to the nearest beat within ~half a beat. Result: all 154
cuts within 0.0000s of a beat. Also give lyric blocks a **~0.18s lead-in** so
they are readable *on* the beat rather than starting at it.

Because text timing comes from the vocal alignment and cuts come from the beat
grid, snapping cuts never desyncs the words.

**Frame-exactness.** Rendering N clips with `-t <seconds>` lets each round down
to a whole frame; 154 clips drifted **1.6s early** and `-shortest` truncated the
song. Quantise slot boundaries to frame indices on the shared timeline and
render exact counts with `-frames:v`. Residual: 8ms.

## 5. Clip selection

Use the episode's **embedded subtitle track** as the index of where things
happen — it gives ~7,850 timestamped, text-labelled, speaker-labelled moments to
search instead of blind sampling.

### Subtitle extraction traps

- **Take the `Format:` line from `[Events]`, not the first one.** `[V4+ Styles]`
  has its own with 23 columns. Using it silently parses **zero** events.
- Speaker names are often abbreviated (`Yuk`=Yukiteru, `Yun`=Yuno, `Mur`=Murmur).
  They are gold for character-targeted selection.
- Some releases **burn typesetting into the video** (diary/phone screens). No
  subtitle data marks these. See §5.3.

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

- Skip subtitle lines that quote a diary entry (`"`, `(`, `「`).
- Anchor to named main-cast speakers.
- **Trim the episode tail hard.** Post-ED omake ("Murmur's Counseling Room"),
  next-episode previews and credits occupy roughly the **last 90 seconds**. A
  25s tail trim let SD-comedy title cards into the edit; use ≥95s.
- Detect OP/ED as dialogue-free gaps ≥80s and exclude them.
- Keep a `BLACKLIST` of `(episode, start, end)` regions rejected on sight.
  Bath/fanservice scenes and remaining text screens need this — no metric
  catches them reliably.

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
- **Check whether the font is an outline face.** Kranky looked fine at thumbnail
  size but is hollow-stroked; over footage it washed out completely. Zoom to
  100% and look. A solid high-contrast serif (Georgia Bold) reads far better.
- Copy the font into an `assets/` dir and pass `fontsdir=` so lookup is
  reproducible.
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

Even aggregated this is approximate. Verify on a contact sheet of frames
*sampled while text is up*, not random frames.

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

Follow the user's own shipped examples if any exist. For this user: Title Case,
65–97 chars, 0–3 ALL-CAPS emphasis words, at most one `!`/`?`, no emoji, with a
trailing `- <Series> AMV`.

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

## 13. Windows / PowerShell notes

- `Set-Content -Encoding utf8` writes a **BOM**, which ffmpeg's concat demuxer
  rejects (`unknown keyword '\ufeffile'`). Use `-Encoding ascii`.
- PowerShell stringifies `5.0` as `"5"` — filenames built from floats will not
  match what you expect.
- The `tile` filter needs one input stream with N frames, not N inputs; feed it
  via the concat demuxer.
- Wildcard deletes may be blocked by the harness; delete directories or use
  fresh output paths.
