import pytest

from cucolor.resolution import estimate_minimum_distinguishable_difference


def test_resolution_requires_independently_prepared_solution_rows():
    rows = [
        {"concentration": 1.0, "signal": value}
        for value in [0.10, 0.11, 0.09]
    ] + [
        {"concentration": 1.2, "signal": value}
        for value in [0.30, 0.31, 0.29]
    ]
    result = estimate_minimum_distinguishable_difference(rows, min_replicates=3)
    assert result.status == "ESTIMATED"
    assert result.minimum_tested_difference == pytest.approx(0.2)
    assert result.pairs[0].distinguishable is True


def test_resolution_does_not_count_three_photos_as_three_solutions():
    rows = [
        {"concentration": 1.0, "signal": 0.10},
        {"concentration": 1.2, "signal": 0.30},
    ]
    result = estimate_minimum_distinguishable_difference(rows, min_replicates=3)
    assert result.status == "INSUFFICIENT_REPLICATES"
    assert result.minimum_tested_difference is None


def test_resolution_does_not_skip_under_replicated_intermediate_level():
    rows = []
    rows += [{"concentration": 1.0, "signal": x} for x in [0.10, 0.11, 0.09]]
    rows += [{"concentration": 1.1, "signal": 0.20}]  # insufficient level
    rows += [{"concentration": 1.2, "signal": x} for x in [0.30, 0.31, 0.29]]
    result = estimate_minimum_distinguishable_difference(rows, min_replicates=3)
    assert result.status == "INSUFFICIENT_REPLICATES"
    assert result.pairs == []
