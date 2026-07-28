"""Render the AMV: grade each clip, concatenate, burn lyrics, mux the song.

Three passes, deliberately:
  1. every EDL slot is cut and graded to a matching intermediate,
  2. those are concatenated by stream copy,
  3. one final pass burns the lyric overlay and attaches the song.

Building it as a single giant filter_complex would need all 154 inputs open at
once and blows past the command-line length limit on Windows.
"""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from amv.ffmpeg_tools import (
    choose_h264_encoder,
    h264_encoder_args,
    probe_duration,
    run,
    write_concat_file,
)

ROOT = Path(__file__).resolve().parent.parent
EDL_PATH = ROOT / "data" / "edl.json"
WORK_DIR = ROOT / "data" / "work"
CLIPS_DIR = ROOT / "data" / "clips"
OUT_PATH = ROOT / "data" / "out" / "amv_black_salt_halo.mp4"
SONG = ROOT / "assets" / "black_salt_halo.mp3"
FONTS_DIR = ROOT / "assets"

WIDTH, HEIGHT = 1920, 1080
FPS_NUM, FPS_DEN = 24000, 1001
FPS = f"{FPS_NUM}/{FPS_DEN}"
FPS_VALUE = FPS_NUM / FPS_DEN


def slot_frames(slots: list[dict]) -> list[int]:
    """Exact frame count per slot, quantised on the shared timeline.

    Asking ffmpeg for a duration in seconds lets every clip round down to a
    whole frame independently, and 154 of those roundings drifted the edit 1.6s
    early against the music. Snapping each slot boundary to a frame index and
    taking the difference makes the clip lengths sum to the song exactly.
    """
    edges = [round(s["out_start"] * FPS_VALUE) for s in slots]
    edges.append(round(slots[-1]["out_end"] * FPS_VALUE))
    return [max(1, edges[i + 1] - edges[i]) for i in range(len(slots))]

# Colour grade (this replaced the earlier full grayscale pass): cool the
# shadows, warm the highlights, lift saturation a little and hold an S-curve for
# contrast. Shadow point stays at 0.095 — crushing harder previously buried 15%
# of the runtime near black.
GRADE = (
    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={WIDTH}:{HEIGHT},setsar=1,"
    "eq=contrast=1.17:saturation=1.05:brightness=-0.014:gamma=0.96,"
    # Cool the shadows and keep midtones/highlights close to neutral. Warming
    # the highlights washed the whole video orange — this source is full of
    # sunset scenes and the push stacked on top of them.
    "colorbalance=rs=-0.075:gs=-0.02:bs=0.11:rm=-0.015:gm=0:bm=0.025:"
    "rh=0.015:gh=0:bh=-0.015,"
    "curves=master='0/0 0.20/0.085 0.5/0.49 0.85/0.94 1/1',"
    "vignette=angle=PI/5,"
    "unsharp=5:5:0.32:5:5:0.0,"
    f"fps={FPS},format=yuv420p"
)

# Length of the dip-to-black used where one song section hands over to the next.
SECTION_DIP = 0.20
# Open from black and close to black; the outro instrumental carries the exit.
OPEN_FADE = 1.6
CLOSE_FADE = 3.5


def clip_filter(fade_in: bool, fade_out: bool, duration: float) -> str:
    """Grade chain for one clip, plus a dip to black at section handovers.

    Cuts inside a section stay hard and on the beat — that is what gives an AMV
    its drive. Only the section changes get a transition.
    """
    chain = GRADE
    if fade_in:
        chain += f",fade=t=in:st=0:d={SECTION_DIP}"
    if fade_out:
        chain += f",fade=t=out:st={max(0.0, duration - SECTION_DIP):.3f}:d={SECTION_DIP}"
    return chain


# Radial focus: a sharp circle in the middle falling off to blurred edges.
# Radii are in units of half-frame-height, so 1.0 reaches the top/bottom edge
# and the corners sit at ~2.06 — that keeps the clear area a true circle on a
# 16:9 frame rather than an ellipse.
FOCUS_INNER = 0.82
FOCUS_OUTER = 1.62
BLUR_SIGMA = 13


def write_focus_mask(path: Path) -> Path:
    """Write the radial mask as a binary PGM.

    A greyscale image input costs one decode; generating the same gradient with
    `geq` would evaluate a per-pixel expression across every frame.
    Black in the centre keeps the sharp source, white at the edges takes the
    blurred copy.
    """
    import numpy as np

    ys = (np.arange(HEIGHT) - (HEIGHT - 1) / 2) / (HEIGHT / 2)
    xs = (np.arange(WIDTH) - (WIDTH - 1) / 2) / (HEIGHT / 2)
    radius = np.hypot(xs[None, :], ys[:, None])

    ramp = (radius - FOCUS_INNER) / (FOCUS_OUTER - FOCUS_INNER)
    ramp = np.clip(ramp, 0.0, 1.0)
    # Smoothstep, so the transition has no visible banding edge.
    mask = ramp * ramp * (3.0 - 2.0 * ramp)

    data = (mask * 255.0 + 0.5).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(f"P5\n{WIDTH} {HEIGHT}\n255\n".encode("ascii"))
        f.write(data.tobytes())
    return path


def clip_path(index: int) -> Path:
    return CLIPS_DIR / f"clip_{index:04d}.mp4"


