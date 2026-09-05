---
name: amv-grade-and-transitions
description: Colour-grade AMV footage (cool shadows, neutral highlights, exposure re-check) and apply radial focus blur and cut/section transitions. Use when tuning grade_preview.py / check_exposure.py, when the video looks washed out or crushed, or when adding dip-to-black / fade transitions.
---

# AMV pipeline: grade and transitions

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

## Grade

- Colour: cool the shadows, keep midtones and highlights **near neutral**, small
  saturation lift, S-curve contrast, vignette.
- **Do not warm the highlights** on a sunset-heavy source — it stacks on top of
  the existing warmth and washes the whole video orange.
- Tune on stills (`grade_preview.py` grades real frames), never by re-rendering.
- **Re-measure exposure after grading.** The first grade put 15.3% of runtime
  under 0.12 luma and 7.3% near-black, swallowing whole shots. Target roughly
  <8% and <4%. Remember to subtract *intentional* darkness (fades, dips) before
  concluding the grade is wrong.

## Radial focus blur

`split` → `gblur` → `maskedmerge` against a smoothstep mask written as a binary
PGM. Two traps:

- Apply it **before** burning subtitles, or the text blurs at the edges too.
- A `-loop 1` image input never ends, so the filtergraph pads the video out to
  the audio length. Cap the output with `-frames:v`.

## Transitions

- Hard cuts on the beat *inside* a section — that is what gives an AMV drive.
  (Cut timing itself is covered in [amv-beat-cutting](../amv-beat-cutting/SKILL.md).)
- A short dip to black (~0.2s out + 0.2s in) **only at section handovers**.
- Global fade from black (~1.5s) and to black (~3.5s).
