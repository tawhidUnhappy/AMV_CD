"""Curated lyric plan for 'Who I Am Anymore'.

Timings come from WhisperX run on the **Demucs-isolated vocal stem**
(`tmp/song/transcript_vocals.json`), on the combined ~3:35 track (two rips of
the same song concatenated back-to-back — see assets/song.mp3). Structure:
verse + chorus, a ~32s instrumental gap, the same verse + chorus again with
minor lyric variation on the last line, then an outro recap that closes on an
unresolved line ("I don't even know why") rather than the title hook.

Every phrase is timed, because the cut structure follows the whole song, and
every phrase is also displayed: this is a subtitle track, not a selective
lyric-video treatment. Each phrase is a single line so it sits on one row at
the bottom of frame.

Two known ASR mishearings, corrected in the display text (not the word
indices, which still point at the real audio):
- Word 73 transcribes as "snacks"; the second occurrence of the same line
  (word 138) transcribes clearly as "scars" — the intended lyric.
- Word 52-53 transcribes as "Gotta laugh"; the clearer second occurrence
  (words 206-208) gives the intended "always gotta last?".

Word indices refer to `tmp/song/words_vocals.txt` (see amv/subs/dump_words.py).
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
    # Every line is subtitled now, so this defaults on. It stays as a field
    # because the cut structure still follows phrases that are never displayed
    # in other configurations.
    show: bool = True
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


PHRASES: tuple[Phrase, ...] = (
    Phrase(0, 4, ("LOST IN MY HEAD AGAIN",), section="intro"),
    Phrase(5, 13, ("STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN",), section="verse"),
    Phrase(14, 22, ("TRYING TO BLOCK THE NOISE INSIDE THIS EMPTY TOWN",), section="verse"),
    Phrase(23, 31, ("YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY",), section="verse"),
    Phrase(32, 41, ("NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY",), section="verse"),
    Phrase(42, 53, ("AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN GOTTA LAUGH",), section="prechorus"),
    Phrase(54, 62, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus"),
    Phrase(63, 70, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus"),
    Phrase(71, 80, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus"),
    Phrase(81, 88, ("I DON'T EVEN KNOW WHO I AM ANYMORE",), section="chorus"),
    Phrase(89, 95, ("POPPING MEMORIES LIKE PILLS, TRYING TO FORGET",), section="verse"),
    Phrase(96, 101, ("EVERY BROKEN PROMISE EVERY DEEP REGRET",), section="verse"),
    Phrase(102, 110, ("HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW",), section="verse"),
    Phrase(111, 118, ("FAKE SMILES ON MY FACE BUT NOBODY KNOWS",), section="verse"),
    Phrase(119, 127, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus"),
    Phrase(128, 135, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus"),
    Phrase(136, 145, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus"),
    Phrase(146, 153, ("I DON'T EVEN KNOW WHO I AM ANYMORE",), section="chorus"),
    Phrase(154, 158, ("LOST IN MY HEAD AGAIN",), section="verse"),
    Phrase(159, 167, ("STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN",), section="verse"),
    Phrase(168, 176, ("TRY TO BLOCK THE NOISE INSIDE THIS EMPTY TOWN",), section="verse"),
    Phrase(177, 185, ("YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY",), section="verse"),
    Phrase(186, 195, ("NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY",), section="verse"),
    Phrase(196, 208, ("AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN ALWAYS GOTTA LAST?",), section="prechorus"),
    Phrase(209, 217, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus"),
    Phrase(218, 225, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus"),
    Phrase(226, 235, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus"),
    Phrase(236, 243, ("I DON'T EVEN KNOW WHO I AM ANYMORE",), section="chorus"),
    Phrase(244, 248, ("YEAH WHO I AM ANYMORE",), section="outro"),
    Phrase(249, 255, ("POPPING MEMORIES LIKE PILLS, TRYING TO FORGET",), section="outro"),
    Phrase(256, 261, ("EVERY BROKEN PROMISE EVERY DEEP REGRET",), section="outro"),
    Phrase(262, 270, ("HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW",), section="outro"),
    Phrase(271, 278, ("FAKE SMILES ON MY FACE BUT NOBODY KNOWS",), section="outro"),
    Phrase(279, 287, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="outro"),
    Phrase(288, 295, ("LOSING ALL I WANT JUST TO FEEL ALRIGHT",), section="outro"),
    Phrase(296, 305, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="outro"),
    Phrase(306, 310, ("I DON'T EVEN KNOW WHY",), section="outro"),
    Phrase(311, 311, ("YEAH",), section="outro"),
)

# First word of each phrase, lowercased and stripped, as a guard against the
# indices silently drifting if the transcript is ever regenerated.
EXPECTED_FIRST_WORD = {
    0: "lost", 23: "you", 42: "and", 54: "now", 63: "losing", 71: "got",
    81: "i", 89: "popping", 119: "now", 154: "lost", 196: "and", 209: "now",
    244: "yeah", 279: "now", 306: "i", 311: "yeah",
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
