---
name: amv-ops
description: Fast start for working in AMV_CD - how to run anything (./amv.sh), the code map, the check-your-work tools (regress, compare, strip), and the traps that cost time before. Load first for any AMV_CD task; the stage skills (amv-lyric-video and friends) hold the deep knowledge per stage.
---

# AMV_CD fast start

The repo is code only. Source media, outputs and every user choice are never
committed: `config.json`, `workspace/projects/`, `workspace/global/`, `output/` and `workspace/tmp/` are
gitignored. The owner's preferences, machine layout and per-show notes are in
the amv-preferences skill - load it with this one; it wins where they differ.

## Running things: `./amv.sh`

```bash
./amv.sh list                        # every command, what it does, whether it needs the GPU env
./amv.sh <command> --help
```

- It runs in a small cached environment built from `requirements-light.txt`
  (numpy/librosa/pillow/scipy) with `PYTHONPATH` set, from any cwd.
  A full `uv sync` pulls torch/CUDA, so don't reach for `uv run` in the
  project env. Only `vocals`, `transcribe` and `subs` need torch; they say so
  and run with `AMV_FULL=1 ./amv.sh ...` after `uv sync`.
- `python -m amv.x.y` still works for any module; commands are `command`
  plug-ins (`amv/plugins/commands/`).

## Where things live (remanga-style)

The repo is code only. Everything a user makes is in ONE gitignored folder,
`workspace/` (config "workspace_dir"), plus `config.json` at the root:
- `config.json` - machine paths (`library_dir`: one folder per show), the
  active `project`, plug-in choice + settings (`separators`/`transcribers`),
  optional `shorts_dir`. Template: `config.example.json`.
- `workspace/projects/<name>/project.json` - one lyric AMV (`amv.core.project`):
  song, source, lyric plan, `section_episodes`, `pacing`, `themes`,
  `blacklist`, `thumbnails`; its song file can sit beside it.
- `workspace/global/` - shared: `shorts/specs/`, `shorts/catalog/` (shots,
  songs, Shorts built), `intro/{picks,montages,remakes,blacklist.json}`.
- `workspace/output/shorts/` - delivered Shorts.
- `workspace/tmp/` - every generated file and cache (`amv.core.paths`).
- `examples/` (tracked) - `project.example.json`, `short.example.json`.

