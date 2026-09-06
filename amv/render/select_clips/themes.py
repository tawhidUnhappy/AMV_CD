"""Per-lyric keyword search terms and the story-relevant blacklist.

Split out of the selection CLI so the (large, hand-tuned) domain data is
separate from the scoring/candidate-building code that consumes it.
"""

from __future__ import annotations

# This release's subtitles are OCR'd from PGS bitmaps (see amv/subs/pgs_ocr.py),
# which carry no speaker names at all -- every event has speaker="". There is
# no per-character targeting available for this build; MAIN_SPEAKERS stays
# empty (candidates.py treats that as "any dialogue line" rather than "match
# a named main-cast speaker"), and every THEMES entry below scores on keyword
# match only.
MAIN_SPEAKERS: set[str] = set()

# Regions rejected on sight during contact-sheet QA (episode, start, end).
# Both entries here are staff/credits text cards -- unusable as footage
# regardless of content judgment, not a content-appropriateness call.
BLACKLIST: tuple[tuple[int, float, float], ...] = (
    (8, 1235.0, 1255.0),   # full-screen end-credits staff card, burned-in text
    (21, 60.0, 80.0),      # full-screen end-credits staff card, burned-in text
)

# Per-lyric search terms. Keys are the joined display lines from
# amv/audio/lyrics.py. Mushoku Tensei S1 follows Rudeus, reincarnated as a
# baby after dying in shame as a friendless adult, growing up carrying his
# old self's regret and self-loathing while trying to become someone worth
# being -- close thematic overlap with the song's identity-crisis "who I
# am anymore" throughline, even without character-name targeting.
THEMES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "LOST IN MY HEAD AGAIN": (("think", "remember", "again", "always", "still"), None),
    "STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN": (
        ("night", "sleep", "awake", "alone", "time"), None),
    "TRYING TO BLOCK THE NOISE INSIDE THIS EMPTY TOWN": (
        ("quiet", "alone", "nobody", "empty", "silence"), None),
    "TRY TO BLOCK THE NOISE INSIDE THIS EMPTY TOWN": (
        ("quiet", "alone", "nobody", "empty", "silence"), None),
    "YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY": (
        ("promise", "leave", "gone", "left", "goodbye", "away"), None),
    "NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY": (
        ("sorry", "should've", "couldn't", "regret", "wish"), None),
    "AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN GOTTA LAUGH": (
        ("memory", "remember", "past", "hurt", "pain"), None),
    "AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN ALWAYS GOTTA LAST?": (
        ("memory", "remember", "past", "hurt", "pain"), None),
    "NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT": (
        ("fight", "demon", "monster", "battle", "enemy"), None),
    "LOSING WHO I WAS JUST TO FEEL ALRIGHT": (
        ("change", "became", "used to", "different", "myself"), None),
    "GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR": (
        ("scar", "wound", "hurt", "cry", "tears", "blood"), None),
    "I DON'T EVEN KNOW WHO I AM ANYMORE": (
        ("who", "myself", "am i", "anymore", "identity"), None),
    "POPPING MEMORIES LIKE PILLS, TRYING TO FORGET": (
        ("forget", "remember", "memory", "past"), None),
    "EVERY BROKEN PROMISE EVERY DEEP REGRET": (
        ("promise", "regret", "broken", "sorry", "fault"), None),
    "HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW": (
        ("trust", "believe", "alone", "nobody", "afraid"), None),
    "FAKE SMILES ON MY FACE BUT NOBODY KNOWS": (
        ("smile", "fine", "pretend", "hide", "secret", "lie"), None),
    "YEAH WHO I AM ANYMORE": (
        ("who", "myself", "am i", "anymore", "identity"), None),
    "LOSING ALL I WANT JUST TO FEEL ALRIGHT": (
        ("want", "wish", "hope", "give up", "alright"), None),
    "I DON'T EVEN KNOW WHY": (
        ("why", "don't know", "confused", "lost"), None),
    "YEAH": ((), None),
}
