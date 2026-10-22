---
name: amv-song-gen
description: Make new, original songs (vocals + lyrics, or instrumentals) locally with ACE-Step 1.5 through `./amv.sh song-gen` - set it up, write the caption and lyrics well, check the result, and swap engines (song_generator plug-ins). Use when the user wants an AI song, a royalty-free track for a Short/intro, background music, or asks about ACE-Step or the song generator.
---

# Song generation (amv-song-gen)

ACE-Step 1.5 (MIT; songs you make are yours, no Content ID risk from labels) runs
in its own environment, like remanga's tools. Pieces:
- `amv/plugins/ace_step/`: `setup.py` (pinned repo + `uv sync --frozen` + models),
  `generate.py` (the SongGenerator), `scripts/` (worker, models, songs). The
  scripts run in ACE-Step's env and never import `amv`.
- `amv/audio/song_gen.py`: the `song-gen` command. `amv/core/tool_setup.py`:
  `tool-setup`. `amv/core/tools.py`: `ensure` and `run(live=True)`.
- Kinds: `tool` gained the hooks `install` / `weights` / `interpreter` (a tool that
  sets itself up); `song_generator` is new. Another engine (HeartMuLa, ...) is
  one more plug-in folder, with no core changes.

## Where things live

| What | Where |
| --- | --- |
| Clone (pinned `setup.REF`) | `workspace/tools/ace_step/src` |
| Its environment | `workspace/tools/ace_step/venv` (marker `.amv-tool.json` = the ref it was built from) |
| Models | `workspace/tools/ace_step/checkpoints` (main ~10 GB + LM) |
| Songs | `workspace/output/songs/<name>/`: audio, `request.json`, `job.json`, `result.json` |

Change the location with config.json `"tools": {"ace_step": {"dir": ...}}`. Pin a
newer commit with `"ref"` there, then `./amv.sh tool-setup ace_step` re-syncs.
Generation settings go in `"song_generators": {"ace_step": {...}}`: `model`, `lm`,
`backend`, `steps`, `format` (documented in the plug-in's `__init__`).

## Guiding the user

- First time: run `./amv.sh tool-setup ace_step` yourself, in the background. It
  is one-time: several GB of environment plus ~11.5 GB of models. Say how big it
  is before starting. `song-gen` also sets itself up on first use.
- Ask only what changes the song: style and mood, vocals or instrumental, their
  own lyrics or written by the engine, length. Write the caption and lyrics
  yourself from that (rules below), show them in one short block, and generate.
- Make `--count 2` (or more) when the GPU allows. Report the files, the seeds
  and the time taken. A seed repeats a song exactly; use one to iterate on a
  good take.
- You cannot listen. Say so, and check what you can (Checks below) before
  calling a song good.

## Writing the input (from ACE-Step's own guide, docs/en/Tutorial.md)

**Caption** (the positional prompt) matters most. Combine style, mood,
instruments, timbre, vocal type and tempo feel:
"melancholic lo-fi hip-hop, warm piano, vinyl crackle, soft female vocal, slow
tempo". Be specific, not vague. Never put conflicting styles side by side; turn
a conflict into an evolution over time instead ("starts with soft strings,
becomes heavy rock").

**Lyrics** are the time script. Put each section on its own tag line: `[Intro]`,
`[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`; and `[Build]`, `[Drop]`,
`[Breakdown]`, `[Guitar Solo]`, `[Fade Out]`.
- At most one modifier per tag: `[Chorus - anthemic]`. A stack of them gets
  sung as lyrics.
- Aim for 6–10 syllables per line, and keep matching lines similar in length.
- CAPS = belted, `(words)` = backing vocals, stretched vowels ("aliiive") = held notes.
- Keep caption and lyrics consistent: an instrument tagged in the lyrics must be
  in the caption.
- Instrumental: `--instrumental`, or the lyrics `[Instrumental]`.

Write original lyrics. Never paste a real song's lyrics, and never ask for a
named singer's voice.

## Checks (before saying it is done)

- `ffprobe` each file: the length is roughly `--duration`, and there is an audio stream.
- `./amv.sh blender-beats FILE` or `./amv.sh short-song FILE`: there is a real
  beat grid, the BPM is near `--bpm`, and the sections change.
- Vocals sung: run the faster_whisper transcriber over the file (the
  `transcriber` plug-in, `amv.plugins.faster_whisper.transcribe`). Mostly the
  right words means the lyrics really got sung. An empty transcript on a vocal
  song means a failed take; try another seed.
- `result.json` holds the lyrics ACE-Step actually used, plus the timings and
  peak VRAM/RAM.

## Measured (2026-10-16, RTX 3060 12 GB, 14 GB RAM)

ACE-Step reads the 3060 as 11.6 GB, which puts it in tier 4: the 0.6B LM, INT8,
and both the DiT and the rest offloaded to the CPU. Test: a 30 s song with my
lyrics, seed 42.
- Generation: 70.5 s, plus 93.6 s to load the models, so 2:53 wall time for one song.
- Peak VRAM 5.5 GB; peak RAM 8.7 GB (9.1 GB including the process).
- Result: a 30.0 s, 48 kHz stereo wav at 120.19 BPM (asked: 120). Whisper heard
  7 of the 8 lyric lines.
- The weights match Hugging Face's sha256 (11 files). The clone is at `REF`
  with no changes.

The model load (~1.5 min) is paid once per `song-gen` run. Make all the
versions in one call (`--count`) rather than one run per version.

## Traps

- 12 GB card = ACE-Step tier 4/5 (`models.gpu()` decides). The LM falls back to
  0.6B, with INT8 and CPU offload, and batches are capped (`count_capped_to` in
  the result). CPU offload uses system RAM: this box has 14 GB, so close other
  heavy jobs (local LLM, remanga TTS) first.
- The last lyric line was missing from a 30 s song → 8 lines plus 2 tags don't fit
  in 30 s → allow ~3–4 s per sung line, or raise `--duration`.
- Whisper wrote "Thanks for watching!" over the instrumental tail → a known
  whisper hallucination over music → ignore words after the last lyric line.
- Hundreds of "AffineQuantizedTensor on older torch. Moving parameters
  individually" log lines → ACE-Step's INT8 offload path is noisy, not
  failing → ignore them.
- ACE-Step prints to stdout itself, so the worker writes `result.json` and never
  uses stdout as its answer.
- With no lyrics, not instrumental, and `lm = none`, it refuses. Writing lyrics
  needs the planner LM.
- `uv sync` needs `--frozen` and the repo's own `uv.lock`. Its pyproject pins
  torch cu128 from PyTorch's index, which an unpinned resolve can swap for a
  CPU wheel.

- "The song is bad" (2026-10-20) → with the planner LM on, the 0.6B LM writes audio codes
  and the DiT renders them as a cover ("cover task: no src_audio but audio codes provided")
  → the owner wants no reference or sample: config.json song_generators.ace_step.lm = "none".
  Without the LM a 132 s song with 26 lines skipped verse 2 in both takes (ending in
  "oh, oh") → fewer lines, or more seconds per line, and check the transcript.

- "The song quality is bad" (2026-10-22) -> ACE-Step's best-quality knobs (64 steps, ADG,
  guidance 8, shift 3) are now the defaults; DCW is NOT (an A/B: DCW alone sang 0 of 10 lines,
  whisper heard "Thank you" - the vocals were mush; everything else on sang 10/10). One knob
  per run: `song-gen ... --opt adg=false --opt steps=50`. Check every take's transcript.

## Maintenance

When a session hits something new here, add a symptom → cause → rule line
under Traps before ending the turn.
