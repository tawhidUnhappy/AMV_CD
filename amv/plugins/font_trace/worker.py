"""Glyph bitmaps -> CFF .otf. Runs in the font_trace tool environment.

    python worker.py job.json

job.json: {name, S (px per cap), side (side bearing, cap units), space (cap
units), glyphs: {codepoint: {baseline (row in its bitmap), how}}, npz, out}.
Cap height is 700 units of 1000. Lower-case letters map to the capitals."""

from __future__ import annotations

import json
import sys

import numpy as np
import potrace
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

UPM, CAP = 1000, 700


def draw(mask: np.ndarray, baseline: float, scale: float, lsb: float, pen) -> None:
    """Trace the mask and draw it: x shifted by lsb, y flipped about the baseline.
    potrace (on the inverted bitmap) gives outers and holes opposite ways; after
    the y flip every contour is reversed so outers run counter-clockwise (CFF)."""
    paths = potrace.Bitmap(~mask.astype(bool)).trace(turdsize=4, alphamax=1.0, opticurve=True, opttolerance=0.2)
    rpen = ReverseContourPen(pen)

    def pt(p):
        return (round(lsb + p.x * scale, 1), round((baseline - p.y) * scale, 1))

    for curve in paths or []:
        rpen.moveTo(pt(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                rpen.lineTo(pt(seg.c))
                rpen.lineTo(pt(seg.end_point))
            else:
                rpen.curveTo(pt(seg.c1), pt(seg.c2), pt(seg.end_point))
        rpen.closePath()


def main() -> None:
    job = json.loads(open(sys.argv[1], encoding="utf-8").read())
    arrays = np.load(job["npz"])
    S = job["S"]
    scale = CAP / S
    side = job["side"] * CAP
    order = [".notdef", "space"]
    charstrings, metrics, cmap = {}, {}, {}
    pen = T2CharStringPen(0, None)
    charstrings[".notdef"] = pen.getCharString()
    metrics[".notdef"] = (int(CAP * 0.5), 0)
    pen = T2CharStringPen(0, None)
    charstrings["space"] = pen.getCharString()
    space_w = int(job["space"] * CAP)
    metrics["space"] = (space_w, 0)
    cmap[32] = "space"
    cmap[0xA0] = "space"
    for cp, info in sorted(job["glyphs"].items(), key=lambda kv: int(kv[0])):
        code = int(cp)
        name = f"uni{code:04X}"
        mask = arrays[f"g{code}"]
        width = int(round(mask.shape[1] * scale + 2 * side))
        pen = T2CharStringPen(width, None)
        draw(mask, info["baseline"], scale, side, pen)
        charstrings[name] = pen.getCharString()
        metrics[name] = (width, int(round(side)))
        order.append(name)
        cmap[code] = name
        ch = chr(code)
        if ch.isalpha() and ch.isupper() and ch.lower() != ch and ord(ch.lower()) not in cmap:
            cmap[ord(ch.lower())] = name
    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    family = job["name"]
    fb.setupCFF(family.replace(" ", ""), {"FullName": family}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=900, descent=-250)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=900, sTypoDescender=-250, usWinAscent=950, usWinDescent=300, sCapHeight=CAP,
                sxHeight=CAP)
    fb.setupPost()
    fb.save(job["out"])
    print(f"{len(order) - 2} glyphs, cap {CAP}/{UPM}, side bearing {side:.0f}, space {space_w}")


if __name__ == "__main__":
    main()
