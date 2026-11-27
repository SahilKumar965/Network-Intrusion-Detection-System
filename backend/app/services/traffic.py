"""Business logic between the API routes and the model/database: uploads, predictions, alerts, stats."""
import io
import logging
import math

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from backend.app.ml.predictor import BENIGN, Predictor
from backend.app.models.db_models import Alert, ModelMetadata, Prediction, Upload
from ml.preprocessing import normalize_columns

log = logging.getLogger(__name__)

# Shown on the alert detail page. Context columns are display-only and never reach the model.
CONTEXT_COLUMNS = ["Source IP", "Source Port", "Destination IP", "Timestamp"]
KEY_FEATURES = [
    "Destination Port", "Protocol", "Flow Duration", "Total Fwd Packets", "Total Backward Packets",
    "Flow Bytes/s", "Flow Packets/s", "SYN Flag Count", "Init_Win_bytes_backward", "Average Packet Size",
]
HIGH_RISK = {"DoS", "DDoS", "BruteForce", "WebAttack", "Bot"}
LOW_CONFIDENCE = 0.6


class InvalidUpload(ValueError):
    """The uploaded file is not a usable traffic CSV. The message is safe to show to the user."""


def severity_for(label: str, confidence: float) -> str | None:
    """HIGH for attacks that do damage, MEDIUM for reconnaissance; one level lower when the model is unsure."""
    if label == BENIGN:
        return None
    levels = ["LOW", "MEDIUM", "HIGH"]
    level = 2 if label in HIGH_RISK else 1
    if confidence < LOW_CONFIDENCE:
        level -= 1
    return levels[level]


