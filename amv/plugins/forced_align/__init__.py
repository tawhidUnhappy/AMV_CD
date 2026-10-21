"""forced_align: known words -> exact word times in a voice recording (CTC forced
alignment with torchaudio's MMS_FA model). The lyric video aligns every lyric line
inside the window whisper placed it in: whisper's own word stamps on sung vocals
ran up to 1-2 s late (2026-10-22). Runs in its own uv environment (torch 2.8 +
torchaudio 2.8, CUDA 12.8 wheels; torchaudio 2.9+ dropped parts of the alignment API).

    worker.py   job.json -> {segment key: [[start, end, score], ...]}"""

from pathlib import Path

from amv.plugins import Tool, register

register("tool", Tool("forced_align", ("torch==2.8.0+cu128", "torchaudio==2.8.0+cu128", "soundfile", "numpy"),
                      worker=str(Path(__file__).with_name("worker.py")),
                      index="https://download.pytorch.org/whl/cu128"))
