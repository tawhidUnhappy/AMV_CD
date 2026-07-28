"""Fill every timeline slot with a source moment and write the EDL.

Selection combines three signals:

1. *Story arc*  - each section draws from its own episode range, so the video
   walks the series forward instead of shuffling all 26 episodes uniformly.
2. *Theme*      - lyric slots score subtitle dialogue against per-line keywords
   and a preferred speaker, so lines land on footage that means something.
3. *Visuals*    - every shortlisted window is decoded small and scored for
   brightness, contrast and motion, which rejects black frames, fades and
   static talking heads that would read as dead air in an AMV.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from amv.timeline import SECTION_EPISODES, Slot, build_slots

ROOT = Path(__file__).resolve().parent.parent
SCENE_INDEX = ROOT / "data" / "subs" / "scene_index.json"
EDL_PATH = ROOT / "data" / "edl.json"

# Trim episode head/tail: studio logos, "previously on", and — the big one —
# the post-ED "Murmur's Counseling Room" omake plus the next-episode preview,
# which together occupy roughly the last minute and a half. A 25s tail let SD
# comedy segments and title cards into the edit.
HEAD_SKIP = 12.0
TAIL_SKIP = 95.0
# A dialogue-free stretch this long is the OP or ED credit sequence.
CREDITS_GAP = 80.0
# Keep picks apart so the same shot never appears twice.
MIN_SEPARATION = 9.0

SPEAKER_YUNO = "Yun"
SPEAKER_YUKI = "Yuk"

# Anchoring shots to a named main-cast line keeps the camera on a character.
# Dialogue-free stretches turned out to be establishing shots — streets, trees,
# signage — rather than the action the first pass assumed.
MAIN_SPEAKERS = {"Yuk", "Yun", "Aki", "Mur", "Min", "Ury", "Kur", "Nis", "Hin", "Kou",
                 "Mar", "Tsu", "Deu", "Rei", "Hir", "Mao", "Ai", "Mom", "Kam"}

# Regions rejected on sight during contact-sheet QA (episode, start, end).
# Mirai Nikki has bath/fanservice beats that no visual metric flags reliably,
# and they have no place in this edit.
BLACKLIST: tuple[tuple[int, float, float], ...] = (
    (20, 30.0, 100.0),    # cold-open bath scene
    (22, 583.0, 598.0),   # full-screen diary entry, wall of typeset text
    (24, 456.0, 472.0),   # diary UI screenshot
    (26, 1100.0, 1115.0),  # SD/chibi comedy beat, wrong tone for the outro
    (5, 1018.0, 1050.0),  # blown-out white flash, and an awkward rear framing
    (7, 186.0, 199.0),    # food insert
    (8, 292.0, 305.0),    # fanservice framing
    (15, 672.0, 683.0),   # disembodied legs, unreadable out of context
    (15, 723.0, 736.0),   # SD/chibi comedy beat
    (13, 1305.0, 1318.0),  # comedy beat, wrong tone
    (4, 694.0, 707.0),    # full-screen diary log, burned-in text
    (12, 848.0, 861.0),   # diary phone UI
    (9, 459.0, 472.0),    # memo/diary UI screen
    (8, 993.0, 1008.0),   # full-screen diary log
    (13, 509.0, 521.0),   # schedule chart, unreadable insert
    (16, 878.0, 890.0),   # wall telephone, dead insert
    (13, 316.0, 330.0),   # bath scene
    (10, 1002.0, 1015.0),  # bath scene
)

# Per-lyric search terms. Keys are the joined display lines from amv/lyrics.py.
THEMES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "I WOKE UP / WITH ASH ON MY TONGUE": (("wake", "dream", "morning", "dead", "again"), SPEAKER_YUKI),
    "IN YOUR MIRROR / I LOOK UNSUNG": (("myself", "who", "me", "alone", "nobody"), SPEAKER_YUKI),
    "MY HANDS ARE CLEAN / BUT THEY DON'T FEEL MINE": (("hands", "kill", "blood", "didn't", "fault"), SPEAKER_YUKI),
    "LIKE SOMEBODY ELSE / CROSSED THAT LINE": (("killed", "murder", "line", "crossed", "did"), None),
    "I KEEP THE PILLS / IN A SUGAR TIN": (("secret", "hiding", "hidden", "know"), None),
    "I SMILE TOO HARD / WHEN I LET YOU IN": (("smile", "happy", "friend", "together", "love"), SPEAKER_YUNO),
    "IF I WAS BORN / FROM A TORN DOWN PRAYER": (("born", "parents", "family", "pray", "home"), SPEAKER_YUNO),
    "WHY DO I STILL / LOOK FOR CARE": (("alone", "friend", "care", "need", "help"), SPEAKER_YUKI),
    "TELL ME / WHAT YOU SEE": (("see", "tell", "look", "what"), None),
    "WHEN YOU / LOOK AT ME": (("look", "eyes", "me", "watching"), SPEAKER_YUNO),
    "A GIRL, A GATE / OR THE SHAPE OF FATE": (("god", "deus", "future", "world", "fate"), None),
    "AM I / IMMORTAL?": (("god", "die", "death", "survive", "win"), None),
    "SAY MY NAME / SLOW": (("yukiteru", "yuno", "name", "call"), SPEAKER_YUNO),
    "WATCH THE / BACK ROOM": (("watching", "behind", "following", "there"), SPEAKER_YUNO),
    "HOLD ME CLOSE NOW / I'M THE SOURCE / OF ALL SINS": (
        ("fault", "because", "sin", "blame", "hold", "together"), None),
    "YOUR MOUTH SAYS ANGEL / YOUR EYES SAY RUN": (("love", "run", "scared", "away", "please"), SPEAKER_YUNO),
    "MY SHADOW MOVES / WHEN THE ROOM GOES NUMB": (("behind", "dark", "shadow", "alone"), None),
    "I TASTE THE RIVER / UNDER MY SKIN": (("blood", "cold", "hurt", "pain"), None),
    "COLD AND SILVER / PULLING ME IN": (("knife", "blade", "axe", "weapon", "cut"), None),
    "DEMON LORD / IS THAT WHAT I WEAR?": (("monster", "demon", "god", "kill", "murderer"), SPEAKER_YUNO),
    "CRIMES OF SMOKE / IN MY BRAIDED HAIR": (("blood", "killed", "body", "bodies", "corpse"), SPEAKER_YUNO),
    "I DON'T NEED MERCY / I NEED A SIGN": (("mercy", "save", "help", "please", "need"), SPEAKER_YUKI),
    "ARE YOU AFRAID / OF WHAT YOU'LL FIND?": (("afraid", "scared", "fear", "truth", "know"), SPEAKER_YUKI),
    "IF I WAS MADE / IN THE MOUTH OF NIGHT": (("born", "made", "monster", "parents", "became"), SPEAKER_YUNO),
    "THEN WHY DO I / STILL WANT THE LIGHT?": (("light", "hope", "want", "save", "live"), SPEAKER_YUKI),
    "PIERCE IN MY THROAT / PRAYER IN MY TEETH": (("pray", "god", "wish", "promise", "swear"), None),
    "I SPLIT IN TWO / WHEN YOU SPEAK TO ME": (("two", "another", "myself", "second", "other"), None),
    "AM I / A MONSTER?": (("monster", "kill", "murderer", "crazy", "insane"), SPEAKER_YUNO),
}

WORD_RE = re.compile(r"[a-z']+")


@dataclass
class Candidate:
    episode: int
    file: str
    start: float
    duration: float
    theme_score: float
    note: str
    brightness: float = 0.0
    contrast: float = 0.0
    motion: float = 0.0
    skin: float = 0.0
    visual_score: float = 0.0

    @property
    def total(self) -> float:
        return self.theme_score + self.visual_score


def credits_zones(episode: dict) -> list[tuple[float, float]]:
    """OP/ED spans, found as very long dialogue-free stretches."""
    zones: list[tuple[float, float]] = []
    events = episode["events"]
    for prev, nxt in zip(events, events[1:]):
        if nxt["start"] - prev["end"] >= CREDITS_GAP:
            zones.append((prev["end"], nxt["start"]))
    return zones


def usable(episode: dict, start: float, duration: float, zones: list[tuple[float, float]]) -> bool:
    end = start + duration
    if start < HEAD_SKIP or end > episode["duration"] - TAIL_SKIP:
        return False
    number = episode["episode"]
    for ep, b_start, b_end in BLACKLIST:
        if ep == number and start < b_end and end > b_start:
            return False
    return not any(start < z_end and end > z_start for z_start, z_end in zones)


def is_diary_reading(event: dict) -> bool:
    """Lines that quote a diary entry play over a full-screen phone graphic.

    That typesetting is burned into this release, so those shots are a wall of
    text — useless as footage and unreadable once graded and overlaid.
    """
    text = event["text"]
    return '"' in text or text.startswith("(") or "「" in text


def theme_score(event: dict, keywords: tuple[str, ...], speaker: str | None) -> float:
    score = 0.0
    words = set(WORD_RE.findall(event["text"].lower()))
    hits = sum(1 for k in keywords if k in words)
    score += hits * 3.0
    # Substring fallback catches inflections ("killed" for "kill").
    lowered = event["text"].lower()
    score += sum(0.8 for k in keywords if k not in words and k in lowered)
    if speaker and event["speaker"] == speaker:
        score += 2.5
    return score


def probe_stats(path: str, start: float, duration: float) -> tuple[float, float, float, float]:
    """Decode the window tiny and return (brightness, contrast, motion, skin).

    A 96x54 8fps RGB stream is enough to tell a black frame from a face and a
    static shot from a fight, at a fraction of the cost of a real decode.

    `skin` is the fraction of warm, pale, R>G>B pixels — a rough stand-in for
    "a character is on screen". Calibration showed it separates character shots
    (mean 0.30) from scenery and text screens (mean 0.15) on average, but the
    tails overlap: warm food reads as skin, and an unlit night shot reads as
    none. It is therefore weighted, never used as a gate.
    """
    width, height, fps = 96, 54, 8
    command = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", path,
        "-vf", f"scale={width}:{height},fps={fps},format=rgb24", "-f", "rawvideo", "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        return 0.0, 0.0, 0.0, 0.0
    frame_size = width * height * 3
    count = len(result.stdout) // frame_size
    if count < 2:
        return 0.0, 0.0, 0.0, 0.0
    rgb = np.frombuffer(result.stdout[: count * frame_size], dtype=np.uint8)
    rgb = rgb.reshape(count, height, width, 3).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    skin = (r > 110) & (g > 70) & (b > 50) & (r > g) & (g >= b) & ((mx - mn) > 14) & ((r - b) > 18) & (r < 252)

    luma = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32) / 255.0
    brightness = float(luma.mean())
    contrast = float(luma.std())
    motion = float(np.abs(np.diff(luma, axis=0)).mean())
    return brightness, contrast, motion, float(skin.mean())


def visual_score(brightness: float, contrast: float, motion: float, skin: float, want_motion: bool) -> float:
    # Reject fades to black/white outright — they read as a dropout mid-cut.
    if brightness < 0.10 or brightness > 0.92:
        return -50.0
    if contrast < 0.055:
        return -25.0
    score = 0.0
    # Mid-range exposure is what grades best once crushed to grayscale.
    score += 6.0 * (1.0 - min(1.0, abs(brightness - 0.45) / 0.45))
    score += 10.0 * min(1.0, contrast / 0.22)
    # Break slots want kinetic footage; lyric slots want a readable, calmer
    # frame the text can sit on top of.
    if want_motion:
        score += 16.0 * min(1.0, motion / 0.055)
        score += 7.0 * min(1.0, skin / 0.30)
    else:
        score += 9.0 * min(1.0, motion / 0.030)
        if motion > 0.10:
            score -= 6.0
        # Lyric lines want a face to land on, so weight character presence harder.
        score += 14.0 * min(1.0, skin / 0.30)
    return score


def build_candidates(slot: Slot, episodes: dict[int, dict], zones: dict[int, list], rng: np.random.Generator,
                     limit: int) -> list[Candidate]:
    low, high = SECTION_EPISODES.get(slot.section, (1, 26))
    pool = [episodes[n] for n in range(low, high + 1) if n in episodes]
    duration = slot.duration
    keywords, speaker = THEMES.get(slot.lyric, ((), None))
    candidates: list[Candidate] = []

    if slot.kind == "lyric" and keywords:
        scored: list[tuple[float, dict, dict]] = []
        for episode in pool:
            for event in episode["events"]:
                if is_diary_reading(event):
                    continue
                value = theme_score(event, keywords, speaker)
                if value > 0:
                    scored.append((value, episode, event))
        scored.sort(key=lambda item: -item[0])
        for value, episode, event in scored[: limit * 4]:
            # Start slightly before the line so the shot is already running.
            start = max(0.0, event["start"] - 0.35)
            if not usable(episode, start, duration, zones[episode["episode"]]):
                continue
            candidates.append(
                Candidate(episode["episode"], episode["file"], start, duration, value,
                          f"theme:{event['speaker']}:{event['text'][:48]}")
            )
            if len(candidates) >= limit:
                break

    if len(candidates) < limit:
        # Anchor on main-cast dialogue so a character is on screen, and let the
        # motion score pick out the kinetic ones. Sampling dialogue-free gaps
        # instead just surfaced scenery.
        anchors: list[tuple[dict, float]] = []
        for episode in pool:
            for event in episode["events"]:
                if event["speaker"] not in MAIN_SPEAKERS or is_diary_reading(event):
                    continue
                anchors.append((episode, max(0.0, event["start"] - 0.3)))
        rng.shuffle(anchors)  # type: ignore[arg-type]
        for episode, start in anchors:
            if not usable(episode, start, duration, zones[episode["episode"]]):
                continue
            candidates.append(Candidate(episode["episode"], episode["file"], start, duration, 0.5, "cast-anchor"))
            if len(candidates) >= limit:
                break

    while len(candidates) < limit and pool:
        episode = pool[int(rng.integers(len(pool)))]
        start = float(rng.uniform(HEAD_SKIP, max(HEAD_SKIP + 1, episode["duration"] - TAIL_SKIP - duration)))
        if usable(episode, start, duration, zones[episode["episode"]]):
            candidates.append(Candidate(episode["episode"], episode["file"], start, duration, 0.0, "random"))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=int, default=6, help="windows shortlisted per slot")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--out", type=Path, default=EDL_PATH)
    args = parser.parse_args()

    index = json.loads(SCENE_INDEX.read_text(encoding="utf-8"))
    episodes = {e["episode"]: e for e in index["episodes"]}
    # Episode 6 is a 2.8min special, too short to hold a usable arc position.
    episodes = {n: e for n, e in episodes.items() if e["duration"] > 600}
    zones = {n: credits_zones(e) for n, e in episodes.items()}
    for n, z in sorted(zones.items()):
        spans = ", ".join(f"{a/60:.1f}-{b/60:.1f}min" for a, b in z)
        print(f"  ep{n:02d} credits: {spans or '(none found)'}", flush=True)

    rng = np.random.default_rng(args.seed)
    slots = build_slots()
    print(f"\nFilling {len(slots)} slots...", flush=True)

    # Break slots need a wider shortlist: they are picked almost purely on
    # motion, so more windows means a better chance of genuinely kinetic footage.
    all_candidates: list[list[Candidate]] = [
        build_candidates(slot, episodes, zones, rng, args.candidates * (2 if slot.kind == "break" else 1))
        for slot in slots
    ]

    flat = [(i, c) for i, group in enumerate(all_candidates) for c in group]
    print(f"Scoring {len(flat)} candidate windows...", flush=True)

    def score_one(item: tuple[int, Candidate]) -> None:
        i, cand = item
        want_motion = slots[i].kind == "break"
        cand.brightness, cand.contrast, cand.motion, cand.skin = probe_stats(cand.file, cand.start, cand.duration)
        cand.visual_score = visual_score(cand.brightness, cand.contrast, cand.motion, cand.skin, want_motion)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(score_one, flat))

    chosen: list[Candidate] = []
    used: list[tuple[int, float]] = []
    for group in all_candidates:
        group.sort(key=lambda c: -c.total)
        pick = None
        for cand in group:
            clash = any(ep == cand.episode and abs(pos - cand.start) < MIN_SEPARATION for ep, pos in used)
            if not clash and cand.visual_score > -20:
                pick = cand
                break
        if pick is None:
            pick = group[0]
        used.append((pick.episode, pick.start))
        chosen.append(pick)

    edl = {
        "song": str(ROOT / "assets" / "black_salt_halo.mp3"),
        "slots": [
            {
                "index": slot.index,
                "out_start": round(slot.start, 3),
                "out_end": round(slot.end, 3),
                "duration": round(slot.duration, 3),
                "section": slot.section,
                "kind": slot.kind,
                "lyric": slot.lyric,
                **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(cand).items()},
            }
            for slot, cand in zip(slots, chosen)
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(edl, indent=1), encoding="utf-8")

    rejected = sum(1 for c in chosen if c.visual_score <= -20)
    from collections import Counter

    print(f"\nWrote {args.out}")
    print(f"episodes used: {dict(sorted(Counter(c.episode for c in chosen).items()))}")
    print(f"sources: {dict(Counter(c.note.split(':')[0] for c in chosen))}")
    print(f"slots still on a poor-visual window: {rejected}")


if __name__ == "__main__":
    main()
