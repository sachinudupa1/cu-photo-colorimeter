"""The measurement agent.

It is a small, rule-based agent: it works through fixed steps (tools), each step
can stop the run or add a warning, and the final status tells you what to do next.
Every number comes from the calibration model, so the answer is reproducible.

    1. check_files     photos open, blank present
    2. check_quality   exposure, saturation, glare/bubbles in the ROI, blank drift
    3. measure         camera absorbance, spread between photos
    4. predict         concentration + 95 % interval
    5. check_range     below detection limit? above the trusted range?
    6. report          text summary, optional row in a CSV log

Status values:
    OK            result is trustworthy
    CHECK         result given, but read the warnings
    RETAKE        photos are bad, no number given (a wrong number is worse than none)
    BELOW_LOD     too faint to quantify, reported as '< LOD'
    OUT_OF_RANGE  too concentrated, dilute and measure again
    ERROR         files missing / unreadable
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from dataclasses import dataclass, field
from pathlib import Path

from .calibration import Calibration
from .features import PhotoStats, absorbance, photo_stats


@dataclass
class Thresholds:
    min_exposure: float = 0.12      # mean sRGB of blank in ROI must be in [min, max]
    max_exposure: float = 0.95
    max_saturated: float = 0.02     # fraction of pure-white pixels allowed in the ROI
    max_cv: float = 0.08            # brightness spread inside the ROI (glare, bubbles)
    max_blank_drift: float = 0.15   # blank today vs blank at calibration (fraction)
    max_photo_spread: float = 0.03  # std of A between photos of one solution (absolute)
    range_margin: float = 0.05      # allowed overshoot above the highest standard


@dataclass
class Report:
    sample_id: str
    status: str
    unit: str
    conc: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    absorbance: float | None = None
    a_std: float | None = None
    n_photos: int = 0
    warnings: list = field(default_factory=list)
    trace: list = field(default_factory=list)   # (step, outcome) pairs

    def text(self) -> str:
        lines = [f"Sample: {self.sample_id}", f"Status: {self.status}"]
        if self.absorbance is not None:
            lines.append(f"Camera absorbance: {self.absorbance:.3f}  "
                         f"(spread {self.a_std:.3f}, {self.n_photos} photos)")
        if self.status in ("OK", "CHECK") and self.conc is not None:
            lines.append(f"Concentration: {self.conc:.2f} {self.unit}  "
                         f"(95% interval {self.ci_low:.2f} to {self.ci_high:.2f})")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)


class ColorimetryAgent:
    def __init__(self, calibration: Calibration, thresholds: Thresholds | None = None,
                 log_path=None):
        self.cal = calibration
        self.th = thresholds or Thresholds()
        self.log_path = Path(log_path) if log_path else None

    # ------------------------------------------------------------------ steps
    def _load(self, paths, role, rep):
        out = []
        for p in paths:
            try:
                out.append(photo_stats(p, self.cal.roi))
            except Exception as e:  # unreadable / missing file
                rep.warnings.append(f"Cannot read {role} photo {p}: {e}")
        return out

    def _quality(self, blanks, samples, rep):
        """Return True if photos are good enough to measure."""
        th, serious = self.th, False
        for kind, group in (("blank", blanks), ("sample", samples)):
            for s in group:
                mean_srgb = sum(s.srgb_mean) / 3
                if kind == "blank" and not th.min_exposure <= mean_srgb <= th.max_exposure:
                    rep.warnings.append(f"Blank photo exposure is off ({mean_srgb:.2f}): "
                                        "too dark or too bright. Retake with the same light.")
                    serious = True
                if s.saturated_frac > th.max_saturated:
                    rep.warnings.append(f"{kind} photo has {s.saturated_frac:.0%} blown-out "
                                        f"pixels in the region ({Path(s.path).name}). "
                                        "Glare or overexposure. Retake.")
                    serious = True
                if s.cv > th.max_cv:
                    rep.warnings.append(f"{kind} photo is uneven inside the region "
                                        f"(spread {s.cv:.2f}, {Path(s.path).name}): glare, bubble "
                                        "or the solution is not centred.")
                    if s.cv > 2.5 * th.max_cv:
                        serious = True
        # lighting drift: is today's blank like the blank used when calibrating?
        if blanks and not math.isnan(self.cal.blank_level) and self.cal.blank_level > 0:
            level = sum(b.value(self.cal.channel, self.cal.linearize) for b in blanks) / len(blanks)
            drift = abs(level / self.cal.blank_level - 1)
            if drift > th.max_blank_drift:
                rep.warnings.append(f"Blank is {drift:.0%} different from calibration day. "
                                    "Light, phone or box position changed: results less reliable.")
        return not serious

    # ------------------------------------------------------------------- run
    def run(self, blank_paths, photo_paths, sample_id="sample") -> Report:
        cal, th = self.cal, self.th
        rep = Report(sample_id=sample_id, status="OK", unit=cal.unit)

        # 1. files
        blanks = self._load(blank_paths, "blank", rep)
        samples = self._load(photo_paths, "sample", rep)
        if not blanks or not samples:
            rep.status = "ERROR"
            rep.warnings.append("Need at least one readable blank photo and one sample photo.")
            rep.trace.append(("check_files", "failed"))
            return self._finish(rep)
        rep.trace.append(("check_files", f"{len(blanks)} blank + {len(samples)} sample photos"))

        # 2. quality
        ok = self._quality(blanks, samples, rep)
        rep.trace.append(("check_quality", "ok" if ok else "bad photos"))
        if not ok:
            rep.status = "RETAKE"
            return self._finish(rep)

        # 3. measure
        a, a_sd, _ = absorbance(samples, blanks, cal.channel, cal.linearize)
        rep.absorbance, rep.a_std, rep.n_photos = a, a_sd, len(samples)
        rep.trace.append(("measure", f"A = {a:.3f}"))
        if len(samples) > 1 and a_sd > th.max_photo_spread:
            rep.warnings.append(f"Photos of this solution disagree (spread {a_sd:.3f}). "
                                "Take them again without moving anything.")

        # 4. predict
        conc = cal.predict(a)
        lo, hi = cal.interval(a, m=len(samples))
        rep.conc, rep.ci_low, rep.ci_high = conc, lo, hi
        rep.trace.append(("predict", f"{conc:.2f} {cal.unit}"))

        # 5. range
        a_lod = cal.intercept + cal.lod * cal.slope
        if a <= a_lod:
            rep.status = "BELOW_LOD"
            rep.warnings.append(f"Below the detection limit (about {cal.lod:.2f} {cal.unit}). "
                                "Report as '< LOD'; use the colorimeter for this one.")
        elif conc > cal.conc_max * (1 + th.range_margin):
            rep.status = "OUT_OF_RANGE"
            rep.warnings.append(f"Above the highest standard ({cal.conc_max:g} {cal.unit}). "
                                "Dilute (same NH3 in every flask) and measure again. "
                                "Do not trust the number.")
        else:
            if conc < cal.conc_min:
                rep.warnings.append(f"Below the lowest standard ({cal.conc_min:g}). "
                                    "Less reliable; add a lower standard if this matters.")
            if rep.warnings:
                rep.status = "CHECK"
        rep.trace.append(("check_range", rep.status))
        return self._finish(rep)

    # -------------------------------------------------------------- reporting
    def _finish(self, rep: Report) -> Report:
        rep.trace.append(("report", rep.status))
        if self.log_path:
            new = not self.log_path.exists()
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "sample_id", "status", "conc", "ci_low", "ci_high",
                                "absorbance", "n_photos", "unit", "warnings"])
                give = rep.status in ("OK", "CHECK")
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"), rep.sample_id,
                            rep.status,
                            f"{rep.conc:.3f}" if give and rep.conc is not None else "",
                            f"{rep.ci_low:.3f}" if give and rep.ci_low is not None else "",
                            f"{rep.ci_high:.3f}" if give and rep.ci_high is not None else "",
                            f"{rep.absorbance:.4f}" if rep.absorbance is not None else "",
                            rep.n_photos, rep.unit, " | ".join(rep.warnings)])
        return rep
