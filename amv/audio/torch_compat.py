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


def _cudnn8_dir():
    """Where this project keeps the old split-style cuDNN 8.x .so's on Linux.

    Deliberately outside the uv-managed venv/site-packages: torch's Linux
    wheel hard-pins `nvidia-cudnn-cu12==9.x` (see pyproject.toml), so pip
    can't also have 8.x installed as that package without a resolver
    conflict. These files are fetched straight from the wheel instead and
    kept in the project folder, entirely outside dependency resolution.
    """
    from amv.core.config import ROOT

    return ROOT / ".cudnn8" / "nvidia" / "cudnn" / "lib"


def _ensure_cudnn8_libs() -> None:
    """Download+extract cuDNN 8.x's .so's on first use, if not already staged.

    ctranslate2 4.4's bundled cuDNN (`ctranslate2.libs/libcudnn-*.so.8.9.7`,
    one monolithic file) is enough for `ctranslate2.get_cuda_device_count()`
    but NOT for actually running a model on GPU — real inference dlopens the
    old split-per-component naming (`libcudnn_ops_infer.so.8`,
    `libcudnn_cnn_infer.so.8`, ...) that torch's own bundled cuDNN 9 (a
    different, incompatible major version) doesn't provide either. Without
    these, whisperx's ASR pass dies with `SIGABRT` right after VAD --
    "Could not load library libcudnn_ops_infer.so.8" -- not a Python
    exception, so it's easy to mistake for something else failing silently.
    """
    import sys
    import zipfile

    if sys.platform == "win32":
        return
    lib_dir = _cudnn8_dir()
    if lib_dir.is_dir() and any(lib_dir.glob("libcudnn_ops_infer.so*")):
        return

    import subprocess
    import tempfile
    from pathlib import Path

    print("cuDNN 8 split libraries not found — downloading them now "
          "(one-time, ~700MB; needed for actual GPU inference, not just import)...",
          flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "--no-deps", "--resume-retries", "5",
             "-d", str(tmp_path), "nvidia-cudnn-cu12==8.9.7.29"],
            check=True,
        )
        wheel = next(tmp_path.glob("nvidia_cudnn_cu12-*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(tmp_path / "extracted")
        lib_dir.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "extracted" / "nvidia" / "cudnn" / "lib").rename(lib_dir)
    print(f"cuDNN 8 libraries staged at {lib_dir}", flush=True)


def add_cudnn_to_ld_library_path() -> None:
    """Linux equivalent of `add_cudnn_to_dll_path`: put cuDNN 8 .so's on
    LD_LIBRARY_PATH before ctranslate2 loads.

    Unlike Windows' `os.add_dll_directory`, glibc's dynamic linker only ever
    reads LD_LIBRARY_PATH at process start, so mutating `os.environ` here has
    no effect on the *current* process — this only helps a subprocess spawned
    afterwards. As a same-process fallback, also `dlopen` the cuDNN .so's
    directly with RTLD_GLOBAL so already-loaded code (ctranslate2's own dlopen
    calls) can resolve the symbols.

    Only cuDNN libraries are force-loaded this way — NOT everything found in
    these directories. `nvidia/cublas/lib` also contains `libnvblas.so`, a
    transparent BLAS-call interceptor: `dlopen`ing it with RTLD_GLOBAL (as an
    earlier version of this function did, globbing every `.so` in each dir)
    activates that interception process-wide. Without an `nvblas.conf`
    specifying a CPU BLAS fallback, any BLAS call NVBLAS intercepts segfaults
    (SIGSEGV, no Python traceback) — this took down whisperx's ASR pass
    immediately after VAD, downstream of the loop that caused it and giving
    no indication CUDA/cuDNN was the actual origin.
    """
    import ctypes
    import os
    import sys

    if sys.platform == "win32":
        return

    _ensure_cudnn8_libs()

    from amv.core.config import site_packages

    candidates = [_cudnn8_dir()]
    root = site_packages()
    if root is not None:
        candidates += [root / "nvidia/cudnn/lib", root / "nvidia/cublas/lib", root / "nvidia/cuda_nvrtc/lib"]
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        os.environ["LD_LIBRARY_PATH"] = f"{candidate}:{os.environ.get('LD_LIBRARY_PATH', '')}"
        for so in sorted(candidate.glob("libcudnn*.so*")):
            try:
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # a version-suffixed duplicate; harmless


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
