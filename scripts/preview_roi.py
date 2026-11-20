"""Draw the measurement region on a photo, so you can check it sits inside the solution.

    python scripts/preview_roi.py photo.jpg --roi 0.42 0.30 0.58 0.70

Saves results/roi_preview.png. The rectangle must be fully inside the coloured
solution: no glass edge, no meniscus, no background.
"""
import argparse
from pathlib import Path

import _paths  # noqa: F401
from PIL import Image, ImageDraw, ImageOps

from cucolor.features import DEFAULT_ROI

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("photo")
p.add_argument("--roi", type=float, nargs=4, default=list(DEFAULT_ROI), metavar=("X0", "Y0", "X1", "Y1"))
p.add_argument("--out", default="results/roi_preview.png")
a = p.parse_args()

img = ImageOps.exif_transpose(Image.open(a.photo)).convert("RGB")
w, h = img.size
x0, y0, x1, y1 = a.roi
ImageDraw.Draw(img).rectangle([x0 * w, y0 * h, x1 * w, y1 * h], outline=(255, 0, 0), width=max(2, w // 200))
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
img.save(a.out)
print(f"Saved {a.out}")
