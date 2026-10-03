"""A show's parts for Shorts, indexed once and chosen by id (remanga-style):
nothing is cut or checked by hand.

    ./amv.sh short-parts Show_Name [--episodes 1-12]   # index (once, cached per episode)
    ./amv.sh short-parts Show_Name --find "hypernova|flugel"   # lines by what is said
    ./amv.sh short-parts Show_Name --show 06L040-06L050        # read a stretch
    ./amv.sh short-parts Show_Name --sheet 06 [--range 900-1200]  # shot sheets, ids drawn

-> workspace/global/shorts/parts/<Show_Name>/<EP>.json, one per episode:

    {"series", "ep", "file", "stream", "english",
     "lines": [{"id": "06L041", "start", "end", "tail", "text", "words": [[t0, t1, w], ...]}],
     "shots": [{"id": "06S113", "start", "end", "motion", "luma"}]}

A LINE is one sentence (or speech up to a real pause): whisper's
words over the episode's separated voices (the "index_separator", Demucs by
default - fast enough for whole episodes; the build re-separates the lines it
uses with the best separator), split where a sentence ends (punctuation, or a long
pause) or the voice really stops; "end_kind" says whether a scene may stop
after it ("ok") or would cut a sentence ("mid") or a voice ("runs-on") -
`short` refuses those edges. Its start/end come from the voice
envelope, not whisper's word times (they end early). `tail` is the pause
after it that a clip keeps (<= LINE_TAIL s, never into the next voice), so
the last word always rings out. Selecting consecutive lines plays them as one
continuous clip.

A SHOT is one cut-to-cut shot from the library index (OP/ED/recap repeats,
the first/last minutes and near-black shots are already out).

A spec then lists ids only:

    "story": ["06L040-06L044", "06L060"], "outro": ["06L071"],
    "drop_shot": "06S113", "shots": ["06S120", {"id": "06S131", "why": "..."}]

and `short` refuses any part that overlaps another part of the same Short,
or footage an earlier Short used (parts/<Show>/used.json: just the time
ranges of the Shorts that exist - no build history).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from amv.core import paths

PARTS = paths.GLOBAL / "shorts" / "parts"
CHUNK = 300.0  # an episode is separated/transcribed in chunks this long
OVERLAP = 10.0  # ... overlapping this much; each keeps the words of its middle
LINE_TAIL = 1.5  # pause kept after a line's last word (config "line_tail", up to 3 s)
GAP_SILENT = 0.2  # a line boundary needs this much real silence between the words
JOIN_GAP = 2.0  # chosen lines further apart than this are separate clips (dead air dropped)
MIN_TAIL = 0.35  # a line keeps at least this much decay unless the next voice starts sooner
VOICE_BACK_DB = 10.0  # a returning voice is within this of the speech level
HARD_GAP = 1.5  # ... or a pause this long, whatever the punctuation says
GAP_DB = 18.0  # "silent" in a gap: this far under the speech (the index stem keeps some music bleed)
WORDLESS_GAP = 0.8  # a gap this long with no words counts as silent
SOFT_GAP = 0.35  # a shorter pause with real silence splits too (whisper drops punctuation), as "mid"
ID = re.compile(r"^(\d+)([LS])(\d+)$")


def folder(series: str) -> Path:
    return PARTS / series


def part_file(series: str, ep: int) -> Path:
    return folder(series) / f"{ep:02d}.json"


def load_ep(series: str, ep: int) -> dict:
    f = part_file(series, ep)
    if not f.exists():
        raise SystemExit(f"{series} ep {ep} is not indexed: ./amv.sh short-parts {series} --episodes {ep}")
    return json.loads(f.read_text(encoding="utf-8"))


def line_tail() -> float:
    from amv.core.config import load

    return max(0.0, min(3.0, float(load().raw.get("line_tail", LINE_TAIL))))


# ---- indexing --------------------------------------------------------------------

def _separator(name: str):
    from amv import plugins
    from amv.core.config import load

    cfg = load()
    sep = plugins.get("separator", name)
    return lambda clips: plugins.call(sep.isolate, clips, cfg.plugin_settings("separator", sep.name))


def _words_and_envelope(file: str, stream: int, duration: float) -> tuple[list[list], np.ndarray]:
    """Whisper's words (source seconds) and the voice envelope (ENV_HOP frames
    from 0 s) over a whole episode, from its separated voices, in chunks."""
    from amv import plugins
    from amv.core.config import load
    from amv.shorts import dub

    starts = list(np.arange(0.0, max(duration - OVERLAP, 1.0), CHUNK - OVERLAP))
    clips = [{"file": file, "stream": stream, "src": float(s), "dur": float(min(CHUNK, duration - s))} for s in starts]
    name = load().raw.get("index_separator", "demucs")
    stems = _separator(name)(clips)
    plug, settings = dub.transcriber()
    said = plugins.call(plug.transcribe, [s["file"] for s in stems], settings)
    env = np.full(int(duration / dub.ENV_HOP) + 1, -120.0)
    words: list[list] = []
    for k, (c, s) in enumerate(zip(clips, stems, strict=True)):
        origin = c["src"] - s["src"]  # source time of the stem file's first sample
        lo = c["src"] + (OVERLAP / 2 if k else 0.0)
        hi = c["src"] + c["dur"] - (OVERLAP / 2 if k + 1 < len(clips) else -1.0)
        words += [[round(a + origin, 3), round(b + origin, 3), w] for a, b, w in said[s["file"]]
                  if lo <= origin + (a + b) / 2 < hi]
        e = dub.envelope(s["file"])
        f0 = int(round(origin / dub.ENV_HOP))
        a, b = max(int(lo / dub.ENV_HOP), f0), min(int(hi / dub.ENV_HOP), f0 + len(e), len(env))
        if b > a:
            env[a:b] = e[a - f0:b - f0]
    return words, env


def _lines(words: list[list], env: np.ndarray, ep: int, tail: float) -> list[dict]:
    """Sentence-sized lines. A line ends where a sentence ends (punctuation,
    or a >= 0.7 s pause) or at a shorter pause the voice really falls silent
    in. Each line says how a scene may stop after it: "end": "ok" (sentence
    over, voice silent), "mid" (the sentence goes on) or "runs-on" (the next
    voice follows with no silence - stopping there clips it)."""
    from amv.shorts import dub

    if not words:
        return []
    spoken = np.concatenate([env[int(a / dub.ENV_HOP):int(b / dub.ENV_HOP) + 1] for a, b, _ in words])
    ref = float(np.percentile(spoken, 90))
    quiet = env < ref - GAP_DB
    run = int(GAP_SILENT / dub.ENV_HOP)

    def silence_between(t0: float, t1: float) -> bool:
        if t1 - t0 >= WORDLESS_GAP:  # no words this long: what is left in the stem is bleed, not a voice
            return True
        a, b = int(t0 / dub.ENV_HOP), int(t1 / dub.ENV_HOP)
        q = quiet[a:b].astype(float)
        return len(q) >= run and float(np.convolve(q, np.ones(run), "valid").max()) >= run

    groups, ends, cur = [], [], [words[0]]
    for i in range(len(words) - 1):
        gap = words[i + 1][0] - words[i][1]
        sentence = dub.ends_sentence(words, i) or gap >= HARD_GAP
        silent = silence_between(words[i][1], words[i + 1][0])
        if sentence or (gap >= SOFT_GAP and silent):
            groups.append(cur)
            ends.append("ok" if sentence and silent else ("runs-on" if sentence else "mid"))
            cur = []
        cur.append(words[i + 1])
    groups.append(cur)
    ends.append("ok")
    out = []
    for g, end_kind in zip(groups, ends, strict=True):
        start, end, _ = dub.voice_bounds(env, 0.0, words, g)
        text = re.sub(r"\s+([,.!?…])", r"\1", " ".join(w[2] for w in g)).strip()
        out.append({"id": f"{ep:02d}L{len(out) + 1:03d}", "start": start, "end": end, "tail": 0.0,
                    "end_kind": end_kind, "text": text, "words": g})
    # The pause after a line, kept so its last word rings out - but only up to
    # where ANY voice comes back (whisper misses a gasp, a "Well...", a scream).
    # A voice "comes back" near speech level and holds; quieter is the stem's
    # music bleed or the line's own reverb, which the tail should keep.
    loud = env > ref - VOICE_BACK_DB
    hold = int(0.1 / dub.ENV_HOP)
    for k, ln in enumerate(out):
        limit = out[k + 1]["start"] - 0.15 if k + 1 < len(out) else ln["end"] + tail
        f = int((ln["end"] + MIN_TAIL) / dub.ENV_HOP)  # the word's own decay is not a returning voice
        stop = int(min(limit, ln["end"] + tail) / dub.ENV_HOP)
        while f < stop and not loud[f:f + hold].all():
            f += 1
        ln["tail"] = round(max(0.0, min(tail, f * dub.ENV_HOP - 0.1 - ln["end"], limit - ln["end"])), 3)
    return out


def _sub_lines(series: str, ep: int, duration: float) -> list[dict]:
    """No English dub: the original voices, its English subtitle lines are the lines."""
    from amv.shorts import story

    out = []
    for ln in story.lines(series, ep, 0.0, duration):
        out.append({"id": f"{ep:02d}L{len(out) + 1:03d}", "start": round(ln["start"], 3),
                    "end": round(ln["end"], 3), "tail": 0.3, "text": ln["text"]})
    return out


def index_episode(series: str, e, force: bool = False) -> Path:
    from amv.core.ffmpeg_tools import probe_duration
    from amv.shorts import story
    from amv.shorts.find import shots_of, usable

    f = part_file(series, e.number)
    if f.exists() and not force:
        return f
    print(f"indexing {series} ep {e.number} ...", flush=True)
    duration = probe_duration(e.file)
    stream, english = story.audio_track(str(e.file))
    if english:
        raw = paths.TMP / "shorts" / "parts" / series / f"{e.number:02d}.npz"
        if raw.exists():  # separation + transcription cached: re-grouping lines is instant
            z = np.load(raw, allow_pickle=True)
            words, env = z["words"].tolist(), z["env"]
        else:
            words, env = _words_and_envelope(str(e.file), stream, duration)
            raw.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(raw, words=np.array(words, dtype=object), env=env.astype(np.float32))
        lines = _lines(words, env, e.number, line_tail())
    else:
        lines = _sub_lines(series, e.number, duration)
    shots = [{"id": f"{e.number:02d}S{k + 1:03d}", "start": s, "end": t, "motion": round(m, 2), "luma": round(lu, 2)}
             for k, (s, t, m, lu) in enumerate(x for x in shots_of(e) if usable(e, x[0], x[1], x[3], []))]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"series": series, "ep": e.number, "file": str(e.file), "stream": stream,
                             "english": english, "lines": lines, "shots": shots}, indent=0, ensure_ascii=False),
                 encoding="utf-8")
    print(f"  {len(lines)} lines, {len(shots)} shots -> {f}", flush=True)
    return f


# ---- choosing --------------------------------------------------------------------

def _range(series: str, ref: str) -> tuple[dict, list[dict]]:
    """'06L040-06L044' / '06L040' -> (episode parts, the lines)."""
    a, _, b = ref.partition("-")
    ma, mb = ID.match(a), ID.match(b or a)
    if not ma or not mb or ma.group(2) != "L" or ma.group(1) != mb.group(1):
        raise SystemExit(f"{ref!r}: a line id or range of one episode, like 06L040 or 06L040-06L044")
    ep = load_ep(series, int(ma.group(1)))
    lines = [ln for ln in ep["lines"] if int(ma.group(3)) <= int(ID.match(ln["id"]).group(3)) <= int(mb.group(3))]
    if not lines:
        raise SystemExit(f"{ref}: no such lines")
    return ep, lines


def scene(series: str, ref: str | dict) -> list[dict]:
    """A spec story/outro entry ("06L040-06L044", or {"lines": ..., "why": ...})
    -> the clips build plays, with the lines' own words."""
    extra = {}
    if isinstance(ref, dict):
        extra, ref = {k: v for k, v in ref.items() if k != "lines"}, ref["lines"]
    ep, lines = _range(series, ref)
    allowed = extra.get("cut_in_voice") or extra.get("mid_sentence")
    k = ep["lines"].index(lines[0])
    before = ep["lines"][k - 1] if k > 0 else None
    edges = []
    if before and before.get("end_kind", "ok") != "ok":
        edges.append(f"starts after {before['id']} ({before['end_kind']}: '{before['text'][-40:]}')")
    if lines[-1].get("end_kind", "ok") != "ok":
        edges.append(f"ends on {lines[-1]['id']} ({lines[-1]['end_kind']}: '{lines[-1]['text'][-40:]}')")
    if edges and not allowed:
        raise SystemExit(f"{ref}: " + "; ".join(edges) + " - take the neighbouring line too "
                         "(or set \"cut_in_voice\": true on the scene if the cut is wanted)")
    # One clip per run of lines that follow each other; a longer silence
    # between two chosen lines is dropped (it keeps only the first one's tail).
    runs, cur = [], [lines[0]]
    for a, b in zip(lines, lines[1:], strict=False):
        if b["start"] - a["end"] > JOIN_GAP:
            runs.append(cur)
            cur = []
        cur.append(b)
    runs.append(cur)
    out = []
    for run in runs:
        words = [w for ln in run for w in ln.get("words", [])]
        out.append({"ep": ep["ep"], "from": run[0]["start"], "to": round(run[-1]["end"] + run[-1]["tail"], 3),
                    "exact": True, "parts": f"{run[0]['id']}-{run[-1]['id']}", "stream": ep["stream"],
                    "english": ep["english"], **({"words": words} if ep["english"] else {}),
                    "why": extra.get("why") or " ".join(ln["text"] for ln in run),
                    **{k: v for k, v in extra.items() if k != "why"}})
    return out


