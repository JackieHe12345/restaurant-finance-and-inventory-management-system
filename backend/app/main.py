from __future__ import annotations

import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, object_session

from .money_routes import ExactMoneyRoute
from .money import MoneyError, ZERO, decimal_value, money, money_text, price_text, product, json_money, normalize_payload, detail_for_comparison, exact_request_numbers, LegacyMoneyNumber
from . import config
from .database import Base, SessionLocal, engine, get_db
from .excel_io import (
    ParsedWorkbook,
    WorkbookFormatError,
    build_internal_workbook,
    build_user_workbook,
    fixed_expense_counts_towards_cash,
    merge_user_record_payload,
    normalize_fixed_expense_cash_flags,
    parse_internal_workbook,
    parse_user_workbook,
    payload_checksum,
    preserve_internal_fixed_expense_flags,
)
from .models import (
    AppUser,
    AuditLog,
    Dataset,
    Device,
    EntryTiming,
    InventoryNameCorrection,
    SyncConflict,
    SyncRecord,
    TemporaryPermission,
    UserDatasetMembership,
    utcnow,
)
from .security import create_access_token, hash_password, require_admin, require_change_permission, require_writer, verify_password, current_user
from .wechat_pay import WeChatPayError
from .wechat_sync import apply_wechat_sync, recalc_revenue_breakdown, wechat_status
from .store_settings import (
    delete_store_payment_config, payment_status, validate_and_save_wechat_files, merchant_for_store
)
from .wechat_pay import WeChatPayClient
from .inventory_validation import (
    validate_inventory, has_documents, guard_entry_inventory, inventory_clock_times, is_voided,
)
from .inventory_balance import guard_inventory_balance
from .name_corrections import router as name_correction_router


app = FastAPI(title="餐饮成本管家云端 API", version="Oct30LingChen")
app.router.route_class = ExactMoneyRoute
app.include_router(name_correction_router)

@app.exception_handler(MoneyError)
async def invalid_money_response(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials="*" not in config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Entry-role policy.  Keep these values in one place so the API, the timing
# endpoint used by the web client, and tests all share the same interpretation.
ENTRY_EDIT_WINDOW = timedelta(minutes=30)
ENTRY_DETAIL_WINDOW = timedelta(hours=12)
AUDIT_RETENTION_DAYS = 366
ENTRY_REVENUE_CUTOFF_HOUR = 11
ENTRY_DETAIL_FIELDS = ("食材明细", "佐料明细", "其他明细", "其它明细")
ENTRY_DETAIL_CATEGORIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "food": (("食材明细",), ("食材成本",)),
    "spice": (("佐料明细",), ("佐料成本",)),
    "other": (("其他明细", "其它明细"), ("其他", "其它")),
}
REVENUE_FIELDS = ("收益", "总金额", "收入", "总收入")
STORE_FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "A": (
        "A店收入", "A店现金", "A店微信增加", "A店微信自动", "A店微信覆盖",
        "A店支付宝增加", "A店支付宝覆盖", "A店外卖",
    ),
    "B": (
        "B店收入", "B店现金", "B店微信增加", "B店微信自动", "B店微信覆盖",
        "B店支付宝增加", "B店支付宝覆盖", "B店外卖",
    ),
}

# These are the nine user-facing income inputs.  The calculated store totals,
# grand total, total cash and total online values deliberately do not receive
# clocks of their own.  The legacy add/automatic payment columns remain data
# inputs for revenue calculation, but the visible manual fields below are the
# authoritative entry-role slots.
ENTRY_INCOME_SLOTS: dict[str, tuple[str, str]] = {
    "a_wechat": ("A店微信", "A店微信覆盖"),
    "a_alipay": ("A店支付宝", "A店支付宝覆盖"),
    "a_cash": ("A店现金", "A店现金"),
    "b_wechat": ("B店微信", "B店微信覆盖"),
    "b_alipay": ("B店支付宝", "B店支付宝覆盖"),
    "b_cash": ("B店现金", "B店现金"),
    "student_takeout": ("学生外卖", "学生外卖"),
    "a_takeout": ("A店外卖", "A店外卖"),
    "b_takeout": ("B店外卖", "B店外卖"),
}
ENTRY_CUSTOMER_SLOTS = {"new": ("新客", "新客人数量"), "total": ("总客数", "总客人数")}
ENTRY_CUSTOMER_FIELDS = ("新客人数量", "总客人数")

ENTRY_DERIVED_REVENUE_FIELDS = (
    "收益", "A店收入", "B店收入", "总现金", "总线上",
)


class LoginBody(BaseModel):
    username: str
    password: str


class DatasetCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    name: str = Field(min_length=1, max_length=200)
    schema_version: int = Field(default=1, ge=1, le=1000)


class DatasetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DeviceRegister(BaseModel):
    dataset_id: str
    name: str
    platform: str = ""


class RecordWrite(BaseModel):
    event_id: str = ""
    expected_version: int = 0
    occurred_at: datetime | None = None
    source: str = "cloud"
    device_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    checksum: str = ""


class RecordDelete(BaseModel):
    event_id: str = ""
    expected_version: int = 0
    occurred_at: datetime | None = None
    source: str = "cloud"
    device_id: str = ""


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)
    role: str = "viewer"
    dataset_ids: list[str] = Field(default_factory=list)
    default_dataset_id: str | None = None


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    is_active: bool | None = None
    dataset_ids: list[str] | None = None
    default_dataset_id: str | None = None


class ConflictResolve(BaseModel):
    resolution: str
    note: str | None = None
    merged_payload: dict[str, Any] | None = None


class StoreNamesUpdate(BaseModel):
    store_a_name: str = Field(default="A店", min_length=1, max_length=80)
    store_b_name: str = Field(default="B店", min_length=1, max_length=80)
    wechat_auto_sync: bool = True


class BulkDeleteBody(BaseModel):
    start_date: date
    end_date: date
    delete_month_records: bool = False
    delete_inventory_in_range: bool = True


class MonthDeleteBody(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    delete_inventory_in_month: bool = True


class CopyLedgerBody(BaseModel):
    target_dataset_id: str = Field(min_length=1, max_length=64)
    confirm_source_name: str = Field(min_length=1, max_length=200)
    confirm_target_name: str = Field(min_length=1, max_length=200)


class CashPositionBody(BaseModel):
    """Editable opening balance settings.

    The aliases are accepted because older desktop builds called the same
    values ``base_balance`` and ``as_of_date``.  ``current_balance`` is also
    accepted as a convenient first-time setup field and is converted to an
    opening balance when no opening value is supplied.
    """

    opening_balance: float | int | str | None = None
    opening_date: date | str | None = None
    shareholder_loan: float | int | str | None = None
    base_balance: float | int | str | None = None
    as_of_date: date | str | None = None
    current_balance: float | int | str | None = None

    @field_validator('opening_balance', 'shareholder_loan', 'base_balance', 'current_balance', mode='before')
    @classmethod
    def exact_cash_amount(cls, value):
        return value if value in (None, '') else money_text(value)

    transactions: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
    expected_version: int = Field(default=0, ge=0)


CASH_FORCE_TYPE = "余额强制修改"
CASH_DELTA_TYPES = {
    "向股东借款", "其它现金收入", "其它现金支出", "现金收入", "现金支出"
}


class AuditDeleteBody(BaseModel):
    audit_ids: list[str] = Field(default_factory=list, max_length=5000)
    dataset_id: str | None = None
    before: datetime | None = None


class TemporaryPermissionCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    dataset_id: str = Field(min_length=1, max_length=64)
    permission_role: str
    business_start_date: date
    business_end_date: date
    starts_at: datetime
    ends_at: datetime


def serialize_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    # SQLite (used by the desktop/offline test profile) returns DateTime
    # columns without tzinfo even though all values are written as UTC. Treat
    # such values as UTC explicitly; calling astimezone() on a naive value
    # would apply the host's local timezone and shift deadlines (e.g. by 8h in
    # Hong Kong).
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def membership_rows(db: Session, user_id: str) -> list[UserDatasetMembership]:
    return list(
        db.scalars(
            select(UserDatasetMembership)
            .where(UserDatasetMembership.user_id == user_id)
            .order_by(UserDatasetMembership.is_default.desc(), UserDatasetMembership.created_at)
        ).all()
    )


def user_out(user: AppUser, db: Session | None = None) -> dict[str, Any]:
    memberships = membership_rows(db, user.id) if db is not None else []
    dataset_ids = [item.dataset_id for item in memberships]
    default = next((item.dataset_id for item in memberships if item.is_default), None)
    if default is None and dataset_ids:
        default = dataset_ids[0]
    grants = active_temporary_permissions(db, user.id) if db is not None else []
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "dataset_ids": dataset_ids,
        "default_dataset_id": default,
        "is_test": user.username.casefold() == config.TEST_USERNAME.casefold(),
        "created_at": serialize_dt(user.created_at),
        "updated_at": serialize_dt(user.updated_at),
        "temporary_permissions": [temporary_permission_out(item) for item in grants],
    }


def dataset_out(dataset: Dataset, *, is_default: bool = False) -> dict[str, Any]:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "schema_version": dataset.schema_version,
        "is_active": True,
        "is_default": is_default,
        "is_test": dataset.id == config.TEST_DATASET_ID,
        "created_at": serialize_dt(dataset.created_at),
        "updated_at": serialize_dt(dataset.updated_at),
    }


def record_out(record: SyncRecord) -> dict[str, Any]:
    payload = (
        normalize_fixed_expense_cash_flags(record.payload)
        if isinstance(record.payload, dict)
        else record.payload
    )
    return {
        "id": record.id,
        "dataset_id": record.dataset_id,
        "record_type": record.record_type,
        "record_key": record.record_key,
        "payload": payload,
        # A legacy row can contain a stale English alias.  Report the checksum
        # of the canonical payload the client actually receives, so a sync
        # client never needs to rediscover that normalisation on its own.
        "checksum": payload_checksum(payload) if isinstance(payload, dict) else record.checksum,
        "version": record.version,
        "sequence": record.sequence,
        "is_deleted": record.is_deleted,
        "created_at": serialize_dt(record.created_at),
        "updated_at": serialize_dt(record.updated_at),
    }


def audit_out(log: AuditLog) -> dict[str, Any]:
    correction_reason = ''
    if log.source == 'inventory_name_correction':
        session = object_session(log)
        if session is not None:
            cache = session.info.setdefault('inventory_name_correction_reasons', {})
            identity = log.dataset_id, log.event_id
            if identity not in cache:
                operation = session.scalar(select(InventoryNameCorrection).where(
                    InventoryNameCorrection.dataset_id == log.dataset_id,
                    InventoryNameCorrection.request_id == log.event_id))
                cache[identity] = operation.reason if operation else ''
            correction_reason = cache[identity]
    change_summary = _audit_change_summary(log.before_payload, log.after_payload, log.record_key)
    if correction_reason:
        label = '品名更正（关联来源保序）' if log.action == 'name_correction_reindex' else '品名更正'
        change_summary = f'{label}：{correction_reason}；{change_summary}'
    return {
        "id": log.id,
        "dataset_id": log.dataset_id,
        "record_type": log.record_type,
        "record_key": log.record_key,
        "action": log.action,
        "source": log.source,
        "event_id": log.event_id,
        "actor_user_id": log.actor_user_id,
        "actor_username": log.actor_username,
        "actor_label": log.actor_username or "cloud",
        "device_id": log.device_id,
        "from_version": log.from_version,
        "to_version": log.to_version,
        "sequence": log.sequence,
        "before_payload": log.before_payload,
        "after_payload": log.after_payload,
        "checksum": log.checksum,
        "occurred_at": serialize_dt(log.occurred_at),
        "created_at": serialize_dt(log.created_at),
        "received_at": serialize_dt(log.created_at),
        "change_summary": change_summary,
        "reason": correction_reason,
    }


def temporary_permission_out(item: TemporaryPermission) -> dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "dataset_id": item.dataset_id,
        "permission_role": item.permission_role,
        "business_start_date": item.business_start_date,
        "business_end_date": item.business_end_date,
        "starts_at": serialize_dt(item.starts_at),
        "ends_at": serialize_dt(item.ends_at),
        "created_by": item.created_by,
        "created_at": serialize_dt(item.created_at),
    }


def active_temporary_permissions(
    db: Session, user_id: str, *, now: datetime | None = None
) -> list[TemporaryPermission]:
    moment = _as_utc(now) or utcnow()
    return list(
        db.scalars(
            select(TemporaryPermission).where(
                TemporaryPermission.user_id == user_id,
                TemporaryPermission.starts_at <= moment,
                TemporaryPermission.ends_at > moment,
            ).order_by(TemporaryPermission.ends_at)
        ).all()
    )


def conflict_out(conflict: SyncConflict) -> dict[str, Any]:
    return {
        "id": conflict.id,
        "dataset_id": conflict.dataset_id,
        "record_type": conflict.record_type,
        "record_key": conflict.record_key,
        "local_version": conflict.local_version,
        "cloud_version": conflict.cloud_version,
        "local_payload": conflict.local_payload,
        "cloud_payload": conflict.cloud_payload,
        "status": conflict.status,
        "resolution": conflict.resolution,
        "note": conflict.note,
        "created_at": serialize_dt(conflict.created_at),
        "resolved_at": serialize_dt(conflict.resolved_at),
    }


def _entry_empty_or_zero(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        try:
            return decimal_value(value) == 0
        except ValueError:
            return False
    return False


def _entry_merge_payload(old: Any, new: Any, path: str = "") -> tuple[Any, list[str]]:
    """Merge an entry-permission edit without changing saved non-zero fields.

    Lists are matched by stable id/date/month keys, which covers daily ledger rows,
    fixed-cost rows and inventory entries. Blank input is treated as "leave saved
    value unchanged"; zero-valued saved fields remain writable after the deadline.
    """
    import copy

    if isinstance(old, dict) and isinstance(new, dict):
        merged = copy.deepcopy(old)
        violations: list[str] = []
        for key, value in new.items():
            child, errors = _entry_merge_payload(old.get(key), value, f"{path}.{key}" if path else str(key))
            merged[key] = child
            violations.extend(errors)
        return merged, violations
    if isinstance(old, list) and isinstance(new, list):
        merged = copy.deepcopy(old)
        violations: list[str] = []
        identity_map: dict[tuple[str, str], int] = {}
        for index, item in enumerate(old):
            if not isinstance(item, dict):
                continue
            identity = next(((key, str(item.get(key))) for key in ("id", "日期", "date", "月份", "month") if item.get(key) not in (None, "")), None)
            if identity:
                identity_map[identity] = index
        used: set[int] = set()
        for index, item in enumerate(new):
            identity = None
            if isinstance(item, dict):
                identity = next(((key, str(item.get(key))) for key in ("id", "日期", "date", "月份", "month") if item.get(key) not in (None, "")), None)
            target = identity_map.get(identity) if identity else (index if index < len(old) else None)
            if target is None or target in used:
                # New inventory rows and new detail rows are legitimate entry work.
                merged.append(copy.deepcopy(item))
                continue
            used.add(target)
            child, errors = _entry_merge_payload(old[target], item, f"{path}[{target}]")
            merged[target] = child
            violations.extend(errors)
        return merged, violations
    if new is None or (isinstance(new, str) and not new.strip()):
        return old, []
    if _entry_empty_or_zero(old) or old == new:
        return copy.deepcopy(new), []
    return old, [path]


def _as_utc(value: Any) -> datetime | None:
    """Return a timezone-aware UTC datetime for DB or JSON timestamp values."""

    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_value(value: Any) -> str:
    """Canonical, bounded representation used for timing comparisons."""

    import json

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _daily_payload_rows(payload: Any, record_key: str = "") -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("daily")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    # Keep compatibility with old single-row exports.
    fields = {"日期", "收益", "总金额", "收入", "总收入", "A店收入", "B店收入", "学生外卖", "A店外卖", "B店外卖", *ENTRY_DETAIL_FIELDS, *ENTRY_CUSTOMER_FIELDS}
    if fields.intersection(payload):
        row = dict(payload)
        if not row.get("日期") and record_key:
            row["日期"] = record_key
        return [row]
    return []


def _detail_value_items(value: Any) -> list[Any]:
    """Decode a detail cell without imposing a new workbook format."""

    import json

    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        text = value.strip()
        try:
            decoded = exact_request_numbers({"detail": json.loads(text)},
                {"detail": json.loads(text, parse_float=Decimal)},
                _number_factory=LegacyMoneyNumber)["detail"]
            if isinstance(decoded, list):
                return decoded
            if isinstance(decoded, dict):
                return [decoded]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        # Each comma/semicolon/newline-delimited token is an independently
        # immutable saved item. This lets an entry-only account append a new
        # item during its category's 12-hour window without changing old ones.
        return [part.strip() for part in re.split(r"[,，;；\n]+", text) if part.strip()]
    return [value]


def _detail_item_base_and_label(item: Any) -> tuple[str, str]:
    """Return a stable-enough identity base and a human-readable item label.

    Current web/desktop payloads serialize detail rows as readable text rather
    than carrying an item id.  Strip the common quantity/unit/amount suffix so
    changing an item's numeric details keeps its original 30-minute clock.
    Structured rows with an explicit id remain fully stable.
    """

    if isinstance(item, dict):
        explicit_id = item.get("id")
        name = ""
        for name_key in ("名称", "name", "食材名称", "佐料名称", "词条名称", "项目"):
            candidate = item.get(name_key)
            if candidate not in (None, ""):
                name = str(candidate).strip()
                if name:
                    break
        unit = str(item.get("单位") or item.get("unit") or "").strip()
        label = name or _json_value(item)
        if explicit_id not in (None, ""):
            return f"id:{explicit_id}", label
        return (f"{name}\x00{unit}" if name else _json_value(item)), label

    text = re.sub(r"\s+", " ", str(item).strip())
    without_note = re.sub(r"\s+备注[:：].*$", "", text).strip()
    # "牛肉 4斤 80" / "牛肉 4 斤 80".
    match = re.match(
        r"^(.*?)\s+[-+]?\d+(?:\.\d+)?\s*[^\d\s,，;；]*\s+[-+]?\d+(?:\.\d+)?$",
        without_note,
    )
    if not match:
        # "牛肉 80".
        match = re.match(r"^(.*?)\s+[-+]?\d+(?:\.\d+)?$", without_note)
    label = (match.group(1) if match else without_note).strip() or text
    return label.casefold(), label


def _detail_snapshot_entries(payload: Any, record_key: str = "") -> dict[str, dict[str, str]]:
    """Map detail-item identities to value/category/label metadata."""

    snapshots: dict[str, dict[str, str]] = {}
    fields = (
        ("食材明细", "food"),
        ("佐料明细", "spice"),
        ("其他明细", "other"),
        ("其它明细", "other"),
    )
    for row in _daily_payload_rows(payload, record_key):
        day = str(row.get("日期") or record_key or "").strip()
        for field, category in fields:
            if field not in row:
                continue
            occurrence: dict[str, int] = {}
            for item in _detail_value_items(row.get(field)):
                base, label = _detail_item_base_and_label(item)
                serialized = _json_value(detail_for_comparison(item))
                ordinal = occurrence.get(base, 0)
                occurrence[base] = ordinal + 1
                identity = f"{day}|{category}|{base}|{ordinal}"
                snapshots[identity] = {
                    "value": serialized,
                    "category": category,
                    "label": label,
                }
        # Cost-only legacy rows obey the same immutable-item policy. Zero and
        # blank remain an empty slot whose first real value is an addition.
        for category, (detail_fields, cost_fields) in ENTRY_DETAIL_CATEGORIES.items():
            if any(_detail_value_items(row.get(name)) for name in detail_fields):
                continue
            raw = next((row.get(name) for name in cost_fields if row.get(name) not in (None, "")), None)
            try:
                numeric = money(raw or 0)
            except (TypeError, ValueError):
                numeric = ZERO
            if abs(numeric) > 1e-9:
                snapshots[f"{day}|{category}|__cost__|0"] = {
                    "value": _json_value(money_text(numeric)),
                    "category": category,
                    "label": f"{ {'food': '食材', 'spice': '佐料', 'other': '其它'}[category] }金额",
                }
    return snapshots


def _detail_snapshots(payload: Any, record_key: str = "") -> dict[str, str]:
    """Map stable detail-item identities to their saved values."""

    return {
        key: item["value"]
        for key, item in _detail_snapshot_entries(payload, record_key).items()
    }


def _entry_value_present(value: Any) -> bool:
    """Blank means unrecorded; numeric zero is a successfully saved value."""

    return not (value is None or (isinstance(value, str) and not value.strip()))


def _entry_income_value(value: Any) -> str:
    if isinstance(value, bool):
        return _json_value(value)
    try:
        return _json_value(money_text(value))
    except (TypeError, ValueError):
        return _json_value(str(value).strip())


def _income_field_snapshots(payload: Any, record_key: str = "") -> dict[str, dict[str, Any]]:
    """Return presence/value state for each user-facing income slot."""

    result: dict[str, dict[str, Any]] = {}
    for row in _daily_payload_rows(payload, record_key):
        day = str(row.get("日期") or record_key or "").strip()
        for key, (label, field) in ENTRY_INCOME_SLOTS.items():
            value = row.get(field)
            present = field in row and _entry_value_present(value)
            result[f"{day}|{key}"] = {
                "day": day,
                "key": key,
                "label": label,
                "field": field,
                "present": present,
                "value": _entry_income_value(value) if present else None,
            }
    return result


def _audit_display_value(value: Any) -> str:
    import json

    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, str):
                return decoded
            if isinstance(decoded, (int, float)):
                return f"{decoded:g}"
        except (TypeError, ValueError, json.JSONDecodeError):
            return value
    return str(value if value not in (None, "") else "空白")


