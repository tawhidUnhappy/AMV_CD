---
name: amv-lyric-channel
description: Make a lyrics-channel video end to end, like workspace/output/lyric_videos/goddamn_devil/goddamn_devil.mp4 - ask the user whether they bring a song or want one generated (ACE-Step), get the lyrics, pick or generate a sky background, then time, render, check and package it (thumbnail, title, description, tags) with ./amv.sh lyric-video. Use when the user asks for a lyric video, a "lyrics" upload, a 7clouds / Vibe Guide style video, or "make a song video like goddamn devil".
---

# Lyrics-channel video, start to finish (amv-lyric-channel)

The finished example is `workspace/output/lyric_videos/goddamn_devil/` (spec
`workspace/global/lyric_videos/goddamn_devil.json`). Every new video copies that
spec's shape. Load `amv-ops` (section "Lyric videos") and `amv-preferences` first;
for a generated song also `amv-song-gen`.

What the pipeline already does (don't rebuild it): a still sky background, every
lyric line timed to the singing (separated voices + transcript + alignment, a
second pass on unheard gaps), the traced "Vibe Hand" font with a dark rim and soft
shadow, each letter wiggling on its own, sparkles, a subtle flash on hits, a title
card, a subscribe card for voidHalfDemon, rendered by HyperFrames at 2560x1440.

## 1. Intake - one round of questions

Ask everything that changes the video in ONE AskUserQuestion call (up to 4
questions), with a recommended default first. Don't ask what the files already say.

1. **Song** - "Which song?" options:
   - "My own file" (they give a path; any mp3/wav/flac)
   - "Generate a new one (ACE-Step)" (go to step 2)
   - "One from /mnt/datadisk/song" (list a few; the copyright_risk_short_clip_only
     folder is NOT for full uploads - say so)
2. **Lyrics** - "Where do the lyrics come from?"
   - "In the song file's tags" (Suno writes them; check with `timing.song_lyrics`)
   - "I'll paste them" (pasted lyrics always win over the tag - preference)
   - "Write them for me" (only with a generated song; you write them, show them first)
3. **Background** - "Which background?"
   - "Generate skies for me (Recommended)" - `bg-gen`, then they pick from a sheet
   - "My own image" (a path)
   - "Same as the last video"
4. **Title / artist** - only if the file name and tags don't tell (Suno tags hold
   `title`; the artist on this channel is "voidHalfDemon" unless they say otherwise).

Then ask in plain text only for what is still missing (a path, a mood or style
for a generated song, their pasted lyrics).

## 1b. A YouTube link as the brief ("make a song like this")

The user may paste any YouTube link. Make an ORIGINAL song in that style - never
copy its lyrics or name a real singer's voice in the caption.
1. What it is: `yt-dlp --skip-download --dump-json URL` (title, channel, tags,
   description). YouTube often answers "Sign in to confirm you're not a bot" -
   then `curl "https://www.youtube.com/oembed?url=URL&format=json"` still gives
   the title and channel without signing in.
2. Research it (WebSearch, cite the pages): the artist, genre, era, tempo, mood,
   vocal type, typical themes - and the EDIT style in the title: "Nightcore"
   (x1.25 speed+pitch), "slowed + reverb", "sped up". The edit becomes spec
   `song_fx` (nightcore / slowed_reverb / slowed / sped_up), applied after
   generation - that is how those uploads are made.
3. Write the caption from the research (genre, mood, instruments, vocal, tempo
   before the edit) and your own lyrics in the same register and themes (keep
   self-harm out even when the genre goes there). Title in the scene's casing
   (emo / SoundCloud titles are lower case).
4. Tell the user in one short block what you found and what you will make.
Example: "Nightcore - cuttin on me [lil happy lil sad]" -> Swedish SoundCloud
emo rap, sad synths + trap -> "left on read (nightcore)": 130 BPM emo trap,
male vocal, nightcore after (2026-10-22).

## 2. A generated song (ACE-Step)

