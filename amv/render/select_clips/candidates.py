"""Build the shortlist of candidate windows for one timeline slot.

Selection combines three signals:

1. *Story arc*  - each section draws from its own episode range, so the video
   walks the series forward instead of shuffling all 26 episodes uniformly.
2. *Theme*      - lyric slots score subtitle dialogue against per-line keywords
   and a preferred speaker, so lines land on footage that means something.
3. *Visuals*    - every shortlisted window is decoded small and scored for
   brightness, contrast and motion (see scoring.py), which rejects black
   frames, fades and static talking heads that would read as dead air in an
   AMV.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from amv.render.select_clips.scoring import HEAD_SKIP, TAIL_SKIP, is_diary_reading, theme_score, usable
from amv.render.select_clips.themes import MAIN_SPEAKERS, THEMES
from amv.render.timeline import SECTION_EPISODES, Slot


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
