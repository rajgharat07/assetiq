"""MySQL / SQLAlchemy schema. Upsert on natural keys — never double-count."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Area(Base):
    __tablename__ = "areas"
    area_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    team_id: Mapped[str] = mapped_column(String(32))
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample")


class Team(Base):
    __tablename__ = "teams"
    team_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    lead_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample")


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample")


class Well(Base):
    __tablename__ = "wells"
    asset_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    well_type: Mapped[str] = mapped_column(String(16))
    area_id: Mapped[str] = mapped_column(String(32), index=True)
    team_id: Mapped[str] = mapped_column(String(32))
    in_charge_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    installed_on: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    recorded_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_inspection_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_inspected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    equipment_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample", index=True)

    __table_args__ = (Index("ix_wells_type_area", "well_type", "area_id"),)


class Inspection(Base):
    __tablename__ = "inspections"
    inspection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    inspector_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ambient_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wellhead_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spill_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    spill_area_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spill_est_volume_bbl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_images_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample", index=True)

    __table_args__ = (Index("ix_insp_asset_time", "asset_id", "inspected_at"),)


class Maintenance(Base):
    __tablename__ = "maintenance"
    maintenance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    maintenance_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    equipment_kind: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technician_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    contractor: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    downtime_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_labor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_parts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triggered_by_inspection_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    report_file: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample", index=True)


class RegulatoryEvent(Base):
    __tablename__ = "regulatory_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    event_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    agency: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    protocol_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    related_inspection_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hours_to_report: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fine_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample", index=True)


class ContextNote(Base):
    __tablename__ = "context_notes"
    note_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    author_user_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    note_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    inspection_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    valid_from: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    valid_to: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample", index=True)


class ReportDoc(Base):
    """Free-text maintenance reports — metadata + path; body in vector store + doc_text."""

    __tablename__ = "report_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    maintenance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    report_file: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample")

    __table_args__ = (UniqueConstraint("report_file", "dataset_tag", name="uq_report_file_tag"),)


class RuleRow(Base):
    __tablename__ = "rules"
    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    operator: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source_file: Mapped[str] = mapped_column(String(256))
    source_section: Mapped[str] = mapped_column(String(128))
    well_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Correction(Base):
    """Formal corrections — keep original, apply at read time. Not the same as a user claim."""

    __tablename__ = "corrections"
    correction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32))  # inspection_field | rule_override
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    original_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(32), default="asset")  # asset | well_type
    scope_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # asset_id or T200/T350
    created_at: Mapped[datetime] = mapped_column(DateTime)
    valid_from: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    valid_to: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class SharedKnowledge(Base):
    __tablename__ = "shared_knowledge"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    author_user_id: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    valid_from: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    valid_to: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class UserMemory(Base):
    __tablename__ = "user_memory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    session_key: Mapped[str] = mapped_column(String(64), default="default")
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | summary
    content: Mapped[str] = mapped_column(Text)
    meta_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class ConflictClaim(Base):
    """Unconfirmed user assertions that disagree with data — never auto-overwrite."""

    __tablename__ = "conflict_claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    author_user_id: Mapped[str] = mapped_column(String(32))
    claim_text: Mapped[str] = mapped_column(Text)
    data_side: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="unconfirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AppState(Base):
    """Single-row counter; bump when corrections/shared/conflicts change so caches invalidate."""

    __tablename__ = "app_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state_version: Mapped[int] = mapped_column(Integer, default=1)


class AnswerCache(Base):
    """Finished answer envelopes for Turbo Mode repeat questions."""

    __tablename__ = "answer_cache"
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    dataset_tag: Mapped[str] = mapped_column(String(32), default="sample")
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    envelope_json: Mapped[dict] = mapped_column(JSON)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


def make_engine(url: str):
    return create_engine(url, pool_pre_ping=True, future=True)


def make_session_factory(url: str):
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True), engine
