import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import ROOT, shoot
from cucolor.agent import ColorimetryAgent
from cucolor.calibration import metrics
from cucolor.pipeline import measure_manifest


@pytest.fixture()
def agent(calibration, tmp_path):
    return ColorimetryAgent(calibration, log_path=tmp_path / "log.csv")


def blanks(tmp_path, gain=1.0):
    return shoot(tmp_path, "blank", 0.0, seed=1, gain=gain, n=3)


def test_holdout_error_is_small(box_data, calibration):
    """The core promise: solutions the model never saw, on a different 'day'."""
    d, df = box_data
    feat = measure_manifest(d / "manifest.csv", d / "photos")
    held = feat[feat.role.isin(["test", "unknown"])]
    truth = dict(zip(df.sample_id, df.true_conc))
    pred = [calibration.predict(a) for a in held.A_R]
    m = metrics([truth[s] for s in held.sample_id], pred)
    assert m["mape_pct"] < 3.0
    assert m["r2"] > 0.995


@pytest.mark.parametrize("true", [6.0, 14.0, 23.0])
def test_agent_measures_unknowns(agent, tmp_path, true):
    rep = agent.run(blanks(tmp_path), shoot(tmp_path, "unk", true, seed=2), "S1")
    assert rep.status in ("OK", "CHECK")
    assert rep.conc == pytest.approx(true, rel=0.05)
    assert rep.ci_low < rep.conc < rep.ci_high
    assert [s for s, _ in rep.trace] == [
        "check_files", "check_quality", "measure", "predict", "check_range", "report"]


def test_too_concentrated_is_refused(agent, tmp_path):
    rep = agent.run(blanks(tmp_path), shoot(tmp_path, "hi", 40.0, seed=3), "S2")
    assert rep.status == "OUT_OF_RANGE"
    assert "Dilute" in rep.text()
    assert "Concentration:" not in rep.text()          # no number is presented as a result


def test_too_faint_is_below_lod(agent, tmp_path):
    rep = agent.run(blanks(tmp_path), shoot(tmp_path, "zero", 0.0, seed=4), "S3")
    assert rep.status == "BELOW_LOD"
    assert "Concentration:" not in rep.text()


def test_overexposed_blank_means_retake(agent, tmp_path):
    white = tmp_path / "white.png"
    Image.fromarray(np.full((80, 60, 3), 255, np.uint8)).save(white)
    rep = agent.run([white], shoot(tmp_path, "s", 10.0), "S4")
    assert rep.status == "RETAKE"
    assert rep.conc is None


def test_glare_in_sample_means_retake(agent, tmp_path):
    photos = shoot(tmp_path, "g", 10.0, seed=5, n=1)
    arr = np.asarray(Image.open(photos[0]).convert("RGB")).copy()
    h, w = arr.shape[:2]
    arr[int(0.35 * h): int(0.55 * h), int(0.44 * w): int(0.56 * w)] = 255   # blown-out patch
    Image.fromarray(arr).save(photos[0])
    rep = agent.run(blanks(tmp_path), photos, "S5")
    assert rep.status == "RETAKE"
    assert any("blown-out" in w or "uneven" in w for w in rep.warnings)


def test_missing_file_is_an_error_not_a_crash(agent, tmp_path):
    rep = agent.run([tmp_path / "nope.jpg"], [tmp_path / "nope2.jpg"], "S6")
    assert rep.status == "ERROR"


def test_lighting_drift_is_warned(agent, tmp_path):
    rep = agent.run(blanks(tmp_path, gain=0.6), shoot(tmp_path, "d", 12.0, gain=0.6, seed=6), "S7")
    assert any("Blank is" in w for w in rep.warnings)
    assert rep.status == "CHECK"
    assert rep.conc == pytest.approx(12.0, rel=0.05)    # blank-referencing still copes


def test_log_has_one_row_per_run(agent, tmp_path):
    agent.run(blanks(tmp_path), shoot(tmp_path, "a", 8.0, seed=7), "STU01")
    agent.run(blanks(tmp_path), shoot(tmp_path, "b", 40.0, seed=8), "STU02")
    rows = list(csv.DictReader(open(tmp_path / "log.csv")))
    assert [r["sample_id"] for r in rows] == ["STU01", "STU02"]
    assert rows[0]["conc"] != "" and rows[1]["conc"] == ""    # refused result has no number


def test_scripts_run_end_to_end(box_data, tmp_path):
    """train.py then measure.py, exactly as a student would run them."""
    d, _ = box_data
    py = sys.executable
    model = tmp_path / "m.json"
    out = subprocess.run(
        [py, str(ROOT / "scripts/train.py"), "--manifest", str(d / "manifest.csv"),
         "--photos", str(d / "photos"), "--model-out", str(model), "--results", str(tmp_path / "res")],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert (tmp_path / "res/calibration.png").exists()
    ph = sorted((d / "photos").glob("day2_unk13.0_*.jpg"))
    bl = sorted((d / "photos").glob("day2_blank_*.jpg"))
    out = subprocess.run(
        [py, str(ROOT / "scripts/measure.py"), "--model", str(model), "--blank", *map(str, bl),
         "--photos", *map(str, ph), "--sample-id", "STU99", "--log", str(tmp_path / "log.csv")],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "Status: OK" in out.stdout
    conc = float(out.stdout.split("Concentration:")[1].split()[0])
    assert conc == pytest.approx(13.0, rel=0.05)
