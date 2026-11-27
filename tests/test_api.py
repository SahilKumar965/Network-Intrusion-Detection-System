"""Endpoint tests against the real trained model."""
import io

import pandas as pd
import pytest

from backend.app import config
from backend.app.services.traffic import severity_for


def upload(client, content: bytes, name: str = "flows.csv"):
    return client.post("/api/v1/upload", files={"file": (name, content, "text/csv")})


def first_record(sample_csv: bytes, client) -> dict:
    cols = client.get("/api/v1/model/info").json()["feature_columns"]
    df = pd.read_csv(io.BytesIO(sample_csv), encoding="latin-1").rename(columns=str.strip)
    return {c: float(df.iloc[0][c]) if pd.notna(df.iloc[0][c]) else None for c in cols}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "model_loaded": True, "database": "ok"}


def test_model_info_reports_saved_metrics(client):
    info = client.get("/api/v1/model/info").json()
    assert info["selected_model"] in info["models"]
    assert len(info["feature_columns"]) == 78
    assert "BENIGN" in info["classes"]
    assert 0 < info["models"][info["selected_model"]]["test"]["macro"]["f1"] <= 1


def test_predict_single(client, sample_csv):
    r = client.post("/api/v1/predict", json={"features": first_record(sample_csv, client)})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] in body["probabilities"]
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-6
    assert body["is_malicious"] == (body["label"] != "BENIGN")


def test_predict_rejects_missing_features(client):
    r = client.post("/api/v1/predict", json={"features": {"Flow Duration": 1.0}})
    assert r.status_code == 422 and "Missing" in r.json()["detail"]


def test_predict_rejects_non_numeric(client):
    assert client.post("/api/v1/predict", json={"features": {"Flow Duration": "abc"}}).status_code == 422


def test_predict_batch(client, sample_csv):
    rec = first_record(sample_csv, client)
    r = client.post("/api/v1/predict/batch", json={"records": [{"features": rec}] * 3})
    assert r.status_code == 200 and len(r.json()["predictions"]) == 3


def test_predict_batch_limits(client):
    assert client.post("/api/v1/predict/batch", json={"records": []}).status_code == 422
    too_many = {"records": [{"features": {}}] * 1001}
    assert client.post("/api/v1/predict/batch", json=too_many).status_code == 422


def test_upload_flow_results_alerts_and_stats(client, sample_csv):
    r = upload(client, sample_csv)
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["row_count"] == 44
    assert sum(up["class_counts"].values()) == 44
    assert up["malicious_count"] == 44 - up["class_counts"].get("BENIGN", 0)

    page = client.get(f"/api/v1/uploads/{up['id']}/results", params={"page_size": 10}).json()
    assert page["total"] == 44 and len(page["items"]) == 10
    mal = client.get(f"/api/v1/uploads/{up['id']}/results", params={"malicious_only": True}).json()
    assert mal["total"] == up["malicious_count"]

    csv = client.get(f"/api/v1/uploads/{up['id']}/results.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert len(csv.text.strip().splitlines()) == 45

    alerts = client.get("/api/v1/alerts", params={"upload_id": up["id"]}).json()
    assert alerts["total"] == up["malicious_count"] > 0
    first = alerts["items"][0]
    assert first["source_ip"] and first["destination_ip"] and isinstance(first["destination_port"], int)
    detail = client.get(f"/api/v1/alerts/{alerts['items'][0]['id']}").json()
    assert detail["filename"] == "flows.csv"
    assert "Source IP" in detail["features"] and "Destination Port" in detail["features"]
    assert detail["flow_timestamp"]

    listed = client.get("/api/v1/uploads").json()
    assert [u["id"] for u in listed] == [up["id"]]

    stats = client.get("/api/v1/dashboard/stats").json()
    assert stats["total_records"] == 44 and stats["uploads"] == 1
    assert stats["malicious_records"] == up["malicious_count"]
    assert sum(stats["severity_counts"].values()) == up["malicious_count"]
    assert len(stats["recent_alerts"]) == 5


def test_alert_filters_and_404(client, sample_csv):
    upload(client, sample_csv)
    high = client.get("/api/v1/alerts", params={"severity": "HIGH"}).json()
    assert all(a["severity"] == "HIGH" for a in high["items"])
    assert client.get("/api/v1/alerts", params={"severity": "CRITICAL"}).status_code == 422
    assert client.get("/api/v1/alerts/999999").status_code == 404
    assert client.get("/api/v1/uploads/999999/results").status_code == 404


@pytest.mark.parametrize("name,content,status,msg", [
    ("flows.txt", b"a,b\n1,2\n", 400, "Only .csv"),
    ("flows.csv", b"", 400, "empty"),
    ("flows.csv", b"\x00\x01\x02binary", 400, "binary"),
    ("flows.csv", b"a,b\n1,2\n", 400, "Missing"),
    ("flows.csv", b'"unclosed\n', 400, "parse"),
    ("flows.csv", b"Flow Duration, Flow Duration\n1,2\n", 400, "Duplicate"),
])
def test_invalid_uploads(client, name, content, status, msg):
    r = upload(client, content, name)
    assert r.status_code == status and msg.lower() in r.json()["detail"].lower()


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    assert upload(client, b"a,b\n1,2\n").status_code == 413


def test_upload_path_traversal_name_is_sanitised(client, sample_csv):
    r = upload(client, sample_csv, "../../etc/evil.csv")
    assert r.status_code == 201 and r.json()["filename"] == "evil.csv"


def test_upload_counts_invalid_cells(client, sample_csv):
    df = pd.read_csv(io.BytesIO(sample_csv), encoding="latin-1")
    df[" Flow Duration"] = df[" Flow Duration"].astype(object)
    df.loc[0, " Flow Duration"] = "not-a-number"
    r = upload(client, df.to_csv(index=False).encode("latin-1"))
    assert r.status_code == 201 and r.json()["invalid_cells"] == 1


def test_rate_limit(client):
    codes = [client.get("/api/v1/dashboard/stats").status_code for _ in range(config.RATE_LIMIT_PER_MINUTE + 1)]
    assert codes[0] == 200 and codes[-1] == 429
    assert client.get("/health").status_code == 200  # health checks are never limited


def test_severity_rules():
    assert severity_for("BENIGN", 0.99) is None
    assert severity_for("DDoS", 0.95) == "HIGH"
    assert severity_for("DDoS", 0.5) == "MEDIUM"
    assert severity_for("PortScan", 0.9) == "MEDIUM"
    assert severity_for("PortScan", 0.5) == "LOW"
