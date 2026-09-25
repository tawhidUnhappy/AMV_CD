"""What is said in every episode of a library, from its text subtitle tracks,
for finding moments by what happens in them ("laugh", "kill", "sorry") rather
than by how the picture moves.

Text tracks only (ASS/SRT) - cheap, no OCR, no torch. Of an episode's English
text tracks the one with the most lines is taken: releases ship a signs-only
track beside the dialogue (Re:Zero's first English track is "Signs & Songs").
A series without text subtitles falls back to the OCR'd scene index when it is
the configured series (tmp/subs/scene_index.json), else has none.

    ./amv.sh dialogue /mnt/datadisk/anime --find "laugh|kill|die" [--series Re_Zero]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from amv.core import config, paths
from amv.intro.library import Episode, discover
from amv.subs.ass_parser import parse_ass

CACHE = paths.INTRO / "dialogue"
TEXT_CODECS = {"ass", "ssa", "subrip", "srt", "mov_text", "webvtt"}


def text_tracks(path: Path) -> list[int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries",
                          "stream=codec_name:stream_tags=language", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    streams = json.loads(out).get("streams", [])
    return [i for i, s in enumerate(streams)
            if s.get("codec_name") in TEXT_CODECS and s.get("tags", {}).get("language", "eng") in ("eng", "en")]


def extract(e: Episode) -> list[dict]:
    cache = CACHE / e.series / f"{e.number:03d}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    best: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for k in text_tracks(e.file):
            ass = Path(tmp) / f"{k}.ass"
            done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(e.file), "-map", f"0:s:{k}", str(ass)],
                                  capture_output=True)
            if done.returncode != 0 or not ass.exists():
                continue
            lines = [{"start": round(ev.start, 3), "end": round(ev.end, 3), "text": ev.text}
                     for ev in parse_ass(ass, e.number) if ev.text.strip()]
            if len(lines) > len(best):
                best = lines
    if not best and e.series == config.load().source_dir.name and paths.SCENE_INDEX.exists():
        index = paths.load_scene_index()
        best = [{"start": ev["start"], "end": ev["end"], "text": ev["text"]}
                for ev in index.get(e.number, {}).get("events", [])]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(best, indent=0), encoding="utf-8")
    return best


def load(library: dict[str, list[Episode]]) -> dict[tuple[str, int], list[dict]]:
    todo = [e for eps in library.values() for e in eps]
    with ThreadPoolExecutor(max_workers=6) as ex:
        return {(e.series, e.number): lines for e, lines in zip(todo, ex.map(extract, todo), strict=True)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--find", default=None, help="regex (case-insensitive) to search the lines for")
    parser.add_argument("--series", default=None)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    library = discover(args.root)
    if args.series:
        library = {args.series: library[args.series]}
    lines = load(library)
    for (series, number), ls in sorted(lines.items()):
        if not args.find:
            print(f"{series} {number:02d}: {len(ls)} lines")
    if args.find:
        pattern = re.compile(args.find, re.IGNORECASE)
        hits = [(s, n, ln) for (s, n), ls in sorted(lines.items()) for ln in ls if pattern.search(ln["text"])]
        for s, n, ln in hits[: args.limit]:
            print(f"{s} {n:02d} {ln['start']:8.2f}  {ln['text'][:90]}")
        print(f"{len(hits)} line(s) match")


if __name__ == "__main__":
    main()
