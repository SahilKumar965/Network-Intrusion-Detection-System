"""HTTP endpoints. Routes only validate input and translate errors; the work happens in services/traffic.py."""
import os
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app import config
from backend.app.database.session import get_db
from backend.app.ml.predictor import Predictor
from backend.app.models.db_models import Alert, Upload
from backend.app.schemas.schemas import (
    AlertDetail, AlertOut, AlertsPage, BatchRequest, BatchResponse, DashboardStats, PredictionOut, ResultsPage, TrafficRecord, UploadOut,
)
from backend.app.services import traffic

router = APIRouter()
api = APIRouter(prefix="/api/v1")
Severity = Literal["HIGH", "MEDIUM", "LOW"]


def get_predictor(request: Request) -> Predictor:
    return request.app.state.predictor


@router.get("/health", tags=["system"])
def health(request: Request, db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "model_loaded": request.app.state.predictor is not None, "database": "ok"}


@api.get("/model/info", tags=["model"])
def model_info(request: Request, predictor: Predictor = Depends(get_predictor)):
    m = predictor.metrics
    return {
        "model_id": request.app.state.model_id,
        "selected_model": m["selected_model"],
        "selection_metric": m["selection_metric"],
        "trained_at": m["trained_at"],
        "dataset": m["dataset"],
        "classes": m["classes"],
        "feature_columns": m["feature_columns"],
        "split_sizes": m["split_sizes"],
        "cleaning": m["cleaning"],
        "models": m["models"],
    }


@api.post("/predict", response_model=PredictionOut, tags=["predict"])
def predict(record: TrafficRecord, predictor: Predictor = Depends(get_predictor)):
    try:
        return traffic.predict_records(predictor, [record.features])[0]
    except traffic.InvalidUpload as e:
        raise HTTPException(422, str(e))


@api.post("/predict/batch", response_model=BatchResponse, tags=["predict"])
def predict_batch(body: BatchRequest, predictor: Predictor = Depends(get_predictor)):
    try:
        return {"predictions": traffic.predict_records(predictor, [r.features for r in body.records])}
    except traffic.InvalidUpload as e:
        raise HTTPException(422, str(e))


@api.post("/upload", response_model=UploadOut, status_code=201, tags=["uploads"])
def upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
           predictor: Predictor = Depends(get_predictor)):
    # Only the base name is kept, for display. It is never used as a filesystem path.
    filename = os.path.basename(file.filename or "upload.csv")[:255]
    if not filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files are accepted")
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    content = file.file.read(limit + 1)  # read one byte past the limit to detect oversize files
    if len(content) > limit:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_MB} MB")
    if not content.strip():
        raise HTTPException(400, "File is empty")
    if b"\x00" in content[:8192]:
        raise HTTPException(400, "File looks binary, not CSV text")
    try:
        return traffic.process_upload(db, predictor, request.app.state.model_id, filename, content)
    except traffic.InvalidUpload as e:
        db.rollback()
        raise HTTPException(400, str(e))


def get_upload_or_404(db: Session, upload_id: int) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found")
    return upload


@api.get("/uploads", response_model=list[UploadOut], tags=["uploads"])
def list_uploads(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    return db.scalars(select(Upload).order_by(Upload.id.desc()).limit(limit)).all()


@api.get("/uploads/{upload_id}", response_model=UploadOut, tags=["uploads"])
def get_upload(upload_id: int, db: Session = Depends(get_db)):
    return get_upload_or_404(db, upload_id)


@api.get("/uploads/{upload_id}/results", response_model=ResultsPage, tags=["uploads"])
def upload_results(upload_id: int, db: Session = Depends(get_db),
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                   label: str | None = Query(None, max_length=30), malicious_only: bool = False,
                   min_confidence: float = Query(0.0, ge=0, le=1), row_index: int | None = Query(None, ge=0)):
    get_upload_or_404(db, upload_id)
    total, items = traffic.get_results(db, upload_id, page, page_size, label, malicious_only, min_confidence, row_index)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@api.get("/uploads/{upload_id}/results.csv", tags=["uploads"])
def upload_results_csv(upload_id: int, db: Session = Depends(get_db)):
    upload = get_upload_or_404(db, upload_id)
    return StreamingResponse(
        traffic.iter_results_csv(db, upload_id), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="predictions_upload_{upload.id}.csv"'},
    )


@api.get("/alerts", response_model=AlertsPage, tags=["alerts"])
def alerts(db: Session = Depends(get_db), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
           severity: Severity | None = None, category: str | None = Query(None, max_length=30),
           upload_id: int | None = None):
    total, items = traffic.list_alerts(db, page, page_size, severity, category, upload_id)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@api.get("/alerts/{alert_id}", response_model=AlertDetail, tags=["alerts"])
def alert_detail(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    return {**AlertOut.model_validate(alert).model_dump(), "features": alert.features,
            "filename": db.get(Upload, alert.upload_id).filename}


@api.get("/dashboard/stats", response_model=DashboardStats, tags=["dashboard"])
def stats(db: Session = Depends(get_db)):
    return traffic.dashboard_stats(db)


router.include_router(api)
