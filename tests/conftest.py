import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cucolor.calibration import fit_calibration  # noqa: E402
from cucolor.pipeline import measure_manifest  # noqa: E402
from cucolor.synth import make_dataset, render_photo  # noqa: E402


def shoot(folder, name, conc, seed=0, gain=1.0, n=3, scenario="box"):
    """Save n synthetic photos of a solution; return their paths."""
    rng = np.random.default_rng(seed)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in range(n):
        p = folder / f"{name}_{k}.jpg"
        Image.fromarray(render_photo(conc, rng, scenario, gain)).save(p, quality=92)
        paths.append(p)
    return paths


@pytest.fixture(scope="session")
def box_data(tmp_path_factory):
    d = tmp_path_factory.mktemp("box")
    df = make_dataset(d, scenario="box", seed=11)
    return d, df


@pytest.fixture(scope="session")
def calibration(box_data):
    d, _ = box_data
    feat = measure_manifest(d / "manifest.csv", d / "photos")
    std = feat[feat.role == "standard"]
    return fit_calibration(
        std.conc, std.A_R, channel="R", linearize=True, unit="mL stock",
        blank_level=float(std.blank_level_R.mean()),
    )
