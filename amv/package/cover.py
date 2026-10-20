"""A cinematic AMV thumbnail (the look of top anime-edit channels, 2026-10-20 research):
ONE strong frame, heavily graded - contrast, colour, bloom, light rays, a chromatic
fringe at the edges, vignette - and 0-2 big metallic words beside the face. Real
frames only. 1280x720 JPEG plus the 168x94 preview YouTube shows on phones.

    ./amv.sh amv-cover SPEC.json                    # -> <out>/thumb.jpg + thumb_small.png
    ./amv.sh amv-cover --edit EDIT_SPEC [--n 24]    # clean SOURCE frames of an edit's shots to choose from
    ./amv.sh amv-cover --candidates VIDEO [--n 24]  # same from a finished video (glitch/text frames included)

Spec:
    {"out": "workspace/output/edits/NAME",
     "frame": {"video": "...mp4", "t": 61.2} | {"file": "...mkv", "at": 1234.5} | {"image": "..png"},
     "zoom": 1.0, "center": [0.5, 0.5],          # crop: push in on the subject
     "flip": false,
     "title": "REWIND", "sub": "RE:ZERO",        # 0-2 words big + an optional small line
     "style": "chrome" | "gold" | "red" | "ice" | "violet",
     "side": "left" | "right" | "bottom" | "top",  # where the words go (away from the face)
     "size": 0.24,                                # title cap height as a fraction of 720
     "max_width": 0.48,                           # of the frame (0.48 on a side, 0.8 top/bottom)
     "grade": {"contrast": 1.18, "saturation": 1.3, "bloom": 0.55, "rays": 0.35,
               "rays_from": [0.5, 0.3], "fringe": 6, "vignette": 0.45, "sharpen": 1.0}}
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1280, 720
STYLES = {  # gradient top -> bottom, extrusion colour, glow colour
    "chrome": ([255, 255, 255], [150, 160, 175], [40, 44, 52], [180, 210, 255]),
    "gold": ([255, 246, 200], [214, 150, 40], [70, 40, 8], [255, 190, 80]),
    "red": ([255, 200, 190], [210, 20, 40], [60, 0, 8], [255, 40, 60]),
    "ice": ([240, 255, 255], [90, 190, 255], [10, 40, 80], [120, 220, 255]),
    "violet": ([250, 230, 255], [160, 70, 255], [40, 10, 70], [190, 120, 255]),
}


def grab(frame: dict) -> Image.Image:
    if "image" in frame:
        return Image.open(frame["image"]).convert("RGB")
    src, t = (frame["video"], frame["t"]) if "video" in frame else (frame["file"], frame["at"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{float(t):.3f}", "-i", src, "-frames:v", "1",
                          "-vf", "scale=1920:1080:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return Image.frombytes("RGB", (1920, 1080), raw)


def crop(img: Image.Image, zoom: float, center: list[float]) -> Image.Image:
    w, h = img.size
    cw, ch = w / zoom, h / zoom
    cx = min(max(center[0] * w, cw / 2), w - cw / 2)
    cy = min(max(center[1] * h, ch / 2), h - ch / 2)
    return img.resize((W, H), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def grade(img: Image.Image, g: dict) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(g.get("contrast", 1.18))
    img = ImageEnhance.Color(img).enhance(g.get("saturation", 1.3))
    if g.get("sharpen", 1.0):
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=int(120 * g.get("sharpen", 1.0)), threshold=2))
    f = np.asarray(img, np.float32)
    # Bloom: highlights blurred wide and screened back on.
    # Threshold from the frame itself: a bright sky or white hair must not blow out.
    lum = f.mean(axis=2)
    thr = max(170.0, float(np.percentile(lum, 92)))
    hi = np.clip((f - thr) * 255 / max(1.0, 255 - thr), 0, 255).astype(np.uint8)
    bloom = np.asarray(Image.fromarray(hi).filter(ImageFilter.GaussianBlur(22)), np.float32)
    a = g.get("bloom", 0.55)
    f = 255 - (255 - f) * (255 - bloom * a) / 255
    # Light rays: the highlights radially smeared out from a point (god rays).
    if g.get("rays", 0.35):
        cx, cy = (np.array(g.get("rays_from", [0.5, 0.3])) * [W, H]).astype(int)
        src = Image.fromarray(hi)
        acc = np.zeros_like(f)
        for k in range(1, 13):
            s = 1 + 0.035 * k
            layer = src.resize((int(W * s), int(H * s)), Image.BILINEAR)
            ox, oy = int(cx * s - cx), int(cy * s - cy)
            acc += np.asarray(layer.crop((ox, oy, ox + W, oy + H)), np.float32) * (1 - k / 13)
        rays = np.asarray(Image.fromarray(np.clip(acc / 4, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)),
                          np.float32)
        f = 255 - (255 - f) * (255 - rays * g.get("rays", 0.35)) / 255
    # Chromatic fringe, growing toward the edges (faces in the middle stay clean).
    px = int(g.get("fringe", 6))
    if px:
        ys, xs = np.mgrid[0:H, 0:W]
        r = np.clip(np.sqrt(((xs - W / 2) / (W / 2)) ** 2 + ((ys - H / 2) / (H / 2)) ** 2) - 0.45, 0, 1)
        # shifted with the edge column repeated (np.roll wrapped the far edge in as a stripe)
        shifted_r = np.concatenate([np.repeat(f[:, :1, 0], px, axis=1), f[:, :-px, 0]], axis=1)
        shifted_b = np.concatenate([f[:, px:, 2], np.repeat(f[:, -1:, 2], px, axis=1)], axis=1)
        f[..., 0] = f[..., 0] * (1 - r) + shifted_r * r
        f[..., 2] = f[..., 2] * (1 - r) + shifted_b * r
    v = g.get("vignette", 0.45)
    ys, xs = np.mgrid[0:H, 0:W]
    rr = np.sqrt(((xs - W / 2) / (W / 2)) ** 2 * 0.8 + ((ys - H / 2) / (H / 2)) ** 2)
    f *= (1 - v * np.clip(rr - 0.55, 0, 1) ** 1.4)[..., None]
    return Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))


def font(size: int, name: str = "Anton") -> ImageFont.FreeTypeFont:
    from amv.edit.text import font_path

    return ImageFont.truetype(font_path(name), size)


def metal_text(text: str, size: int, style: str, tracking: int = 4) -> Image.Image:
    """The words as a layer: vertical metallic gradient, a dark extrusion down-right,
    a thin bright rim and an outer glow in the style's colour."""
    top, mid, ext, glow = (np.array(c, np.float32) for c in STYLES[style])
    f = font(size)
    widths = [f.getlength(ch) for ch in text]
    tw = int(sum(widths) + tracking * (len(text) - 1)) + 40
    asc, desc = f.getmetrics()
    th = asc + desc + 40
    depth = max(4, size // 14)
    pad = depth + 40
    mask = Image.new("L", (tw + 2 * pad, th + 2 * pad), 0)
    d = ImageDraw.Draw(mask)
    x = pad + 20
    for ch, wch in zip(text, widths, strict=True):
        d.text((x, pad + 10), ch, font=f, fill=255)
        x += wch + tracking
    m = np.asarray(mask, np.float32) / 255
    hgt, wid = m.shape
    rows = np.nonzero(m.max(axis=1) > 0.5)[0]
    y0, y1 = (rows[0], rows[-1]) if len(rows) else (0, hgt - 1)
    u = np.clip((np.arange(hgt) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
    # chrome-like: bright top, a dark band just under the middle, lighter bottom
    band = np.where(u < 0.52, top + (mid - top) * (u / 0.52), mid * 0.55 + (top * 0.8 - mid * 0.55) * ((u - 0.52) / 0.48))
    fill = np.broadcast_to(band, (hgt, wid, 3))
    out = np.zeros((hgt, wid, 4), np.float32)
    for k in range(depth, 0, -1):  # extrusion
        sh = np.roll(np.roll(m, k, axis=0), k, axis=1)
        a = np.maximum(out[..., 3], sh)
        out[..., :3] = np.where(sh[..., None] > out[..., 3:4], ext * (0.6 + 0.4 * k / depth), out[..., :3])
        out[..., 3] = a
    out[..., :3] = out[..., :3] * (1 - m[..., None]) + fill * m[..., None]
    out[..., 3] = np.maximum(out[..., 3], m)
    rim = np.clip(m - np.roll(m, 2, axis=0), 0, 1)[..., None]  # bright top edge
    out[..., :3] = out[..., :3] * (1 - rim * 0.8) + 255 * rim * 0.8
    layer = Image.fromarray(np.clip(np.dstack([out[..., :3], out[..., 3:] * 255]), 0, 255).astype(np.uint8), "RGBA")
    g = Image.fromarray((np.maximum(m, out[..., 3]) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(size / 9))
    glow_l = Image.new("RGBA", layer.size, tuple(int(c) for c in glow) + (0,))
    glow_l.putalpha(g.point(lambda v: int(v * 0.85)))
    dark = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    dark.putalpha(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(size / 14)).point(
        lambda v: int(v * 0.7)))
    base = Image.alpha_composite(glow_l, dark)
    return Image.alpha_composite(base, layer).crop(Image.alpha_composite(base, layer).getbbox())


def place(img: Image.Image, layer: Image.Image, side: str, y_frac: float | None = None) -> tuple[int, int]:
    lw, lh = layer.size
    margin = 46
    if side == "left":
        return margin, int((H - lh) * (y_frac if y_frac is not None else 0.5))
    if side == "right":  # keep the bottom-right corner clear for the duration badge
        return W - lw - margin, int((H - lh) * (y_frac if y_frac is not None else 0.38))
    if side == "top":
        return (W - lw) // 2, margin
    return (W - lw) // 2, H - lh - 70


def build(spec: dict) -> Path:
    out = Path(spec.get("out", "."))
    out.mkdir(parents=True, exist_ok=True)
    img = grab(spec["frame"])
    if spec.get("flip"):
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img = crop(img, float(spec.get("zoom", 1.0)), spec.get("center", [0.5, 0.5]))
    img = grade(img, spec.get("grade", {}))
    canvas = img.convert("RGBA")
    style, side = spec.get("style", "chrome"), spec.get("side", "left")
    if spec.get("title"):
        size = int(H * float(spec.get("size", 0.24)) * 1.35)
        words = spec["title"].split("\n")
        layers = [metal_text(w.upper(), size, style) for w in words]
        if spec.get("sub"):
            layers.append(metal_text(spec["sub"].upper(), int(size * 0.32), style, tracking=int(size * 0.06)))
        lw = max(layer.size[0] for layer in layers)
        lh = sum(layer.size[1] for layer in layers) - 18 * (len(layers) - 1)
        block = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        y = 0
        for layer in layers:
            x = 0 if side == "left" else (lw - layer.size[0]) if side == "right" else (lw - layer.size[0]) // 2
            block.alpha_composite(layer, (x, y))
            y += layer.size[1] - 18
        cap = float(spec.get("max_width", 0.48 if side in ("left", "right") else 0.8))
        if lw > W * cap:  # words on a side stay in their half: the face must stay visible
            s = W * cap / lw
            block = block.resize((int(lw * s), int(lh * s)), Image.LANCZOS)
        canvas.alpha_composite(block, place(img, block, side, spec.get("y")))
    final = canvas.convert("RGB")
    path = out / "thumb.jpg"
    final.save(path, quality=93, optimize=True)
    small = final.resize((168, 94), Image.LANCZOS)
    small.save(out / "thumb_small.png")
    preview = Image.new("RGB", (W, H + 20 + 94 * 3), (18, 18, 20))
    preview.paste(final, (0, 0))
    preview.paste(small.resize((168 * 3, 94 * 3), Image.NEAREST), (0, H + 20))
    preview.save(out / "thumb_review.jpg", quality=88)
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB), {out / 'thumb_review.jpg'} (full + phone-size x3)",
          flush=True)
    return path


def score(a: np.ndarray) -> float | None:
    """Sharp (no motion blur), detailed, colourful, not dark or blown; None = unusable."""
    g = a.mean(axis=2)
    sharp = float(np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean())
    sat = float((a.max(axis=2) - a.min(axis=2)).mean())
    lum = float(g.mean())
    return sharp * 0.6 + sat * 0.25 + min(lum, 140) * 0.1 if 45 < lum < 210 else None


def edit_candidates(spec_path: Path, n: int, out: Path) -> None:
    """Each shot of an edit spec at its middle, from the SOURCE file (no text, no
    glitch, no letterbox) - the frames a cover should be built from."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    shots = spec["shots"]
    starts = [0.0] + [s["until"] for s in shots[:-1]]
    scored = []
    for k, (s, t0) in enumerate(zip(shots, starts, strict=True)):
        mid = s["at"] + (s["until"] - t0) * s.get("speed", 1.0) / 2 * (-1 if s.get("reverse") else 1)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", s["file"], "-frames:v", "1",
                              "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) < 320 * 180 * 3:
            continue
        a = np.frombuffer(raw, np.uint8).reshape(180, 320, 3).astype(np.float32)
        sc = score(a)
        if sc is not None:
            scored.append((sc, k, s["file"], mid, a))
    scored.sort(key=lambda x: -x[0])
    picked = sorted(scored[:n], key=lambda x: x[1])
    cols = 6
    sheet = Image.new("RGB", (cols * 320, ((len(picked) + cols - 1) // cols) * 180), (0, 0, 0))
    for j, (_, k, f, t, a) in enumerate(picked):
        im = Image.fromarray(a.astype(np.uint8))
        ImageDraw.Draw(im).text((6, 6), f"shot {k} @{t:.1f}", fill=(255, 230, 0))
        sheet.paste(im, ((j % cols) * 320, (j // cols) * 180))
    out.mkdir(parents=True, exist_ok=True)
    sheet.save(out / "cover_candidates.jpg", quality=88)
    (out / "cover_candidates.json").write_text(json.dumps(
        [{"shot": k, "file": f, "at": round(t, 3)} for _, k, f, t, _ in picked], indent=1))
    print(f"Wrote {out / 'cover_candidates.jpg'} + .json ({len(picked)} shots; use one as frame: {{file, at}})",
          flush=True)


def candidates(video: str, n: int, out: Path) -> None:
    """The video's strongest still frames: sharp (no motion blur), not dark, detailed,
    colourful - a numbered sheet with their times."""
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", "fps=4,scale=320:180", str(tmp / "%05d.png")], check=True)
    scored = []
    for p in sorted(tmp.glob("*.png")):
        sc = score(np.asarray(Image.open(p).convert("RGB"), np.float32))
        if sc is not None:
            scored.append((sc, (int(p.stem) - 1) / 4, p))
    scored.sort(reverse=True)
    picked: list = []
    for s in scored:  # spread out: at least 2 s apart
        if all(abs(s[1] - q[1]) >= 2.0 for q in picked):
            picked.append(s)
        if len(picked) >= n:
            break
    picked.sort(key=lambda s: s[1])
    cols = 6
    sheet = Image.new("RGB", (cols * 320, ((len(picked) + cols - 1) // cols) * 180), (0, 0, 0))
    for k, (_, t, p) in enumerate(picked):
        im = Image.open(p).convert("RGB")
        ImageDraw.Draw(im).text((6, 6), f"{t:.2f}s", fill=(255, 230, 0))
        sheet.paste(im, ((k % cols) * 320, (k // cols) * 180))
    out.mkdir(parents=True, exist_ok=True)
    sheet.save(out / "cover_candidates.jpg", quality=88)
    print(f"Wrote {out / 'cover_candidates.jpg'}: " + ", ".join(f"{t:.2f}" for _, t, _ in picked), flush=True)
    for p in tmp.glob("*.png"):
        p.unlink()
    tmp.rmdir()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", type=Path)
    ap.add_argument("--candidates", default=None, help="a video: its strongest frames on a sheet")
    ap.add_argument("--edit", type=Path, default=None, help="an edit spec: its shots' clean source frames on a sheet")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.edit:
        edit_candidates(args.edit, args.n, args.out or Path("."))
        return
    if args.candidates:
        candidates(args.candidates, args.n, args.out or Path(args.candidates).parent)
        return
    if not args.spec:
        ap.error("a spec, or --candidates VIDEO")
    build(json.loads(args.spec.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
