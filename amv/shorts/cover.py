"""The thumbnail inside the Short itself, so there is nothing to upload beside it.

YouTube does not read cover art from an uploaded file. A Short's thumbnail is
a FRAME of the video: YouTube picks one on its own, or the uploader picks one
in the app's cover picker, whose slider starts at the first frame. So the
thumbnail replaces the first COVER_FRAMES frames (0.125 s at 24 fps - under
the fade-in, too short to register while watching, long enough to land on
with the slider at its left end). It is also embedded as MP4 cover art, which
phone galleries and file browsers show.

The input is always the untouched render (tmp/shorts/NAME/short.mp4), never a
delivered copy, so re-running re-encodes one generation, not one per run.

    ./amv.sh short-cover            # every delivered Short that has a thumbnail
    ./amv.sh short-cover NAME ...   # just these
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from amv.core.ffmpeg_tools import choose_h264_encoder, h264_encoder_args, probe_duration

COVER_FRAMES = 3
FPS = 24


def apply(video: Path, thumb: Path, out: Path, frames: int = COVER_FRAMES) -> Path:
    """video with its first `frames` frames replaced by thumb, thumb as cover art; audio copied."""
    encoder = choose_h264_encoder("auto")
    tmp = out.with_name(out.stem + ".cover-tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-loop", "1", "-framerate", str(FPS), "-t", f"{(frames + 2) / FPS:.3f}", "-i", str(thumb),
         "-i", str(thumb),
         "-filter_complex",
         "[1:v]scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p[t];"
         f"[0:v][t]overlay=0:0:enable='lt(n,{frames})':eof_action=pass:shortest=0,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a", "-map", "2:v",
         *h264_encoder_args(encoder, "p7", 14), "-c:a", "copy",
         "-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic",
         "-map_chapters", "-1", "-map_metadata", "-1", "-movflags", "+faststart", str(tmp)],
        check=True)
    got, want = probe_duration(tmp), probe_duration(video)
    if abs(got - want) > 0.1:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"cover changed the length of {video}: {want:.2f}s -> {got:.2f}s")
    tmp.replace(out)
    return out


def main() -> None:
    import argparse

    from amv.shorts import deliver
    from amv.shorts.find import SHORTS

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="Short names (default: every delivered one)")
    args = parser.parse_args()
    built = deliver._shorts()
    for name in args.names or sorted(built, key=lambda n: built[n].get("number", 10**6)):
        if not built.get(name, {}).get("number"):
            continue
        sid = f"S{built[name]['number']:03d}_{name}"
        dest = deliver.ROOT / sid
        src = SHORTS / name / "short.mp4"
        thumb = dest / f"{sid}_thumbnail.jpg"
        if not (src.exists() and thumb.exists()):
            print(f"  {sid}: skipped ({'no render' if not src.exists() else 'no thumbnail'})")
            continue
        apply(src, thumb, dest / f"{sid}.mp4")
        print(f"  {sid}: thumbnail is frame 0-{COVER_FRAMES - 1} + cover art")


if __name__ == "__main__":
    main()
