"""Where finished Shorts go, laid out so they are easy to find and no two
files can ever collide:

    /mnt/datadisk/shorts/
      INDEX.md                                 every Short: number, date, anime, title, song, length
      S004_rezero_from_zero/
        S004_rezero_from_zero.mp4
        S004_rezero_from_zero_title.txt
        S004_rezero_from_zero_description.txt
        S004_rezero_from_zero_thumbnail.jpg
      by_anime/Re_Zero/S004_rezero_from_zero -> ../../S004_rezero_from_zero

A Short's number is given once, on its first delivery, and kept in the
committed catalog (amv/shorts/catalog/shorts.json) - it is never reused, so
every file name is unique even when files from many Shorts end up in one
folder (a download dir, a phone). Re-rendering a Short replaces its own files;
a spec that reuses another spec's name is refused.

    ./amv.sh short-index            # rebuild INDEX.md + by_anime/, move old unnumbered folders in
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from amv.shorts import catalog

ROOT = Path("/mnt/datadisk/shorts")
FILES = {"short.mp4": "{id}.mp4", "title.txt": "{id}_title.txt", "description.txt": "{id}_description.txt",
         "thumbnail.jpg": "{id}_thumbnail.jpg"}


def _shorts() -> dict:
    return catalog._read(catalog.CATALOG / "shorts.json")


def number(name: str, spec_path: str | None = None) -> int:
    """This Short's permanent number (given now if it has none)."""
    with catalog._LOCK:
        built = _shorts()
        entry = built.setdefault(name, {})
        if spec_path and entry.get("spec") and Path(entry["spec"]).resolve() != Path(spec_path).resolve():
            raise SystemExit(f"Short name {name!r} already belongs to {entry['spec']}; rename this spec")
        if not entry.get("number"):
            entry["number"] = 1 + max((v.get("number", 0) for v in built.values()), default=0)
        catalog._write(catalog.CATALOG / "shorts.json", built)
        return entry["number"]


def short_id(name: str, spec_path: str | None = None) -> str:
    return f"S{number(name, spec_path):03d}_{name}"


def deliver(name: str, spec_path: str, src: Path, root: Path = ROOT) -> Path:
    """Copy a render's files from tmp/shorts/NAME/ to its numbered folder."""
    sid = short_id(name, spec_path)
    dest = root / sid
    dest.mkdir(parents=True, exist_ok=True)
    for f, pattern in FILES.items():
        if (src / f).exists():
            shutil.copy2(src / f, dest / pattern.format(id=sid))
    index(root)
    return dest


def _duration(path: Path) -> str:
    from amv.core.ffmpeg_tools import probe_duration

    try:
        return f"{probe_duration(path):.0f}s"
    except Exception:  # noqa: BLE001 - a missing/odd file must not break the index
        return "?"


def index(root: Path = ROOT) -> Path:
    """INDEX.md and by_anime/ from the numbered folders present on disk."""
    built = _shorts()
    rows = []
    links = root / "by_anime"
    if links.exists():
        shutil.rmtree(links)
    for name, v in sorted(built.items(), key=lambda kv: kv[1].get("number", 10**6)):
        if not v.get("number"):
            continue
        sid = f"S{v['number']:03d}_{name}"
        folder = root / sid
        if not folder.exists():
            continue
        spec = json.loads(Path(v["spec"]).read_text(encoding="utf-8")) if v.get("spec") and Path(v["spec"]).exists() else {}
        title = (folder / f"{sid}_title.txt").read_text(encoding="utf-8").strip() \
            if (folder / f"{sid}_title.txt").exists() else spec.get("title", "")
        kind = "story + dub" if spec.get("story") else "montage"
        thumb = "yes" if (folder / f"{sid}_thumbnail.jpg").exists() else "-"
        rows.append(f"| {sid[:4]} | {v.get('built', '')} | {spec.get('anime', v.get('series', ''))} | {title} | "
                    f"{Path(v.get('song', '')).stem[:40]} | {_duration(folder / f'{sid}.mp4')} | {kind} | {thumb} | "
                    f"[{sid}]({sid}/) |")
        series = v.get("series") or spec.get("series", "other")
        (links / series).mkdir(parents=True, exist_ok=True)
        (links / series / sid).symlink_to(Path("..") / ".." / sid)
    text = ["# Shorts", "",
            "Every rendered Short, oldest first. Each folder holds the video, title, description and thumbnail,",
            "all named with the Short's number (never reused). `by_anime/` groups them per show.", "",
            "| # | built | anime | title | song | length | kind | thumbnail | folder |",
            "|---|---|---|---|---|---|---|---|---|", *rows, ""]
    (root / "INDEX.md").write_text("\n".join(text), encoding="utf-8")
    return root / "INDEX.md"


def migrate(root: Path = ROOT) -> None:
    """Old unnumbered delivery folders (root/NAME/short.mp4...) -> numbered ones, in build order."""
    built = _shorts()
    for name, _ in sorted(built.items(), key=lambda kv: (kv[1].get("built", ""), kv[1].get("number", 10**6))):
        old = root / name
        if old.is_dir() and not old.is_symlink():
            sid = short_id(name)
            dest = root / sid
            dest.mkdir(parents=True, exist_ok=True)
            for f, pattern in FILES.items():
                if (old / f).exists():
                    shutil.move(str(old / f), dest / pattern.format(id=sid))
            if not any(old.iterdir()):
                old.rmdir()
            print(f"  {name}/ -> {sid}/")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    migrate()
    print(f"Wrote {index()}")


if __name__ == "__main__":
    main()
