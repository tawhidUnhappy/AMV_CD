"""The lyric video as a HyperFrames composition (HTML + SVG + GSAP), rendered
by the hyperframes tool plug-in - the default engine of `lyric-video`.

Layout is decided here, in Python, from the same font file the page loads:
every letter is its own SVG <text> at a measured x and baseline, so the page
needs no text layout and each letter can wiggle on its own (the reference's
per-character wiggle: ±3-5 px @1080, ~1 cycle a second, letters independent).

All continuous motion (wiggle, sparkles, the flash, line fades) is one
function of time run from a single driver tween's onUpdate (the onUpdate-proxy
pattern of the hyperframes-animation skill) - seek-safe by construction. The
subscribe card is plain GSAP tweens."""

from __future__ import annotations

import html
import json
import math
import shutil
from pathlib import Path

import numpy as np

from amv.lyric_video import look

CARD_LEN = 5.35


def _measure(text: str, font) -> list[tuple[str, float]]:
    """(char, x offset) of each non-space character of one row."""
    out = []
    for i, ch in enumerate(text):
        if ch.strip():
            out.append((ch, font.getlength(text[:i])))
    return out


def layout_block(rows: list[str], font, cap: float, pitch: float, cx: float, cy: float) -> list[dict]:
    """Letters of rows centred on (cx, cy) - cy is the middle of the caps."""
    first = cy - (pitch * (len(rows) - 1) + cap) / 2 + cap
    letters = []
    for k, row in enumerate(rows):
        x0 = cx - font.getlength(row) / 2
        for ch, dx in _measure(row, font):
            letters.append({"ch": ch, "x": round(x0 + dx, 2), "y": round(first + k * pitch, 2)})
    return letters


def lyric_layout(text: str, font_path: Path, w: int, h: int, case: str = "upper") -> tuple[list[dict], float]:
    """(letters, font px) for one lyric line - the same wrap/size/pitch rules
    as the Python renderer (look.lyric_sprite)."""
    cap = look.CAP * h
    font = look.font_for_cap(font_path, cap)
    rows = look.wrap(look.displayable(look.cased(text, case), font), font, look.WRAP_W * w)
    widest = max(font.getlength(r) for r in rows)
    if widest > look.MAX_W * w:
        cap *= look.MAX_W * w / widest
        font = look.font_for_cap(font_path, cap)
    base = font.getbbox("H")[3]
    desc = max((font.getbbox(ch)[3] - base for r in rows[:-1] for ch in set(r) if ch.strip()), default=0)
    pitch = max(cap * look.PITCH, cap + desc + cap * 0.1)
    return layout_block(rows, font, cap, pitch, w / 2, h / 2), font.font.size


def title_layout(title: str, artist: str, font_path: Path, w: int, h: int, case: str = "upper",
                 title_cap: float = 0.27, artist_cap: float = 0.072, max_w: float = 0.86, cy: float = 0.45):
    cap = title_cap * h
    font = look.font_for_cap(font_path, cap)
    title = look.displayable(look.cased(title, case), font)
    if font.getlength(title) > max_w * w:
        cap *= max_w * w / font.getlength(title)
        font = look.font_for_cap(font_path, cap)
    blocks = []
    acap = min(artist_cap * h, cap * 0.4) if artist else 0
    gap = cap * 0.12
    total = cap + (gap + acap if artist else 0)
    top = cy * h - total / 2
    blocks.append((layout_block([title], font, cap, cap, w / 2, top + cap / 2), font.font.size))
    if artist:
        afont = look.font_for_cap(font_path, acap)
        a = look.displayable(look.cased(artist, case), afont)
        if afont.getlength(a) > max_w * w:
            acap *= max_w * w / afont.getlength(a)
            afont = look.font_for_cap(font_path, acap)
        blocks.append((layout_block([a], afont, acap, acap, w / 2, top + cap + gap + acap / 2), afont.font.size))
    return blocks


def _svg_text(letters: list[dict], size: float, gid: str, w: int, h: int, seeds: bool, rng) -> tuple[str, list]:
    parts, meta = [], []
    for L in letters:
        parts.append(f'<text x="{L["x"]}" y="{L["y"]}" font-size="{size}">{html.escape(L["ch"])}</text>')
        if seeds:
            meta.append([round(float(v), 3) for v in
                         (*rng.uniform(0.35, 1.25, 4), *rng.uniform(0, 2 * math.pi, 4))])
    return (f'<svg class="txt" viewBox="0 0 {w} {h}" width="{w}" height="{h}"><g id="{gid}">'
            + "".join(parts) + "</g></svg>"), meta


