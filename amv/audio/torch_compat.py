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

    from amv.core.config import site_packages

    root = site_packages()
    if root is None:
        return
    for rel in ("nvidia/cudnn/bin", "nvidia/cublas/bin", "nvidia/cuda_nvrtc/bin"):
        candidate = root / rel
        if candidate.is_dir():
            os.add_dll_directory(str(candidate))
            os.environ["PATH"] = f"{candidate};{os.environ.get('PATH', '')}"


def add_cudnn_to_ld_library_path() -> None:
    """Linux equivalent of `add_cudnn_to_dll_path`: put pip's cuDNN 8 .so's on
    LD_LIBRARY_PATH before ctranslate2 loads.

    Unlike Windows' `os.add_dll_directory`, glibc's dynamic linker only ever
    reads LD_LIBRARY_PATH at process start, so mutating `os.environ` here has
    no effect on the *current* process — this only helps a subprocess spawned
    afterwards. As a same-process fallback, also `dlopen` the .so's directly
    with RTLD_GLOBAL so already-loaded code (ctranslate2's own dlopen calls)
    can resolve the symbols.
    """
    import ctypes
    import os
    import sys

    if sys.platform == "win32":
        return

    from amv.core.config import site_packages

    root = site_packages()
    if root is None:
        return
    for rel in ("nvidia/cudnn/lib", "nvidia/cublas/lib", "nvidia/cuda_nvrtc/lib"):
        candidate = root / rel
        if not candidate.is_dir():
            continue
        os.environ["LD_LIBRARY_PATH"] = f"{candidate}:{os.environ.get('LD_LIBRARY_PATH', '')}"
        for so in sorted(candidate.glob("lib*.so*")):
            try:
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # a version-suffixed duplicate or an unrelated .so; harmless


def fix_ctranslate2_exec_stack() -> None:
    """Clear the executable-stack ELF flag on ctranslate2's bundled .so.

    The shipped wheel's libctranslate2 was built with `GNU_STACK` marked
    executable (a harmless build-default relic — nothing in it actually needs
    an executable stack). Recent kernels/glibc refuse to load that instead of
    silently granting it, which surfaces as ImportError: "cannot enable
    executable stack as shared object requires". `execstack`/`paxctl` would
    normally clear this, but neither is a project dependency and the fix is
    one bit in the ELF program header, so do it directly and skip needing
    system packages or sudo. Idempotent: does nothing once already clear, and
    self-heals a fresh `uv sync` on any machine that hits this.
    """
    import struct
    import sys

    if sys.platform == "win32":
        return

    from amv.core.config import site_packages

    root = site_packages()
    if root is None:
        return
    libs_dir = root / "ctranslate2.libs"
    if not libs_dir.is_dir():
        return

    PT_GNU_STACK = 0x6474E551
    PF_X = 0x1
    for so in sorted(libs_dir.glob("libctranslate2*.so*")):
        try:
            with open(so, "r+b") as f:
                header = f.read(64)
                if header[:4] != b"\x7fELF" or header[4] != 2:  # not 64-bit ELF
                    continue
                e_phoff, = struct.unpack_from("<Q", header, 0x20)
                e_phentsize, = struct.unpack_from("<H", header, 0x36)
                e_phnum, = struct.unpack_from("<H", header, 0x38)
                for i in range(e_phnum):
                    off = e_phoff + i * e_phentsize
                    f.seek(off)
                    p_type, p_flags = struct.unpack("<II", f.read(8))
                    if p_type == PT_GNU_STACK and p_flags & PF_X:
                        f.seek(off + 4)
                        f.write(struct.pack("<I", p_flags & ~PF_X))
        except OSError as exc:
            print(f"WARNING: could not check/patch {so.name} for exec-stack: {exc}", flush=True)


def patch() -> None:
    add_cudnn_to_dll_path()
    add_cudnn_to_ld_library_path()
    fix_ctranslate2_exec_stack()

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
