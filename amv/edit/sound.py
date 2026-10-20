"""Sound design for an edit (AMV_EDITING_GUIDE.md section 10): sound effects placed on
the picture's events, plus automation of the song itself. Without these an edit
"feels like it's missing something" even with good cuts.

Spec keys (all optional):

    "sfx": [{"kind": "whoosh", "at": 12.4, "dur": 0.6, "gain": 0}, ...]
        kinds: whoosh, swish (short), riser, reverse (reverse cymbal), impact, boom
        (bigger impact), hit (small punch), glitch, file ({"file": path}); "pan" -1..1,
        "seed". Anchors follow the guide's sync rules: a whoosh/swish PEAKS on "at", a
        riser/reverse ENDS on "at", an impact/boom/hit/glitch/file STARTS on "at".
    "sfx_auto": true, or {"whoosh": dB, "impact": dB, "hit": dB, "glitch": dB, "min_gap": s}
        derived from the picture: a whip or whoosh out of a shot -> whoosh peaking on
        the cut, a flash in -> impact, a punch/shake in -> hit, a glitch fx burst
        (slice/blocks/smear/pixelate/invert) -> glitch. Explicit "sfx" are added on top.
    "sfx_level": -4
        dB of each effect's loudness against the music around it (the guide: 3-6 dB
        under the song); "gain" on an effect is relative to this.
    "music": [{"kind": "duck", "at", "until", "db": -12}, ...]
        duck (volume dips toward "until", snaps back on it - the pre-drop dip),
        muffle (low-pass at "cutoff" Hz; "open": true sweeps it open by "until"),
        cut (silence), stutter (repeat the first "slice" s), tapestop, reverse.

Everything is synthesised (numpy/scipy), so effects fit their moment exactly and carry
no licence; real recordings go in as kind "file" (workspace/assets/sfx/)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal

SR = 48000
GLITCH_FX = {"slice", "blocks", "smear", "pixelate", "invert"}
DEFAULT_GAIN = {"whoosh": 0.0, "swish": -3.0, "riser": -1.0, "reverse": -3.0, "impact": -1.5, "boom": -0.5,
                "hit": -3.0, "glitch": -6.0, "file": 0.0}
DEFAULT_DUR = {"whoosh": 0.6, "swish": 0.3, "riser": 2.0, "reverse": 1.5, "impact": 1.8, "boom": 2.6,
               "hit": 0.45, "glitch": 0.3}
ANCHOR = {"whoosh": "peak", "swish": "peak", "riser": "end", "reverse": "end"}  # else "start"
PEAK_AT = 0.62  # where in a whoosh its loudest point sits


def _n(seconds: float) -> int:
    return max(1, round(seconds * SR))


def _fade(x: np.ndarray, ms_in: float = 2.0, ms_out: float = 15.0) -> np.ndarray:
    """Short fades so nothing clicks (the guide: 10-20 ms out)."""
    a, b = min(len(x), _n(ms_in / 1000)), min(len(x), _n(ms_out / 1000))
    x[:a] *= np.linspace(0, 1, a)[:, None] if x.ndim == 2 else np.linspace(0, 1, a)
    x[len(x) - b:] *= np.linspace(1, 0, b)[:, None] if x.ndim == 2 else np.linspace(1, 0, b)
    return x


def _sweep_filter(x: np.ndarray, freqs, btype: str, block: int = 256, width: float = 0.8) -> np.ndarray:
    """Time-varying 2nd-order filter: cutoff (or band centre) per block from freqs(u), u 0-1."""
    out = np.empty_like(x)
    zi = None
    nb = (len(x) + block - 1) // block
    for j in range(nb):
        f = float(np.clip(freqs(j / max(1, nb - 1)), 30, SR / 2 * 0.95))
        if btype == "band":
            lo, hi = f / (1 + width), min(SR / 2 * 0.98, f * (1 + width))
            sos = signal.butter(2, [lo, hi], btype="band", fs=SR, output="sos")
        else:
            sos = signal.butter(2, f, btype=btype, fs=SR, output="sos")
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        seg = x[j * block:(j + 1) * block]
        out[j * block:j * block + len(seg)], zi = signal.sosfilt(sos, seg, zi=zi)
    return out


def _stereo(mono: np.ndarray, pan_from: float = 0.0, pan_to: float = 0.0) -> np.ndarray:
    p = np.linspace(pan_from, pan_to, len(mono))
    left, right = np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)
    return np.stack([mono * left, mono * right], axis=1) * np.sqrt(2)


def _norm(x: np.ndarray) -> np.ndarray:
    peak = float(np.abs(x).max())
    return x / peak if peak > 0 else x


def whoosh(dur: float, rng: np.random.Generator, bright: float = 1.0, pan: float = 0.0) -> np.ndarray:
    n = _n(dur)
    u = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    # Band centre rises into the peak and falls after it (the Doppler-ish pass-by).
    centre = lambda v: (350 + 2600 * bright * np.exp(-((v - PEAK_AT) / 0.22) ** 2))  # noqa: E731
    band = _sweep_filter(noise, centre, "band", width=1.1)
    env = np.where(u < PEAK_AT, (u / PEAK_AT) ** 2.2, np.exp(-(u - PEAK_AT) / 0.12))
    air = _sweep_filter(rng.standard_normal(n), lambda v: 6000 * bright, "high") * 0.25 * env ** 2
    return _norm(_fade(_stereo((band * env + air), pan - 0.6, pan + 0.6)))


def riser(dur: float, rng: np.random.Generator) -> np.ndarray:
    n = _n(dur)
    u = np.linspace(0, 1, n)
    noise = _sweep_filter(rng.standard_normal(n), lambda v: 200 * (45 ** v), "low")
    noise = _sweep_filter(noise, lambda v: 150, "high")  # static HPF: the noise must not swamp the mix
    f = 180 * (6 ** u)  # pitch sweep under the noise
    phase = 2 * np.pi * np.cumsum(f * (1 + 0.004 * np.sin(2 * np.pi * 6 * u * dur))) / SR
    tone = signal.sawtooth(phase) * 0.18 + np.sin(phase * 2) * 0.12
    tone = _sweep_filter(tone, lambda v: 800 + 7000 * v, "low")
    env = u ** 2.4
    return _norm(_fade(_stereo((noise + tone) * env), ms_out=4))


def reverse_cymbal(dur: float, rng: np.random.Generator) -> np.ndarray:
    n = _n(dur)
    u = np.linspace(0, 1, n)
    hiss = _sweep_filter(rng.standard_normal(n), lambda v: 3500, "high")
    shimmer = _sweep_filter(rng.standard_normal(n), lambda v: 9000, "band", width=0.5) * 0.6
    env = np.exp(-(1 - u) * 5.5)
    return _norm(_fade(_stereo((hiss + shimmer) * env, -0.3, 0.3), ms_out=4))


def impact(dur: float, rng: np.random.Generator, big: bool = False) -> np.ndarray:
    n = _n(dur)
    t = np.arange(n) / SR
    f = 38 + (95 if big else 75) * np.exp(-t / 0.09)  # sub drop
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.55 if big else 0.4))
    thump = np.sin(2 * np.pi * 120 * t) * np.exp(-t / 0.07) * 0.6
    click = _sweep_filter(rng.standard_normal(n), lambda v: 3500, "low") * np.exp(-t / 0.006) * 0.9
    tail = _sweep_filter(rng.standard_normal(n), lambda v: 1300, "low") * np.exp(-t / (0.9 if big else 0.6)) * 0.12
    x = sub + thump + click + tail
    if big:
        x = np.tanh(x * 1.8)
    return _norm(_fade(_stereo(x), ms_in=0.5, ms_out=40))


def hit(dur: float, rng: np.random.Generator) -> np.ndarray:
    n = _n(dur)
    t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12)
    snap = _sweep_filter(rng.standard_normal(n), lambda v: 2500, "band", width=1.5) * np.exp(-t / 0.02) * 0.7
    return _norm(_fade(_stereo(body + snap), ms_in=0.5, ms_out=20))


def glitch(dur: float, rng: np.random.Generator) -> np.ndarray:
    n = _n(dur)
    out = np.zeros(n)
    pos = 0
    while pos < n:
        ln = _n(rng.uniform(0.018, 0.05))
        seg_t = np.arange(min(ln, n - pos)) / SR
        if rng.random() < 0.5:
            seg = signal.square(2 * np.pi * rng.choice([220, 440, 880, 1760, 3520]) * seg_t) * 0.5
        else:
            seg = rng.standard_normal(len(seg_t))
            seg = np.round(seg * 3) / 3  # bit-crushed
        if rng.random() < 0.25:
            seg *= 0  # a gap
        out[pos:pos + len(seg)] = seg
        pos += len(seg)
    out = _sweep_filter(out, lambda v: 7000, "low")
    return _norm(_fade(_stereo(out, rng.uniform(-0.5, 0), rng.uniform(0, 0.5)), ms_out=6))


def load_file(path: str) -> np.ndarray:
    from amv.edit.audio import decode
    import subprocess

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                               capture_output=True, text=True).stdout.strip() or 0)
    return _norm(_fade(decode(path, 0.0, dur).astype(np.float64), ms_in=1, ms_out=15))


def make(ev: dict) -> np.ndarray:
    kind = ev["kind"]
    rng = np.random.default_rng(int(ev.get("seed", round(ev["at"] * 1000))))
    dur = float(ev.get("dur", DEFAULT_DUR.get(kind, 0.5)))
    if kind == "whoosh":
        return whoosh(dur, rng, ev.get("bright", 1.0), ev.get("pan", 0.0))
    if kind == "swish":
        return whoosh(dur, rng, ev.get("bright", 1.6), ev.get("pan", 0.0))
    if kind == "riser":
        return riser(dur, rng)
    if kind == "reverse":
        return reverse_cymbal(dur, rng)
    if kind in ("impact", "boom"):
        return impact(dur, rng, big=kind == "boom")
    if kind == "hit":
        return hit(dur, rng)
    if kind == "glitch":
        return glitch(dur, rng)
    if kind == "file":
        return load_file(ev["file"])
    raise SystemExit(f"unknown sfx kind {kind!r}")


def start_of(ev: dict, length: int) -> int:
    """Sample where the effect starts, from its anchor rule."""
    at = _n(ev["at"]) if ev["at"] > 0 else 0
    anchor = ev.get("anchor") or ANCHOR.get(ev["kind"], "start")
    if anchor == "peak":
        return at - round(length * PEAK_AT)
    if anchor == "end":
        return at - length
    return at


def auto_events(spec: dict) -> list[dict]:
    """SFX from the picture: whooshes on whips, impacts on flashes, hits on punches,
    glitch on glitch bursts. The strongest wins when two land closer than min_gap."""
    cfg = spec.get("sfx_auto")
    if not cfg:
        return []
    cfg = cfg if isinstance(cfg, dict) else {}
    fps = spec.get("fps", 30)
    shots = spec["shots"]
    starts = [0.0] + [s["until"] for s in shots[:-1]]
    evs: list[dict] = []
    rank = {"boom": 5, "impact": 4, "whoosh": 3, "hit": 2, "swish": 1, "glitch": 0}
    for k in range(1, len(shots)):
        cut, into, prev_out = starts[k], shots[k].get("in", {}), shots[k - 1].get("out", {})
        if "flash" in into:
            evs.append({"kind": "boom" if into["flash"] >= 0.3 else "impact", "at": cut})
        if "whip" in prev_out:
            frames = prev_out["whip"].get("frames", 3)
            evs.append({"kind": "whoosh", "at": cut, "dur": max(0.35, 2 * frames / fps * 2.2)})
        elif prev_out.get("whoosh"):
            evs.append({"kind": "whoosh", "at": cut, "dur": max(0.4, prev_out["whoosh"] / fps * 2.5)})
        if "punch" in into or "shake" in into:
            evs.append({"kind": "hit", "at": cut})
    for ev in spec.get("fx", []):
        if ev["kind"] in GLITCH_FX and ev["until"] - ev["at"] <= 0.8:
            evs.append({"kind": "glitch", "at": ev["at"], "dur": max(0.12, ev["until"] - ev["at"])})
    gap = float(cfg.get("min_gap", 0.18))
    evs.sort(key=lambda e: (e["at"], -rank[e["kind"]]))
    kept: list[dict] = []
    for ev in evs:
        clash = [o for o in kept if abs(o["at"] - ev["at"]) < gap]
        if not clash:
            kept.append(ev)
        elif rank[ev["kind"]] > max(rank[o["kind"]] for o in clash):
            for o in clash:
                kept.remove(o)
            kept.append(ev)
    for ev in kept:
        ev["gain"] = float(cfg.get(ev["kind"], 0.0))
    return kept


def automate(mix: np.ndarray, moves: list[dict]) -> np.ndarray:
    """The song's own effects: dips, muffles, cuts, stutters, tape stops, reversals."""
    out = mix.astype(np.float64).copy()
    for mv in moves:
        a, b = _n(mv["at"]), min(len(out), _n(mv["until"]))
        if b <= a:
            continue
        seg = out[a:b]
        kind = mv["kind"]
        if kind == "duck":  # down toward "until", back up on it (the drop hits at full level)
            depth = 10 ** (float(mv.get("db", -12)) / 20)
            if mv.get("shape", "ramp") == "ramp":
                curve = np.linspace(1.0, depth, len(seg))
            else:  # "hold": down in 30 ms, then held
                curve = np.full(len(seg), depth)
                k = min(len(seg), _n(0.03))
                curve[:k] = np.linspace(1.0, depth, k)
            out[a:b] = seg * curve[:, None]
        elif kind == "cut":
            k = min(len(seg) // 2, _n(0.008))
            g = np.zeros(len(seg))
            g[:k] = np.linspace(1, 0, k)
            g[len(seg) - k:] = np.linspace(0, 1, k)
            out[a:b] = seg * g[:, None]
        elif kind == "muffle":
            cut0 = float(mv.get("cutoff", 500))
            freqs = (lambda v: cut0 * ((18000 / cut0) ** (v ** 2))) if mv.get("open") else (lambda v: cut0)
            pad = _n(0.05)
            a0 = max(0, a - pad)
            lp = np.stack([_sweep_filter(out[a0:b, c], lambda v: freqs(max(0.0, (v * (b - a0) - (a - a0)) / (b - a))),
                                         "low") for c in range(2)], axis=1)[a - a0:]
            xf = min(len(seg) // 2, _n(0.03))
            w = np.ones(len(seg))
            w[:xf] = np.linspace(0, 1, xf)
            if not mv.get("open"):
                w[len(seg) - xf:] = np.linspace(1, 0, xf)
            out[a:b] = seg * (1 - w[:, None]) + lp * w[:, None]
        elif kind == "stutter":
            ln = max(_n(0.02), _n(float(mv.get("slice", 0.125))))
            piece = _fade(seg[:ln].copy(), ms_in=2, ms_out=4)
            reps = np.concatenate([piece] * (len(seg) // ln + 1))[:len(seg)]
            out[a:b] = reps
        elif kind == "tapestop":
            rate = np.linspace(1.0, 0.0, len(seg)) ** 1.5
            pos = np.cumsum(rate)
            idx = np.clip(pos, 0, len(seg) - 1)
            out[a:b] = np.stack([np.interp(idx, np.arange(len(seg)), seg[:, c]) for c in range(2)], axis=1)
            out[a:b] *= np.linspace(1, 0.2, len(seg))[:, None]
        elif kind == "reverse":
            out[a:b] = _fade(seg[::-1].copy(), ms_in=4, ms_out=4)
        else:
            raise SystemExit(f"unknown music move {kind!r}")
    return out


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def design(spec: dict, wav: Path, out_dir: Path) -> Path:
    """The edit's final sound: automated song + SFX, limited. Cached by its inputs."""
    events = auto_events(spec) + list(spec.get("sfx", []))
    moves = spec.get("music", [])
    if not events and not moves:
        return wav
    key = hashlib.sha1(json.dumps([str(wav), wav.stat().st_mtime, events, moves, spec.get("sfx_level", -4),
                                   Path(__file__).stat().st_mtime], sort_keys=True).encode()).hexdigest()[:12]
    out = out_dir / f"designed_{key}.wav"
    if out.exists():
        return out
    import soundfile as sf

    mix, sr = sf.read(str(wav), always_2d=True)
    assert sr == SR, f"expected {SR} Hz, got {sr}"
    music = automate(mix, moves)
    level = float(spec.get("sfx_level", -4.0))
    bus = np.zeros_like(music)
    floor = 10 ** (-30 / 20)  # quiet passages still get an audible effect
    for ev in events:
        x = make(ev)
        s = start_of(ev, len(x))
        lo, hi = max(0, s), min(len(bus), s + len(x))
        if hi <= lo:
            continue
        piece = x[lo - s:hi - s]
        around = music[max(0, lo - SR // 2):min(len(music), hi + SR // 2)]
        ref = max(_rms(around), floor)
        loud = piece[np.abs(piece).max(axis=1) > 0.1 * np.abs(piece).max()] if len(piece) else piece
        gain_db = level + DEFAULT_GAIN.get(ev["kind"], 0.0) + float(ev.get("gain", 0.0))
        bus[lo:hi] += piece * (ref / max(_rms(loud), 1e-9)) * 10 ** (gain_db / 20)
    total = music + bus
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.wav")
    sf.write(str(raw), total.astype(np.float32), SR, subtype="FLOAT")
    import subprocess

    # A true-peak limiter: impacts on top of a loud drop would otherwise clip.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                    "alimiter=limit=0.89:attack=3:release=60:level=disabled", "-c:a", "pcm_f32le", str(out)],
                   check=True)
    raw.unlink()
    print(f"sound design: {len(events)} sfx, {len(moves)} music moves -> {out.name}", flush=True)
    return out
