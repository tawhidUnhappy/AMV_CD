"""Curated lyric plan for 'Who I Am Anymore'.

Timings come from WhisperX run on the **Demucs-isolated vocal stem**
(`tmp/song/transcript_vocals.json`), on the combined ~3:35 track (two rips of
the same song concatenated back-to-back — see assets/song.mp3). Both rips
render the same official structure in full (intro, verse 1, prechorus,
chorus 1, verse 2, chorus 2) end to end; they differ only in the exact
delivery of the outro line, since Suno renders the same prompt slightly
differently take to take.

The rips are deliberately ordered so the song closes on its strongest line:
the rip whose outro trails off unresolved ("...I don't even know why") plays
FIRST, and the rip that resolves on the title hook ("...I don't even know
who I am anymore") plays LAST — the reverse of assets/song.mp3's original
build order. Sections from the second rip carry a "_2"/"2" suffix.

Every phrase is timed, because the cut structure follows the whole song, and
every phrase is also displayed: this is a subtitle track, not a selective
lyric-video treatment. Each phrase is a single line so it sits on one row at
the bottom of frame.

One ASR mishearing, corrected in the display text (not the word indices,
which still point at the real audio): word 226 transcribes as "Dance on the
floor"; every other occurrence of this line in the song is "Got these scars
on my chest, tears on the floor" — corrected to the canonical lyric.

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
    # --- Rip A: first pass through the full structure --------------------
    Phrase(0, 4, ("LOST IN MY HEAD AGAIN",), section="intro"),
    Phrase(5, 13, ("STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN",), section="verse1"),
    Phrase(14, 22, ("TRYNA BLOCK THE NOISE INSIDE THIS EMPTY TOWN",), section="verse1"),
    Phrase(23, 31, ("YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY",), section="verse1"),
    Phrase(32, 41, ("NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY",), section="verse1"),
    Phrase(42, 54, ("AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN ALWAYS GOTTA LAST?",), section="prechorus"),
    Phrase(55, 63, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus1"),
    Phrase(64, 71, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus1"),
    Phrase(72, 81, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus1"),
    Phrase(82, 89, ("I DON'T EVEN KNOW WHO I AM ANYMORE",), section="chorus1"),
    Phrase(90, 96, ("THE MEMORIES LIKE PILLS TRYING TO FORGET",), section="verse2"),
    Phrase(97, 102, ("EVERY BROKEN PROMISE EVERY DEEP REGRET",), section="verse2"),
    Phrase(103, 111, ("HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW",), section="verse2"),
    Phrase(112, 119, ("FAKE SMILES ON MY FACE BUT NOBODY KNOWS",), section="verse2"),
    Phrase(120, 128, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus2"),
    Phrase(129, 136, ("LOSING ALL I WANT JUST TO FEEL ALRIGHT",), section="chorus2"),
    Phrase(137, 146, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus2"),
    # This rip's take on the outro line ends unresolved ("...why") rather
    # than the official lyric sheet's "I don't even know who I am..." --
    # Suno renders the same song slightly differently take to take, and this
    # is the actual sung outro on THIS rip. Kept as sung, not corrected to
    # the lyric sheet, since it genuinely is a different delivery.
    Phrase(147, 151, ("I DON'T EVEN KNOW WHY",), section="chorus2"),
    Phrase(152, 152, ("YEAH,",), section="bridge"),
    Phrase(153, 153, ("YEAH",), section="bridge"),
    # --- Rip B: second pass, the fuller take that closes the song ---------
    Phrase(154, 158, ("LOST IN MY HEAD AGAIN",), section="intro2"),
    Phrase(159, 167, ("STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN",), section="verse1_2"),
    Phrase(168, 176, ("TRYNA BLOCK THE NOISE INSIDE THIS EMPTY TOWN",), section="verse1_2"),
    Phrase(177, 185, ("YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY",), section="verse1_2"),
    Phrase(186, 195, ("NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY",), section="verse1_2"),
    Phrase(196, 208, ("AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN ALWAYS GOTTA LAST?",), section="prechorus2"),
    Phrase(209, 217, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus1_2"),
    Phrase(218, 225, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus1_2"),
    # Word 226 transcribes as "Dance on the floor"; every other occurrence of
    # this line in the song is "Got these scars on my chest, tears on the
    # floor" -- corrected to the canonical lyric.
    Phrase(226, 237, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR I DON'T EVEN KNOW WHO I AM ANYMORE",),
           section="chorus1_2"),
    Phrase(238, 244, ("POPPING MEMORIES LIKE PILLS TRYING TO FORGET",), section="verse2_2"),
    Phrase(245, 250, ("EVERY BROKEN PROMISE EVERY DEEP REGRET",), section="verse2_2"),
    Phrase(251, 259, ("HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW",), section="verse2_2"),
    Phrase(260, 267, ("FAKE SMILES ON MY FACE BUT NOBODY KNOWS",), section="verse2_2"),
    Phrase(268, 276, ("NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT",), section="chorus2_2"),
    Phrase(277, 284, ("LOSING WHO I WAS JUST TO FEEL ALRIGHT",), section="chorus2_2"),
    Phrase(285, 294, ("GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR",), section="chorus2_2"),
    # The song's strongest, most resolved line -- matching the official
    # lyric sheet's title hook -- lands here, at the very end. Deliberately
    # paired with the outro's episode range (see timeline.py) so the video
    # closes on it.
    Phrase(295, 302, ("I DON'T EVEN KNOW WHO I AM ANYMORE",), section="chorus2_2"),
    # Trailing ad-lib as the track fades, ~10s after the last real line --
    # too short and too late to matter for cut structure, kept only so the
    # phrase list covers the whole song.
    Phrase(303, 303, ("BYE-BYE",), section="chorus2_2"),
)

# First word of each phrase, lowercased and stripped, as a guard against the
# indices silently drifting if the transcript is ever regenerated.
EXPECTED_FIRST_WORD = {
    0: "lost", 23: "you", 42: "and", 55: "now", 64: "losing", 72: "got",
    82: "i", 90: "the", 120: "now", 152: "yeah", 154: "lost", 196: "and",
    209: "now", 226: "dance", 238: "popping", 268: "now", 295: "i", 303: "bye-bye",
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
