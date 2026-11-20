from __future__ import annotations

import json
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from cucolor.agent import ColorimetryAgent
from . import settings
from .firebase_service import firestore_client
from .model_service import (
    TRAINING_COLLECTION, TESTING_COLLECTION, add_test_reference,
    approve_candidate, build_candidate_model, create_test_record,
    create_training_record, dashboard_summary, list_test_records,
    list_training_records, load_active_model, verify_training_record,
)
from .security import require_team_member, verify_public_app_check

app = FastAPI(title="Cu-Photo-Colorimeter API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Firebase-AppCheck"],
)

# Best-effort, per-process guard for a small live demonstration. For a public
# production service, add a managed edge rate limiter/Cloud Armor policy too.
_prediction_times: deque[float] = deque()


class VerifyBody(BaseModel):
    verified: bool


class ApproveBody(BaseModel):
    approve_as_provisional: bool = False


class ReferenceBody(BaseModel):
    reference_concentration: float | None = Field(default=None, ge=0)
    colorimeter_absorbance: float | None = Field(default=None, ge=0)
    promote_to_training: bool = False
    training_role: str | None = None
    verified: bool = False


def _check_rate_limit() -> None:
    now = time.monotonic()
    while _prediction_times and now - _prediction_times[0] > 60:
        _prediction_times.popleft()
    if len(_prediction_times) >= settings.MAX_PREDICTIONS_PER_MINUTE_PER_PROCESS:
        raise HTTPException(status_code=429, detail="Demo is receiving too many requests. Please try again shortly.")
    _prediction_times.append(now)


