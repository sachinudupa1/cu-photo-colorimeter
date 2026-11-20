"""Make fake photos so you can test the code without a lab.

    python scripts/make_synthetic_data.py --out data/synthetic --scenario box

These are NOT experimental results. Never present them as such.
"""
import argparse

import _paths  # noqa: F401
from cucolor.synth import make_dataset

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--out", default="data/synthetic")
p.add_argument("--scenario", choices=["box", "room"], default="box")
p.add_argument("--seed", type=int, default=0)
a = p.parse_args()

df = make_dataset(a.out, scenario=a.scenario, seed=a.seed)
print(f"Wrote {len(df)} photos and {a.out}/manifest.csv  (scenario: {a.scenario})")
