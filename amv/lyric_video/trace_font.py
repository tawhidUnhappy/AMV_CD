"""A font traced from the text burned into a video: every glyph of known lines
cut out of clean frames, averaged, vectorised, built into an .otf.

    ./amv.sh font-trace workspace/global/lyric_videos/fonts/NAME.json   # -> workspace/assets/fonts/NAME.otf
    ./amv.sh font-trace SPEC --sheet                                      # the traced glyphs, for a look

Spec:
    video        the reference video
    name         the font's family name (and file name)
    samples      [{"t": seconds, "text": "LINE ONE\\nLINE TWO"}, ...] - a moment where the
                 lines are fully faded in, and exactly what they say (spaces matter;
                 one entry per text line, top to bottom)
    region       [x0, y0, x1, y1] of the frame to read (leave out overlays like a subscribe card)
    fallback     a font file for characters the video never shows (its strokes are
                 thickened/thinned to the traced weight)

Made for white text with a dark rim (the lyrics-channel style): a glyph is a
connected bright region whose border is dark - sparkles have no rim and are
skipped. Letters that wiggle per frame are aligned by their centroid before
averaging. Missing characters: ! " - ... : are built from traced ones, the rest
come from the fallback, lower case maps to the capitals."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from amv.core import paths
from amv.core.config import ROOT, load

S = 512             # glyph canvas: px per cap height
FRAMES = 15         # frames averaged around each sample time
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CHARSET = LETTERS + "!\"'(),-.:;?&/…’_@#$%*+=[]"


def _path(p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else ROOT / q


def frames(video: Path, t: float, region: list[int]) -> np.ndarray:
    """FRAMES grey frames centred on t, cropped to region, float32."""
    x0, y0, x1, y1 = region
    fps = 30.0
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t - FRAMES / 2 / fps):.3f}", "-i", str(video),
                          "-frames:v", str(FRAMES), "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, y1 - y0, x1 - x0).astype(np.float32)


def glyphs_of(frame: np.ndarray) -> list[dict]:
    """Bright regions with a dark rim, each with its bbox and soft coverage."""
    lab, n = ndimage.label(frame > 175)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        comp = lab[sl] == i + 1
        area = int(comp.sum())
        if area < 30 or frame[sl][comp].mean() < 228:
            continue
        pad = 4
        ys = slice(max(0, sl[0].start - pad), sl[0].stop + pad)
        xs = slice(max(0, sl[1].start - pad), sl[1].stop + pad)
        mask = lab[ys, xs] == i + 1
        ring = ndimage.binary_dilation(mask, iterations=3) & ~mask
        if frame[ys, xs][ring].mean() > 140:      # no dark rim: a sparkle
            continue
        near = ndimage.binary_dilation(mask, iterations=1)
        soft = np.clip((frame[ys, xs] - 60) / 190, 0, 1) * near
        out.append({"x0": sl[1].start, "x1": sl[1].stop, "y0": sl[0].start, "y1": sl[0].stop,
                    "cy": (sl[0].start + sl[0].stop) / 2, "soft": soft, "oy": ys.start, "ox": xs.start})
    return out


def rows_of(found: list[dict], n_rows: int) -> list[list[dict]]:
    """Split glyphs into n_rows text lines at the biggest vertical gaps."""
    found = sorted(found, key=lambda g: g["cy"])
    if n_rows == 1:
        return [sorted(found, key=lambda g: g["x0"])]
    gaps = sorted(range(1, len(found)), key=lambda k: found[k]["cy"] - found[k - 1]["cy"])[-(n_rows - 1):]
    cuts = [0, *sorted(gaps), len(found)]
    return [sorted(found[a:b], key=lambda g: g["x0"]) for a, b in zip(cuts, cuts[1:])]


def collect(spec: dict) -> tuple[dict[str, list[dict]], list[float], list[float]]:
    """{char: [occurrence...]}, letter gaps and word gaps (cap units)."""
    video = _path(spec["video"])
    region = spec.get("region", [0, 0, 1920, 1080])
    occ: dict[str, list[dict]] = {}
    gaps, word_gaps = [], []
    for s in spec["samples"]:
        lines = s["text"].split("\n")
        used = 0
        for k, f in enumerate(frames(video, s["t"], region)):
            rows = rows_of(glyphs_of(f), len(lines))
            if [len(r) for r in rows] != [len(line.replace(" ", "")) for line in lines]:
                continue
            used += 1
            for line, row in zip(lines, rows):
                chars = line.replace(" ", "")
                spaced = [i for i, c in enumerate(line) if c != " "]
                letters = [g for g, c in zip(row, chars) if c.isalnum()]
                base = float(np.median([g["y1"] for g in letters]))
                cap = float(np.median([g["y1"] - g["y0"] for g in letters]))
                for j, (g, c) in enumerate(zip(row, chars)):
                    occ.setdefault(c, []).append({**g, "cap": cap, "base": base, "src": f"{s['t']}#{k}"})
                    if j:
                        gap = (g["x0"] - row[j - 1]["x1"]) / cap
                        (word_gaps if spaced[j] - spaced[j - 1] > 1 else gaps).append(gap)
        print(f"  {s['t']:7.2f}s  {used}/{FRAMES} frames read  {s['text']!r}")
    return occ, gaps, word_gaps


def average(occs: list[dict], letter: bool) -> tuple[np.ndarray, float]:
    """The averaged glyph on an S-per-cap canvas, and its baseline row in it.
    Only occurrences within 80% of the sharpest one's size are used."""
    top = max(o["cap"] for o in occs)
    occs = [o for o in occs if o["cap"] >= 0.8 * top]
    acc, n = None, 0
    ref_c = None
    offs = []
    for o in occs:
        z = S / o["cap"]
        g = np.clip(ndimage.zoom(o["soft"], z, order=3), 0, 1)
        cy, cx = ndimage.center_of_mass(g)
        # baseline row inside this upsampled patch
        base = (o["base"] - o["oy"]) * z
        offs.append(base - cy)
        if acc is None:
            H, W = g.shape[0] + 64, g.shape[1] + 64
            acc = np.zeros((H, W), np.float32)
            ref_c = (H / 2, W / 2)
        shifted = ndimage.shift(np.pad(g, ((0, max(0, H - g.shape[0])), (0, max(0, W - g.shape[1]))))[:H, :W],
                                (ref_c[0] - cy, ref_c[1] - cx), order=1)
        acc += shifted
        n += 1
    avg = acc / n
    baseline = ref_c[0] + float(np.median(offs))
    if letter:  # letters sit on the baseline: snap the averaged bottom edge to it
        ys = np.nonzero((avg > 0.5).any(axis=1))[0]
        baseline = float(ys.max() + 1)
    return avg, baseline


