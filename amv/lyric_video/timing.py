"""When each lyric line is sung: the song's voices stem (configured separator),
word timings of it (configured transcriber), and the known lyric lines aligned
to those words.

Whisper on a sung mix mishears and skips; the lyrics are known, so they only
need placing. A global alignment (lyric words vs heard words, fuzzy word
match) gives every line the time of its first and last matched word. Whispered or
glitched lines are often not heard in the whole-song pass but ARE heard when
their gap (between two placed lines) is transcribed on its own - the second
pass. Lines still unheard are spread over the SUNG part of the gap (the voices
stem's envelope), by word count, cut at its pauses ("filled": true). Where the stem is silent
they are left out and reported - text on screen where nothing is sung reads
worse than a missing line.

Lines in parentheses are ad-libs OR stage directions ("(Beat cuts out)") -
they are kept only when the alignment hears them."""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from amv.core.ffmpeg_tools import probe_duration

# A line is shown when at least this share of its words was heard (ad-libs need more).
MIN_COVER = 0.34
MIN_COVER_ADLIB = 0.5
# Fuzzy word match: similarity below this is a mismatch.
WORD_SIM = 0.6


def song_lyrics(song: Path) -> str:
    """The lyrics stored in the song's tags (Suno and most taggers write
    "lyrics" / "lyrics-eng" / USLT), or ""."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(song)],
                         capture_output=True, text=True, check=True).stdout
    tags = json.loads(out).get("format", {}).get("tags", {})
    for key, value in tags.items():
        if key.lower().startswith(("lyrics", "uslt", "unsyncedlyrics")):
            return value
    return ""


def parse_lines(text: str) -> list[dict]:
    """Lyric lines: [section] headers dropped, blank lines skipped,
    parenthesised whole lines marked as ad-libs."""
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line or re.fullmatch(r"\[.*\]", line):
            continue
        adlib = line.startswith("(") and line.endswith(")")
        lines.append({"text": line.strip("()").strip() if adlib else line, "adlib": adlib})
    return lines


NUMBERS = {str(i): w for i, w in enumerate("zero one two three four five six seven eight nine ten".split())}
# A heard word longer than this is smeared over a pause (whisper's first word
# after silence); line starts come from the first word that is not.
SMEAR = 1.0
WORD_STEP = 0.35


def norm(word: str) -> str:
    """Lower case, letters/digits only, digits as words ("3," -> "three")."""
    w = re.sub(r"[^a-z0-9]", "", word.lower().replace("’", "'"))
    return NUMBERS.get(w, w)


def tokens(text: str) -> list[str]:
    """Lyric words as heard: hyphenated runs split ("Oh-oh-oh" is three "oh"s)."""
    return [t for t in (norm(w) for w in re.split(r"[\s\-‐–—]+", text)) if t]


def voices_and_words(song: Path, cache: Path) -> list[list]:
    """[[start, end, word], ...] of the song's separated voices, cached."""
    from amv import plugins
    from amv.core.config import load

    out = cache / "words.json"
    key = f"{song.resolve()}|{song.stat().st_size}|{song.stat().st_mtime_ns}"
    if out.exists():
        stored = json.loads(out.read_text(encoding="utf-8"))
        if stored.get("key") == key:
            return stored["words"]
    cfg = load()
    sep = plugins.get("separator", cfg.raw.get("separator") or None)
    clip = {"file": str(song), "stream": 0, "src": 0.0, "dur": probe_duration(song)}
    stem = plugins.call(sep.isolate, [clip], cfg.plugin_settings("separator", sep.name))[0]
    plug = plugins.get("transcriber", cfg.raw.get("transcriber") or None)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "voices.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{stem['src']:.3f}", "-t", f"{clip['dur']:.3f}",
                        "-i", stem["file"], "-ac", "1", "-ar", "16000", str(wav)], check=True)
        words = plugins.call(plug.transcribe, [str(wav)], cfg.plugin_settings("transcriber", plug.name))[str(wav)]
    cache.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"key": key, "stem": stem["file"], "words": words}), encoding="utf-8")
    return words


