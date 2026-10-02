"""The lyric plan of the active project (amv.core.project: "lyrics").

A plan is a list of phrases, each a run of transcript words
(`tmp/song/words_vocals.txt`, from ./amv.sh words) shown as one or more
display lines, with a section name the story arc (section_episodes) and the
cut pacing key off. Timings come from WhisperX on the Demucs-isolated vocal
stem (`tmp/song/transcript_vocals.json`): ASR on the full mix misplaces words.

Display text may correct a mishearing; the word indices still point at the
real audio. `expected_first_word` ({index: word}) guards the indices against
drifting if the transcript is ever regenerated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from amv.core import paths

TRANSCRIPT = paths.TRANSCRIPT


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


def phrases() -> tuple[Phrase, ...]:
    """The project's phrases, in plan order."""
    from amv.core import project

    plan = project.required("lyrics")
    return tuple(Phrase(p["first_word"], p["last_word"], tuple(p["lines"]), p.get("emphasis"),
                        p.get("show", True), p.get("section", "verse")) for p in plan["phrases"])


def expected_first_word() -> dict[int, str]:
    from amv.core import project

    return {int(k): v for k, v in project.required("lyrics").get("expected_first_word", {}).items()}


def load_words(transcript: Path | None = None) -> list[dict]:
    data = json.loads((transcript or TRANSCRIPT).read_text(encoding="utf-8"))
    return [w for s in data["segments"] for w in s.get("words", [])]


def song_duration(transcript: Path | None = None) -> float:
    return float(json.loads((transcript or TRANSCRIPT).read_text(encoding="utf-8"))["duration"])


def timed_phrases(transcript: Path | None = None) -> list[TimedPhrase]:
    words = load_words(transcript)
    result: list[TimedPhrase] = []
    for phrase in phrases():
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
    for phrase in phrases():
        if phrase.emphasis and phrase.emphasis not in " ".join(phrase.lines).split():
            problems.append(f"emphasis {phrase.emphasis!r} not in {' '.join(phrase.lines)!r}")

    words = load_words(transcript)
    for index, expected in expected_first_word().items():
        actual = words[index]["word"].strip().lower().strip(".,?!")
        if actual != expected:
            problems.append(f"word {index} is {actual!r}, expected {expected!r} — indices have drifted")
    if problems:
        raise ValueError("Lyric plan problems:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    validate()
    timed = timed_phrases()
    shown = [p for p in timed if p.show]
    print(f"{len(timed)} phrases, {len(shown)} shown on screen, over {song_duration():.2f}s\n")
    prev_end = 0.0
    for p in timed:
        gap = p.start - prev_end
        marker = f"   <-- {gap:5.1f}s instrumental" if gap >= 3.0 else ""
        flag = "TEXT" if p.show else "    "
        print(f"[{p.start:7.2f} -> {p.end:7.2f}] {flag} {p.section:9s} "
              f"{' / '.join(p.lines)}   red={p.emphasis}{marker}")
        prev_end = p.end
    print(f"\ntail after last phrase: {song_duration() - prev_end:.2f}s")
