"""Flow: order shots so each cut continues a movement (AMV_EDITING_GUIDE.md section 3,
Molob: clips should read like a sentence, not random words).

A pool entry needs `./amv.sh flow` fields: head/tail motion [x, y] (picture fractions
per second, +x = content moves right), strength, focus_head/focus_tail. A "link"
score for A -> B rewards:
  - motion continuity: A's tail direction carried on by B's head (cosine, weighted by
    how much they move); B may be mirrored (x negated) when that makes it continue;
  - eye trace: B's focal point near where A's was.
`sequence` fills slots in order with a small beam search over link + energy fit
(intense slots want strong movers), then `transition` picks each cut's device:
a whip along a strong outgoing motion, a punch on hard hits, or a plain cut when
the motion already carries it."""

from __future__ import annotations

import math


def _vec(v: list[float], flip: bool) -> tuple[float, float]:
    return (-v[0], v[1]) if flip else (v[0], v[1])


def _focus(p: list[float] | None, flip: bool) -> tuple[float, float]:
    p = p or [0.5, 0.5]
    return (1 - p[0], p[1]) if flip else (p[0], p[1])


def link(a: dict, b: dict, flip_a: bool = False, flip_b: bool = False) -> float:
    ta, hb = _vec(a.get("tail", [0, 0]), flip_a), _vec(b.get("head", [0, 0]), flip_b)
    na, nb = math.hypot(*ta), math.hypot(*hb)
    s_dir = 0.0
    if na > 0.04 and nb > 0.04:
        cos = (ta[0] * hb[0] + ta[1] * hb[1]) / (na * nb)
        s_dir = cos * min(1.0, (na + nb) / 0.5)
    fa, fb = _focus(a.get("focus_tail"), flip_a), _focus(b.get("focus_head"), flip_b)
    s_eye = 1 - min(1.0, math.dist(fa, fb) / 0.5)
    return 1.5 * s_dir + 0.8 * s_eye - (0.08 if flip_b else 0.0)


def fit(entry: dict, slot: dict) -> float:
    """How well a shot's energy suits the slot: intense slots want strong movement."""
    s = min(1.0, entry.get("strength", 0.0) / 0.6)
    want = 1.0 if slot.get("mood") == "intense" else 0.25
    mood = 0.6 if entry.get("mood", slot.get("mood")) == slot.get("mood") else -0.6
    return mood - abs(s - want)


def sequence(pool: list[dict], slots: list[dict], beam: int = 8, allow_flip: bool = True) -> list[tuple[dict, bool]]:
    """One (entry, flipped) per slot, each entry used once, maximising links + fit."""
    beams: list[tuple[float, list[tuple[int, bool]]]] = [(0.0, [])]
    for slot in slots:
        nxt = []
        for score, path in beams:
            used = {i for i, _ in path}
            prev = (pool[path[-1][0]], path[-1][1]) if path else None
            options = []
            for i, e in enumerate(pool):
                if i in used or e.get("duration", 9) < slot.get("need", 0):
                    continue
                for flip in ((False, True) if allow_flip and not e.get("no_flip") else (False,)):
                    s = fit(e, slot) * 1.2
                    if prev:
                        s += link(prev[0], e, prev[1], flip)
                    options.append((s, i, flip))
            options.sort(reverse=True)
            for s, i, flip in options[:beam]:
                nxt.append((score + s, path + [(i, flip)]))
        nxt.sort(key=lambda x: -x[0])
        beams = nxt[:beam] or beams
    best = beams[0][1]
    return [(pool[i], flip) for i, flip in best]


def transition(a: dict, b: dict, flip_a: bool, flip_b: bool, slot: dict) -> dict:
    """The cut's device: {"out": {...}} on the outgoing shot and/or {"in": {...}} on the next."""
    ta = _vec(a.get("tail", [0, 0]), flip_a)
    na = math.hypot(*ta)
    carried = link(a, b, flip_a, flip_b) > 1.2
    dev: dict = {}
    if na > 0.22 and not carried:
        # whip along the outgoing motion: the movement itself carries the eye over
        dev["out"] = {"whip": {"dir": [round(ta[0] / na, 2), round(ta[1] / na, 2)], "frames": 3}}
    elif slot.get("mood") == "intense" and slot.get("downbeat") and not carried:
        dev["in"] = {"punch": 1.12, "frames": 5, "rgb": 10}
    return dev