Follow `amv-song-gen`: ACE-Step 1.5, `lm: "none"`, `acestep-v15-xl-sft` (the
owner's settings), at ACE-Step's best-quality knobs minus DCW (defaults since
2026-10-22: 64 steps, ADG, guidance 8, shift 3). A/B on a 45 s excerpt, seed 7, lines
sung of 10: old defaults 10, shift 3 9, ADG 10, DCW 0, all minus DCW 10 - DCW turns
the vocals to mush; never switch it on. Lower-case lyrics sing fine. Write a caption (genre, mood, tempo, vocals) and lyrics with
section tags ([Verse], [Chorus], ...). Show both in one short block, generate a
few takes, and keep the take whose transcript has every lyric line. Songs land in
`workspace/output/songs/<name>/`; the lyrics you wrote are the lyrics file.

## 2b. Style follows the song

The house look is the default, not a rule: pick the font, case and colours for
the song's theme (owner, 2026-10-22). Fonts (assets/fonts/theme, OFL/Apache):

| Theme | Fonts | Case / extras |
| --- | --- | --- |
| lyrics-channel pop (default) | Vibe Hand (workspace/assets/fonts) | upper |
| emo, sad rap, nightcore, diary | ShadowsIntoLight, NanumPenScript, PermanentMarker | lower; soft pink/red glow |
| dreamy, romantic, soft pop | Pacifico, Satisfy | as_written |
| dark, aggressive, villain | BebasNeue, SedgwickAveDisplay, Creepster (horror only) | upper |
| synthwave, retro, EDM | Audiowide, Monoton (titles) | upper; cyan/magenta glow |
| lo-fi, acoustic, storytelling | SpecialElite, Kalam-Bold | as_written |

Spec `"style": {"case": "lower", "fill": "#ffffff", "rim": "...", "shadow": "...",
"glow": "rgba(255,90,150,0.35)"}`. Render a quick sheet of 3-4 candidate fonts
with the hook line over the chosen background (look.lyric_sprite) and pick the
most legible one that fits.

## 3. The spec

Copy `workspace/global/lyric_videos/goddamn_devil.json` to
`workspace/global/lyric_videos/<name>.json` and change only:
`song`, `title`, `artist`, `lyrics_file` (save pasted/written lyrics as
`<name>.lyrics.txt` beside the spec, sections in [brackets]), `background`, and
`meta` (plain layout + keywords), `font` / `style` (2b), `song_fx` for an edit.
Keep `channel`, `size`, `fps`, `engine: hyperframes`, `flash` 0.1, `wiggle` 3.5.
The song is mastered to -14 LUFS for the upload automatically (spec `master`).

## 4. Timing - check before anything renders

```bash
./amv.sh lyric-video workspace/global/lyric_videos/<name>.json --lines
```
The first run separates the voices of the whole song (ensemble: ~30 min for 4 min
of audio on the 3060) - run it in the background and watch the log with Monitor;
later runs reuse the cache (`workspace/tmp/lyric_video/<name>/words.json`).
Read the output:
- "left out" must be only stage directions ("(Beat cuts out)") and unheard ad-libs.
  A real sung line left out: look at the stem around it before touching anything.
- `[filled]` lines were not heard even alone and are spread over the sung gap -
  check one with `--frames` at its time.
- Times come from FORCED ALIGNMENT of the known words (forced_align tool, torchaudio
  MMS_FA) inside whisper's window: whisper's own stamps on sung vocals were 1-2 s
  late on some lines and early on others ("lyrics appear 1-2 s late", 2026-10-22).
  `lines.json` keeps `whisper_start` and `fa_score` per line. A doubt about one line:
  plot the voices stem's spectrogram round it with both starts marked and look
  where the note begins - don't argue from numbers.
- Lines still early/late: fix timing.py for every song, never hand-time one
  song (preference).

## 5. Background

Generated: match the song's mood, make a handful, let the user choose.
```bash
./amv.sh bg-gen --count 8 --seed <n> --sheet            # curated mix
./amv.sh bg-gen --scene clouds --mood cotton_candy --count 4 --sheet
```
Mood guide: dark / aggressive / villain -> night, aurora, fire_sunset, blue_hour;
romantic / soft -> cotton_candy, dusk, dawn, mint; happy / summer -> day_blue,
golden_hour (clouds, cumulus, sea); melancholic -> blue_hour, dusk ranges.
Show `workspace/output/backgrounds/sheet.jpg` (Read it, then ask which number);
the file names are `<scene>_<mood>_<seed>.png`. White text must stay readable: avoid
a bright cumulus or sun glitter right behind the centre line.

## 6. Look before rendering

```bash
./amv.sh lyric-video SPEC --frames 0.5,16.7,19.6,<a chorus second>,<a filled line>
```
Read `workspace/tmp/lyric_video/<name>/frames/contact-sheet.jpg`: title card, the
card mid-click and with the bell on, a chorus line, wrapping of the longest line,
any character the font lacks (it shows as a gap - add it to the font, see amv-ops).

## 7. Render and verify

```bash
./amv.sh lyric-video SPEC        # ~8 min for 4:20 (HyperFrames, 1440p30) - background + Monitor
```
Then, before saying it is done:
- `ffprobe`: video + audio only, both as long as the song.
- a review sheet at TRUE times: `-vf "select='lt(mod(t\,6)\,0.034)',scale=384:-1,drawtext=...,tile=8x6" -fps_mode vfr`
  (`fps=1/N` samples mid-interval and mislabels times by seconds).
- if anything about motion changed: track one line's letters frame to frame
  (each should drift ±3-6 px @1080, independently).

## 8. Package

`--meta` (also written by the full render) makes `<name>_title.txt`,
`<name>_description.txt`, `<name>_tags.txt`. Default to spec
`"meta": {"layout": "plain", "keywords": [...]}` - the description is only the
sectioned lyrics, hashtags, tags and related keywords, no links or channel lines
(owner, 2026-10-22). Write 10-15 keywords for the genre/mood/use ("night drive
music", "dreamy synth pop"). The full Vibe Guide layout (links, follow blocks)
is there only when asked; its missing links stay `<...>`, never guessed. The
thumbnail is `<name>_thumbnail.jpg` (title + artist over the background).

## Example run (left on read (nightcore), 2026-10-22) - a YouTube link as the brief

Link -> oEmbed (yt-dlp was bot-blocked) -> "Nightcore - cuttin on me [lil happy lil sad]"
-> research -> original emo-rap lyrics, 130 BPM, male vocal; 2 takes (10 min), 23/23 lines
sung in one; spec song_fx nightcore (170 s -> 136 s), ShadowsIntoLight lower case, soft
pink glow, clouds_blue_hour bg; timing 15 min (all 23 lines force-aligned, the lowest
scores checked on spectrograms); render 4:30; -14.0 LUFS. Traps: a lower-case title's
descenders ran into the artist line (fixed in code); tags kept "(nightcore)" brackets
(tags now use the base title + "<base> nightcore").

## Example run (Neon Lullaby, 2026-10-22)

ACE-Step, 24 lines in 160 s at 112 BPM, 2 takes in 7 min; the take with 23/24 lines
heard in the mix was used and all 24 got timed (the last one by the gap pass);
timing ~20 min (separation), stills 20 s, render 4:49 for 2:40 at 1440p.
Spec `workspace/global/lyric_videos/neon_lullaby.json` - copy it for the next one.

Deliver: the four paths, the left-out lines and why, anything that needs the
user (placeholders, a font gap). Code changes: commit + push (preference).
