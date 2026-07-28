"""Flag words whose alignment looks smeared (long duration + low confidence).

Held/reverbed vocals make wav2vec2 stretch a word across an instrumental bar,
which would leave lyric text hanging on screen long before it is sung.
"""

from __future__ import annotations


import numpy as np

from amv.lyrics import load_words


def main() -> None:
    words = load_words()

    print("suspicious words (duration > 1.2s):")
    for i, w in enumerate(words):
        dur = w["end"] - w["start"]
        if dur > 1.2:
            print(f"  {i:3d}  {w['start']:7.2f}->{w['end']:7.2f} ({dur:5.2f}s) score={w.get('score', 0):.2f}  {w['word']!r}")

    # Cross-check against raw audio loudness: a genuinely held note keeps energy
    # up across the span, a smeared one sits over a quiet/instrumental bar.
    import whisperx

    from amv.config import load as load_config

    audio = whisperx.load_audio(str(load_config().require_song()))
    sr = 16000

    def rms_db(start: float, end: float) -> float:
        chunk = audio[int(start * sr) : int(end * sr)]
        if chunk.size == 0:
            return -99.0
        return float(20 * np.log10(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)) + 1e-9))

    print("\nloudness around the questionable spans:")
    for label, a, b in [
        ("verse2 held 'Your mouth'", 70.0, 79.3),
        ("verse2 sung line", 79.4, 81.5),
        ("bridge held 'If'", 138.9, 146.7),
        ("bridge sung line", 147.1, 149.3),
        ("known instrumental", 121.0, 129.0),
        ("known vocal (chorus)", 102.0, 104.3),
    ]:
        print(f"  {label:26s} {a:6.1f}-{b:6.1f}  {rms_db(a, b):6.2f} dBFS")


if __name__ == "__main__":
    main()
