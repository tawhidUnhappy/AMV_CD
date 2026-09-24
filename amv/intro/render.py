"""Render the intro: grade each shot, join them, then one pass for the focus
falloff, the fades and the song.

The same grade and radial focus as the full AMV (amv.render.grade), so an
intro and a video made here look like one channel. Intro-only touches:

- a short white flash on the first shot of the drive - the orchestra's
  entrance is the one moment the whole intro is built around;
- a fade in from black (the track itself starts from silence) and a quick
  fade out at the end, with the music faded over the same stretch so the
  excerpt ends instead of being cut off mid-note.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from amv.core import config
from amv.core.ffmpeg_tools import (
    choose_h264_encoder,
    h264_encoder_args,
    probe_duration,
    probe_json,
    run,
    write_concat_file,
)
from amv.render.grade import BLUR_SIGMA, GRADE, HEIGHT, WIDTH, write_focus_mask
from amv.render.pipeline import slot_frames

FADE_IN = 0.7
FADE_OUT = 0.45
FLASH = 0.25


def render_shot(job: tuple[dict, int, Path, str, bool]) -> Path:
    slot, frames, out, encoder, flash = job
    chain = GRADE + (f",fade=t=in:st=0:d={FLASH}:color=white" if flash else "")
    run(["ffmpeg", "-hide_banner", "-y", "-ss", f"{slot['start']:.3f}", "-i", slot["file"],
         "-t", f"{slot['duration'] + 0.6:.3f}", "-frames:v", str(frames),
         "-an", "-sn", "-dn", "-map_chapters", "-1", "-vf", chain,
         *h264_encoder_args(encoder, "p6", 16), "-pix_fmt", "yuv420p", "-video_track_timescale", "24000",
         str(out)], print_command=False)
    return out


def render(slots: list[dict], song: Path, seconds: float, work: Path, out: Path) -> Path:
    clips_dir = work / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    encoder = choose_h264_encoder("auto")
    frames = slot_frames(slots)
    first_drive = next((s["index"] for s in slots if s["kind"] == "drive"), None)
    has_calm = any(s["kind"] == "calm" for s in slots)
    jobs = [(s, f, clips_dir / f"shot_{s['index']:02d}.mp4", encoder, has_calm and s["index"] == first_drive)
            for s, f in zip(slots, frames, strict=True)]
    with ThreadPoolExecutor(max_workers=3) as ex:
        paths = list(ex.map(render_shot, jobs))

    silent = work / "silent.mp4"
    run(["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0",
         "-i", str(write_concat_file(paths, work / "concat.txt")), "-c", "copy", str(silent)], print_command=False)

    total = sum(frames) / config.load().fps_value
    mask = write_focus_mask(work / "focus_mask.pgm")
    fps = config.load().fps
    graph = (
        "[0:v]format=yuv420p,split=2[sharp][pre];"
        f"[pre]gblur=sigma={BLUR_SIGMA}:steps=2[blurred];"
        f"[1:v]format=gray,scale={WIDTH}:{HEIGHT},format=yuv420p[mask];"
        "[sharp][blurred][mask]maskedmerge,"
        f"fade=t=in:st=0:d={FADE_IN},fade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}[v]"
    )
    # Picture and sound are made apart and joined by stream copy. In one
    # graph, the sound took its timing from a picture that was being dropped
    # and retimed (a looped image input runs at 25 fps): non-monotonic audio
    # timestamps, and 7-8s of sound under 11s of picture.
    picture = work / "picture.mp4"
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(silent), "-loop", "1", "-framerate", fps, "-i", str(mask),
         "-filter_complex", graph, "-map", "[v]", "-r", fps, "-frames:v", str(sum(frames)),
         *h264_encoder_args(encoder, "p6", 16), "-pix_fmt", "yuv420p", "-an", str(picture)], print_command=False)
    sound = work / "sound.m4a"
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(song), "-vn",
         "-af", f"atrim=0:{seconds},asetpts=PTS-STARTPTS,afade=t=out:st={seconds - FADE_OUT:.3f}:d={FADE_OUT}",
         "-c:a", "aac", "-b:a", "320k", str(sound)], print_command=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-y", "-i", str(picture), "-i", str(sound), "-map", "0:v", "-map", "1:a",
         "-c", "copy", "-movflags", "+faststart", str(out)], print_command=False)
    audio_seconds = float(probe_json(out, "stream=codec_type,duration").get("streams", [{}])[-1].get("duration", 0))
    print(f"Wrote {out}  ({probe_duration(out):.2f}s, sound {audio_seconds:.2f}s, timeline {total:.3f}s)", flush=True)
    if audio_seconds < seconds - 0.1:
        raise SystemExit(f"the sound stops at {audio_seconds:.2f}s of {seconds:.2f}s - the mux dropped audio")
    return out
