"""Prove a refactor changed nothing: snapshot the pipeline's outputs, change
the code, check them again.

    ./amv.sh regress snapshot            # before touching anything
    ./amv.sh regress check               # after: every output compared
    ./amv.sh regress check --quick       # skip select (the slow one, ~3 min)

What it runs, each into its own folder under tmp/regress/:
  timeline  - the printed cut schedule
  select    - a fresh EDL (--out, so tmp/edl.json is never touched); compared
              slot by slot, ignoring the song path
  lyrics    - the ASS overlay built from tmp/edl.json
  remake    - every committed remake spec built into a plan against
              tmp/intro/reference_map.json, when that map exists (no render)

A deliberate behaviour change shows up as a difference too; that is the
point. Snapshot again once it is the new normal.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from amv.core import paths
from amv.core.config import ROOT

REGRESS = paths.TMP / "regress"


def run(args: list[str], out: Path | None = None) -> str:
    result = subprocess.run([sys.executable, "-m", "amv", *args], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"`amv {' '.join(args)}` failed:\n{result.stderr[-2000:]}")
    if out is not None:
        out.write_text(result.stdout, encoding="utf-8")
    return result.stdout


def produce(where: Path, quick: bool) -> list[str]:
    where.mkdir(parents=True, exist_ok=True)
    made = []
    run(["timeline"], where / "timeline.txt")
    made.append("timeline.txt")
    run(["lyrics", "--out", str(where / "lyrics.ass")])
    made.append("lyrics.ass")
    if not quick:
        run(["select", "--candidates", "8", "--out", str(where / "edl.json")])
        made.append("edl.json")
    reference_map = paths.INTRO / "reference_map.json"
    if reference_map.exists():
        from amv.intro.remake import build_plan

        frames = json.loads(reference_map.read_text(encoding="utf-8"))["frames"]
        for spec_path in sorted((ROOT / "amv" / "intro" / "remakes").glob("*.json")):
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            try:
                plan = build_plan(spec, frames, Path("song"))
            except SystemExit as err:  # the map is from another video
                plan = {"not built": str(err)}
            name = f"remake_{spec_path.stem}.json"
            (where / name).write_text(json.dumps(plan, indent=0, sort_keys=True), encoding="utf-8")
            made.append(name)
    return made


def same(a: Path, b: Path) -> bool:
    if a.suffix == ".json" and a.name == "edl.json":
        return json.loads(a.read_text())["slots"] == json.loads(b.read_text())["slots"]
    return a.read_bytes() == b.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["snapshot", "check"])
    parser.add_argument("--quick", action="store_true", help="skip select, the slow one")
    args = parser.parse_args()

    if args.action == "snapshot":
        made = produce(REGRESS / "snapshot", args.quick)
        print(f"Snapshot of {', '.join(made)} in {REGRESS / 'snapshot'}")
        return
    snapshot = REGRESS / "snapshot"
    if not snapshot.is_dir():
        raise SystemExit("No snapshot yet - run `./amv.sh regress snapshot` before changing the code.")
    made = produce(REGRESS / "current", args.quick)
    failed = []
    for name in made:
        before = snapshot / name
        if not before.exists():
            print(f"  new     {name} (not in the snapshot)")
        elif same(before, REGRESS / "current" / name):
            print(f"  same    {name}")
        else:
            print(f"  CHANGED {name}   (diff {before} {REGRESS / 'current' / name})")
            failed.append(name)
    if failed:
        raise SystemExit(f"{len(failed)} output(s) changed")
    print("Nothing changed.")


if __name__ == "__main__":
    main()