def build(spec: dict, plan: dict, out_dir: Path, resolve) -> Path:
    """Write the composition folder; return index.html."""
    w, h = spec.get("size", [2560, 1440])
    fps = spec.get("fps", 30)
    u = h / 1080
    dur = plan["duration"]
    font_path = resolve(spec["font"])
    out_dir.mkdir(parents=True, exist_ok=True)
    from amv.lyric_video.build import song_file, ui_font
    assets = {"bg": resolve(spec["background"]), "font": font_path, "song": song_file(spec)}
    assets["ui"] = ui_font(spec)
    ch = dict(spec.get("channel") or {})
    if ch:
        assets["logo"] = resolve(ch["logo"])
    names = {}
    for key, src in assets.items():
        name = f"{key}{src.suffix.lower()}"
        shutil.copyfile(src, out_dir / name)
        names[key] = name
    from amv.plugins.hyperframes.setup import gsap_file
    shutil.copyfile(gsap_file(), out_dir / "gsap.min.js")

    style = spec.get("style", {})
    fill = style.get("fill", "#ffffff")
    rim = style.get("rim", "rgba(22,12,38,0.92)")
    shadow = style.get("shadow", "rgba(24,12,40,0.85)")
    glow = f" drop-shadow(0 0 {14 * u:.1f}px {style['glow']})" if style.get("glow") else ""
    rng = np.random.default_rng(spec.get("seed", 11))
    clips, lines_js = [], []
    for k, ln in enumerate(plan["lines"]):
        letters, size = lyric_layout(ln["text"], font_path, w, h, style.get("case", "upper"))
        svg, seeds = _svg_text(letters, size, f"l{k}", w, h, True, rng)
        a, b = ln["a"], ln["b"]
        clips.append(f'<div id="c{k}" class="clip layer" data-start="{a:.3f}" data-duration="{b - a:.3f}" '
                     f'data-track-index="3">{svg}</div>')
        lines_js.append({"g": f"l{k}", "a": a, "b": b, "s": seeds})
    title_svgs = []
    for j, (letters, size) in enumerate(title_layout(spec.get("title", ""), spec.get("artist", ""), font_path, w, h,
                                                             style.get("case", "upper"))):
        svg, _ = _svg_text(letters, size, f"t{j}", w, h, False, rng)
        title_svgs.append(svg)
    title_clip = (f'<div id="title" class="clip layer" data-start="0" data-duration="{plan["title_end"]:.3f}" '
                  f'data-track-index="2"><div id="titleIn">{"".join(title_svgs)}</div></div>')
    parts = look.sparkles(spec.get("sparkles", 45), w, h)
    sparks = [[round(p["x"], 1), round(p["y"], 1), round(p["vx"], 2), round(p["vy"], 2), round(p["r"], 2),
               round(p["tw"], 3), round(p["ph"], 3), round(p["base"], 3)] for p in parts]
    spark_divs = "".join(f'<div class="sp" id="s{i}" style="width:{2 * s[4]:.1f}px;height:{2 * s[4]:.1f}px;'
                         f'margin:-{s[4]:.1f}px 0 0 -{s[4]:.1f}px"></div>' for i, s in enumerate(sparks))
    flashes = sorted((n / fps, s) for n, s in plan["flashes"].items())
    data = {"lines": lines_js, "sparks": sparks, "flashes": [[round(t, 3), round(s, 3)] for t, s in flashes],
            "titleEnd": plan["title_end"], "W": w, "H": h, "amp": spec.get("wiggle", 3.5) * u,
            "fadeIn": 0.3, "fadeOut": 0.2, "flash": spec.get("flash", 0.1), "flashDecay": 0.16, "dur": dur}
    card_html, card_js = _card(ch, names, plan.get("card_at"), w, h, u) if ch and plan.get("card_at") is not None \
        else ("", "")

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={w}, height={h}" />
<title>{html.escape(spec.get('title', 'Lyric video'))}</title>
<script src="gsap.min.js"></script>
<style>
@font-face {{ font-family: "LyricFont"; src: url("{names['font']}"); }}
@font-face {{ font-family: "CardFont"; src: url("{names['ui']}"); font-weight: 100 900; }}
body {{ margin: 0; background: #000; }}
#root {{ position: relative; width: 100%; height: 100%; overflow: hidden; }}
.layer {{ position: absolute; inset: 0; }}
#bg {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
#flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; }}
.sp {{ position: absolute; left: 0; top: 0; border-radius: 50%; background: #fff;
      box-shadow: 0 0 {3 * u:.1f}px rgba(255,255,255,0.6); opacity: 0; }}
svg.txt {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible;
          filter: drop-shadow(0 0 {1.6 * u:.1f}px {rim}) drop-shadow({3 * u:.1f}px {4 * u:.1f}px {4.5 * u:.1f}px {shadow}){glow}; }}
svg.txt text {{ font-family: "LyricFont"; fill: {fill}; stroke: {rim}; stroke-width: {3.2 * u:.1f}px;
               stroke-linejoin: round; paint-order: stroke fill; }}
{_card_css(u) if card_html else ''}
</style>
</head>
<body>
<div id="root" data-composition-id="lyric" data-start="0" data-width="{w}" data-height="{h}" data-fps="{fps}"
     data-duration="{dur:.3f}">
  <img id="bg" src="{names['bg']}" alt="" />
  <div id="flash"></div>
  <div id="sparks" class="layer">{spark_divs}</div>
  {title_clip}
  {''.join(clips)}
  {card_html}
  <audio id="song" src="{names['song']}" data-start="0" data-duration="{dur:.3f}" data-track-index="0"></audio>
</div>
<script>
const D = {json.dumps(data, separators=(",", ":"))};
const TAU = Math.PI * 2;
const flashEl = document.getElementById("flash");
const sparkEls = D.sparks.map((_, i) => document.getElementById("s" + i));
const lines = D.lines.map(L => ({{...L, el: document.getElementById(L.g), kids: Array.from(document.getElementById(L.g).children)}}));
const titleEl = document.getElementById("titleIn");
const mod = (a, n) => ((a % n) + n) % n;
function frame(t) {{
  let f = 0;
  for (const [ft, s] of D.flashes) {{
    if (ft > t) break;
    if (t - ft < 0.6) f = Math.max(f, D.flash * s * Math.exp(-(t - ft) / D.flashDecay));
  }}
  flashEl.style.opacity = f.toFixed(4);
  D.sparks.forEach((p, i) => {{
    const y = mod(p[1] + p[3] * t, D.H + 40) - 20, x = mod(p[0] + p[2] * t, D.W);
    sparkEls[i].style.transform = `translate(${{x.toFixed(1)}}px, ${{y.toFixed(1)}}px)`;
    sparkEls[i].style.opacity = (p[7] * (0.7 + 0.3 * Math.sin(TAU * p[5] * t + p[6]))).toFixed(3);
  }});
  for (const L of lines) {{
    if (t < L.a - 0.05 || t > L.b + 0.05) continue;
    L.el.style.opacity = Math.max(0, Math.min(1, (t - L.a) / D.fadeIn, (L.b - t) / D.fadeOut)).toFixed(3);
    L.kids.forEach((el, k) => {{
      const s = L.s[k];
      const dx = D.amp * (0.6 * Math.sin(TAU * s[0] * t + s[4]) + 0.4 * Math.sin(TAU * s[1] * t + s[5]));
      const dy = D.amp * (0.6 * Math.sin(TAU * s[2] * t + s[6]) + 0.4 * Math.sin(TAU * s[3] * t + s[7]));
      el.setAttribute("transform", `translate(${{dx.toFixed(2)}} ${{dy.toFixed(2)}})`);
    }});
  }}
  if (titleEl) titleEl.style.opacity = Math.max(0, Math.min(1, (D.titleEnd - t) / D.fadeOut)).toFixed(3);
}}
const tl = gsap.timeline({{ paused: true }});
const clock = {{ t: 0 }};
tl.fromTo(clock, {{ t: 0 }}, {{ t: D.dur, duration: D.dur, ease: "none", onUpdate: () => frame(clock.t) }}, 0);
{card_js}
frame(0);
window.__timelines["lyric"] = tl;
</script>
</body>
</html>
"""
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def _card_css(u: float) -> str:
    return f"""
#card {{ position: absolute; border-radius: {14 * u:.1f}px; background: #fff;
        box-shadow: 0 {6 * u:.1f}px {24 * u:.1f}px rgba(0,0,0,0.28); font-family: "CardFont"; }}
