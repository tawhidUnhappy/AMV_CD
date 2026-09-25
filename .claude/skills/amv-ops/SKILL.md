---
name: amv-ops
description: Fast start for working in AMV_CD - how to run anything (./amv.sh), the code map, the check-your-work tools (regress, compare, strip), and the traps that cost time before. Load first for any AMV_CD task; the stage skills (amv-lyric-video and friends) hold the deep knowledge per stage.
---

# AMV_CD fast start

Repo: github.com/tawhidUnhappy/AMV_CD. Push straight to `main` after changes
(the user's standing habit). Source media and outputs are never committed:
`config.json` (media paths) and `tmp/` (everything generated) are gitignored.

## Running things: `./amv.sh`

```bash
./amv.sh list                        # every command, what it does, whether it needs the GPU env
./amv.sh <command> --help
```

- It runs in a small cached environment built from `requirements-light.txt`
  (numpy/librosa/pillow/scipy) with `PYTHONPATH` set, from any cwd.
  **The project `.venv` is broken** (its `bin/` is empty since 2026-09) and a
  full `uv sync` pulls torch/CUDA, so don't reach for `uv run` in the project
  env. Only `vocals`, `transcribe` and `subs` need torch; they say so and run
  with `AMV_FULL=1 ./amv.sh ...` after the user has chosen to `uv sync`.
- `python -m amv.x.y` still works for any module; `amv/__main__.py:COMMANDS`
  is the one table of names.

## Code map

`amv/core/` config (config.json -> Config), **paths (every tmp/ path +
load_slots/load_scene_index; never join ROOT/"tmp" yourself)**, ffmpeg_tools
(run, encoders, concat, subtitles_filter), regress.
`amv/audio/` isolate_vocals, transcribe_song, beats, lyrics (the lyric plan).
`amv/subs/` extract_subs (+ pgs/pgs_ocr for bitmap tracks) -> tmp/subs/scene_index.json.
`amv/render/` timeline (slots), select_clips/ (candidates, scoring, themes = BLACKLIST, cli: score_all/pick/order_breaks), grade, pipeline (render), lyric_overlay/.
`amv/vision/` **decode (decode_tiny: the one way to read footage small)**, contact_sheet (grab_all/tile), strip, compare, skin, checks.
`amv/intro/` plan+select+render (`intro`: new intro from a song), reference (`reference`: which episode frame is behind each frame of a video), remake (`remake`: plan/spec renderer), `remakes/*.json` (committed specs).

## Checking your work - use these, don't hand-roll them

- **Refactor?** `./amv.sh regress snapshot` BEFORE the first edit, `./amv.sh
  regress check` after (`--quick` skips the 3-5 min select). It diffs the
  timeline, a fresh EDL (slots), lyrics.ass and every remake plan. On
  2026-09-24 this was done by hand with a git worktree; it proved the
  paths/decode/select refactor byte-identical.
- **Any picked footage?** `./amv.sh strip --edl ...` - start/middle/end of
  every slot. One mid-frame per shot (contact sheet) missed credit text fading
  in at a shot's start and a pan onto a child's legs; the strip caught both.
- **Two videos?** `./amv.sh compare A B [--watermark tr] [--frames 200-215]
  [--video]` - per-frame likeness, weak frames listed, labelled A-over-B sheet.

## Multi-show (channel) intros: library -> gallery -> picks

The anime library is `/mnt/datadisk/anime/<Show>/` (one folder per show,
episode number read from the file name - see `library.EPISODE_PATTERNS`).
`./amv.sh intro --library /mnt/datadisk/anime ...` needs no subtitles: each
episode is decoded once to an 8 fps index (tmp/intro/library/, ~45 min for
70 episodes), and footage that repeats across a show's episodes (OP, ED,
eyecatches, title cards, recaps) is excluded. Scores alone picked dull shots
(a door, a crowd pan) twice, even with spectacle terms - so the real flow is
`--gallery` (12 sheets, start/mid/end per candidate), look, write
`amv/intro/picks/NAME.json` (ids, optional `{"id", "shift"}`), then
`--picks`. Per-show rejects go in `amv/intro/blacklist.json`.
The delivered channel intro (no name on screen, 11 s) is
`amv/intro/picks/channel_intro.json`; copies live in /mnt/datadisk/channel_intro/
(1080p, plus a 4K/24 fps/44.1 kHz copy that joins onto remanga recaps by stream copy).

**Montage (v2, the current channel intro):** the gallery/picks intro felt
flat - hard cuts only, a still shot, one cut per two beats. v2 is a shot list
(`amv/intro/montages/channel_intro.json`, `./amv.sh montage SPEC`) rendered
frame by frame through remake.render: dissolves in the swell, a push-in on
every shot, a whoosh into the drop, a cut on EVERY beat after it, white flash
on the drop, zoom punch + RGB split on the two strongest accents. Beat times
come from `amv.intro.plan` (librosa onsets). Short beat-length shots were
found inside gallery windows by probing every 0.05 s offset for the most
motion with no cut; override by eye when the striking moment is elsewhere.

