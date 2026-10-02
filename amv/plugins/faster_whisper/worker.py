"""faster-whisper over a list of wav files -> word timings (JSON on stdout).

Runs in the faster_whisper tool environment (amv/plugins/faster_whisper): CTranslate2,
no torch. The cuDNN/cuBLAS wheels are loaded by path before ctranslate2 is
imported, since their lib folders are not on the loader path in a uv env.

    python dub_worker.py MODEL a.wav b.wav ...   ->   {"a.wav": [[start, end, "word"], ...], ...}
"""

from __future__ import annotations

import ctypes
import glob
import json
import os
import sys

os.environ.setdefault("TQDM_DISABLE", "1")


def preload_cuda() -> None:
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return
    for pkg in (nvidia.cublas, nvidia.cudnn):
        for lib in sorted(glob.glob(os.path.join(list(pkg.__path__)[0], "lib", "lib*.so*"))):
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def main() -> None:
    model_name, wavs = sys.argv[1], sys.argv[2:]
    preload_cuda()
    import ctranslate2
    from faster_whisper import WhisperModel

    cuda = ctranslate2.get_cuda_device_count() > 0
    model = WhisperModel(model_name, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")
    out = {}
    for wav in wavs:
        # No VAD (it drops quiet real words) and no conditioning on previous
        # text (it loops) - the same settings remanga settled on.
        segments, _ = model.transcribe(wav, language="en", word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False, beam_size=5)
        out[wav] = [[round(w.start, 3), round(w.end, 3), w.word.strip()] for s in segments for w in (s.words or [])]
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    main()
