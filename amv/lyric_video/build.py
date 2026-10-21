"""A "lyrics channel" video from a spec: one still background, the song, every
lyric line timed to the singing, plus the house touches of that style -
title card, drifting sparkles, a one-frame flash on the strongest hits, and a
subscribe card with a cursor that clicks SUBSCRIBE and the bell.

    ./amv.sh lyric-video workspace/global/lyric_videos/NAME.json            # -> workspace/output/lyric_videos/NAME/
    ./amv.sh lyric-video SPEC --lines                                        # just print the timed lines
    ./amv.sh lyric-video SPEC --frames 1,16.5,40                             # finished stills, no video
    ./amv.sh lyric-video SPEC --from 10 --to 25                              # a quick part
    ./amv.sh lyric-video SPEC --thumb                                        # only the thumbnail

Spec keys (paths absolute or relative to the repo):
    song, background, title, artist        required ("artist" may be "")
    font                                   the lyric/title font file
    ui_font                                the subscribe card's font (default: Roboto from assets/fonts)
    lyrics / lyrics_file                   text, or a .txt beside the spec; default: the song's own lyrics tag
    channel {name, logo, focus [x, y], zoom, tagline, verified, at}
                                           the subscribe card (left out: no card); at = start second
    rough, bold                            hand-drawn edge wobble / stroke thickening for a clean font, px @1080 (0)
    track                                  letter spacing, a fraction of the cap height (0)
    engine                                 hyperframes (default: HTML/SVG/GSAP page rendered by the
                                           hyperframes tool, per-letter wiggle) or python (numpy compositor)
    wiggle                                 per-letter wiggle amplitude, px @1080 (3.5; hyperframes engine)
    flash                                  white veil at the strongest hits, 0-1 (0.1; 0 = off)
    size [w, h] (2560x1440), fps (30), sparkles (45), flashes (true), jobs (4; hyperframes: workers)
    title_seconds                          longest the opening title stays (3.0)
    meta {layout ("plain": lyrics + tags + keywords only), keywords, feat, subscribe_url, spotify_url,
          stream, follow {name: [links]}, about, links, submissions, hashtags}           the description's links and lines (missing links: <...>;
                                           spotify_url "" leaves the Spotify line out)

The lines shown, the ones left out (barely heard) and their cover are in
workspace/tmp/lyric_video/NAME/lines.json - check them before delivering."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from amv.core import paths
from amv.core.config import ROOT
from amv.core.ffmpeg_tools import choose_h264_encoder, h264_encoder_args, probe_duration, write_concat_file
from amv.lyric_video import look, timing

FADE_IN, FADE_OUT = 0.3, 0.2   # measured: lines fade in ~0.3 s, out ~0.2 s
LEAD = 0.12                    # text starts fading in this long before the first word
HOLD = 0.8                     # and stays at most this long after the last word
MIN_SHOW = 0.7
FLASH = 0.1                    # white veil at the strongest hit (spec "flash"); the reference's
FLASH_DECAY = 0.16             # +25/255 one-frame pop read as too much (2026-10-22): subtle, decaying
CARD_LEN = 5.35                # the subscribe card's whole animation, seconds


def _path(p: str) -> Path:
    q = Path(os.path.expandvars(p)).expanduser()
    return q if q.is_absolute() else ROOT / q


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec.setdefault("name", path.stem)
    for key in ("song", "background", "font"):
        if key not in spec:
            raise SystemExit(f"spec needs '{key}'")
    return spec


def ui_font(spec: dict) -> Path:
    if spec.get("ui_font"):
        return _path(spec["ui_font"])
    return ROOT / "assets" / "fonts" / "Roboto-VF.ttf"


def ease_out_back(x: float) -> float:
    c1 = 1.4
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


# ---- the plan: what is on screen when ------------------------------------------

def plan(spec: dict) -> dict:
    song = _path(spec["song"])
    cache = paths.LYRIC_VIDEO / spec["name"]
    if spec.get("lyrics_file"):
        text = _path(spec["lyrics_file"]).read_text(encoding="utf-8")
    else:
        text = spec.get("lyrics") or timing.song_lyrics(song)
    if not text:
        raise SystemExit("no lyrics: put them in the spec ('lyrics') or the song's lyrics tag")
    shown, dropped = timing.timed_lines(song, text, cache)
    duration = probe_duration(song)
    title_end = spec.get("title_seconds", 3.0)
    if shown:
        title_end = max(1.5, min(title_end, shown[0]["start"] - LEAD - 0.1))
    lines = []
    for k, line in enumerate(shown):
        a = max(line["start"] - LEAD, title_end + 0.05)
        nxt = shown[k + 1]["start"] - LEAD if k + 1 < len(shown) else duration
        b = min(line["end"] + HOLD, nxt - 0.02)
        b = max(b, min(a + MIN_SHOW, nxt - 0.02))
        if lines and a < lines[-1]["b"]:
            a = lines[-1]["b"]
        if b - a < 0.25:
            dropped.append({**line, "why": "no room on screen"})
            continue
        lines.append({"text": line["text"], "a": round(a, 3), "b": round(b, 3), "filled": line.get("filled", False)})
    return {"duration": duration, "title_end": title_end, "lines": lines, "dropped": dropped, "lyrics_text": text,
            "flashes": flashes(song, duration, spec.get("fps", 30)) if spec.get("flashes", True) else {},
            "card_at": (spec.get("channel") or {}).get("at", 15.0) if spec.get("channel") else None}


def flashes(song: Path, duration: float, fps: float) -> dict[int, float]:
    """{frame: strength 0..1}: the strongest onsets inside the loud parts,
    at most ~2 a second, like the reference's one-frame flashes in its drops."""
    import librosa

    y, sr = librosa.load(str(song), sr=22050, mono=True)
    hop = 512
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, fmax=2000)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0][:len(env)]
    loud = rms > np.percentile(rms, 55)
    peaks = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.2,
                                   wait=int(0.25 * sr / hop))
    peaks = [p for p in peaks if loud[p]]
    if not peaks:
        return {}
    vals = np.array([env[p] for p in peaks])
    cut = np.percentile(vals, 50)
    out = {}
    lo, hi = cut, vals.max()
    for p, v in zip(peaks, vals):
        if v >= cut:
            t = p * hop / sr
            out[int(round(t * fps))] = float(0.5 + 0.5 * (v - lo) / max(1e-6, hi - lo))
    return out


