"""Pydantic request/response models: every input is validated before it reaches the model or database."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_BATCH = 1000


class TrafficRecord(BaseModel):
    """One flow record: feature name -> value. null values are allowed and get imputed."""
    features: dict[str, float | None] = Field(
        description="All feature columns listed by GET /api/v1/model/info; extra keys are ignored.",
        examples=[{"Destination Port": 80, "Flow Duration": 1200}],
    )


class BatchRequest(BaseModel):
    records: list[TrafficRecord] = Field(min_length=1, max_length=MAX_BATCH)


class PredictionOut(BaseModel):
    label: str
    confidence: float
    is_malicious: bool
    severity: str | None
    probabilities: dict[str, float]


class BatchResponse(BaseModel):
    predictions: list[PredictionOut]


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    size_bytes: int
    row_count: int
    malicious_count: int
    invalid_cells: int
    class_counts: dict[str, int]
    created_at: datetime


class PredictionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_index: int
    label: str
    confidence: float


class ResultsPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PredictionRow]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    upload_id: int
    row_index: int
    category: str
    severity: str
    confidence: float
    flow_timestamp: str | None
    source_ip: str | None
    destination_ip: str | None
    destination_port: int | None
    created_at: datetime


class AlertDetail(AlertOut):
    features: dict
    filename: str


class AlertsPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AlertOut]


class DashboardStats(BaseModel):
    total_records: int
    malicious_records: int
    benign_records: int
    uploads: int
    class_distribution: dict[str, int]
    severity_counts: dict[str, int]
    recent_alerts: list[AlertOut]