async def _read_images(files: list[UploadFile], *, minimum: int = 1) -> list[tuple[str, bytes, str]]:
    if len(files) < minimum or len(files) > settings.MAX_PHOTOS_PER_SAMPLE:
        raise HTTPException(status_code=400, detail=f"Upload between {minimum} and {settings.MAX_PHOTOS_PER_SAMPLE} photos.")
    result = []
    for file in files:
        content_type = (file.content_type or "").lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=415, detail="Only JPEG, PNG and WebP photographs are accepted.")
        data = await file.read(settings.MAX_UPLOAD_BYTES + 1)
        if len(data) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Each photo must be no larger than {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        # Validate that the upload is a decodable image, not just a renamed file.
        try:
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image dimensions are too large.")
                image.verify()
        except Exception:
            raise HTTPException(status_code=400, detail=f"Could not decode {file.filename or 'uploaded image'}.")
        result.append((file.filename or "photo.jpg", data, content_type))
    return result


@app.get("/health")
def health():
    return {"ok": True, "service": "cu-photo-colorimeter-api", "version": "1.0.0"}


@app.get("/api/team/me")
def team_me(claims: Annotated[dict, Depends(require_team_member)]):
    return {"uid": claims.get("uid"), "email": claims.get("email"), "team_member": True}


@app.get("/api/team/dashboard")
def team_dashboard(_: Annotated[dict, Depends(require_team_member)]):
    return dashboard_summary()


@app.get("/api/team/training-data")
def team_training_data(limit: int = 100, _: dict = Depends(require_team_member)):
    return {"items": list_training_records(max(1, min(limit, 250)))}


@app.post("/api/team/training-data")
async def team_create_training_data(
    metadata: Annotated[str, Form()],
    photos: Annotated[list[UploadFile], File()],
    _: Annotated[dict, Depends(require_team_member)],
):
    try:
        data = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Metadata must be valid JSON.")
    allowed_roles = {"blank", "standard", "validation", "resolution"}
    if data.get("role") not in allowed_roles:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(allowed_roles)}")
    if not data.get("sample_id") or not data.get("session_id"):
        raise HTTPException(status_code=422, detail="sample_id and session_id are required.")
    if data["role"] == "blank":
        data["concentration"] = None
        data["colorimeter_absorbance"] = None
    else:
        try:
            data["concentration"] = float(data["concentration"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="A numeric known concentration is required for this role.")
        if data["concentration"] < 0:
            raise HTTPException(status_code=422, detail="Concentration cannot be negative.")
    if data.get("colorimeter_absorbance") in (None, ""):
        data["colorimeter_absorbance"] = None
    else:
        try:
            data["colorimeter_absorbance"] = float(data["colorimeter_absorbance"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Colorimeter absorbance must be numeric.")
        if data["colorimeter_absorbance"] < 0:
            raise HTTPException(status_code=422, detail="Colorimeter absorbance cannot be negative.")
    data["verified"] = data.get("verified") is True
    data["sample_id"] = str(data["sample_id"]).strip()
    data["session_id"] = str(data["session_id"]).strip()
    if not data["sample_id"] or not data["session_id"]:
        raise HTTPException(status_code=422, detail="sample_id and session_id cannot be blank.")
    uploaded = await _read_images(photos)
    try:
        record_id = await run_in_threadpool(create_training_record, data, uploaded)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Firebase save failed: {exc}")
    return {"record_id": record_id, "sample_id": data["sample_id"], "saved": True}


@app.patch("/api/team/training-data/{record_id}/verification")
def team_verify_training_data(record_id: str, body: VerifyBody, _: dict = Depends(require_team_member)):
    try:
        verify_training_record(record_id, body.verified)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"record_id": record_id, "verified": body.verified}


@app.post("/api/team/train")
def team_train(_: dict = Depends(require_team_member)):
    try:
        result = build_candidate_model()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Training failed: {exc}")
    return result


@app.post("/api/team/models/{version}/approve")
def team_approve_model(version: str, body: ApproveBody, _: dict = Depends(require_team_member)):
    try:
        return approve_candidate(version, body.approve_as_provisional)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/team/testing-data")
def team_testing_data(limit: int = 100, _: dict = Depends(require_team_member)):
    return {"items": list_test_records(max(1, min(limit, 250)))}


@app.patch("/api/team/testing-data/{test_id}/reference")
def team_add_test_reference(test_id: str, body: ReferenceBody, _: dict = Depends(require_team_member)):
    if body.reference_concentration is None and body.colorimeter_absorbance is None:
        raise HTTPException(status_code=422, detail="Provide a reference concentration, colorimeter absorbance, or both.")
    try:
        return add_test_reference(
            test_id, body.reference_concentration, body.colorimeter_absorbance,
            promote_to_training=body.promote_to_training,
            training_role=body.training_role,
            verified=body.verified,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/public/model-info")
def public_model_info():
    try:
        _, metadata = load_active_model()
    except FileNotFoundError:
        return {"model_available": False, "message": "The team has not published an approved calibration model yet."}
    return {
        "model_available": True,
        "version": metadata.get("version"),
        "approval_status": metadata.get("approval_status"),
        "unit": metadata.get("unit"),
        "range_min": metadata.get("range_min"),
        "range_max": metadata.get("range_max"),
        "lod": metadata.get("lod"),
        "loq": metadata.get("loq"),
        "validation_metrics": metadata.get("validation_metrics"),
        "selected_method": metadata.get("selected_method"),
        "selection_status": metadata.get("selection_status"),
        "mdd": metadata.get("mdd"),
        "warning": "Performance applies only to the validated phone, dark box, lighting and chemistry protocol.",
    }


@app.post("/api/public/predict")
async def public_predict(
    request: Request,
    blank_photos: Annotated[list[UploadFile], File()],
    sample_photos: Annotated[list[UploadFile], File()],
    sample_id: Annotated[str | None, Form()] = None,
):
    verify_public_app_check(request)
    _check_rate_limit()
    blanks = await _read_images(blank_photos)
    samples = await _read_images(sample_photos)
    if sum(len(item[1]) for item in blanks + samples) > 24 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Combined blank and sample photos must be no larger than 24 MB per prediction.")
    try:
        calibration, model_meta = await run_in_threadpool(load_active_model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    all_files = blanks + samples
    with tempfile.TemporaryDirectory(prefix="cu-photo-live-") as tmp:
        folder = Path(tmp)
        blank_paths = []
        sample_paths = []
        for index, (name, content, _) in enumerate(all_files):
            path = folder / f"capture_{index}_{Path(name).name}"
            path.write_bytes(content)
            (blank_paths if index < len(blanks) else sample_paths).append(path)
        report = ColorimetryAgent(calibration).run(blank_paths, sample_paths, sample_id or "PRESENTATION")
    result = {
        "sample_id": report.sample_id,
        "status": report.status,
        "unit": report.unit,
        "concentration": report.conc if report.status in {"OK", "CHECK"} else None,
        "prediction_interval": [report.ci_low, report.ci_high] if report.ci_low is not None and report.ci_high is not None else None,
        "camera_absorbance": report.absorbance,
        "camera_absorbance_sd": report.a_std,
        "n_photos": report.n_photos,
        "warnings": report.warnings,
        "trace": [{"step": step, "result": detail} for step, detail in report.trace],
    }
    try:
        test_id = await run_in_threadpool(create_test_record, {"sample_id": sample_id}, all_files[:len(blanks)], all_files[len(blanks):], result, model_meta)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Prediction completed, but saving the test record failed: {exc}")
    result["test_id"] = test_id
    result["model_version"] = model_meta.get("version")
    return result
