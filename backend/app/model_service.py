from __future__ import annotations

import json
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cucolor.calibration import Calibration, metrics, fit_calibration
from cucolor.features import DEFAULT_ROI, absorbance, photo_stats

from . import settings
from .firebase_service import firestore_client
from .storage_service import storage_bucket

TRAINING_COLLECTION = "training_data"
TESTING_COLLECTION = "testing_data"


def _download_photo(blob_path: str, folder: Path, index: int) -> Path:
    bucket = storage_bucket()
    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError(f"Stored photo is missing: {blob_path}")
    destination = folder / f"photo_{index}{Path(blob_path).suffix or '.jpg'}"
    destination.write_bytes(blob.download_as_bytes())
    return destination


def _read_training_records() -> list[dict]:
    db = firestore_client()
    docs = db.collection(TRAINING_COLLECTION).stream()
    records = []
    for doc in docs:
        item = doc.to_dict() or {}
        item["record_id"] = doc.id
        records.append(item)
    return records


def _feature_rows(records: list[dict], temp_dir: Path) -> list[dict]:
    """Create one feature row per independently prepared solution."""
    by_session: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_session[str(rec.get("session_id", ""))].append(rec)

    output: list[dict] = []
    file_index = 0
    for session_id, session_records in by_session.items():
        blank_records = [r for r in session_records if r.get("role") == "blank" and r.get("verified") is True]
        blank_paths: list[Path] = []
        for rec in blank_records:
            for photo in rec.get("photos", []):
                file_index += 1
                blank_paths.append(_download_photo(photo["storage_path"], temp_dir, file_index))
        if not blank_paths:
            continue
        blanks = [photo_stats(p, DEFAULT_ROI) for p in blank_paths]
        blank_level = float(np.mean([b.value("R", True) for b in blanks]))

        for rec in session_records:
            role = rec.get("role")
            if role not in {"standard", "validation", "resolution"} or rec.get("verified") is not True:
                continue
            if rec.get("concentration") is None:
                continue
            sample_paths = []
            for photo in rec.get("photos", []):
                file_index += 1
                sample_paths.append(_download_photo(photo["storage_path"], temp_dir, file_index))
            if not sample_paths:
                continue
            samples = [photo_stats(p, DEFAULT_ROI) for p in sample_paths]
            a_r, a_sd, _ = absorbance(samples, blanks, "R", True)
            a_g, _, _ = absorbance(samples, blanks, "G", True)
            a_b, _, _ = absorbance(samples, blanks, "B", True)
            a_r_srgb, _, _ = absorbance(samples, blanks, "R", False)
            a_g_srgb, _, _ = absorbance(samples, blanks, "G", False)
            a_b_srgb, _, _ = absorbance(samples, blanks, "B", False)
            from cucolor.features import hue_degrees
            rgb = np.mean([p.srgb_mean for p in samples], axis=0)
            output.append({
                "record_id": rec["record_id"],
                "sample_id": rec.get("sample_id", rec["record_id"]),
                "session_id": session_id,
                "role": role,
                "concentration": float(rec["concentration"]),
                "concentration_unit": rec.get("concentration_unit", "unit"),
                "camera_absorbance": float(a_r),
                "camera_absorbance_sd": float(a_sd),
                "A_R": float(a_r), "A_G": float(a_g), "A_B": float(a_b),
                "A_R_srgb": float(a_r_srgb), "A_G_srgb": float(a_g_srgb), "A_B_srgb": float(a_b_srgb),
                "hue": float(np.mean([hue_degrees(p) for p in samples])),
                "colorimeter_absorbance": rec.get("colorimeter_absorbance"),
                "n_photos": len(samples),
                "red": float(rgb[0]), "green": float(rgb[1]), "blue": float(rgb[2]),
                "blank_level": blank_level,
            })
    return output


