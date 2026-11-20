"""Empirical concentration-resolution analysis.

The input must contain one row per independently prepared solution, with a
mean camera absorbance (or predicted concentration) for that prepared solution.
Multiple photos of one flask are technical replicates and MUST be averaged
before calling this function; they are not independent solution replicates.

The reported value is the smallest *tested adjacent concentration gap* whose
signal distributions are statistically distinguishable after Holm correction.
It is not a universal instrument specification and should be reported with the
replicate count and experimental conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
from scipy import stats


@dataclass
class PairResolution:
    lower_concentration: float
    upper_concentration: float
    difference: float
    lower_n: int
    upper_n: int
    mean_signal_difference: float
    p_value: float
    adjusted_p_value: float
    distinguishable: bool


@dataclass
class ResolutionResult:
    alpha: float
    minimum_tested_difference: float | None
    status: str
    minimum_independent_replicates: int
    pairs: list[PairResolution]
    note: str

    def to_dict(self) -> dict:
        result = asdict(self)
        return result


def _holm_adjust(p_values: Iterable[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in original order."""
    p = np.asarray(list(p_values), dtype=float)
    if p.size == 0:
        return []
    order = np.argsort(p)
    adjusted_sorted = np.maximum.accumulate((p[order] * (len(p) - np.arange(len(p)))))
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0)
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist()


def estimate_minimum_distinguishable_difference(
    rows: Iterable[dict],
    *,
    concentration_key: str = "concentration",
    signal_key: str = "signal",
    alpha: float = 0.05,
    min_replicates: int = 3,
) -> ResolutionResult:
    """Estimate the smallest tested adjacent concentration gap distinguishable.

    Each row represents an independently prepared solution. Compare adjacent
    concentration groups using Welch's two-sample t-test, then apply Holm
    correction across all adjacent comparisons. A group needs at least
    ``min_replicates`` independently prepared solutions.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if min_replicates < 2:
        raise ValueError("min_replicates must be at least 2")

    grouped: dict[float, list[float]] = {}
    for row in rows:
        try:
            concentration = float(row[concentration_key])
            signal = float(row[signal_key])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(concentration) and np.isfinite(signal):
            grouped.setdefault(concentration, []).append(signal)

    levels = sorted(grouped)
    if len(levels) < 2:
        return ResolutionResult(
            alpha, None, "INSUFFICIENT_LEVELS", min_replicates, [],
            "At least two distinct concentrations with sufficient independent preparations are required.",
        )

    eligible = [c for c in levels if len(grouped[c]) >= min_replicates]
    if len(eligible) < 2:
        return ResolutionResult(
            alpha, None, "INSUFFICIENT_REPLICATES", min_replicates, [],
            f"Each concentration needs at least {min_replicates} independently prepared solutions. "
            "Repeated photos of one flask do not count as independent preparations.",
        )

    # Only compare levels that are adjacent in the complete experimental series.
    # Do not silently skip an under-replicated concentration and compare across it.
    adjacent_pairs = [
        (lower, upper)
        for lower, upper in zip(levels, levels[1:])
        if len(grouped[lower]) >= min_replicates and len(grouped[upper]) >= min_replicates
    ]
    if not adjacent_pairs:
        return ResolutionResult(
            alpha, None, "INSUFFICIENT_REPLICATES", min_replicates, [],
            f"At least one adjacent concentration pair needs {min_replicates} independent preparations at both levels.",
        )

    comparisons = []
    raw_p = []
    for lower, upper in adjacent_pairs:
        low = np.asarray(grouped[lower], dtype=float)
        high = np.asarray(grouped[upper], dtype=float)
        test = stats.ttest_ind(low, high, equal_var=False, nan_policy="omit")
        p_value = float(test.pvalue) if np.isfinite(test.pvalue) else 1.0
        raw_p.append(p_value)
        comparisons.append({
            "lower": lower, "upper": upper, "low": low, "high": high,
            "p": p_value,
        })

    adjusted = _holm_adjust(raw_p)
    pairs: list[PairResolution] = []
    for item, p_adj in zip(comparisons, adjusted):
        pairs.append(PairResolution(
            lower_concentration=float(item["lower"]),
            upper_concentration=float(item["upper"]),
            difference=float(item["upper"] - item["lower"]),
            lower_n=len(item["low"]), upper_n=len(item["high"]),
            mean_signal_difference=float(np.mean(item["high"]) - np.mean(item["low"])),
            p_value=float(item["p"]), adjusted_p_value=float(p_adj),
            distinguishable=bool(p_adj < alpha),
        ))

    detected = [pair.difference for pair in pairs if pair.distinguishable]
    if detected:
        minimum = float(min(detected))
        status = "ESTIMATED"
        note = (
            "Smallest tested adjacent concentration gap meeting the statistical criterion. "
            "This applies only to the tested phone, lighting, blank, ROI, chemistry and preparation protocol."
        )
    else:
        minimum = None
        status = "NO_TESTED_GAP_DISTINGUISHED"
        note = "No adjacent tested concentration pair met the corrected significance criterion."

    return ResolutionResult(alpha, minimum, status, min_replicates, pairs, note)
