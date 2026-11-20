"""Manifest CSV -> one row of features per solution.

Manifest columns (see data/README.md):
    file            photo file name (relative to the photo folder)
    sample_id       one id per solution (all photos of a solution share it)
    role            blank | standard | test | unknown
    conc            concentration (e.g. mL of stock in the flask). May be empty for unknown.
    session         label for the lab session; every session needs its own blank photos
    colorimeter_abs (optional) absorbance read on the real colorimeter for that solution
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .features import DEFAULT_ROI, absorbance, hue_degrees, photo_stats

REQUIRED = {"file", "sample_id", "role", "conc", "session"}
_EPS = 1e-6


def measure_manifest(manifest, photo_dir, roi=DEFAULT_ROI) -> pd.DataFrame:
    df = pd.read_csv(manifest)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Manifest is missing columns: {sorted(missing)}")
    photo_dir = Path(photo_dir)
    rows = []
    for session, g in df.groupby("session"):
        blank_files = g[g.role == "blank"].file
        if len(blank_files) == 0:
            raise ValueError(f"Session '{session}' has no blank photos")
        blanks = [photo_stats(photo_dir / f, roi) for f in blank_files]
        blank_lin_R = float(np.mean([b.value("R", True) for b in blanks]))
        for sid, gs in g[g.role != "blank"].groupby("sample_id", sort=False):
            stats = [photo_stats(photo_dir / f, roi) for f in gs.file]
            a_r, a_r_sd, _ = absorbance(stats, blanks, "R", True)
            a_g, _, _ = absorbance(stats, blanks, "G", True)
            a_b, _, _ = absorbance(stats, blanks, "B", True)
            a_r_srgb, _, _ = absorbance(stats, blanks, "R", False)
            srgb = np.mean([s.srgb_mean for s in stats], axis=0)
            row = {
                "sample_id": sid, "session": session, "role": gs.role.iloc[0],
                "conc": gs.conc.iloc[0], "n_photos": len(stats),
                "A_R": a_r, "A_R_std": a_r_sd, "A_G": a_g, "A_B": a_b,
                "A_R_srgb": a_r_srgb,
                # no blank: pretend the white background is exactly 1.0
                "A_R_raw": float(-np.log10(max(np.mean([s.value("R", True) for s in stats]), _EPS))),
                "hue": float(np.mean([hue_degrees(s) for s in stats])),
                "r": srgb[0], "g": srgb[1], "b": srgb[2],
                "blank_level_R": blank_lin_R,
            }
            if "colorimeter_abs" in gs.columns:
                row["colorimeter_abs"] = gs.colorimeter_abs.iloc[0]
            rows.append(row)
    return pd.DataFrame(rows)
