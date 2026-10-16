"""Effect-heavy music edits (`./amv.sh edit`): a montage shot list, plus beat-timed
glitch effects, stutters, kinetic text and 3D shots rendered in Blender, over one
window of a song - built for vertical, loopable, rewatchable edits.

    build.py     the spec -> plan -> Blender segments -> final pass -> mp4
    audio.py     the song window, optionally ending on its instrumental (a clean loop)
    text.py      kinetic text layers
    blender/     the Blender scripts a spec's "blender" segments run (headless)
"""
