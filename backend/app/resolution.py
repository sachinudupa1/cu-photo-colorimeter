"""Helpers that explain the empirical resolution result in API responses."""
from cucolor.resolution import estimate_minimum_distinguishable_difference


def resolution_summary(rows: list[dict], signal_key: str = "camera_absorbance") -> dict:
    result = estimate_minimum_distinguishable_difference(
        rows,
        concentration_key="concentration",
        signal_key=signal_key,
        alpha=0.05,
        min_replicates=3,
    )
    return result.to_dict()
