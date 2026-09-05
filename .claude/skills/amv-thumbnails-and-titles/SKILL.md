---
name: amv-thumbnails-and-titles
description: Compose YouTube thumbnails from real frames with libass text/arrows/bubbles, and write titles/descriptions with correct attribution. Use when working on amv/thumbnail.py, when an arrow points at nothing, when a split-layout crop cuts off a face, or when drafting the video title/description/credits.
---

# AMV pipeline: thumbnails and titles

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

## Thumbnails

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

The same skin heuristic *is* good enough for the coarser left-vs-right question
in lyric placement (see [amv-lyric-typography](../amv-lyric-typography/SKILL.md)) —
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

## Titles and description

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

## Attribution and safety

- **Never invent a credit.** If the song's artist is not identifiable from the
  file, leave a visible `<ARTIST>` placeholder and say so. A fabricated credit
  gets published as fact.
- Include a fair-use / non-profit note and credit the studio and artist.
- Do not commit the source video, the song, the separated stem, or licensed
  fonts. `.gitignore` should cover `data/` and the media extensions in
  `assets/`; verify with `git check-ignore -v <file>`.
