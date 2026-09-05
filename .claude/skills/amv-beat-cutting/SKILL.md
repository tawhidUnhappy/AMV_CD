---
name: amv-beat-cutting
description: Snap AMV cuts to a librosa beat grid (not vocal onsets) and render frame-exact clip lengths. Use when an edit "doesn't click" rhythmically, when tuning cut timing, or when clip counts/lengths drift from the expected song duration.
---

# AMV pipeline: cuts on the beat grid

Part of the [amv-lyric-video](../amv-lyric-video/SKILL.md) pipeline.

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

Because text timing comes from the vocal alignment (see
[amv-lyric-sync](../amv-lyric-sync/SKILL.md)) and cuts come from the beat grid,
snapping cuts never desyncs the words.

**Frame-exactness.** Rendering N clips with `-t <seconds>` lets each round down
to a whole frame; 154 clips drifted **1.6s early** and `-shortest` truncated the
song. Quantise slot boundaries to frame indices on the shared timeline and
render exact counts with `-frames:v`. Residual: 8ms.
