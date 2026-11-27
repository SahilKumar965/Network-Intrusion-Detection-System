"""Database operations, run on SQLite and (when configured) PostgreSQL."""
import io

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import func, select

from backend.app import config
from backend.app.database import session
from backend.app.ml.predictor import Predictor
from backend.app.models.db_models import Alert, ModelMetadata, Prediction, Upload
from backend.app.services.traffic import InvalidUpload, process_upload, register_model


@pytest.fixture(scope="module")
def predictor():
    return Predictor(config.MODEL_PATH, config.METRICS_PATH)


@pytest.fixture()
def db(database):
    with session.SessionLocal() as s:
        yield s


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_register_model_is_idempotent_and_tracks_active(db, predictor):
    first = register_model(db, predictor)
    assert register_model(db, predictor).id == first.id
    assert count(db, ModelMetadata) == 1

    # A retrained model (new trained_at) becomes the only active one.
    predictor.metrics = {**predictor.metrics, "trained_at": "2099-01-01T00:00:00+00:00"}
    try:
        second = register_model(db, predictor)
    finally:
        predictor.metrics = {**predictor.metrics, "trained_at": first.trained_at}
    assert second.id != first.id
    assert [m.id for m in db.scalars(select(ModelMetadata).where(ModelMetadata.is_active))] == [second.id]


def test_upload_persists_predictions_and_alerts(db, predictor, sample_csv):
    model_id = register_model(db, predictor).id
    up = process_upload(db, predictor, model_id, "flows.csv", sample_csv)

    assert db.get(Upload, up.id).row_count == 44
    assert count(db, Prediction) == 44
    assert count(db, Alert) == up.malicious_count
    alert = db.scalars(select(Alert)).first()
    assert alert.features["Source IP"] and alert.severity in {"HIGH", "MEDIUM", "LOW"}


def test_non_finite_values_are_stored_as_null(db, predictor, sample_csv):
    # PostgreSQL's JSON type rejects NaN/Infinity, so they must become null before insert.
    df = pd.read_csv(io.BytesIO(sample_csv), encoding="latin-1")
    col = next(c for c in df.columns if c.strip() == "Flow Bytes/s")
    df[col] = np.inf
    model_id = register_model(db, predictor).id
    process_upload(db, predictor, model_id, "inf.csv", df.to_csv(index=False).encode("latin-1"))

    alerts = db.scalars(select(Alert)).all()
    assert alerts and all(a.features["Flow Bytes/s"] is None for a in alerts)


def test_invalid_upload_writes_nothing(db, predictor):
    model_id = register_model(db, predictor).id
    with pytest.raises(InvalidUpload):
        process_upload(db, predictor, model_id, "bad.csv", b"a,b\n1,2\n")
    db.rollback()
    assert count(db, Upload) == 0 and count(db, Prediction) == 0