def to_json_value(v):
    """JSON can't hold NaN/inf or numpy types."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    if hasattr(v, "item"):
        return to_json_value(v.item())
    return v


def predict_records(predictor: Predictor, records: list[dict]) -> list[dict]:
    """Classify records sent as JSON (single or batch). Not stored: only uploads are persisted."""
    X = pd.DataFrame(records)
    missing = predictor.missing_columns(X.columns)
    if missing:
        raise InvalidUpload(f"Missing {len(missing)} feature(s), e.g. {missing[:5]}")
    labels, conf, proba = predictor.predict(X.astype("float64"))
    return [
        {
            "label": label,
            "confidence": float(c),
            "is_malicious": label != BENIGN,
            "severity": severity_for(label, float(c)),
            "probabilities": {cls: float(p) for cls, p in zip(predictor.classes, row)},
        }
        for label, c, row in zip(labels, conf, proba)
    ]


def register_model(db: Session, predictor: Predictor) -> ModelMetadata:
    """Record the loaded model once (matched by name + training time) and mark it active."""
    m = predictor.metrics
    row = db.scalar(select(ModelMetadata).where(
        ModelMetadata.name == predictor.model_name, ModelMetadata.trained_at == m["trained_at"]))
    if row is None:
        row = ModelMetadata(
            name=predictor.model_name, trained_at=m["trained_at"],
            macro_f1_test=m["models"][predictor.model_name]["test"]["macro"]["f1"], metrics=m)
        db.add(row)
    for other in db.scalars(select(ModelMetadata).where(ModelMetadata.is_active)):
        other.is_active = other is row
    row.is_active = True
    db.commit()
    return row


def process_upload(db: Session, predictor: Predictor, model_id: int, filename: str, content: bytes) -> Upload:
    """Parse, validate and classify an uploaded CSV, then store predictions and alerts."""
    try:
        # pandas only parses text into values here; nothing in the file is ever executed.
        raw = pd.read_csv(io.BytesIO(content), encoding="latin-1", low_memory=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError, ValueError) as e:
        raise InvalidUpload(f"Could not parse CSV: {type(e).__name__}") from e

    raw = raw.rename(columns=lambda c: str(c).strip())
    dupes = raw.columns[raw.columns.duplicated()].unique().tolist()
    if dupes:  # e.g. "Flow Bytes/s" and " Flow Bytes/s": the same column after stripping spaces
        raise InvalidUpload(f"Duplicate column(s): {dupes[:5]}")
    feats = normalize_columns(raw)
    missing = predictor.missing_columns(feats.columns)
    if missing:
        raise InvalidUpload(f"Missing {len(missing)} required column(s), e.g. {missing[:5]}")

    original = feats[predictor.feature_columns]
    X = original.apply(pd.to_numeric, errors="coerce")
    invalid_cells = int((original.notna() & X.isna()).to_numpy().sum())
    X = X[X.notna().any(axis=1)]  # blank lines are not records
    if X.empty:
        raise InvalidUpload("The file has no data rows")

    labels, conf, _ = predictor.predict(X)
    labels_s = pd.Series(labels, index=X.index)
    upload = Upload(
        filename=filename, size_bytes=len(content), row_count=len(X),
        malicious_count=int((labels_s != BENIGN).sum()), invalid_cells=invalid_cells,
        class_counts={k: int(v) for k, v in labels_s.value_counts().items()}, model_id=model_id,
    )
    db.add(upload)
    db.flush()  # assigns upload.id

    db.execute(insert(Prediction), [
        {"upload_id": upload.id, "row_index": int(i), "label": lab, "confidence": float(c)}
        for i, lab, c in zip(X.index, labels, conf)
    ])

    is_alert = (labels_s != BENIGN).to_numpy()
    alert_idx = X.index[is_alert]
    context = [c for c in CONTEXT_COLUMNS if c in raw.columns]
    detail = pd.concat([raw.loc[alert_idx, context], X.loc[alert_idx, [c for c in KEY_FEATURES if c in X.columns]]], axis=1)
    alerts = []
    for i, lab, c, row in zip(alert_idx, labels_s[alert_idx], conf[is_alert], detail.to_dict("records")):
        values = {k: to_json_value(v) for k, v in row.items()}
        alerts.append({
            "upload_id": upload.id, "row_index": int(i), "category": lab, "confidence": float(c),
            "severity": severity_for(lab, float(c)), "features": values,
            "flow_timestamp": str(values["Timestamp"]) if values.get("Timestamp") is not None else None,
        })
    if alerts:
        db.execute(insert(Alert), alerts)
    db.commit()
    log.info("upload %s: %d rows, %d alerts, %d invalid cells", upload.id, len(X), len(alerts), invalid_cells)
    return upload


def get_results(db: Session, upload_id: int, page: int, page_size: int,
                label: str | None, malicious_only: bool, min_confidence: float, row_index: int | None):
    q = select(Prediction).where(Prediction.upload_id == upload_id, Prediction.confidence >= min_confidence)
    if label:
        q = q.where(Prediction.label == label)
    if malicious_only:
        q = q.where(Prediction.label != BENIGN)
    if row_index is not None:
        q = q.where(Prediction.row_index == row_index)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.order_by(Prediction.row_index).offset((page - 1) * page_size).limit(page_size)).all()
    return total, items


def iter_results_csv(db: Session, upload_id: int):
    """Stream all predictions of an upload as CSV, in chunks so big uploads don't load into memory at once."""
    yield "row_index,label,confidence,is_malicious\n"
    q = select(Prediction.row_index, Prediction.label, Prediction.confidence).where(
        Prediction.upload_id == upload_id).order_by(Prediction.row_index)
    for r in db.execute(q.execution_options(yield_per=5000)):
        yield f"{r.row_index},{r.label},{r.confidence:.4f},{r.label != BENIGN}\n"


def list_alerts(db: Session, page: int, page_size: int, severity: str | None, category: str | None, upload_id: int | None):
    q = select(Alert)
    if severity:
        q = q.where(Alert.severity == severity)
    if category:
        q = q.where(Alert.category == category)
    if upload_id is not None:
        q = q.where(Alert.upload_id == upload_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.order_by(Alert.created_at.desc(), Alert.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return total, items


def dashboard_stats(db: Session) -> dict:
    total, malicious, uploads = db.execute(
        select(func.coalesce(func.sum(Upload.row_count), 0), func.coalesce(func.sum(Upload.malicious_count), 0), func.count(Upload.id))
    ).one()
    distribution: dict[str, int] = {}
    for counts in db.scalars(select(Upload.class_counts)):
        for k, v in counts.items():
            distribution[k] = distribution.get(k, 0) + v
    severity = dict(db.execute(select(Alert.severity, func.count()).group_by(Alert.severity)).all())
    recent = db.scalars(select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(5)).all()
    return {
        "total_records": int(total), "malicious_records": int(malicious), "benign_records": int(total - malicious),
        "uploads": int(uploads), "class_distribution": distribution, "severity_counts": severity, "recent_alerts": recent,
    }
