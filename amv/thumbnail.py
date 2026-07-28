"""Compose YouTube thumbnails from real frames — no image generation.

Follows the house style calibrated against D:\\thumbnail_examples: big ALL-CAPS
yellow #FFE600 labels, black stroke ~12% of font size, slight tilt, fat block
arrows pointing at the character each label names, bottom-right left clear for
YouTube's duration overlay.

Text and arrows are drawn through libass, which gives rotation, thick outlines
and vector shapes in a single pass — ffmpeg's drawtext cannot rotate.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "data" / "qa" / "thumbcand"
OUT_DIR = ROOT / "data" / "out" / "thumbnails"
FONT_DIR = ROOT / "data" / "work" / "thumbfonts"

WIDTH, HEIGHT = 1280, 720

# ASS colours are &HAABBGGRR.
YELLOW = "&H0000E6FF&"   # #FFE600
WHITE = "&H00FFFFFF&"
BLACK = "&H00000000&"
RED = "&H002222CC&"

LABEL_FONT = "Arial Black"
BRUSH_FONT = "Edo"

SYSTEM_FONTS = Path("C:/Windows/Fonts")
USER_FONTS = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"


@dataclass
class Text:
    body: str
    x: int
    y: int
    an: int = 5
    size: int = 96
    colour: str = YELLOW
    angle: float = -3.0
    font: str = LABEL_FONT
    outline: float | None = None  # defaults to 12% of size


@dataclass
class Arrow:
    """Fat block arrow.

    Give it `from_xy` (usually the label) and `to_xy` (the thing it names) and
    the position and angle are computed. Hand-guessing `x/y/angle` is what put
    the first batch of arrows on the wrong side of the frame and pointing at the
    back of a character's head — use `face_targets()` to find the real subject.
    """

    from_xy: tuple[int, int] | None = None
    to_xy: tuple[int, int] | None = None
    #: Fraction of the way from `from_xy` to `to_xy` at which to sit.
    along: float = 0.55
    #: Explicit placement, only for cases with no sensible target.
    x: int = 0
    y: int = 0
    angle: float = 0.0
    scale: float = 1.0
    colour: str = YELLOW

    def resolve(self) -> tuple[int, int, float]:
        if self.from_xy is None or self.to_xy is None:
            return self.x, self.y, self.angle
        fx, fy = self.from_xy
        tx, ty = self.to_xy
        px = int(fx + (tx - fx) * self.along)
        py = int(fy + (ty - fy) * self.along)
        angle = math.degrees(math.atan2(ty - fy, tx - fx))
        return px, py, angle


@dataclass
class Bubble:
    """Dark speech bubble sized to the text that sits on it."""

    x: int
    y: int
    width: int
    height: int
    tail_dx: int = 120
    tail_dy: int = 90
    angle: float = 0.0
    fill: str = "&H00101010&"


@dataclass
class Thumb:
    name: str
    source: Path
    texts: list[Text] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)
    bubbles: list[Bubble] = field(default_factory=list)
    #: Optional second frame for the side-by-side split layout.
    right_source: Path | None = None
    #: Zoom and horizontal framing per split panel. A half-width crop of a 16:9
    #: frame has only horizontal slack, so zoom in first to place a face.
    left_zoom: float = 1.0
    left_shift: float = 0.5    # 0 = crop hard left, 1 = hard right
    left_vshift: float = 0.5   # 0 = crop hard top, 1 = hard bottom
    right_zoom: float = 1.0
    right_shift: float = 0.5
    right_vshift: float = 0.5
    #: Extra punch so the thumbnail reads at sidebar size.
    grade: str = "eq=contrast=1.10:saturation=1.25:brightness=0.02,unsharp=5:5:0.6:5:5:0.0"


def face_targets(image: Path, halves: int = 2) -> list[tuple[int, int]]:
    """Best-effort face position per vertical band, in 1280x720 coordinates.

    UNRELIABLE ON THIS SOURCE — do not trust it blind. Mirai Nikki is full of
    warm tan interiors (tatami rooms, wood panelling, sunset light) that satisfy
    the skin predicate, so the density peak lands on a wall. It works on frames
    with cool or dark backgrounds and is useless on warm ones.

    Treat the output as a hint, set `Arrow.to_xy` from what you actually see in
    the rendered thumbnail, and verify by looking at the result either way.
    """
    import numpy as np

    w, h = 128, 72
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(image),
         "-vf", f"scale={w}:{h},format=rgb24", "-f", "rawvideo", "-"],
        capture_output=True, check=True,
    )
    rgb = np.frombuffer(result.stdout[: w * h * 3], dtype=np.uint8).reshape(h, w, 3).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    skin = ((r > 110) & (g > 70) & (b > 50) & (r > g) & (g >= b)
            & ((mx - mn) > 14) & ((r - b) > 18) & (r < 252)).astype(np.float32)

    # Densest compact patch, not the centroid: a centroid is dragged toward
    # arms and torso and lands on a character's chest or on empty background
    # between two people. A face is the tightest concentration of skin, so a
    # box-sum peak finds it far more reliably.
    box = 11
    kernel = np.ones((box, box), dtype=np.float32)
    padded = np.pad(skin, box // 2, mode="constant")
    density = np.zeros_like(skin)
    for dy in range(box):
        for dx in range(box):
            density += padded[dy : dy + h, dx : dx + w] * kernel[dy, dx]

    targets: list[tuple[int, int]] = []
    band = w // halves
    for i in range(halves):
        lo, hi = i * band, (i + 1) * band
        chunk = density[:, lo:hi]
        if chunk.max() < box:  # too little skin to call a face
            continue
        py, px = np.unravel_index(int(np.argmax(chunk)), chunk.shape)
        targets.append((int((px + lo) / w * WIDTH), int(py / h * HEIGHT)))
    return targets


def arrow_shape(scale: float) -> str:
    """A chunky right-pointing arrow as ASS drawing commands."""
    s = scale
    pts = [(0, -18), (52, -18), (52, -40), (104, 0), (52, 40), (52, 18), (0, 18)]
    body = " ".join(f"l {int(x * s)} {int(y * s)}" for x, y in pts[1:])
    return f"m {int(pts[0][0] * s)} {int(pts[0][1] * s)} {body}"


def bubble_shape(bubble: Bubble) -> str:
    """Rounded speech bubble with a tail, in absolute screen coordinates.

    Drawn absolutely and anchored with \\an7\\pos(0,0): ASS centres a drawing by
    its *bounding box*, so a long tail under an \\an5 anchor drags the whole
    bubble off its intended spot.
    """
    left, right = bubble.x - bubble.width // 2, bubble.x + bubble.width // 2
    top, bottom = bubble.y - bubble.height // 2, bubble.y + bubble.height // 2
    r = min(46, bubble.height // 4, bubble.width // 4)
    tx, ty = bubble.x + bubble.tail_dx, bubble.y + bubble.tail_dy
    return (
        f"m {left + r} {top} "
        f"l {right - r} {top} b {right} {top} {right} {top} {right} {top + r} "
        f"l {right} {bottom - r} b {right} {bottom} {right} {bottom} {right - r} {bottom} "
        f"l {tx + 45} {bottom} l {tx} {ty} l {tx - 55} {bottom} "
        f"l {left + r} {bottom} b {left} {bottom} {left} {bottom} {left} {bottom - r} "
        f"l {left} {top + r} b {left} {top} {left} {top} {left + r} {top}"
    )


def build_ass(thumb: Thumb) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: L,{LABEL_FONT},96,{YELLOW},{YELLOW},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,11,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = [header]
    for bubble in thumb.bubbles:
        rows.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an7\\pos(0,0)\\org({bubble.x},{bubble.y})\\frz{-bubble.angle}\\c{bubble.fill}"
            f"\\3c{WHITE}\\bord5\\shad0\\p1}}{bubble_shape(bubble)}{{\\p0}}"
        )
    for arrow in thumb.arrows:
        # Drawings honour \frz, so one shape serves every direction.
        ax, ay, angle = arrow.resolve()
        rows.append(
            f"Dialogue: 0,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an5\\pos({ax},{ay})\\frz{-angle}\\c{arrow.colour}"
            f"\\3c{BLACK}\\bord6\\p1}}{arrow_shape(arrow.scale)}{{\\p0}}"
        )
    for text in thumb.texts:
        outline = text.outline if text.outline is not None else round(text.size * 0.12, 1)
        body = text.body.replace("\n", "\\N")
        rows.append(
            f"Dialogue: 1,0:00:00.00,0:00:10.00,L,,0,0,0,,"
            f"{{\\an{text.an}\\pos({text.x},{text.y})\\fn{text.font}\\fs{text.size}"
            f"\\frz{-text.angle}\\c{text.colour}\\3c{BLACK}\\bord{outline}\\shad0}}{body}"
        )
    return "\n".join(rows) + "\n"


def stage_fonts() -> Path:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for source in (SYSTEM_FONTS / "ariblk.ttf", USER_FONTS / "edo.ttf", ROOT / "assets" / "georgiab.ttf"):
        if source.exists():
            shutil.copy(source, FONT_DIR / source.name)
    return FONT_DIR


def render(thumb: Thumb, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = ROOT / "data" / "work"
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / f"thumb_{thumb.name}.ass"
    ass_path.write_text(build_ass(thumb), encoding="utf-8")

    fonts = stage_fonts()
    ass_arg = ass_path.resolve().as_posix().replace(":", "\\:")
    fonts_arg = fonts.resolve().as_posix().replace(":", "\\:")
    output = out_dir / f"{thumb.name}.jpg"

    if thumb.right_source is not None:
        # Side-by-side: two half-width crops with a hard divider.
        half = WIDTH // 2

        def panel(index: int, zoom: float, shift: float, vshift: float) -> str:
            w, h = int(WIDTH * zoom), int(HEIGHT * zoom)
            return (
                f"[{index}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={half}:{HEIGHT}:(iw-{half})*{shift:.3f}:(ih-{HEIGHT})*{vshift:.3f},"
                f"{thumb.grade}"
            )

        graph = (
            f"{panel(0, thumb.left_zoom, thumb.left_shift, thumb.left_vshift)}[l];"
            f"{panel(1, thumb.right_zoom, thumb.right_shift, thumb.right_vshift)}[r];"
            f"[l][r]hstack=inputs=2,"
            f"drawbox=x={half - 4}:y=0:w=8:h={HEIGHT}:color=black@1:t=fill,"
            f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'[v]"
        )
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(thumb.source), "-i", str(thumb.right_source),
            "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "2", str(output),
        ]
    else:
        graph = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},{thumb.grade},"
            f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'"
        )
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(thumb.source),
            "-vf", graph, "-frames:v", "1", "-q:v", "2", str(output),
        ]
    subprocess.run(command, check=True)
    return output


def thumbnails() -> list[Thumb]:
    return [
        # 1. label-arrow, two labels — the proven house variant. cand04 has both
        # characters facing camera; cand00 showed Yuno from behind, so the
        # YANDERE label pointed at the back of her head.
        Thumb(
            name="01_label_arrow",
            source=CAND / "cand04.png",
            texts=[
                Text("HER\nOBSESSION", 250, 130, an=5, size=88, angle=-4.0),
                Text("YANDERE", 1000, 150, an=5, size=104, angle=3.0),
            ],
            # Targets read off the rendered frame, not guessed: Yuki's face sits
            # at ~(310,265) and Yuno's at ~(1040,355). The angle follows.
            arrows=[
                Arrow(from_xy=(250, 200), to_xy=(310, 265), along=0.75, scale=1.0),
                Arrow(from_xy=(1000, 215), to_xy=(1040, 350), along=0.72, scale=1.0),
            ],
        ),
        # 2. bubble — a line pulled straight from the song, in a dark bubble
        # with white brush text.
        Thumb(
            name="02_bubble",
            source=CAND / "cand05.png",
            bubbles=[Bubble(x=330, y=215, width=560, height=250, tail_dx=150, tail_dy=215, angle=-3.0)],
            texts=[
                Text("AM I A\nMONSTER?", 330, 200, an=5, size=96, colour=WHITE,
                     angle=-3.0, font=BRUSH_FONT, outline=0),
                Text("MIRAI NIKKI AMV", 300, 650, an=5, size=58, angle=-2.0),
            ],
        ),
        # 3. split — two frames, a label under each, badge top-centre.
        Thumb(
            name="03_split",
            # cand09 framed Yuno too high to survive a half-width crop — her
            # face kept landing above the cut. cand05 centres her instead.
            source=CAND / "cand05.png",
            right_source=CAND / "cand07.png",
            left_zoom=1.15,
            left_shift=0.52,
            left_vshift=0.30,
            right_zoom=1.05,
            right_shift=0.55,
            right_vshift=0.35,
            texts=[
                Text("MIRAI NIKKI", 640, 68, an=5, size=58, colour=WHITE, angle=0.0),
                Text("THE STALKER", 320, 630, an=5, size=76, angle=-3.0),
                Text("THE PREY", 960, 630, an=5, size=76, angle=3.0),
            ],
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    for thumb in thumbnails():
        if not thumb.source.exists():
            raise SystemExit(f"Missing source frame {thumb.source} - run amv/thumb_candidates.py")
        print(f"Wrote {render(thumb, args.out)}")


if __name__ == "__main__":
    main()