def shot(series: str, ref: str | dict) -> str | dict:
    """"06S113" -> the "EP-SECONDS" id the montage builder resolves; dicts keep their keys."""
    sid = ref["id"] if isinstance(ref, dict) else ref
    m = ID.match(sid)
    if not m:
        return ref  # already "EP-SECONDS"
    ep = load_ep(series, int(m.group(1)))
    s = next((x for x in ep["shots"] if x["id"] == sid), None)
    if s is None:
        raise SystemExit(f"{sid}: no such shot")
    moment = f"{ep['ep']:02d}-{s['start'] + 0.05:.2f}"
    return {**ref, "id": moment, "part": sid} if isinstance(ref, dict) else {"id": moment, "part": sid}


def expand(spec: dict) -> dict:
    """A spec with part ids -> the form build plans (scenes as dicts, shots as moment ids)."""
    series = spec["series"]
    out = dict(spec)

    def is_part(x) -> bool:
        return (isinstance(x, str) and bool(ID.match(x.partition("-")[0]))) or (isinstance(x, dict) and "lines" in x)

    for key in ("story", "outro"):
        out[key] = [c for x in spec.get(key, []) for c in (scene(series, x) if is_part(x) else [x])]
    for key in ("build_shots", "shots"):
        out[key] = [shot(series, x) for x in spec.get(key, [])]
    if spec.get("drop_shot"):
        out["drop_shot"] = shot(series, spec["drop_shot"])
    return out


