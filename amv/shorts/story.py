"""The story part of a Short: scenes played as they are, with the English dub
and its lines captioned, before (and after) the beat-cut montage.

A story segment is {"ep", "from", "to"} of the spec's series: the picture
runs at normal speed through the episode's own cuts, the audio is the
episode's English track (picked by language tag - its position differs per
release), and the English subtitle lines inside it become captions under the
picture. Under a story segment the song plays quietly; from the drop it is
full. Captions and the hook line at the top are one ASS file burned in by the
renderer, in fonts shipped with the project (assets/fonts, OFL).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from amv.core.config import ROOT
from amv.intro import dialogue

FONTS = ROOT / "assets" / "fonts"
CAPTION_FONT = "Anton"  # tall, condensed: a lot of words per line on a phone
HOOK_FONT = "Poppins Black"
YELLOW = "&H0000E6FF"  # ASS is BGR: #FFE600, the house thumbnail yellow


@lru_cache(maxsize=64)
def english_stream(file: str) -> int:
    """Index of the English audio track among the file's audio streams."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream_tags=language,title", "-of", "json", file], capture_output=True, text=True,
                         check=True).stdout
    streams = json.loads(out).get("streams", [])
    for k, s in enumerate(streams):
        tags = {key.lower(): str(v).lower() for key, v in s.get("tags", {}).items()}
        if tags.get("language") in ("eng", "en") or "english" in tags.get("title", ""):
            return k
    raise SystemExit(f"no English audio track in {file}")


def lines(series: str, episode: int, start: float, end: float) -> list[dict]:
    """English subtitle lines overlapping [start, end] (signs/song tracks are
    not the dialogue track; dialogue.extract keeps the fullest one)."""
    from amv.shorts.find import load_show

    e = next(x for x in load_show(series) if x.number == episode)
    out = []
    for ln in dialogue.extract(e):
        if ln["end"] > start + 0.15 and ln["start"] < end - 0.15:
            text = re.sub(r"\{[^}]*\}", "", ln["text"]).replace("\\N", " ").replace("\\n", " ")
            text = re.sub(r"\s+", " ", text).strip()
            if text and not re.fullmatch(r"[\[(♪].*[\])♪]?", text):  # [sighs], ♪ lyrics ♪
                out.append({"start": max(ln["start"], start), "end": min(ln["end"], end), "text": text})
    # the same line on two tracks/styles: keep one
    uniq: list[dict] = []
    for ln in out:
        if not uniq or ln["text"] != uniq[-1]["text"]:
            uniq.append(ln)
    return uniq


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _hook(text: str) -> str:
    """*word* -> yellow; the rest white."""
    return re.sub(r"\*([^*]+)\*", lambda m: f"{{\\c{YELLOW}}}{m.group(1)}{{\\c&H00FFFFFF}}", text)


def write_ass(path: Path, captions: list[dict], hook: str | None, seconds: float, width: int, height: int,
              picture_top: int, picture_bottom: int) -> Path:
    """Captions just under the picture, the hook just above it (both in the
    blurred band, clear of YouTube's own overlay at the bottom/right)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for f in FONTS.glob("*.ttf"):
        shutil.copy2(f, path.parent / f.name)
    cap_y = picture_bottom + 40
    hook_y = picture_top - 40
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{CAPTION_FONT},74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,6,2,8,90,90,0,1
Style: Hook,{HOOK_FONT},66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,3,2,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if hook:
        events.append(f"Dialogue: 1,{_ts(0)},{_ts(seconds)},Hook,,0,0,0,,"
                      f"{{\\an2\\pos({width // 2},{hook_y})\\fad(250,300)}}{_hook(hook)}")
    for c in captions:
        # a quick pop-in: starts a touch small, settles in 120 ms
        events.append(f"Dialogue: 0,{_ts(c['start'])},{_ts(c['end'])},Caption,,0,0,0,,"
                      f"{{\\an8\\pos({width // 2},{cap_y})\\fscx88\\fscy88\\t(0,120,\\fscx100\\fscy100)}}"
                      f"{c['text'].upper()}")
    path.write_text(head + "\n".join(events) + "\n", encoding="utf-8")
    return path
