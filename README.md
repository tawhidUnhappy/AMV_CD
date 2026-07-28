# AMV_CD — Mirai Nikki × "Black Salt Halo"

A self-contained AMV pipeline. 16:9 1080p, grayscale, burned-in lyrics in white
with a red emphasis word per line.

Everything lives in `D:\AMV_CD`. Nothing is read from or written to
`D:\MediaConductor` at runtime — the ffmpeg helpers were copied in, not imported.

## Output

`data/out/amv_black_salt_halo.mp4` — 198.82s, 1920x1080, 23.976fps, H.264 +
AAC 256k.

## Setup

```powershell
cd D:\AMV_CD
uv sync
```

Windows-only by design (`tool.uv.environments`). Notable pins, each load-bearing:

| Pin | Why |
| --- | --- |
| `setuptools<81` | ctranslate2 4.4 imports `pkg_resources`, removed in 81 |
| `nvidia-cudnn-cu12>=8.9,<9` | ctranslate2 4.4 links cuDNN 8; torch bundles only cuDNN 9 |
| `torch` from `pytorch-cu124` | GPU WhisperX |

`amv/torch_compat.py` handles two more incompatibilities: it registers the cuDNN 8
directory on the DLL search path before `ctranslate2` imports, and it falls back
from torch 2.6's `weights_only=True` loader for the stock pyannote VAD
checkpoint (rewinding the file handle, which the failed attempt leaves consumed).

## Pipeline

Run in order:

```powershell
$env:PYTHONPATH="D:\AMV_CD"
uv run python amv\isolate_vocals.py       # Demucs -> data/song/vocals.wav
uv run python amv\transcribe_song.py --audio data\song\vocals.wav `
    --out data\song\transcript_vocals.json
