"""Set up tool environments ahead of time (each also sets itself up on first use).

    ./amv.sh tool-setup                 # every tool that sets itself up
    ./amv.sh tool-setup ace_step        # one
    ./amv.sh tool-setup ace_step --force --no-weights

Package-list tools are built by uv on first use and need nothing here."""

from __future__ import annotations

import argparse

from amv import plugins
from amv.core import tools


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="tool names (default: all that set themselves up)")
    parser.add_argument("--force", action="store_true", help="rebuild the environment even if current")
    parser.add_argument("--no-weights", action="store_true", help="environment only, no model download")
    args = parser.parse_args()

    names = args.names or [t.name for t in plugins.items("tool") if t.install]
    for name in names:
        tool = plugins.get("tool", name)
        if not tool.install:
            print(f"{name}: a package-list tool - uv builds it on first use")
            continue
        print(f"== {name}")
        tools.ensure(name, force=args.force, weights=not args.no_weights)
        print(f"{name}: ready")


if __name__ == "__main__":
    main()
