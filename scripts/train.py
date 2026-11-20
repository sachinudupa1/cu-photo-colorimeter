"""Build the calibration from standards, then test it on solutions it has not seen.

    python scripts/train.py --manifest data/synthetic/manifest.csv --photos data/synthetic/photos

Outputs
    models/calibration.json       used by measure.py
    results/predictions.csv       every test/unknown solution: true vs predicted
    results/calibration.png       calibration line + held-out check
"""
import argparse
from pathlib import Path

import _paths
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from cucolor.calibration import fit_calibration, metrics
from cucolor.features import DEFAULT_ROI
from cucolor.pipeline import measure_manifest

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--manifest", required=True)
p.add_argument("--photos", required=True, help="folder with the photos")
p.add_argument("--model-out", default="models/calibration.json")
p.add_argument("--results", default="results")
p.add_argument("--unit", default="mL stock")
p.add_argument("--roi", type=float, nargs=4, default=list(DEFAULT_ROI),
               metavar=("X0", "Y0", "X1", "Y1"), help="region of the photo to use, as fractions")
a = p.parse_args()

feat = measure_manifest(a.manifest, a.photos, tuple(a.roi))
std = feat[feat.role == "standard"]
cal_session = std.session.iloc[0]
cal = fit_calibration(
    std.conc, std.A_R, channel="R", linearize=True, roi=tuple(a.roi), unit=a.unit,
    blank_level=float(std.blank_level_R.mean()),
)
cal.save(a.model_out)

print(f"Calibration from {cal.n} standards (session '{cal_session}')")
print(f"  A = {cal.slope:.4f} x conc + {cal.intercept:.4f}     R2 = {cal.r2:.4f}")
print(f"  detection limit {cal.lod:.2f} {a.unit}, quantification limit {cal.loq:.2f} {a.unit}")
print(f"  trusted range: {cal.conc_min:g} to {cal.conc_max:g} {a.unit}")
if cal.curvature_gain > 0.3:
    print(f"  WARNING: the points curve (a quadratic fits {cal.curvature_gain:.0%} better). "
          "Narrow the range, drop the darkest standards, or check lighting.")

# camera absorbance vs the real colorimeter, if the manifest has it
if "colorimeter_abs" in std and std.colorimeter_abs.notna().sum() >= 3:
    r = np.corrcoef(std.A_R, std.colorimeter_abs.astype(float))[0, 1]
    print(f"  camera vs colorimeter absorbance: r = {r:.4f}")

# hold-out check
Path(a.results).mkdir(parents=True, exist_ok=True)
# Unknown samples have no ground-truth concentration. Score only labelled test rows.
held = feat[(feat.role == "test") & feat.conc.notna()].copy()
if len(held):
    held["pred"] = [cal.predict(x) for x in held.A_R]
    held["abs_err"] = (held.pred - held.conc).abs()
    held["pct_err"] = held.abs_err / held.conc * 100
    cols = ["sample_id", "role", "conc", "pred", "abs_err", "pct_err", "A_R"]
    if "colorimeter_abs" in held:
        cols.append("colorimeter_abs")
    held[cols].to_csv(f"{a.results}/predictions.csv", index=False)
    m = metrics(held.conc, held.pred)
    print(f"\nHeld-out solutions ({m['n']}): mean abs error {m['mae']:.2f} {a.unit}, "
          f"mean % error {m['mape_pct']:.1f}%, worst {m['max_abs_err']:.2f}, R2 {m['r2']:.4f}")
    print(held[["sample_id", "conc", "pred", "pct_err"]].round(2).to_string(index=False))

# plot
from _paths import BLUE, INK, MUTED, ORANGE, style_axes  # noqa: E402

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=150)
xs = np.linspace(0, cal.conc_max * 1.05, 50)
ax1.plot(xs, cal.slope * xs + cal.intercept, color=MUTED, lw=1.5, label="Fitted line")
ax1.scatter(std.conc, std.A_R, s=36, color=BLUE, edgecolor="white", linewidth=1.5,
            zorder=3, label="Standards")
if len(held):
    ax1.scatter(held.conc, held.A_R, s=36, color=ORANGE, edgecolor="white", linewidth=1.5,
                zorder=3, label="Held-out solutions")
ax1.axvspan(0, cal.lod, color=MUTED, alpha=0.15, lw=0)
ax1.set_xlabel(f"Concentration ({a.unit})")
ax1.set_ylabel("Camera absorbance (red channel)")
ax1.set_title(f"Calibration  (R² = {cal.r2:.3f}, shaded = below detection limit)", fontsize=10)
ax1.legend(frameon=False, labelcolor=INK, fontsize=9)
style_axes(ax1)

if len(held):
    lim = [0, max(held.conc.max(), held.pred.max()) * 1.08]
    ax2.plot(lim, lim, color=MUTED, lw=1.5, label="Perfect agreement")
    ax2.scatter(held.conc, held.pred, s=36, color=ORANGE, edgecolor="white",
                linewidth=1.5, zorder=3, label="Held-out solutions")
    ax2.set_xlim(lim)
    ax2.set_ylim(lim)
    ax2.set_xlabel(f"True concentration ({a.unit})")
    ax2.set_ylabel(f"Predicted ({a.unit})")
    ax2.set_title(f"Held-out check  (mean error {m['mape_pct']:.1f}%)", fontsize=10)
    ax2.legend(frameon=False, labelcolor=INK, fontsize=9)
    style_axes(ax2)
else:
    ax2.axis("off")
fig.tight_layout()
fig.savefig(f"{a.results}/calibration.png")
print(f"\nSaved {a.model_out}, {a.results}/calibration.png, {a.results}/predictions.csv")
