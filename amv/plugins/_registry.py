"""One registry per kind of plug-in, and the lazy references plug-ins point
at their code with.

A plug-in is registered as a small, frozen description (see _kinds.py) whose
code is named by REFERENCE - "amv.plugins.demucs.separate:isolate" - not
imported, so registering imports nothing heavy and `./amv.sh list` stays
instant."""

from __future__ import annotations

import importlib
from typing import Any

KINDS = ("command", "tool", "separator", "transcriber", "song_fx", "video_fx")

_registry: dict[str, dict[str, Any]] = {kind: {} for kind in KINDS}
# Where each plug-in came from, for `./amv.sh plugins`.
_origin: dict[tuple[str, str], str] = {}
_current_origin = ["built-in"]


def register(kind: str, item: Any) -> Any:
    """Adds `item` (anything with a `name`) under `kind`. A later plug-in with
    the same name replaces an earlier one - that is how a drop-in plug-in
    overrides a built-in. Returns the item."""
    if kind not in _registry:
        raise ValueError(f"No plug-in kind '{kind}' - the kinds are {', '.join(KINDS)}")
    _registry[kind][item.name] = item
    _origin[(kind, item.name)] = _current_origin[0]
    return item


def items(kind: str) -> list[Any]:
    """Every plug-in of `kind`, in their `order` (then name): the first one
    is the kind's default."""
    from amv.plugins._loader import load

    load()
    return sorted(_registry[kind].values(), key=lambda item: (getattr(item, "order", 100), item.name))


def names(kind: str) -> tuple[str, ...]:
    return tuple(item.name for item in items(kind))


def find(kind: str, name: str | None) -> Any | None:
    """The plug-in of `kind` called `name`, or None."""
    items(kind)
    return _registry[kind].get((name or "").strip())


def get(kind: str, name: str | None = None) -> Any:
    """The plug-in called `name`; with no name, the kind's first one. An
    unknown name is an error that lists what is installed."""
    if name:
        found = find(kind, name)
        if found is None:
            raise SystemExit(f"No {kind} plug-in {name!r} - installed: {', '.join(names(kind)) or 'none'}")
        return found
    every = items(kind)
    if not every:
        raise SystemExit(f"No '{kind}' plug-in is installed")
    return every[0]


def origin(kind: str, name: str) -> str:
    return _origin.get((kind, name), "?")


def resolve(ref: Any) -> Any:
    """The object a reference names ("package.module:attr"); anything that
    isn't a string is already the object."""
    if not isinstance(ref, str):
        return ref
    module, _, attr = ref.partition(":")
    target: Any = importlib.import_module(module)
    for part in filter(None, attr.split(".")):
        target = getattr(target, part)
    return target


def call(ref: Any, *args: Any, **kwargs: Any) -> Any:
    return resolve(ref)(*args, **kwargs)