def _sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def align(lines: list[dict], words: list[list]) -> list[dict]:
    """Each line with "start"/"end" (seconds) and "cover" (share of its words
    heard), from a global alignment of lyric words to heard words."""
    lyr = [(i, t, pos) for i, line in enumerate(lines) for pos, t in enumerate(tokens(line["text"]))]
    heard = [(w, norm(part)) for w in words for part in re.split(r"[-‐–—]+", w[2])]
    heard = [h for h in heard if h[1]]
    n, m = len(lyr), len(heard)
    skip_lyric, skip_heard = -0.6, -0.3  # unsung lyric words cost more than extra heard ones
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]  # 1 diag, 2 up (skip lyric), 3 left (skip heard)
    for i in range(1, n + 1):
        score[i][0], move[i][0] = score[i - 1][0] + skip_lyric, 2
    for j in range(1, m + 1):
        score[0][j], move[0][j] = score[0][j - 1] + skip_heard, 3
    for i in range(1, n + 1):
        a = lyr[i - 1][1]
        row, prev = score[i], score[i - 1]
        for j in range(1, m + 1):
            s = _sim(a, heard[j - 1][1])
            best, mv = prev[j - 1] + (2.0 * s if s >= WORD_SIM else -1.0), 1
            if prev[j] + skip_lyric > best:
                best, mv = prev[j] + skip_lyric, 2
            if row[j - 1] + skip_heard > best:
                best, mv = row[j - 1] + skip_heard, 3
            row[j], move[i][j] = best, mv
    hits: dict[int, list[list]] = {}
    i, j = n, m
    while i > 0 or j > 0:
        mv = move[i][j]
        if mv == 1:
            if _sim(lyr[i - 1][1], heard[j - 1][1]) >= WORD_SIM:
                hits.setdefault(lyr[i - 1][0], []).append([*heard[j - 1][0][:3], lyr[i - 1][2]])
            i, j = i - 1, j - 1
        elif mv == 2:
            i -= 1
        else:
            j -= 1
    out = []
    for k, line in enumerate(lines):
        got = sorted(hits.get(k, []))
        total = max(1, len(tokens(line["text"])))
        cover = len(got) / total
        entry = {**line, "cover": round(cover, 2)}
        if got:
            entry["start"], entry["end"] = line_start(got), got[-1][1]
        out.append(entry)
    return out


