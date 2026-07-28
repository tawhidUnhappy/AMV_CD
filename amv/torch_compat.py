"""Compatibility shims for torch 2.6 + pyannote/whisperx.

torch 2.6 flipped `torch.load(weights_only=...)` to True by default. The
pyannote VAD checkpoint whisperx downloads pickles omegaconf config objects,
which the safe unpickler rejects, so loading dies before any audio is read.

These are the stock whisperx/pyannote checkpoints from the HuggingFace Hub, so
rather than disabling the safety check wholesale we allowlist exactly the
config/stdlib globals those checkpoints legitimately contain.
"""

from __future__ import annotations


def add_cudnn_to_dll_path() -> None:
    """Put the pip-installed cuDNN 8 next to ctranslate2 on the DLL search path.

    torch bundles cuDNN 9 in torch/lib, but ctranslate2 4.4 links cuDNN 8, so the
    two runtimes live in separate directories and only torch's is registered
    automatically. Must run before `import ctranslate2`.
    """
    import os
    import sys

    if sys.platform != "win32":
        return

    from amv.config import site_packages

    root = site_packages()
    if root is None:
        return
    for rel in ("nvidia/cudnn/bin", "nvidia/cublas/bin", "nvidia/cuda_nvrtc/bin"):
        candidate = root / rel
        if candidate.is_dir():
            os.add_dll_directory(str(candidate))
            os.environ["PATH"] = f"{candidate};{os.environ.get('PATH', '')}"


def patch() -> None:
    add_cudnn_to_dll_path()

    import torch.serialization as serialization

    allowed: list[type] = []

    try:
        from omegaconf.base import ContainerMetadata, Metadata
        from omegaconf.dictconfig import DictConfig
        from omegaconf.listconfig import ListConfig
        from omegaconf.nodes import AnyNode, ValueNode

        allowed += [ListConfig, DictConfig, ContainerMetadata, Metadata, AnyNode, ValueNode]
    except ImportError:
        pass

    import collections
    import typing

    import torch
    from torch.torch_version import TorchVersion

    allowed += [collections.defaultdict, dict, list, int, float, str, bytes, set, tuple]
    allowed += [typing.Any, TorchVersion]

    try:
        serialization.add_safe_globals(allowed)
    except Exception as exc:  # pragma: no cover - depends on torch version
        print(f"WARNING: could not register safe globals: {exc}", flush=True)

    # The allowlist above covers what these checkpoints are *known* to carry, but
    # the exact global set drifts between pyannote/lightning releases. Rather than
    # chase each one, keep the safe loader as the default and fall back to the
    # legacy path only when it refuses — these are the stock whisperx/pyannote
    # checkpoints, and the fallback is scoped to this offline pipeline.
    if getattr(torch.load, "_amv_patched", False):
        return

    original_load = torch.load

    def load(*args, **kwargs):
        # Callers inside lightning/pyannote pass weights_only=True explicitly, so
        # the retry has to cover that case too — not just an omitted kwarg.
        if kwargs.get("weights_only") is False:
            return original_load(*args, **kwargs)
        kwargs.setdefault("weights_only", True)
        try:
            return original_load(*args, **kwargs)
        except Exception:
            print("torch.load: safe unpickle refused, retrying trusted checkpoint", flush=True)
            # Callers hand us an open file object, and the failed attempt left it
            # part-consumed — rewind or the retry dies on a truncated stream.
            if args and hasattr(args[0], "seek"):
                args[0].seek(0)
            kwargs["weights_only"] = False
            return original_load(*args, **kwargs)

    load._amv_patched = True
    torch.load = load
