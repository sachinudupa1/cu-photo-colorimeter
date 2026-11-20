# Experimental data roles

The web application stores **one Firestore document per independently prepared solution** in `training_data`. Several photographs of that same flask are stored as photo replicates under the one document.

| Role | Known concentration? | Used for |
|---|---:|---|
| `blank` | No | Session reference (NH₃ + water, no copper); one or more per session |
| `standard` | Yes | Fit the concentration calibration; must be verified |
| `validation` | Yes | Compare candidate feature/calibration choices; never used to fit them |
| `resolution` | Yes | MDD/resolution study; independent prepared solutions at repeated concentration levels |

Public unknown samples and their predictions go into the separate `testing_data` collection. Their reference concentration can be appended later by a teammate after the initial prediction has been recorded.

## Required experimental discipline

- Every session needs its own blank photos.
- Every blank must have the same ammonia volume and the same final flask volume as other solutions.
- Use one unique `sample_id` per prepared flask. Add multiple photographs of that flask in the same record; do not create a second record to represent another photograph of the same solution.
- Keep the same concentration unit throughout the calibration.
- At least four **distinct verified standard concentrations** are required to fit a model.
- Keep separate `validation` concentrations out of the fitting process.
- To estimate the minimum distinguishable difference, prepare at least three independent flasks at each tested concentration. Five photographs of one flask measure camera repeatability, not preparation-to-preparation variation.
- Do not label an unknown as known until the prediction has been saved and the reference is measured independently.
- Do not edit or crop photos by hand. The processing pipeline applies the configured ROI.

The camera does not automatically know the real concentration. The value entered for a standard must be based on the preparation record and checked by the team. The colorimeter absorbance is stored as an independent reference measurement.