def stem_width(mask: np.ndarray) -> float:
    """Median horizontal run length through the middle third (an I's stem)."""
    h = mask.shape[0]
    runs = []
    for row in mask[h // 3: 2 * h // 3]:
        r = np.diff(np.concatenate([[0], row.astype(int), [0]]))
        starts, ends = np.nonzero(r == 1)[0], np.nonzero(r == -1)[0]
        runs += list(ends - starts)
    return float(np.median(runs)) if runs else 0.0


def trim(mask: np.ndarray, baseline: float) -> tuple[np.ndarray, float]:
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return mask, baseline
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return mask[y0:y1, x0:x1], baseline - y0


def from_fallback(ch: str, font_path: Path, weight_px: float) -> tuple[np.ndarray, float] | None:
    """A character drawn by the fallback font at cap S, stroke matched to weight_px."""
    probe = ImageFont.truetype(str(font_path), 400)
    hb = probe.getbbox("H")
    font = ImageFont.truetype(str(font_path), int(400 * S / (hb[3] - hb[1])))
    img = Image.new("L", (S * 3, S * 2))
    ImageDraw.Draw(img).text((S, S // 2), ch, font=font, fill=255)
    m = np.asarray(img) > 127
    if not m.any():
        return None
    base = S // 2 + font.getbbox("H")[3]
    iimg = Image.new("L", (S * 2, S * 2))
    ImageDraw.Draw(iimg).text((S // 2, S // 2), "I", font=font, fill=255)
    diff = (weight_px - stem_width(np.asarray(iimg) > 127)) / 2
    if diff >= 1:
        m = ndimage.binary_dilation(m, iterations=int(round(diff)))
    elif diff <= -1:
        m = ndimage.binary_erosion(m, iterations=int(round(-diff)))
    return trim(m, base)


def build_glyphs(occ: dict[str, list[dict]], fallback: Path | None) -> dict[str, tuple[np.ndarray, float, str]]:
    """{char: (binary mask at S per cap, baseline row, how it was made)}."""
    out = {}
    for c, occs in occ.items():
        avg, base = average(occs, c.isalnum())
        m = ndimage.gaussian_filter(avg, 1.5) > 0.5
        m, base = trim(m, base)
        out[c] = (m, base, f"traced x{len(occs)}")
    weight = stem_width(out["I"][0]) if "I" in out else S * 0.16
    if "." in out:
        dot, dbase, _ = out["."]
        dw = dot.shape[1]
        if "…" not in out:
            gap = int(dw * 0.35)
            m = np.zeros((dot.shape[0], dw * 3 + gap * 2), bool)
            for k in range(3):
                m[:, k * (dw + gap): k * (dw + gap) + dw] |= dot
            out["…"] = (m, dbase, "three traced .")
        if ":" not in out:
            h = int(S * 0.62)
            m = np.zeros((h, dw), bool)
            m[:dot.shape[0]] |= dot[:, :dw]
            m[h - dot.shape[0]:] |= dot
            out[":"] = (m, dbase + (h - dot.shape[0]), "two traced .")
        if "I" in out and "!" not in out:
            stem = np.asarray(Image.fromarray(out["I"][0].astype(np.uint8) * 255).resize(
                (out["I"][0].shape[1], int(S * 0.68)), Image.LANCZOS)) > 127
            gap = int(S * 0.1)
            W = max(stem.shape[1], dw)
            m = np.zeros((stem.shape[0] + gap + dot.shape[0], W), bool)
            m[:stem.shape[0], (W - stem.shape[1]) // 2:(W - stem.shape[1]) // 2 + stem.shape[1]] = stem
            m[-dot.shape[0]:, (W - dw) // 2:(W - dw) // 2 + dw] |= dot
            out["!"] = (m, float(m.shape[0]) - (dot.shape[0] - dbase), "traced I + .")
    if "'" in out and '"' not in out:
        ap, abase, _ = out["'"]
        gap = int(ap.shape[1] * 0.45)
        m = np.zeros((ap.shape[0], ap.shape[1] * 2 + gap), bool)
        m[:, :ap.shape[1]] = ap
        m[:, ap.shape[1] + gap:] = ap
        out['"'] = (m, abase, "two traced '")
    if "'" in out and "’" not in out:
        out["’"] = out["'"][:2] + ("traced '",)
    if "I" in out and "-" not in out:
        bar = np.rot90(out["I"][0])
        bar = np.asarray(Image.fromarray(bar.astype(np.uint8) * 255).resize((int(S * 0.34), bar.shape[0]),
                                                                           Image.LANCZOS)) > 127
        out["-"] = (bar, S * 0.42 + bar.shape[0] / 2, "traced I, turned")
    for c in CHARSET:
        if c not in out and fallback:
            got = from_fallback(c, fallback, weight)
            if got:
                out[c] = (*got, "fallback")
    return out


def sheet(glyphs: dict, path: Path) -> None:
    cell = 140
    keys = sorted(glyphs)
    cols = 12
    img = Image.new("RGB", (cols * cell, ((len(keys) + cols - 1) // cols) * cell), (150, 120, 220))
    d = ImageDraw.Draw(img)
    for i, c in enumerate(keys):
        m, base, how = glyphs[c]
        k = 90 / S
        g = Image.fromarray(m.astype(np.uint8) * 255).resize((max(1, int(m.shape[1] * k)), max(1, int(m.shape[0] * k))))
        x, y = (i % cols) * cell + 10, (i // cols) * cell + 10
        img.paste((255, 255, 255), (x, int(y + 100 - base * k)), g)
        d.line([(x, y + 100), (x + cell - 20, y + 100)], fill=(255, 220, 0))
        d.text((x, y + 108), f"{c} {how}", fill=(0, 0, 0))
    img.save(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--sheet", action="store_true", help="also write a sheet of the glyphs (PNG)")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    name = spec.get("name") or args.spec.stem
    print(f"Reading {len(spec['samples'])} sample(s) of {spec['video']}")
    occ, gaps, word_gaps = collect(spec)
    fallback = _path(spec["fallback"]) if spec.get("fallback") else None
    glyphs = build_glyphs(occ, fallback)
    for c in sorted(glyphs):
        print(f"  {c!r}: {glyphs[c][2]}")
    missing = [c for c in CHARSET if c not in glyphs]
    if missing:
        print("  no glyph for:", "".join(missing))
    out_dir = load().workspace / "assets" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)
    work = paths.TMP / "font_trace" / name
    work.mkdir(parents=True, exist_ok=True)
    if args.sheet:
        sheet(glyphs, work / "glyphs.png")
        print(work / "glyphs.png")
    side = float(np.median(gaps)) / 2 if gaps else 0.05
    space = (float(np.median(word_gaps)) if word_gaps else 0.3) - 2 * side
    with tempfile.TemporaryDirectory() as tmp:
        arrays = {f"g{ord(c)}": m.astype(np.uint8) for c, (m, _, _) in glyphs.items()}
        np.savez_compressed(Path(tmp) / "glyphs.npz", **arrays)
        manifest = {"name": name, "S": S, "side": side, "space": max(0.1, space),
                    "glyphs": {str(ord(c)): {"baseline": float(b), "how": how} for c, (_, b, how) in glyphs.items()},
                    "npz": str(Path(tmp) / "glyphs.npz"), "out": str(out_dir / f"{name}.otf")}
        (Path(tmp) / "job.json").write_text(json.dumps(manifest), encoding="utf-8")
        from amv.core import tools
        done = tools.run("font_trace", str(Path(tmp) / "job.json"))
        if done.returncode != 0:
            raise SystemExit(f"font build failed:\n{done.stderr[-3000:]}")
        print(done.stdout.strip())
    print(out_dir / f"{name}.otf")


if __name__ == "__main__":
    main()
