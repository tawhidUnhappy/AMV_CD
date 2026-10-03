"""The active lyric-AMV project: workspace/projects/<name>/project.json (config.json
"project" picks it; the folder is yours and gitignored).

A project holds everything one edit decides that is not code:

    song, source_dir, episode_pattern   override config.json for this edit
    lyrics.phrases                      the lyric plan: [{first_word, last_word,
                                        lines, section, emphasis?, show?}]
                                        word indices into workspace/tmp/song/words_vocals.txt
    lyrics.expected_first_word          {index: word} - guards against drift
    section_episodes                    {section: [first_ep, last_ep]} - the story arc
    pacing                              cut lengths: max_shot, break_cut, min_shot,
                                        tail_cut, open_cut, snap_tolerance (seconds)
    themes                              {lyric line: {keywords, speaker?}} - search terms
    main_speakers                       named speakers to prefer (empty = any line)
    blacklist                           [{episode, start, end}] - rejected on sight
    thumbnails                          [{name, source, texts: [{text, x, y, ...}]}]

examples/project.example.json is a complete small one to copy.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

from amv.core.config import load


def folder(name: str | None = None) -> Path:
    cfg = load()
    return cfg.projects_dir / (name or cfg.project)


@lru_cache(maxsize=1)
def optional() -> dict:
    """The active project's data; {} when none is configured or its folder is
    gone (commands that need one fail in required(); Shorts and intros don't)."""
    name = load().project
    if not name:
        return {}
    path = folder(name) / "project.json"
    if not path.is_file():
        print(f"note: project {name!r}: {path} not found (config.json \"project\"; "
              "examples/project.example.json to start one)", file=sys.stderr, flush=True)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def required(key: str):
    """project[key], or a clear error naming what to set."""
    data = optional()
    if not data:
        raise SystemExit('no project: set "project" in config.json to a folder in projects/ '
                         "(copy examples/project.example.json to workspace/projects/<name>/project.json)")
    if key not in data:
        raise SystemExit(f"project {data.get('name', load().project)!r} has no {key!r} - see amv.core.project")
    return data[key]