#card .av {{ position: absolute; border-radius: 50%; overflow: hidden; }}
#card .av img {{ width: 100%; height: 100%; object-fit: cover; }}
#card .name {{ position: absolute; font-weight: 500; color: #0f0f0f; white-space: nowrap; }}
#card .tag {{ position: absolute; font-weight: 400; color: #6e6e6e; white-space: nowrap; }}
#card .btn {{ position: absolute; border-radius: {4 * u:.1f}px; display: flex; align-items: center;
             justify-content: center; font-weight: 500; letter-spacing: {0.5 * u:.1f}px; }}
#btnSub {{ background: #e60012; color: #fff; }}
#btnDone {{ background: #ececec; color: #6e6e6e; opacity: 0; }}
#card svg.bell {{ position: absolute; overflow: visible; }}
#bellOn {{ opacity: 0; }}
.rip {{ position: absolute; border-radius: 50%; background: rgba(200,200,200,1); opacity: 0; }}
#cursor {{ position: absolute; left: 0; top: 0; opacity: 0; }}
"""


def _card(ch: dict, names: dict, at: float, w: int, h: int, u: float) -> tuple[str, str]:
    """The subscribe card (measured on the reference, seconds from `at`): slides
    up 0-0.42 with an overshoot, cursor in 0.95-1.5, clicks SUBSCRIBE at 1.75,
    to the bell 2.2-3.0, clicks it at 3.6 (it rings), leaves 4.2-4.6, slides
    down 4.95-5.35."""
    cw, chh = 900 * u, 190 * u
    cx, cy = (w - cw) / 2, h - look.CARD_BOTTOM * u - chh
    av = 130 * u
    fx, fy = ch.get("focus", [0.5, 0.5])
    zoom = ch.get("zoom", 1.0)
    tagline = ch.get("tagline", "")
    name_y = chh / 2 - (30 * u if tagline else 0)
    bw, bh = 220 * u, 58 * u
    bx, by = cw - 30 * u - bw - 60 * u, (chh - bh) / 2
    bell = 44 * u
    lx, ly = bx + bw + 22 * u, (chh - bell) / 2
    btn_font = 26 * u
    bell_path = ("M22 4 C30 4 34 10 34 18 L35 30 L40 36 L4 36 L9 30 L10 18 C10 10 14 4 22 4 Z "
                 "M17 38 A5 5 0 0 0 27 38 Z")
    card = f"""
