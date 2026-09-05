---
name: amv-clip-selection
description: Select AMV footage using embedded episode subtitle tracks for story arc, theme match, and a tiny-decode visual probe, while structurally avoiding burned-in text screens and end-of-episode filler. Use when picking which source moments go on which song section (amv/extract_subs.py, amv/select_clips.py), or when clip choices look wrong/off-tone.
---

# AMV pipeline: clip selection

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

Use the episode's **embedded subtitle track** as the index of where things
happen. A 26-episode season yielded ~7,850 timestamped, text-labelled,
speaker-labelled moments to search over instead of sampling blind.

(If a release has no text subtitle track, this whole approach is unavailable and
you fall back to scene detection plus much heavier visual QA.)

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
- Prefer an English *text* track (`ass`/`subrip`); bitmap tracks (PGS/VobSub)
  carry no parsable text.

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
