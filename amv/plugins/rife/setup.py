"""rife-ncnn-vulkan's setup: the pinned release zip, unpacked into <dir> (default
workspace/tools/rife). Quick when already done; --force re-downloads."""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

RELEASE = "20221029"
URL = f"https://github.com/nihui/rife-ncnn-vulkan/releases/download/{RELEASE}/rife-ncnn-vulkan-{RELEASE}-ubuntu.zip"


def home(settings: dict) -> Path:
    if settings.get("dir"):
        return Path(os.path.expandvars(settings["dir"])).expanduser()
    from amv.core import paths

    return paths.TOOLS / "rife"


def binary(settings: dict) -> Path:
    exe = home(settings) / f"rife-ncnn-vulkan-{RELEASE}-ubuntu" / "rife-ncnn-vulkan"
    if not exe.exists():
        install(settings)
    return exe


def install(settings: dict, force: bool = False) -> None:
    root = home(settings)
    exe = root / f"rife-ncnn-vulkan-{RELEASE}-ubuntu" / "rife-ncnn-vulkan"
    if exe.exists() and not force:
        return
    root.mkdir(parents=True, exist_ok=True)
    zpath = root / f"rife-{RELEASE}.zip"
    print(f"[rife] downloading {URL} (~430 MB)...", flush=True)
    subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(zpath), URL], check=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(root)
    exe.chmod(0o755)
    zpath.unlink()
    print(f"[rife] ready: {exe}", flush=True)


if __name__ == "__main__":
    import sys

    install({}, force="--force" in sys.argv)