<div id="cardClip" class="clip layer" data-start="{at:.3f}" data-duration="{CARD_LEN}" data-track-index="5">
  <div id="card" style="left:{cx:.1f}px;top:{cy:.1f}px;width:{cw:.1f}px;height:{chh:.1f}px">
    <div class="av" style="left:{30 * u:.1f}px;top:{(chh - av) / 2:.1f}px;width:{av:.1f}px;height:{av:.1f}px">
      <img src="{names['logo']}" alt="" style="object-position:{fx * 100:.0f}% {fy * 100:.0f}%;transform-origin:{fx * 100:.0f}% {fy * 100:.0f}%;scale:{zoom}" />
    </div>
    <div class="name" style="left:{30 * u + av + 26 * u:.1f}px;top:{name_y - 30 * u:.1f}px;font-size:{50 * u:.1f}px;line-height:{60 * u:.1f}px">{html.escape(ch['name'])}</div>
    {f'<div class="tag" style="left:{30 * u + av + 26 * u:.1f}px;top:{chh / 2 + 10 * u:.1f}px;font-size:{26 * u:.1f}px;line-height:{34 * u:.1f}px">{html.escape(tagline)}</div>' if tagline else ''}
    <div id="btnSub" class="btn" style="left:{bx:.1f}px;top:{by:.1f}px;width:{bw:.1f}px;height:{bh:.1f}px;font-size:{btn_font:.1f}px">SUBSCRIBE</div>
    <div id="btnDone" class="btn" style="left:{bx:.1f}px;top:{by:.1f}px;width:{bw:.1f}px;height:{bh:.1f}px;font-size:{btn_font:.1f}px">SUBSCRIBED</div>
    <svg id="bell" class="bell" viewBox="0 0 44 44" style="left:{lx:.1f}px;top:{ly:.1f}px;width:{bell:.1f}px;height:{bell:.1f}px">
      <path id="bellOff" d="{bell_path}" fill="none" stroke="#606060" stroke-width="3.2" stroke-linejoin="round" />
      <g id="bellOn"><path d="{bell_path}" fill="#282828" />
        <path d="M2 14 Q0 20 2 26 M42 14 Q44 20 42 26" fill="none" stroke="#282828" stroke-width="3" stroke-linecap="round" /></g>
    </svg>
    <div id="rip1" class="rip" style="left:{bx + bw / 2 - 54 * u:.1f}px;top:{by + bh / 2 - 54 * u:.1f}px;width:{108 * u:.1f}px;height:{108 * u:.1f}px"></div>
    <div id="rip2" class="rip" style="left:{lx + bell / 2 - 54 * u:.1f}px;top:{ly + bell / 2 - 54 * u:.1f}px;width:{108 * u:.1f}px;height:{108 * u:.1f}px"></div>
  </div>
  <svg id="cursor" viewBox="0 0 24 32" width="{36 * u:.1f}" height="{48 * u:.1f}">
    <path d="M1 1 L1 25 L7 19.5 L11 29 L15 27.3 L11 18 L19 18 Z" fill="#fff" stroke="#000" stroke-width="1.6" stroke-linejoin="round" />
  </svg>
