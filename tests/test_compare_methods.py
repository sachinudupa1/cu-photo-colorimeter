import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("compare_methods", ROOT / "scripts" / "compare_methods.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_unknown_samples_are_not_scored_as_nan():
    rows = []
    for i, conc in enumerate([1, 2, 3, 4]):
        rows.append({"sample_id": f"s{i}", "role": "standard", "conc": conc,
                     "A_R": .03*conc, "A_R_srgb": .04*conc, "A_R_raw": .03*conc,
                     "A_G": .02*conc, "A_B": .01*conc, "hue": 200-conc,
                     "r": .9-conc*.01, "g": .8-conc*.01, "b": .7-conc*.01})
    rows.append({"sample_id": "known-test", "role": "test", "conc": 2.5,
                 "A_R": .075, "A_R_srgb": .1, "A_R_raw": .075,
                 "A_G": .05, "A_B": .025, "hue": 197.5,
                 "r": .875, "g": .775, "b": .675})
    rows.append({"sample_id": "unknown", "role": "unknown", "conc": np.nan,
                 "A_R": .12, "A_R_srgb": .16, "A_R_raw": .12,
                 "A_G": .08, "A_B": .04, "hue": 196,
                 "r": .86, "g": .76, "b": .66})
    results = module.evaluate(pd.DataFrame(rows), {"known-test": 2.5, "unknown": np.nan})
    assert all(value["n"] == 1 for value in results.values())


def test_compare_methods_requires_labelled_test_samples():
    frame = pd.DataFrame([{"sample_id":"s1","role":"standard","conc":1,
                           "A_R":.1,"A_R_srgb":.1,"A_R_raw":.1,"A_G":.1,"A_B":.1,
                           "hue":100,"r":.5,"g":.5,"b":.5}])
    with pytest.raises(ValueError, match="labelled role='test'"):
        module.evaluate(frame, {})
