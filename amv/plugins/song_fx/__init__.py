"""Whole-song effects for a Short (spec "song_fx": NAME or {"kind": NAME,
...settings}), rendered once to a cached wav that is then analysed as the
song - so drops and beats move with the speed.

    slowed_reverb  0.85x speed and pitch + a hall reverb ("slowed + reverb")
    slowed         0.85x
    nightcore      1.25x speed and pitch
    sped_up        1.15x
Each takes {"rate": x} to change its speed."""

from amv.plugins import SongFx, register

CHAIN = "amv.plugins.song_fx.chains:rate_chain"

register("song_fx", SongFx("slowed_reverb", "Slowed + Reverb", CHAIN, {"rate": 0.85, "reverb": True}, order=1))
register("song_fx", SongFx("slowed", "Slowed", CHAIN, {"rate": 0.85}, order=2))
register("song_fx", SongFx("nightcore", "Nightcore", CHAIN, {"rate": 1.25}, order=3))
register("song_fx", SongFx("sped_up", "Sped Up", CHAIN, {"rate": 1.15}, order=4))
