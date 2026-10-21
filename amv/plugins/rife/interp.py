"""Anime-aware slow motion with RIFE: a source window becomes a clip `factor` times
slower at the same frame rate, so a montage shot can swap it in (file, at 0,
speed x factor) and every slowed frame is a real in-between instead of a repeat.

Anime is drawn on twos/threes: half or more of the frames are holds. Interpolating
those as-is gives holds that stay holds (jerky). So holds are dropped first, each
unique drawing keeps its own time, RIFE fills in-betweens on the unique sequence, and
the result is re-timed onto an even clock. A cut inside the window ends it there:
nothing is ever blended across a cut."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

HOLD = 0.0035   # mean abs grey change (0-1) under which a frame repeats the last drawing
CUT = 0.16      # over which it is a cut
MAX_GAP = 4     # source frames: drawings further apart than this are held, not morphed
SOURCE_FPS = Fraction(24000, 1001)


def _settings() -> dict:
    from amv.core import tools

    return tools.settings("rife")


def _grey(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L").resize((160, 90)), np.float32) / 255.0


def slow_clip(file: str, at: float, seconds: float, factor: int, reverse: bool = False) -> tuple[Path, float]:
    """(clip, usable seconds of source) - the window [at, at + seconds) (or [at -
    seconds, at) when reverse) slowed `factor` times; cached."""
    from amv.core import paths
    from amv.plugins.rife.setup import binary

    st = _settings()
    model = st.get("model", "rife-v4.6")
    a = at - seconds if reverse else at
    key = hashlib.sha1(f"{file}|{a:.3f}|{seconds:.3f}|{factor}|{model}|v2".encode()).hexdigest()[:14]
    out_dir = paths.TMP / "interp"
    out = out_dir / f"{key}.mp4"
    meta = out_dir / f"{key}.txt"
    if out.exists() and meta.exists():
        return out, float(meta.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rife_", dir=out_dir))
    try:
        src = work / "src"
        src.mkdir()
        # Frame-exact decode of the window at the source's own rate.
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, a):.4f}", "-i", file, "-t", f"{seconds:.4f}",
                        "-fps_mode", "passthrough", "-vf", "scale=1920:1080:flags=lanczos", str(src / "%06d.png")],
                       check=True)
        frames = sorted(src.glob("*.png"))
        if len(frames) < 2:
            raise SystemExit(f"rife: no frames in {file} @ {a:.2f}")
        greys = [_grey(p) for p in frames]
        diffs = [0.0] + [float(np.abs(greys[i] - greys[i - 1]).mean()) for i in range(1, len(greys))]
        end = next((i for i in range(1, len(diffs)) if diffs[i] > CUT), len(frames))
        frames, diffs = frames[:end], diffs[:end]
        uniq = [0] + [i for i in range(1, len(frames)) if diffs[i] > HOLD]
        usable = len(frames) / float(SOURCE_FPS)
        times = np.array(uniq, np.float64)          # in source frames
        if len(uniq) < 2:                            # a still: nothing to interpolate
            uniq, times = [0, len(frames) - 1], np.array([0.0, len(frames) - 1.0])
        gaps = np.diff(times)
        gap = int(np.max(gaps[gaps <= MAX_GAP])) if np.any(gaps <= MAX_GAP) else 1
        steps = max(2, factor * gap)                 # in-betweens per unique pair
        inp = work / "in"
        inp.mkdir()
        for j, i in enumerate(uniq):
            shutil.copy(frames[i], inp / f"{j:06d}.png")
        n_out = (len(uniq) - 1) * steps + 1
        res = work / "out"
        res.mkdir()
        exe = binary(st)
        run = subprocess.run([str(exe), "-i", str(inp), "-o", str(res), "-n", str(n_out), "-m", str(exe.parent / model),
                              "-g", str(st.get("gpu", 0)), "-j", "4:2:4", "-f", "%06d.png"],
                             capture_output=True, text=True)
        got = sorted(res.glob("*.png"))
        if run.returncode != 0 or len(got) < n_out:
            raise SystemExit(f"rife failed ({len(got)}/{n_out}): {run.stderr[-1500:]}")
        # Re-time: output m sits at unique position m / steps; map positions to source
        # frames through the unique drawings' real times, then sample an even clock.
        # A pair of drawings further apart than MAX_GAP frames is a deliberate hold (a
        # pause, a talking head): it stays a hold - morphing across it turns into mush.
        clock = np.arange(0, len(frames) - 1 + 1e-9, 1.0 / factor)
        pick = []
        for c in clock:
            j = min(len(times) - 2, int(np.searchsorted(times, c, side="right")) - 1)
            g = times[j + 1] - times[j]
            if g <= MAX_GAP:
                pick.append(j * steps + round((c - times[j]) / g * steps))
            else:
                pick.append(j * steps)
        pick = np.clip(np.array(pick), 0, n_out - 1)
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{got[m]}'\nduration {1 / float(SOURCE_FPS):.6f}\n" for m in pick))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-r", f"{SOURCE_FPS.numerator}/{SOURCE_FPS.denominator}", "-fps_mode", "cfr",
                        "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p", str(out)], check=True)
        meta.write_text(f"{usable:.4f}")
        print(f"[rife] {Path(file).name} @{a:.2f}+{usable:.2f}s: {len(frames)} frames, {len(uniq)} drawings "
              f"-> x{factor} ({len(pick)} frames)", flush=True)
        return out, usable
    finally:
        shutil.rmtree(work, ignore_errors=True)
