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
BLACKLIST: tuple[tuple[int, float, float], ...] = (
    (8, 1235.0, 1255.0),   # full-screen end-credits staff card, burned-in text
    (21, 60.0, 80.0),      # full-screen end-credits staff card, burned-in text
    (20, 100.0, 120.0),    # "Director Manabu Okamoto" credits card, burned-in text
    # Episode 20 is "Ghost Scare", a side-story episode centred on Eris (with
    # Cliff Grimoire also featured) rather than Rudeus -- this window picked
    # up Cliff standing in where the edit wants Rudeus. Not a content issue,
    # just the wrong character for this slot.
    (20, 1080.0, 1100.0),
)

# Per-lyric search terms. Keys are the joined display lines from
# amv/audio/lyrics.py. Chosen against real dialogue in tmp/subs/scene_index.json
# (grepped, not guessed) rather than generic English synonyms -- e.g. "trust"
# and "ashamed" for the verse that plays over the Superd-prejudice arc
# (episodes 17-20) hits real dialogue about Ruijerd's race, not a coincidence.
# "who am I"/"myself"/"anymore" anchor the identity hook throughout; "scars"
# not "scar" avoids a substring false-match against "scary" in theme_score's
# fallback check.
THEMES: dict[str, tuple[tuple[str, ...], str | None]] = {
    "LOST IN MY HEAD AGAIN": (
        ("myself", "again", "remember", "strange", "who"), None),
    "STARING AT THE CEILING WHILE THE CLOCK RUNS DOWN": (
        ("night", "sleep", "awake", "alone", "quiet"), None),
    "TRYNA BLOCK THE NOISE INSIDE THIS EMPTY TOWN": (
        ("quiet", "alone", "nobody", "empty", "silence"), None),
    "YOU SAID YOU'D STAY FOREVER BUT YOU WALKED AWAY": (
        ("promise", "leave", "gone", "left", "goodbye"), None),
    "NOW I'M DROWNING IN THE WORDS THAT I COULDN'T SAY": (
        ("sorry", "should've", "couldn't", "regret", "wish"), None),
    "AND EVERY MEMORY CUTS LIKE GLASS WHY DOES THE PAIN ALWAYS GOTTA LAST?": (
        ("memory", "remember", "forget", "hurt", "pain"), None),
    "NOW I'M FIGHTING DEMONS IN THE DEAD OF NIGHT": (
        ("demon", "monster", "fight", "battle", "superd"), None),
    "LOSING WHO I WAS JUST TO FEEL ALRIGHT": (
        ("change", "became", "used to", "different", "myself"), None),
    "GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR": (
        ("scars", "wound", "hurt", "cry", "tears"), None),
    "I DON'T EVEN KNOW WHO I AM ANYMORE": (
        ("who", "myself", "am i", "anymore", "identity"), None),
    "THE MEMORIES LIKE PILLS TRYING TO FORGET": (
        ("forget", "remember", "memory", "past"), None),
    "POPPING MEMORIES LIKE PILLS TRYING TO FORGET": (
        ("forget", "remember", "memory", "past"), None),
    "EVERY BROKEN PROMISE EVERY DEEP REGRET": (
        ("promise", "regret", "broken", "sorry", "fault"), None),
    "HARD TO TRUST ANYBODY WHEN YOU'RE DOWN THIS LOW": (
        ("trust", "believe", "afraid", "ashamed", "shame"), None),
    "FAKE SMILES ON MY FACE BUT NOBODY KNOWS": (
        ("smile", "fine", "pretend", "hide", "secret"), None),
    "LOSING ALL I WANT JUST TO FEEL ALRIGHT": (
        ("want", "wish", "hope", "give up", "alright"), None),
    "I DON'T EVEN KNOW WHY": (
        ("why", "don't know", "confused", "lost"), None),
    "YEAH,": ((), None),
    "YEAH": ((), None),
    "GOT THESE SCARS ON MY CHEST TEARS ON THE FLOOR I DON'T EVEN KNOW WHO I AM ANYMORE": (
        ("scars", "myself", "who", "anymore"), None),
    "BYE-BYE": ((), None),
}
