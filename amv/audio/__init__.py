"""Audio-side pipeline: vocal isolation, transcription, beat detection, lyrics.

The only two GPU/CUDA workloads in the whole project (Demucs and WhisperX)
live here, alongside the torch/Windows compatibility shims (`torch_compat`)
and the centralized device selection (`device`) they both use. This
subpackage's submodules are intentionally *not* re-exported here: each is a
standalone CLI entry point (`python -m amv.audio.<name>`) with heavy,
optional dependencies (torch, demucs, whisperx, librosa), so importing
`amv.audio` itself must stay cheap and dependency-free.
"""

from __future__ import annotations
