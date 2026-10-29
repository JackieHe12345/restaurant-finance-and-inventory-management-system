from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserDatasetMembership(Base):
    """Assign a non-admin user to one or more explicitly authorized datasets.

    Admin users deliberately do not need membership rows: their role is the explicit
    cross-dataset permission.  Normal web and sync requests must have a row here.
    """

    __tablename__ = "user_dataset_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "dataset_id", name="uq_user_dataset_membership"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRecord(Base):
    __tablename__ = "sync_records"
    __table_args__ = (UniqueConstraint("dataset_id", "record_type", "record_key", name="uq_record_identity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    record_key: Mapped[str] = mapped_column(String(240), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    sequence: Mapped[int] = mapped_column(Integer, index=True, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EntryTiming(Base):
    """Server-owned edit windows for the entry-only role.

    Daily payloads are intentionally JSON documents, and a single document can
    contain many ingredient/seasoning/other rows.  ``SyncRecord.updated_at`` is
    therefore not sufficient to enforce the product rule that each saved
    detail item has its own 30-minute correction clock while the first item of
    the day starts one shared 12-hour addition window for all three categories.
    This side table keeps those timestamps out of user payloads (and prevents a
    client from extending its own deadline by editing JSON).
    """

    __tablename__ = "entry_timings"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "record_type", "record_key",
            name="uq_entry_timing_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    record_key: Mapped[str] = mapped_column(String(240), index=True)
    # Earliest category timestamp retained for backward compatibility.
    detail_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # JSON object: {"day|food|name|0": "2026-...", ...}; timestamps are the
    # first successful save and never move when an item is corrected. Each
    # category owns an independent twelve-hour addition window.
    detail_item_times: Mapped[dict] = mapped_column(JSONB, default=dict)
    # The food/spice/other keys contain the shared detail-addition start.
    # Income slots reuse this JSON column as "income:<slot>": "timestamp" so
    # all nine fields are independent. Startup performs an idempotent in-place
    # migration for servers whose V13 table predates these JSONB columns.
    detail_field_times: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Legacy aggregate clocks retained for older web/desktop clients.
    store_a_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    store_b_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Legacy/total-only income rows use their own clock when no A/B split exists.
    revenue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    record_key: Mapped[str] = mapped_column(String(240), index=True)
    action: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(40), default="cloud")
    event_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    actor_user_id: Mapped[str] = mapped_column(String(36), default="")
    actor_username: Mapped[str] = mapped_column(String(80), default="")
    device_id: Mapped[str] = mapped_column(String(36), default="")
    from_version: Mapped[int] = mapped_column(Integer, default=0)
    to_version: Mapped[int] = mapped_column(Integer, default=0)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    before_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TemporaryPermission(Base):
    """Administrator-scheduled access for specific business dates and hours."""

    __tablename__ = "temporary_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    permission_role: Mapped[str] = mapped_column(String(20))
    business_start_date: Mapped[str] = mapped_column(String(10))
    business_end_date: Mapped[str] = mapped_column(String(10))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    record_key: Mapped[str] = mapped_column(String(240), index=True)
    local_version: Mapped[int] = mapped_column(Integer, default=0)
    cloud_version: Mapped[int] = mapped_column(Integer, default=0)
    local_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cloud_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    resolution: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InventoryNameCorrection(Base):
    """Durable idempotency receipt, independent of audit retention/deletion."""
    __tablename__ = "inventory_name_corrections"
    __table_args__ = (UniqueConstraint("dataset_id", "request_id", name="uq_inventory_name_correction_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(64), ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict] = mapped_column(JSONB)
    response_payload: Mapped[dict] = mapped_column(JSONB)
    actor_user_id: Mapped[str] = mapped_column(String(36), default="")
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