# ---- no footage twice ---------------------------------------------------------------

def ranges(series: str, story_segs: list[dict], items: list[dict]) -> list[list]:
    """[ep, start, end, what] of every piece of footage a Short shows."""
    out = [[g["ep"], g["from"], g["to"], g.get("parts") or f"ep{g['ep']} {g['from']:.1f}"] for g in story_segs]
    for it in items:
        s = it["shot"]
        out.append([s.episode, round(it["at"], 3), round(it["at"] + it["need"] * it["speed"], 3),
                    it.get("part") or it["id"]])
    return out


def check_unique(series: str, name: str, used_here: list[list]) -> None:
    """Refuse footage shown twice in this Short, or already shown by another Short."""
    clash = []
    for i, a in enumerate(used_here):
        for b in used_here[i + 1:]:
            if a[0] == b[0] and min(a[2], b[2]) - max(a[1], b[1]) > 0.1:
                clash.append(f"{a[3]} and {b[3]} show the same footage (ep {a[0]} {max(a[1], b[1]):.1f}s)")
    for other, rs in _used(series).items():
        if other == name:
            continue
        for a in used_here:
            for b in rs:
                if a[0] == b[0] and min(a[2], b[2]) - max(a[1], b[1]) > 0.1:
                    clash.append(f"{a[3]} was already used by {other} (ep {a[0]} {max(a[1], b[1]):.1f}s)")
    if clash:
        raise SystemExit("footage used twice:\n  " + "\n  ".join(clash))