def _json_safe(value):
    """Convert numpy scalars and non-finite floats to strict JSON values."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    return value


def _save_json_to_storage(path: str, data: dict) -> None:
    blob = storage_bucket().blob(path)
    blob.upload_from_string(
        json.dumps(_json_safe(data), indent=2, allow_nan=False),
        content_type="application/json",
    )


METHODS = [
    {"name": "Red channel · linear-light · blank referenced", "feature": "A_R", "channel": "R", "linearize": True},
    {"name": "Red channel · sRGB · blank referenced", "feature": "A_R_srgb", "channel": "R", "linearize": False},
    {"name": "Green channel · linear-light · blank referenced", "feature": "A_G", "channel": "G", "linearize": True},
    {"name": "Green channel · sRGB · blank referenced", "feature": "A_G_srgb", "channel": "G", "linearize": False},
    {"name": "Blue channel · linear-light · blank referenced", "feature": "A_B", "channel": "B", "linearize": True},
    {"name": "Blue channel · sRGB · blank referenced", "feature": "A_B_srgb", "channel": "B", "linearize": False},
]


def select_calibration_method(standards: list[dict], validation: list[dict], unit: str, blank_level: float):
    """Fit several simple calibration choices and select by held-out validation MAE.

    Selection is performed only when validation contains at least three distinct
    prepared concentrations. Otherwise the established red/linear method is kept
    as the baseline and no claim of automatic method selection is made.
    """
    candidates = []
    comparison = []
    validation_levels = {r["concentration"] for r in validation}
    can_select = len(validation) >= 3 and len(validation_levels) >= 3
    methods = METHODS if can_select else METHODS[:1]
    for method in methods:
        try:
            calibration = fit_calibration(
                [r["concentration"] for r in standards],
                [r[method["feature"]] for r in standards],
                channel=method["channel"], linearize=method["linearize"],
                roi=DEFAULT_ROI, unit=unit, blank_level=blank_level,
            )
            score = None
            if validation:
                predicted = [calibration.predict(r[method["feature"]]) for r in validation]
                score = metrics([r["concentration"] for r in validation], predicted)
            comparison.append({
                "method": method["name"], "feature": method["feature"],
                "mae": score["mae"] if score else None,
                "rmse": score["rmse"] if score else None,
                "mape_pct": score["mape_pct"] if score else None,
                "selected": False,
            })
            candidates.append((calibration, method, score))
        except (ValueError, FloatingPointError):
            comparison.append({"method": method["name"], "feature": method["feature"], "mae": None,
                               "rmse": None, "mape_pct": None, "selected": False,
                               "rejected": "Calibration could not be fitted with a positive slope."})
    if not candidates:
        raise ValueError("No channel produced a valid positive-slope calibration. Check photos, blank and ROI.")
    if can_select:
        chosen = min(candidates, key=lambda item: (item[2]["mae"], item[2]["rmse"]))
        selection_status = "selected_by_validation_mae"
    else:
        chosen = candidates[0]
        selection_status = "baseline_only_insufficient_validation"
    calibration, method, score = chosen
    for row in comparison:
        row["selected"] = row["feature"] == method["feature"]
    return calibration, method, score, comparison, selection_status


def build_candidate_model() -> dict:
    records = _read_training_records()
    if not records:
        raise ValueError("No training records exist yet.")
    with tempfile.TemporaryDirectory(prefix="cu-photo-train-") as tmp:
        rows = _feature_rows(records, Path(tmp))
    standards = [r for r in rows if r["role"] == "standard"]
    distinct = sorted({r["concentration"] for r in standards})
    if len(distinct) < 4:
        raise ValueError(f"At least 4 distinct verified standard concentrations are required; found {len(distinct)}.")
    units = {r["concentration_unit"] for r in standards}
    if len(units) != 1:
        raise ValueError("All calibration standards must use the same concentration unit.")

    unit = next(iter(units))
    validation = [r for r in rows if r["role"] == "validation"]
    calibration, selected_method, validation_metrics, method_comparison, selection_status = select_calibration_method(
        standards, validation, unit,
        blank_level=float(np.mean([r["blank_level"] for r in standards])),
    )

    # Compare the camera's absorbance with the laboratory colorimeter reference.
    # This is a diagnostic comparison, not the target used to fit concentration.
    paired = [r for r in standards if r.get("colorimeter_absorbance") is not None]
    camera_colorimeter_comparison = None
    if len(paired) >= 3:
        from scipy import stats as scipy_stats
        camera_values = np.asarray([r[selected_method["feature"]] for r in paired], dtype=float)
        colorimeter_values = np.asarray([float(r["colorimeter_absorbance"]) for r in paired], dtype=float)
        regression = scipy_stats.linregress(camera_values, colorimeter_values)
        fitted = regression.slope * camera_values + regression.intercept
        camera_colorimeter_comparison = {
            "n": len(paired),
            "pearson_r": float(regression.rvalue),
            "slope": float(regression.slope),
            "intercept": float(regression.intercept),
            "rmse_absorbance": float(np.sqrt(np.mean((colorimeter_values - fitted) ** 2))),
            "note": "Descriptive camera-vs-colorimeter absorbance comparison on paired standards; not a concentration accuracy claim.",
        }

    resolution_rows = [r for r in rows if r["role"] == "resolution"]
    mdd = None
    if resolution_rows:
        from .resolution import resolution_summary
        mdd = resolution_summary(resolution_rows, signal_key=selected_method["feature"])

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    model_path = f"{settings.MODEL_STORAGE_PREFIX}/candidates/{version}/calibration.json"
    metadata_path = f"{settings.MODEL_STORAGE_PREFIX}/candidates/{version}/metadata.json"
    with tempfile.TemporaryDirectory(prefix="cu-photo-model-") as tmp:
        model_file = Path(tmp) / "calibration.json"
        calibration.save(model_file)
        storage_bucket().blob(model_path).upload_from_filename(
            str(model_file), content_type="application/json"
        )
    metadata = {
        "version": version,
        "model_path": model_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "standards_count": len(standards),
        "distinct_standard_concentrations": distinct,
        "unit": unit,
        "calibration_r2": calibration.r2,
        "slope": calibration.slope,
        "intercept": calibration.intercept,
        "lod": calibration.lod,
        "loq": calibration.loq,
        "range_min": calibration.conc_min,
        "range_max": calibration.conc_max,
        "curvature_gain": calibration.curvature_gain,
        "selected_method": selected_method["name"],
        "selected_feature": selected_method["feature"],
        "selection_status": selection_status,
        "method_comparison": method_comparison,
        "camera_colorimeter_comparison": camera_colorimeter_comparison,
        "validation_metrics": validation_metrics,
        "validation_count": len(validation),
        "validation_unique_concentrations": len({r["concentration"] for r in validation}),
        "mdd": mdd,
        "approval_status": "candidate",
        "warning": "Candidate model; not approved for public predictions until a team member approves it.",
    }
    _save_json_to_storage(metadata_path, metadata)
    return metadata


def approve_candidate(version: str, approve_as_provisional: bool = False) -> dict:
    bucket = storage_bucket()
    base = f"{settings.MODEL_STORAGE_PREFIX}/candidates/{version}"
    metadata_blob = bucket.blob(f"{base}/metadata.json")
    if not metadata_blob.exists():
        raise FileNotFoundError("Candidate model version was not found.")
    metadata = json.loads(metadata_blob.download_as_text())
    if metadata.get("approval_status") != "candidate":
        raise ValueError("This model is not a pending candidate.")
    if metadata.get("validation_unique_concentrations", 0) < 3 and not approve_as_provisional:
        raise ValueError("At least 3 distinct labelled validation concentrations are required. Explicitly approve as provisional only if this is a demonstration model.")
    if metadata.get("standards_count", 0) < 4 or metadata.get("slope", 0) <= 0:
        raise ValueError("Model failed the basic calibration checks.")

    metadata["approval_status"] = "approved_provisional" if approve_as_provisional and metadata.get("validation_unique_concentrations", 0) < 3 else "approved"
    metadata["approved_at"] = datetime.now(timezone.utc).isoformat()
    _save_json_to_storage(f"{base}/metadata.json", metadata)
    pointer = {
        "version": version,
        "model_path": metadata["model_path"],
        "metadata_path": f"{base}/metadata.json",
        "approval_status": metadata["approval_status"],
        "approved_at": metadata["approved_at"],
    }
    _save_json_to_storage(f"{settings.MODEL_STORAGE_PREFIX}/active.json", pointer)
    return pointer


def load_active_model() -> tuple[Calibration, dict]:
    bucket = storage_bucket()
    pointer_blob = bucket.blob(f"{settings.MODEL_STORAGE_PREFIX}/active.json")
    if not pointer_blob.exists():
        raise FileNotFoundError("No approved model is active yet. Train and approve a model in the private laboratory first.")
    pointer = json.loads(pointer_blob.download_as_text())
    model_blob = bucket.blob(pointer["model_path"])
    if not model_blob.exists():
        raise FileNotFoundError("The active model file is missing from Firebase Storage.")
    model_json = json.loads(model_blob.download_as_text())
    model_json["roi"] = tuple(model_json["roi"])
    calibration = Calibration(**model_json)
    metadata_blob = bucket.blob(pointer["metadata_path"])
    metadata = json.loads(metadata_blob.download_as_text()) if metadata_blob.exists() else pointer
    return calibration, metadata


def create_training_record(metadata: dict, uploaded_photos: list[tuple[str, bytes, str]]) -> str:
    db = firestore_client()
    bucket = storage_bucket()
    record_id = uuid.uuid4().hex
    duplicate = list(db.collection(TRAINING_COLLECTION).where("sample_id", "==", metadata.get("sample_id")).limit(1).stream())
    if duplicate:
        raise ValueError(f"Sample ID '{metadata.get('sample_id')}' already exists. Add further photos to the original flask record instead of creating a duplicate prepared-solution record.")
    photo_refs = []
    try:
        for name, content, content_type in uploaded_photos:
            safe_name = Path(name).name.replace(" ", "_")[:100]
            path = f"training/{record_id}/{uuid.uuid4().hex}_{safe_name}"
            blob = bucket.blob(path)
            blob.upload_from_string(content, content_type=content_type)
            photo_refs.append({"storage_path": path, "filename": safe_name, "content_type": content_type, "size_bytes": len(content)})
        doc = {
            **metadata,
            "record_id": record_id,
            "photos": photo_refs,
            "created_at": datetime.now(timezone.utc),
        }
        db.collection(TRAINING_COLLECTION).document(record_id).set(doc)
    except Exception:
        for photo in photo_refs:
            try:
                bucket.blob(photo["storage_path"]).delete()
            except Exception:
                pass
        raise
    return record_id


def list_training_records(limit: int = 100) -> list[dict]:
    db = firestore_client()
    result = []
    for doc in db.collection(TRAINING_COLLECTION).order_by("created_at", direction="DESCENDING").limit(limit).stream():
        row = doc.to_dict() or {}
        row["record_id"] = doc.id
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        # Do not expose private Storage download URLs; paths remain server-side metadata.
        result.append(row)
    return result


def verify_training_record(record_id: str, verified: bool) -> None:
    doc = firestore_client().collection(TRAINING_COLLECTION).document(record_id)
    if not doc.get().exists:
        raise FileNotFoundError("Training record not found.")
    doc.update({"verified": bool(verified), "verified_at": datetime.now(timezone.utc) if verified else None})


def create_test_record(payload: dict, blank_files: list[tuple[str, bytes, str]], sample_files: list[tuple[str, bytes, str]], report: dict, model_meta: dict) -> str:
    db = firestore_client()
    bucket = storage_bucket()
    test_id = uuid.uuid4().hex

    def store_group(files: list[tuple[str, bytes, str]], group: str) -> list[dict]:
        refs = []
        for name, content, content_type in files:
            safe_name = Path(name).name.replace(" ", "_")[:100]
            path = f"testing/{test_id}/{group}/{uuid.uuid4().hex}_{safe_name}"
            bucket.blob(path).upload_from_string(content, content_type=content_type)
            refs.append({"storage_path": path, "filename": safe_name, "content_type": content_type, "size_bytes": len(content)})
        return refs

    blank_refs = store_group(blank_files, "blank")
    sample_refs = store_group(sample_files, "sample")
    doc = {
        "test_id": test_id,
        "sample_id": payload.get("sample_id") or f"LIVE-{test_id[:8]}",
        "blank_photos": blank_refs,
        "sample_photos": sample_refs,
        "model_version": model_meta.get("version"),
        "unit": report.get("unit"),
        "status": report.get("status"),
        "predicted_concentration": report.get("concentration"),
        "prediction_interval": report.get("prediction_interval"),
        "camera_absorbance": report.get("camera_absorbance"),
        "warnings": report.get("warnings", []),
        "reference_concentration": None,
        "colorimeter_absorbance": None,
        "prediction_error": None,
        "created_at": datetime.now(timezone.utc),
        "source": "public_presentation_site",
    }
    db.collection(TESTING_COLLECTION).document(test_id).set(doc)
    return test_id


def list_test_records(limit: int = 100) -> list[dict]:
    db = firestore_client()
    result = []
    for doc in db.collection(TESTING_COLLECTION).order_by("created_at", direction="DESCENDING").limit(limit).stream():
        row = doc.to_dict() or {}
        row["test_id"] = doc.id
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        row.pop("photos", None)
        result.append(row)
    return result


def add_test_reference(
    test_id: str,
    reference_concentration: float | None,
    colorimeter_absorbance: float | None,
    *,
    promote_to_training: bool = False,
    training_role: str | None = None,
    verified: bool = False,
) -> dict:
    db = firestore_client()
    test_ref = db.collection(TESTING_COLLECTION).document(test_id)
    snap = test_ref.get()
    if not snap.exists:
        raise FileNotFoundError("Test record not found.")
    old = snap.to_dict() or {}
    predicted = old.get("predicted_concentration")
    error = None
    absolute_error = None
    if reference_concentration is not None and predicted is not None:
        error = float(predicted) - float(reference_concentration)
        absolute_error = abs(error)

    updates = {
        "reference_concentration": reference_concentration,
        "colorimeter_absorbance": colorimeter_absorbance,
        "prediction_error": error,
        "absolute_prediction_error": absolute_error,
        "reference_added_at": datetime.now(timezone.utc),
    }

    promoted_ids = None
    if promote_to_training:
        if old.get("promoted_to_training") is True:
            raise ValueError("This test record has already been promoted to training_data.")
        if not verified:
            raise ValueError("Confirm that the reference concentration and colorimeter reading have been checked before adding this result to training_data.")
        if reference_concentration is None:
            raise ValueError("A known reference concentration is required before a test can be used for training.")
        if training_role not in {"standard", "validation", "resolution"}:
            raise ValueError("training_role must be standard, validation or resolution.")
        if old.get("status") not in {"OK", "CHECK"}:
            raise ValueError("A rejected/retake test cannot be promoted into training_data.")
        if not old.get("blank_photos") or not old.get("sample_photos"):
            raise ValueError("The test does not contain both blank and sample photographs.")
        unit = old.get("unit") or "unit"
        session_id = f"live-{test_id}"
        blank_id = f"{test_id}-blank"
        sample_id = f"{test_id}-labelled"
        now = datetime.now(timezone.utc)
        training = db.collection(TRAINING_COLLECTION)
        # Reuse the already stored private photo objects; do not duplicate large files.
        training.document(f"feedback-{test_id}-blank").set({
            "record_id": f"feedback-{test_id}-blank", "sample_id": blank_id,
            "session_id": session_id, "role": "blank", "concentration": None,
            "concentration_unit": unit, "colorimeter_absorbance": None,
            "photos": old["blank_photos"], "verified": True,
            "source_test_id": test_id, "created_at": now,
        })
        training.document(f"feedback-{test_id}-sample").set({
            "record_id": f"feedback-{test_id}-sample", "sample_id": sample_id,
            "session_id": session_id, "role": training_role,
            "concentration": float(reference_concentration), "concentration_unit": unit,
            "colorimeter_absorbance": colorimeter_absorbance,
            "photos": old["sample_photos"], "verified": True,
            "source_test_id": test_id, "created_at": now,
        })
        promoted_ids = [f"feedback-{test_id}-blank", f"feedback-{test_id}-sample"]
        updates.update({
            "promoted_to_training": True,
            "training_role": training_role,
            "training_record_ids": promoted_ids,
            "promoted_at": now,
        })

    test_ref.update(updates)
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in updates.items()}


def _independent_test_metrics(test_rows: list[dict]) -> list[dict]:
    """Summarise blind tests labelled after prediction, grouped by model version.

    Once a result is deliberately promoted into training_data, it is excluded
    from the independent-test summary so the same sample is not presented as
    both training feedback and untouched evaluation evidence.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in test_rows:
        if row.get("promoted_to_training") is True:
            continue
        if row.get("status") not in {"OK", "CHECK"}:
            continue
        if row.get("predicted_concentration") is None or row.get("reference_concentration") is None:
            continue
        if not row.get("model_version"):
            continue
        grouped[str(row["model_version"])].append(row)

    output = []
    for version, rows in sorted(grouped.items(), key=lambda item: item[0], reverse=True):
        truth = np.asarray([float(r["reference_concentration"]) for r in rows], dtype=float)
        prediction = np.asarray([float(r["predicted_concentration"]) for r in rows], dtype=float)
        error = prediction - truth
        nonzero = truth != 0
        total = float(np.sum((truth - np.mean(truth)) ** 2))
        mape = float(np.mean(np.abs(error[nonzero] / truth[nonzero])) * 100) if np.any(nonzero) else None
        output.append({
            "model_version": version,
            "n": int(len(rows)),
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "mape_pct": mape,
            "r2": float(1 - np.sum(error ** 2) / total) if total > 0 else None,
            "bias": float(np.mean(error)),
            "note": "Only labelled OK/CHECK tests that have not been promoted to training_data are included.",
        })
    return output


def dashboard_summary() -> dict:
    db = firestore_client()
    training = list(db.collection(TRAINING_COLLECTION).stream())
    tests = list(db.collection(TESTING_COLLECTION).stream())
    training_rows = [(d.to_dict() or {}) for d in training]
    test_rows = [(d.to_dict() or {}) for d in tests]
    role_counts: dict[str, int] = defaultdict(int)
    for row in training_rows:
        role_counts[row.get("role", "unknown")] += 1
    verified = sum(1 for row in training_rows if row.get("verified") is True)
    labelled = sum(1 for row in test_rows if row.get("reference_concentration") is not None)
    independent = _independent_test_metrics(test_rows)
    return {
        "training_records": len(training),
        "verified_training_records": verified,
        "role_counts": dict(role_counts),
        "test_records": len(tests),
        "labelled_test_records": labelled,
        "independent_labelled_test_records": sum(row["n"] for row in independent),
        "independent_test_metrics_by_model": independent,
    }
