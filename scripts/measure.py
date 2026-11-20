"""Measure an unknown solution from photos (the 'teacher mode' tool).

    python scripts/measure.py --model models/calibration.json \\
        --blank today/blank1.jpg today/blank2.jpg today/blank3.jpg \\
        --photos today/stu07_1.jpg today/stu07_2.jpg today/stu07_3.jpg \\
        --sample-id STU07 --log results/log.csv

Every run is appended to the log, so you can check each student's result later
without remembering what quantity each one was given.
"""
import argparse

import _paths  # noqa: F401
from cucolor.agent import ColorimetryAgent
from cucolor.calibration import Calibration

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--model", default="models/calibration.json")
p.add_argument("--blank", nargs="+", required=True, help="blank photos from today")
p.add_argument("--photos", nargs="+", required=True, help="photos of the solution")
p.add_argument("--sample-id", default="sample")
p.add_argument("--log", default=None, help="CSV file to append the result to")
p.add_argument("--trace", action="store_true", help="show what each agent step did")
a = p.parse_args()

agent = ColorimetryAgent(Calibration.load(a.model), log_path=a.log)
rep = agent.run(a.blank, a.photos, sample_id=a.sample_id)
if a.trace:
    for step, outcome in rep.trace:
        print(f"[{step}] {outcome}")
    print()
print(rep.text())
