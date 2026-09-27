"""A Short's thumbnail (1080x1920) from a real frame, in the user's reference
style (/mnt/datadisk/thumbnail_examples): the picture full-bleed, one to
three SHORT labels ("BOUGHT BRIDE", "VILLAIN") in yellow condensed caps with
a black outline, each with a fat yellow arrow pointing at who it names.
No generated imagery.

    spec "thumbnail": {"ep": 1, "t": 155.9, "x": 0.45, "aspect": 0.75,   # frame, crop centre, crop shape
                       "labels": [{"text": "BOUGHT\\nBRIDE", "at": [0.3, 0.2], "to": [0.45, 0.42]}]}

Or "panels": [{"ep", "t", "x"}, ...] stacks frames top to bottom (a
comparison: her two faces), labels drawn over the stack; a label may set
"color": [r, g, b].

"at" is the label's centre and "to" the point the arrow tip touches, both as
fractions of the 1080x1920 canvas - READ "to" OFF A RENDER (render without
labels first, look, then place): an arrow aimed from imagination points at
nothing (amv-thumbnails-and-titles skill). The arrow starts at the label's
edge facing the target; its angle comes from atan2.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from amv.shorts.story import FONTS

W, H = 1080, 1920
YELLOW, BLACK = (255, 230, 0), (8, 8, 8)


def grab(file: str, t: float) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", file, "-frames:v", "1", "-an", "-sn",
                          "-vf", "scale=1920:1080,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return Image.frombuffer("RGB", (1920, 1080), raw[: 1920 * 1080 * 3])


def arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], tip: tuple[float, float], width: float = 46) -> None:
    """A fat block arrow from start to tip, outlined in black."""
    dx, dy = tip[0] - start[0], tip[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 30:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head_len, head_w = min(length * 0.55, width * 2.1), width * 1.25
    neck = (tip[0] - ux * head_len, tip[1] - uy * head_len)
    half = width / 2
    shape = [(start[0] + px * half, start[1] + py * half), (neck[0] + px * half, neck[1] + py * half),
             (neck[0] + px * head_w, neck[1] + py * head_w), tip,
             (neck[0] - px * head_w, neck[1] - py * head_w), (neck[0] - px * half, neck[1] - py * half),
             (start[0] - px * half, start[1] - py * half)]
    draw.polygon(shape, fill=YELLOW, outline=BLACK, width=9)


def label(draw: ImageDraw.ImageDraw, text: str, centre: tuple[float, float], size: int,
          color: list[int] | None = None) -> tuple[float, ...]:
    font = ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), size)
    box = draw.multiline_textbbox(centre, text, font=font, anchor="mm", align="center", spacing=4,
                                  stroke_width=max(8, size // 9))
    draw.multiline_text(centre, text, font=font, fill=tuple(color) if color else YELLOW, anchor="mm", align="center", spacing=4,
                        stroke_width=max(8, size // 9), stroke_fill=BLACK)
    return box


def thumbnail(spec: dict, out: Path) -> Path:
    from amv.shorts.find import crop_x, load_show

    th = spec["thumbnail"]
    if th.get("panels"):
        canvas = panels(spec, th["panels"])
        return _labels(canvas, th, out)
    e = next(x for x in load_show(spec["series"]) if x.number == th["ep"])
    frame = grab(str(e.file), th["t"])
    x = th.get("x", crop_x(str(e.file), th["t"], th["t"] + 0.1))
    # A crop of `aspect` (width/height, default 3:4) around x, as wide as the
    # canvas, on a blurred copy of the frame: a full-bleed 9:16 slice of a
    # 16:9 close-up is one eye, not two characters.
    from PIL import ImageFilter

    aspect, zoom = th.get("aspect", 0.75), th.get("zoom", 1.0)
    ch = 1080 / zoom
    cw = min(1920, ch * aspect)
    cx = min(max(x * 1920, cw / 2), 1920 - cw / 2)
    cy = min(max(th.get("y", 0.5) * 1080, ch / 2), 1080 - ch / 2)
    pic = frame.crop((round(cx - cw / 2), round(cy - ch / 2), round(cx + cw / 2), round(cy + ch / 2)))
    pic = pic.resize((W, round(W / aspect)), Image.LANCZOS)
    back = frame.resize((round(H * 16 / 9), H), Image.BILINEAR)
    left = (back.width - W) // 2
    back = back.crop((left, 0, left + W, H)).filter(ImageFilter.GaussianBlur(30))
    canvas = Image.eval(back, lambda v: int(v * 0.55))
    canvas.paste(pic, (0, (H - pic.height) // 2 + round(th.get("offset_y", 0.0) * H)))
    return _labels(canvas, th, out)


def panels(spec: dict, items: list[dict]) -> Image.Image:
    """Frames stacked top to bottom, each cropped to fill its band - for a
    thumbnail whose point is a comparison (her two faces, before/after)."""
    from amv.shorts.find import load_show

    eps = {x.number: x for x in load_show(spec["series"])}
    canvas = Image.new("RGB", (W, H))
    band = H // len(items)
    for k, p in enumerate(items):
        frame = grab(str(eps[p["ep"]].file), p["t"])
        ch = 1080 / p.get("zoom", 1.0)
        cw = ch * W / band
        if cw > 1920:  # band wider than the frame: crop height instead
            cw, ch = 1920, 1920 * band / W
        cx = min(max(p.get("x", 0.5) * 1920, cw / 2), 1920 - cw / 2)
        cy = min(max(p.get("y", 0.5) * 1080, ch / 2), 1080 - ch / 2)
        crop = frame.crop((round(cx - cw / 2), round(cy - ch / 2), round(cx + cw / 2), round(cy + ch / 2)))
        canvas.paste(crop.resize((W, band), Image.LANCZOS), (0, k * band))
    draw = ImageDraw.Draw(canvas)
    for k in range(1, len(items)):
        draw.rectangle([0, k * band - 6, W, k * band + 6], fill=BLACK)
    return canvas


def _labels(canvas: Image.Image, th: dict, out: Path) -> Path:
    draw = ImageDraw.Draw(canvas)
    for lab in th.get("labels", []):
        centre = (lab["at"][0] * W, lab["at"][1] * H)
        size = lab.get("size", 150)
        box = label(draw, lab["text"], centre, size, lab.get("color"))
        if lab.get("to"):
            tip = (lab["to"][0] * W, lab["to"][1] * H)
            # start at the label's edge facing the target
            bx = min(max(tip[0], box[0]), box[2])
            by = min(max(tip[1], box[1]), box[3])
            gap = 18
            ang = math.atan2(tip[1] - by, tip[0] - bx)
            arrow(draw, (bx + gap * math.cos(ang), by + gap * math.sin(ang)), tip)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def main() -> None:
    import argparse
    import json

    from amv.shorts.find import SHORTS

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--candidates", default=None,
                        help="EP:T[:X],... - render these frames bare, side by side, to choose one and "
                             "read label/arrow positions off (a grid at 10%% steps is drawn)")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    out_dir = SHORTS / spec["name"]
    if args.candidates:
        tiles = []
        for k, item in enumerate(args.candidates.split(",")):
            ep, t, *x = item.split(":")
            th = {**spec.get("thumbnail", {}), "ep": int(ep), "t": float(t), "labels": []}
            if x:
                th["x"] = float(x[0])
            path = thumbnail({**spec, "thumbnail": th}, out_dir / f"thumb_candidate_{k}.jpg")
            img = Image.open(path).resize((432, 768))
            d = ImageDraw.Draw(img)
            for f in range(1, 10):
                d.line([(f * 43.2, 0), (f * 43.2, 768)], fill=(255, 255, 255), width=1)
                d.line([(0, f * 76.8), (432, f * 76.8)], fill=(255, 255, 255), width=1)
            d.text((6, 6), item, fill=(255, 230, 0), stroke_width=2, stroke_fill=(0, 0, 0))
            tiles.append(img)
        sheet = Image.new("RGB", (432 * len(tiles), 768))
        for k, img in enumerate(tiles):
            sheet.paste(img, (432 * k, 0))
        sheet.save(out_dir / "thumb_candidates.jpg", quality=88)
        print(f"Wrote {out_dir / 'thumb_candidates.jpg'} (grid lines every 0.1)")
        return
    print(f"Wrote {thumbnail(spec, out_dir / 'thumbnail.jpg')}")


if __name__ == "__main__":
    main()