def _customer_field_snapshots(payload: Any, record_key: str = "") -> dict[str, dict[str, Any]]:
    """Keep the two existing customer inputs independent from income saves."""
    result: dict[str, dict[str, Any]] = {}
    for row in _daily_payload_rows(payload, record_key):
        day = str(row.get("日期") or record_key or "").strip()
        for key, (label, field) in ENTRY_CUSTOMER_SLOTS.items():
            value = row.get(field)
            present = _entry_value_present(value)
            result[f"{day}|{key}"] = {
                "day": day, "key": key, "label": label, "field": field,
                "present": present,
                "value": format(decimal_value(value), ".1f") if present else None,
            }
    return result


def _customer_clock_updates(
    field_times: dict[str, str], old_payload: Any, new_payload: Any,
    record_key: str, fallback: datetime, now: datetime, *, enforce: bool,
) -> dict[str, str]:
    """Pin existing first-save clocks even when another field is being edited."""
    field_times = dict(field_times)
    old_customers = _customer_field_snapshots(old_payload, record_key)
    new_customers = _customer_field_snapshots(new_payload, record_key)
    for identity in set(old_customers) | set(new_customers):
        old_item = old_customers.get(identity) or {}
        new_item = new_customers.get(identity) or {}
        item = new_item or old_item
        clock_key = f"customer:{item['key']}"
        saved_at = _as_utc(field_times.get(clock_key))
        if saved_at is None and old_item.get("present") and old_item.get("value") != "0.0":
            saved_at = fallback
        changed = (old_item.get("present"), old_item.get("value")) != (new_item.get("present"), new_item.get("value"))
        if changed and enforce and saved_at is not None and now >= saved_at + ENTRY_EDIT_WINDOW:
            raise HTTPException(status_code=403, detail=f"{item['label']}人数只能在首次保存后 30 分钟内修改或清空。")
        if saved_at is None and new_item.get("present") and (changed or new_item.get("value") != "0.0"):
            saved_at = now
        if saved_at is not None:
            field_times[clock_key] = saved_at.isoformat()
    return field_times


def _normalize_customer_counts(payload: dict[str, Any], record_key: str) -> dict[str, Any]:
    """Validate new/total counts without filling untouched inputs with zero."""
    import copy
    import math

    result = copy.deepcopy(payload)
    rows = _daily_payload_rows(result, record_key)
    for row in rows:
        for field in ENTRY_CUSTOMER_FIELDS:
            if field not in row or not _entry_value_present(row[field]):
                continue
            try:
                value = float(row[field])
            except (TypeError, ValueError):
                value = float("nan")
            if isinstance(row[field], bool) or not math.isfinite(value) or value < 0 or not value.is_integer():
                raise HTTPException(status_code=422, detail=f"{field}必须是大于或等于 0 的整数。")
            row[field] = int(value)
        if (all(_entry_value_present(row.get(field)) for field in ENTRY_CUSTOMER_FIELDS)
            and row["新客人数量"] > row["总客人数"]):
            raise HTTPException(status_code=422, detail="总客人数不能少于新客人数。")
    if isinstance(result.get("daily"), list):
        result["daily"] = rows
    elif rows:
        result = rows[0]
    return result


def _audit_field_label(path: list[str]) -> str:
    """Make a compact Chinese label for a JSON field path in an audit row."""

    labels = {
        "daily": "当日账本", "dishes": "今日做出的菜品", "monthly_fixed": "固定成本",
        "entries": "入库", "adjustments": "库存调整", "overrides": "库存覆盖",
        "transactions": "现金流水", "opening_balance": "期初现金余额",
        "opening_date": "余额基准日期", "shareholder_loan": "向股东借款",
        "name": "名称", "名称": "名称", "date": "日期", "日期": "日期",
        "amount": "金额", "金额": "金额", "quantity": "数量", "数量": "数量",
        "unit": "单位", "单位": "单位", "total": "总价", "总价": "总价",
        "note": "备注", "备注": "备注", "成本": "成本", "总成本": "总成本",
        "菜品名称": "菜品名称", "菜品份数": "菜品份数", "食材明细": "食材明细",
        "佐料明细": "佐料明细", "其他明细": "其它明细", "其它明细": "其它明细",
        "食材成本": "食材成本", "佐料成本": "佐料成本", "水电": "水电",
        "其他": "其它", "收益": "总收入", "总金额": "总收入",
    }
    useful = [labels.get(part, part) for part in path if part and not part.isdigit()]
    return " · ".join(useful[-3:]) or "账本内容"


def _audit_list_identity(item: Any, index: int) -> str:
    """Use a business identity for arrays so an audit says what changed."""

    if isinstance(item, dict):
        for key in ("id", "日期", "date", "月份", "month", "name", "名称", "菜品名称"):
            value = item.get(key)
            if value not in (None, ""):
                return f"{key}:{value}"
    return f"#{index}"


def _audit_generic_changes(before: Any, after: Any, record_key: str = "") -> list[str]:
    """Describe all remaining JSON changes instead of hiding them behind a fallback.

    The specialised rules above deliberately make common ledger edits terse.
    This generic walker is the safety net for every other record type (dish,
    inventory, fixed costs and future fields).  It is bounded so one import
    cannot create an unusable audit row.
    """

    ignored = {"updated_at", "created_at", "checksum", "version", "sequence"}
    changes: list[str] = []

    def add(text: str) -> None:
        if len(changes) < 30:
            changes.append(text)

    def walk(old: Any, new: Any, path: list[str]) -> None:
        if len(changes) >= 30:
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new), key=str):
                if str(key) in ignored:
                    continue
                old_has, new_has = key in old, key in new
                child_path = [*path, str(key)]
                if not old_has:
                    add(f"增加 {_audit_field_label(child_path)} {_audit_display_value(new.get(key))}")
                elif not new_has:
                    add(f"删除 {_audit_field_label(child_path)} {_audit_display_value(old.get(key))}")
                else:
                    walk(old.get(key), new.get(key), child_path)
            return
        if isinstance(old, list) and isinstance(new, list):
            old_map = {_audit_list_identity(item, index): item for index, item in enumerate(old)}
            new_map = {_audit_list_identity(item, index): item for index, item in enumerate(new)}
            for key in sorted(set(old_map) | set(new_map)):
                child_path = [*path, key]
                if key not in old_map:
                    add(f"增加 {_audit_field_label(child_path)} {_audit_display_value(new_map[key])}")
                elif key not in new_map:
                    add(f"删除 {_audit_field_label(child_path)} {_audit_display_value(old_map[key])}")
                else:
                    walk(old_map[key], new_map[key], child_path)
            return
        if old != new:
            label = _audit_field_label(path or [record_key or "账本内容"])
            if old in (None, ""):
                add(f"增加 {label} {_audit_display_value(new)}")
            elif new in (None, ""):
                add(f"清空 {label} {_audit_display_value(old)} → 空白")
            else:
                add(f"修改 {label} {_audit_display_value(old)} → {_audit_display_value(new)}")

    walk(before, after, [])
    return changes


def _audit_change_summary(before: Any, after: Any, record_key: str = "") -> str:
    """Create a concrete, human-readable before/after description."""

    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    changes: list[str] = []
    categories = {"food": "食材", "spice": "佐料", "other": "其它"}
    old_details = _detail_snapshot_entries(before, record_key)
    new_details = _detail_snapshot_entries(after, record_key)
    for key in sorted(set(old_details) | set(new_details)):
        old, new = old_details.get(key), new_details.get(key)
        category = categories.get((new or old or {}).get("category", ""), "明细")
        if old is None and new is not None:
            changes.append(f"增加 {category} {_audit_display_value(new.get('value'))}")
        elif new is None and old is not None:
            changes.append(f"删除 {category} {_audit_display_value(old.get('value'))}")
        elif old and new and old.get("value") != new.get("value"):
            changes.append(
                f"修改 {category} {_audit_display_value(old.get('value'))} → {_audit_display_value(new.get('value'))}"
            )
    old_income = _income_field_snapshots(before, record_key)
    new_income = _income_field_snapshots(after, record_key)
    for key in sorted(set(old_income) | set(new_income)):
        old, new = old_income.get(key), new_income.get(key)
        old_present, new_present = bool(old and old.get("present")), bool(new and new.get("present"))
        if not old_present and not new_present:
            continue
        label = str((new or old or {}).get("label") or "收入")
        old_value = _audit_display_value(old.get("value")) if old_present and old else "空白"
        new_value = _audit_display_value(new.get("value")) if new_present and new else "空白"
        if old_value != new_value:
            verb = "增加" if not old_present else ("清空" if not new_present else "修改")
            changes.append(f"{verb} {label} {new_value}" if verb == "增加" else f"{verb} {label} {old_value} → {new_value}")
    old_transactions = before.get("transactions", []) if isinstance(before.get("transactions"), list) else []
    new_transactions = after.get("transactions", []) if isinstance(after.get("transactions"), list) else []
    old_ids = {str(item.get("id") or _json_value(item)): item for item in old_transactions if isinstance(item, dict)}
    new_ids = {str(item.get("id") or _json_value(item)): item for item in new_transactions if isinstance(item, dict)}
    for key in sorted(set(new_ids) - set(old_ids)):
        item = new_ids[key]
        changes.append(f"增加 {item.get('type') or '现金项目'} {_money_value(item.get('amount')):,.2f} 元")
    # Never hide a real mutation behind a vague "账本内容已更新" message.
    # The specialised entries remain first; generic fields explain anything
    # they did not cover, such as dish recipes, fixed costs or inventory rows.
    if before != after:
        generic = _audit_generic_changes(before, after, record_key)
        if changes:
            known_terms = ("食材明细", "佐料明细", "其它明细", "A店", "B店", "学生外卖", "现金流水")
            generic = [item for item in generic if not any(term in item for term in known_terms)]
        changes.extend(generic)
    return "；".join(changes[:20]) or "没有实际数据变化"


def _store_snapshots(payload: Any, record_key: str = "") -> dict[str, str]:
    """Return independent A/B projections for income-window enforcement."""

    result: dict[str, str] = {}
    for row in _daily_payload_rows(payload, record_key):
        day = str(row.get("日期") or record_key or "").strip()
        for slot, fields in STORE_FIELD_GROUPS.items():
            values: dict[str, Any] = {}
            for field in fields:
                if field not in row:
                    continue
                value = row.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    values[field] = None
                else:
                    try:
                        values[field] = money_text(value)
                    except (TypeError, ValueError):
                        values[field] = str(value)
            # Empty hidden inputs are emitted by older web clients alongside a
            # total-only 收益 value.  They do not constitute a store split and
            # must not suppress the total-income clock below.
            if values and any(value is not None for value in values.values()):
                result[f"{day}|{slot}"] = _json_value(values)
    return result


def _revenue_snapshots(payload: Any, record_key: str = "") -> dict[str, str]:
    """Return total-only revenue projections keyed by business day.

    Newer rows also carry A/B projections, so callers use this map only when a
    row has no store split.  Keeping it separate prevents the derived ``收益``
    field from accidentally sharing (or extending) an A/B edit clock.
    """

    result: dict[str, str] = {}
    for row in _daily_payload_rows(payload, record_key):
        day = str(row.get("日期") or record_key or "").strip()
        values = {field: row.get(field) for field in REVENUE_FIELDS if field in row}
        if values and any(value not in (None, "") for value in values.values()):
            result[day] = _json_value(values)
    return result


def _record_day(record_key: str, payload: Any = None) -> date | None:
    candidates = [record_key]
    for row in _daily_payload_rows(payload, record_key):
        candidates.insert(0, row.get("日期"))
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        try:
            return date.fromisoformat(text[:10].replace("/", "-"))
        except ValueError:
            continue
    return None


def _effective_record_role(
    db: Session,
    user: AppUser,
    dataset_id: str,
    record_type: str,
    record_key: str,
    payload: Any = None,
    *,
    now: datetime | None = None,
) -> str:
    """Return permanent or scheduled permission for this exact business date."""

    if user.role in {"admin", "editor"}:
        return user.role
    business_day = _record_day(record_key, payload) if record_type == "day" else None
    rank = {"viewer": 0, "entry": 1, "editor": 2, "admin": 3}
    best = user.role if user.role in rank else "viewer"
    if business_day is None:
        return best
    day_text = business_day.isoformat()
    for grant in active_temporary_permissions(db, user.id, now=now):
        if grant.dataset_id != dataset_id:
            continue
        if not (grant.business_start_date <= day_text <= grant.business_end_date):
            continue
        if grant.permission_role in {"entry", "editor"} and rank[grant.permission_role] > rank[best]:
            best = grant.permission_role
    return best


def _entry_revenue_deadline(record_key: str, payload: Any, now: datetime) -> datetime | None:
    day = _record_day(record_key, payload)
    if day is None:
        return None
    # A still-empty income slot may be entered until 11:00 on the following
    # business-calendar day.  A slot first saved at 10:59 keeps its own full
    # 30-minute correction window after that hard first-entry cutoff.
    local_tz = _business_timezone()
    local_deadline = datetime.combine(
        day + timedelta(days=1), datetime.min.time(), tzinfo=local_tz
    ).replace(hour=ENTRY_REVENUE_CUTOFF_HOUR)
    return local_deadline.astimezone(timezone.utc)


