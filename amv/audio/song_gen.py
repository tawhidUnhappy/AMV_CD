"""Make a new song with a song_generator plug-in (default ACE-Step 1.5).

    ./amv.sh song-gen "dark synthwave, female vocals, driving bass" --lyrics lyrics.txt --duration 60
    ./amv.sh song-gen "epic orchestral battle theme" --instrumental --duration 90 --count 2
    ./amv.sh song-gen "upbeat j-pop about a summer festival"        # the engine writes the lyrics

Lyrics take section tags: [verse], [chorus], [bridge], [outro]. Output goes to
workspace/output/songs/<name>/: the songs, request.json and result.json (seeds,
lyrics used, timings). config.json "song_generator" picks the engine,
"song_generators": {name: {...}} its settings."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from amv import plugins
from amv.core import config, paths


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "song"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prompt", help="style, mood, instruments, voice - the caption")
    parser.add_argument("--lyrics", help="a lyrics file, or the lyrics themselves")
    parser.add_argument("--instrumental", action="store_true")
    parser.add_argument("--duration", type=float, help="seconds (default: the engine decides)")
    parser.add_argument("--bpm", type=int)
    parser.add_argument("--key", help='e.g. "A minor"')
    parser.add_argument("--language", help="vocal language code, e.g. en, ja, bn")
    parser.add_argument("--count", type=int, default=1, help="versions to make (capped by GPU size)")
    parser.add_argument("--seed", type=int, default=-1, help="-1 = random; the same seed repeats a song")
    parser.add_argument("--name", help="output folder name (default: from the prompt + time)")
    parser.add_argument("--out", type=Path, help="output folder (default workspace/output/songs/<name>)")
    parser.add_argument("--engine", help="song_generator plug-in (default: config.json, else the first)")
    parser.add_argument("--opt", action="append", default=[], metavar="KEY=VALUE",
                        help="override one engine setting for this run (e.g. --opt steps=50 --opt adg=false)")
    args = parser.parse_args()

    cfg = config.load()
    engine = plugins.get("song_generator", args.engine or cfg.raw.get("song_generator") or None)
    lyrics = args.lyrics or ""
    if lyrics and Path(lyrics).is_file():
        lyrics = Path(lyrics).read_text(encoding="utf-8")
    out = args.out or paths.SONGS / (args.name or f"{slug(args.prompt)}_{time.strftime('%Y%m%d_%H%M%S')}")
    request = {"prompt": args.prompt, "lyrics": lyrics, "instrumental": args.instrumental,
               "duration": args.duration, "bpm": args.bpm, "key": args.key, "language": args.language,
               "count": args.count, "seed": args.seed, "out_dir": str(out)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "request.json").write_text(json.dumps({**request, "engine": engine.name}, indent=1), encoding="utf-8")

    settings = cfg.plugin_settings("song_generator", engine.name)
    for kv in args.opt:
        key, _, value = kv.partition("=")
        settings[key] = json.loads(value) if value[:1] in "-0123456789tfn[{\"" and value not in ("",) else value
    result = plugins.call(engine.generate, request, settings)
    print(f"\n{engine.name}: {len(result['files'])} song(s) in {result.get('seconds')}s "
          f"(models loaded in {result.get('load_seconds')}s; peak VRAM {result.get('peak_vram_gb')} GB, "
          f"RAM {result.get('peak_ram_gb')} GB)")
    for path, seed in zip(result["files"], result.get("seeds", [])):
        print(f"  {path}   seed {seed}")
    print(f"Lyrics used + settings: {out / 'result.json'}")


if __name__ == "__main__":
    main()
