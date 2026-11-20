# Experimental data collection protocol

This is a software/data-recording guide, not a substitute for the chemistry lab's approved procedure or teacher supervision. Follow the lab manual and the instructor's directions for chemical preparation and handling. Concentrated ammonia is hazardous; use it only under the lab's approved ventilation and PPE rules.

## Record design

Each document in `training_data` represents **one independently prepared flask**. Multiple images of the same flask are technical photo replicates attached to that one record. Do not enter each photo as a separate independently prepared solution.

Use the same `session_id` for all samples photographed under the same phone, box, light, blank and setup. Start a new session if the setup changes, the phone changes, the box/light moves, or a fresh blank is taken after a material setup change.

## Roles in the private Data Collection tab

| Role | What to record | Model use |
|---|---|---|
| `blank` | Same ammonia/water matrix without copper; one or more blank photos | Reference for samples in that session; mark verified after checking it |
| `standard` | Known prepared concentration, matching colorimeter absorbance, sample photos | Fits the calibration model |
| `validation` | Known concentration and colorimeter absorbance, kept out of model fitting | Selects among candidate feature methods; do not use these as a final blind test if they selected the model |
| `resolution` | Independently prepared replicate solutions at deliberately close concentration levels | Estimates the smallest tested adjacent gap distinguished by the camera signal |

Use at least four distinct verified `standard` concentrations before attempting candidate training. Aim for standards spanning the working linear range established by the laboratory colorimeter. A practical first data set may include roughly 8–12 distinct standards, with separate validation levels. That is a planning target, not a scientific rule; follow the available equipment and actual absorbance range.

## Photographing consistently

1. Ask the teacher whether phone photography is permitted.
2. Use one fixed phone for the first validated dataset where possible. Record its make/model.
3. Use the same dark box, tube/cuvette, position, white LED, matte background and sample fill height.
4. Keep flash off. Avoid zoom. Keep the phone and sample at marked positions.
5. Capture the session blank first, then capture every sample without moving the setup.
6. Where the phone permits it, lock focus/exposure/white balance using the phone camera controls. The web page's photo picker cannot force these settings on every phone.
7. Take several photos of each prepared flask, but remember that these are technical replicates, not separate preparations.
8. Use unique sample IDs. Keep units and session IDs consistent.

The browser input requests the rear camera on supported phones, but the browser may open the device's native camera/photo picker. Some devices may present the gallery instead. Test this on the actual phone before evaluation.

## Minimum distinguishable difference study

Use the `resolution` role for this study. Choose several nearby concentration levels in the validated colorimeter range. Prepare at least three independent flasks at each concentration level (more replicates are preferable when time and chemicals allow). Photograph each prepared flask in the same session and enter its prepared concentration. Do not treat three photos of a single flask as three independent preparations.

The software compares the mean camera feature of each prepared flask across adjacent tested concentration levels using Welch's two-sample t-test and Holm correction. The reported value is the smallest tested adjacent concentration gap that passes the chosen statistical screen. It is not a universal camera resolution or guaranteed quantification capability. Report the replicate counts and the phone, box, light, solution and preparation conditions alongside it.

## Blind test and feedback cycle

1. Make a live prediction in the public presentation website without entering the true concentration first.
2. The API saves the prediction, model version, warning status, blank/sample photos and timestamp in `testing_data`.
3. Only after the prediction is saved, the team enters the independently known concentration and the corresponding laboratory colorimeter absorbance in the private Model Laboratory tab.
4. The private dashboard calculates error metrics by model version for labelled `OK`/`CHECK` tests that have not been promoted to training.
5. If a result is suitable for future training, a teammate explicitly verifies it and promotes it with a deliberate role (`standard`, `validation` or `resolution`). Promotion is never automatic.
6. Retrain a candidate, inspect validation metrics and MDD, and manually approve it. Keep a separate final blind test set untouched for reporting.

Never claim an accuracy value, MDD, LOD or LOQ from synthetic photos. Only verified laboratory data can support experimental results.