def render_clip(args: tuple[dict, int, str, str, int, bool, bool]) -> Path:
    slot, frames, encoder, preset, cq, fade_in, fade_out = args
    output = clip_path(slot["index"])
    command = [
        "ffmpeg", "-hide_banner", "-y",
        # -ss before -i seeks fast. Decode a little extra, then take an exact
        # frame count so the clip length is deterministic.
        "-ss", f"{slot['start']:.3f}",
        "-i", slot["file"],
        "-t", f"{slot['duration'] + 0.6:.3f}",
        "-frames:v", str(frames),
        "-an", "-sn", "-dn", "-map_chapters", "-1",
        "-vf", clip_filter(fade_in, fade_out, slot["duration"]),
        *h264_encoder_args(encoder, preset, cq),
        "-pix_fmt", "yuv420p",
        "-video_track_timescale", "24000",
        str(output),
    ]
    run(command, print_command=False)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edl", type=Path, default=EDL_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--encoder", default="auto")
    parser.add_argument("--preset", default="p6")
    parser.add_argument("--cq", type=int, default=19)
    parser.add_argument("--final-cq", type=int, default=18)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="render only the first N slots (preview)")
    parser.add_argument("--keep-clips", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    slots = json.loads(args.edl.read_text(encoding="utf-8"))["slots"]
    if args.limit:
        slots = slots[: args.limit]
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    encoder = choose_h264_encoder(args.encoder)

    frames = slot_frames(slots)
    print(f"Timeline: {sum(frames)} frames = {sum(frames) / FPS_VALUE:.3f}s", flush=True)

    # A section handover dips to black: the outgoing clip fades out and the
    # incoming one fades in.
    starts_section = {
        slots[i]["index"] for i in range(1, len(slots))
        if slots[i]["section"] != slots[i - 1]["section"]
    }
    ends_section = {
        slots[i]["index"] for i in range(len(slots) - 1)
        if slots[i]["section"] != slots[i + 1]["section"]
    }
    print(f"Section handovers: {len(starts_section)}", flush=True)

    pending = [(s, f) for s, f in zip(slots, frames)
               if not (args.skip_existing and clip_path(s["index"]).exists())]
    print(f"Rendering {len(pending)} clips ({len(slots) - len(pending)} already present)...", flush=True)
    jobs = [
        (slot, count, encoder, args.preset, args.cq,
         slot["index"] in starts_section, slot["index"] in ends_section)
        for slot, count in pending
    ]
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for _ in pool.map(render_clip, jobs):
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(jobs)}", flush=True)

    paths = [clip_path(s["index"]) for s in slots]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"Missing rendered clips: {missing[:10]}")

    concat_file = write_concat_file(paths, WORK_DIR / "concat.txt")
    silent = WORK_DIR / "silent.mp4"
    print("Concatenating...", flush=True)
    run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c", "copy", str(silent)],
        print_command=False,
    )
    joined = probe_duration(silent)
    expected = sum(frames) / FPS_VALUE
    print(f"Concatenated: {joined:.3f}s (expected {expected:.3f}s)", flush=True)
    if abs(joined - expected) > 0.15:
        print(f"WARNING: joined length is {joined - expected:+.3f}s off the timeline", flush=True)

    lyrics = WORK_DIR / "lyrics.ass"
    if not lyrics.exists():
        raise SystemExit(f"Missing {lyrics} - run amv/lyric_overlay.py first")

    # libass needs a POSIX-ish path with the drive colon escaped inside a filter.
    ass_arg = lyrics.resolve().as_posix().replace(":", "\\:")
    fonts_arg = FONTS_DIR.resolve().as_posix().replace(":", "\\:")
    mask = write_focus_mask(WORK_DIR / "focus_mask.pgm")
    print("Applying radial focus, burning lyrics, muxing audio...", flush=True)
    # Order matters: the footage is blurred first, then the lyrics are drawn on
    # top, so the text stays sharp wherever it sits in the frame.
    total = sum(frames) / FPS_VALUE
    # Opening and closing fades run last so the lyrics fade with the picture.
    filtergraph = (
        "[0:v]format=yuv420p,split=2[sharp][pre];"
        f"[pre]gblur=sigma={BLUR_SIGMA}:steps=2[blurred];"
        f"[1:v]format=gray,scale={WIDTH}:{HEIGHT},format=yuv420p[mask];"
        "[sharp][blurred][mask]maskedmerge[focused];"
        f"[focused]subtitles='{ass_arg}':fontsdir='{fonts_arg}',"
        f"fade=t=in:st=0:d={OPEN_FADE},"
        f"fade=t=out:st={max(0.0, total - CLOSE_FADE):.3f}:d={CLOSE_FADE}[v]"
    )
    run(
        [
            "ffmpeg", "-hide_banner", "-y",
            "-i", str(silent),
            "-loop", "1", "-i", str(mask),
            "-i", str(SONG),
            "-filter_complex", filtergraph,
            "-map", "[v]", "-map", "2:a",
            *h264_encoder_args(encoder, args.preset, args.final_cq),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "256k",
            # The mask is an endless -loop 1 input, so the graph would otherwise
            # pad the video out to the song. Cap it at the timeline's own length.
            "-frames:v", str(sum(frames)),
            "-shortest", "-movflags", "+faststart",
            str(args.out),
        ],
        print_command=False,
    )

    if not args.keep_clips:
        shutil.rmtree(CLIPS_DIR, ignore_errors=True)

    print(f"\nWrote {args.out}  ({probe_duration(args.out):.2f}s)", flush=True)


if __name__ == "__main__":
    main()
