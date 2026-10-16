"""A song's timing in video frames, for keyframing music-synced Blender animation.

    ./amv.sh blender-beats SONG [--fps 30] [--out FILE]

Writes JSON (default workspace/tmp/blender/<song>.beats.json), every time in seconds
AND Blender frames (frame 1 = 0 s): tempo_bpm, beats (beat_in_bar 1-4 guessed),
onsets (drum hits / note starts), sections (where the song changes), and per-frame
envelopes 0..1: rms (loudness), bass, mid, high.

Beats follow rises in actual bass loudness, not librosa's dB onset curve alone: on a
120 BPM kick + hi-hat test the dB curve put every beat on the hi-hats (quiet hats
jump as far in dB as kicks). Sections are clustered per beat, not per STFT hop
(per-hop clustering put the one boundary at 0.2 s instead of 20 s).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from amv.core import paths


def _norm(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    lo, hi = np.percentile(x, 2), np.percentile(x, 98)
    return np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)


def analyse(song: Path, fps: float) -> dict:
    import librosa

    y, sr = librosa.load(str(song), sr=22050, mono=True)
    dur = len(y) / sr
    hop = 256

    def frame(t: float) -> int:
        return int(round(t * fps)) + 1

    S = np.abs(librosa.stft(y, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr)

    def band(lo: float, hi: float) -> np.ndarray:
        return S[(freqs >= lo) & (freqs < hi)].sum(axis=0)

    bass = band(20, 250)
    full_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    bass_flux = np.maximum(0, np.diff(bass, prepend=bass[0]))
    _, beat_f = librosa.beat.beat_track(onset_envelope=_norm(full_env) + 3 * _norm(bass_flux),
                                        sr=sr, hop_length=hop, trim=False)
    beat_t = librosa.frames_to_time(beat_f, sr=sr, hop_length=hop)
    tempo = 60 / float(np.median(np.diff(beat_t))) if len(beat_t) > 1 else 0.0
    onset_t = librosa.onset.onset_detect(onset_envelope=full_env, sr=sr, hop_length=hop, units="time")

    # Downbeat guess: the beat phase (of 4) whose beats carry the most bass.
    phase = int(np.argmax([bass[beat_f[p::4]].mean() for p in range(4)])) if len(beat_f) >= 8 else 0

    sec_t = np.array([0.0])
    if len(beat_f) >= 8:
        feats = librosa.util.normalize(np.vstack([
            librosa.feature.mfcc(y=y, sr=sr, hop_length=hop),
            librosa.feature.chroma_stft(S=S**2, sr=sr, hop_length=hop)]), axis=1)
        per_beat = librosa.util.sync(feats, beat_f, aggregate=np.median)
        k = min(max(2, int(dur // 15)), per_beat.shape[1] - 1)  # ~one section per 15 s
        starts = np.concatenate([[0], beat_f])  # per_beat column i starts at starts[i]
        sec_t = librosa.frames_to_time(starts[librosa.segment.agglomerative(per_beat, k)], sr=sr, hop_length=hop)

    t_stft = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
    t_vid = np.arange(int(np.ceil(dur * fps))) / fps

    def env(x) -> list[float]:
        return [round(float(v), 3) for v in np.interp(t_vid, t_stft, _norm(x))]

    return {
        "song": str(song.resolve()),
        "duration": round(dur, 3),
        "fps": fps,
        "frame_count": len(t_vid),
        "tempo_bpm": round(tempo, 2),
        "beats": [{"t": round(float(t), 3), "frame": frame(t), "beat_in_bar": (i - phase) % 4 + 1}
                  for i, t in enumerate(beat_t)],
        "onsets": [{"t": round(float(t), 3), "frame": frame(t)} for t in onset_t],
        "sections": [{"t": round(float(t), 3), "frame": frame(t)} for t in sec_t],
        "envelopes": {"rms": env(librosa.feature.rms(S=S)[0]), "bass": env(bass),
                      "mid": env(band(250, 2000)), "high": env(band(2000, 11025))},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("song", type=Path)
    parser.add_argument("--fps", type=float, default=30, help="the Blender scene's frame rate (default 30)")
    parser.add_argument("--out", type=Path, help="default: workspace/tmp/blender/<song>.beats.json")
    args = parser.parse_args()
    if not args.song.is_file():
        raise SystemExit(f"song not found: {args.song}")

    data = analyse(args.song, args.fps)
    out = args.out or paths.BLENDER / f"{args.song.stem}.beats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data), encoding="utf-8")
    beats = data["beats"]
    span = f" from {beats[0]['t']:.2f}s to {beats[-1]['t']:.2f}s" if beats else ""
    print(f"tempo   : {data['tempo_bpm']} BPM")
    print(f"beats   : {len(beats)}{span}")
    print(f"onsets  : {len(data['onsets'])}   sections at: "
          + ", ".join(f"{s['t']:.1f}s" for s in data["sections"]))
    print(f"frames  : {data['frame_count']} @ {args.fps} fps")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
