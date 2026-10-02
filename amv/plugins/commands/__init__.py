"""The built-in ./amv.sh commands. Each is a module run as __main__ with the
remaining arguments (every one has its own --help); a drop-in plug-in adds
its own with register("command", Command(...)).

`gpu` commands import torch (Demucs, WhisperX, the PGS OCR model) and need
the full project environment (`uv sync`, then AMV_FULL=1 ./amv.sh ...)."""

from amv.plugins import Command, register

_COMMANDS = (
    ('song', 'vocals', 'amv.audio.isolate_vocals', True, 'Demucs -> workspace/tmp/song/vocals.wav'),
    ('song', 'transcribe', 'amv.audio.transcribe_song', True, 'WhisperX word timings of the vocal stem'),
    ('song', 'beats', 'amv.audio.beats', False, 'librosa beat grid -> workspace/tmp/song/beats.json'),
    ('song', 'words', 'amv.subs.dump_words', False, 'numbered transcript words, for writing amv/audio/lyrics.py'),
    ('source', 'subs', 'amv.subs.extract_subs', True, 'episode subtitles (OCR for bitmap tracks) -> scene index'),
    ('the edit', 'timeline', 'amv.render.timeline', False, 'print the cut schedule'),
    ('the edit', 'select', 'amv.render.select_clips', False, 'fill every slot -> workspace/tmp/edl.json'),
    ('the edit', 'lyrics', 'amv.render.lyric_overlay', False, 'lyric overlay -> workspace/tmp/work/lyrics.ass (reads the EDL)'),
    ('the edit', 'render', 'amv.render.pipeline', False, 'grade, join, burn lyrics, mux -> workspace/tmp/out/amv.mp4'),
    ('look at it', 'sheet', 'amv.vision.contact_sheet', False, 'contact sheets of an EDL (one frame per slot)'),
    ('look at it', 'strip', 'amv.vision.strip', False, 'start/middle/end of every slot of an EDL, one row each'),
    ('look at it', 'compare', 'amv.vision.compare', False, 'two videos frame by frame: correlation report + sheet'),
    ('look at it', 'exposure', 'amv.vision.check_exposure', False, 'near-black / blown runtime of a render'),
    ('look at it', 'grade-preview', 'amv.render.grade_preview', False, 'graded vs raw frames, no render'),
    ('look at it', 'fonts', 'amv.render.font_compare', False, 'candidate lyric fonts over a real frame'),
    ('look at it', 'check-timing', 'amv.subs.check_lyric_timing', False, 'does the lyric text sit over singing'),
    ('look at it', 'check-sync', 'amv.subs.check_sync', False, 'A/V offset of a render against the song'),
    ('extras', 'thumbs', 'amv.thumbnail', False, 'YouTube thumbnails from real frames'),
    ('extras', 'thumb-candidates', 'amv.vision.thumb_candidates', False, 'strong frames to build thumbnails from'),
    ('extras', 'intro', 'amv.intro', False, 'a new short intro cut to the opening of a track'),
    ('extras', 'reference', 'amv.intro.reference', False, 'which episode frame is behind every frame of a video'),
    ('extras', 'remake', 'amv.intro.remake', False, 'render a remake of an existing intro from a spec or plan'),
    ('extras', 'dialogue', 'amv.intro.dialogue', False, "every show's subtitle lines, cached; --find REGEX to search them"),
    ('extras', 'flow', 'amv.intro.flow', False, 'which way each shot of a pool moves at its start and end (for flowing cuts)'),
    ('extras', 'montage', 'amv.intro.montage', False, 'render an editor-style montage from a shot list (dissolves, punches)'),
    ('shorts', 'short-song', 'amv.shorts.song', False, "where a track drops, the Short's window and its bass-hit grid"),
    ('shorts', 'short-find', 'amv.shorts.find', False, 'candidate shots of a show (dialogue + motion) and sheets with the 9:16 crop'),
    ('shorts', 'short', 'amv.shorts.build', False, 'a vertical Short from a spec: plan, crop, effects, render, title/description'),
    ('shorts', 'short-thumb', 'amv.shorts.thumb', False, "a Short's thumbnail (labels + arrows), or --candidates frames to pick from"),
    ('shorts', 'short-index', 'amv.shorts.deliver', False, 'numbered Short folders in shorts_dir: INDEX.md, by_anime/'),
    ('shorts', 'short-catalog', 'amv.shorts.catalog', False, 'what earlier sessions learned: songs, vetted/rejected shots, Shorts built'),
    ('upkeep', 'config', 'amv.core.config', False, 'print the resolved config.json'),
    ('upkeep', 'regress', 'amv.core.regress', False, 'snapshot / check pipeline outputs around a refactor'),
    ("upkeep", "plugins", "amv.plugins.cli", False, "every installed plug-in, by kind, and any that failed to load"),
)

for order, (group, name, module, gpu, text) in enumerate(_COMMANDS):
    register("command", Command(name, module, text, group=group, gpu=gpu, order=order))
