"""Curated lyric plan for 'Black Salt Halo'.

Timings come from WhisperX run on the **Demucs-isolated vocal stem**
(`data/song/transcript_vocals.json`). Transcribing the full mix put the opening
"I woke up" at 2.71s when it is actually sung at 11.54s, and dropped five whole
lines ("if i was born from a torn down prayer", "demon lord, is that what i
wear?", "crimes of smoke in my braided hair", "i don't need mercy, i need a
sign", "cold and silver, pulling me in").

Every phrase is timed, because the cut structure follows the whole song. Only
phrases with `show=True` are drawn on screen — an AMV puts text on the hooks and
the striking images, not on every line.

Word indices refer to `data/song/words_vocals.txt` (see amv/subs/dump_words.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from amv.core import config

ROOT = config.ROOT
TRANSCRIPT = ROOT / "tmp" / "song" / "transcript_vocals.json"


@dataclass(frozen=True)
class Phrase:
    first_word: int
    last_word: int
    lines: tuple[str, ...]
    emphasis: str | None = None
    show: bool = False
    section: str = "verse"


@dataclass
class TimedPhrase:
    start: float
    end: float
    lines: tuple[str, ...]
    emphasis: str | None
    section: str
    show: bool
    text: str = field(default="")

    @property
    def duration(self) -> float:
        return self.end - self.start


# Word 0 is a spurious "Bye." the ASR hallucinated in the intro silence.
PHRASES: tuple[Phrase, ...] = (
    # --- Verse 1 -----------------------------------------------------------
    Phrase(1, 8, ("I WOKE UP", "WITH ASH ON MY TONGUE"), "ASH", show=True, section="intro"),
    Phrase(9, 14, ("IN YOUR MIRROR", "I LOOK UNSUNG"), "MIRROR"),
    Phrase(15, 23, ("MY HANDS ARE CLEAN", "BUT THEY DON'T FEEL MINE"), "CLEAN", show=True),
    Phrase(24, 29, ("LIKE SOMEBODY ELSE", "CROSSED THAT LINE"), "CROSSED", show=True),
    Phrase(30, 37, ("I KEEP THE PILLS", "IN A SUGAR TIN"), "PILLS"),
    Phrase(38, 46, ("I SMILE TOO HARD", "WHEN I LET YOU IN"), "SMILE"),
    Phrase(47, 55, ("IF I WAS BORN", "FROM A TORN DOWN PRAYER"), "PRAYER", show=True),
    Phrase(56, 62, ("WHY DO I STILL", "LOOK FOR CARE"), "CARE", section="prechorus"),
    # --- Chorus 1 ----------------------------------------------------------
    Phrase(63, 67, ("TELL ME", "WHAT YOU SEE"), None, section="chorus"),
    Phrase(68, 72, ("WHEN YOU", "LOOK AT ME"), None, section="chorus"),
    Phrase(73, 81, ("A GIRL, A GATE", "OR THE SHAPE OF FATE"), "GATE", show=True, section="chorus"),
    Phrase(82, 84, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="chorus"),
    Phrase(85, 87, ("AM I", "IMMORTAL?"), "IMMORTAL?", show=True, section="chorus"),
    Phrase(88, 91, ("SAY MY NAME", "SLOW"), None, section="chorus"),
    Phrase(92, 95, ("WATCH THE", "BACK ROOM"), None, section="chorus"),
    Phrase(96, 98, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="chorus"),
    Phrase(99, 101, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="chorus"),
    Phrase(102, 111, ("HOLD ME CLOSE NOW", "I'M THE SOURCE", "OF ALL SINS"), "SINS",
           show=True, section="chorus"),
    # --- Verse 2 -----------------------------------------------------------
    Phrase(112, 119, ("YOUR MOUTH SAYS ANGEL", "YOUR EYES SAY RUN"), "RUN", show=True),
    Phrase(120, 127, ("MY SHADOW MOVES", "WHEN THE ROOM GOES NUMB"), "SHADOW"),
    Phrase(128, 134, ("I TASTE THE RIVER", "UNDER MY SKIN"), "RIVER"),
    Phrase(135, 140, ("COLD AND SILVER", "PULLING ME IN"), "SILVER"),
    Phrase(141, 147, ("DEMON LORD", "IS THAT WHAT I WEAR?"), "DEMON", show=True),
    Phrase(148, 154, ("CRIMES OF SMOKE", "IN MY BRAIDED HAIR"), "CRIMES"),
    Phrase(155, 162, ("I DON'T NEED MERCY", "I NEED A SIGN"), "MERCY", show=True),
    Phrase(163, 169, ("ARE YOU AFRAID", "OF WHAT YOU'LL FIND?"), "AFRAID",
           show=True, section="prechorus"),
    # --- Chorus 2 ----------------------------------------------------------
    Phrase(170, 174, ("TELL ME", "WHAT YOU SEE"), None, section="chorus"),
    Phrase(175, 179, ("WHEN YOU", "LOOK AT ME"), None, section="chorus"),
    Phrase(180, 188, ("A GIRL, A GATE", "OR THE SHAPE OF FATE"), "FATE", section="chorus"),
    Phrase(189, 191, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="chorus"),
    Phrase(192, 194, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="chorus"),
    Phrase(195, 198, ("SAY MY NAME", "SLOW"), None, section="chorus"),
    # ASR hears "bad boom"; the sung line is "back room".
    Phrase(199, 202, ("WATCH THE", "BACK ROOM"), None, section="chorus"),
    Phrase(203, 206, ("AM I", "A MONSTER?"), "MONSTER?", show=True, section="chorus"),
    Phrase(207, 210, ("AM I", "A MONSTER?"), "MONSTER?", section="chorus"),
    Phrase(211, 220, ("HOLD ME CLOSE NOW", "I'M THE SOURCE", "OF ALL SINS"), "SINS", section="chorus"),
    # --- Bridge ------------------------------------------------------------
    Phrase(221, 229, ("IF I WAS MADE", "IN THE MOUTH OF NIGHT"), "NIGHT", show=True, section="bridge"),
    Phrase(230, 237, ("THEN WHY DO I", "STILL WANT THE LIGHT?"), "LIGHT?", show=True, section="bridge"),
    Phrase(238, 245, ("PIERCE IN MY THROAT", "PRAYER IN MY TEETH"), "PRAYER", section="bridge"),
    Phrase(246, 254, ("I SPLIT IN TWO", "WHEN YOU SPEAK TO ME"), "SPLIT", show=True, section="bridge"),
    # --- Finale ------------------------------------------------------------
    Phrase(255, 257, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="finale"),
    Phrase(258, 260, ("AM I", "IMMORTAL?"), "IMMORTAL?", section="finale"),
    Phrase(261, 264, ("SAY MY NAME", "SLOW"), None, section="finale"),
    Phrase(265, 268, ("WATCH THE", "BACK ROOM"), None, section="finale"),
    Phrase(269, 272, ("AM I", "A MONSTER?"), "MONSTER?", section="finale"),
    Phrase(273, 276, ("AM I", "A MONSTER?"), "MONSTER?", show=True, section="finale"),
    Phrase(277, 286, ("HOLD ME CLOSE NOW", "I'M THE SOURCE", "OF ALL SINS"), "SINS",
           show=True, section="finale"),
)

# First word of each phrase, lowercased and stripped, as a guard against the
# indices silently drifting if the transcript is ever regenerated.
EXPECTED_FIRST_WORD = {
    1: "i", 24: "like", 47: "if", 73: "a", 102: "hold", 112: "your",
    141: "demon", 155: "i", 180: "a", 203: "am", 221: "if", 277: "hold",
}


def load_words(transcript: Path | None = None) -> list[dict]:
    data = json.loads((transcript or TRANSCRIPT).read_text(encoding="utf-8"))
    return [w for s in data["segments"] for w in s.get("words", [])]


def song_duration(transcript: Path | None = None) -> float:
    return float(json.loads((transcript or TRANSCRIPT).read_text(encoding="utf-8"))["duration"])


def timed_phrases(transcript: Path | None = None) -> list[TimedPhrase]:
    words = load_words(transcript)
    result: list[TimedPhrase] = []
    for phrase in PHRASES:
        if phrase.last_word >= len(words):
            raise IndexError(f"Phrase {phrase.lines} wants word {phrase.last_word}, only {len(words)} aligned")
        start = float(words[phrase.first_word]["start"])
        end = float(words[phrase.last_word]["end"])
        if end <= start:
            raise ValueError(f"Phrase {phrase.lines} has non-positive duration ({start} -> {end})")
        spoken = " ".join(w["word"] for w in words[phrase.first_word : phrase.last_word + 1])
        result.append(
            TimedPhrase(start, end, phrase.lines, phrase.emphasis, phrase.section, phrase.show, spoken)
        )
    result.sort(key=lambda p: p.start)
    for a, b in zip(result, result[1:]):
        if a.end > b.start + 0.01:
            raise ValueError(f"Phrases overlap: {a.lines} ends {a.end:.2f}, {b.lines} starts {b.start:.2f}")
    return result


def validate(transcript: Path | None = None) -> None:
    """Check emphasis words exist, and that indices still point at the right words."""
    problems: list[str] = []
    for phrase in PHRASES:
        if phrase.emphasis and phrase.emphasis not in " ".join(phrase.lines).split():
            problems.append(f"emphasis {phrase.emphasis!r} not in {' '.join(phrase.lines)!r}")

    words = load_words(transcript)
    for index, expected in EXPECTED_FIRST_WORD.items():
        actual = words[index]["word"].strip().lower().strip(".,?!")
        if actual != expected:
            problems.append(f"word {index} is {actual!r}, expected {expected!r} — indices have drifted")
    if problems:
        raise ValueError("Lyric plan problems:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    validate()
    phrases = timed_phrases()
    shown = [p for p in phrases if p.show]
    print(f"{len(phrases)} phrases, {len(shown)} shown on screen, over {song_duration():.2f}s\n")
    prev_end = 0.0
    for p in phrases:
        gap = p.start - prev_end
        marker = f"   <-- {gap:5.1f}s instrumental" if gap >= 3.0 else ""
        flag = "TEXT" if p.show else "    "
        print(f"[{p.start:7.2f} -> {p.end:7.2f}] {flag} {p.section:9s} "
              f"{' / '.join(p.lines)}   red={p.emphasis}{marker}")
        prev_end = p.end
    print(f"\ntail after last phrase: {song_duration() - prev_end:.2f}s")
