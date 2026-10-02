"""`./amv.sh plugins`: every installed plug-in by kind, where it came from
(built-in, plugins/<file>, an entry point), and any that failed to load."""

from __future__ import annotations

from amv import plugins


def main() -> None:
    for kind in plugins.KINDS:
        found = plugins.items(kind)
        print(f"{kind} ({len(found)})")
        for item in found:
            text = getattr(item, "summary", None) or getattr(item, "help", None) or getattr(item, "label", "")
            print(f"  {item.name:20s} {text}  [{plugins.origin(kind, item.name)}]")
    for where, why in plugins.failures():
        print(f"FAILED {where}: {why}")


if __name__ == "__main__":
    main()
