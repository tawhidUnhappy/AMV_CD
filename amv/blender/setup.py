"""Set up Blender for Claude: the MCP add-on, free extensions and asset-library keys.

    ./amv.sh blender-setup                # add-on + extensions (Blender must be closed)
    ./amv.sh blender-setup --keys         # also ask for Sketchfab / Poly Pizza keys
    ./amv.sh blender-setup --check        # report only; safe while Blender is open

Everything is written to Blender's own user preferences. It runs Blender headless,
so Blender has to be closed: a running Blender saves its preferences on quit and
would overwrite what this wrote. The Claude Code side is the repo's .mcp.json.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

from amv.core import config, paths

ADDON_URL = "https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py"
ADDON_MODULE = "blender_mcp"
MCP_PORT = 9876

# Free, from extensions.blender.org (ids as `blender -c extension list` prints them).
EXTENSIONS = (
    # assets + building
    "ambientcg_material_importer", "extra_mesh_objects", "extra_curve_objectes", "Bagapie",
    "PlaceHelper", "bool_tool", "looptools", "dynamic_sky", "antlandscape",
    # music timing
    "audio_trigger_lite", "frames_per_beat", "nla_midi_copier", "simple_audio_visualizer",
    "timeline_audio_visualizer",
    # motion + repeating animation
    "commotion", "animall", "camera_shakify", "handheld_loop", "easeit", "momentum",
    "randomize_noise_offset",
)
BUILTIN_ADDONS = ("node_wrangler", "rigify")  # ship with Blender, off by default
KEY_PREFS = {"sketchfab_api_key": "Sketchfab API token (sketchfab.com/settings/password)",
             "polypizza_api_key": "Poly Pizza API key (poly.pizza/settings/api)"}

INSTALL_HINT = {
    "Linux": "sudo snap install blender --classic",
    "Windows": "winget install BlenderFoundation.Blender",
    "Darwin": "brew install --cask blender",
}

# Runs inside Blender (`--python-expr`); the job comes in through AMV_BLENDER_JOB.
_IN_BLENDER = r'''
import bpy, addon_utils, json, os
job = json.loads(os.environ["AMV_BLENDER_JOB"])
prefs = bpy.context.preferences
out = {"errors": []}
if not job["check"]:
    prefs.system.use_online_access = True
    if job["addon"]:
        bpy.ops.preferences.addon_install(filepath=job["addon"], overwrite=True)
    try:
        bpy.ops.extensions.repo_refresh_all()
    except Exception as e:
        out["errors"].append(f"refresh: {e}")
    for mod in job["modules"]:
        try:
            addon_utils.enable(mod, default_set=True, handle_error=None)
        except Exception as e:
            out["errors"].append(f"{mod}: {e}")
    if job["keys"] and job["addon_module"] in prefs.addons:
        p = prefs.addons[job["addon_module"]].preferences
        for k, v in job["keys"].items():
            setattr(p, k, v)
    bpy.ops.wm.save_userpref()
out["enabled"] = [m for m in job["modules"] + [job["addon_module"]] if addon_utils.check(m)[1]]
out["online"] = bool(prefs.system.use_online_access)
a = prefs.addons.get(job["addon_module"])
out["keys"] = {k: bool(a and getattr(a.preferences, k, "")) for k in job["key_names"]}
print("AMV_BLENDER_RESULT " + json.dumps(out))
'''


def find_blender() -> Path | None:
    """config.json "blender", then PATH, then the usual install places per OS."""
    own = config.load().raw.get("blender")
    if own:
        path = Path(os.path.expandvars(own)).expanduser()
        return path if path.is_file() else None
    found = shutil.which("blender")
    if found:
        return Path(found)
    places = [Path("/snap/bin/blender"), Path("/Applications/Blender.app/Contents/MacOS/Blender")]
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:  # newest "Blender 5.x" folder first
            places += sorted(Path(root, "Blender Foundation").glob("Blender*/blender.exe"), reverse=True)
    return next((p for p in places if p.is_file()), None)


def blender_version(blender: Path) -> str:
    out = subprocess.run([str(blender), "--version"], capture_output=True, text=True, timeout=120)
    return next((line for line in out.stdout.splitlines() if line.startswith("Blender")), "unknown")


def mcp_connected() -> bool:
    """Is a Blender listening for Claude (the add-on's "Connect to Claude")?"""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("localhost", MCP_PORT)) == 0


def blender_running() -> bool:
    if mcp_connected():
        return True
    if platform.system() == "Windows":
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq blender.exe"], capture_output=True, text=True)
        return "blender.exe" in out.stdout.lower()
    return subprocess.run(["pgrep", "-x", "blender"], capture_output=True).returncode == 0


def download_addon() -> Path:
    dest = paths.BLENDER / f"{ADDON_MODULE}.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ADDON_URL, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def install_extensions(blender: Path, ids: list[str]) -> list[str]:
    """Download + unpack from extensions.blender.org. Returns the ids that failed."""
    if not ids:
        return []
    cmd = [str(blender), "--online-mode", "-c", "extension", "install", "-s", "--no-prefs", ",".join(ids)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    done = {line.split('"')[1] for line in out.stdout.splitlines() if line.startswith("STATUS Installed")}
    ext_dir = extensions_dir(blender)  # already installed earlier counts as done
    return [i for i in ids if i not in done and not (ext_dir / i).is_dir()]


def extensions_dir(blender: Path) -> Path:
    """The user's extensions.blender.org folder, from Blender itself."""
    out = subprocess.run([str(blender), "-c", "extension", "repo-list"], capture_output=True, text=True, timeout=120)
    lines = out.stdout.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "blender_org:":
            for nxt in lines[i + 1:i + 6]:
                if nxt.strip().startswith("directory:"):
                    return Path(nxt.split('"')[1])
    return Path()


def run_in_blender(blender: Path, job: dict) -> dict:
    env = dict(os.environ, AMV_BLENDER_JOB=json.dumps(job))
    out = subprocess.run([str(blender), "-b", "--python-expr", _IN_BLENDER],
                         capture_output=True, text=True, env=env, timeout=600)
    for line in out.stdout.splitlines():
        if line.startswith("AMV_BLENDER_RESULT "):
            return json.loads(line.split(" ", 1)[1])
    raise SystemExit(f"Blender did not report back:\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}")


def ask_keys() -> dict:
    print("Paste each key (input is hidden). Leave blank to keep the current one.")
    keys = {k: getpass.getpass(f"  {label}: ").strip() for k, label in KEY_PREFS.items()}
    return {k: v for k, v in keys.items() if v}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report the setup; change nothing")
    parser.add_argument("--keys", action="store_true", help="ask for the Sketchfab / Poly Pizza API keys")
    parser.add_argument("--no-extensions", action="store_true", help="only the MCP add-on")
    parser.add_argument("--extensions", help="comma-separated extension ids instead of the default set")
    args = parser.parse_args()

    blender = find_blender()
    if not blender:
        hint = INSTALL_HINT.get(platform.system(), "download it from https://www.blender.org/download/")
        raise SystemExit(f"Blender not found. Install it ({hint}), or set \"blender\" in config.json "
                         f"to the Blender executable.")
    print(f"Blender : {blender}  ({blender_version(blender)})")
    if not shutil.which("uvx"):
        print("uvx     : MISSING - install uv (https://docs.astral.sh/uv/); Claude starts the MCP server with it")

    ids = [] if args.no_extensions else (args.extensions.split(",") if args.extensions else list(EXTENSIONS))
    modules = [f"bl_ext.blender_org.{i}" for i in ids] + ([] if args.no_extensions else list(BUILTIN_ADDONS))
    job = {"check": args.check, "addon": None, "addon_module": ADDON_MODULE, "modules": modules,
           "keys": {}, "key_names": list(KEY_PREFS)}

    if not args.check:
        if blender_running():
            raise SystemExit("Close Blender first: it saves its preferences on quit and would undo this. "
                             "(--check works while it is open.)")
        job["addon"] = str(download_addon())
        print(f"Add-on  : downloaded {ADDON_URL}")
        failed = install_extensions(blender, ids)
        if failed:
            print(f"NOT installed (not on extensions.blender.org for this Blender?): {', '.join(failed)}")
            modules[:] = [m for m in modules if m.rsplit(".", 1)[-1] not in failed]
        if args.keys:
            job["keys"] = ask_keys()

    result = run_in_blender(blender, job)
    enabled = set(result["enabled"])
    print(f"MCP add-on : {'on' if ADDON_MODULE in enabled else 'NOT INSTALLED'}")
    print(f"Extensions : {len([m for m in modules if m in enabled])}/{len(modules)} on"
          + "".join(f"\n  off: {m.rsplit('.', 1)[-1]}" for m in modules if m not in enabled))
    print(f"Online access: {'on' if result['online'] else 'off (extensions and asset libraries cannot download)'}")
    print("API keys   : " + ", ".join(f"{k.split('_')[0]} {'set' if v else 'not set'}"
                                      for k, v in result["keys"].items()))
    print(f"Connected  : {'yes - Claude can use Blender now' if mcp_connected() else 'no'} (port {MCP_PORT})")
    for err in result["errors"]:
        print(f"  error: {err}", file=sys.stderr)
    if not args.check:
        print("\nNext: open Blender, press N, tab 'MCP for Blender', click 'Connect to Claude'.\n"
              "Then restart Claude Code in this folder and approve the 'blender' MCP server (.mcp.json).")


if __name__ == "__main__":
    main()