# ---- drawing --------------------------------------------------------------------

class Assets:
    def __init__(self, spec: dict, p: dict):
        self.w, self.h = spec.get("size", [2560, 1440])
        self.fps = spec.get("fps", 30)
        font = _path(spec["font"])
        self.bg = look.background(_path(spec["background"]), self.w, self.h)
        self.lines = [(ln["a"], ln["b"], look.lyric_sprite(ln["text"], font, self.w, self.h, spec.get("rough", 0.0),
                                          spec.get("bold", 0.0), spec.get("track", 0.0))) for ln in p["lines"]]
        self.title = look.title_sprite(spec.get("title", ""), spec.get("artist", ""), font, self.w, self.h,
                                       rough=spec.get("rough", 0.0), bold=spec.get("bold", 0.0),
                                       track=spec.get("track", 0.0))
        self.title_end = p["title_end"]
        self.flash = spec.get("flash", FLASH)
        self.flash_list = sorted((n / self.fps, v) for n, v in p["flashes"].items())
        self.parts = look.sparkles(spec.get("sparkles", 45), self.w, self.h)
        self.dots = {pp["r"]: look.dot_sprite(pp["r"]) for pp in self.parts}
        self.card_at = p["card_at"]
        if self.card_at is not None:
            ch = dict(spec["channel"])
            ch["logo"] = str(_path(ch["logo"]))
            c = look.card_states(ch, ui_font(spec), self.h)
            self.card = c
            self.card_sprites = {k: look.to_sprite(c[k]) for k in ("subscribe", "subscribed", "bell_on")}
            self.card_shadow = look.to_sprite(c["shadow"], *c["shadow_off"])
            self.cursor = look.to_sprite(c["cursor"])

    def frame(self, n: int) -> np.ndarray:
        t = n / self.fps
        f = self.bg.copy()
        veil = flash_at(self.flash_list, t, self.flash)
        if veil > 1 / 512:
            f *= 1 - veil
            f += 255 * veil
        look.sparkle_frame(f, self.parts, self.dots, t)
        cx, cy = self.w // 2, self.h // 2
        if t < self.title_end:
            look.blend(f, self.title, cx, int(self.h * 0.45), min(1.0, (self.title_end - t) / FADE_OUT))
        for a, b, s in self.lines:
            if a <= t < b:
                op = min(1.0, (t - a) / FADE_IN, (b - t) / FADE_OUT)
                look.blend(f, s, cx, cy, op)
        if self.card_at is not None and self.card_at <= t < self.card_at + CARD_LEN:
            self.draw_card(f, t - self.card_at)
        return f

    def draw_card(self, f: np.ndarray, t: float) -> None:
        """Measured on the reference (seconds from the card's start): slides up
        0-0.42 with an overshoot, cursor in 0.95-1.5, clicks SUBSCRIBE at 1.75,
        moves to the bell 2.2-3.0, clicks it at 3.6, leaves 4.2-4.6, card
        slides down 4.95-5.35."""
        c = self.card
        W, H = c["size"]
        u = self.h / 1080
        x0 = (self.w - W) // 2
        rest_y = self.h - int(look.CARD_BOTTOM * u) - H
        off = self.h - rest_y + 40 * u
        if t < 0.42:
            y = rest_y + off * (1 - ease_out_back(t / 0.42))
        elif t > 4.95:
            y = rest_y + off * smooth((t - 4.95) / 0.4) ** 2
        else:
            y = rest_y
        y = int(round(y))
        state = "subscribe" if t < 1.85 else ("subscribed" if t < 3.7 else "bell_on")
        look.blend(f, self.card_shadow, x0, y)
        look.blend(f, self.card_sprites[state], x0, y)
        bx, by = x0 + c["button"][0], y + c["button"][1]
        lx, ly = x0 + c["bell"][0], y + c["bell"][1]
        start = (x0 + W + 160 * u, y + H + 220 * u)
        exit_ = (x0 + W * 0.55, self.h + 120 * u)
        if t < 0.95 or t > 4.6:
            pos = None
        elif t < 1.5:
            k = smooth((t - 0.95) / 0.55)
            pos = (start[0] + (bx - start[0]) * k, start[1] + (by - start[1]) * k)
        elif t < 2.2:
            pos = (bx, by)
        elif t < 3.0:
            k = smooth((t - 2.2) / 0.8)
            pos = (bx + (lx - bx) * k, by + (ly - by) * k)
        elif t < 4.2:
            pos = (lx, ly)
        else:
            k = smooth((t - 4.2) / 0.4)
            pos = (lx + (exit_[0] - lx) * k, ly + (exit_[1] - ly) * k)
        for click, (px, py) in ((1.75, (bx, by)), (3.6, (lx, ly))):
            if click <= t < click + 0.35:
                k = (t - click) / 0.35
                ripple(f, px, py, (14 + 40 * k) * u, 0.45 * (1 - k))
        if pos:
            press = any(cl <= t < cl + 0.12 for cl in (1.75, 3.6))
            look.blend(f, self.cursor, int(pos[0] + (2 * u if press else 0)), int(pos[1] + (2 * u if press else 0)))