**Mood intros (evil/sad, `amv/intro/montages/evil_intro.json`):** the
picture can't find a mood, the dialogue can. `./amv.sh dialogue ROOT --find
REGEX [--series S]` searches every show's English text subtitles (cached in
tmp/intro/dialogue/; Mushoku falls back to the OCR'd scene index). Broad words
("why", "die") drown in hits - search specific phrases, then sample the
matching stretch every 3 s (`ffmpeg -vf fps=1/3,...,tile`) and pick by eye.
Re:Zero DC ep08 2140-2690 s is Petelgeuse + Subaru's breakdown. The song is
Unravel (remanga/global/bgm) from 20 s (`song_start`) - NOT royalty-free,
the user was told; the other tracks in /mnt/datadisk/background_music are.
Look for dark footage: `lift` before contrast, `saturation` < 1, a `tint`.

**Flow intro (`amv/intro/montages/flow_intro.json`, from /mnt/datadisk/ReferanceEdit):**
the reference edits (Voidwalker, a JJK edit) cut at a median 0.17-0.29 s with
bursts, and flow comes from movement carried across cuts. `./amv.sh flow
POOL.json` measures each shot's global motion at head and tail (phase
correlation) - most anime shots read "still" (held frames, subject-only
motion), so flow is mostly MADE: `pan` continuing the neighbour's direction,
`out: whip {dir}` smearing/sliding both sides of a cut the same way,
`in: shake` on impacts, `speed` < 1 for slow-mo finales. Cuts sit on the
song's own accents (librosa onsets > ~6). Check the render for clips that
burn to white or fade to black inside a slot (both happened) and move "at".

**AMV flow rules (researched 2026-09-25, applied in `montages/subaru_intro.json`):**
1. Eye trace - keep the focal point (usually a face) where it was across a cut;
   `align: true` + `focus_head/tail` from `./amv.sh flow` does it automatically.
2. Motion continuity - carry direction across the cut; cut DURING motion, not at
   rest; whip along the outgoing shot's measured tail motion.
3. Impact frame on the beat - every cut on a beat/onset, hits on the strongest.
4. Velocity ramps - ~200% into the beat, ~20-60% after, eased (`velocity`
   keyframes); motion blur on the fast frames (`trail`, automatic above 1.4x).
5. Impact freeze - 10-15% speed for 3-5 frames on the big hits, then out.
6. Scale pulse - ~1.05 -> 1.2 zoom between beats, eased.
7. Shake on bass/impacts; flashes and whips reset the eye between unrelated shots.
Traps met: 0.8 s scan windows slowed to fill 1.3 s slots expose fades to black
inside the source - print per-frame luma of the window before committing it;
night scenes at luma < 0.1 read as gaps, replace rather than lift.

## Remaking an intro someone else cut

`./amv.sh reference VIDEO --seconds N` -> tmp/intro/reference_map.json, then
write a spec in `amv/intro/remakes/` (copy mushoku_ep1_recap.json: `require`
pins the map frames it assumes, `overrides` fill effect frames via
`like`/`anchor`+`step`, plus grade/caption/audio delay) and
`./amv.sh remake --spec ... --song ...`. Find the audio offset by
cross-correlating the reference audio with the song (scipy.signal.correlate);
it was 0.242s. Frames with no close match are effects: view them frame by
frame (`ffmpeg -vf select=between(n,a,b),tile`), then rebuild.

## Traps that cost time before

- **`pkill -f <pattern>` matches your own shell** when the pattern is in the
  same command line - it killed the job it was meant to precede. Kill by PID.
- **`rm` on `$VAR/...` is blocked** by a safety check; write `"${S:?}"/...`
  or skip the cleanup (ffmpeg `-y` overwrites anyway).
- **Frame-exact decoding**: no fps filter => `-fps_mode passthrough`
  (decode_tiny does it), same decoder and seek in matcher and renderer, seek
  (n-0.5)/fps for frame n. See amv-clip-selection "Frame-exact work".
- **Never mux a looped still image and audio in one graph.** The intro's
  focus mask (`-loop 1` image, 25 fps by default) set the picture's timing,
  frames were dropped, and the audio got non-monotonic timestamps: 7-8 s of
  sound under 11 s of picture, different every run. render.py now makes the
  picture and the sound separately, joins them by stream copy, and refuses a
  file whose sound is short. When checking any render, check the AUDIO
  duration too (`ffprobe -show_entries stream=codec_type,duration`).
- **Long GPU decodes** (motion map / reference index over 24 episodes) take
  ~8-10 min the first time; run them in the background and let them cache
  under tmp/intro/.
- **OP/ED**: this release subtitles the OP lyrics, so the gap detector misses
  it; `scoring.song_zones` catches it. The full AMV does not use it yet (the
  user has not decided).
- Content: Mushoku Tensei has fanservice involving child characters. Every
  pick gets looked at (strip); rejects go in `themes.BLACKLIST` with a reason.

## Maintenance

When a session hits a non-obvious bug or trap here, add a terse
symptom -> cause -> rule line above before ending the turn, and delete what
a code change made stale.
