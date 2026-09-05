"""Project configuration and path resolution.

Everything user-specific — where the episodes live, which song, which font —
comes from `config.json` at the project root, so the pipeline is not tied to any
one machine, series or track. Copy `config.example.json` to `config.json` and
edit it, or override any single value from the command line.

Paths in the config may be absolute or relative to the project root.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("AMV_CONFIG", ROOT / "config.json"))
EXAMPLE_PATH = ROOT / "config.example.json"

DEFAULTS: dict = {
    "source_dir": "",
    "episode_pattern": r"(?:Ep[-_ ]?|E|Episode[ _])(\d{1,3})",
    "song": "assets/song.mp3",
    "lyric_font_file": "assets/lyric.ttf",
    "lyric_font_family": "Georgia",
    "lyric_font_bold": True,
    "width": 1920,
    "height": 1080,
    "fps": "24000/1001",
}


@dataclass(frozen=True)
class Config:
    source_dir: Path
    episode_pattern: str
    song: Path
    lyric_font_file: Path
    lyric_font_family: str
    lyric_font_bold: bool
    width: int
    height: int
    fps: str

    @property
    def fps_value(self) -> float:
        num, _, den = self.fps.partition("/")
        return float(num) / float(den or 1)

    @property
    def data(self) -> Path:
        return ROOT / "data"

    def require_source(self) -> Path:
        if not self.source_dir or not self.source_dir.is_dir():
            raise SystemExit(
                f"source_dir is not set or does not exist: {self.source_dir!s}\n"
                f"Set it in {CONFIG_PATH} (copy {EXAMPLE_PATH.name} to start), "
                f"or pass --source on the command line."
            )
        return self.source_dir

    def require_song(self) -> Path:
        if not self.song.is_file():
            raise SystemExit(f"song not found: {self.song}\nSet 'song' in {CONFIG_PATH}.")
        return self.song


def _resolve(value: str) -> Path:
    if not value:
        return Path()
    path = Path(os.path.expandvars(value)).expanduser()
    return path if path.is_absolute() else (ROOT / path)


@lru_cache(maxsize=1)
def load() -> Config:
    values = dict(DEFAULTS)
    if CONFIG_PATH.is_file():
        values.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    elif EXAMPLE_PATH.is_file():
        print(
            f"NOTE: no {CONFIG_PATH.name} found — using defaults. "
            f"Copy {EXAMPLE_PATH.name} to {CONFIG_PATH.name} and edit it.",
            file=sys.stderr,
        )
    return Config(
        source_dir=_resolve(values["source_dir"]),
        episode_pattern=values["episode_pattern"],
        song=_resolve(values["song"]),
        lyric_font_file=_resolve(values["lyric_font_file"]),
        lyric_font_family=values["lyric_font_family"],
        lyric_font_bold=bool(values["lyric_font_bold"]),
        width=int(values["width"]),
        height=int(values["height"]),
        fps=values["fps"],
    )


def site_packages() -> Path | None:
    """Locate the active environment's site-packages without assuming a layout.

    Used to put vendored CUDA DLLs on the search path. Hard-coding
    `.venv/Lib/site-packages` breaks under a differently-named venv, a conda
    env, or a non-Windows layout.
    """
    import sysconfig

    for key in ("purelib", "platlib"):
        candidate = sysconfig.get_paths().get(key)
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    for entry in sys.path:
        if entry.endswith(("site-packages", "dist-packages")) and Path(entry).is_dir():
            return Path(entry)
    return None


def font_dirs() -> list[Path]:
    """Directories to search for system-installed fonts, per platform."""
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", "C:/Windows"))
        return [
            windir / "Fonts",
            home / "AppData/Local/Microsoft/Windows/Fonts",
        ]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local/share/fonts"]


def find_font(*names: str) -> Path | None:
    """First matching font file from the platform font directories."""
    for directory in font_dirs():
        if not directory.is_dir():
            continue
        for name in names:
            direct = directory / name
            if direct.is_file():
                return direct
            for match in directory.rglob(name):
                return match
    return None


if __name__ == "__main__":
    cfg = load()
    print(f"config file : {CONFIG_PATH} ({'found' if CONFIG_PATH.is_file() else 'missing, using defaults'})")
    for field in ("source_dir", "song", "lyric_font_file", "lyric_font_family", "width", "height", "fps"):
        print(f"  {field:18s} {getattr(cfg, field)}")
    print(f"  site-packages      {site_packages()}")