def _used(series: str) -> dict:
    from amv.shorts import catalog

    f = folder(series) / "used.json"
    used = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    alive = catalog._read(catalog.CATALOG / "shorts.json")
    return {k: v for k, v in used.items() if k in alive}  # a deleted Short frees its footage


def mark_used(series: str, name: str, used_here: list[list]) -> None:
    f = folder(series) / "used.json"
    used = _used(series)
    used[name] = [[a, round(b, 2), round(c, 2)] for a, b, c, _ in used_here]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(used, separators=(",", ":")), encoding="utf-8")


def used_ids(series: str, ep: dict) -> dict[str, str]:
    """Part id -> the Short that used its footage (for --find / --sheet)."""
    out = {}
    for name, rs in _used(series).items():
        for kind in ("lines", "shots"):
            for p in ep[kind]:
                end = p["end"] + p.get("tail", 0.0)
                if any(r[0] == ep["ep"] and min(end, r[2]) - max(p["start"], r[1]) > 0.1 for r in rs):
                    out[p["id"]] = name
    return out


# ---- command -----------------------------------------------------------------------

def _episodes(spec: str | None, all_numbers: list[int]) -> list[int]:
    if not spec:
        return all_numbers
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return [n for n in out if n in all_numbers]


def main() -> None:
    from amv.shorts.find import Shot, load_show, sheets

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("series")
    parser.add_argument("--episodes", help="index only these, e.g. 1-12 or 1,4,101")
    parser.add_argument("--force", action="store_true", help="re-index episodes already indexed")
    parser.add_argument("--find", help="regex over the indexed lines (case-insensitive)")
    parser.add_argument("--show", help="print a line range, e.g. 06L040-06L050")
    parser.add_argument("--sheet", type=int, help="contact sheets of one episode's shots, ids drawn")
    parser.add_argument("--range", help="with --sheet: only shots in this time range, e.g. 900-1200")
    args = parser.parse_args()
    eps = {e.number: e for e in load_show(args.series)}

    if args.find or args.show:
        files = sorted(folder(args.series).glob("[0-9]*.json"))
        if not files:
            raise SystemExit(f"nothing indexed yet: ./amv.sh short-parts {args.series}")
        pattern = re.compile(args.find, re.IGNORECASE) if args.find else None
        for f in files:
            ep = json.loads(f.read_text(encoding="utf-8"))
            if args.show:
                _, lines = (ep, []) if not args.show.startswith(f"{ep['ep']:02d}L") else _range(args.series, args.show)
            else:
                lines = [ln for ln in ep["lines"] if pattern.search(ln["text"])]
            used = used_ids(args.series, ep) if lines else {}
            for ln in lines:
                mark = f" [used: {used[ln['id']]}]" if ln["id"] in used else ""
                flag = "" if ln.get("end_kind", "ok") == "ok" else f" [{ln['end_kind']}]"
                print(f"{ln['id']} {ln['start']:8.2f}-{ln['end']:8.2f} (+{ln['tail']:.1f}){mark}{flag}  {ln['text']}")
        return

    if args.sheet is not None:
        ep = load_ep(args.series, args.sheet)
        lo, _, hi = (args.range or "0-1e9").partition("-")
        used = used_ids(args.series, ep)
        picked = [s for s in ep["shots"] if float(lo) <= s["start"] <= float(hi) and s["id"] not in used]
        shots = [Shot(s["id"], args.series, ep["ep"], ep["file"], s["start"], s["end"], s["motion"], s["luma"])
                 for s in picked]
        stem = paths.TMP / "shorts" / "parts" / f"{args.series}-{ep['ep']:02d}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        for p in sheets(shots, stem):
            print(f"Wrote {p}")
        print(f"{len(shots)} unused shots (start / middle / end per row)")
        return

    for n in _episodes(args.episodes, sorted(eps)):
        index_episode(args.series, eps[n], args.force)


if __name__ == "__main__":
    main()
