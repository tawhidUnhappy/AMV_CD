---
name: amv-clip-selection
description: Select AMV footage using embedded episode subtitle tracks (text or OCR'd PGS bitmap) for story arc, theme match, and a tiny-decode visual probe, while structurally avoiding burned-in text screens and end-of-episode filler. Use when picking which source moments go on which song section (amv/subs/extract_subs.py, amv/render/select_clips/), or when clip choices look wrong/off-tone.
---

# AMV pipeline: clip selection

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

Use the episode's **embedded subtitle track** as the index of where things
happen. A 26-episode season yielded ~7,850 timestamped, text-labelled,
speaker-labelled moments to search over instead of sampling blind.

(If a release has no subtitle track at all — text or bitmap — this whole
approach is unavailable and you fall back to scene detection plus much
heavier visual QA.)

## Subtitle extraction traps

- **Take the `Format:` line from `[Events]`, not the first one.** In ASS,
  `[V4+ Styles]` has its own `Format:` with a different column set. Parsing
  Dialogue rows against it silently yields **zero** events — a bug that looks
  like "the file has no subtitles".
- Speaker names are often present but abbreviated (three-letter tags). Dump the
  distribution first; they are gold for character-targeted selection.
- Some releases **burn typesetting into the video** (on-screen text, phone or
  computer screens). No subtitle data marks these. See "Structural avoidance"
  below.
- Prefer an English *text* track (`ass`/`subrip`) when one exists — `subtitle_stream_index()`
  in `amv/core/ffmpeg_tools.py` picks it automatically.
- **A bitmap track (PGS/VobSub) is not a dead end — OCR it.** `amv/subs/pgs.py`
  decodes the bitmaps and `amv/subs/pgs_ocr.py` runs them through
  DeepSeek-OCR-2 (see [amv-environment-setup](../amv-environment-setup/SKILL.md)
  for why that model needs its own venv), producing the same timestamped-event
  shape `extract_subs.py` builds from a text track — clip selection downstream
  doesn't need to know which source it came from. Two things this needed that
  a text track wouldn't:
  - **Multiple PGS tracks per episode is normal** — a small "signs only" one
    alongside the full dialogue track. Picking by decoded byte size
    (`NUMBER_OF_BYTES` tag) reliably finds the real one; one release here had
    a 228KB signs track (19 subtitle events for a 23-minute episode) next to a
    10.7MB dialogue track (346 events) with an identical language tag.
  - PGS carries **no speaker names** — every OCR'd event has `speaker=""`, so
    speaker-targeted selection (§ below) only works for releases with a text
    track.

### PGS OCR takes real GPU time — extract the full series anyway

A text track costs nothing to extract (plain ffmpeg conversion, all episodes,
always). **OCR is a GPU model pass per subtitle line** — realistically several
minutes *per episode* (~1-2s/line x ~300+ lines), not a few seconds; a
24-episode season is a few hours of GPU time.

Extract (and OCR) the **whole series anyway, not a guessed subset.** Theme
matching (below) works by searching the full indexed dialogue for what
actually fits each lyric — picking episodes ahead of time by guessing which
ones "sound like" the song's themes throws away the thing that makes this
approach work at all, and a guess made without real plot knowledge of the
source is likely to be wrong in a way that's expensive to discover later
(re-extracting the episodes that were actually needed).

If you do need to economize (a very long series, or genuinely tight time),
`extract_subs.py --episodes '1-5,10,15,20,24'` limits the run and the index
*merges* across runs — a follow-up run topping up more episodes doesn't
re-OCR what's already indexed, so under-provisioning isn't a dead end, just
a slower path to the same full index.

## What works

- **Story arc**: map each song section to an episode range so the edit walks the
  series forward instead of shuffling uniformly.
- **Theme match**: score subtitle text against per-lyric keywords + a preferred
  speaker.
- **Visual probe**: decode each shortlisted window tiny (96x54 RGB, 8fps) and
  score brightness, contrast, motion and skin fraction. Rejects black frames,
  fades and static talking heads cheaply.

## What does NOT work

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

## Structural avoidance beats detection

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
