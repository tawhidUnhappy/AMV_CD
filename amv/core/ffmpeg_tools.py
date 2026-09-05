"""ffmpeg/ffprobe helpers.

Thin wrappers over the ffmpeg CLI: command running, concat files, stream
probing, and encoder selection. The only external requirements are `ffmpeg` and
`ffprobe` on PATH.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


def run(
    command: list[str],
    *,
    capture: bool = False,
    quiet_ffmpeg: bool = True,
    print_command: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if quiet_ffmpeg and command and Path(command[0]).name.lower() == "ffmpeg" and "-loglevel" not in command:
        insert_at = 2 if len(command) > 1 and command[1] == "-hide_banner" else 1
        command = command[:insert_at] + ["-loglevel", "error"] + command[insert_at:]
    if print_command:
        print(" ".join(shlex.quote(part) for part in command), flush=True)
    return subprocess.run(
        command,
        check=check,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ffconcat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def write_concat_file(paths: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        f.write("ffconcat version 1.0\n")
        for path in paths:
            f.write(f"file '{ffconcat_path(path)}'\n")
    return output


def probe_json(path: Path, entries: str) -> dict:
    result = run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
        capture=True,
        quiet_ffmpeg=False,
        print_command=False,
    )
    return json.loads(result.stdout or "{}")


def probe_duration(path: Path) -> float:
    data = probe_json(path, "format=duration")
    value = data.get("format", {}).get("duration")
    if value is None:
        raise ValueError(f"Could not read duration: {path}")
    return max(0.08, float(value))


TEXT_SUBTITLE_CODECS = {"ass", "ssa", "subrip", "srt", "mov_text", "webvtt"}
BITMAP_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}


def subtitle_streams(path: Path) -> list[dict]:
    """All subtitle streams, each tagged with its per-type `position` (what
    `-map 0:s:N` expects) alongside ffprobe's fields."""
    data = probe_json(path, "stream=index,codec_type,codec_name:stream_tags=language,NUMBER_OF_BYTES")
    streams = []
    position = 0
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        stream["position"] = position
        streams.append(stream)
        position += 1
    return streams


def subtitle_stream_index(path: Path) -> tuple[int, str]:
    """(position, codec_name) of the best subtitle stream to use.

    ffmpeg's `-map 0:s:N` numbering is per-type, so the returned position is N
    (not the absolute stream index). Prefers an English text track. Falls back
    to a bitmap (PGS/VobSub) track when that's all there is — some releases
    ship multiple PGS tracks (e.g. a small "signs only" one alongside the full
    dialogue track), so among bitmap tracks pick the largest by encoded byte
    size, which is reliably the full-dialogue one (see amv-clip-selection).
    """
    streams = subtitle_streams(path)
    text_fallback: int | None = None
    best_bitmap: tuple[int, int] | None = None  # (position, size)
    for stream in streams:
        codec = stream.get("codec_name", "")
        language = (stream.get("tags", {}) or {}).get("language", "").lower()
        position = stream["position"]
        if codec in TEXT_SUBTITLE_CODECS:
            if text_fallback is None:
                text_fallback = position
            if language in {"eng", "en"}:
                return position, codec
        elif codec in BITMAP_SUBTITLE_CODECS:
            size = int((stream.get("tags", {}) or {}).get("NUMBER_OF_BYTES", 0) or 0)
            if best_bitmap is None or size > best_bitmap[1]:
                best_bitmap = (position, size)
    if text_fallback is not None:
        return text_fallback, next(s["codec_name"] for s in streams if s["position"] == text_fallback)
    if best_bitmap is not None:
        position = best_bitmap[0]
        return position, next(s["codec_name"] for s in streams if s["position"] == position)
    raise ValueError(f"No subtitle stream found in {path}")


def available_encoders() -> set[str]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return set()
    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


def choose_h264_encoder(requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    encoders = available_encoders()
    for candidate in ("h264_nvenc", "h264_amf", "h264_qsv", "h264_videotoolbox"):
        if candidate in encoders:
            print(f"Auto video encoder: {candidate}", flush=True)
            return candidate
    print("Auto video encoder: libx264", flush=True)
    return "libx264"


def h264_encoder_args(encoder: str, preset: str, cq: int) -> list[str]:
    if encoder == "libx264":
        x264_preset = {
            "p1": "ultrafast",
            "p2": "superfast",
            "p3": "veryfast",
            "p4": "fast",
            "p5": "medium",
            "p6": "slow",
            "p7": "veryslow",
        }.get(preset, preset)
        return ["-c:v", "libx264", "-preset", x264_preset, "-crf", str(cq)]
    if encoder == "h264_videotoolbox":
        return ["-c:v", encoder, "-q:v", str(max(1, min(100, cq)))]
    if encoder in {"h264_amf", "h264_qsv"}:
        return ["-c:v", encoder, "-global_quality", str(cq)]
    return ["-c:v", encoder, "-preset", preset, "-tune", "hq", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
