"""Compose YouTube thumbnails from real frames — no image generation.

Thumbnails come from the *original* footage, not the graded render — the video
is deliberately cool and vignetted, which is the opposite of what reads at
120px in a YouTube sidebar.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from amv.thumbnail.layout import OUT_DIR, thumbnails
from amv.thumbnail.render import render


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    for thumb in thumbnails():
        if not thumb.source.exists():
            raise SystemExit(f"Missing source frame {thumb.source} - run 'python -m amv.vision.thumb_candidates'")
        print(f"Wrote {render(thumb, args.out)}")


if __name__ == "__main__":
    main()
