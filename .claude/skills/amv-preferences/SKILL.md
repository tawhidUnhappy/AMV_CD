---
name: amv-preferences
description: The channel's house preferences, machine layout and per-show notes for AMV_CD (Shorts, intros, lyric AMVs). Load together with amv-ops for any AMV_CD task, before making a Short, intro or AMV.
---

# AMV_CD preferences (house style)

How the owner wants things made, and on which machine. amv-ops is the generic
how-to; this skill wins where they differ. When a new preference is stated,
add it here with the date and commit it with the code.

## Working habits

- Commit + push AMV_CD to `main` after every change, without being asked.
- Quality over speed or size.
- Verify before claiming it works: run it, look at the review sheet/strip,
  check streams (`ffprobe`: video + audio only, audio as long as video).
- Fix the code (for every edit), not one output's data.
- Code stays general: no show, song or `/mnt/...` path in the CODE (2026-10-02);
  preferences and notes live in this skill (in the repo, 2026-10-02); generated
  data in gitignored `config.json` + `workspace/`.

## Machine layout

- Anime library: `/mnt/datadisk/anime/<Show_Name>/`, one folder per show
  (regroup any download dir that way). `config.json` "library_dir".
- Songs: `/mnt/datadisk/song/`; royalty-free tracks: `/mnt/datadisk/background_music/`.
- Everything I make in AMV_CD is in `AMV_CD/workspace/` (one folder, like remanga):
  projects, Short specs + catalog (`global/`), delivered Shorts (`output/shorts/`), caches (`tmp/`).
- Whisper weights: `/mnt/datadisk/remanga/checkpoints/faster_whisper_large_v3`
  (config "transcribers"), so there's no second 3 GB download.
- Thumbnail style references: `/mnt/datadisk/thumbnail_examples` (yellow labels + arrows).
- Reference edits for flow: `/mnt/datadisk/ReferanceEdit` (Voidwalker, a JJK edit).
- Channel intro copies: `/mnt/datadisk/channel_intro/` (1080p + a 4K/24 fps/44.1 kHz
  copy that joins onto remanga recaps by stream copy).
- 14 GB RAM, RTX 3060 12 GB - check a model's memory before running it.

## Shorts - what I want

- "make N shots" = N YouTube **Shorts**.
- **Story Shorts only** (2026-09-27): episode scenes with the ENGLISH dub and
  captions -> beat-cut montage from the song's drop -> an outro line.
  **No music-only Shorts** (2026-09-28) - every Short has the anime's own voices.
- **Voices only** (2026-10-02): the episode's background music/effects are
  stripped from dialogue (Demucs separator, htdemucs_ft). Keep it on.
- Layout (2026-09-26): the whole 16:9 picture centred on a blurred, dimmed
  copy of itself - never a full-screen 9:16 crop.
- The anime's name is written at the top of every Short (2026-10-02), above
  the hook line (spec "anime_label" for a shorter form of a long title).
- Every Short gets a title (<= 100 chars with " #shorts"), a description and a
  thumbnail in the thumbnail_examples style. The thumbnail is a **separate
  file** I upload by hand (2026-10-02: no thumbnail inside the video).
- All previous Shorts (S001-S024) were deleted 2026-10-02 at my request.
- Outputs easy to find, names never collide: `SNNN_name/`, every file
  prefixed with the number, INDEX.md, by_anime/.
- Titles follow what the DUB says, not the subtitles (they differ).
- Songs without " - Artist" in the file name get the `<ARTIST ...>`
  placeholder - tell me so I fill it in.
- **Popular songs** (2026-10-02): pick well-known tracks that fit the story's
  mood (e.g. Alibi for dark/tragic, Bling-Bang-Bang-Born for OP/comedic) -
  obscure instrumentals "don't vibe". Set "song_credit" when the file name
  isn't "Title - Artist".
- **Voices clearly audible** over the music (2026-10-02): dialogue is
  levelled to -14 LUFS; the last outro word must never be faded out.
- Effects are optional (slowed+reverb, nightcore, outline/glow/grain) - use
  them when they suit the story.
- Match footage energy to the song; my ranking of the first montage tests:
  Re:Zero > Hell Mode > Angel ("it doesn't follow" = hits falling off the cuts).
- Rejected: voice cloning, per-panel emoting (remanga), wizard-style
  settings - keep settings a flat list.

## Per-show notes

- **Mushoku Tensei**: subtitles are OCR'd bitmaps (typos, no punctuation) -
  search loosely, trust the dub transcript. Has fanservice involving child
  characters: look at every pick (strip), blacklist on sight.
- **Re:Zero** (Director's Cut) ep08 2140-2690 s: Petelgeuse + Subaru's
  breakdown (dark/evil intros).
- **No Game No Life** (`NoGameNoLife`): episodes 1-12, the Zero movie is
  episode 101 (dual audio), specials 201-206 are Japanese-only. Subtitles are
  typeset per frame (merged by dialogue). Fanservice involving Shiro (11) and
  others: ep 7 bath (07-22 to 07-60), ep 6 1031.8 (circular-breathing kiss),
  ep 6 1175.4, Zero 4640.5/4676.9/5359.0 - never use. Built: S025-S028.
- **Rich_Girl_Caretaker**: Japanese audio only - keeps original voices with
  English subtitles as captions.
- **Smoking_Behind_the_Supermarket**: "smok" matches 705 shots - use focused
  regexes.
- Unravel (remanga/global/bgm) is NOT royalty-free; I was told.

## My projects and intros

- Lyric AMV: `workspace/projects/mushoku_who_i_am/` (song.mp3 beside it) (Mushoku Tensei S1 x "Who I Am
  Anymore", two Suno rips back to back). OP/ED zones: the release subtitles
  the OP; I haven't decided whether the AMV should use `song_zones`.
- Channel intro: `workspace/global/intro/montages/channel_intro.json` (11 s, no name on
  screen), mood intros `evil_intro`, `subaru_intro`, `flow_intro`;
  remake spec `workspace/global/intro/remakes/mushoku_ep1_recap.json` (audio offset 0.242 s).