def voiced(stem: Path, rate: int = 50) -> list[tuple[float, float]]:
    """Sung stretches of the voices stem: RMS over floor + 10% of
    (p99 - p20) (the amv-lyric-sync threshold), pauses < 0.35 s bridged,
    blips < 0.15 s dropped."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(stem), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    hop = sr // rate
    n = len(mono) // hop
    rms = np.sqrt((mono[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    lo, hi = np.percentile(db, 20), np.percentile(db, 99)
    on = db > lo + 0.10 * (hi - lo)
    runs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append([start / rate, i / rate])
            start = None
    if start is not None:
        runs.append([start / rate, n / rate])
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 0.35:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= 0.15]


def fill_unheard(aligned: list[dict], sung: list[tuple[float, float]]) -> None:
    """Give lines still unheard after the second pass a time inside the sung
    part of their gap (see the module docstring). Changes lines in place."""
    for k, j in gaps(aligned):
        prev, nxt = aligned[k - 1], aligned[j]
        run = [ln for ln in aligned[k:j] if not ln["adlib"]]
        if not run:
            continue
        g0, g1 = prev["end"] + 0.05, nxt["start"] - 0.05
        segs = [(max(a, g0), min(b, g1)) for a, b in sung if b > g0 and a < g1]
        segs = [(a, b) for a, b in segs if b - a >= 0.15]
        total = sum(b - a for a, b in segs)
        if total < 0.45 * len(run):
            continue
        weights = [max(1, len(tokens(ln["text"]))) for ln in run]
        # walk the sung time: each line takes its share, cut at the nearest pause
        cuts = [segs[0][0]]
        acc, wsum = 0.0, sum(weights)
        for w in weights[:-1]:
            acc += total * w / wsum
            t = _sung_time_at(segs, acc)
            pauses = [(segs[i][1] + segs[i + 1][0]) / 2 for i in range(len(segs) - 1)]
            near = [p for p in pauses if abs(p - t) < 1.0 and p > cuts[-1] + 0.3]
            cuts.append(min(near, key=lambda p: abs(p - t)) if near else t)
        cuts.append(segs[-1][1])
        for ln, a, b in zip(run, cuts, cuts[1:]):
            ln.update(start=round(a, 3), end=round(b, 3), filled=True, placed=True)


def _sung_time_at(segs: list[tuple[float, float]], amount: float) -> float:
    for a, b in segs:
        if amount <= b - a:
            return a + amount
        amount -= b - a
    return segs[-1][1]


def _mark(lines: list[dict]) -> None:
    for line in lines:
        need = MIN_COVER_ADLIB if line["adlib"] else MIN_COVER
        line["placed"] = "start" in line and line["cover"] >= need


def gaps(aligned: list[dict]) -> list[tuple[int, int]]:
    """(first, end) index runs of unplaced lines with a placed line each side."""
    out, k = [], 0
    while k < len(aligned):
        if aligned[k]["placed"]:
            k += 1
            continue
        j = k
        while j < len(aligned) and not aligned[j]["placed"]:
            j += 1
        if k > 0 and j < len(aligned):
            out.append((k, j))
        k = j
    return out


def hear_gaps(aligned: list[dict], stem: Path, cache: Path) -> None:
    """The second pass: transcribe each gap's stretch of the stem alone (one
    model load for all, cached in words.json) and align the gap's lines to it."""
    from amv import plugins
    from amv.core.config import load

    store_path = cache / "words.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))
    heard = store.setdefault("gaps", {})
    spans = {}
    for k, j in gaps(aligned):
        t0, t1 = max(0.0, aligned[k - 1]["end"] - 0.5), aligned[j]["start"] + 0.5
        if t1 - t0 >= 1.0:
            spans[(k, j)] = (t0, t1, f"{t0:.2f}-{t1:.2f}")
    todo = [v for v in spans.values() if v[2] not in heard]
    if todo:
        cfg = load()
        plug = plugins.get("transcriber", cfg.raw.get("transcriber") or None)
        with tempfile.TemporaryDirectory() as tmp:
            wavs = []
            for t0, t1, key in todo:
                wav = Path(tmp) / f"{key}.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i",
                                str(stem), "-ac", "1", "-ar", "16000", str(wav)], check=True)
                wavs.append(str(wav))
            got = plugins.call(plug.transcribe, wavs, cfg.plugin_settings("transcriber", plug.name))
            for (t0, _, key), wav in zip(todo, wavs):
                heard[key] = [[round(a + t0, 3), round(b + t0, 3), w] for a, b, w in got[wav]]
        store_path.write_text(json.dumps(store), encoding="utf-8")
    for (k, j), (_, _, key) in spans.items():
        lo, hi = aligned[k - 1]["end"] - 0.1, aligned[j]["start"] + 0.1
        words = [w for w in heard[key] if lo <= w[0] < hi]
        for i, line in enumerate(align([{**ln} for ln in aligned[k:j]], words)):
            if "start" in line:
                aligned[k + i].update(start=line["start"], end=line["end"], cover=line["cover"], second_pass=True)
    _mark(aligned)


MAX_BACK = 1.6   # never reach further back than this for unheard leading words


def line_start(got: list[list]) -> float:
    """The line's start: its first word that is not smeared ("One" 2.2 s + "last"
    2.7 s in a whispered build-up put a line 2 s early), stepped back WORD_STEP
    for every lyric word before it - heard or NOT: when whisper missed the first
    word or two, starting at the first heard one put the text 1-2 s late
    (2026-10-22). got: [start, end, word, position in the line]."""
    for w in got:
        if w[1] - w[0] <= SMEAR:
            back = min(MAX_BACK, WORD_STEP * w[3])
            heard_before = [g for g in got if g[0] < w[0]]
            floor = heard_before[0][0] if heard_before else w[0] - back
            return max(floor, w[0] - back) if heard_before else w[0] - back
    return max(got[0][0], got[-1][1] - SMEAR)


