"""What the English dub actually says in a story segment, and where.

Dubs are rewritten for lip-sync: the English SUBTITLE track (which finds the
moment - see amv.intro.dialogue) has other words and other timings than the
English AUDIO. So each story segment's dub audio is transcribed (the
`transcriber` plug-in, faster-whisper large-v3 by default: word timings,
cached), the segment's in/out points are moved so no spoken word is cut, and
the captions are the dub's own words.

Which transcriber: config.json "transcriber" (default: the first installed);
its settings: "transcribers": {name: {...}} - e.g. a local model folder.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from amv.shorts import catalog

PAD = 2.5  # transcribe this much either side, to see words the approximate bounds cut


def transcriber():
    """(the configured Transcriber plug-in, its settings)."""
    from amv import plugins
    from amv.core.config import load

    cfg = load()
    plug = plugins.get("transcriber", cfg.raw.get("transcriber") or None)
    return plug, cfg.plugin_settings("transcriber", plug.name)


def _key(file: str, stream: int, t0: float, t1: float, voices: bool = False) -> str:
    return f"{file}|{stream}|{t0:.3f}|{t1:.3f}" + ("|voices" if voices else "")


def separate(clips: list[dict]) -> list[dict]:
    """The clips pointed at their voices only (the configured separator plug-in)."""
    from amv import plugins
    from amv.core.config import load

    cfg = load()
    sep = plugins.get("separator", cfg.raw.get("separator") or None)
    return plugins.call(sep.isolate, clips, cfg.plugin_settings("separator", sep.name))


def transcribe(jobs: list[tuple[str, int, float, float]], voices: bool = False) -> dict[str, list[list]]:
    """Words (absolute source seconds) for each (file, audio stream, t0, t1);
    one model load for all the ones not cached yet. `voices`: transcribe the
    separated voices, not the full mix - an explosion under "Wyvern Slash!"
    made whisper hear "Wyvern great googly" in the mix, and nothing in the stem."""
    store = catalog._read(catalog.CACHE / "dub.json")
    todo = [j for j in jobs if _key(*j, voices) not in store]
    if todo:
        sources = [(file, stream, t0) for file, stream, t0, _ in todo]
        if voices:
            stems = separate([{"file": f, "stream": s, "src": t0, "dur": t1 - t0} for f, s, t0, t1 in todo])
            sources = [(c["file"], c["stream"], c["src"]) for c in stems]
        with tempfile.TemporaryDirectory() as tmp:
            wavs = []
            for k, ((_, _, t0, t1), (file, stream, at)) in enumerate(zip(todo, sources, strict=True)):
                wav = Path(tmp) / f"{k}.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-t", f"{t1 - t0:.3f}", "-i", file,
                                "-map", f"0:a:{stream}", "-ac", "1", "-ar", "16000", str(wav)], check=True)
                wavs.append(str(wav))
            from amv import plugins

            plug, settings = transcriber()
            words = plugins.call(plug.transcribe, wavs, settings)
            for (file, stream, t0, t1), wav in zip(todo, wavs, strict=True):
                store[_key(file, stream, t0, t1, voices)] = [[round(a + t0, 3), round(b + t0, 3), w] for a, b, w in words[wav]]
        catalog._write(catalog.CACHE / "dub.json", store)
    return {_key(*j, voices): store[_key(*j, voices)] for j in jobs}


SENTENCE_END = r"([!?]|(?<!\.)\.)$"  # "..." / "…" is a hesitation ("I truly... love you"), not an end
# Whisper often leaves punctuation out ("everything i am to you now please come
# back to me"): a pause this long between words also ends a sentence.
SENTENCE_PAUSE = 0.7


# Whisper sometimes drops the full stops of a whole stretch but keeps the
# capitals: "The world of games It's Disboard You see, everything..." - a
# capitalised word after a short pause starts a sentence (not "I", "I'm"...,
# and not after a comma).
CAPITAL_PAUSE = 0.2


def ends_sentence(words: list[list], i: int) -> bool:
    """Does a sentence end after word i?"""
    if i + 1 >= len(words) or re.search(SENTENCE_END, words[i][2]):
        return True
    gap = words[i + 1][0] - words[i][1]
    nxt = words[i + 1][2]
    capital = nxt[:1].isupper() and not re.match(r"^I(\b|'|$)", nxt) and not words[i][2].endswith(",")
    return gap >= SENTENCE_PAUSE or (capital and gap >= CAPITAL_PAUSE)


def starts_sentence(words: list[list], i: int) -> bool:
    """Does a sentence start at word i?"""
    return i == 0 or ends_sentence(words, i - 1)


def refine(words: list[list], start: float, end: float) -> tuple[float, float, list[list]]:
    """Move [start, end] out to whole sentences: back to where the first
    kept word's sentence starts (<= 6 s), on to where the last one's ends
    (<= 6 s) - a scene that stopped at the next comma ("...the two of us,")
    played as an unfinished sentence. The exact in/out points then come
    from the voice itself (voice_bounds). Returns (start, end, kept)."""
    kept = [w for w in words if w[1] > start + 0.05 and w[0] < end - 0.05]
    if not kept:
        return start, end, []
    first, last = words.index(kept[0]), words.index(kept[-1])
    while not starts_sentence(words, first) and start - words[first - 1][0] < 6.0:
        first -= 1
    while not ends_sentence(words, last) and words[last + 1][1] - end < 6.0:
        last += 1
    kept = words[first:last + 1]
    return round(min(start, kept[0][0] - 0.12), 3), round(max(end, kept[-1][1] + 0.2), 3), kept


def mid_sentence(words: list[list], kept: list[list]) -> str | None:
    """Why a scene of these kept words would cut a sentence, or None."""
    if not kept:
        return None
    first, last = words.index(kept[0]), words.index(kept[-1])
    if not starts_sentence(words, first):
        return f"starts mid-sentence: '...{' '.join(w[2] for w in words[max(0, first - 4):first])}' | " \
               f"'{' '.join(w[2] for w in kept[:4])}...'"
    if not ends_sentence(words, last):
        return f"ends mid-sentence: '...{' '.join(w[2] for w in kept[-4:])}' | " \
               f"'{' '.join(w[2] for w in words[last + 1:last + 5])}...'"
    return None


# The voice itself sets the cut, not whisper's word times (they end early: a
# word's tail - "lose", "me" - was cut off). 10 ms frames; "silent" = this far
# under the loud part of the speech, for this long.
ENV_HOP = 0.01
SILENT_DB = 28.0
SILENT_FOR = 0.15
END_CAP = 1.2  # never carry an end more than this past the last word


def envelope(wav: str) -> np.ndarray:
    import soundfile as sf

    data, sr = sf.read(wav, dtype="float32", always_2d=True)
    hop = int(sr * ENV_HOP)
    x = data.mean(1)[: len(data) // hop * hop].reshape(-1, hop)
    return 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9)


LOUD_CUT_DB = 20.0  # a cut this close to the speech's level is a cut through a voice


def voice_bounds(env: np.ndarray, offset: float, words: list[list], kept: list[list]) -> tuple[float, float, str | None]:
    """(start, end, problem) in source seconds: where the kept speech really
    begins and fades out. `env` is the voices stem's envelope, `offset` the
    source time of its first frame. Each cut goes at the first silence past
    the speech; with none before the next word (the next line follows at
    once) at the quietest moment between them. `problem` says why a cut
    still falls inside a voice (whisper's punctuation said the sentence
    ended, the voice says it goes on)."""
    def frame(t: float) -> int:
        return max(0, min(len(env) - 1, int(round((t - offset) / ENV_HOP))))

    def time(f: int) -> float:
        return offset + f * ENV_HOP

    a, b = frame(kept[0][0]), frame(kept[-1][1])
    ref = float(np.percentile(env[a:b], 90)) if b > a else float(env.max())
    silent = env < ref - SILENT_DB
    run = max(1, int(SILENT_FOR / ENV_HOP))
    first, last = words.index(kept[0]), words.index(kept[-1])
    problem = None

    nxt = words[last + 1][0] if last + 1 < len(words) else kept[-1][1] + END_CAP + 0.05
    cap = min(nxt - 0.05, kept[-1][1] + END_CAP)
    lo, hi = frame(kept[-1][1] - 0.05), frame(cap)
    end = None
    for f in range(lo, max(lo, hi - run) + 1):
        if silent[f:f + run].all():
            end = time(f) + 0.1
            break
    if end is None:  # no silence before the next word: the quietest moment in between
        f = lo + int(np.argmin(env[lo:hi + 1])) if hi > lo else hi
        end = time(f)
        if env[f] > ref - LOUD_CUT_DB:
            problem = (f"the voice is still loud ({env[f] - ref:.0f} dB) at the out point after "
                       f"'{' '.join(w[2] for w in kept[-3:])}' - the sentence goes on: "
                       f"'{' '.join(w[2] for w in words[last + 1:last + 5])}'")
    end = min(cap, max(end, kept[-1][1] + 0.12))

    prev = words[first - 1][1] if first > 0 else kept[0][0] - 0.65
    floor = max(prev + 0.05, kept[0][0] - 0.6)
    lo, hi = frame(floor), frame(kept[0][0] + 0.03)
    start = None
    for f in range(hi, min(hi, lo + run) - 1, -1):
        if silent[f - run:f].all():
            start = time(f) - 0.06
            break
    if start is None:
        f = lo + int(np.argmin(env[lo:hi + 1])) if hi > lo else lo
        start = time(f)
        if env[f] > ref - LOUD_CUT_DB and first > 0 and problem is None:
            problem = (f"the voice is still loud ({env[f] - ref:.0f} dB) at the in point before "
                       f"'{' '.join(w[2] for w in kept[:3])}'")
    start = max(floor, min(start, kept[0][0] - 0.05))
    return round(start, 3), round(end, 3), problem


def captions(kept: list[list], seg_start: float, out_at: float, max_words: int = 5) -> list[dict]:
    """Short caption chunks from the kept words: break at sentence ends,
    at pauses over 0.35 s, or every `max_words` words."""
    # Whisper loops on a stammer ("I... I... I... I... I..."): at most two in a row.
    kept = [w for k, w in enumerate(kept)
            if k < 2 or not (w[2].lower() == kept[k - 1][2].lower() == kept[k - 2][2].lower())]
    chunks: list[list[list]] = []
    for w in kept:
        if chunks:
            last = chunks[-1]
            full = len(last) >= max_words or re.search(r"[.!?…]$", last[-1][2]) or w[0] - last[-1][1] > 0.35
            if not full:
                last.append(w)
                continue
        chunks.append([w])
    out = []
    for c in chunks:
        text = " ".join(w[2] for w in c)
        text = re.sub(r"\s+([,.!?…])", r"\1", text).strip()
        out.append({"start": round(out_at + c[0][0] - seg_start, 3),
                    "end": round(out_at + c[-1][1] - seg_start + 0.15, 3), "text": text})
    # no overlap, no gap flicker: each caption runs to the next when they are close
    for a, b in zip(out, out[1:], strict=False):
        if b["start"] - a["end"] < 0.25:
            a["end"] = b["start"]
    return out
