"""Straight-line calibration (Beer-Lambert) with the usual analytical-chemistry extras."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy import stats as sstats

from .features import DEFAULT_ROI


@dataclass
class Calibration:
    # A = slope * conc + intercept   (fitted on the standards)
    slope: float
    intercept: float
    n: int                 # number of standards used
    c_mean: float
    a_mean: float
    sxx: float             # sum((c - c_mean)^2)
    s_resid: float         # residual standard deviation of A
    r2: float
    lod: float             # 3.3 * s_resid / slope   (conc units)
    loq: float             # 10  * s_resid / slope
    conc_min: float        # lowest / highest standard = trusted range
    conc_max: float
    a_min: float
    a_max: float
    curvature_gain: float  # how much a quadratic fit improves on the line (0 = straight)
    channel: str = "R"
    linearize: bool = True
    roi: tuple = DEFAULT_ROI
    unit: str = "mL stock"
    blank_level: float = float("nan")  # blank brightness during calibration (drift check)

    # ---- prediction -------------------------------------------------------
    def predict(self, a: float) -> float:
        return (a - self.intercept) / self.slope

    def interval(self, a: float, m: int = 1, conf: float = 0.95):
        """Classical inverse-prediction interval for a solution measured m times."""
        if self.n < 3:
            return (float("nan"), float("nan"))
        t = sstats.t.ppf(0.5 + conf / 2, self.n - 2)
        sx0 = (self.s_resid / abs(self.slope)) * math.sqrt(
            1.0 / m + 1.0 / self.n
            + (a - self.a_mean) ** 2 / (self.slope ** 2 * self.sxx)
        )
        c = self.predict(a)
        return (c - t * sx0, c + t * sx0)

    # ---- save / load (plain JSON, nothing to unpickle) -------------------
    def save(self, path) -> None:
        d = asdict(self)
        d["roi"] = list(self.roi)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(d, indent=2))

    @staticmethod
    def load(path) -> "Calibration":
        d = json.loads(Path(path).read_text())
        d["roi"] = tuple(d["roi"])
        return Calibration(**d)


def fit_calibration(conc, absb, **meta) -> Calibration:
    """Fit A = slope*conc + intercept from per-solution mean absorbances."""
    c = np.asarray(conc, dtype=float)
    a = np.asarray(absb, dtype=float)
    if len(c) < 4:
        raise ValueError("Need at least 4 different standard concentrations")
    if np.ptp(c) == 0:
        raise ValueError("All standards have the same concentration")
    res = sstats.linregress(c, a)
    pred = res.slope * c + res.intercept
    s_resid = math.sqrt(float(np.sum((a - pred) ** 2)) / (len(c) - 2))

    # Does a curve fit much better than a line? Then the range is too wide.
    rmse_lin = math.sqrt(float(np.mean((a - pred) ** 2)))
    quad = np.polyval(np.polyfit(c, a, 2), c)
    rmse_quad = math.sqrt(float(np.mean((a - quad) ** 2)))
    gain = 0.0 if rmse_lin < 1e-12 else max(0.0, 1.0 - rmse_quad / rmse_lin)

    slope = float(res.slope)
    if slope <= 0:
        raise ValueError("Slope is not positive: absorbance does not rise with concentration. "
                         "Check the photos, the ROI and the concentrations in the manifest.")
    return Calibration(
        slope=slope, intercept=float(res.intercept), n=len(c),
        c_mean=float(c.mean()), a_mean=float(a.mean()),
        sxx=float(np.sum((c - c.mean()) ** 2)), s_resid=s_resid, r2=float(res.rvalue ** 2),
        lod=3.3 * s_resid / slope, loq=10.0 * s_resid / slope,
        conc_min=float(c.min()), conc_max=float(c.max()),
        a_min=float(a.min()), a_max=float(a.max()),
        curvature_gain=gain, **meta,
    )


def metrics(true, pred) -> dict:
    """Error numbers for the report. % error is skipped where true == 0."""
    t = np.asarray(true, dtype=float)
    p = np.asarray(pred, dtype=float)
    err = p - t
    nz = t != 0
    ss_tot = float(np.sum((t - t.mean()) ** 2))
    return {
        "n": int(len(t)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(math.sqrt(np.mean(err ** 2))),
        "mape_pct": float(np.mean(np.abs(err[nz] / t[nz])) * 100) if nz.any() else float("nan"),
        "max_abs_err": float(np.max(np.abs(err))),
        "r2": float(1 - np.sum(err ** 2) / ss_tot) if ss_tot > 0 else float("nan"),
    }