def _business_timezone() -> timezone | ZoneInfo:
    """Return the configured business timezone used for calendar cutoffs.

    Database timestamps are stored in UTC, but day-based product rules (cash
    flow inclusion and the next-day 11:00 revenue cutoff) follow the operator's
    local business day.  Keep the fallback deterministic when an invalid
    deployment setting is supplied.
    """

    timezone_name = os.environ.get("BUSINESS_TIMEZONE", config.WECHAT_TIMEZONE)
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return timezone.utc


def _timing_fallback(record: SyncRecord | None, now: datetime) -> datetime:
    if record is not None:
        value = _as_utc(record.updated_at) or _as_utc(record.created_at)
        if value is not None:
            return value
    return now


def _timing_row(
    db: Session, dataset_id: str, record_type: str, record_key: str
) -> EntryTiming | None:
    return db.scalar(
        select(EntryTiming).where(
            EntryTiming.dataset_id == dataset_id,
            EntryTiming.record_type == record_type,
            EntryTiming.record_key == record_key,
        ).with_for_update()
    )


def _protected_entry_path(path: str) -> bool:
    return any(
        f".{field}" in path or path.endswith(field)
        for field in (
            *ENTRY_DETAIL_FIELDS, "食材成本", "佐料成本", "其他", "其它",
            *STORE_FIELD_GROUPS["A"], *STORE_FIELD_GROUPS["B"], "学生外卖",
            *ENTRY_DERIVED_REVENUE_FIELDS, *ENTRY_CUSTOMER_FIELDS,
        )
    )