def flash_at(flash_list: list[tuple[float, float]], t: float, peak: float) -> float:
    """The white veil at time t: each hit (time, strength) peaks at peak *
    strength and decays with FLASH_DECAY (the same model as the HyperFrames page)."""
    v = 0.0
    for ft, s in flash_list:
        if ft > t:
            break
        if t - ft < 0.6:
            v = max(v, peak * s * math.exp(-(t - ft) / FLASH_DECAY))
    return v


def ripple(f: np.ndarray, x: float, y: float, r: float, alpha: float) -> None:
    n = int(r) + 2
    x0, y0 = int(x) - n, int(y) - n
    yy, xx = np.mgrid[y0:y0 + 2 * n + 1, x0:x0 + 2 * n + 1]
    d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    a = np.clip(r - d, 0, 1) * alpha
    H, W = f.shape[:2]
    ys, xs = slice(max(0, y0), min(H, y0 + 2 * n + 1)), slice(max(0, x0), min(W, x0 + 2 * n + 1))
    a = a[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0]
    region = f[ys, xs]
    region *= 1 - a[..., None]
    region += 200 * a[..., None]


# ---- render -----------------------------------------------------------------------

_ASSETS: Assets | None = None


def _render_part(job: tuple[int, int, str, str]) -> str:
    a, b, out, encoder = job
    A = _ASSETS
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{A.w}x{A.h}",
           "-r", str(A.fps), "-i", "-", *h264_encoder_args(encoder, "p7", 16), "-pix_fmt", "yuv420p",
           "-profile:v", "high", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(a, b):
        proc.stdin.write(np.clip(A.frame(n) + 0.5, 0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"encode failed for frames {a}-{b}")
    return out


def render(spec: dict, p: dict, out: Path, t0: float, t1: float, jobs: int) -> None:
    global _ASSETS
    _ASSETS = Assets(spec, p)
    A = _ASSETS
    n0, n1 = int(round(t0 * A.fps)), int(round(t1 * A.fps))
    encoder = choose_h264_encoder(spec.get("encoder", "auto"))
    work = paths.LYRIC_VIDEO / spec["name"] / "parts"
    work.mkdir(parents=True, exist_ok=True)
    jobs = max(1, min(jobs, (n1 - n0) // 30 or 1))
    edges = np.linspace(n0, n1, jobs + 1).astype(int)
    parts = [(int(edges[i]), int(edges[i + 1]), str(work / f"part{i:02d}.mp4"), encoder) for i in range(jobs)]
    print(f"Rendering {n1 - n0} frames at {A.w}x{A.h} in {jobs} part(s)...", flush=True)
    import importlib
    import multiprocessing as mp

    # ./amv.sh runs this file as __main__, whose functions can't be pickled by
    # name: hand the workers the importable module's, with the assets set there
    # (fork shares them; nothing big is pickled).
    mod = importlib.import_module("amv.lyric_video.build")
    mod._ASSETS = A
    with ProcessPoolExecutor(jobs, mp_context=mp.get_context("fork")) as ex:
        done = list(ex.map(mod._render_part, parts))
    concat = write_concat_file([Path(d) for d in done], work / "parts.txt")
    video = work / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
                    str(video)], check=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}",
                    "-i", str(_path(spec["song"])), "-map", "0:v:0", "-map", "1:a:0", "-map_chapters", "-1",
                    "-map_metadata", "-1", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(out)], check=True)