FA_BACK = 1.6       # how far before whisper's start a line's real start may be
FA_MIN_SCORE = 0.08  # mean CTC confidence below this: keep whisper's times. Sung vowels score
                     # low (0.12-0.2) even when right - checked on spectrograms (Neon Lullaby):
                     # the aligner was right on all 13 disputed lines, whisper 1.2-1.5 s late on 3


def force_align(aligned: list[dict], stem: Path, cache: Path) -> None:
    """Exact line times: each placed line's known words force-aligned (CTC,
    forced_align tool) inside a window round whisper's placement - from just
    after the previous line (at most FA_BACK before) to just past the next
    line's start. Whisper's word stamps on sung vocals ran up to 1-2 s late.
    Cached in words.json "fa"; a weak alignment keeps whisper's times."""
    from amv.core import tools

    placed = [ln for ln in aligned if ln.get("placed")]
    store_path = cache / "words.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))
    done = store.setdefault("fa", {})
    segs = []
    for k, ln in enumerate(placed):
        prev_end = placed[k - 1]["end"] if k else 0.0
        nxt = placed[k + 1]["start"] if k + 1 < len(placed) else ln["end"] + 2.0
        t0 = max(min(prev_end, ln["start"]) - 0.1, ln["start"] - FA_BACK, 0.0)
        t1 = max(min(nxt + 0.4, ln["end"] + 1.2), ln["start"] + 0.6)
        key = f"{t0:.2f}|{t1:.2f}|{ln['text']}"
        ln["_fa"] = key
        if key not in done:
            segs.append({"key": key, "t0": t0, "t1": t1, "words": tokens(ln["text"])})
    if segs:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job.json"
            out = Path(tmp) / "out.json"
            job.write_text(json.dumps({"wav": str(stem), "out": str(out), "segments": segs}), encoding="utf-8")
            print(f"Force-aligning {len(segs)} line(s) to the voices...", flush=True)
            run = tools.run("forced_align", str(job))
            if run.returncode != 0 or not out.exists():
                print(f"  forced alignment failed, keeping whisper's times:\n{(run.stderr or '')[-1500:]}")
                for ln in placed:
                    ln.pop("_fa", None)
                return
            done.update(json.loads(out.read_text(encoding="utf-8")))
        store_path.write_text(json.dumps(store), encoding="utf-8")
    for ln in placed:
        words = [w for w in (done.get(ln.pop("_fa")) or []) if w]
        if not words:
            continue
        score = float(np.mean([w[2] for w in words]))
        ln["fa_score"] = round(score, 3)
        if score >= FA_MIN_SCORE:
            ln["whisper_start"] = ln["start"]
            ln["start"], ln["end"] = words[0][0], words[-1][1]


def timed_lines(song: Path, text: str, cache: Path) -> tuple[list[dict], list[dict]]:
    """(lines to show, lines left out) - each shown line has start/end."""
    words = voices_and_words(song, cache)
    aligned = align(parse_lines(text), words)
    _mark(aligned)
    stem = json.loads((cache / "words.json").read_text(encoding="utf-8")).get("stem")
    if stem and Path(stem).exists():
        hear_gaps(aligned, Path(stem), cache)
        fill_unheard(aligned, voiced(Path(stem)))
        force_align(aligned, Path(stem), cache)
    shown, dropped = [], []
    for line in aligned:
        (shown if line.pop("placed") else dropped).append(line)
    # The alignment is monotonic, but a line whose only matched word sits far
    # from the rest can still overlap its neighbour: clamp starts in order.
    for a, b in zip(shown, shown[1:]):
        if b["start"] < a["start"]:
            b["start"] = a["start"]
    (cache / "lines.json").write_text(json.dumps({"shown": shown, "dropped": dropped}, indent=1), encoding="utf-8")
    return shown, dropped
