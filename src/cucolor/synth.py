"""Synthetic photos of a blue solution, so the whole pipeline can be tested without a lab.

IMPORTANT: results on synthetic photos only show that the CODE works. They are not
experimental results and must never be presented as such in the report.

The photo is a white background with a tube-shaped solution in the middle. The
solution transmits light by Beer-Lambert, per colour channel:

    T_c = 10 ** (-eps_c * conc)

Two scenarios:
    "box"   fixed light, locked camera: tiny brightness jitter, small noise
    "room"  ordinary room: big brightness changes, a light gradient, glare, and
            the phone's auto-exposure (it brightens dark solutions, which hides
            the colour change)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from .features import srgb_to_linear  # noqa: F401  (kept for symmetry / tests)

# absorbance per mL of stock (red is absorbed most by the Cu-NH3 complex)
EPS = {"R": 0.030, "G": 0.010, "B": 0.0015}
W, H = 480, 640


def _linear_to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def render_photo(conc, rng, scenario="box", session_gain=1.0, roi_shift=0.0):
    """Return an HxWx3 uint8 image of a solution with concentration `conc` (mL stock)."""
    y, x = np.mgrid[0:H, 0:W]
    xf, yf = x / W, y / H
    flare = 0.01 if scenario == "box" else 0.03

    base = 0.80 * session_gain
    if scenario == "box":
        gain = rng.normal(1.0, 0.004)
        noise = 0.004
        vignette = 1 - 0.10 * ((xf - 0.5) ** 2 + (yf - 0.5) ** 2)
    else:
        gain = rng.normal(1.0, 0.12)
        noise = 0.010
        vignette = 1 - 0.30 * ((xf - rng.uniform(0.2, 0.8)) ** 2 + (yf - 0.5) ** 2) \
            + rng.uniform(-0.1, 0.1) * (xf - 0.5)

    light = base * gain * vignette
    img = np.stack([light] * 3, axis=-1)

    # the solution: a vertical tube in the middle
    cx = 0.5 + roi_shift
    tube = (np.abs(xf - cx) < 0.13) & (yf > 0.12) & (yf < 0.88)
    for c, name in enumerate("RGB"):
        t = 10 ** (-EPS[name] * conc)
        t = (t + flare) / (1 + flare)       # stray light / flare
        img[..., c] = np.where(tube, img[..., c] * t, img[..., c])

    if scenario == "room" and rng.random() < 0.4:   # glare spot on the glass
        gx, gy = rng.uniform(cx - 0.06, cx + 0.06), rng.uniform(0.3, 0.7)
        glare = np.exp(-(((xf - gx) / 0.03) ** 2 + ((yf - gy) / 0.05) ** 2))
        img += (0.5 * glare * tube)[..., None]

    if scenario == "room":   # phone auto-exposure: scale so the average is 'normal'
        img *= 0.45 / max(float(img.mean()), 1e-6)

    img = img + rng.normal(0, noise, img.shape)
    return (_linear_to_srgb(img) * 255).round().astype(np.uint8)


def true_absorbance(conc):
    """What a good colorimeter (red filter) would read, with a little stray light."""
    t = 10 ** (-EPS["R"] * conc)
    return float(-np.log10((t + 0.01) / 1.01))


def make_dataset(out_dir, scenario="box", seed=0,
                 train_conc=(2, 4, 6, 9, 12, 15, 18, 21, 24, 28),
                 test_conc=(7.5, 16.5, 25.5), unknown_conc=(5.0, 13.0, 22.0),
                 photos_per_solution=5, blanks=5, eval_gain=0.96):
    """Write photos + manifest.csv. Session 'day1' = calibration, 'day2' = evaluation
    day with slightly different lighting. Returns the manifest DataFrame."""
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    (out / "photos").mkdir(parents=True, exist_ok=True)
    rows = []

    def add(session, sample_id, role, conc, n, gain, shift, colorimeter=None):
        for k in range(n):
            name = f"{session}_{sample_id}_{k + 1}.jpg"
            Image.fromarray(render_photo(conc, rng, scenario, gain, shift)).save(
                out / "photos" / name, quality=92)
            rows.append(dict(file=name, sample_id=f"{session}_{sample_id}", role=role,
                             conc=(np.nan if role == "unknown" else conc), session=session,
                             true_conc=conc, colorimeter_abs=colorimeter))

    for session, gain, shift in (("day1", 1.0, 0.0), ("day2", eval_gain, 0.005)):
        add(session, "blank", "blank", 0.0, blanks, gain, shift)
        if session == "day1":
            for c in train_conc:
                add(session, f"std{c}", "standard", c, photos_per_solution, gain, shift,
                    true_absorbance(c) + rng.normal(0, 0.004))
        else:
            for c in test_conc:
                add(session, f"test{c}", "test", c, photos_per_solution, gain, shift,
                    true_absorbance(c) + rng.normal(0, 0.004))
            for c in unknown_conc:
                add(session, f"unk{c}", "unknown", c, photos_per_solution, gain, shift,
                    true_absorbance(c) + rng.normal(0, 0.004))

    df = pd.DataFrame(rows)
    df.to_csv(out / "manifest.csv", index=False)
    return df
