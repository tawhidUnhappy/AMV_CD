"""Title, description and tags for a full AMV (2026-10-20 research; the amv-packaging skill
has the reasons). Writes into the spec's "out": title.txt (the pick), titles.txt
(candidates with lengths), description.txt, tags.txt.

    ./amv.sh amv-meta SPEC.json

Spec (a "package" block in an edit spec works too):
    {"out": "workspace/output/edits/NAME",
     "anime": ["Re:Zero - Starting Life in Another World"], "anime_short": "Re:Zero",
     "characters": ["Subaru", "Emilia", "Rem"],
     "song": {"title": "Rewind", "artist": null, "generator": "ACE-Step 1.5"},  # artist null + generator = original AI song
     "hook": "He Died 100 Times For Her",          # optional: a story hook for the title
     "style": "phonk", "channel": null,              # "channel": your AMV tag, e.g. "Toxic"
     "rights": "White Fox / Kadokawa",               # optional; never guessed
     "extra_tags": []}

Never invents a credit: a song with neither "artist" nor "generator" gets an
<ARTIST> placeholder and a warning."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_TITLE = 100
SHOWN = 55  # what a phone shows of a title in the feed/search (40-60 by source)
MAX_TAGS = 500


def song_credit(song: dict) -> tuple[str, str, bool]:
    """(title text, description line, placeholder?)"""
    title = song.get("title") or "<SONG>"
    if song.get("artist"):
        return f"{song['artist']} - {title}", f"🎧 Song: {song['artist']} - {title}", False
    if song.get("generator"):
        return title, (f"🎧 Music: \"{title}\" - an original track made for this edit "
                       f"(AI-generated with {song['generator']}, lyrics written for it)."), False
    return f"<ARTIST> - {title}", f"🎧 Song: <ARTIST> - {title}", True


def titles(spec: dict) -> list[str]:
    short = spec.get("anime_short") or spec["anime"][0]
    song, _, _ = song_credit(spec.get("song", {}))
    name = spec.get("song", {}).get("title", "")
    chars = spec.get("characters", [])
    hook, style = spec.get("hook"), spec.get("style")
    tag = f"{spec['channel']} AMV" if spec.get("channel") else "AMV"
    out = []
    if hook:
        out.append(f"{hook} | {short} {tag} - {name}")
    out.append(f"{short} {tag} - {song}")
    if chars:
        out.append(f"{chars[0]} - {name} Edit | {short} {tag}")
    if style:
        out.append(f"{short} - {name} [{style.title()} {tag}]")
    out.append(f"{song} ({tag})")
    seen, good = set(), []
    for t in out:
        t = re.sub(r"\s+", " ", t).strip()
        if t not in seen and len(t) <= MAX_TITLE and len(re.findall(r"[!?]", t)) <= 1:
            seen.add(t)
            good.append(t)
    return good


def description(spec: dict) -> tuple[str, bool]:
    short = spec.get("anime_short") or spec["anime"][0]
    _, line, placeholder = song_credit(spec.get("song", {}))
    name = spec.get("song", {}).get("title", "")
    style = f"{spec['style']} " if spec.get("style") else ""
    chars = spec.get("characters", [])
    who = f" - {', '.join(chars[:3])}" if chars else ""
    first = f"{short} {style}AMV to \"{name}\"{who}."  # the first ~150 chars: what this is
    parts = [first[:150], "", line, "🎬 Anime: " + " / ".join(f"{a} (AMV)" for a in spec["anime"])]
    if spec.get("notes"):
        parts.append(f"✂️ {spec['notes']}")
    rights = spec.get("rights")
    parts += ["", (f"Anime footage © {rights}." if rights else "Anime footage © its respective owners.")
              + " A non-commercial fan edit; no ownership of the footage is claimed.", ""]
    tags = [f"#{t}" for t in ("amv", re.sub(r"[^a-z0-9]", "", short.lower()), "animeedit")]
    parts.append(" ".join(tags))  # YouTube shows the first three hashtags above the title
    return "\n".join(parts) + "\n", placeholder


def tags(spec: dict) -> list[str]:
    short = spec.get("anime_short") or spec["anime"][0]
    name = spec.get("song", {}).get("title", "")
    style = spec.get("style")
    cand = [f"{short} amv", f"{short} edit", *(f"{c} edit" for c in spec.get("characters", [])),
            *spec["anime"], short, "amv", "anime edit", "anime music video",
            *([f"{style} edit", f"{style} amv"] if style else []), f"{name} amv" if name else "",
            *spec.get("extra_tags", [])]
    out, total = [], 0
    for t in cand:
        t = t.strip()
        if t and t.lower() not in {o.lower() for o in out} and total + len(t) + 1 <= MAX_TAGS:
            out.append(t)
            total += len(t) + 1
    return out


def write(spec: dict) -> None:
    out = Path(spec.get("out", "."))
    out.mkdir(parents=True, exist_ok=True)
    ts = titles(spec)
    (out / "title.txt").write_text(ts[0] + "\n", encoding="utf-8")
    (out / "titles.txt").write_text("".join(f"{len(t):3d}  {t}\n" for t in ts), encoding="utf-8")
    desc, placeholder = description(spec)
    (out / "description.txt").write_text(desc, encoding="utf-8")
    (out / "tags.txt").write_text(", ".join(tags(spec)) + "\n", encoding="utf-8")
    for t in ts:
        flag = "" if len(t) <= SHOWN else f"  (phones show ~{SHOWN}: \"{t[:SHOWN]}...\")"
        print(f"{len(t):3d}  {t}{flag}")
    print(f"Wrote {out}/title.txt, titles.txt, description.txt, tags.txt", flush=True)
    if placeholder:
        print("WARNING: the song's artist is unknown - fill in <ARTIST> before publishing.", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    spec = json.loads(ap.parse_args().spec.read_text(encoding="utf-8"))
    write(spec.get("package", spec))


if __name__ == "__main__":
    main()