def hf_dir(spec: dict) -> Path:
    return paths.LYRIC_VIDEO / spec["name"] / "hyperframes"


def hf_render(spec: dict, p: dict, out: Path) -> None:
    """Write the HyperFrames composition and render it; the song is muxed back
    at AAC 320k (the page's own audio mix is not trusted for the delivery)."""
    from amv.lyric_video import hf_comp
    from amv.plugins.hyperframes.setup import cli

    comp = hf_dir(spec)
    hf_comp.build(spec, p, comp, _path)
    video = comp.parent / "hyperframes_video.mp4"
    cli("render", str(comp), "-o", str(video), "--fps", str(spec.get("fps", 30)), "--quality", "delivery",
        "--workers", str(spec.get("jobs", "auto")))
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(_path(spec["song"])),
                    "-map", "0:v:0", "-map", "1:a:0", "-map_chapters", "-1", "-map_metadata", "-1",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart",
                    "-shortest", str(out)], check=True)


def hf_frames(spec: dict, p: dict, times: list[float]) -> Path:
    from amv.lyric_video import hf_comp
    from amv.plugins.hyperframes.setup import cli

    comp = hf_dir(spec)
    hf_comp.build(spec, p, comp, _path)
    shots = paths.LYRIC_VIDEO / spec["name"] / "frames"
    cli("snapshot", str(comp), "--at", ",".join(f"{t:g}" for t in times), "--no-end", "-o", str(shots))
    return shots


