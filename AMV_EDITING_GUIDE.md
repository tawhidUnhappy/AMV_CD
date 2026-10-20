# AMV editing guide

How good anime edits are made: styles, clip selection and flow, sync, speed and
velocity, shakes and camera motion, transitions, effects, colour, text, and sound
design (sound effects and audio effects). Gathered from the web on 2026-10-20 (sources
at the end). Each technique is marked with how AMV_CD does it today:

- **have**: a spec key or plug-in that does it (`./amv.sh edit` / `montage` specs, `video_fx`, `song_fx`)
- **gap**: not built yet. These are the things to add next.

Numbers are starting points taken from the sources. Judge the result by eye and ear.

---

## 1. Why an edit "feels off" (read this first)

1. **Clip selection decides flow more than transitions do.** "Most people just pick cool
   clips, not clips that connect." Flow means the edit plays as one continuous movement:
   a punch carries into the next shot, a zoom carries over, a movement finishes where the
   next one begins. Clips should read like a sentence, not a list of random words. [Molob, Flow]
2. **Plan the transition while choosing the clips.** If you choose clips first and think
   about transitions afterwards, you end up forcing clips together, and those edits get
   scrapped. [Molob, Flow]
3. **Sound design is half the feel.** With the same clips, transitions and effects, the
   version with sound effects "feels way more satisfying". [Molob, SFX]
4. **Sync to the frame.** Sound effects moved just **3 frames** off made a whole edit feel
   disconnected. [Molob, SFX]
5. **Restraint.** More effects do not make a better edit. Every effect and sound needs a
   purpose. "Vibe" style teaches this. [Molob, Styles; Molob, SFX]

Lessons from AMV_CD's own edits:
- Rezero_changing (2026-10-20) was judged bad. It had beat cuts and effects, but no
  sound effects, no audio effects, no clip links (shots were chosen by dialogue keyword
  or by mood), mostly still talking heads, and no velocity.

## 2. Styles (Molob's beginner tier list)

| Style | What it is | Tier | AMV_CD |
|---|---|---|---|
| **Flow** | Clips whose movement connects shot to shot. Teaches syncing, pacing, clip selection, transitions, shakes, effects and sound | S | partial: `./amv.sh flow` measures motion at the head and tail of each shot; `align`, `whip`. No link finder |
| **Velocity** | Twixtor or time remap: slow the clip, speed it up on the beat, plus scaling and colour correction | S (best first edit) | have: `velocity` keyframes, `trail` motion blur. No optical-flow interpolation (gap) |
| **Vibe** | Chill and clean, slower songs, opacity and small scale transitions | A | have: `dissolve`, `zoom` |
| **Typography** | Animated lyrics or words that are part of the frame | B | partial: `text` (pop, glitch, tracking, flicker). No per-letter animation or masking behind characters |
| **Mograph** | Custom shape and solid elements, a consistent colour theme | C | gap |
| **Compositing** | Characters masked onto new backgrounds, relit | C | gap (needs segmentation) |
| **Polyester** | Lots of masking with fast guitar songs | D | gap (masking) |
| **Roto** | Rotation transitions with heavy overlays | D | gap (rotation) |
| **VFX** | Effects transform the clips and carry transitions | D (advanced) | partial: glitch_fx, Blender segments |
| **Manga animation** | Manga panels animated | F (hardest) | — |
| **Depth map** | A twixtor edit with a depth-map effect over all of it | F ("we do not need more") | — |

Channels the owner pointed at (2026-10-20):
- **Toxic AMV (@Toxic404Team):** full-length 1.5–3 min AMVs on high-energy tracks (phonk,
  hardtekk, jumpstyle, montagem, dubstep, often "slowed"/"super slowed"/"sped up"). Titles
  are "Artist - Song (Toxic AMV)".
- **Molob (@Molob):** 20–40 s character edits ("took me 10+ hours"), plus the tutorials used
  in this guide.

## 3. Clips and flow

**Finding clips**
- Collect far more clips than you need. "Editing is like cooking: few ingredients, few
  dishes." [Molob, Flow] → have: library index, `short-parts`, `intro --gallery`.
