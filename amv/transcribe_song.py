"""Transcribe the AMV song with WhisperX to get word-level timestamps.

Word timings are what let the lyric overlay land on the beat, so the alignment
pass (not just the ASR pass) is the part that matters here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIO = ROOT / "assets" / "black_salt_halo.mp3"
DEFAULT_OUT = ROOT / "data" / "song" / "transcript.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    from amv import torch_compat

    torch_compat.patch()

    import whisperx

    print(f"Loading {args.model} on {args.device} ({args.compute_type})...", flush=True)
    model = whisperx.load_model(
        args.model,
        args.device,
        compute_type=args.compute_type,
        language=args.language,
    )

    audio = whisperx.load_audio(str(args.audio))
    duration = len(audio) / 16000.0
    print(f"Audio: {args.audio.name}  {duration:.2f}s", flush=True)

    result = model.transcribe(audio, batch_size=args.batch_size, language=args.language)
    print(f"ASR pass: {len(result['segments'])} segments", flush=True)

    # Free the ASR weights before the alignment model loads — 12GB card, and
    # wav2vec2 alongside large-v3 is the usual OOM here.
    del model
    import gc
    import torch

    gc.collect()
    torch.cuda.empty_cache()

    align_model, metadata = whisperx.load_align_model(language_code=args.language, device=args.device)
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        audio,
        args.device,
        return_char_alignments=False,
    )
    print(f"Alignment pass: {len(aligned['segments'])} segments", flush=True)

    payload = {
        "audio": str(args.audio),
        "duration": duration,
        "language": args.language,
        "model": args.model,
        "segments": aligned["segments"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out}", flush=True)

    for seg in aligned["segments"]:
        print(f"  [{seg['start']:7.2f} -> {seg['end']:7.2f}] {seg['text'].strip()}", flush=True)


if __name__ == "__main__":
    main()