def thumbnail(spec: dict, out: Path, size=(1280, 720)) -> None:
    """The reference thumbnail: the background, the title huge, the artist under it."""
    w, h = size
    f = look.background(_path(spec["background"]), w, h)
    s = look.title_sprite(spec.get("title", ""), spec.get("artist", ""), _path(spec["font"]), w, h,
                          title_cap=0.23, artist_cap=0.072, rough=spec.get("rough", 0.0),
                          bold=spec.get("bold", 0.0), track=spec.get("track", 0.0))
    look.blend(f, s, w // 2, int(h * 0.5))
    Image.fromarray(np.clip(f + 0.5, 0, 255).astype(np.uint8)).save(out, quality=95)


PLACEHOLDER = "<{}>"  # never a guessed link: the owner fills these in (spec "meta")


def _camel(text: str) -> str:
    words = re.sub(r"[^A-Za-z0-9 ]", "", text).split()
    return words[0] if len(words) == 1 else "".join(w[:1].upper() + w[1:] for w in words)


def lyric_sections(text: str, skip: set[str]) -> str:
    """The lyrics for a description: "[Verse 1 — Melodic, dark]" -> "Verse 1:",
    lines the video left out as unsung (stage directions, unheard ad-libs)
    dropped, and a section left empty by that dropped too."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        head = re.fullmatch(r"\[(.*)\]", line)
        if head:
            sections.append((re.split(r"\s+[—–-]\s+", head.group(1))[0].strip(), []))
        elif line and line.strip("()").strip() not in skip:
            sections[-1][1].append(line)
    blocks = [([f"{name}:"] if name else []) + body for name, body in sections if body]
    return "\n\n".join("\n".join(b) for b in blocks)


def tags_for(song: str, artists: list[str], feat: list[str]) -> list[str]:
    """YouTube tags in the lyrics-channel pattern (song, song lyrics, song + artists, ...)."""
    s = song.lower().replace("'", "").replace("’", "")
    a = [x.lower() for x in artists]
    f = [x.lower() for x in feat]
    names = " ".join(a)
    out = [s, f"{s} lyrics"]
    for k in range(1, len(a) + 1):
        out.append(f"{s} lyrics {' '.join(a[:k])}")
    for k in range(1, len(a) + 1):
        out += [f"{s} {' '.join(a[:k])}", f"{s} {' '.join(a[:k])} lyrics"]
    if f:
        out += [f"{s} {names} {' '.join(f)}", f"{s} {names} {' '.join(f)} lyrics"]
    out += a + f
    if len(a) > 1:
        out += [names, " ".join(reversed(a))]
    out += [f"{names} {s}", f"{names} {s} lyrics"]
    if f:
        out += [f"{names} {' '.join(f)} {s}", f"{names} {' '.join(f)} {s} lyrics"]
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    # YouTube's tag field holds 500 characters
    keep, total = [], 0
    for t in uniq:
        if total + len(t) + 1 > 500:
            break
        keep.append(t)
        total += len(t) + 1
    return keep


def meta(spec: dict, p: dict, out_dir: Path) -> dict[str, Path]:
    """Title, description and tags in the lyrics-channel layout (the Vibe Guide
    "Headlights (Lyrics)" upload): title lines, subscribe / Spotify /
    notifications, stream, follow blocks, sectioned lyrics, channel blurb,
    hashtags, tags. Links come only from spec "meta"; missing ones are <...>."""
    song = spec.get("title", "")
    artists = [x.strip() for x in re.split(r",\s*", spec.get("artist", "")) if x.strip()]
    m = spec.get("meta", {})
    feat = m.get("feat", [])
    by = ", ".join(artists)
    ft = f" ft. {', '.join(feat)}" if feat else ""
    title = (f"{by} - {song} (Lyrics){ft}" if by else f"{song} (Lyrics){ft}")[:100]
    second = f"{song} (Lyrics) - {by}{ft}" if by else ""
    ch = spec.get("channel") or {}
    channel = ch.get("name", by)
    follow = m.get("follow") or {name: [] for name in artists + feat}
    skip = {d["text"] for d in p["dropped"] if d.get("cover", 0) == 0}
    tags = tags_for(song, artists, feat)
    hashtags = [f"#{_camel(x)}" for x in artists + [song] + feat] + ["#Lyrics"] + [f"#{h.lstrip('#')}" for h in m.get("hashtags", [])]
    if m.get("layout") == "plain":
        # just the lyrics, the tags and related keywords - no links, no channel lines (owner, 2026-10-22)
        keywords = list(dict.fromkeys([*m.get("keywords", []), *tags]))
        lines = [title, "", "🎤 Lyrics:", lyric_sections(p["lyrics_text"], skip), "",
                 " ".join(dict.fromkeys(hashtags)), "", "Tags:", *tags, "", "Keywords:", ", ".join(keywords)]
        return _write_meta(spec, out_dir, title, lines, tags)
    lines = [title, second, "", "",
             f"For more quality music subscribe here ➡ {m.get('subscribe_url') or PLACEHOLDER.format('YOUR CHANNEL SUBSCRIBE LINK')}"]
    if m.get("spotify_url") != "":  # absent: placeholder; "" (no Spotify): line left out
        lines.append(f"We're on Spotify ➡ {m.get('spotify_url') or PLACEHOLDER.format('SPOTIFY LINK')}")
    lines += ["🔔 Turn on notifications to stay updated with new uploads!", "",
              "✖ Stream / Download:", m.get("stream", "Soon"), ""]
    for name, links in follow.items():
        lines.append(f"✖ Follow {name}")
        lines += [f"  {x}" for x in links] or [f"  {PLACEHOLDER.format(name + ' SOCIAL LINKS')}"]
        lines.append("")
    lines += ["🎤  Lyrics:", lyric_sections(p["lyrics_text"], skip), ""]
    about = m.get("about")
    lines.append(f"{channel.upper()} - {about}" if about else f"{channel.upper()} - {PLACEHOLDER.format('CHANNEL TAGLINE')}")
    lines += [f"➡ {x}" for x in m.get("links", [])] or [f"➡ {PLACEHOLDER.format('CHANNEL LINKS')}"]
    if m.get("submissions"):
        lines += ["", f"Send your submissions: {m['submissions']}"]
    lines += ["", " ".join(dict.fromkeys(hashtags)), "", "Tags:", *tags]
    return _write_meta(spec, out_dir, title, lines, tags)


def _write_meta(spec: dict, out_dir: Path, title: str, lines: list[str], tags: list[str]) -> dict[str, Path]:
    name = spec["name"]
    files = {"title": out_dir / f"{name}_title.txt", "description": out_dir / f"{name}_description.txt",
             "tags": out_dir / f"{name}_tags.txt"}
    files["title"].write_text(title + "\n", encoding="utf-8")
    files["description"].write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    files["tags"].write_text(", ".join(tags) + "\n", encoding="utf-8")
    old = out_dir / f"{name}_title_description.txt"
    if old.exists():
        old.unlink()
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--lines", action="store_true", help="print the timed lines and stop")
    ap.add_argument("--frames", help="comma-separated seconds: finished stills only")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--thumb", action="store_true", help="only the thumbnail")
    ap.add_argument("--meta", action="store_true", help="only the title, description and tags files")
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args()
    spec = load_spec(args.spec)
    out_dir = paths.LYRIC_VIDEOS_OUT / spec["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.thumb:
        thumbnail(spec, out_dir / f"{spec['name']}_thumbnail.jpg")
        print(out_dir / f"{spec['name']}_thumbnail.jpg")
        return
    p = plan(spec)
    if args.meta:
        for path in meta(spec, p, out_dir).values():
            print(path)
        return
    if args.lines or args.frames:
        for ln in p["lines"]:
            print(f"{ln['a']:7.2f} {ln['b']:7.2f}  {ln['text']}" + ("   [filled: not heard, placed on the sung gap]" if ln["filled"] else ""))
        for ln in p["dropped"]:
            print(f"  left out (cover {ln.get('cover')}): {ln['text']}" + (f" - {ln['why']}" if ln.get("why") else ""))
        print(f"title until {p['title_end']:.2f}s, {len(p['flashes'])} flashes, card at {p['card_at']}")
    if args.lines:
        return
    engine = spec.get("engine", "hyperframes")
    if args.frames and engine == "hyperframes":
        print(hf_frames(spec, p, [float(x) for x in args.frames.split(",")]))
        return
    if args.frames:
        global _ASSETS
        _ASSETS = Assets(spec, p)
        shots = paths.LYRIC_VIDEO / spec["name"] / "frames"
        shots.mkdir(parents=True, exist_ok=True)
        for t in (float(x) for x in args.frames.split(",")):
            img = np.clip(_ASSETS.frame(int(round(t * _ASSETS.fps))) + 0.5, 0, 255).astype(np.uint8)
            path = shots / f"{t:07.2f}.png"
            Image.fromarray(img).save(path)
            print(path)
        return
    t1 = args.t1 if args.t1 is not None else p["duration"]
    whole = args.t0 == 0 and args.t1 is None
    out = out_dir / (f"{spec['name']}.mp4" if whole else f"{spec['name']}_{args.t0:g}-{t1:g}.mp4")
    if engine == "hyperframes":
        if not whole:
            raise SystemExit("--from/--to are for the python engine; with hyperframes use --frames, or the "
                             "studio: hyperframes preview " + str(hf_dir(spec)))
        hf_render(spec, p, out)
    else:
        render(spec, p, out, args.t0, t1, args.jobs or spec.get("jobs", 4))
    if whole:
        thumbnail(spec, out_dir / f"{spec['name']}_thumbnail.jpg")
        meta(spec, p, out_dir)
    print(out)


if __name__ == "__main__":
    main()