- Prefer clips chosen for **movement and mood** over plot. Action edits often use just one
  or two fights. [AMV.org forum]
- Source quality: 1080p or better, no subtitles or watermarks. Continuous shots of 3–15 s
  retime best. [AnimeWorld Twixtor] → have: OP/ED (repeat) exclusion. Burned-in subtitles
  are not detected (gap).

**Links (what makes two clips flow)**
- Similar movement, similar camera motion, similar character position, or anything else
  that connects them. Find the links, put them on the beats, and test. [Molob, Flow]
- Almost-links can be fixed:
  - **Reverse / ping-pong:** time-remap the end of clip A so a hand moving right returns
    left into clip B. [Molob, Flow] → gap (`reverse` / `pingpong` on a shot)
  - **Flip horizontally** when facing directions don't match: "helps a lot more than
    people think." [Molob, Flow] → gap (`flip: true`)
- Eye trace: keep the focal point where it was across the cut. → have: `align` +
  `focus_head/tail`.
- Transition **into** the motion: if the next clip is tighter on the face, zoom into the
  face so it feels like the camera moving closer. Always ask "how can this transition be as
  seamless as possible?" [Molob, Flow] → have: `zoom`, `punch`, `whip`.

**Creative transitions (when clips don't link)**
- **Mask transition:** mask the character or object from the next clip and bring it into
  the clip before, right at the end, so position and motion continue. Don't use a character
  cut off by the frame, because the mask edge shows. [Molob, Flow] → gap (needs anime
  segmentation)
- **Eye transition:** zoom into an eye and the next clip is inside it, or zoom out of an
  eye from the previous clip. The eye shot must already be close, or the zoom shows
  pixels. [Molob, Flow] → gap
- **Matched glow:** make something glow in A (an eye) and something in B (a ball), then
  match their position and size across the cut. [Molob, Flow] → gap (glow exists; matching
  doesn't)
- **Mixed sync:** lyric sync over vocals, beat sync over instrumentals, so the sync never
  becomes predictable. [AMV.org forum]

## 4. Timing and sync

- **Beat sync:** the simplest kind and the easiest to overdo. It suits action and upbeat
  songs and can ruin a slow, moody video. [AMV.org forum]
- **Lyric sync:** the picture matches the words. → partial: `text` placed at word times.
- **Lip sync:** easiest when the speaking character's mouth is the only thing moving in the
  frame. Avoid lip flaps when you aren't syncing them. [Phade's guide] → gap
- **Ears over waveform:** the hit may not sit where the waveform peak is. If it looks
  wrong, it is wrong. [AMV.org newsletter]
- **Cut on the song's own accents** (onsets), with every cut on a beat or onset and the hits
  on the strongest ones. → have: `blender-beats`, `short-song`, the amv-ops flow rules.
- **Before the drop:** a few beats of silence or accelerating subdivisions; set aside 2, 4
  or 8 bars to build tension. [Baby Audio]

## 5. Speed: velocity, slow motion, freezes

| Technique | Values from the sources | AMV_CD |
|---|---|---|
| Velocity on the beat | Speed **200%** on the beat marker, **20%** between, back to 200% on the next. Easy Ease, then refine in the graph editor [AEJuice]. TikTok variant: 150 on the beat, then 50 right after | have: `velocity: [[0, 2.0], [0.25, 0.2], [1, 0.2]]` |
| Zoom pulse with velocity | Scale **100 → 130 → 100** between beat markers, eased [AEJuice] | have: `zoom`, `ease`, `bass_zoom` |
| Speed ramp | 100% → **25–40%** just before peak action → back to 100%, Bezier. Slow the anticipation, not the impact [AnimeWorld Twixtor] | have: `velocity` keyframes |
| Slow motion (Twixtor) | **25–50%**, never below 20% without pre-processing. Motion-weighted blend (optical flow ghosts on flat anime colour), motion sensitivity ~0.7, input FPS = source (24, animation on twos) [AnimeWorld Twixtor] | partial: `speed` < 1 repeats frames. **gap: frame interpolation** (RIFE/optical flow) for smooth slow motion |
| Twixtor artifacts | Lower motion sensitivity to reduce warping, raise it to reduce blending, keyframe it if needed. Track points on the subject (Pro) [Boris FX] | — |
| Motion blur | Turn on for speed transitions [AEJuice, Pixflow] | have: `trail` (automatic above 1.4×), `whoosh` zoom blur, `whip` smear |
| Freeze frame | Hold a frame (copy-paste a time-remap keyframe) [Pixflow] | have: `velocity` dip to ~0.12 (impact freeze), `stutter` with `freeze` |
| Reverse | Time > Time Reverse Layer [Pixflow] | gap |
| Posterize time (stutter) | **8–12 fps** on glitch moments [Glitchology] | have: `stutter` with `hold` |
| Colour after retiming | Retimed output looks flatter: saturation **+10–15**, contrast **+8–12**, a slight S-curve [AnimeWorld Twixtor] | have: `look` (contrast, saturation, lift, tint) |

## 6. Shakes and camera motion

- **Anime shake (AE):** adjustment layer + Motion Tile (so the edges don't show) + shake +
  lens blur + exposure + time remap. [TikTok tutorial, via search]
- **Wiggle shake:** `posterizeTime(12); wiggle(12, 15)`; horizontal only:
  `posterizeTime(12); w = wiggle(12, 15); [w[0], value[1]]`. [Glitchology]
- **Mild / Chaos shake:** frequency, X and Y amount, from subtle to aggressive. [Filmora]
- **Zoom + rotation + shake transitions.** [YouTube AE tutorial] → rotation is a gap.
- **Motion tile / mirror edges:** lets shakes and zooms move past the frame edge.
  [Adobe, Filmora "Surround Image"] → gap (AMV_CD crops inside the frame instead)

AMV_CD: `in: {shake}` (an impact jolt), `pan`, `zoom`, `ease`, `bass_zoom`, `punch`.
**gap:** continuous shake with posterize-time feel, rotation shake, motion-tile edges.

## 7. Transitions

| Transition | How | AMV_CD |
|---|---|---|
| Hard cut on the beat | default | have |
| Zoom in/out through the cut | scale **~104%** at the cut + an RGB split, screen blend [Make Your Media, via search] | have: `zoom`, `punch` + `rgb` |
| Whip / smear | directional blur on both sides of the cut | have: `whip` |
| Zoom blur (whoosh) | radial blur on the last frames | have: `out: whoosh` |
| Flash | exposure keyframes on an adjustment layer [Filmora] | have: `in: flash` (+ `flash_color`) |
| Dip to black | | have: `in: dip` |
| Dissolve / opacity | | have: `in: dissolve` |
| Lens-blur transition | blur amount + iris scale peaking at the cut [Filmora] | gap |
| Glitch transition | Adjustment layer **6–10 frames** centred on the cut. Displacement peaks at **80–200 px** on the cut frame. RGB offset **0→20→40 px→0**. Posterize time 8–12 fps. Optional 1 frame of invert. Linear or hold keys, not ease. "8 frames at 24 fps is plenty, >12 stops reading as a transition" [Glitchology] | have: `fx` rgb_split/slice/blocks/invert with `shape`. Keep bursts ≤ 10 frames |
| Mask transition | see §3 | gap |
| Eye transition | see §3 | gap |
| Rotation (roto) | rotate with overlays | gap |
| Luma-key fade | threshold keyframed [Filmora] | gap |

## 8. Effects catalogue

**Glitch / digital**
- RGB split: three copies, one channel each, screen blend, offset **5–15 px**. **1–3 px on
  HD feels like a lens; more feels like a glitch.** [Glitchology] → have: `rgb_split` (`px`)
- Chromatic aberration: radial from a focal point, pushed to the edges, keeping faces and
  text aligned. Red/cyan or magenta/green read as a lens. [Glitchology CA] → have: `chroma`
- Displacement glitch: Fractal Noise "Block" (wide), Evolution `time*1000` → Displacement
  Map, horizontal **30–80**, vertical 0. Or Wave Warp "Square". [Glitchology] → have: `slice`
- Block corruption / datamosh: Time Displacement, Echo, Pixel Motion Blur, freeze holds
  [Glitchology] → have: `blocks`, `smear` (fake). gap: a real datamosh (P-frame bleed)
- Glitch intensity in **2–6 frame** spikes. [Glitchology] → have: `shape: flicker/decay`
- Pixelate, posterize, invert. → have
- VHS: low noise, a few px of R/B shift, scanlines (width 2–4 px, multiply/overlay, low
  opacity), a rolling tracking band, slight wave warp. [Glitchology] → have: `scanlines`,
  `grain`, `rgb_split`. gap: tracking band, wobble

**Light / blur / look**
- Glow (Deep Glow, S_Glow). Glows look better in 32-bit. [Adobe; plugins named in search] →
  have: `glow`
- Lens flares (Optical Flares, S_LensFlare) → gap
- Light leaks / "light effect" overlay with opacity keyframes [Filmora] → gap
- Lens / box / square blur as an accent [Filmora] → gap
- Vignette, grain, contrast, saturation, tint, lift → have: `look`, `grain`
- Outline / edge glow → have: `outline`
- Edge detect / depth map over the whole edit → overused, skip [Molob, Styles]
- Letterbox → have: `letterbox`

**Retime looks:** posterize time, stutter, freeze, reverse (see §5).

**3D:** shatter, voxel heart, etc. → have: Blender segments (`amv-blender`).

## 9. Text (typography)
- Words should feel part of the frame, not slapped on top. Hard to do well, but useful.
  [Molob, Styles]
- AMV_CD: `text` with pop, glitch, tracking, flicker, colour and font. **gaps:** text masked
  behind a character, per-letter reveals, text tracked to motion, text that takes the
  shake.

## 10. Sound design (the biggest gap in AMV_CD)

Three kinds [Molob, SFX]:
1. **Action SFX:** what is on screen. Punches, sword clashes, electricity, camera shutter,
   camera beep + flash.
2. **Supporting SFX:** whooshes on fast transitions; a **riser** into a reveal and an
   **impact** as the beat hits; ambience. Stronger whooshes for big moves, subtle ones for
   small ones.
3. **Audio effects:** changing the song itself.
   - **Volume dip right before the drop, back up as the beat hits** (Molob's favourite).
   - **Muffled** (low-pass) so the music sounds distant.
   - Slowing the track, a glitch / stutter on the music.

Workflow: one pass per category, in order: action → supporting → audio effects. Don't jump
back. [Molob, SFX]

Rules with numbers:
- **Sync:** the loudest part of a whoosh lands exactly on the transition (usually the beat);
  a punch sound on the frame the punch lands. **3 frames off is audible.** [Molob, SFX]
- **Riser:** its end on the cut / downbeat. **Impact:** its attack on the downbeat.
  Cut the riser on beat one, leave a beat of space, stack an impact or sub-drop. [MixClap; search]
- **Level:** SFX **3–6 dB under the music**; they support the song and never cover it.
  [MixClap; Molob]
- **Density:** "an effect every 4 seconds is tiring." Every SFX needs a purpose. [MixClap; Molob]
- **Clicks:** a **10–20 ms** fade-out on every SFX. [MixClap]
- Typical lengths: whoosh 0.3–6 s (fast 0.4–0.5 s for rhythmic cuts), riser 2–8 s, impact /
  sub-drop 1–7 s, reverse cymbal ~2 s, downlifter 1–4 s, vinyl stop / tape stop 0.7–6 s,
  glitch ~0.9 s. [MixClap]
- Making them: rising LPF on noise = riser, with a static HPF so the noise doesn't swamp
  the mix. Reverb washes and noise sweeps reset energy. Reverse cymbals. Layer quick + long
  whooshes with peaks synced, then EQ and compress. Pitch up = tension, pitch down =
  release. [Baby Audio; Krotos]
- Free sources: Pixabay (risers, whooshes), MixClap CC0 pack (28 transition SFX), Selekt
  Audio CC0 risers. [search]

AMV_CD status: **gap**. Nothing here adds SFX or edits the song inside an edit. `song_fx`
(slowed, reverb, nightcore, sped up) works only on the whole song. Needed:
- an `sfx` spec list (file, at, gain dB, fade), aligned by peak or attack, plus an SFX library folder in workspace
- automatic whoosh-on-cut / riser-into-drop / impact-on-hit from the beat analysis
- song automation: volume dip before the drop, low-pass muffle, stutter on the music

## 11. Song choice
- Toxic AMV's tracks: phonk, hardtekk, jumpstyle, montagem, dubstep, "slowed" / "sped up"
  versions. High-energy, with clear hits. Molob: phonk/montagem, plus some rap.
- AMV_CD: `song-gen` (ACE-Step). **The planner LM gave weak results here.** The 0.6B LM
  writes audio codes and the DiT renders them as a "cover". With `lm: none` (config.json,
  2026-10-20) it renders from caption + lyrics only, but then it may skip lyric lines.

## 12. What to build next in AMV_CD (from the gaps above, most impact first)
1. **Sound design layer** (§10): SFX placement + music automation (dip, muffle).
2. **Flow link finder** (§3): pair shots whose tail motion matches the next shot's head
   (direction, speed, position), plus `flip` and `reverse` / `pingpong`.
3. **Frame interpolation** for slow motion and velocity (RIFE or similar, its own tool env).
4. **Continuous shake** with posterize-time feel, rotation, motion-tile edges.
5. **Segmentation masks** for mask and eye transitions and text behind characters.
6. Lens-blur transition, light leaks, lens flares.

---

## Sources
- Molob, *How to Make Your Anime Edits Flow PERFECTLY*: https://www.youtube.com/watch?v=YCfDb799jsY
- Molob, *How to Make Your Anime Edits 10x Better with Sound Effects*: https://www.youtube.com/watch?v=GvXMxde91uA
- Molob, *What's the BEST Editing Style for Beginners*: https://www.youtube.com/watch?v=i8YT_V-izZg
- Toxic AMV channel: https://www.youtube.com/@Toxic404Team · Molob channel: https://www.youtube.com/@Molob
- AEJuice, velocity edits: https://aejuice.com/blog/how-to-do-velocity-edits-after-effects/
- Pixflow, speed ramps: https://pixflow.net/blog/how-to-create-smooth-speed-ramps-using-after-effects-time-remapping/
- Boris FX, Twixtor: https://borisfx.com/blog/twixtor-after-effects-how-to-step-by-step-guide/
- AnimeWorld Twixtor guide (values unverified, a seller's site): https://animeworldtwixtor.com/how-to-use-twixtor-in-after-effects-complete-beginner-to-advanced-guide-2026/
- Filmora, AMV polishing: https://filmora.wondershare.com/video-effects/amv-edit-slow-with-filmora.html
- Glitchology, AE glitch: https://glitchology.com/after-effects-glitch/ · chromatic aberration: https://glitchology.com/chromatic-aberration/
- Adobe effect list / stylize effects: https://helpx.adobe.com/after-effects/using/effect-list.html · https://helpx.adobe.com/after-effects/using/stylize-effects.html
- Baby Audio, drops and risers: https://babyaud.io/blog/drops-risers-sfx
- Krotos, whoosh design: https://sound.krotosaudio.com/whoosh-sound-effects/
- MixClap, transition SFX: https://www.mixclap.com/en/blog/transition-sound-effects
- AnimeMusicVideos.org guides and forum (pages refused automated reads; points from search summaries): https://www.animemusicvideos.org/guides/ · https://www.animemusicvideos.org/forum/viewtopic.php?t=133426 · https://www.animemusicvideos.org/forum/viewtopic.php?t=64149
- Pixabay riser/whoosh SFX: https://pixabay.com/sound-effects/search/riser%20whoosh/
