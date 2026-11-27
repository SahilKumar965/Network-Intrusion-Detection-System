"""Database tables. Raw traffic features are NOT stored per row: only predictions,
plus a few key features on alerts so an analyst can investigate them."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModelMetadata(Base):
    __tablename__ = "model_metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    trained_at: Mapped[str] = mapped_column(String(40))
    macro_f1_test: Mapped[float] = mapped_column(Float)
    metrics: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    row_count: Mapped[int] = mapped_column(Integer)
    malicious_count: Mapped[int] = mapped_column(Integer)
    invalid_cells: Mapped[int] = mapped_column(Integer)
    class_counts: Mapped[dict] = mapped_column(JSON)
    model_id: Mapped[int] = mapped_column(ForeignKey("model_metadata.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    __table_args__ = (Index("ix_predictions_upload_row", "upload_id", "row_index"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    flow_timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True)  # from the CSV, if it has one
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # Connection fields for the alert list, read from the stored features (None if the CSV had no such column).
    @property
    def source_ip(self) -> str | None:
        return self.features.get("Source IP")

    @property
    def destination_ip(self) -> str | None:
        return self.features.get("Destination IP")

    @property
    def destination_port(self) -> int | None:
        port = self.features.get("Destination Port")
        return int(port) if port is not None else None