uv run python amv\beats.py                # librosa -> beat grid (172 BPM)
uv run python amv\extract_subs.py         # 26 episodes -> ASS + scene index
uv run python amv\select_clips.py --candidates 8   # -> data/edl.json
uv run python amv\contact_sheet.py        # QA sheets, review before rendering
uv run python amv\lyric_overlay.py        # -> data/work/lyrics.ass  (needs the EDL)
uv run python amv\render.py               # -> data/out/amv_black_salt_halo.mp4
uv run python amv\check_lyric_timing.py   # every shown line sits over singing
```

`lyric_overlay.py` reads `data/edl.json`, so run it *after* `select_clips.py`.

### Transcribe the vocal stem, not the mix

This is load-bearing. Whisper run on the full mix put the opening "I woke up" at
**2.71s** when it is sung at **11.54s** — the block appeared nine seconds early —
and silently dropped five whole lines ("if i was born from a torn down prayer",
"demon lord, is that what i wear?", "crimes of smoke in my braided hair", "i
don't need mercy, i need a sign", "cold and silver, pulling me in"). It also
misheard "pierce in my throat" as "kiss" and "back room" as "background".

Demucs separation takes ~8s on the GPU and fixes all of it: 287 aligned words
instead of 222. `amv/check_lyric_timing.py` then verifies every displayed block
against energy in the vocal stem, so a repeat of that failure cannot ship
quietly.

### Where the cuts come from

- **Song side** — WhisperX `large-v3` plus forced alignment gives 222 word-level
  timestamps. `amv/lyrics.py` maps hand-written display phrases onto word-index
  ranges, so on-screen timing follows the actual vocal.
- **Source side** — every episode's embedded English ASS track is extracted and
  parsed into ~7850 timestamped dialogue events. Those events, not blind
  sampling, are what the selector searches.

- **Beat grid** — librosa reports 172.27 BPM, a beat every 0.348s (std 0.011s).

`amv/timeline.py` turns the lyric phrases into ~155 gapless slots covering the
song: one cut per lyric line (split at 3.2s), rapid cuts through the seven
instrumental breaks. **Every cut is then snapped to the beat grid** — all 154
boundaries land within 0.0000s of a beat. Lyric *text* timing is generated
separately from the vocal alignment, so moving a cut by up to ~0.17s never pulls
the words off the singing.

`amv/select_clips.py` fills each slot using three signals — a per-section
episode range so the edit walks the series forward, keyword + speaker matching
against subtitle text for lyric slots, and a small decoded probe (brightness,
contrast, motion, skin fraction) that rejects black frames and favours shots
with a character in them.

## Things that were measured, not assumed

Two detectors were built, calibrated against frames judged by eye, and one was
**rejected**:

- *Fine-scale edge density*, to catch the burned-in diary/phone screens. It did
  not separate them: good frames scored 0.099–0.201, text screens 0.113–0.322.
  Discarded. `amv/calibrate_detail.py` retains the evidence.
- *Skin fraction*, as a "character on screen" proxy. Character shots averaged
  0.30 versus 0.15 for scenery and text — a real but noisy gap (warm food reads
  as skin, unlit night shots read as none). Kept as a **weight, never a gate**.
  See `amv/calibrate_skin.py`.

Because the text-screen detector failed, diary screens are avoided
structurally instead: quoted diary-reading lines are skipped, and shots are
anchored to named main-cast dialogue.

Two more corrections came from measurement rather than guesswork:

- The first render drifted **1.61s early** by the end — 154 clips each rounding
  down to a whole frame. `slot_frames()` now quantises slot boundaries on the
  shared timeline and renders exact frame counts (`-frames:v`). Residual: 8ms.
- The first grade left **15.3% of runtime under 0.12 luma** and 7.3% near-black.
  `amv/check_exposure.py` found it; lifting the shadow point and easing the
  vignette brought that to 6.8% / 3.8%.
- A reported "~1s sync delay" was **not** a mux offset: `amv/check_sync.py`
  cross-correlates the rendered track against the source mp3 and measures
  +0.000s. The looseness was editorial — cuts sat on vocal onsets and a flat
  0.75s grid rather than on the beat. Fixed by beat-snapping every cut and
  giving lyric blocks a 0.18s lead-in so they are readable *on* the beat rather
  than starting at it.

## Look

- **Grade** — colour, not grayscale: cool shadows, near-neutral midtones and
  highlights, mild saturation lift, S-curve contrast, vignette. An earlier
  version warmed the highlights and washed the whole video orange — this source
  is full of sunset scenes and the push stacked on top of them. Tune it with
  `amv/grade_preview.py`, which grades real frames without a full render.
- **Lyrics on the hooks only** — 17 of 47 phrases carry text (`show=True` in
  `amv/lyrics.py`). The rest of the song plays on footage alone.
- **Transitions** — hard cuts on the beat inside a section (that is what gives
  an AMV its drive), a 0.2s dip to black at the 14 section handovers, and a 1.6s
  open / 3.5s close from and to black.
- **Text in/out** — blocks drift up into place (`\move`), resolve out of a blur
  haze and dissolve back into one on exit.
- **Radial focus** — a sharp circle in the middle falling off to a `gblur`
  sigma-17 edge, composited with `maskedmerge` against a smoothstep mask written
  as a binary PGM (`write_focus_mask`). Applied *before* the subtitle burn, so
  the lyrics stay sharp wherever they sit.
- **Type** — Georgia Bold, white, no drop shadow, one red word per phrase, placed
  on the opposite side of the frame from the subject.
  The originally specified Kranky is an *outline* face; its hollow strokes
  washed out over footage, so it was swapped after a rendered side-by-side
  (`amv/font_compare.py`).
- **Animation** — no GIF/APNG needed; libass does this natively. Blocks
  materialise out of a `\blur` haze via `\t()`, and emphasis phrases get an
  offset red ghost layer that fades out — a chromatic split that reads as unease
  rather than as a render fault.
- **Placement** — `subject_side()` reuses the skin-fraction probe to find which
  half of the shot the character occupies, and places the text on the opposite
  side. The first pass centred chorus hooks and landed them on people's faces.

## Human-in-the-loop QA

`amv/contact_sheet.py` renders every chosen frame to tiled sheets. Three review
passes drove real fixes:

- `TAIL_SKIP` was raised 25s → 95s after SD-comedy title cards reached the edit:
  the post-ED "Murmur's Counseling Room" omake occupies the last ~90s of most
  episodes.
- Break slots were re-anchored from dialogue-*free* gaps to main-cast dialogue.
  Dialogue-free stretches turned out to be establishing shots — streets, trees,
  an air conditioner — not the action the first pass assumed.
- `BLACKLIST` in `select_clips.py` holds regions rejected on sight, including a
  bath scene and fanservice framings that no metric flags reliably.

Re-review the sheets after any change to selection; the blacklist is keyed to
source timestamps, so it survives re-selection but not re-timing.

## Known limitations

- Clip choice is heuristic. Roughly one shot in ten is still merely
  serviceable rather than good; a further QA-and-blacklist pass would tighten it.
- Two lyric phrases ("YOUR MOUTH SAYS ANGEL", "IF I WAS MADE") use
  `start_override` because forced alignment smeared held notes 8-9s ahead of the
  intelligible vocal. Loudness could not settle it — those spans are loud
  instrumental bars, not quiet gaps — so they are anchored to the sung line on
  the grounds that text arriving slightly late reads far better than text
  hanging 9s early.
- OP/ED detection finds credit sequences as 80s+ dialogue-free gaps. In a few
  episodes only one of the two is found; the 95s tail trim covers the rest.