**Plug-ins** (`amv/plugins/`, copied from remanga's design): `_registry.py`,
`_loader.py`, `_kinds.py`; built-ins are folders (`commands`, `demucs`,
`faster_whisper`, `song_fx`, `video_fx`); drop-ins in top-level `plugins/`
(see its README); entry-point group `amv.plugins`. Kinds: command, tool,
separator, transcriber, song_fx, video_fx. `./amv.sh plugins` lists them.
A `tool` runs its worker via `amv.core.tools.run` (offline first).
Never hard-code a show, song or `/mnt/...` path in code - it goes in the
project, global/ or config.json.

## Code map

`amv/core/` config (config.json -> Config), **paths (every workspace/tmp/ path +
load_slots/load_scene_index; never join ROOT/"tmp" yourself)**, ffmpeg_tools
(run, encoders, concat, subtitles_filter), regress.
`amv/audio/` isolate_vocals, transcribe_song, beats, lyrics (the lyric plan).
`amv/subs/` extract_subs (+ pgs/pgs_ocr for bitmap tracks) -> workspace/tmp/subs/scene_index.json.
`amv/render/` timeline (slots), select_clips/ (candidates, scoring, themes = the project's themes/blacklist, cli: score_all/pick/order_breaks), grade, pipeline (render), lyric_overlay/.
`amv/vision/` **decode (decode_tiny: the one way to read footage small)**, contact_sheet (grab_all/tile), strip, compare, skin, checks.
`amv/shorts/` song (drop/window), find (candidate shots + crop), build (spec -> Short), catalog (global/ knowledge + tmp cache), dub, fx, deliver.
`amv/intro/` plan+select+render (`intro`: new intro from a song), reference (`reference`: which episode frame is behind each frame of a video), remake (`remake`: plan/spec renderer; specs in workspace/global/intro/remakes/).
`amv/plugins/` registry + built-ins; `amv/core/project.py` the active project; `amv/core/tools.py` isolated tool envs.

## Checking your work - use these, don't hand-roll them

- **Refactor?** `./amv.sh regress snapshot` BEFORE the first edit, `./amv.sh
  regress check` after (`--quick` skips the 3-5 min select). It diffs the
  timeline, a fresh EDL (slots), lyrics.ass and every remake plan.
- **Any picked footage?** `./amv.sh strip --edl ...` - start/middle/end of
  every slot. One mid-frame per shot (contact sheet) missed credit text fading
  in at a shot's start and a pan onto a child's legs; the strip caught both.
- **Two videos?** `./amv.sh compare A B [--watermark tr] [--frames 200-215]
  [--video]` - per-frame likeness, weak frames listed, labelled A-over-B sheet.

## Multi-show (channel) intros: library -> gallery -> picks

The anime library is config.json `library_dir`: one folder per show,
episode number read from the file name (`library.EPISODE_PATTERNS`).
`./amv.sh intro --library LIBRARY ...` needs no subtitles: each
episode is decoded once to an 8 fps index (workspace/tmp/intro/library/, ~45 min for
70 episodes), and footage that repeats across a show's episodes (OP, ED,
eyecatches, title cards, recaps) is excluded. Scores alone picked dull shots
(a door, a crowd pan) twice, even with spectacle terms - so the real flow is
`--gallery` (12 sheets, start/mid/end per candidate), look, write
`workspace/global/intro/picks/NAME.json` (ids, optional `{"id", "shift"}`), then
`--picks`. Per-show rejects go in `workspace/global/intro/blacklist.json`.

**Montage:** a gallery/picks intro feels flat - hard cuts only, a still shot,
one cut per two beats. A montage is a shot list (`workspace/global/intro/montages/NAME.json`,
`./amv.sh montage SPEC`; its "mood" key feeds the Shorts catalog) rendered
frame by frame through remake.render: dissolves in the swell, a push-in on
every shot, a whoosh into the drop, a cut on EVERY beat after it, white flash
on the drop, zoom punch + RGB split on the two strongest accents. Beat times
come from `amv.intro.plan` (librosa onsets). Short beat-length shots were
found inside gallery windows by probing every 0.05 s offset for the most
motion with no cut; override by eye when the striking moment is elsewhere.

**Mood intros (evil/sad):** the
picture can't find a mood, the dialogue can. `./amv.sh dialogue ROOT --find
REGEX [--series S]` searches every show's English text subtitles (cached in
workspace/tmp/intro/dialogue/; a show with only bitmap subs falls back to the OCR'd scene index). Broad words
("why", "die") drown in hits - search specific phrases, then sample the
matching stretch every 3 s (`ffmpeg -vf fps=1/3,...,tile`) and pick by eye.
Say so when a chosen song is not royalty-free. Look for dark footage: `lift` before contrast, `saturation` < 1, a `tint`.

**Flow intros (from reference edits):** fast fan edits cut at a median 0.17-0.29 s with
bursts, and flow comes from movement carried across cuts. `./amv.sh flow
POOL.json` measures each shot's global motion at head and tail (phase
correlation) - most anime shots read "still" (held frames, subject-only
motion), so flow is mostly MADE: `pan` continuing the neighbour's direction,
`out: whip {dir}` smearing/sliding both sides of a cut the same way,
`in: shake` on impacts, `speed` < 1 for slow-mo finales. Cuts sit on the
song's own accents (librosa onsets > ~6). Check the render for clips that
burn to white or fade to black inside a slot (both happened) and move "at".

**AMV flow rules:**
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

## YouTube Shorts (vertical, one show, one track) - `amv/shorts/`

**Start here: `./amv.sh short-catalog`** - what earlier sessions already know
(songs + drops, vetted/rejected shots per show with why/mood/crop, Shorts built).
`short-catalog SHOW --mood dark [--sheet]` lists/draws the good shots to reuse.

```bash
./amv.sh short-song SONG                         # drops (bass rise), window, hit grid, accents
./amv.sh short-find SHOW --find REGEX [--motion N] [--episodes 11-12] --tag T
#   -> workspace/tmp/shorts/pool/SHOW-T-NN.jpg: start/mid/end per shot, 9:16 crop drawn; LOOK at them
./amv.sh short workspace/global/shorts/specs/NAME.json        # plan+render 1080x1920, review.jpg, title/description
#   -> workspace/tmp/shorts/NAME/ and delivered to <shorts_dir>/SNNN_NAME/ (short.mp4, title.txt, description.txt)
```

Layout (default): the WHOLE 16:9 picture centred on a
blurred, dimmed copy of itself (`build.LAYOUT`, renderer `remake.blur_fill`),
not a full-screen 9:16 crop. Spec `"frame": "crop"` gives the old crop;
`"layout": {"frame_aspect": 1.333}` a bigger, narrower centre picture. The crop
traps below only matter for "crop" or zoomed-in punches.

**Story Shorts:** scenes
played as-is with the ENGLISH dub + burned captions, then the beat-cut montage
from the drop, then an outro line. Spec keys `story`, `outro`, `hook_text`,
`thumbnail`, `"seconds": "auto"` (build.py docstring). Workflow per Short:
1. `./amv.sh dialogue ROOT --series S --find REGEX` -> the lines that tell the
   story (episode 1 usually holds the premise); print the stretch around them
   to get from/to.
2. `short-find SHOW --episodes a-b --find ... --motion N` -> montage shot ids;
   read the sheets; FOCUSED regexes (a show's own name word can match 700+ shots).
3. `short SPEC` - read the printed `dub:` line per scene. The dub is a
   different script from the subtitles (whisper large-v3 transcribes it,
   cached): when a scene starts/ends mid-sentence, read the words in
   workspace/tmp/shorts/cache/dub.json and pin the scene with `"exact": true`.
4. `short-thumb SPEC --candidates EP:T:X,...` -> bare frames with a 0.1 grid;
   choose, then write labels (`at`/`to` read off the grid) or `panels` (a
   two-frame comparison: SAME GIRL?!, BEFORE / AFTER) and render.
Delivery: `<shorts_dir>/SNNN_name/` (config.json) with every file prefixed by the
number (never reused; kept in catalog/shorts.json), INDEX.md, by_anime/.
`./amv.sh short-index` rebuilds them. Titles <= 100 chars incl. " #shorts".
Optional effects (`song_fx` / `video_fx` plug-ins, all optional):
`"song_fx": "slowed_reverb"|"slowed"|"nightcore"|"sped_up"` renders the song once
to workspace/tmp/shorts/cache/fx/ and THAT file is analysed (drops/beats move with the
speed: find drops on the processed song, not the original); dialogue untouched;
the description says "(Slowed + Reverb edit)". `"video_fx": ["outline", "glow",
"grain"]` (or {"outline": {"color": [r,g,b], "strength", "width"}}) is applied on
the montage only (story scenes plain) unless `"video_fx_scope": "all"`; ~0.1 s
per frame with all three. The first outline was invisible: blurring a thin
edge mask dilutes it - it is boosted after the blur, and the image border is
masked out (it read as an edge).
Language: a scene uses the English dub when the episode has one; with none
(a Japanese-only release) it keeps the original voices and the
English SUBTITLES are the captions and the clock (scene widened to whole lines).
A spec without `story`/`outro` is a music-only montage.
Voices only (default): story/outro clips go through Demucs
htdemucs_ft (the `separator` plug-in, `amv/plugins/demucs/`, own uv env: torch +
demucs on Python 3.12 - demucs' `lameenc` has no cp311/cp312 wheel in an
offline cache, the first build needs the network, ~3 min) and only the vocals
stem is mixed; stems cached in workspace/tmp/shorts/cache/vocals/. Measured: speech
-0.5 dB, the episode's music in a pause -12.5 dB. `"dialogue_only": false`
in a spec keeps the full mix.
The thumbnail is a separate file (YouTube ignores MP4 cover art and picks a
frame); deliver copies the render untouched.

A spec lists shot ids ("EP-SECONDS") for build / drop / after-drop; slots,
sub-windows, speed, crop, whips, punches on accents, look per mood are derived
(build.py docstring). Per-shot facts go in the spec (`x`, `at`, `why`) and are
recorded in the catalog on every build. Always read `workspace/tmp/shorts/NAME/review.jpg`
(a frame every 0.5 s) before delivering.
A story longer than the song's run-up to its drop is refused (the window
would clamp at 0 s and the slots run backwards): pick a later drop.

Traps (all fixed in code; keep the rules):
- A centroid focus lands BETWEEN two eyes/characters (a nose, sky) - fatal in a
  9:16 crop. `find.crop_x` takes the crop-wide band with most edges+colour.
- `crop_x` misreads near-black frames; a vetted `x` (spec override, or an intro's
  measured `focus_head`) in the catalog wins over it.
- Dark scenes: the 8 fps index misses cuts, one "shot" can be 40-60 s, and the
  busiest stretch of it is another scene. The id's time is the moment - start
  there; search only the first ~2 s. Catalog keys are moments, not index shots.
- Extreme close-ups (eye macros, teeth) that work in 16:9 are texture at 9:16 -
  `short-catalog SHOW --not-vertical ID --reason ...`; short-find then skips them.
- A shot slowed to fill the end slot runs into the next real shot: pin `x`
  to keep the subject, or pick a longer shot.
- "It doesn't follow" = the biggest hits fall mid-shot: the 2-beat cut grid is
  counted from the drop, and a weak drop (12.8 dB rise vs 39) put it a beat out of phase.
  Rule: check the strongest accents land ON cuts (compare montage.json cuts with
  `short-song` accents); pick the grid phase that hits them. And match footage
  energy to the SONG, not the show - talking heads under a jumpstyle track drag.
- Episode audio as inputs dragged the mkv CHAPTERS into the mp4 as a text
  track: render maps `-map_chapters -1`. Check new
  renders with ffprobe: only video + audio.
- Whisper on a finished Short "heard" a story line twice over the music right
  after the story (context hallucination). Verify a suspect line by
  transcribing that stretch alone, and the song alone at the same time.
- OCR'd bitmap subtitles have typos and no punctuation: search them
  loosely, trust the dub transcript for captions.
- `[S01 E06] Title` episode names were read as episode 1 (the "S01") -
  library.EPISODE_PATTERNS now tries `S\d+ E(\d+)` first. New show folders go
  in the library as `<Show_Name>/` (one per show).
- Separated voices vary 10 LU clip to clip and sat 4-10 LU under the montage,
  and a quick FX'd shout sat ~8 dB under the speech around it (heard as
  "missing"): dialogue clips run through loudnorm (`DIALOGUE_LUFS` -14,
  `DIALOGUE_LRA` 5; spec "dialogue_lufs"). Demucs itself kept the shout (-2 dB).
- The end fade (0.6 s) ate an outro's last word when the Short ended on it:
  `OUTRO_TAIL` holds music after the outro.
- An explosion under a shouted line made whisper caption "Wyvern great
  googly" for "Wyvern Slash": captions are transcribed from the separated
  voices (dub cache keys end "|voices").
- "seconds": "auto" sized the drive from a perfect beat grid; real hits drift
  later, so it came up one hit short ("14 shots need 28 hits, has 27"). It is
  read off the song's actual hits for the latest cut phase now.
- The song at full gain put the montage at ~-8 LUFS vs dialogue at -14 (YouTube
  normalises to -14 and would pull the voices down): `MUSIC_FULL` 0.55.
- Song credits come from the file name "Title - Artist"; no " - " means an
  explicit `<ARTIST ...>` placeholder in description.txt, never a guess.

## Remaking an intro someone else cut

`./amv.sh reference VIDEO --seconds N` -> workspace/tmp/intro/reference_map.json, then
write a spec in `workspace/global/intro/remakes/` (`require`
pins the map frames it assumes, `overrides` fill effect frames via
`like`/`anchor`+`step`, plus grade/caption/audio delay) and
`./amv.sh remake --spec ... --song ...`. Find the audio offset by
cross-correlating the reference audio with the song (scipy.signal.correlate).
Frames with no close match are effects: view them frame by
frame (`ffmpeg -vf select=between(n,a,b),tile`), then rebuild.

## Traps that cost time before

- **`./amv.sh` dies with "Failed to fetch https://pypi.org/simple/..."** when
  PyPI is slow: `uv run --with-requirements` re-resolves every run. The light
  env is cached, so `UV_OFFLINE=1 ./amv.sh ...` works. Tool plug-ins
  already try offline first.

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
  under workspace/tmp/intro/.
- **OP/ED**: a release that subtitles the OP lyrics defeats the gap
  detector; `scoring.song_zones` catches it (opt-in).
- Content: some shows have fanservice involving child characters. Every
  pick gets looked at (strip); rejects go in the project's `blacklist` with a reason.

## Maintenance

When a session hits a non-obvious bug or trap here, add a terse
symptom -> cause -> rule line above before ending the turn, and delete what
a code change made stale.
