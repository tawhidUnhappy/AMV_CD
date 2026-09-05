"""Decode a Blu-ray PGS (.sup) subtitle stream into timed bitmap events.

PGS carries pre-rendered bitmaps, not text — ffmpeg's `-c:s ass` conversion
that works for text tracks (see ass_parser.py) cannot touch it. This module
only does the binary decode (segments -> RLE bitmap -> cropped RGBA image);
turning those images into text is OCR's job (see pgs_ocr.py).

Format reference: the "Presentation Graphic Stream" segment layout used on
Blu-ray subtitle tracks. Decoding logic (segment parsing, RLE run decode,
YCbCr->RGB) is adapted from the pgsrip project (MIT-licensed) and trimmed to
just what this pipeline needs — no OpenCV, no OCR, no ripper/CLI machinery.
"""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class SegmentType(enum.Enum):
    PDS = 0x14  # Palette Definition
    ODS = 0x15  # Object Definition (the bitmap)
    PCS = 0x16  # Presentation Composition (when/where to show it)
    WDS = 0x17  # Window Definition (the display region)
    END = 0x80  # End of display set


@dataclass
class _Segment:
    type: SegmentType
    pts: float  # seconds
    payload: bytes


def _read_segments(data: bytes):
    i = 0
    n = len(data)
    while i + 13 <= n:
        if data[i:i + 2] != b"PG":
            break
        pts_90k, _dts_90k, seg_type, size = struct.unpack_from(">IIBH", data, i + 2)
        start = i + 13
        yield _Segment(SegmentType(seg_type), pts_90k / 90000.0, data[start:start + size])
        i = start + size


@dataclass
class SubtitleBitmap:
    start: float
    end: float
    x: int
    y: int
    width: int
    height: int
    image: np.ndarray  # (h, w, 4) uint8 RGBA


def _decode_rle(data: bytes, width: int, height: int, palette: dict[int, tuple[int, int, int, int]]) -> np.ndarray:
    """Decode PGS's run-length-encoded, palette-indexed bitmap to RGBA."""
    out = np.zeros((height * width, 4), dtype=np.uint8)
    pos = 0
    i = 0
    n = len(data)
    while i < n and pos < height * width:
        first = data[i]
        if first != 0:
            length, color = 1, first
            i += 1
        else:
            second = data[i + 1]
            if second == 0:
                # end of line
                pos = ((pos // width) + 1) * width
                i += 2
                continue
            elif second < 64:
                length, color, i = second, 0, i + 2
            elif second < 128:
                length = ((second - 64) << 8) + data[i + 2]
                color, i = 0, i + 3
            elif second < 192:
                length, color, i = second - 128, data[i + 2], i + 3
            else:
                length = ((second - 192) << 8) + data[i + 2]
                color, i = data[i + 3], i + 4
        y, cr, cb, alpha = palette.get(color, (0, 0, 0, 0))
        end = min(pos + length, height * width)
        # BT.601 YCbCr -> RGB
        yf = y - 16
        r = np.clip(1.164 * yf + 1.596 * (cr - 128), 0, 255)
        g = np.clip(1.164 * yf - 0.813 * (cr - 128) - 0.391 * (cb - 128), 0, 255)
        b = np.clip(1.164 * yf + 2.018 * (cb - 128), 0, 255)
        out[pos:end] = (int(r), int(g), int(b), alpha)
        pos = end
    return out.reshape(height, width, 4)


def decode_sup(path: Path) -> list[SubtitleBitmap]:
    """Parse a .sup file into one cropped, timed RGBA bitmap per subtitle."""
    data = path.read_bytes()

    events: list[SubtitleBitmap] = []
    window: tuple[int, int, int, int] | None = None  # x, y, w, h
    palette: dict[int, tuple[int, int, int, int]] = {}
    object_data = bytearray()
    object_size: tuple[int, int] | None = None
    start_pts: float | None = None
    has_object = False

    for seg in _read_segments(data):
        if seg.type == SegmentType.WDS and len(seg.payload) >= 10:
            # One window definition per display set here (num_windows == 1).
            x, y, w, h = struct.unpack_from(">HHHH", seg.payload, 2)
            window = (x, y, w, h)
        elif seg.type == SegmentType.PDS:
            n_entries = (len(seg.payload) - 2) // 5
            for e in range(n_entries):
                off = 2 + e * 5
                idx, y, cr, cb, alpha = struct.unpack_from(">BBBBB", seg.payload, off)
                palette[idx] = (y, cr, cb, alpha)
        elif seg.type == SegmentType.PCS:
            num_objects = seg.payload[10] if len(seg.payload) > 10 else 0
            if num_objects == 0 and has_object and start_pts is not None and window:
                # A composition with no objects clears the previous subtitle.
                events[-1] = SubtitleBitmap(
                    start=events[-1].start, end=seg.pts,
                    x=events[-1].x, y=events[-1].y,
                    width=events[-1].width, height=events[-1].height,
                    image=events[-1].image,
                )
                has_object = False
            elif num_objects > 0:
                start_pts = seg.pts
        elif seg.type == SegmentType.ODS:
            # sequence flag (first/last) is byte 3; width/height follow when present.
            seq = seg.payload[3]
            if seq in (0x80, 0xC0):  # FIRST or FIRST_AND_LAST: header present
                object_size = struct.unpack_from(">HH", seg.payload, 7)
                object_data = bytearray(seg.payload[11:])
            else:
                object_data.extend(seg.payload[4:])
            if seq in (0x40, 0xC0):  # LAST or FIRST_AND_LAST: object complete
                if window and object_size and start_pts is not None:
                    w, h = object_size
                    image = _decode_rle(bytes(object_data), w, h, palette)
                    x, y, _ww, _wh = window
                    events.append(SubtitleBitmap(start=start_pts, end=start_pts, x=x, y=y,
                                                  width=w, height=h, image=image))
                    has_object = True

    # Any subtitle still open when the stream ends (no trailing clear) gets a
    # nominal hold rather than zero duration.
    if events and events[-1].end <= events[-1].start:
        last = events[-1]
        events[-1] = SubtitleBitmap(start=last.start, end=last.start + 4.0, x=last.x, y=last.y,
                                     width=last.width, height=last.height, image=last.image)
    return [e for e in events if e.end > e.start]
