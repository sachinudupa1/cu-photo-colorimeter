"""Compare seven ways of converting photos into concentration estimates.

Only labelled held-out `test` samples are scored. Unlabelled `unknown` samples
are prediction-only data and are deliberately excluded from error metrics.
"""
import argparse
import tempfile
from pathlib import Path

import _paths
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as sstats
from sklearn.ensemble import RandomForestRegressor

from cucolor.calibration import metrics
from cucolor.pipeline import measure_manifest
from cucolor.synth import make_dataset

METHODS = [
    ("Red, blank-referenced (ours)", "A_R"),
    ("Red, no gamma correction", "A_R_srgb"),
    ("Red, no blank photo", "A_R_raw"),
    ("Green channel", "A_G"),
    ("Blue channel", "A_B"),
    ("HSV hue", "hue"),
    ("Random forest on RGB", None),
]


def evaluate(feat, truth):
    """Fit on verified standards and score only labelled held-out test samples."""
    train = feat[feat.role == "standard"].copy()
    held = feat[(feat.role == "test") & feat.conc.notna()].copy()
    if train.empty:
        raise ValueError("No standard samples found.")
    if held.empty:
        raise ValueError("No labelled role='test' samples found; unknown samples cannot be scored.")
    y_true = held.sample_id.map(truth).astype(float).to_numpy()
    if not np.isfinite(y_true).all():
        raise ValueError("Every held-out test sample must have a known concentration in the manifest.")
    out = {}
    for label, col in METHODS:
        if col is None:
            rf = RandomForestRegressor(n_estimators=200, random_state=0)
            rf.fit(train[["r", "g", "b"]], train.conc.astype(float))
            pred = rf.predict(held[["r", "g", "b"]])
        else:
            fit = sstats.linregress(train[col].astype(float), train.conc.astype(float))
            pred = fit.slope * held[col].astype(float) + fit.intercept
        out[label] = metrics(y_true, pred)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest")
    p.add_argument("--photos")
    p.add_argument("--label", default="your photos")
    p.add_argument("--results", default="results")
    a = p.parse_args()
    Path(a.results).mkdir(parents=True, exist_ok=True)

    runs = {}
    if a.manifest:
        if not a.photos:
            p.error("--photos is required when --manifest is supplied")
        feat = measure_manifest(a.manifest, a.photos)
        man = pd.read_csv(a.manifest).drop_duplicates("sample_id")
        truth = dict(zip(man.sample_id, man.conc))
        runs[a.label] = evaluate(feat, truth)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for scen in ("box", "room"):
                per_seed = []
                for seed in range(4):
                    d = Path(tmp) / f"{scen}{seed}"
                    df = make_dataset(d, scenario=scen, seed=seed)
                    feat = measure_manifest(d / "manifest.csv", d / "photos")
                    truth = dict(zip(df.sample_id, df.conc))
                    per_seed.append(evaluate(feat, truth))
                runs[scen] = {
                    method: {key: float(np.nanmean([r[method][key] for r in per_seed]))
                             for key in per_seed[0][method]}
                    for method, _ in METHODS
                }

    rows = [{"method": method, "setting": setting, **values}
            for setting, result in runs.items() for method, values in result.items()]
    table = pd.DataFrame(rows)
    table.to_csv(f"{a.results}/method_comparison.csv", index=False)
    show = table.pivot(index="method", columns="setting", values="mape_pct").loc[[m for m, _ in METHODS]]
    print("Mean absolute percentage error on labelled held-out test solutions (lower is better)")
    print(show.round(2).to_string())

    from _paths import BLUE, INK, MUTED, ORANGE, style_axes
    nice = {"box": "Dark box (fixed light)", "room": "Room light (auto-exposure)"}
    settings = [s for s in ("box", "room") if s in show.columns] or list(show.columns)
    colours = {settings[0]: BLUE, **({settings[1]: ORANGE} if len(settings) > 1 else {})}
    fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=150)
    ypos = np.arange(len(show))[::-1]
    h = 0.34 if len(settings) > 1 else 0.5
    for i, setting in enumerate(settings):
        off = ((len(settings) - 1) / 2 - i) * h
        vals = show[setting].to_numpy()
        ax.barh(ypos + off, vals, height=h * 0.85, color=colours[setting], label=nice.get(setting, setting))
        for y, value in zip(ypos + off, vals):
            ax.text(value + 0.3, y, f"{value:.1f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(ypos)
    ax.set_yticklabels(show.index, color=INK, fontsize=9)
    ax.set_xlabel("Mean absolute percentage error on held-out solutions (%)")
    ax.set_title("How the photo is read changes the error", fontsize=10, loc="left", color=INK)
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower right")
    style_axes(ax)
    ax.grid(False, axis="y")
    fig.tight_layout()
    fig.savefig(f"{a.results}/method_comparison.png")
    print(f"\nSaved {a.results}/method_comparison.csv and .png")


if __name__ == "__main__":
    main()
