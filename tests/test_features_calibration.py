import math

import numpy as np
import pytest
from PIL import Image

from cucolor.calibration import Calibration, fit_calibration, metrics
from cucolor.features import absorbance, photo_stats, srgb_to_linear
from cucolor.synth import _linear_to_srgb


def solid(path, lin_rgb, size=(60, 80)):
    """Save a flat-colour image whose LINEAR light values are lin_rgb."""
    srgb = _linear_to_srgb(np.array(lin_rgb, dtype=float))
    arr = np.ones((size[1], size[0], 3)) * srgb
    Image.fromarray((arr * 255).round().astype(np.uint8)).save(path)
    return path


def test_srgb_roundtrip():
    x = np.linspace(0, 1, 11)
    assert np.allclose(srgb_to_linear(_linear_to_srgb(x)), x, atol=1e-6)


def test_half_the_light_is_absorbance_0301(tmp_path):
    blank = photo_stats(solid(tmp_path / "b.png", (0.8, 0.8, 0.8)))
    sample = photo_stats(solid(tmp_path / "s.png", (0.4, 0.8, 0.8)))
    a, sd, _ = absorbance([sample], [blank], "R", True)
    assert a == pytest.approx(math.log10(2), abs=0.005)
    g, _, _ = absorbance([sample], [blank], "G", True)
    assert g == pytest.approx(0.0, abs=0.005)      # green unchanged
    assert sd == 0.0


def test_blank_cancels_overall_brightness(tmp_path):
    # same solution, lamp 30% dimmer: blank-referenced absorbance must not change
    b1 = photo_stats(solid(tmp_path / "b1.png", (0.8, 0.8, 0.8)))
    s1 = photo_stats(solid(tmp_path / "s1.png", (0.4, 0.6, 0.7)))
    b2 = photo_stats(solid(tmp_path / "b2.png", (0.56, 0.56, 0.56)))
    s2 = photo_stats(solid(tmp_path / "s2.png", (0.28, 0.42, 0.49)))
    a1 = absorbance([s1], [b1], "R", True)[0]
    a2 = absorbance([s2], [b2], "R", True)[0]
    assert a1 == pytest.approx(a2, abs=0.01)


def test_roi_ignores_outside(tmp_path):
    arr = np.ones((100, 100, 3)) * 0.5
    arr[:, :20] = 1.0                                   # bright strip outside the ROI
    Image.fromarray((arr * 255).astype(np.uint8)).save(tmp_path / "x.png")
    st = photo_stats(tmp_path / "x.png", roi=(0.4, 0.3, 0.6, 0.7))
    assert st.srgb_mean[0] == pytest.approx(0.5, abs=0.01)
    assert st.saturated_frac == 0


def test_fit_recovers_line():
    c = np.array([2, 4, 6, 8, 10, 12.0])
    a = 0.03 * c + 0.01
    cal = fit_calibration(c, a)
    assert cal.slope == pytest.approx(0.03)
    assert cal.intercept == pytest.approx(0.01)
    assert cal.r2 == pytest.approx(1.0)
    assert cal.predict(0.19) == pytest.approx(6.0)
    assert cal.curvature_gain == 0.0


def test_lod_formula_and_interval():
    rng = np.random.default_rng(0)
    c = np.linspace(2, 20, 10)
    a = 0.03 * c + rng.normal(0, 0.004, 10)
    cal = fit_calibration(c, a)
    assert cal.lod == pytest.approx(3.3 * cal.s_resid / cal.slope)
    assert cal.loq == pytest.approx(10 * cal.s_resid / cal.slope)
    lo, hi = cal.interval(0.03 * 10, m=3)
    assert lo < 10 < hi
    # measuring more photos never widens the interval
    lo1, hi1 = cal.interval(0.3, m=1)
    lo5, hi5 = cal.interval(0.3, m=5)
    assert (hi5 - lo5) < (hi1 - lo1)


def test_curvature_is_flagged():
    c = np.linspace(2, 40, 10)
    a = 1.5 * (1 - np.exp(-c / 20))                       # saturating curve
    assert fit_calibration(c, a).curvature_gain > 0.5


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        fit_calibration([1, 2, 3], [0.1, 0.2, 0.3])        # too few standards
    with pytest.raises(ValueError):
        fit_calibration([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1])  # negative slope


def test_metrics():
    m = metrics([10, 20, 0], [11, 18, 0.5])
    assert m["mae"] == pytest.approx((1 + 2 + 0.5) / 3)
    assert m["mape_pct"] == pytest.approx((10 + 10) / 2)     # zero skipped
    assert m["max_abs_err"] == 2


def test_save_load_roundtrip(tmp_path):
    cal = fit_calibration([1, 2, 3, 4, 5], [0.1, 0.21, 0.29, 0.41, 0.5], unit="mL", blank_level=0.7)
    cal.save(tmp_path / "m.json")
    back = Calibration.load(tmp_path / "m.json")
    assert back == cal


def test_resolution_requires_independent_preparations_and_detects_separation():
    from cucolor.resolution import estimate_minimum_distinguishable_difference

    rows = []
    rng = np.random.default_rng(12)
    # Each row is a separately prepared solution, not an individual photograph.
    for conc, mean in [(5.0, 0.10), (5.5, 0.101), (6.0, 0.20)]:
        for _ in range(8):
            rows.append({"concentration": conc, "signal": float(rng.normal(mean, 0.002))})
    result = estimate_minimum_distinguishable_difference(rows)
    assert result.status == "ESTIMATED"
    assert result.minimum_tested_difference == pytest.approx(0.5)
    assert result.pairs[0].distinguishable is False
    assert result.pairs[1].distinguishable is True


def test_resolution_does_not_treat_photos_as_independent_preparations():
    from cucolor.resolution import estimate_minimum_distinguishable_difference

    rows = [
        {"concentration": 5.0, "signal": 0.10},
        {"concentration": 5.0, "signal": 0.11},
        {"concentration": 6.0, "signal": 0.20},
        {"concentration": 6.0, "signal": 0.21},
    ]
    result = estimate_minimum_distinguishable_difference(rows)
    assert result.status == "INSUFFICIENT_REPLICATES"
    assert result.minimum_tested_difference is None
