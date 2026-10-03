"""RoFormer vocals over a list of wavs, several models averaged.

Runs in the audio_separator tool environment. Each model is loaded once
and runs over every input; the vocals of all models are then averaged.

    python worker.py MODEL_DIR OVERLAP m1.ckpt,m2.ckpt in1.wav out1.wav in2.wav out2.wav ...
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")


def main() -> None:
    import numpy as np
    import soundfile as sf
    from audio_separator.separator import Separator

    model_dir, overlap, names, pairs = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(","), sys.argv[4:]
    ins, outs = pairs[::2], pairs[1::2]
    acc: list[np.ndarray | None] = [None] * len(ins)
    with tempfile.TemporaryDirectory() as tmp:
        sep = Separator(log_level=logging.WARNING, model_file_dir=model_dir, output_dir=tmp,
                        output_format="WAV", output_single_stem="Vocals", sample_rate=44100,
                        mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                                     "batch_size": 1, "overlap": overlap, "pitch_shift": 0})
        for name in names:
            sep.load_model(model_filename=name)
            for k, src in enumerate(ins):
                made = sep.separate(src, {"Vocals": f"{Path(name).stem}_{k}"})
                path = Path(made[0]) if Path(made[0]).is_absolute() else Path(tmp) / made[0]
                data, sr = sf.read(str(path), dtype="float32", always_2d=True)
                n = sf.info(src).frames
                data = np.pad(data, ((0, max(0, n - len(data))), (0, 0)))[:n]
                acc[k] = data if acc[k] is None else acc[k] + data
                path.unlink()
            print(f"{name}: {len(ins)} clip(s)", flush=True)
    for k, dst in enumerate(outs):
        sf.write(dst, acc[k] / len(names), 44100, subtype="FLOAT")
        print(dst, flush=True)


if __name__ == "__main__":
    main()
