"""Candidate shots for an edit, by how they MOVE (not by dialogue): every shot between
two cuts of a series' library index (amv.intro.library, 8 fps grey), with its motion
energy, brightness and length; OP/ED/recap repeats left out. Numbered sheets
(start / middle / end of each shot) to choose from by eye.

    ./amv.sh edit-pool SERIES --out DIR [--episodes 201-225] [--top 480] [--min 0.8]
        -> DIR/pool.json (all candidates, best first) + DIR/pool_NN.jpg sheets

Pick ids from the sheets into a picks file (amv-edit-flow skill), then
`./amv.sh flow` measures their head/tail motion and amv.edit.links orders them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from amv.core import paths
from amv.intro import library as lib

CUT = 0.10       # mean abs grey change (0-1) at 8 fps that is a cut
MIN_LUMA, MAX_LUMA = 0.10, 0.85
REPEAT_CORR = 0.90


def song_zones(series: str, eps: list[lib.Episode], pad: float = 15.0) -> dict[int, list[tuple[float, float]]]:
    """OP/ED by their subtitled lyrics: a line that recurs in 3+ episodes is a song's,
    and its neighbourhood (credits included) is out. Catches what the picture-repeat
    check misses (per-episode credit text, an OP only a few episodes use)."""
    from collections import defaultdict

    from amv.intro import dialogue

    lines = dialogue.load({series: eps})
    eps_of: dict[str, set] = defaultdict(set)
    for (_, n), ls in lines.items():
        for ln in ls:
            eps_of[ln["text"].strip().lower()].add(n)
    zones: dict[int, list[tuple[float, float]]] = {}
    for (_, n), ls in lines.items():
        zones[n] = [(ln["start"] - pad, ln["end"] + pad) for ln in ls
                    if len(ln["text"].strip()) > 12 and len(eps_of[ln["text"].strip().lower()]) >= 3]
    return zones


def shots_of(ep: lib.Episode, min_len: float, zones: list[tuple[float, float]] = ()) -> list[dict]:
    f = ep.frames.astype(np.float32) / 255.0
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    cuts = [0] + [i + 1 for i in np.nonzero(d > CUT)[0]] + [len(f)]
    out = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        t0, t1 = a / lib.INDEX_FPS, b / lib.INDEX_FPS
        if t1 - t0 < min_len or any(r0 - 1 <= t0 <= r1 + 1 or r0 - 1 <= t1 <= r1 + 1 for r0, r1 in ep.repeats) \
                or any(z0 <= t1 and t0 <= z1 for z0, z1 in zones):
            continue
        seg, inner = f[a:b], d[a:max(a + 1, b - 1)]
        luma = float(seg.mean())
        if not MIN_LUMA < luma < MAX_LUMA:
            continue
        # motion: how much the picture changes inside the shot (held frames count as still)
        energy = float(np.mean(inner)) if len(inner) else 0.0
        detail = float(seg.std(axis=(1, 2)).mean())
        out.append({"ep": ep.number, "file": str(ep.file), "start": round(t0 + 0.06, 2),
                    "duration": round(t1 - t0 - 0.12, 2), "energy": round(energy, 4), "luma": round(luma, 3),
                    "detail": round(detail, 3)})
    return out


def sheet(entries: list[dict], path: Path, first_id: int) -> None:
    from amv.vision.decode import decode_tiny

    tw, th = 256, 144
    cols = 4  # 4 shots per row, 3 frames each
    rows = (len(entries) + cols - 1) // cols
    img = Image.new("RGB", (cols * 3 * tw, rows * (th + 16)), (12, 12, 14))
    d = ImageDraw.Draw(img)
    for k, e in enumerate(entries):
        x0, y0 = (k % cols) * 3 * tw, (k // cols) * (th + 16)
        for j, frac in enumerate((0.08, 0.5, 0.92)):
            fr = decode_tiny(e["file"], tw, th, start=e["start"] + e["duration"] * frac, duration=0.05)
            if len(fr):
                img.paste(Image.fromarray(fr[0]), (x0 + j * tw, y0 + 16))
        d.text((x0 + 4, y0 + 2), f"{first_id + k}  ep{e['ep']} {e['start']:.1f}s {e['duration']:.1f}s "
                                 f"e{e['energy']:.3f}", fill=(255, 220, 0))
    img.save(path, quality=84)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--episodes", default="", help="e.g. 101-113,201-225")
    ap.add_argument("--top", type=int, default=480, help="candidates on the sheets (by motion)")
    ap.add_argument("--min", type=float, default=0.8, help="shortest shot, seconds")
    ap.add_argument("--per-sheet", type=int, default=40)
    args = ap.parse_args()
    from amv.core import config

    root = Path(config.load().library_dir)
    eps = lib.discover(root)[args.series]
    if args.episodes:
        keep = set()
        for part in args.episodes.split(","):
            a, _, b = part.partition("-")
            keep.update(range(int(a), int(b or a) + 1))
        eps = [e for e in eps if e.number in keep]
    lib.index({args.series: eps}, paths.INTRO / "library")
    # Stricter than the library default: credits change the text over a repeated ED
    # (Re:Zero's snowflake ED passed at 0.97). Losing a recurring shot is cheap here.
    lib.find_repeats(eps, corr=REPEAT_CORR)
    zones = song_zones(args.series, eps)
    cands = [s for e in eps for s in shots_of(e, args.min, zones.get(e.number, []))]
    # Ranked by motion, then detail; a few per episode at most in the top so one
    # fight doesn't fill every sheet.
    cands.sort(key=lambda s: -(s["energy"] * 10 + s["detail"]))
    per_ep: dict[int, int] = {}
    top, rest = [], []
    cap = max(6, args.top // max(1, len(eps)) * 2)
    for s in cands:
        if len(top) < args.top and per_ep.get(s["ep"], 0) < cap:
            top.append(s)
            per_ep[s["ep"]] = per_ep.get(s["ep"], 0) + 1
        else:
            rest.append(s)
    top.sort(key=lambda s: (s["ep"], s["start"]))
    for i, s in enumerate(top):
        s["id"] = i
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "pool.json").write_text(json.dumps(top, indent=0), encoding="utf-8")
    for k in range(0, len(top), args.per_sheet):
        sheet(top[k:k + args.per_sheet], args.out / f"pool_{k // args.per_sheet:02d}.jpg", k)
    print(f"{len(cands)} shots in {len(eps)} episodes; {len(top)} on {(len(top) + args.per_sheet - 1) // args.per_sheet}"
          f" sheets in {args.out}", flush=True)


if __name__ == "__main__":
    main()
