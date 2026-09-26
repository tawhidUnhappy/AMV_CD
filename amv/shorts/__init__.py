"""Vertical YouTube Shorts: a ~25 s beat-cut edit of one show to one track.

    ./amv.sh short-song SONG                 # where the drop is, the window, the hit grid
    ./amv.sh short-find SHOW --find REGEX    # candidate shots + review sheets (crop box drawn)
    ./amv.sh short amv/shorts/specs/NAME.json  # plan, crop, effects, render, title/description

The only hand step is reading the sheets and listing shot ids in a spec -
everything a person used to decide per shot (sub-window, crop, speed, whip
direction, punches on the hits) is derived. See amv/shorts/build.py.
"""
