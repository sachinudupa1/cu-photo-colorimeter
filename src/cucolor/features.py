"""Turn a photo into numbers.

Idea (same as the colorimeter, but the camera is the detector):

    A = -log10(I_sample / I_blank)

I is the average brightness of one colour channel inside a small region (ROI)
in the middle of the solution. The blank is the photo of the reference solution
(NH3 + water, no copper) taken in the same session, so lighting changes cancel.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Region of interest as fractions of the image: (x0, y0, x1, y1).
# Default = a narrow strip in the middle. Use scripts/preview_roi.py to check it.
DEFAULT_ROI = (0.42, 0.30, 0.58, 0.70)
CHANNELS = {"R": 0, "G": 1, "B": 2}
_EPS = 1e-6


def srgb_to_linear(x):
    """Phone photos are gamma-encoded (sRGB). Light intensity is the linear value."""
    x = np.asarray(x, dtype=float)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def load_rgb(path) -> np.ndarray:
    """Load an image as float RGB in 0..1, respecting the phone's rotation tag."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return np.asarray(img.convert("RGB"), dtype=float) / 255.0


def crop(arr: np.ndarray, roi) -> np.ndarray:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = roi
    sub = arr[int(y0 * h): int(y1 * h), int(x0 * w): int(x1 * w)]
    if sub.size == 0:
        raise ValueError(f"ROI {roi} selects no pixels")
    return sub


@dataclass
class PhotoStats:
    path: str
    lin_mean: tuple        # mean linear R, G, B in the ROI
    srgb_mean: tuple       # mean sRGB R, G, B (0..1) in the ROI
    cv: float              # spread of brightness in the ROI (glare, bubbles, bad ROI)
    saturated_frac: float  # fraction of ROI pixels that are (nearly) pure white

    def value(self, channel: str = "R", linearize: bool = True) -> float:
        i = CHANNELS[channel]
        return float((self.lin_mean if linearize else self.srgb_mean)[i])


def photo_stats(path, roi=DEFAULT_ROI) -> PhotoStats:
    arr = load_rgb(path)
    sub = crop(arr, roi)
    lin = srgb_to_linear(sub)
    lum = lin.mean(axis=2)
    cv = float(lum.std() / max(lum.mean(), _EPS))
    saturated = float((sub.max(axis=2) >= 0.99).mean())
    return PhotoStats(
        path=str(path),
        lin_mean=tuple(float(v) for v in lin.reshape(-1, 3).mean(axis=0)),
        srgb_mean=tuple(float(v) for v in sub.reshape(-1, 3).mean(axis=0)),
        cv=cv,
        saturated_frac=saturated,
    )


def absorbance(samples, blanks, channel: str = "R", linearize: bool = True):
    """Camera absorbance of a solution from one or more photos.

    Returns (mean A, std of A across photos, list of per-photo A).
    The blank level is the mean over all blank photos.
    """
    blank = float(np.mean([b.value(channel, linearize) for b in blanks]))
    blank = max(blank, _EPS)
    per_photo = [-np.log10(max(s.value(channel, linearize), _EPS) / blank) for s in samples]
    std = float(np.std(per_photo, ddof=1)) if len(per_photo) > 1 else 0.0
    return float(np.mean(per_photo)), std, [float(a) for a in per_photo]


def hue_degrees(stats: PhotoStats) -> float:
    """HSV hue (0-360) of the mean colour. Used only for method comparison."""
    r, g, b = stats.srgb_mean
    return 360.0 * colorsys.rgb_to_hsv(r, g, b)[0]