def _entry_timing_updates(
    db: Session,
    *,
    record: SyncRecord | None,
    dataset_id: str,
    record_type: str,
    record_key: str,
    old_payload: dict[str, Any],
    new_payload: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Validate an entry-role write and return its payload plus timing updates.

    The returned update dictionary is deliberately separate from the SQLAlchemy
    object.  ``write_record`` first checks for a no-op and only then persists the
    timestamps, so refreshing a page cannot extend an edit window.
    """

    import copy

    timing = _timing_row(db, dataset_id, record_type, record_key)
    fallback = _timing_fallback(record, now)
    detail_times: dict[str, str] = dict((timing.detail_item_times or {}) if timing else {})
    field_times: dict[str, str] = dict((timing.detail_field_times or {}) if timing else {})
    detail_started = _as_utc(timing.detail_started_at) if timing else None
    store_a_at = _as_utc(timing.store_a_at) if timing else None
    store_b_at = _as_utc(timing.store_b_at) if timing else None
    revenue_at = _as_utc(timing.revenue_at) if timing else None

    old_details = _detail_snapshots(old_payload, record_key)
    # Freeze legacy first-save anchors before an unrelated write advances the
    # record's updated_at. Decimal formatting must never reopen old clocks.
    for identity in old_details:
        detail_times.setdefault(identity, fallback.isoformat())
    new_details = _detail_snapshots(new_payload, record_key)
    category_names = {"food": "食材", "spice": "佐料", "other": "其它"}
    fresh_detail_additions: dict[str, list[str]] = {}
    old_category_has_items: dict[str, bool] = {}
    for category, label in category_names.items():
        marker = f"|{category}|"
        old_category = {key: value for key, value in old_details.items() if marker in key}
        new_category = {key: value for key, value in new_details.items() if marker in key}
        old_keys, new_keys = set(old_category), set(new_category)
        old_category_has_items[category] = bool(old_keys)
        # Text payloads have no persistent item id. If saved text replaces an
        # existing token (for example correcting its name), carry the old
        # first-save timestamp to the replacement. Otherwise a rename would be
        # misread as delete+add and incorrectly grant a fresh 30-minute clock.
        unmatched_old = [key for key in old_category if key not in new_keys]
        unmatched_new = [key for key in new_category if key not in old_keys]
        for old_key, new_key in zip(unmatched_old, unmatched_new):
            original_at = _as_utc(detail_times.get(old_key)) or fallback
            detail_times.setdefault(old_key, original_at.isoformat())
            detail_times.setdefault(new_key, original_at.isoformat())
        # A saved item keeps its own first-save timestamp.  Modifying or
        # deleting it is allowed for 30 minutes and never renews that clock.
        changed_existing = {
            key for key in old_keys
            if key not in new_category or old_category[key] != new_category.get(key)
        }
        # A previously removed item retains a tombstone timestamp, so deleting
        # and re-adding it cannot manufacture a fresh correction window.
        readded = {
            key for key in (new_keys - old_keys)
            if _as_utc(detail_times.get(key)) is not None
        }
        changed_existing.update(readded)
        for key in changed_existing:
            saved_at = _as_utc(detail_times.get(key)) or fallback
            if now >= saved_at + ENTRY_EDIT_WINDOW:
                raise HTTPException(
                    status_code=403,
                    detail=f"{label}项目只能在各自首次保存后 30 分钟内修改或删除。",
                )
            detail_times.setdefault(key, saved_at.isoformat())
        fresh_detail_additions[category] = [
            key for key in (new_keys - old_keys) if key not in readded
        ]

    # Food, seasoning and other each own a separate twelve-hour addition
    # window. Saving food must not start or shorten the seasoning clock.
    category_starts: list[datetime] = []
    for category, label in category_names.items():
        started = _as_utc(field_times.get(category))
        # Sep01V1 stored only one legacy timestamp. Apply it solely to a
        # category which already contained data, leaving untouched categories
        # genuinely unstarted.
        if started is None and old_category_has_items.get(category):
            started = detail_started or fallback
        additions = fresh_detail_additions.get(category) or []
        if additions:
            if started is not None and now >= started + ENTRY_DETAIL_WINDOW:
                raise HTTPException(
                    status_code=403,
                    detail=f"当日{label}新增窗口已截止（该分类首条明细保存后 12 小时）。",
                )
            if started is None:
                started = now
            for key in additions:
                detail_times[key] = now.isoformat()
        if started is not None:
            field_times[category] = started.isoformat()
            category_starts.append(started)
    detail_started = min(category_starts, default=detail_started)

    # Each of the nine visible income inputs has an independent first-save
    # timestamp.  Blank and missing are unrecorded; numeric zero is recorded.
    old_income = _income_field_snapshots(old_payload, record_key)
    new_income = _income_field_snapshots(new_payload, record_key)
    for identity in set(old_income) | set(new_income):
        old_item = old_income.get(identity)
        new_item = new_income.get(identity)
        template = old_item or new_item or {}
        key = str(template.get("key") or identity.rsplit("|", 1)[-1])
        label = str(template.get("label") or ENTRY_INCOME_SLOTS.get(key, (key, ""))[0])
        day = str(template.get("day") or identity.rsplit("|", 1)[0])
        old_present = bool(old_item and old_item.get("present"))
        new_present = bool(new_item and new_item.get("present"))
        old_value = old_item.get("value") if old_present and old_item else None
        new_value = new_item.get("value") if new_present and new_item else None
        clock_key = f"income:{key}"
        saved_at = _as_utc(field_times.get(clock_key))
        if saved_at is None and old_present:
            if key.startswith("a_"):
                saved_at = store_a_at or fallback
            elif key.startswith("b_"):
                saved_at = store_b_at or fallback
            else:
                saved_at = revenue_at or fallback
            field_times[clock_key] = saved_at.isoformat()

        if old_present == new_present and old_value == new_value:
            continue
        if saved_at is not None:
            if now >= saved_at + ENTRY_EDIT_WINDOW:
                raise HTTPException(
                    status_code=403,
                    detail=f"{label}只能在首次保存后 30 分钟内修改或清空。",
                )
        elif new_present:
            deadline = _entry_revenue_deadline(day, {}, now)
            if deadline is not None and now >= deadline:
                raise HTTPException(
                    status_code=403,
                    detail=f"{label}未录入时最晚须在第二天 11:00 前首次保存。",
                )
            saved_at = now
            field_times[clock_key] = saved_at.isoformat()

    field_times = _customer_clock_updates(
        field_times, old_payload, new_payload, record_key, fallback, now, enforce=True
    )

    a_income_times = [
        _as_utc(field_times.get(f"income:{key}"))
        for key in ("a_wechat", "a_alipay", "a_cash", "a_takeout")
    ]
    b_income_times = [
        _as_utc(field_times.get(f"income:{key}"))
        for key in ("b_wechat", "b_alipay", "b_cash", "b_takeout")
    ]
    a_income_times = [value for value in a_income_times if value is not None]
    b_income_times = [value for value in b_income_times if value is not None]
    if a_income_times:
        store_a_at = min(a_income_times)
    if b_income_times:
        store_b_at = min(b_income_times)

    # Older clients can submit only 收益/总金额.  Apply the same next-day
    # cutoff and fixed 30-minute window to that representation, while avoiding
    # a second clock for a derived total sent alongside any of the nine inputs.
    old_revenues = _revenue_snapshots(old_payload, record_key)
    new_revenues = _revenue_snapshots(new_payload, record_key)
    if old_revenues and revenue_at is None:
        revenue_at = fallback
    income_days = {
        str(item.get("day") or "")
        for item in [*old_income.values(), *new_income.values()]
        if item.get("present")
    }
    for identity in set(old_revenues) | set(new_revenues):
        if identity in income_days or old_revenues.get(identity) == new_revenues.get(identity):
            continue
        old_value_exists = old_revenues.get(identity) is not None
        if old_value_exists:
            old_at = revenue_at or fallback
            if now >= old_at + ENTRY_EDIT_WINDOW:
                raise HTTPException(status_code=403, detail="总收入只能在保存后 30 分钟内修改。")
            if revenue_at is None:
                revenue_at = old_at
        elif new_revenues.get(identity) is not None:
            deadline = _entry_revenue_deadline(identity, new_payload, now)
            if deadline is not None and now >= deadline:
                raise HTTPException(
                    status_code=403,
                    detail="当日总收入未录入时最晚须在第二天 11:00 前首次保存。",
                )
            if revenue_at is None:
                revenue_at = now

    write_payload: dict[str, Any] = copy.deepcopy(new_payload or {})

    # Keep the historical entry-role behaviour for non-detail fields after the
    # record-level 30-minute window, while allowing the per-item rules above to
    # decide detail/store fields.  Blank cells remain non-destructive.
    if record is not None and not record.is_deleted:
        record_at = _as_utc(record.updated_at) or _as_utc(record.created_at) or fallback
        if now - record_at >= ENTRY_EDIT_WINDOW:
            merged, violations = _entry_merge_payload(old_payload or {}, write_payload)
            blocked = [path for path in violations if not _protected_entry_path(path)]
            if blocked:
                fields = ", ".join(blocked[:8])
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "录入权限仅可继续填写空白或 0 字段；以下已有数据已超过 30 分钟，"
                        f"不能修改：{fields}"
                    ),
                )
            # _entry_merge_payload intentionally preserves protected values when
            # they differ.  Overlay the values after timing validation so a
            # legitimate within-window edit is not lost.
            if isinstance(merged, dict) and isinstance(write_payload, dict):
                merged_daily = _daily_payload_rows(merged, record_key)
                incoming_daily = _daily_payload_rows(write_payload, record_key)
                if merged_daily and incoming_daily:
                    by_day = {
                        str(row.get("日期") or record_key): row for row in incoming_daily
                    }
                    for row in merged_daily:
                        incoming = by_day.get(str(row.get("日期") or record_key))
                        if not incoming:
                            continue
                        for field in (
                            *ENTRY_DETAIL_FIELDS, "食材成本", "佐料成本", "其他", "其它",
                            *STORE_FIELD_GROUPS["A"], *STORE_FIELD_GROUPS["B"], "学生外卖",
                            *ENTRY_DERIVED_REVENUE_FIELDS, *ENTRY_CUSTOMER_FIELDS,
                        ):
                            if field in incoming:
                                row[field] = copy.deepcopy(incoming[field])
                    if isinstance(merged.get("daily"), list):
                        merged["daily"] = merged_daily
                write_payload = merged

    update = {
        "detail_started_at": detail_started,
        "detail_item_times": detail_times,
        "detail_field_times": field_times,
        "store_a_at": store_a_at,
        "store_b_at": store_b_at,
        "revenue_at": revenue_at,
    }
    return write_payload, update


def _persist_entry_timing(
    db: Session,
    *,
    dataset_id: str,
    record_type: str,
    record_key: str,
    update: dict[str, Any],
) -> EntryTiming:
    timing = _timing_row(db, dataset_id, record_type, record_key)
    if timing is None:
        timing = EntryTiming(
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
        )
        db.add(timing)
    timing.detail_started_at = update.get("detail_started_at")
    timing.detail_item_times = dict(update.get("detail_item_times") or {})
    timing.detail_field_times = dict(update.get("detail_field_times") or {})
    timing.store_a_at = update.get("store_a_at")
    timing.store_b_at = update.get("store_b_at")
    timing.revenue_at = update.get("revenue_at")
    return timing


def ensure_admin(db: Session) -> None:
    user = db.scalar(select(AppUser).where(AppUser.username == config.ADMIN_USERNAME))
    if user:
        return
    db.add(
        AppUser(
            username=config.ADMIN_USERNAME,
            display_name="管理员",
            role="admin",
            password_hash=hash_password(config.ADMIN_PASSWORD),
        )
    )
    db.commit()


def set_user_dataset_memberships(
    db: Session,
    user: AppUser,
    dataset_ids: list[str],
    default_dataset_id: str | None,
) -> None:
    cleaned: list[str] = []
    for value in dataset_ids:
        dataset_id = str(value or "").strip()
        if dataset_id and dataset_id not in cleaned:
            cleaned.append(dataset_id)
    if default_dataset_id:
        default_dataset_id = str(default_dataset_id).strip()
        if default_dataset_id not in cleaned:
            raise HTTPException(status_code=422, detail="默认账本必须包含在 dataset_ids 中。")
    elif cleaned:
        default_dataset_id = cleaned[0]

    if user.role != "admin" and not cleaned:
        raise HTTPException(status_code=422, detail="普通账号至少要绑定一套账本。")
    if user.username.casefold() == config.TEST_USERNAME.casefold():
        if cleaned != [config.TEST_DATASET_ID]:
            raise HTTPException(status_code=422, detail="Test 账号只能绑定 Test 独立账本。")

    for dataset_id in cleaned:
        if db.get(Dataset, dataset_id) is None:
            raise HTTPException(status_code=422, detail=f"账本不存在：{dataset_id}。")

    db.execute(
        delete(UserDatasetMembership).where(UserDatasetMembership.user_id == user.id)
    )
    db.flush()
    for dataset_id in cleaned:
        db.add(
            UserDatasetMembership(
                user_id=user.id,
                dataset_id=dataset_id,
                is_default=dataset_id == default_dataset_id,
            )
        )


def bind_legacy_users_if_unambiguous(db: Session) -> None:
    """Preserve single-ledger deployments when the membership table is first added."""
    datasets = list(
        db.scalars(
            select(Dataset)
            .where(Dataset.id != config.TEST_DATASET_ID)
            .order_by(Dataset.created_at)
        ).all()
    )
    if len(datasets) != 1:
        return
    dataset_id = datasets[0].id
    users = db.scalars(select(AppUser).where(AppUser.role != "admin")).all()
    changed = False
    for user in users:
        if user.username.casefold() == config.TEST_USERNAME.casefold():
            continue
        exists = db.scalar(
            select(UserDatasetMembership.id).where(
                UserDatasetMembership.user_id == user.id
            )
        )
        if exists:
            continue
        db.add(
            UserDatasetMembership(
                user_id=user.id, dataset_id=dataset_id, is_default=True
            )
        )
        changed = True
    if changed:
        db.commit()


def ensure_test_account(db: Session) -> None:
    if not config.TEST_LOGIN_ENABLED:
        return
    dataset = db.get(Dataset, config.TEST_DATASET_ID)
    if dataset is None:
        dataset = Dataset(
            id=config.TEST_DATASET_ID,
            name="Test 独立演示账本",
            schema_version=2,
        )
        db.add(dataset)
        db.flush()

    user = db.scalar(
        select(AppUser).where(func.lower(AppUser.username) == config.TEST_USERNAME.lower())
    )
    if user is None:
        user = AppUser(
            username=config.TEST_USERNAME,
            display_name="Test 演示账户",
            role="viewer",
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.flush()
    else:
        user.role = "viewer"
        user.is_active = True

    db.execute(
        delete(UserDatasetMembership).where(UserDatasetMembership.user_id == user.id)
    )
    db.flush()
    db.add(
        UserDatasetMembership(
            user_id=user.id,
            dataset_id=config.TEST_DATASET_ID,
            is_default=True,
        )
    )
    db.commit()


def next_sequence(db: Session, dataset_id: str) -> int:
    current = db.scalar(select(func.max(SyncRecord.sequence)).where(SyncRecord.dataset_id == dataset_id))
    audit_current = db.scalar(select(func.max(AuditLog.sequence)).where(AuditLog.dataset_id == dataset_id))
    return int(max(current or 0, audit_current or 0)) + 1


def get_dataset_or_404(
    db: Session, dataset_id: str, *, for_update: bool = False
) -> Dataset:
    if for_update:
        dataset = db.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
    else:
        dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在。")
    return dataset


def authorized_dataset(
    db: Session,
    user: AppUser,
    dataset_id: str,
    *,
    write: bool = False,
    for_update: bool = False,
) -> Dataset:
    dataset = get_dataset_or_404(db, dataset_id, for_update=for_update)
    if user.role == "admin":
        return dataset
    membership = db.scalar(
        select(UserDatasetMembership).where(
            UserDatasetMembership.user_id == user.id,
            UserDatasetMembership.dataset_id == dataset_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="当前账号无权访问这套账本。")
    if write and user.role not in {"admin", "editor", "entry"}:
        raise HTTPException(status_code=403, detail="当前账号只读，不能修改账本。")
    return dataset


def get_record(db: Session, dataset_id: str, record_type: str, record_key: str) -> SyncRecord | None:
    return db.scalar(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == record_type,
            SyncRecord.record_key == record_key,
        )
    )


def add_audit(
    db: Session,
    *,
    user: AppUser,
    dataset_id: str,
    record_type: str,
    record_key: str,
    action: str,
    source: str,
    event_id: str,
    device_id: str,
    from_version: int,
    to_version: int,
    sequence: int,
    before_payload: dict[str, Any] | None,
    after_payload: dict[str, Any] | None,
    checksum: str,
    occurred_at: datetime | None,
) -> None:
    # Every writer, including an administrator, must be traceable in the
    # change log. Administrators may delete audit rows, but their own changes
    # are not exempt from being recorded.
    db.add(
        AuditLog(
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
            action=action,
            source=source,
            event_id=event_id,
            actor_user_id=user.id,
            actor_username=user.username,
            device_id=device_id,
            from_version=from_version,
            to_version=to_version,
            sequence=sequence,
            before_payload=before_payload,
            after_payload=after_payload,
            checksum=checksum,
            occurred_at=occurred_at or utcnow(),
        )
    )


def apply_workbook_records(
    db: Session,
    *,
    dataset_id: str,
    parsed: ParsedWorkbook,
    replace: bool,
    merge: bool = False,
    replace_user_year: int | None = None,
    preserve_internal_fixed_flags: bool = False,
    user: AppUser,
    source: str,
) -> dict[str, int]:
    existing_rows = list(
        db.scalars(select(SyncRecord).where(SyncRecord.dataset_id == dataset_id)).all()
    )
    existing = {(item.record_type, item.record_key): item for item in existing_rows}
    incoming = {
        (item.record_type, item.record_key): item for item in parsed.records
    }
    sequence = next_sequence(db, dataset_id)
    event_id = f"workbook-{uuid4()}"
    counts = {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0}

    for identity in sorted(incoming):
        item = incoming[identity]
        record = existing.get(identity)
        payload = (
            merge_user_record_payload(
                record.payload if record is not None and not record.is_deleted else None,
                item.payload,
                record_type=item.record_type,
            )
            if merge
            else item.payload
        )
        if preserve_internal_fixed_flags:
            payload = preserve_internal_fixed_expense_flags(
                record.payload if record is not None and not record.is_deleted else None,
                payload,
            )
        else:
            payload = normalize_fixed_expense_cash_flags(payload)
        payload = normalize_payload(payload, record.payload if record else None)
        if item.record_type == "global" and item.record_key == "inventory":
            # Explicit administrator workbook restore can replace historical
            # documents. Validate V2 fields while preserving old source data.
            validate_inventory(payload, record.payload if record else None,
                               today=utcnow().astimezone(_business_timezone()).date().isoformat(),
                               restoration=True)
        if item.record_type == "global" and item.record_key in {"cash_position", "cash_balance"}:
            payload = _canonical_cash_payload(
                payload,
                previous_payload=(
                    record.payload if record is not None and not record.is_deleted else None
                ),
                strict_types=False,
            )
            _protect_locked_cash_forces(
                record.payload if record is not None and not record.is_deleted else None,
                payload,
            )
        checksum = payload_checksum(payload)
        if (
            record is not None
            and not record.is_deleted
            and record.payload == payload
            and record.checksum == checksum
        ):
            counts["unchanged"] += 1
            continue

        before_payload = record.payload if record is not None else None
        before_version = record.version if record is not None else 0
        if record is None:
            record = SyncRecord(
                dataset_id=dataset_id,
                record_type=item.record_type,
                record_key=item.record_key,
                payload=payload,
                checksum=checksum,
                version=1,
                sequence=sequence,
                is_deleted=False,
            )
            db.add(record)
            action = "create"
            counts["created"] += 1
        else:
            action = "restore" if record.is_deleted else "update"
            record.payload = payload
            record.checksum = checksum
            record.version += 1
            record.sequence = sequence
            record.is_deleted = False
            counts["updated"] += 1
        add_audit(
            db,
            user=user,
            dataset_id=dataset_id,
            record_type=item.record_type,
            record_key=item.record_key,
            action=action,
            source=source,
            event_id=event_id,
            device_id="",
            from_version=before_version,
            to_version=record.version,
            sequence=sequence,
            before_payload=before_payload,
            after_payload=payload,
            checksum=checksum,
            occurred_at=utcnow(),
        )
        sequence += 1

    replacement_prefix = (
        f"{int(replace_user_year):04d}-" if replace_user_year is not None else None
    )
    if replace or replacement_prefix is not None:
        for identity, record in sorted(existing.items()):
            in_user_replacement_scope = bool(
                replacement_prefix is not None
                and (
                    (
                        record.record_type in {"day", "month"}
                        and record.record_key.startswith(replacement_prefix)
                    )
                    or (
                        record.record_type == "global"
                        and record.record_key in {"ingredients", "fixed_categories"}
                    )
                )
            )
            if (
                identity in incoming
                or record.is_deleted
                or record.record_type not in {"day", "month", "global"}
                or (not replace and not in_user_replacement_scope)
            ):
                continue
            if (
                record.record_type == "global"
                and record.record_key in {"cash_position", "cash_balance"}
            ):
                _protect_locked_cash_forces(record.payload, None)
            before_payload = record.payload
            before_version = record.version
            record.is_deleted = True
            record.version += 1
            record.sequence = sequence
            add_audit(
                db,
                user=user,
                dataset_id=dataset_id,
                record_type=record.record_type,
                record_key=record.record_key,
                action="delete",
                source=source,
                event_id=event_id,
                device_id="",
                from_version=before_version,
                to_version=record.version,
                sequence=sequence,
                before_payload=before_payload,
                after_payload=None,
                checksum=record.checksum,
                occurred_at=utcnow(),
            )
            sequence += 1
            counts["deleted"] += 1

    db.commit()
    return counts


def read_workbook_upload(file: UploadFile) -> bytes:
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="只接受 .xlsx 文件，不接受 .xls/.xlsm。")
    try:
        content = file.file.read(config.MAX_WORKBOOK_UPLOAD_BYTES + 1)
    finally:
        file.file.close()
    if not content:
        raise HTTPException(status_code=422, detail="上传的 Excel 文件为空。")
    if len(content) > config.MAX_WORKBOOK_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Excel 文件超过 25 MB 上限。")
    return content


def workbook_response(content: bytes, *, filename: str, fallback: str) -> Response:
    clean_name = "".join(
        character for character in filename if ord(character) >= 32 and character not in {'"', "\\", "/"}
    )[:180]
    encoded = quote(clean_name or fallback, safe="")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


_WECHAT_SCHEDULER_STARTED = False
_WECHAT_SCHEDULER_STATE: dict[str, Any] = {
    "last_attempt_at": "",
    "last_success_date": "",
    "last_error": "",
}


def _dataset_store_settings_payload(db: Session, dataset_id: str) -> dict[str, Any]:
    record = get_record(db, dataset_id, "global", "store_settings")
    payload = record.payload if record and not record.is_deleted and isinstance(record.payload, dict) else {}
    settings = payload.get("store_settings") if isinstance(payload.get("store_settings"), dict) else {}
    return {
        "store_a_name": str(settings.get("store_a_name") or "A店").strip() or "A店",
        "store_b_name": str(settings.get("store_b_name") or "B店").strip() or "B店",
        "wechat_auto_sync": bool(settings.get("wechat_auto_sync", True)),
    }


def _write_store_settings_payload(
    db: Session, dataset_id: str, body: StoreNamesUpdate, user: AppUser
) -> dict[str, Any]:
    dataset = authorized_dataset(db, user, dataset_id, write=True, for_update=True)
    record = get_record(db, dataset_id, "global", "store_settings")
    before_payload = record.payload if record and not record.is_deleted else None
    before_version = int(record.version if record else 0)
    payload = {"store_settings": {
        "store_a_name": body.store_a_name.strip(),
        "store_b_name": body.store_b_name.strip(),
        "wechat_auto_sync": bool(body.wechat_auto_sync),
    }}
    checksum = payload_checksum(payload)
    sequence = next_sequence(db, dataset_id)
    if record is None:
        record = SyncRecord(
            dataset_id=dataset_id, record_type="global", record_key="store_settings",
            payload=payload, checksum=checksum, version=1, sequence=sequence, is_deleted=False,
        )
        db.add(record)
        action = "create"
    else:
        action = "restore" if record.is_deleted else "update"
        record.payload = payload
        record.checksum = checksum
        record.version += 1
        record.sequence = sequence
        record.is_deleted = False
    add_audit(
        db, user=user, dataset_id=dataset_id, record_type="global", record_key="store_settings",
        action=action, source="store_settings", event_id=f"store-settings-{uuid4()}", device_id="",
        from_version=before_version, to_version=record.version, sequence=sequence,
        before_payload=before_payload, after_payload=payload, checksum=checksum, occurred_at=utcnow(),
    )
    dataset.schema_version = max(3, int(dataset.schema_version or 1))
    db.commit()
    return _dataset_store_settings_payload(db, dataset_id)


def _money_value(value: Any, default: Any = ZERO) -> Decimal:
    """All monetary reads, including legacy JSON numbers, enter Decimal here."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return money(default, limit=None)
    return money(value, limit=None)


def _effective_store_amount(row: dict[str, Any], slot: str) -> tuple[Decimal, bool]:
    """Resolve one store's income from direct or payment-split fields."""

    prefix = f"{slot}店"
    direct_key = f"{prefix}收入"
    payment_keys = (
        f"{prefix}现金",
        f"{prefix}微信增加", f"{prefix}微信自动", f"{prefix}微信覆盖",
        f"{prefix}支付宝增加", f"{prefix}支付宝覆盖", f"{prefix}外卖",
    )
    has_any = any(key in row and row.get(key) not in (None, "") for key in (direct_key, *payment_keys))
    if not has_any:
        return ZERO, False
    if row.get(direct_key) not in (None, ""):
        return _money_value(row.get(direct_key)), True
    cash = _money_value(row.get(f"{prefix}现金"))
    if row.get(f"{prefix}微信覆盖") not in (None, ""):
        wechat = _money_value(row.get(f"{prefix}微信覆盖"))
    else:
        wechat = _money_value(row.get(f"{prefix}微信自动")) + _money_value(row.get(f"{prefix}微信增加"))
    alipay = (
        _money_value(row.get(f"{prefix}支付宝覆盖"))
        if row.get(f"{prefix}支付宝覆盖") not in (None, "")
        else _money_value(row.get(f"{prefix}支付宝增加"))
    )
    return cash + wechat + alipay + _money_value(row.get(f"{prefix}外卖")), True


def _effective_day_revenue(row: dict[str, Any]) -> Decimal:
    a, has_a = _effective_store_amount(row, "A")
    b, has_b = _effective_store_amount(row, "B")
    if has_a or has_b:
        return a + b + _money_value(row.get("学生外卖"))
    for key in ("收益", "总金额", "收入", "总收入"):
        if key in row and row.get(key) not in (None, ""):
            return _money_value(row.get(key))
    if row.get("总现金") not in (None, "") or row.get("总线上") not in (None, ""):
        return _money_value(row.get("总现金")) + _money_value(row.get("总线上"))
    return ZERO


def _fixed_month_amount(row: dict[str, Any]) -> Decimal:
    split = row.get("水费支出") not in (None, "") or row.get("电费支出") not in (None, "")
    water = _money_value(row.get("水费支出")) if split else _money_value(row.get("水电费"))
    electric = _money_value(row.get("电费支出")) if split else ZERO
    return sum(
        (
            _money_value(row.get("人工总额")),
            _money_value(row.get("房租总额")),
            water,
            electric,
            _money_value(row.get("煤气费")),
            _money_value(row.get("其它固定成本")),
        )
    )


def _cash_date(value: Any, *, default: date | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if text:
        try:
            return date.fromisoformat(text[:10].replace("/", "-"))
        except ValueError:
            pass
    if default is not None:
        return default
    return date.min


def _cash_payload_from_record(record: SyncRecord | None) -> dict[str, Any]:
    payload = dict(record.payload or {}) if record and not record.is_deleted and isinstance(record.payload, dict) else {}
    if payload.get("opening_balance") in (None, "") and payload.get("base_balance") not in (None, ""):
        payload["opening_balance"] = payload.get("base_balance")
    if payload.get("opening_date") in (None, "") and payload.get("as_of_date") not in (None, ""):
        payload["opening_date"] = payload.get("as_of_date")
    return payload


def _cash_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是"}
    return bool(value)


def _cash_amount(value: Any, *, allow_zero: bool, message: str) -> str:
    try:
        amount = money(decimal_value(value, blank_zero=False))
    except MoneyError:
        raise HTTPException(status_code=422, detail=message) from None
    if amount < 0 or (not allow_zero and amount == 0):
        raise HTTPException(status_code=422, detail=message)
    return money_text(amount)


def _cash_force_transaction(item: Any) -> bool:
    return isinstance(item, dict) and (
        str(item.get("mode") or "").strip().casefold() == "force"
        or str(item.get("type") or item.get("类型") or "").strip() == CASH_FORCE_TYPE
    )


def _normalise_cash_transactions(
    value: Any,
    *,
    previous_payload: dict[str, Any] | None = None,
    strict_types: bool = True,
) -> list[dict[str, Any]]:
    """Return the one canonical transaction representation used by all writers.

    Legacy transactions without ``mode`` remain ordinary signed deltas.  A
    force transaction stores a target balance, so 0 is a valid amount and its
    amount must never be converted to an absolute delta by a client.
    """

    if value is None:
        rows: list[Any] = []
    elif isinstance(value, list):
        rows = value
    else:
        raise HTTPException(status_code=422, detail="现金明细必须是列表。")

    previous_rows = (
        previous_payload.get("transactions", [])
        if isinstance(previous_payload, dict)
        and isinstance(previous_payload.get("transactions"), list)
        else []
    )
    previous_by_id = {
        str(row.get("id")): row
        for row in previous_rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="现金明细格式不正确。")
        transaction_date = _cash_date(item.get("date", item.get("日期")))
        if transaction_date == date.min:
            raise HTTPException(status_code=422, detail="现金明细必须填写正确日期。")
        transaction_id = str(item.get("id") or uuid4()).strip()
        if transaction_id in seen_ids:
            raise HTTPException(status_code=422, detail="现金明细 id 不能重复。")
        seen_ids.add(transaction_id)
        previous = previous_by_id.get(transaction_id)
        kind = str(item.get("type") or item.get("类型") or "其它现金收入").strip()
        if _cash_force_transaction(item):
            amount = _cash_amount(
                item.get("amount", item.get("金额")),
                allow_zero=True,
                message="余额强制修改必须填写大于或等于 0 的目标余额。",
            )
            raw_created_at = item.get("created_at")
            if raw_created_at in (None, "") and isinstance(previous, dict):
                raw_created_at = previous.get("created_at")
            if raw_created_at in (None, ""):
                created_at = utcnow()
            else:
                created_at = _as_utc(raw_created_at)
                if created_at is None:
                    raise HTTPException(status_code=422, detail="余额强制修改的保存时间格式不正确。")
            raw_locked = item.get("system_locked")
            if raw_locked is None and isinstance(previous, dict):
                raw_locked = previous.get("system_locked", False)
            result.append({
                "id": transaction_id,
                "date": transaction_date.isoformat(),
                "type": CASH_FORCE_TYPE,
                "amount": amount,
                "description": CASH_FORCE_TYPE,
                "mode": "force",
                "system_locked": _cash_bool(raw_locked),
                "created_at": serialize_dt(created_at),
            })
            continue

        if strict_types and kind not in CASH_DELTA_TYPES:
            raise HTTPException(status_code=422, detail=f"不支持的现金明细类型：{kind}。")
        amount = _cash_amount(
            abs(_money_value(item.get("amount", item.get("金额")))),
            allow_zero=False,
            message="现金明细金额必须大于 0。",
        )
        result.append({
            "id": transaction_id,
            "date": transaction_date.isoformat(),
            "type": kind,
            "amount": amount,
            "description": str(item.get("description") or item.get("说明") or kind).strip(),
        })
    return result


def _canonical_cash_payload(
    payload: Any,
    *,
    previous_payload: dict[str, Any] | None = None,
    strict_types: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="现金余额表记录格式不正确。")
    result = dict(payload)
    result["transactions"] = _normalise_cash_transactions(
        result.get("transactions", []),
        previous_payload=previous_payload,
        strict_types=strict_types,
    )
    return normalize_payload(result, previous_payload)


def _locked_cash_forces(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        return {}
    return {
        str(item.get("id") or ""): item
        for item in payload["transactions"]
        if _cash_force_transaction(item)
        and _cash_bool(item.get("system_locked"))
        and str(item.get("id") or "").strip()
    }


def _protect_locked_cash_forces(before_payload: Any, after_payload: Any) -> None:
    """Reject removing or mutating a force created by the correction control."""

    locked = _locked_cash_forces(before_payload)
    if not locked:
        return
    after = {
        str(item.get("id") or ""): item
        for item in (
            after_payload.get("transactions", [])
            if isinstance(after_payload, dict)
            and isinstance(after_payload.get("transactions"), list)
            else []
        )
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    immutable_fields = (
        "id", "date", "type", "amount", "description", "mode", "system_locked", "created_at"
    )
    for transaction_id, old in locked.items():
        new = after.get(transaction_id)
        if new is None or any((money_text(old.get(key)) != money_text(new.get(key))) if key == "amount" else old.get(key) != new.get(key) for key in immutable_fields):
            raise HTTPException(
                status_code=403,
                detail="通过‘把余额强行修正成：’保存的余额强制修改记录不能删除或修改。",
            )


def _cash_flow_summary_db(
    db: Session,
    dataset_id: str,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Calculate available cash from the same JSON records used by both clients."""

    now_utc = _as_utc(now) or utcnow()
    # Cash movement is keyed by the business calendar, not UTC midnight.  In
    # Hong Kong/Shanghai, for example, 03:00 on Sep 3 is still Sep 2 in UTC
    # but must include Sep 3's ledger entries in the visible balance.
    today = now_utc.astimezone(_business_timezone()).date()
    opening = _money_value(payload.get("opening_balance", payload.get("base_balance")))
    opening_date = _cash_date(payload.get("opening_date", payload.get("as_of_date")), default=date.min)
    income = ZERO
    daily_expenses = ZERO
    fixed_expenses = ZERO
    cash_entries: list[dict[str, Any]] = []
    fixed_months_with_items: set[str] = set()
    day_records = db.scalars(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "day",
            SyncRecord.is_deleted.is_(False),
        )
    ).all()
    for record in day_records:
        rows = _daily_payload_rows(record.payload or {}, record.record_key)
        if not rows:
            rows = [{"日期": record.record_key}]
        for row in rows:
            day = _cash_date(row.get("日期"), default=_cash_date(record.record_key))
            if day <= opening_date or day > today:
                continue
            revenue = _effective_day_revenue(row)
            income += revenue
            if revenue:
                cash_entries.append({"date": day.isoformat(), "type": "营业收入", "description": "当日收入", "amount": revenue})
            for key, label in (
                ("食材成本", "食材"), ("佐料成本", "佐料"), ("水电", "水电"),
                ("其他", "其它"), ("手续费", "手续费／抽成"),
            ):
                amount = _money_value(row.get(key))
                if not amount and key == "其他":
                    amount = _money_value(row.get("其它"))
                if amount:
                    daily_expenses += amount
                    cash_entries.append({"date": day.isoformat(), "type": "经营支出", "description": label, "amount": -amount})
        expenses = (record.payload or {}).get("fixed_expenses", []) if isinstance(record.payload, dict) else []
        if isinstance(expenses, list):
            for expense in expenses:
                if not isinstance(expense, dict):
                    continue
                expense_day = _cash_date(expense.get("日期"), default=_cash_date(record.record_key))
                month_key = expense_day.isoformat()[:7]
                fixed_months_with_items.add(month_key)
                if not fixed_expense_counts_towards_cash(expense):
                    continue
                if opening_date < expense_day <= today:
                    amount = _money_value(expense.get("金额", expense.get("amount")))
                    fixed_expenses += amount
                    if amount:
                        cash_entries.append({"date": expense_day.isoformat(), "type": "固定成本", "description": str(expense.get("明细") or expense.get("类别") or "固定成本"), "amount": -amount})

    inventory_expenses = ZERO
    inventory = db.scalar(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "global",
            SyncRecord.record_key == "inventory",
            SyncRecord.is_deleted.is_(False),
        )
    )
    inventory_payload = inventory.payload if inventory and isinstance(inventory.payload, dict) else {}
    for entry in inventory_payload.get("entries", []) if isinstance(inventory_payload.get("entries"), list) else []:
        if not isinstance(entry, dict) or is_voided(entry):
            continue
        entry_day = _cash_date(entry.get("date", entry.get("日期")))
        if opening_date < entry_day <= today:
            amount = _money_value(
                entry.get("total", entry.get("总价")),
                product(entry.get("quantity", entry.get("数量")), entry.get("unit_price", entry.get("单价"))),
            )
            inventory_expenses += amount
            if amount:
                cash_entries.append({"date": entry_day.isoformat(), "type": "入库支出", "description": str(entry.get("name") or entry.get("名称") or "入库"), "amount": -amount})

    # Legacy records store fixed-cost totals once per month.  Use them only when
    # that month has no itemized daily expenses, avoiding a double deduction.
    month_records = db.scalars(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "month",
            SyncRecord.is_deleted.is_(False),
        )
    ).all()
    for record in month_records:
        rows = (record.payload or {}).get("monthly_fixed", []) if isinstance(record.payload, dict) else []
        if not isinstance(rows, list) or not rows:
            continue
        row = rows[-1] if isinstance(rows[-1], dict) else {}
        month_key = str(row.get("月份") or record.record_key or "")[:7]
        try:
            month_start = date.fromisoformat(f"{month_key}-01")
        except ValueError:
            continue
        payment_day = month_start
        if month_key in fixed_months_with_items or not (opening_date < payment_day <= today):
            continue
        amount = _fixed_month_amount(row)
        fixed_expenses += amount
        if amount:
            cash_entries.append({"date": payment_day.isoformat(), "type": "固定成本", "description": f"{month_key} 月度固定成本", "amount": -amount})

    transactions = payload.get("transactions", [])
    if not isinstance(transactions, list):
        transactions = []
    shareholder_loan = _money_value(payload.get("shareholder_loan"))
    loan_summary_entries: list[dict[str, Any]] = []
    if shareholder_loan:
        legacy_loan_date = opening_date if opening_date != date.min else today
        loan_summary_entries.append({
            "date": legacy_loan_date.isoformat(), "amount": shareholder_loan,
        })
        cash_entries.append({
            "date": legacy_loan_date.isoformat(),
            "type": "向股东借款",
            "description": "旧版股东借款",
            "amount": shareholder_loan,
            "mode": "delta",
        })
    for transaction in transactions:
        if not isinstance(transaction, dict):
            continue
        transaction_day = _cash_date(transaction.get("date", transaction.get("日期")))
        if transaction_day == date.min or transaction_day > today:
            continue
        amount = _money_value(transaction.get("amount", transaction.get("金额")))
        kind = str(transaction.get("type") or transaction.get("类型") or "其它现金调整")
        if kind == "向股东借款" and not _cash_force_transaction(transaction):
            loan_amount = abs(amount)
            shareholder_loan += loan_amount
            if loan_amount:
                loan_summary_entries.append({
                    "date": transaction_day.isoformat(), "amount": loan_amount,
                })
        # A transaction from before the opening date is already represented by
        # the opening balance and must not be applied again.  It still belongs
        # in borrowing history and the month/year/cumulative loan statistics.
        if transaction_day < opening_date:
            continue
        if _cash_force_transaction(transaction):
            cash_entries.append({
                "id": str(transaction.get("id") or ""),
                "date": transaction_day.isoformat(),
                "type": CASH_FORCE_TYPE,
                "description": CASH_FORCE_TYPE,
                "amount": max(ZERO, amount),
                "mode": "force",
                "system_locked": _cash_bool(transaction.get("system_locked")),
                "created_at": str(transaction.get("created_at") or ""),
            })
            continue
        signed = -abs(amount) if kind in {"现金支出", "其它现金支出"} else abs(amount)
        if signed:
            cash_entries.append({
                "id": str(transaction.get("id") or ""),
                "date": transaction_day.isoformat(),
                "type": kind,
                "description": str(transaction.get("description") or transaction.get("说明") or kind),
                "amount": signed,
                "mode": "delta",
            })
    total_expenses = daily_expenses + inventory_expenses + fixed_expenses
    loan_entries_total = sum((_money_value(item.get("amount")) for item in loan_summary_entries), ZERO)
    current_month = today.isoformat()[:7]
    current_year = today.isoformat()[:4]

    # Every automatic and ordinary delta on a date is applied before force
    # transactions for that date.  This makes a correction represent the
    # closing balance at the moment it was saved.  Multiple corrections on one
    # date follow their immutable server timestamp and id.
    chronological = sorted(
        cash_entries,
        key=lambda item: (
            str(item.get("date") or ""),
            1 if item.get("mode") == "force" else 0,
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
            str(item.get("type") or ""),
        ),
    )
    running_balance = opening
    current_month_start = date(today.year, today.month, 1)
    # The legacy opening value is the only known carry-over when the original
    # baseline was first entered during the selected month.  New corrections
    # are events, so future months can derive their carry-over precisely.
    previous_month_balance = opening
    for item in chronological:
        if item.get("mode") == "force":
            running_balance = _money_value(item.get("amount"))
            item["income"] = None
            item["expense"] = None
        else:
            movement = _money_value(item.get("amount"))
            running_balance += movement
            item["income"] = movement if movement > 0 else None
            item["expense"] = abs(movement) if movement < 0 else None
        item["running_balance"] = running_balance
        item["deletable"] = bool(item.get("id")) and not (
            item.get("mode") == "force" and _cash_bool(item.get("system_locked"))
        )
        if _cash_date(item.get("date")) < current_month_start:
            previous_month_balance = running_balance

    # The UI presents newest rows first, but keeps the running balance that was
    # calculated in true chronological order above.
    display_entries = list(reversed(chronological))
    return json_money({
        "opening_balance": opening,
        "opening_date": opening_date.isoformat() if opening_date != date.min else "",
        "shareholder_loan": shareholder_loan,
        "income": income,
        "daily_expenses": daily_expenses,
        "inventory_expenses": inventory_expenses,
        "fixed_expenses": fixed_expenses,
        "total_expenses": total_expenses,
        "current_balance": running_balance,
        "previous_month_balance": previous_month_balance,
        "shareholder_loan_total": loan_entries_total,
        "shareholder_loan_this_month": decimal_value(sum(
            _money_value(item.get("amount")) for item in loan_summary_entries
            if str(item.get("date") or "").startswith(current_month)
        ), limit=None),
        "shareholder_loan_this_year": decimal_value(sum(
            _money_value(item.get("amount")) for item in loan_summary_entries
            if str(item.get("date") or "").startswith(current_year)
        ), limit=None),
        "entries": display_entries,
        "days": sum(
            1 for record in day_records
            for row in _daily_payload_rows(record.payload or {}, record.record_key)
            if opening_date < _cash_date(row.get("日期"), default=_cash_date(record.record_key)) <= today
        ),
    })


def _cash_position_response(db: Session, dataset_id: str) -> dict[str, Any]:
    record = db.scalar(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "global",
            SyncRecord.record_key.in_(["cash_position", "cash_balance"]),
            SyncRecord.is_deleted.is_(False),
        ).order_by((SyncRecord.record_key == "cash_position").desc())
    )
    payload = _cash_payload_from_record(record)
    flow = _cash_flow_summary_db(db, dataset_id, payload)
    return {
        "dataset_id": dataset_id,
        "record": record_out(record) if record else None,
        **flow,
    }


def _normalise_cash_body(
    body: CashPositionBody,
    *,
    previous_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    opening_raw = body.opening_balance
    if opening_raw in (None, ""):
        opening_raw = body.base_balance
    if opening_raw in (None, ""):
        opening_raw = body.current_balance
    opening = _money_value(opening_raw)
    shareholder_loan = _money_value(body.shareholder_loan)
    if opening < 0 or shareholder_loan < 0:
        raise HTTPException(status_code=422, detail="目前余额和向股东借款不能为负数。")
    date_raw = body.opening_date if body.opening_date not in (None, "") else body.as_of_date
    opening_date = _cash_date(date_raw, default=utcnow().date())
    transactions = _normalise_cash_transactions(
        body.transactions,
        previous_payload=previous_payload,
        strict_types=True,
    )
    return json_money({
        "opening_balance": opening,
        "opening_date": opening_date.isoformat(),
        "shareholder_loan": shareholder_loan,
        "base_balance": opening,
        "as_of_date": opening_date.isoformat(),
        "transactions": transactions,
    })


def _save_cash_position_record(
    db: Session,
    *,
    dataset_id: str,
    body: CashPositionBody,
    user: AppUser,
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True, for_update=True)
    # Lock both aliases before choosing one.  Installations upgraded from the
    # early web build can briefly contain an active ``cash_balance`` alongside
    # the canonical ``cash_position``; renaming the former blindly would hit
    # the unique record-identity constraint.
    candidates = db.scalars(
        select(SyncRecord)
        .where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "global",
            SyncRecord.record_key.in_(["cash_position", "cash_balance"]),
        )
        .order_by((SyncRecord.record_key == "cash_position").desc(), SyncRecord.updated_at.desc())
        .with_for_update()
    ).all()
    record = next((item for item in candidates if not item.is_deleted), None)
    if record is None:
        # Prefer restoring the canonical identity when only deleted aliases
        # remain; otherwise any deleted row can be reused without inserting a
        # duplicate identity.
        record = next((item for item in candidates if item.record_key == "cash_position"), None)
        record = record or (candidates[0] if candidates else None)
    if record and body.expected_version not in {0, record.version}:
        raise HTTPException(status_code=409, detail="现金余额表记录版本冲突。")
    before_payload = record.payload if record and not record.is_deleted else None
    before_version = int(record.version if record else 0)
    payload = _cash_payload_from_record(record)
    payload.update(_normalise_cash_body(body, previous_payload=payload))
    payload = normalize_payload(payload, before_payload)
    _protect_locked_cash_forces(before_payload, payload)
    checksum = payload_checksum(payload)
    sequence = next_sequence(db, dataset_id)
    if record is None:
        record = SyncRecord(
            dataset_id=dataset_id,
            record_type="global",
            record_key="cash_position",
            payload=payload,
            checksum=checksum,
            version=1,
            sequence=sequence,
            is_deleted=False,
        )
        db.add(record)
        action = "create"
    else:
        record.record_key = "cash_position"
        record.payload = payload
        record.checksum = checksum
        record.version += 1
        record.sequence = sequence
        record.is_deleted = False
        action = "restore" if before_payload is None else "update"
    add_audit(
        db,
        user=user,
        dataset_id=dataset_id,
        record_type="global",
        record_key="cash_position",
        action=action,
        source="cash_position",
        event_id=f"cash-position-{uuid4()}",
        device_id="",
        from_version=before_version,
        to_version=record.version,
        sequence=sequence,
        before_payload=before_payload,
        after_payload=payload,
        checksum=checksum,
        occurred_at=utcnow(),
    )
    db.commit()
    return _cash_position_response(db, dataset_id)


def _wechat_scheduler_loop() -> None:
    last_attempt_by_dataset: dict[str, float] = {}
    last_success_by_dataset: dict[str, str] = {}
    while True:
        try:
            tz = ZoneInfo(config.WECHAT_TIMEZONE)
            now = datetime.now(tz)
            target_day = (now.date() - timedelta(days=1)).isoformat()
            scheduled = now.replace(
                hour=max(0, min(23, int(config.WECHAT_SYNC_HOUR))),
                minute=max(0, min(59, int(config.WECHAT_SYNC_MINUTE))),
                second=0, microsecond=0,
            )
            if now >= scheduled:
                with SessionLocal() as db:
                    actor = db.scalar(select(AppUser).where(AppUser.username == config.ADMIN_USERNAME))
                    if actor is None:
                        raise WeChatPayError("找不到管理员账号，无法记录微信自动同步审计。")
                    datasets = list(db.scalars(select(Dataset).where(Dataset.id != config.TEST_DATASET_ID)).all())
                    for dataset in datasets:
                        settings = _dataset_store_settings_payload(db, dataset.id)
                        if not settings.get("wechat_auto_sync"):
                            continue
                        if merchant_for_store(dataset.id, "A") is None and merchant_for_store(dataset.id, "B") is None:
                            continue
                        if last_success_by_dataset.get(dataset.id) == target_day:
                            continue
                        last_attempt = last_attempt_by_dataset.get(dataset.id, 0.0)
                        if time.monotonic() - last_attempt < 15 * 60:
                            continue
                        last_attempt_by_dataset[dataset.id] = time.monotonic()
                        _WECHAT_SCHEDULER_STATE["last_attempt_at"] = now.isoformat()
                        try:
                            apply_wechat_sync(
                                db, dataset_id=dataset.id, bill_date=target_day, actor=actor,
                                source="wechat_bill_auto", force=False,
                            )
                            last_success_by_dataset[dataset.id] = target_day
                            _WECHAT_SCHEDULER_STATE["last_success_date"] = target_day
                            _WECHAT_SCHEDULER_STATE["last_error"] = ""
                        except Exception as exc:
                            db.rollback()
                            _WECHAT_SCHEDULER_STATE["last_error"] = f"{dataset.name}: {exc}"
        except Exception as exc:
            _WECHAT_SCHEDULER_STATE["last_error"] = str(exc)
        time.sleep(60)


def _start_wechat_scheduler() -> None:
    global _WECHAT_SCHEDULER_STARTED
    if _WECHAT_SCHEDULER_STARTED:
        return
    _WECHAT_SCHEDULER_STARTED = True
    threading.Thread(
        target=_wechat_scheduler_loop, name="wechat-bill-auto-sync", daemon=True
    ).start()


def purge_expired_audit_logs(db: Session, *, now: datetime | None = None) -> int:
    """Delete audit rows older than the product's 366-day retention period."""

    cutoff = (now or utcnow()) - timedelta(days=AUDIT_RETENTION_DAYS)
    result = db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    return int(result.rowcount or 0)


def ensure_entry_timing_schema() -> None:
    """Upgrade an existing V13 timing table without touching ledger data.

    ``metadata.create_all`` creates missing tables, but intentionally does not
    add columns to an existing PostgreSQL table. Sep01V1 stores per-item and
    per-income clocks in two JSONB maps, so an in-place deployment must add
    those columns before the ORM performs its first query.
    """

    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE entry_timings "
                "ADD COLUMN IF NOT EXISTS detail_item_times JSONB NOT NULL "
                "DEFAULT '{}'::jsonb"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE entry_timings "
                "ADD COLUMN IF NOT EXISTS detail_field_times JSONB NOT NULL "
                "DEFAULT '{}'::jsonb"
            )
        )


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_entry_timing_schema()
    db = next(get_db())
    try:
        purge_expired_audit_logs(db)
        db.commit()
        ensure_admin(db)
        bind_legacy_users_if_unambiguous(db)
        ensure_test_account(db)
    finally:
        db.close()
    # The Sep01V1 UI no longer exposes WeChat API controls. Keep the old scheduler
    # disabled so an obsolete credential cannot mutate a ledger in the background.


@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    users = db.scalar(select(func.count()).select_from(AppUser))
    datasets = db.scalar(select(func.count()).select_from(Dataset))
    records = db.scalar(select(func.count()).select_from(SyncRecord))
    return {
        "status": "ok",
        "version": app.version,
        "users": int(users or 0),
        "datasets": int(datasets or 0),
        "records": int(records or 0),
        "time": serialize_dt(utcnow()),
    }


@app.post("/api/v1/auth/login")
def login(body: LoginBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确。")
    token, expires_at = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": serialize_dt(expires_at),
        "user": user_out(user, db),
    }


@app.post("/api/v1/auth/test-login")
def test_login(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not config.TEST_LOGIN_ENABLED:
        raise HTTPException(status_code=404, detail="Test 快速登录未启用。")
    user = db.scalar(
        select(AppUser).where(func.lower(AppUser.username) == config.TEST_USERNAME.lower())
    )
    if not user or not user.is_active or user.role != "viewer":
        raise HTTPException(status_code=503, detail="Test 演示账号当前不可用。")
    membership = db.scalar(
        select(UserDatasetMembership).where(
            UserDatasetMembership.user_id == user.id,
            UserDatasetMembership.dataset_id == config.TEST_DATASET_ID,
        )
    )
    if membership is None:
        raise HTTPException(status_code=503, detail="Test 演示账本尚未配置。")
    token, expires_at = create_access_token(
        user, expire_minutes=config.TEST_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": serialize_dt(expires_at),
        "user": user_out(user, db),
    }


@app.get("/api/v1/auth/me")
def me(
    user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return user_out(user, db)


@app.get("/api/v1/users")
def list_users(_: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    users = db.scalars(select(AppUser).order_by(AppUser.created_at)).all()
    return [user_out(user, db) for user in users]


@app.post("/api/v1/users")
def create_user(body: UserCreate, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.role not in {"admin", "editor", "entry", "viewer"}:
        raise HTTPException(status_code=422, detail="role 必须是 admin/editor/entry/viewer。")
    username = body.username.strip()
    if username.casefold() == config.TEST_USERNAME.casefold():
        raise HTTPException(status_code=409, detail="Test 是系统保留账号。")
    exists = db.scalar(
        select(AppUser).where(func.lower(AppUser.username) == username.lower())
    )
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在。")
    user = AppUser(
        username=username,
        display_name=body.display_name.strip() or username,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    dataset_ids = list(body.dataset_ids)
    if body.default_dataset_id and not dataset_ids:
        dataset_ids = [body.default_dataset_id]
    set_user_dataset_memberships(
        db, user, dataset_ids, body.default_dataset_id
    )
    db.commit()
    db.refresh(user)
    return user_out(user, db)


@app.patch("/api/v1/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    is_test = user.username.casefold() == config.TEST_USERNAME.casefold()
    if body.role is not None:
        if body.role not in {"admin", "editor", "entry", "viewer"}:
            raise HTTPException(status_code=422, detail="role 必须是 admin/editor/entry/viewer。")
        if is_test and body.role != "viewer":
            raise HTTPException(status_code=422, detail="公开 Test 账号必须保持只读权限。")
        user.role = body.role
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.is_active is not None:
        if is_test and not body.is_active:
            raise HTTPException(status_code=422, detail="公开 Test 快速登录账号不能停用。")
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
    assignments_changed = (
        body.dataset_ids is not None
        or "default_dataset_id" in body.model_fields_set
        or body.role is not None
    )
    if assignments_changed:
        current = membership_rows(db, user.id)
        dataset_ids = (
            list(body.dataset_ids)
            if body.dataset_ids is not None
            else [item.dataset_id for item in current]
        )
        default_dataset_id = (
            body.default_dataset_id
            if "default_dataset_id" in body.model_fields_set
            else next((item.dataset_id for item in current if item.is_default), None)
        )
        if default_dataset_id and not dataset_ids:
            dataset_ids = [default_dataset_id]
        set_user_dataset_memberships(
            db, user, dataset_ids, default_dataset_id
        )
    db.commit()
    db.refresh(user)
    return user_out(user, db)


@app.delete("/api/v1/users/{user_id}")
def delete_user(user_id: str, current: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在。")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员账号。")
    if user.username.casefold() == config.TEST_USERNAME.casefold():
        raise HTTPException(status_code=400, detail="公开 Test 账号不能删除。")
    db.delete(user)
    db.commit()
    return {"deleted": True, "user_id": user_id}


@app.get("/api/v1/temporary-permissions")
def list_temporary_permissions(
    _: AppUser = Depends(require_admin), db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(TemporaryPermission).order_by(
            TemporaryPermission.starts_at.desc(), TemporaryPermission.created_at.desc()
        )
    ).all()
    return [temporary_permission_out(item) for item in rows]


@app.post("/api/v1/temporary-permissions")
def create_temporary_permission(
    body: TemporaryPermissionCreate,
    admin: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    target = db.get(AppUser, body.user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="目标账号不存在或已停用。")
    if target.role == "admin" or target.username.casefold() == config.TEST_USERNAME.casefold():
        raise HTTPException(status_code=422, detail="管理员或公开 Test 账号不需要临时权限。")
    get_dataset_or_404(db, body.dataset_id)
    if body.permission_role not in {"entry", "editor"}:
        raise HTTPException(status_code=422, detail="临时权限必须是录入权限或修改权限。")
    starts_at = _as_utc(body.starts_at)
    ends_at = _as_utc(body.ends_at)
    if starts_at is None or ends_at is None or ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="结束时间必须晚于开始时间。")
    if body.business_end_date < body.business_start_date:
        raise HTTPException(status_code=422, detail="业务结束日期不能早于开始日期。")
    grant = TemporaryPermission(
        user_id=target.id,
        dataset_id=body.dataset_id,
        permission_role=body.permission_role,
        business_start_date=body.business_start_date.isoformat(),
        business_end_date=body.business_end_date.isoformat(),
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=admin.id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return temporary_permission_out(grant)


@app.delete("/api/v1/temporary-permissions/{permission_id}")
def delete_temporary_permission(
    permission_id: str,
    _: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    grant = db.get(TemporaryPermission, permission_id)
    if not grant:
        raise HTTPException(status_code=404, detail="临时权限记录不存在。")
    db.delete(grant)
    db.commit()
    return {"deleted": True, "id": permission_id}


@app.get("/api/v1/datasets")
def list_datasets(user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if user.role == "admin":
        datasets = db.scalars(
            select(Dataset).order_by(
                (Dataset.id == config.TEST_DATASET_ID).asc(), Dataset.created_at
            )
        ).all()
        return [dataset_out(item) for item in datasets]
    memberships = membership_rows(db, user.id)
    if not memberships:
        return []
    by_id = {
        item.id: item
        for item in db.scalars(
            select(Dataset).where(
                Dataset.id.in_([membership.dataset_id for membership in memberships])
            )
        ).all()
    }
    return [
        dataset_out(by_id[item.dataset_id], is_default=item.is_default)
        for item in memberships
        if item.dataset_id in by_id
    ]


@app.post("/api/v1/datasets")
def create_dataset(body: DatasetCreate, _: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    dataset = db.get(Dataset, body.id)
    if dataset:
        return dataset_out(dataset)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="账本名称不能为空。")
    dataset = Dataset(id=body.id, name=name, schema_version=body.schema_version)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset_out(dataset)


@app.patch("/api/v1/datasets/{dataset_id}")
def rename_dataset(
    dataset_id: str,
    body: DatasetUpdate,
    _: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    dataset = get_dataset_or_404(db, dataset_id, for_update=True)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="账本名称不能为空。")
    dataset.name = name
    db.commit()
    db.refresh(dataset)
    return dataset_out(dataset)


@app.delete("/api/v1/datasets/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    confirm_name: str = Query(min_length=1, max_length=200),
    _: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    dataset = get_dataset_or_404(db, dataset_id, for_update=True)
    if dataset.id == config.TEST_DATASET_ID:
        raise HTTPException(status_code=422, detail="Test 独立演示账本不能删除。")
    if confirm_name != dataset.name:
        raise HTTPException(status_code=409, detail="确认名称与当前账本名称不一致。")
    membership_count = db.scalar(
        select(func.count())
        .select_from(UserDatasetMembership)
        .where(UserDatasetMembership.dataset_id == dataset_id)
    )
    if int(membership_count or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="仍有用户绑定这套账本，请先在用户管理中解除绑定。",
        )

    # These two historical tables intentionally have no foreign key so that an
    # audit schema migration cannot block normal sync writes.  Dataset deletion
    # must therefore remove them explicitly; all other children use FK cascade.
    db.execute(delete(SyncConflict).where(SyncConflict.dataset_id == dataset_id))
    db.execute(delete(AuditLog).where(AuditLog.dataset_id == dataset_id))
    db.execute(delete(EntryTiming).where(EntryTiming.dataset_id == dataset_id))
    deleted = {"deleted": True, "id": dataset.id, "name": dataset.name}
    db.delete(dataset)
    db.commit()
    return deleted


@app.get("/api/v1/datasets/{dataset_id}/workbooks/internal")
def download_internal_workbook(
    dataset_id: str,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    dataset = authorized_dataset(db, user, dataset_id)
    records = db.scalars(
        select(SyncRecord)
        .where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.is_deleted.is_(False),
        )
        .order_by(SyncRecord.record_type, SyncRecord.record_key)
    ).all()
    audit_rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.dataset_id == dataset_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(5000)
    ).all()
    try:
        content = build_internal_workbook(
            dataset_id=dataset.id,
            schema_version=max(2, dataset.schema_version),
            records=records,
            audit_records=[audit_out(row) for row in audit_rows],
        )
    except WorkbookFormatError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return workbook_response(
        content,
        filename=f"{dataset.name}_(勿删) 成本管理软件内部数据.xlsx",
        fallback="internal-workbook.xlsx",
    )


@app.post("/api/v1/datasets/{dataset_id}/workbooks/internal")
def upload_internal_workbook(
    dataset_id: str,
    file: UploadFile = File(...),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id)
    content = read_workbook_upload(file)
    try:
        parsed = parse_internal_workbook(content)
        authorized_dataset(db, user, dataset_id, write=True, for_update=True)
        counts = apply_workbook_records(
            db,
            dataset_id=dataset_id,
            parsed=parsed,
            replace=True,
            user=user,
            source="web_internal_excel",
        )
    except WorkbookFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "mode": "replace",
        "imported_records": len(parsed.records),
        "records": len(parsed.records),
        "warnings": parsed.warnings,
        **counts,
    }


@app.post("/api/v1/datasets/{dataset_id}/workbooks/internal-overwrite")
def upload_internal_workbook_with_backup(
    dataset_id: str,
    confirm_target_name: str = Form(...),
    confirm_again: str = Form(...),
    file: UploadFile = File(...),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dangerous cross-ledger/admin replacement: require two confirmations and backup target first."""
    target = authorized_dataset(db, user, dataset_id, write=True, for_update=True)
    if confirm_target_name.strip() != target.name or confirm_again.strip() != target.name:
        raise HTTPException(status_code=409, detail="双重确认失败：两次确认都必须匹配目标账本名称。")
    content = read_workbook_upload(file)
    target_records = list(db.scalars(
        select(SyncRecord).where(SyncRecord.dataset_id == target.id, SyncRecord.is_deleted.is_(False))
    ).all())
    try:
        parsed = parse_internal_workbook(content)
        backup_content = build_internal_workbook(
            dataset_id=target.id, schema_version=max(2, target.schema_version), records=target_records
        )
        backup_dir = Path("/opt/restaurant-cloud/backups/ledger-overwrite")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{target.id}-{stamp}.xlsx"
        backup_path.write_bytes(backup_content)
        counts = apply_workbook_records(
            db, dataset_id=target.id, parsed=parsed, replace=True, user=user,
            source="internal_excel_overwrite_other",
        )
    except WorkbookFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "mode": "replace", "target_dataset_id": target.id, "target_dataset_name": target.name,
        "backup_path": str(backup_path), "imported_records": len(parsed.records),
        "records": len(parsed.records), "warnings": parsed.warnings, **counts,
    }


@app.get("/api/v1/datasets/{dataset_id}/workbooks/user")
def download_user_workbook(
    dataset_id: str,
    year: int = Query(ge=2000, le=2200),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    dataset = authorized_dataset(db, user, dataset_id)
    records = db.scalars(
        select(SyncRecord)
        .where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.is_deleted.is_(False),
        )
        .order_by(SyncRecord.record_type, SyncRecord.record_key)
    ).all()
    try:
        content = build_user_workbook(
            dataset_id=dataset.id,
            schema_version=max(2, dataset.schema_version),
            year=year,
            records=records,
        )
    except WorkbookFormatError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return workbook_response(
        content,
        filename=f"{dataset.name}_用户Excel_{year}.xlsx",
        fallback=f"user-workbook-{year}.xlsx",
    )


@app.post("/api/v1/datasets/{dataset_id}/workbooks/user")
def upload_user_workbook(
    dataset_id: str,
    year: int = Query(ge=2000, le=2200),
    file: UploadFile = File(...),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True)
    content = read_workbook_upload(file)
    try:
        parsed = parse_user_workbook(
            content, year=year, expected_dataset_id=dataset_id
        )
        authorized_dataset(db, user, dataset_id, write=True, for_update=True)
        counts = apply_workbook_records(
            db,
            dataset_id=dataset_id,
            parsed=parsed,
            replace=False,
            replace_user_year=year,
            preserve_internal_fixed_flags=True,
            user=user,
            source="web_user_excel",
        )
    except WorkbookFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "mode": "replace_year",
        "year": year,
        "replace_year": year,
        "imported_records": len(parsed.records),
        "records": len(parsed.records),
        "warnings": parsed.warnings,
        "deleted_records": counts["deleted"],
        **counts,
    }


@app.post("/api/v1/datasets/{dataset_id}/workbooks/user-merge")
def merge_user_workbook(
    dataset_id: str,
    year: int = Query(ge=2000, le=2200),
    file: UploadFile = File(...),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add workbook data to the selected year without deleting absent records."""
    authorized_dataset(db, user, dataset_id, write=True)
    content = read_workbook_upload(file)
    try:
        parsed = parse_user_workbook(
            content, year=year, expected_dataset_id=dataset_id
        )
        authorized_dataset(db, user, dataset_id, write=True, for_update=True)
        counts = apply_workbook_records(
            db,
            dataset_id=dataset_id,
            parsed=parsed,
            replace=False,
            merge=True,
            preserve_internal_fixed_flags=True,
            user=user,
            source="web_user_excel_merge",
        )
    except WorkbookFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "mode": "merge",
        "year": year,
        "imported_records": len(parsed.records),
        "records": len(parsed.records),
        "warnings": parsed.warnings,
        **counts,
    }


@app.post("/api/v1/devices/register")
def register_device(body: DeviceRegister, user: AppUser = Depends(require_writer), db: Session = Depends(get_db)) -> dict[str, Any]:
    authorized_dataset(db, user, body.dataset_id, write=True)
    device = Device(dataset_id=body.dataset_id, name=body.name, platform=body.platform)
    db.add(device)
    db.commit()
    db.refresh(device)
    return {
        "id": device.id,
        "dataset_id": device.dataset_id,
        "name": device.name,
        "platform": device.platform,
        "created_at": serialize_dt(device.created_at),
        "last_seen_at": serialize_dt(device.last_seen_at),
    }


@app.get("/api/v1/datasets/{dataset_id}/store-settings")
def get_store_settings(
    dataset_id: str,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id)
    settings = _dataset_store_settings_payload(db, dataset_id)
    return {
        **settings,
        "wechat": {
            "A": payment_status(dataset_id, "A"),
            "B": payment_status(dataset_id, "B"),
            "sync_time": f"{config.WECHAT_SYNC_HOUR:02d}:{config.WECHAT_SYNC_MINUTE:02d}",
            "timezone": config.WECHAT_TIMEZONE,
            "amount_mode": config.WECHAT_AMOUNT_MODE,
        },
        "scheduler": dict(_WECHAT_SCHEDULER_STATE),
    }


@app.put("/api/v1/datasets/{dataset_id}/store-settings")
def update_store_settings(
    dataset_id: str,
    body: StoreNamesUpdate,
    user: AppUser = Depends(require_writer),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.store_a_name.strip() == body.store_b_name.strip():
        raise HTTPException(status_code=422, detail="两家店的显示名称不能完全相同。")
    return _write_store_settings_payload(db, dataset_id, body, user)


@app.get("/api/v1/datasets/{dataset_id}/cash-position")
@app.get("/api/v1/datasets/{dataset_id}/cash_position")
def get_cash_position(
    dataset_id: str,
    user: AppUser = Depends(require_change_permission),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Read the balance module; entry and viewer accounts cannot discover it."""

    authorized_dataset(db, user, dataset_id)
    return _cash_position_response(db, dataset_id)


@app.put("/api/v1/datasets/{dataset_id}/cash-position")
@app.put("/api/v1/datasets/{dataset_id}/cash_position")
def update_cash_position(
    dataset_id: str,
    body: CashPositionBody,
    user: AppUser = Depends(require_change_permission),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _save_cash_position_record(
        db, dataset_id=dataset_id, body=body, user=user
    )


@app.get("/api/v1/datasets/{dataset_id}/entry-windows")
def list_entry_windows(
    dataset_id: str,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Expose server deadlines so entry users can see an honest countdown."""

    authorized_dataset(db, user, dataset_id)
    timing_rows = db.scalars(
        select(EntryTiming)
        .where(
            EntryTiming.dataset_id == dataset_id,
            EntryTiming.record_type == "day",
        )
        .order_by(EntryTiming.record_key)
    ).all()
    day_records = db.scalars(
        select(SyncRecord).where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "day",
            SyncRecord.is_deleted.is_(False),
        )
    ).all()
    timings = {(row.record_type, row.record_key): row for row in timing_rows}
    records = {(row.record_type, row.record_key): row for row in day_records}
    now = utcnow()
    result: list[dict[str, Any]] = []
    identities = sorted(set(timings) | set(records), key=lambda item: (item[1], item[0]))
    for identity in identities:
        timing = timings.get(identity)
        record = records.get(identity)
        record_type, record_key = identity
        payload = (
            record.payload
            if record is not None and isinstance(record.payload, dict)
            else {}
        )
        fallback = _timing_fallback(record, now)
        detail_item_times = dict((timing.detail_item_times or {}) if timing else {})
        detail_field_times = dict((timing.detail_field_times or {}) if timing else {})

        legacy_detail_started = _as_utc(timing.detail_started_at) if timing else None
        snapshots = _detail_snapshot_entries(payload, record_key)
        detail_started_by_category: dict[str, str | None] = {}
        detail_deadlines: dict[str, str | None] = {}
        category_start_values: list[datetime] = []
        for category in ENTRY_DETAIL_CATEGORIES:
            started = _as_utc(detail_field_times.get(category))
            if started is None and any(
                item.get("category") == category for item in snapshots.values()
            ):
                started = legacy_detail_started or fallback
            detail_started_by_category[category] = serialize_dt(started)
            detail_deadlines[category] = serialize_dt(
                started + ENTRY_DETAIL_WINDOW if started is not None else None
            )
            if started is not None:
                category_start_values.append(started)
        first_detail_started = min(category_start_values, default=None)
        detail_items: list[dict[str, Any]] = []
        for item_key, item in snapshots.items():
            saved_at = _as_utc(detail_item_times.get(item_key)) or fallback
            detail_items.append(
                {
                    "key": item_key,
                    "category": item["category"],
                    "label": item["label"],
                    "saved_at": serialize_dt(saved_at),
                    "edit_deadline": serialize_dt(saved_at + ENTRY_EDIT_WINDOW),
                }
            )

        # The key may be a legacy slash date; use the stored key for the
        # revenue cutoff and leave it null when no calendar date is available.
        revenue_deadline = _entry_revenue_deadline(record_key, payload, now)
        current_income = _income_field_snapshots(payload, record_key)
        income_fields: dict[str, dict[str, Any]] = {}
        a_saved_times: list[datetime] = []
        b_saved_times: list[datetime] = []
        for key, (label, field) in ENTRY_INCOME_SLOTS.items():
            item = current_income.get(f"{record_key}|{key}")
            if item is None:
                item = next(
                    (value for value in current_income.values() if value.get("key") == key),
                    None,
                )
            present = bool(item and item.get("present"))
            saved_at = _as_utc(detail_field_times.get(f"income:{key}"))
            if saved_at is None and present:
                if key.startswith("a_"):
                    saved_at = (_as_utc(timing.store_a_at) if timing else None) or fallback
                elif key.startswith("b_"):
                    saved_at = (_as_utc(timing.store_b_at) if timing else None) or fallback
                else:
                    saved_at = (_as_utc(timing.revenue_at) if timing else None) or fallback
            edit_deadline = saved_at + ENTRY_EDIT_WINDOW if saved_at is not None else None
            if saved_at is not None and key.startswith("a_"):
                a_saved_times.append(saved_at)
            if saved_at is not None and key.startswith("b_"):
                b_saved_times.append(saved_at)
            if saved_at is not None:
                state = "editable" if now < edit_deadline else "locked"
            else:
                state = "unrecorded" if revenue_deadline is None or now < revenue_deadline else "expired"
            income_fields[key] = {
                "label": label,
                "field": field,
                "saved_at": serialize_dt(saved_at),
                "edit_deadline": serialize_dt(edit_deadline),
                "entry_deadline": serialize_dt(revenue_deadline),
                "state": state,
            }

        current_customers = _customer_field_snapshots(payload, record_key)
        customer_fields: dict[str, dict[str, Any]] = {}
        for key, (label, field) in ENTRY_CUSTOMER_SLOTS.items():
            item = current_customers.get(f"{record_key}|{key}") or next(
                (value for value in current_customers.values() if value.get("key") == key), {}
            )
            saved_at = _as_utc(detail_field_times.get(f"customer:{key}"))
            if saved_at is None and item.get("present") and item.get("value") != "0.0":
                saved_at = fallback
            deadline = saved_at + ENTRY_EDIT_WINDOW if saved_at is not None else None
            customer_fields[key] = {
                "label": label, "field": field,
                "saved_at": serialize_dt(saved_at), "edit_deadline": serialize_dt(deadline),
                "state": ("editable" if now < deadline else "locked") if deadline is not None else "unrecorded",
            }

        store_a_at = (_as_utc(timing.store_a_at) if timing else None) or (
            min(a_saved_times) if a_saved_times else None
        )
        store_b_at = (_as_utc(timing.store_b_at) if timing else None) or (
            min(b_saved_times) if b_saved_times else None
        )
        legacy_revenue_at = _as_utc(timing.revenue_at) if timing else None
        result.append(
            {
                "record_type": record_type,
                "record_key": record_key,
                "detail_started_at": serialize_dt(first_detail_started),
                "detail_deadline": serialize_dt(
                    first_detail_started + ENTRY_DETAIL_WINDOW
                    if first_detail_started is not None
                    else None
                ),
                "detail_started_at_by_category": detail_started_by_category,
                "detail_deadlines": detail_deadlines,
                "detail_item_times": detail_item_times,
                "detail_items": detail_items,
                "income_fields": income_fields,
                "customer_fields": customer_fields,
                "store_a_at": serialize_dt(store_a_at),
                "store_a_deadline": serialize_dt(
                    store_a_at + ENTRY_EDIT_WINDOW
                    if store_a_at is not None
                    else None
                ),
                "store_b_at": serialize_dt(store_b_at),
                "store_b_deadline": serialize_dt(
                    store_b_at + ENTRY_EDIT_WINDOW
                    if store_b_at is not None
                    else None
                ),
                "revenue_at": serialize_dt(legacy_revenue_at),
                "revenue_edit_deadline": serialize_dt(
                    legacy_revenue_at + ENTRY_EDIT_WINDOW
                    if legacy_revenue_at is not None
                    else None
                ),
                "revenue_deadline": serialize_dt(revenue_deadline),
            }
        )
    return result


def _read_payment_upload(file: UploadFile | None, *, required: bool = False, max_bytes: int = 2 * 1024 * 1024) -> bytes | None:
    if file is None:
        if required:
            raise HTTPException(status_code=422, detail="缺少必需的微信支付文件。")
        return None
    try:
        content = file.file.read(max_bytes + 1)
    finally:
        file.file.close()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{file.filename or '文件'} 超过 2 MB 上限。")
    if required and not content:
        raise HTTPException(status_code=422, detail=f"{file.filename or '文件'} 为空。")
    return content or None


# Sep01V1 no longer exposes WeChat bill/configuration API routes.
def upload_store_wechat_config(
    dataset_id: str,
    store: str,
    mchid: str = Form(...),
    public_key_id: str = Form(...),
    apiclient_cert: UploadFile = File(...),
    apiclient_key: UploadFile = File(...),
    pub_key: UploadFile = File(...),
    apiclient_p12: UploadFile | None = File(default=None),
    readme_cn: UploadFile | None = File(default=None),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True)
    try:
        result = validate_and_save_wechat_files(
            dataset_id,
            store,
            mchid=mchid,
            public_key_id=public_key_id,
            cert_bytes=_read_payment_upload(apiclient_cert, required=True) or b"",
            private_key_bytes=_read_payment_upload(apiclient_key, required=True) or b"",
            public_key_bytes=_read_payment_upload(pub_key, required=True) or b"",
            p12_bytes=_read_payment_upload(apiclient_p12),
            readme_bytes=_read_payment_upload(readme_cn),
        )
    except WeChatPayError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"store": str(store).upper(), "status": result}


def remove_store_wechat_config(
    dataset_id: str,
    store: str,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True)
    try:
        delete_store_payment_config(dataset_id, store)
    except WeChatPayError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": True, "store": str(store).upper()}


def test_store_wechat_config(
    dataset_id: str,
    store: str,
    bill_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id)
    merchant = merchant_for_store(dataset_id, store)
    if merchant is None:
        raise HTTPException(status_code=422, detail="这家店还没有完整的微信支付配置。")
    try:
        bill = WeChatPayClient(merchant).request_trade_bill(bill_date)
    except WeChatPayError as exc:
        status_code = 503 if exc.status_code >= 500 else 400
        raise HTTPException(status_code=status_code, detail={"message": str(exc), "wechat_code": exc.code}) from exc
    return {
        "ok": True,
        "bill_date": bill_date,
        "rows": len(bill.rows),
        "sha1": bill.sha1,
    }


def sync_wechat_trade_bill(
    dataset_id: str,
    bill_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    force: bool = Query(default=False),
    user: AppUser = Depends(require_change_permission),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True, for_update=True)
    try:
        parsed_day = date.fromisoformat(bill_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="bill_date 必须是 YYYY-MM-DD。") from None
    if parsed_day >= datetime.now(ZoneInfo(config.WECHAT_TIMEZONE)).date():
        raise HTTPException(status_code=422, detail="微信交易账单只能同步已经结束的历史日期。")
    try:
        return apply_wechat_sync(
            db,
            dataset_id=dataset_id,
            bill_date=bill_date,
            actor=user,
            source="wechat_bill_force" if force else "wechat_bill_manual",
            force=force,
        )
    except WeChatPayError as exc:
        db.rollback()
        status_code = 503 if exc.status_code >= 500 else 400
        raise HTTPException(
            status_code=status_code,
            detail={"message": str(exc), "wechat_code": exc.code},
        ) from exc


def _soft_delete_record(db: Session, record: SyncRecord, *, user: AppUser, source: str, event_id: str, sequence: int) -> int:
    if record.is_deleted:
        return sequence
    before_payload = record.payload
    before_version = record.version
    record.is_deleted = True
    record.version += 1
    record.sequence = sequence
    add_audit(
        db,
        user=user,
        dataset_id=record.dataset_id,
        record_type=record.record_type,
        record_key=record.record_key,
        action="delete",
        source=source,
        event_id=event_id,
        device_id="",
        from_version=before_version,
        to_version=record.version,
        sequence=sequence,
        before_payload=before_payload,
        after_payload=None,
        checksum=record.checksum,
        occurred_at=utcnow(),
    )
    return sequence + 1


def _purge_inventory_range(payload: dict[str, Any], start_text: str, end_text: str) -> tuple[dict[str, Any], int]:
    value = dict(payload or {})
    removed = 0
    for key in ("entries", "adjustments", "overrides"):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        kept = []
        for row in rows:
            if not isinstance(row, dict):
                kept.append(row)
                continue
            day = str(row.get("date") or row.get("日期") or row.get("day") or "").strip()
            in_range = bool(day and start_text <= day <= end_text)
            if in_range:
                removed += 1
            else:
                kept.append(row)
        value[key] = kept
    return value, removed


@app.post("/api/v1/datasets/{dataset_id}/records/bulk-delete")
def bulk_delete_records(
    dataset_id: str,
    body: BulkDeleteBody,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, write=True, for_update=True)
    if body.end_date < body.start_date:
        raise HTTPException(status_code=422, detail="结束日期不能早于开始日期。")
    start_text, end_text = body.start_date.isoformat(), body.end_date.isoformat()
    if (body.end_date - body.start_date).days > 3660:
        raise HTTPException(status_code=422, detail="一次最多删除 10 年范围的数据。")
    sequence = next_sequence(db, dataset_id)
    event_id = f"bulk-delete-{uuid4()}"
    deleted_days = 0
    deleted_months = 0
    rows = list(db.scalars(select(SyncRecord).where(SyncRecord.dataset_id == dataset_id).with_for_update()).all())
    for record in rows:
        if record.record_type == "day" and start_text <= record.record_key <= end_text and not record.is_deleted:
            sequence = _soft_delete_record(db, record, user=user, source="bulk_delete", event_id=event_id, sequence=sequence)
            deleted_days += 1
        elif body.delete_month_records and record.record_type == "month" and start_text[:7] <= record.record_key <= end_text[:7] and not record.is_deleted:
            sequence = _soft_delete_record(db, record, user=user, source="bulk_delete", event_id=event_id, sequence=sequence)
            deleted_months += 1
    inventory_removed = 0
    if body.delete_inventory_in_range:
        inventory = get_record(db, dataset_id, "global", "inventory")
        if inventory and not inventory.is_deleted and isinstance(inventory.payload, dict):
            updated, inventory_removed = _purge_inventory_range(inventory.payload, start_text, end_text)
            if updated != inventory.payload:
                before = inventory.payload
                before_version = inventory.version
                inventory.payload = updated
                inventory.checksum = payload_checksum(updated)
                inventory.version += 1
                inventory.sequence = sequence
                add_audit(
                    db, user=user, dataset_id=dataset_id, record_type="global", record_key="inventory",
                    action="update", source="bulk_delete", event_id=event_id, device_id="",
                    from_version=before_version, to_version=inventory.version, sequence=sequence,
                    before_payload=before, after_payload=updated, checksum=inventory.checksum, occurred_at=utcnow(),
                )
                sequence += 1
    db.commit()
    return {
        "deleted_days": deleted_days,
        "deleted_months": deleted_months,
        "inventory_rows_removed": inventory_removed,
        "start_date": start_text,
        "end_date": end_text,
    }


@app.post("/api/v1/datasets/{dataset_id}/records/delete-month")
def delete_month_records(
    dataset_id: str,
    body: MonthDeleteBody,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        year, month = (int(part) for part in body.month.split("-"))
        start_day = date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        end_day = next_month - timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=422, detail="月份格式不正确。") from None
    return bulk_delete_records(
        dataset_id,
        BulkDeleteBody(
            start_date=start_day,
            end_date=end_day,
            delete_month_records=True,
            delete_inventory_in_range=body.delete_inventory_in_month,
        ),
        user,
        db,
    )


@app.post("/api/v1/datasets/{source_dataset_id}/copy-to-ledger")
def copy_entire_ledger(
    source_dataset_id: str,
    body: CopyLedgerBody,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    source = authorized_dataset(db, user, source_dataset_id)
    target = authorized_dataset(db, user, body.target_dataset_id, write=True, for_update=True)
    if source.id == target.id:
        raise HTTPException(status_code=422, detail="源账本和目标账本不能是同一套账本。")
    if body.confirm_source_name.strip() != source.name:
        raise HTTPException(status_code=409, detail="第一次确认失败：源账本名称不匹配。")
    if body.confirm_target_name.strip() != target.name:
        raise HTTPException(status_code=409, detail="第二次确认失败：目标账本名称不匹配。")
    source_records = list(db.scalars(select(SyncRecord).where(SyncRecord.dataset_id == source.id, SyncRecord.is_deleted.is_(False))).all())
    target_records = list(db.scalars(select(SyncRecord).where(SyncRecord.dataset_id == target.id, SyncRecord.is_deleted.is_(False))).all())
    try:
        backup_content = build_internal_workbook(
            dataset_id=target.id,
            schema_version=max(2, target.schema_version),
            records=target_records,
        )
        backup_dir = Path("/opt/restaurant-cloud/backups/ledger-overwrite")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{target.id}-{stamp}.xlsx"
        backup_path.write_bytes(backup_content)
        source_content = build_internal_workbook(
            dataset_id=source.id,
            schema_version=max(2, source.schema_version),
            records=source_records,
        )
        parsed = parse_internal_workbook(source_content)
        counts = apply_workbook_records(
            db,
            dataset_id=target.id,
            parsed=parsed,
            replace=True,
            user=user,
            source="copy_entire_ledger",
        )
    except WorkbookFormatError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "copied": True,
        "source_dataset_id": source.id,
        "source_dataset_name": source.name,
        "target_dataset_id": target.id,
        "target_dataset_name": target.name,
        "backup_path": str(backup_path),
        **counts,
    }


@app.get("/api/v1/datasets/{dataset_id}/records")
def list_records(
    dataset_id: str,
    include_deleted: bool = False,
    offset: int = 0,
    limit: int = Query(default=2000, le=5000),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    authorized_dataset(db, user, dataset_id)
    stmt = select(SyncRecord).where(SyncRecord.dataset_id == dataset_id)
    if not include_deleted:
        stmt = stmt.where(SyncRecord.is_deleted.is_(False))
    rows = db.scalars(stmt.order_by(SyncRecord.sequence, SyncRecord.id).offset(offset).limit(limit)).all()
    return [record_out(row) for row in rows]


@app.get("/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}")
def read_record(dataset_id: str, record_type: str, record_key: str, user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id)
    record = get_record(db, dataset_id, record_type, record_key)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在。")
    return record_out(record)


def _guard_inventory_db(db: Session, dataset_id: str, previous: dict | None, payload: dict) -> None:
    # The caller owns the dataset row lock. Day writes take that same lock, so
    # this authoritative snapshot cannot change halfway through a stock check.
    records = db.scalars(select(SyncRecord).where(
        SyncRecord.dataset_id == dataset_id,
        SyncRecord.is_deleted.is_(False),
        SyncRecord.record_type.in_(["day", "global"]),
    ).order_by(SyncRecord.sequence, SyncRecord.id)).all()
    days = [{"record_key": row.record_key, "payload": row.payload,
             "sequence": row.sequence, "version": row.version}
            for row in records if row.record_type == "day"]
    ingredients = next((row.payload.get("ingredients", []) for row in records
                        if row.record_type == "global" and row.record_key == "ingredients"
                        and isinstance(row.payload, dict)), [])
    units_payload = next((row.payload for row in records if row.record_type == "global"
                          and row.record_key == "units" and isinstance(row.payload, dict)), {})
    units = [str(item.get("unit") or item.get("单位") or item.get("name") or "")
             if isinstance(item, dict) else str(item)
             for item in (units_payload.get("units") if isinstance(units_payload.get("units"), list) else [])]
    guard_inventory_balance(previous or {}, payload, days, ingredients,
                            today=utcnow().astimezone(_business_timezone()).date().isoformat(), units=units)


@app.put("/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}")
def write_record(
    dataset_id: str,
    record_type: str,
    record_key: str,
    body: RecordWrite,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, for_update=True)
    effective_role = _effective_record_role(
        db, user, dataset_id, record_type, record_key, body.payload, now=utcnow()
    )
    if effective_role not in {"admin", "editor", "entry"}:
        raise HTTPException(status_code=403, detail="当前账号在所选日期没有录入或修改权限。")
    if (
        effective_role == "entry"
        and record_type == "global"
        and record_key in {"cash_position", "cash_balance"}
    ):
        raise HTTPException(status_code=403, detail="现金余额表只对修改权限和管理员开放。")
    record = get_record(db, dataset_id, record_type, record_key)
    before_payload = record.payload if record else None
    before_version = record.version if record else 0
    is_inventory = record_type == "global" and record_key == "inventory"
    document_inventory = is_inventory and (has_documents(body.payload) or has_documents(before_payload))
    write_payload = normalize_payload(normalize_fixed_expense_cash_flags(body.payload), before_payload)

    if record and (body.expected_version not in {0, record.version}
                   or (document_inventory and body.expected_version != record.version)):
        conflict = SyncConflict(
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
            local_version=body.expected_version,
            cloud_version=record.version,
            local_payload=write_payload,
            cloud_payload=record.payload,
        )
        db.add(conflict)
        db.commit()
        raise HTTPException(status_code=409, detail={"conflict_id": conflict.id, "message": "记录版本冲突。"})

    if is_inventory:
        if effective_role == "entry" and (before_payload or {}).get("item_settings", []) != write_payload.get("item_settings", []):
            raise HTTPException(status_code=403, detail="安全库存设置仅对修改权限和管理员开放。")
        validate_inventory(write_payload, before_payload,
                           today=utcnow().astimezone(_business_timezone()).date().isoformat())
    if record_type == "day":
        write_payload = _normalize_customer_counts(
            write_payload, record_key
        )
    is_cash_record = (
        record_type == "global" and record_key in {"cash_position", "cash_balance"}
    )
    if is_cash_record:
        write_payload = _canonical_cash_payload(
            write_payload,
            previous_payload=(record.payload if record and not record.is_deleted else None),
            strict_types=False,
        )
        _protect_locked_cash_forces(
            record.payload if record and not record.is_deleted else None,
            write_payload,
        )
    # A client checksum may have been calculated before legacy aliases were
    # reconciled.  Store and audit the checksum of the canonical payload.
    write_checksum = payload_checksum(write_payload)
    timing_update: dict[str, Any] | None = None
    if document_inventory:
        timing = _timing_row(db, dataset_id, record_type, record_key)
        field_times = inventory_clock_times(before_payload or {}, write_payload,
            dict(timing.detail_field_times or {}) if timing else {},
            now=utcnow(), fallback=_timing_fallback(record, utcnow()))
        if effective_role == "entry":
            guard_entry_inventory(before_payload or {}, write_payload,
                now=utcnow(), fallback=_timing_fallback(record, utcnow()), field_times=field_times)
        timing_update = {
            "detail_started_at": timing.detail_started_at if timing else None,
            "detail_item_times": dict(timing.detail_item_times or {}) if timing else {},
            "detail_field_times": field_times,
            "store_a_at": timing.store_a_at if timing else None,
            "store_b_at": timing.store_b_at if timing else None,
            "revenue_at": timing.revenue_at if timing else None,
        }
    elif effective_role == "entry":
        # Server time, rather than the client-provided occurred_at, determines
        # every deadline.  The latter remains useful for audit display only.
        write_payload, timing_update = _entry_timing_updates(
            db,
            record=record if record and not record.is_deleted else None,
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
            old_payload=(record.payload or {}) if record and not record.is_deleted else {},
            new_payload=write_payload,
            now=utcnow(),
        )
        write_payload = normalize_fixed_expense_cash_flags(write_payload)
        write_checksum = payload_checksum(write_payload)

    elif record_type == "day":
        # Admin/editor writes are unrestricted, but still establish customer
        # first-save timestamps so later unrelated writes do not reopen them.
        timing = _timing_row(db, dataset_id, record_type, record_key)
        field_times = _customer_clock_updates(
            dict(timing.detail_field_times or {}) if timing else {},
            (record.payload or {}) if record and not record.is_deleted else {},
            write_payload, record_key, _timing_fallback(record, utcnow()), utcnow(), enforce=False,
        )
        if any(key.startswith("customer:") for key in field_times):
            timing_update = {
                "detail_started_at": timing.detail_started_at if timing else None,
                "detail_item_times": dict(timing.detail_item_times or {}) if timing else {},
                "detail_field_times": field_times,
                "store_a_at": timing.store_a_at if timing else None,
                "store_b_at": timing.store_b_at if timing else None,
                "revenue_at": timing.revenue_at if timing else None,
            }

    if is_inventory:
        _guard_inventory_db(db, dataset_id, before_payload, write_payload)

    no_change = (
        record
        and not record.is_deleted
        and record.payload == write_payload
        and record.checksum == write_checksum
    )
    if no_change:
        return record_out(record)

    sequence = next_sequence(db, dataset_id)
    if not record:
        record = SyncRecord(
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
            payload=write_payload,
            checksum=write_checksum,
            version=1,
            sequence=sequence,
            is_deleted=False,
        )
        db.add(record)
        action = "create"
    else:
        record.payload = write_payload
        record.checksum = write_checksum
        record.version += 1
        record.sequence = sequence
        record.is_deleted = False
        action = "update"

    add_audit(
        db,
        user=user,
        dataset_id=dataset_id,
        record_type=record_type,
        record_key=record_key,
        action=action,
        source=body.source,
        event_id=body.event_id,
        device_id=body.device_id,
        from_version=before_version,
        to_version=record.version,
        sequence=sequence,
        before_payload=before_payload,
        after_payload=write_payload,
        checksum=write_checksum,
        occurred_at=body.occurred_at,
    )
    if timing_update is not None:
        _persist_entry_timing(
            db,
            dataset_id=dataset_id,
            record_type=record_type,
            record_key=record_key,
            update=timing_update,
        )
    db.commit()
    db.refresh(record)
    return record_out(record)


@app.post("/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}/delete")
def delete_record(
    dataset_id: str,
    record_type: str,
    record_key: str,
    body: RecordDelete,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id, for_update=True)
    effective_role = _effective_record_role(
        db, user, dataset_id, record_type, record_key, None, now=utcnow()
    )
    if effective_role not in {"admin", "editor", "entry"}:
        raise HTTPException(status_code=403, detail="当前账号在所选日期没有录入或修改权限。")
    if (
        effective_role == "entry"
        and record_type == "global"
        and record_key in {"cash_position", "cash_balance"}
    ):
        raise HTTPException(status_code=403, detail="现金余额表只对修改权限和管理员开放。")
    record = get_record(db, dataset_id, record_type, record_key)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在。")
    if body.expected_version not in {0, record.version}:
        raise HTTPException(status_code=409, detail="记录版本冲突。")
    if record.is_deleted:
        return record_out(record)
    if record_type == "global" and record_key == "inventory" and has_documents(record.payload):
        raise HTTPException(status_code=403, detail="库存单据需保留记录，不能删除整表；请作废入／出库单或新增盘点单纠正。")
    if (
        record_type == "global"
        and record_key in {"cash_position", "cash_balance"}
        and _locked_cash_forces(record.payload)
    ):
        raise HTTPException(
            status_code=403,
            detail="包含系统锁定的余额强制修改记录，不能删除整张现金余额表。",
        )
    if effective_role == "entry":
        # The entry UI edits individual income/detail values via PUT, where
        # every slot/item is checked against its own clock. Deleting the whole
        # JSON record would otherwise erase older locked items together with a
        # newly-added one and bypass those independent deadlines.
        raise HTTPException(
            status_code=403,
            detail="录入权限不能删除整日记录；请在各项目自己的 30 分钟修改时间内修改。",
        )
    sequence = next_sequence(db, dataset_id)
    before_payload = record.payload
    before_version = record.version
    record.is_deleted = True
    record.version += 1
    record.sequence = sequence
    add_audit(
        db,
        user=user,
        dataset_id=dataset_id,
        record_type=record_type,
        record_key=record_key,
        action="delete",
        source=body.source,
        event_id=body.event_id,
        device_id=body.device_id,
        from_version=before_version,
        to_version=record.version,
        sequence=sequence,
        before_payload=before_payload,
        after_payload=None,
        checksum=record.checksum,
        occurred_at=body.occurred_at,
    )
    db.commit()
    db.refresh(record)
    return record_out(record)


@app.get("/api/v1/datasets/{dataset_id}/changes")
def changes(dataset_id: str, after_sequence: int = 0, limit: int = Query(default=500, le=5000), user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    authorized_dataset(db, user, dataset_id)
    rows = db.scalars(
        select(SyncRecord)
        .where(SyncRecord.dataset_id == dataset_id, SyncRecord.sequence > after_sequence)
        .order_by(SyncRecord.sequence, SyncRecord.id)
        .limit(limit + 1)
    ).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_value = max([after_sequence] + [item.sequence for item in items])
    return {"items": [record_out(item) for item in items], "next_sequence": next_value, "has_more": has_more}


@app.get("/api/v1/audit")
def audit_logs(
    dataset_id: str,
    hours: int = Query(default=AUDIT_RETENTION_DAYS * 24, ge=1, le=AUDIT_RETENTION_DAYS * 24),
    limit: int = Query(default=500, le=5000),
    start_date: date | None = None,
    end_date: date | None = None,
    user: AppUser = Depends(require_change_permission),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    authorized_dataset(db, user, dataset_id)
    # Opportunistic cleanup keeps the retention promise even on installations
    # that do not restart the API regularly.
    purge_expired_audit_logs(db)
    db.commit()
    cutoff = utcnow() - timedelta(hours=min(hours, AUDIT_RETENTION_DAYS * 24))
    conditions = [AuditLog.dataset_id == dataset_id, AuditLog.created_at >= cutoff]
    if start_date is not None:
        local_start = datetime.combine(start_date, datetime.min.time(), tzinfo=_business_timezone())
        conditions.append(AuditLog.created_at >= local_start.astimezone(timezone.utc))
    if end_date is not None:
        local_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=_business_timezone())
        conditions.append(AuditLog.created_at < local_end.astimezone(timezone.utc))
    rows = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    ).all()
    return [audit_out(row) for row in rows]


def _delete_audit_rows(
    db: Session,
    *,
    user: AppUser,
    dataset_id: str | None = None,
    audit_ids: list[str] | None = None,
    before: datetime | None = None,
) -> int:
    if dataset_id:
        authorized_dataset(db, user, dataset_id)
    stmt = delete(AuditLog)
    conditions = []
    if dataset_id:
        conditions.append(AuditLog.dataset_id == dataset_id)
    if audit_ids:
        conditions.append(AuditLog.id.in_(list(dict.fromkeys(audit_ids))))
    if before is not None:
        cutoff = _as_utc(before)
        if cutoff is not None:
            conditions.append(AuditLog.created_at < cutoff)
    if not conditions:
        raise HTTPException(status_code=422, detail="请指定要删除的修改记录。")
    result = db.execute(stmt.where(*conditions))
    db.commit()
    return int(result.rowcount or 0)


@app.delete("/api/v1/audit/{audit_id}")
def delete_audit_log(
    audit_id: str,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deleted = _delete_audit_rows(db, user=user, audit_ids=[audit_id])
    if not deleted:
        raise HTTPException(status_code=404, detail="修改记录不存在。")
    return {"deleted": True, "deleted_count": deleted, "audit_id": audit_id}


@app.delete("/api/v1/audit")
def delete_audit_logs(
    dataset_id: str | None = None,
    before: datetime | None = None,
    audit_id: list[str] | None = Query(default=None),
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deleted = _delete_audit_rows(
        db, user=user, dataset_id=dataset_id, audit_ids=audit_id, before=before
    )
    return {"deleted": True, "deleted_count": deleted, "dataset_id": dataset_id}


@app.post("/api/v1/audit/delete")
def delete_audit_logs_body(
    body: AuditDeleteBody,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    deleted = _delete_audit_rows(
        db,
        user=user,
        dataset_id=body.dataset_id,
        audit_ids=body.audit_ids,
        before=body.before,
    )
    return {"deleted": True, "deleted_count": deleted, "dataset_id": body.dataset_id}


@app.get("/api/v1/conflicts")
def list_conflicts(
    dataset_id: str,
    pending_only: bool = True,
    limit: int = Query(default=500, le=5000),
    _: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(SyncConflict).where(SyncConflict.dataset_id == dataset_id)
    if pending_only:
        stmt = stmt.where(SyncConflict.status == "pending")
    rows = db.scalars(stmt.order_by(SyncConflict.created_at.desc()).limit(limit)).all()
    return [conflict_out(row) for row in rows]


@app.post("/api/v1/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    body: ConflictResolve,
    user: AppUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conflict = db.get(SyncConflict, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="冲突不存在。")
    if conflict.status != "pending":
        return conflict_out(conflict)
    authorized_dataset(
        db, user, conflict.dataset_id, write=True, for_update=True
    )
    record = get_record(db, conflict.dataset_id, conflict.record_type, conflict.record_key)
    if not record:
        raise HTTPException(status_code=404, detail="冲突对应记录不存在。")
    before_payload = record.payload
    before_version = record.version
    if body.resolution == "use_local":
        chosen_payload = normalize_payload(conflict.local_payload or {}, before_payload)
        if record.record_type == "global" and record.record_key == "inventory":
            validate_inventory(chosen_payload, before_payload,
                               today=utcnow().astimezone(_business_timezone()).date().isoformat())
            _guard_inventory_db(db, conflict.dataset_id, before_payload, chosen_payload)
        if record.record_type == "global" and record.record_key in {"cash_position", "cash_balance"}:
            chosen_payload = _canonical_cash_payload(
                chosen_payload, previous_payload=before_payload, strict_types=False
            )
            _protect_locked_cash_forces(before_payload, chosen_payload)
        record.payload = chosen_payload
        record.checksum = payload_checksum(chosen_payload)
        record.version += 1
        record.is_deleted = False
    elif body.resolution == "merged":
        chosen_payload = normalize_payload(body.merged_payload or {}, before_payload)
        if record.record_type == "global" and record.record_key == "inventory":
            validate_inventory(chosen_payload, before_payload,
                               today=utcnow().astimezone(_business_timezone()).date().isoformat())
            _guard_inventory_db(db, conflict.dataset_id, before_payload, chosen_payload)
        if record.record_type == "global" and record.record_key in {"cash_position", "cash_balance"}:
            chosen_payload = _canonical_cash_payload(
                chosen_payload, previous_payload=before_payload, strict_types=False
            )
            _protect_locked_cash_forces(before_payload, chosen_payload)
        record.payload = chosen_payload
        record.checksum = payload_checksum(chosen_payload)
        record.version += 1
        record.is_deleted = False
    elif body.resolution == "use_cloud":
        chosen_payload = record.payload
    else:
        raise HTTPException(status_code=422, detail="resolution 必须是 use_local/use_cloud/merged。")
    sequence = next_sequence(db, conflict.dataset_id)
    record.sequence = sequence
    conflict.status = "resolved"
    conflict.resolution = body.resolution
    conflict.note = body.note or ""
    conflict.resolved_at = utcnow()
    add_audit(
        db,
        user=user,
        dataset_id=conflict.dataset_id,
        record_type=conflict.record_type,
        record_key=conflict.record_key,
        action="conflict_resolved",
        source="cloud",
        event_id="",
        device_id="",
        from_version=before_version,
        to_version=record.version,
        sequence=sequence,
        before_payload=before_payload,
        after_payload=chosen_payload,
        checksum=record.checksum,
        occurred_at=utcnow(),
    )
    db.commit()
    db.refresh(conflict)
    return conflict_out(conflict)
