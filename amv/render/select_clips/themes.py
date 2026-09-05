"""Per-lyric keyword/speaker search terms and the story-relevant blacklist.

Split out of the selection CLI so the (large, hand-tuned) domain data is
separate from the scoring/candidate-building code that consumes it.
"""

from __future__ import annotations

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

# Per-lyric search terms. Keys are the joined display lines from amv/audio/lyrics.py.
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
