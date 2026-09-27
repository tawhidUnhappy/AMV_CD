"""What the English dub actually says in a story segment, and where.

Dubs are rewritten for lip-sync: the English SUBTITLE track (which finds the
moment - see amv.intro.dialogue) has other words and other timings than the
English AUDIO. So each story segment's dub audio is transcribed (faster-whisper
large-v3, word timings, cached), the segment's in/out points are moved so no
spoken word is cut, and the captions are the dub's own words.

The model: $AMV_WHISPER_MODEL, else remanga's local large-v3 weights when
present (no second 3 GB download), else "large-v3" from the Hub.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from amv.shorts import catalog

PAD = 2.5  # transcribe this much either side, to see words the approximate bounds cut
LOCAL_MODEL = Path("/mnt/datadisk/remanga/checkpoints/faster_whisper_large_v3")
RUN = ["uv", "run", "-q", "--no-project", "--python", "3.12", "--with", "faster-whisper",
       "--with", "nvidia-cublas-cu12", "--with", "nvidia-cudnn-cu12", "python",
       str(Path(__file__).with_name("dub_worker.py"))]


def model_name() -> str:
    if os.environ.get("AMV_WHISPER_MODEL"):
        return os.environ["AMV_WHISPER_MODEL"]
    return str(LOCAL_MODEL) if (LOCAL_MODEL / "model.bin").exists() else "large-v3"


def _key(file: str, stream: int, t0: float, t1: float) -> str:
    return f"{file}|{stream}|{t0:.3f}|{t1:.3f}"


def transcribe(jobs: list[tuple[str, int, float, float]]) -> dict[str, list[list]]:
    """Words (absolute source seconds) for each (file, audio stream, t0, t1);
    one model load for all the ones not cached yet."""
    store = catalog._read(catalog.CACHE / "dub.json")
    todo = [j for j in jobs if _key(*j) not in store]
    if todo:
        with tempfile.TemporaryDirectory() as tmp:
            wavs = []
            for k, (file, stream, t0, t1) in enumerate(todo):
                wav = Path(tmp) / f"{k}.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", file,
                                "-map", f"0:a:{stream}", "-ac", "1", "-ar", "16000", str(wav)], check=True)
                wavs.append(str(wav))
            print(f"Transcribing {len(wavs)} dub segment(s) ({model_name()})...", flush=True)
            done = subprocess.run([*RUN, model_name(), *wavs], capture_output=True, text=True)
            if done.returncode != 0:
                raise SystemExit(f"dub transcription failed:\n{done.stderr[-2000:]}")
            words = json.loads(done.stdout)
            for (file, stream, t0, t1), wav in zip(todo, wavs, strict=True):
                store[_key(file, stream, t0, t1)] = [[round(a + t0, 3), round(b + t0, 3), w] for a, b, w in words[wav]]
        catalog._write(catalog.CACHE / "dub.json", store)
    return {_key(*j): store[_key(*j)] for j in jobs}


def refine(words: list[list], start: float, end: float) -> tuple[float, float, list[list]]:
    """Move [start, end] so no word is cut: a word straddling an edge is
    taken whole; the out point gets a short tail but stops before the next
    word. Returns (start, end, the words kept)."""
    kept = [w for w in words if w[1] > start + 0.05 and w[0] < end - 0.05]
    if not kept:
        return start, end, []
    # Words running straight into the kept speech (gap < 0.3 s) are the same
    # sentence - the dub's "No" before "matter how you feel" ended right at a
    # subtitle-based in point and was lost. Walk back through them, <= 1.5 s.
    # Walk the in point back to the start of its sentence (a word after one
    # ending . ! ?) through joined speech, <= 3 s: the dub's "No" before "matter
    # how you feel" was lost at a subtitle-based in point. If no sentence start
    # is that close, stop at the nearest comma rather than mid-phrase ("in a
    # squeezing grip, and..." opened an outro).
    first = words.index(kept[0])
    back, k = [], first
    while k > 0 and words[k][0] - words[k - 1][1] < 0.6 and start - words[k - 1][0] < 3.0 \
            and not re.search(r"[.!?…]$", words[k - 1][2]):
        k -= 1
        back.insert(0, words[k])
    at_sentence = k == 0 or re.search(r"[.!?…]$", words[k - 1][2]) or words[k][0] - words[k - 1][1] >= 0.6
    if back and not at_sentence:
        commas = [i for i, w in enumerate(back) if re.search(r",$", w[2])]
        back = back[commas[-1] + 1:] if commas else []
    kept = back + kept
    # And end on punctuation: an out point mid-clause ("...who's always
    # worried") reads as a cut-off. Walk forward to the next , . ! ? <= 2 s.
    last = words.index(kept[-1])
    while (not re.search(r"[.,!?…]$", kept[-1][2]) and last + 1 < len(words)
           and words[last + 1][0] - kept[-1][1] < 0.6 and words[last + 1][1] - end < 2.0):
        last += 1
        kept.append(words[last])
    new_start = min(start, kept[0][0] - 0.12)
    after = [w for w in words if w[0] >= kept[-1][1]]
    tail_room = (after[0][0] - 0.06) if after else kept[-1][1] + 0.6
    new_end = max(end, min(kept[-1][1] + 0.35, tail_room))
    before = [w for w in words if w[1] <= kept[0][0]]
    if before:
        new_start = max(new_start, before[-1][1] + 0.04)
    return round(new_start, 3), round(new_end, 3), kept


def captions(kept: list[list], seg_start: float, out_at: float, max_words: int = 5) -> list[dict]:
    """Short caption chunks from the kept words: break at sentence ends,
    at pauses over 0.35 s, or every `max_words` words."""
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
