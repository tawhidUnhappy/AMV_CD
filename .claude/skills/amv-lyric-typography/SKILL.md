---
name: amv-lyric-typography
description: Render AMV lyric overlays as ASS/libass (colour, sizing, blur/move animation, face-avoiding placement) and decide which phrases get on-screen text at all. Use when working on amv/lyric_overlay.py, font_compare.py, when text overlaps a face, or when the video reads like a subtitle track instead of an AMV.
---

# AMV pipeline: lyric typography (ASS / libass)

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

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

## Placement — the face-collision bug

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

Note the same skin heuristic *is* good enough for the coarser left-vs-right
question here, even though it is **not** good enough for aiming a thumbnail
arrow precisely — see [amv-thumbnails-and-titles](../amv-thumbnails-and-titles/SKILL.md).
Precision requirements differ: "which half of frame" tolerates noise that
"point an arrow at this face" does not.

## Lyrics on some lines only

Text on every line reads as a subtitle track, not an AMV. Put text on roughly
**one third** of phrases — the hooks and the striking images — and let the rest
play on footage. Keep *all* phrases timed (the cut structure follows the whole
song) and gate display behind a `show` flag.
