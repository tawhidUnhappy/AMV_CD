"""What earlier sessions learned, kept so the next one starts from it.

Two layers:

- amv/shorts/catalog/ (COMMITTED, small JSON, the knowledge):
    songs.json          per track: tempo, beat period, bass drops, the windows used
    shots/<Series>.json per shot: what it shows ("why"), moods, crop x, verdict
                        (good / reject + reason), which Shorts used it
    shorts.json         every Short built: spec, song window, series, when
  `./amv.sh short` records into it on every build; `short-find` reads it (rejects
  are skipped, known-good shots are starred on the sheets); `--import-intros`
  seeds it from the hand-vetted montage specs in amv/intro/montages/.

- tmp/shorts/cache/ (NOT committed, the measurements): crop/focus/motion per
  shot window and the librosa analysis per song, keyed by file + times (+ mtime
  for songs), so a rerun decodes nothing it already measured.

    ./amv.sh short-catalog                          # what is known, per show and per song
    ./amv.sh short-catalog Re_Zero --mood dark      # good shots of a show for a mood
    ./amv.sh short-catalog Re_Zero --sheet          # sheet of them (crop drawn) to pick from
    ./amv.sh short-catalog Hell_Mode --reject 12-600.5 --reason "dust hides the monster"
    ./amv.sh short-catalog Re_Zero --not-vertical 08-2691.8 --reason "eye macro, mush at 9:16"
    ./amv.sh short-catalog Hell_Mode --note 12-472.0 "Allen's red eye ignites" --mood power
    ./amv.sh short-catalog --import-intros
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import threading
from pathlib import Path

from amv.core import paths

CATALOG = Path(__file__).with_name("catalog")
CACHE = paths.TMP / "shorts" / "cache"
_LOCK = threading.Lock()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ---- measurement cache (tmp/, machine-local) ---------------------------------

def cached(kind: str, key: str, compute):
    """compute() once per (kind, key); the value must be JSON-able."""
    path = CACHE / f"{kind}.json"
    with _LOCK:
        store = _read(path)
        if key in store:
            return store[key]
    value = compute()
    with _LOCK:
        store = _read(path)
        store[key] = value
        _write(path, store)
    return value


def song_key(song: Path) -> str:
    st = song.stat()
    return hashlib.sha1(f"{song.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]


# ---- the knowledge (committed) -------------------------------------------------

def shots_file(series: str) -> Path:
    return CATALOG / "shots" / f"{series}.json"


def shots(series: str) -> dict:
    return _read(shots_file(series))


def rejected(series: str, vertical: bool = False) -> set[str]:
    """Ids never to offer; with `vertical`, also those that do not survive a 9:16 crop."""
    return {k for k, v in shots(series).items()
            if v.get("verdict") == "reject" or (vertical and v.get("vertical") is False)}


def update_shot(series: str, sid: str, **fields) -> None:
    with _LOCK:
        data = shots(series)
        entry = data.setdefault(sid, {})
        for k, v in fields.items():
            if v is None:
                continue
            if k in ("moods", "used_in"):
                entry[k] = sorted(set(entry.get(k, [])) | set(v))
            else:
                entry[k] = v
        _write(shots_file(series), data)


def moment_id(episode: int, t: float) -> str:
    """A catalog key: the moment, not the index shot around it - in dark
    scenes the 8 fps index misses cuts and one "shot" can hold a minute of
    different ones."""
    return f"{episode:02d}-{round(float(t), 2):g}"


def vetted_x(series: str, sid: str) -> float | None:
    """A crop centre someone confirmed (a spec override or an intro's measured
    focal point) - preferred to find.crop_x, which misreads near-black frames."""
    return shots(series).get(sid, {}).get("x")


def record_short(spec: dict, spec_path: Path, items: list[dict], w) -> None:
    """Called by `short` after planning: the song window and every shot used."""
    mood = spec.get("mood", "power")
    for it in items:
        shot = it["shot"]
        update_shot(spec["series"], it["id"], episode=shot.episode, file_name=Path(shot.file).name,
                    at=it["at"], crop_x=round(it["focus"][0], 3), x=it.get("x"), why=it.get("why"),
                    moods=[mood], used_in=[spec["name"]], verdict="good", role=it["role"])
    with _LOCK:
        songs = _read(CATALOG / "songs.json")
        name = Path(spec["song"]).name
        entry = songs.setdefault(name, {})
        entry.update({"period": w.period, "path": spec["song"]})
        used = [u for u in entry.get("windows", []) if u["short"] != spec["name"]]
        entry["windows"] = [*used, {"short": spec["name"], "start": w.start, "drop": w.drop, "end": w.end,
                                    "accents": w.accents}]
        _write(CATALOG / "songs.json", songs)
        built = _read(CATALOG / "shorts.json")
        built[spec["name"]] = {"spec": str(spec_path), "series": spec["series"], "song": name, "mood": mood,
                               "window": [w.start, w.end], "drop": w.drop, "shots": [it["id"] for it in items],
                               "built": dt.date.today().isoformat()}
        _write(CATALOG / "shorts.json", built)


def record_song(song: Path, drops: list[tuple[float, float]], tempo: float, duration: float) -> None:
    with _LOCK:
        songs = _read(CATALOG / "songs.json")
        entry = songs.setdefault(song.name, {})
        entry.update({"path": str(song), "tempo": round(tempo, 2), "duration": round(duration, 2),
                      "drops": [[round(t, 2), round(r, 1)] for t, r in drops]})
        _write(CATALOG / "songs.json", songs)


# ---- seeding from the hand-vetted intro montages --------------------------------

def import_intros() -> int:
    """Every shot of amv/intro/montages/*.json has a "why" someone wrote after
    looking at it - the best-vetted footage in the repo."""
    from amv.intro.library import episode_number
    moods = {"evil_intro": "dark", "subaru_intro": "dark", "flow_intro": "power", "channel_intro": "power"}
    count = 0
    for spec_path in sorted((Path(__file__).parents[1] / "intro" / "montages").glob("*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        for s in spec.get("shots", []):
            file = Path(s["file"])
            series, ep = file.parent.name, episode_number(file.name)
            if ep is None:
                continue
            focus = s.get("focus_head") or s.get("center")
            why = re.sub(r"^(hit|accent|the drop): ", "", s.get("why", "")) or None
            update_shot(series, moment_id(ep, s["at"]), episode=ep, file_name=file.name, at=float(s["at"]),
                        x=round(focus[0], 3) if focus else None, why=why,
                        moods=[moods.get(spec_path.stem, "power")], verdict="good",
                        used_in=[f"intro:{spec_path.stem}"])
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("series", nargs="?")
    parser.add_argument("--mood", default=None)
    parser.add_argument("--sheet", action="store_true", help="draw the good shots, crop box on")
    parser.add_argument("--reject", metavar="ID")
    parser.add_argument("--reason", default=None)
    parser.add_argument("--note", nargs=2, metavar=("ID", "WHY"))
    parser.add_argument("--not-vertical", metavar="ID", help="fine in 16:9, unreadable in a 9:16 crop")
    parser.add_argument("--import-intros", action="store_true")
    args = parser.parse_args()
    if args.import_intros:
        print(f"imported {import_intros()} vetted intro shots")
    if args.reject:
        update_shot(args.series, args.reject, verdict="reject", reason=args.reason or "rejected on sight")
    if args.not_vertical:
        update_shot(args.series, args.not_vertical, vertical=False,
                    vertical_reason=args.reason or "unreadable in a 9:16 crop")
    if args.note:
        update_shot(args.series, args.note[0], why=args.note[1], moods=[args.mood] if args.mood else None)
    if args.series:
        good = {k: v for k, v in shots(args.series).items() if v.get("verdict") != "reject"
                and (not args.mood or args.mood in v.get("moods", []))}
        for sid, v in sorted(good.items(), key=lambda kv: (kv[1].get("episode", 0), kv[1].get("at", 0))):
            flag = "16:9only" if v.get("vertical") is False else ""
            print(f"{sid:10s} {','.join(v.get('moods', [])):12s} x{v.get('x', v.get('crop_x', '-'))!s:6s} {flag:8s} "
                  f"{v.get('why') or ''}  [{', '.join(v.get('used_in', []))}]")
        bad = {k: v for k, v in shots(args.series).items() if v.get("verdict") == "reject"}
        for sid, v in bad.items():
            print(f"{sid:10s} REJECT  {v.get('reason', '')}")
        if args.sheet and good:
            from amv.shorts import find

            picked = [find.shot_at(args.series, v["episode"], v["at"]) for v in good.values()]
            for s, (sid, v) in zip(picked, good.items(), strict=True):
                s.id, s.start = sid, max(s.start, v["at"])  # the moment, not the index shot's start
                s.focus, s.line = v.get("x", v.get("crop_x", 0.5)), (v.get("why") or "")[:70]
            find.POOL.mkdir(parents=True, exist_ok=True)
            for p in find.sheets(picked, find.POOL / f"{args.series}-catalog"):
                print(f"Wrote {p}")
        return
    songs = _read(CATALOG / "songs.json")
    print("songs:")
    for name, v in sorted(songs.items()):
        wins = ", ".join(f"{u['short']} {u['start']:.1f}-{u['end']:.1f} (drop {u['drop']:.2f})" for u in v.get("windows", []))
        print(f"  {name[:60]:60s} tempo {v.get('tempo', '-')}  drops {v.get('drops', [])[:3]}  used: {wins or '-'}")
    print("shots:")
    for path in sorted((CATALOG / "shots").glob("*.json")):
        data = _read(path)
        good = sum(v.get("verdict") != "reject" for v in data.values())
        print(f"  {path.stem:26s} {good} good, {len(data) - good} rejected")
    print("shorts:")
    for name, v in sorted(_read(CATALOG / "shorts.json").items()):
        print(f"  {name:26s} {v['series']:18s} {v['song'][:40]:40s} {v['built']}")


if __name__ == "__main__":
    main()