</div>"""
    off = h - cy + 40 * u
    bxa, bya = cx + bx + bw / 2, cy + by + bh / 2
    lxa, lya = cx + lx + bell / 2, cy + ly + bell / 2
    sx, sy = cx + cw + 160 * u, cy + chh + 220 * u
    ex, ey = cx + cw * 0.55, h + 120 * u
    js = f"""
tl.fromTo("#card", {{ y: {off:.1f} }}, {{ y: 0, duration: 0.42, ease: "back.out(1.4)" }}, {at:.3f});
tl.to("#card", {{ y: {off:.1f}, duration: 0.4, ease: "power2.in" }}, {at + 4.95:.3f});
tl.set("#cursor", {{ x: {sx:.1f}, y: {sy:.1f}, opacity: 0 }}, 0);
tl.set("#cursor", {{ opacity: 1 }}, {at + 0.95:.3f});
tl.to("#cursor", {{ x: {bxa:.1f}, y: {bya:.1f}, duration: 0.55, ease: "power2.inOut" }}, {at + 0.95:.3f});
tl.to("#cursor", {{ scale: 0.86, duration: 0.06, yoyo: true, repeat: 1, transformOrigin: "0% 0%" }}, {at + 1.72:.3f});
tl.fromTo("#rip1", {{ scale: 0, opacity: 0.45 }}, {{ scale: 1, opacity: 0, duration: 0.35, ease: "power1.out" }}, {at + 1.75:.3f});
tl.set("#btnSub", {{ opacity: 0 }}, {at + 1.85:.3f});
tl.set("#btnDone", {{ opacity: 1 }}, {at + 1.85:.3f});
tl.to("#cursor", {{ x: {lxa:.1f}, y: {lya:.1f}, duration: 0.8, ease: "power2.inOut" }}, {at + 2.2:.3f});
tl.to("#cursor", {{ scale: 0.86, duration: 0.06, yoyo: true, repeat: 1, transformOrigin: "0% 0%" }}, {at + 3.57:.3f});
tl.fromTo("#rip2", {{ scale: 0, opacity: 0.45 }}, {{ scale: 1, opacity: 0, duration: 0.35, ease: "power1.out" }}, {at + 3.6:.3f});
tl.set("#bellOff", {{ opacity: 0 }}, {at + 3.7:.3f});
tl.set("#bellOn", {{ opacity: 1 }}, {at + 3.7:.3f});
tl.fromTo("#bell", {{ rotation: -14 }}, {{ rotation: 14, duration: 0.08, yoyo: true, repeat: 5, ease: "sine.inOut", transformOrigin: "50% 10%", immediateRender: false }}, {at + 3.7:.3f});
tl.set("#bell", {{ rotation: 0 }}, {at + 4.2:.3f});
tl.to("#cursor", {{ x: {ex:.1f}, y: {ey:.1f}, duration: 0.4, ease: "power2.in" }}, {at + 4.2:.3f});
tl.set("#cursor", {{ opacity: 0 }}, {at + 4.6:.3f});"""
    return card, js
