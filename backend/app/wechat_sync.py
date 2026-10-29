from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from datetime import date, datetime, timezone
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .money import decimal_value, money, money_text as _exact_money_text
from .excel_io import payload_checksum
from .models import AppUser, AuditLog, Dataset, SyncRecord
from .store_settings import merchant_for_store, payment_status
from .wechat_pay import WeChatPayClient, WeChatPayError, summarize_rows


PAYMENT_BREAKDOWN_FIELDS = (
    "A店现金", "B店现金",
    "A店微信增加", "A店微信自动", "A店微信覆盖", "A店支付宝增加", "A店支付宝覆盖",
    "B店微信增加", "B店微信自动", "B店微信覆盖", "B店支付宝增加", "B店支付宝覆盖",
    "学生外卖", "A店外卖", "B店外卖",
)

# Older desktop releases used both ``YYYY/MM/DD`` and Chinese date strings,
# and one early cloud importer could put several daily rows under a single
# non-date record key.  Keep the compatibility parser local to the sync path so
# the canonical API contract can remain YYYY-MM-DD.
_DAY_TEXT_RE = re.compile(
    r"^\s*(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})"
    r"\s*(?:日)?(?:$|[T\s])"
)
_LEGACY_DAY_FIELDS = {
    "日期", "收益", "总金额", "收入", "总收入", "A店收入", "B店收入", "学生外卖", "A店外卖", "B店外卖",
    "总客人数", "食材成本", "佐料成本", "水电", "其他",
}


def _entered(value: Any) -> bool:
    text = str(value if value is not None else "").strip()
    return bool(text and text.lower() != "none")


def money_text(value: Any) -> str:
    try:
        return _exact_money_text(value, limit=None)
    except ValueError as exc:
        raise WeChatPayError(f"金额无效：{exc}") from exc


def _num(value: Any) -> Decimal:
    # Saved channel totals may aggregate many individually capped payments.
    try:
        return money(value, limit=None)
    except ValueError as exc:
        raise WeChatPayError(f"账本金额无效：{exc}") from exc


def _canonical_day(value: Any) -> str:
    """Return a calendar date in ISO form without timezone conversion."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    match = _DAY_TEXT_RE.match(text)
    if not match:
        return text
    try:
        return date(
            int(match.group(1)), int(match.group(2)), int(match.group(3))
        ).isoformat()
    except ValueError:
        return text


def _day_rows(payload: Any, record_key: str = "") -> list[dict[str, Any]]:
    """Read daily rows from both current and very old bare-row payloads."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("daily")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    if any(field in payload for field in _LEGACY_DAY_FIELDS):
        row = deepcopy(payload)
        if not _entered(row.get("日期")) and _canonical_day(record_key):
            row["日期"] = record_key
        return [row]
    return []


def _legacy_revenue(row: Any) -> Decimal | None:
    """Read total income from current or legacy total-only columns."""
    if not isinstance(row, dict):
        return None
    # A non-zero raw channel/cash field is a newer, more specific source than
    # a stale total-only value left by an older desktop build.  Resolve it
    # first so ``总金额=2539`` plus a real split does not resurrect 2539.
    if _has_breakdown(row):
        return money(
            (_num(row.get("A店现金")) if _entered(row.get("A店现金")) else Decimal("0"))
            + (_num(row.get("B店现金")) if _entered(row.get("B店现金")) else Decimal("0"))
            + _effective_wechat(row, "A店")
            + _effective_alipay(row, "A店")
            + _effective_wechat(row, "B店")
            + _effective_alipay(row, "B店")
            + _num(row.get("学生外卖")) + _num(row.get("A店外卖")) + _num(row.get("B店外卖")),
            limit=None,
        )
    saw_value = False
    for field in ("收益", "总金额", "收入", "总收入"):
        if not _entered(row.get(field)):
            continue
        saw_value = True
        value = _num(row.get(field))
        if abs(value) > Decimal("0.000000001"):
            return value
    store_a = _num(row.get("A店收入")) if _entered(row.get("A店收入")) else Decimal("0")
    store_b = _num(row.get("B店收入")) if _entered(row.get("B店收入")) else Decimal("0")
    if abs(store_a) > Decimal("0.000000001") or abs(store_b) > Decimal("0.000000001"):
        return store_a + store_b + _num(row.get("学生外卖"))
    # A transitional build exposed only the aggregate cash/online columns.
    # They are derived values, but still carry the real legacy total when the
    # direct total and per-store columns are absent.
    total_cash = _num(row.get("总现金")) if _entered(row.get("总现金")) else Decimal("0")
    total_online = _num(row.get("总线上")) if _entered(row.get("总线上")) else Decimal("0")
    if abs(total_cash) > Decimal("0.000000001") or abs(total_online) > Decimal("0.000000001"):
        return total_cash + total_online
    if _entered(row.get("总现金")) or _entered(row.get("总线上")):
        saw_value = True
    return Decimal("0") if saw_value else None


def _has_breakdown(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    # A店收入/B店收入/总现金/总线上 are derived columns in the new schema.
    # Older releases sometimes persisted only those columns; treating them as
    # editable payment inputs would make an API=0 sync recalculate the row to
    # zero and erase the legacy total.  Recalculation is justified only when a
    # raw cash or channel field is present.
    return any(
        abs(_num(row.get(field))) > Decimal("0.000000001")
        for field in PAYMENT_BREAKDOWN_FIELDS
    )


def _merge_nonempty_row(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Coalesce duplicate legacy rows without allowing zero to erase data."""
    result = deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if key == "日期":
            if not _entered(result.get(key)) and _entered(value):
                result[key] = deepcopy(value)
            continue
        if not _entered(value):
            continue
        old = result.get(key)
        if not _entered(old):
            result[key] = deepcopy(value)
            continue
        # This merge also sees dates, notes and nested details. Only compare
        # genuinely numeric values; financial calculations below stay strict.
        try:
            old_number, new_number = decimal_value(old, limit=None), decimal_value(value, limit=None)
        except ValueError:
            continue
        if old_number == 0 and new_number != 0:
            result[key] = deepcopy(value)
    # A legacy row may have stored the real value only as 总金额/收入.
    legacy = _legacy_revenue(result)
    if legacy is not None and (
        not _entered(result.get("收益")) or abs(_num(result.get("收益"))) <= Decimal("0.000000001")
    ):
        result["收益"] = money_text(legacy)
    return result


def _effective_wechat(row: dict[str, Any], prefix: str) -> Decimal:
    manual = row.get(f"{prefix}微信覆盖")
    automatic = row.get(f"{prefix}微信自动")
    added = row.get(f"{prefix}微信增加")
    if _entered(manual):
        return _num(manual)
    if _entered(automatic):
        return _num(automatic) + _num(added)
    return _num(added)


def _effective_alipay(row: dict[str, Any], prefix: str) -> Decimal:
    manual = row.get(f"{prefix}支付宝覆盖")
    return _num(manual) if _entered(manual) else _num(row.get(f"{prefix}支付宝增加"))


def recalc_revenue_breakdown(row: dict[str, Any]) -> dict[str, Any]:
    cash_a = _num(row.get("A店现金"))
    cash_b = _num(row.get("B店现金"))
    a_wechat = _effective_wechat(row, "A店")
    a_alipay = _effective_alipay(row, "A店")
    b_wechat = _effective_wechat(row, "B店")
    b_alipay = _effective_alipay(row, "B店")
    a_takeout = _num(row.get("A店外卖"))
    b_takeout = _num(row.get("B店外卖"))
    student_takeout = _num(row.get("学生外卖"))
    a_revenue = cash_a + a_wechat + a_alipay + a_takeout
    b_revenue = cash_b + b_wechat + b_alipay + b_takeout
    row["总现金"] = money_text(cash_a + cash_b)
    row["总线上"] = money_text(a_wechat + a_alipay + b_wechat + b_alipay + a_takeout + b_takeout + student_takeout)
    row["A店收入"] = money_text(a_revenue)
    row["B店收入"] = money_text(b_revenue)
    row["收益"] = money_text(a_revenue + b_revenue + student_takeout)
    return row


def _next_sequence(db: Session, dataset_id: str) -> int:
    record_max = db.scalar(select(func.max(SyncRecord.sequence)).where(SyncRecord.dataset_id == dataset_id))
    audit_max = db.scalar(select(func.max(AuditLog.sequence)).where(AuditLog.dataset_id == dataset_id))
    return int(max(record_max or 0, audit_max or 0)) + 1


def _matching_row_indexes(record: SyncRecord, day: str) -> tuple[list[dict[str, Any]], list[int]]:
    payload = record.payload if isinstance(record.payload, dict) else {}
    rows = _day_rows(payload, str(record.record_key or ""))
    record_day = _canonical_day(record.record_key)
    indexes: list[int] = []
    for index, row in enumerate(rows):
        # A single row without a date inherits a canonical/date-alias key.  A
        # multi-row legacy payload must have an explicit date, otherwise we
        # would risk assigning another day's income to this bill.
        fallback = record_day if len(rows) == 1 else ""
        row_day = _canonical_day(row.get("日期") or fallback)
        if row_day == day:
            indexes.append(index)
    return rows, indexes


def _find_day_record_matches(
    db: Session, dataset_id: str, day: str
) -> list[tuple[SyncRecord, list[dict[str, Any]], list[int], int]]:
    """Lock and find every cloud record that represents ``day``.

    The exact canonical key is preferred, then a date-alias key, then a
    multi-day aggregate whose payload contains the date.  Returning all
    matches lets the caller coalesce a legacy non-zero row into a newer empty
    placeholder instead of creating a second record that masks it.
    """
    canonical = _canonical_day(day)
    records = db.scalars(
        select(SyncRecord)
        .where(
            SyncRecord.dataset_id == dataset_id,
            SyncRecord.record_type == "day",
        )
        .order_by(SyncRecord.sequence, SyncRecord.id)
        .with_for_update()
    ).all()
    matches: list[tuple[tuple[Any, ...], SyncRecord, list[dict[str, Any]], list[int], int]] = []
    for record in records:
        rows, indexes = _matching_row_indexes(record, canonical)
        key_day = _canonical_day(record.record_key)
        if str(record.record_key or "") == canonical:
            key_rank = 0
        elif key_day == canonical:
            key_rank = 1
        elif indexes:
            key_rank = 2
        else:
            continue
        # Active rows win over tombstones; among same-key rows the canonical
        # identity wins.  A non-zero matching legacy row is retained when an
        # older import also left a zero placeholder.
        has_nonzero = any(
            _legacy_revenue(rows[index]) is not None
            and abs(_num(_legacy_revenue(rows[index]))) > Decimal("0.000000001")
            for index in indexes
        )
        score = (
            1 if record.is_deleted else 0,
            key_rank,
            0 if has_nonzero else 1,
            -int(record.sequence or 0),
            -int(record.version or 0),
            str(record.id or ""),
        )
        matches.append((score, record, rows, indexes, key_rank))
    matches.sort(key=lambda item: item[0])
    # A tombstoned row represents an intentional deletion.  Only fall back to
    # it when there is no active representation of this date; otherwise a
    # deleted non-zero legacy row must not be resurrected by synchronization.
    active_matches = [item for item in matches if not item[1].is_deleted]
    if active_matches:
        matches = active_matches
    return [(record, rows, indexes, key_rank) for _, record, rows, indexes, key_rank in matches]


def _record_for_update(db: Session, dataset_id: str, day: str) -> SyncRecord | None:
    """Backward-compatible single-record helper used by older callers/tests."""
    matches = _find_day_record_matches(db, dataset_id, _canonical_day(day))
    return matches[0][0] if matches else None


def _preferred_row_index(rows: list[dict[str, Any]], indexes: list[int]) -> int | None:
    if not indexes:
        return None
    # Keep a non-zero manually-entered/legacy total when duplicate rows exist;
    # an empty API placeholder must never become the authoritative row.
    for index in reversed(indexes):
        value = _legacy_revenue(rows[index])
        if value is not None and abs(_num(value)) > Decimal("0.000000001"):
            return index
    return indexes[-1]


def _prepare_day_payload(
    record: SyncRecord | None,
    matches: list[tuple[SyncRecord, list[dict[str, Any]], list[int], int]],
    day: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a payload containing the selected day while preserving siblings."""
    source = record.payload if record and isinstance(record.payload, dict) else {}
    payload = deepcopy(source)
    rows = _day_rows(payload, str(record.record_key or "") if record else day)
    # ``_day_rows`` returns copies for a bare legacy row, so all writes below
    # are isolated from the SQLAlchemy JSON object until assignment at the end.
    rows = [deepcopy(row) for row in rows]
    primary_indexes: list[int] = []
    if record:
        for candidate, candidate_rows, candidate_indexes, _ in matches:
            if candidate.id == record.id:
                primary_indexes = candidate_indexes
                # If a candidate payload was a bare row, rows already contains
                # that row; otherwise preserve the exact current payload rows.
                if candidate_rows and not rows:
                    rows = [deepcopy(row) for row in candidate_rows]
                break

    target_index = _preferred_row_index(rows, primary_indexes)
    if target_index is None:
        # A canonical key may have an empty daily list.  It is still the right
        # record to update, but the target row must be appended.
        target_index = len(rows)
        rows.append({"日期": day})
    else:
        target = rows[target_index]
        # Coalesce duplicate same-day rows within the primary payload first.
        duplicate_indexes = [
            index for index, row in enumerate(rows)
            if index != target_index
            and _canonical_day(row.get("日期") or (day if len(rows) == 1 else "")) == day
        ]
        for index in duplicate_indexes:
            target = _merge_nonempty_row(target, rows[index])
        if duplicate_indexes:
            duplicate_set = set(duplicate_indexes)
            compacted: list[dict[str, Any]] = []
            compacted_target_index: int | None = None
            for index, candidate in enumerate(rows):
                if index in duplicate_set:
                    continue
                if index == target_index:
                    compacted_target_index = len(compacted)
                    compacted.append(target)
                else:
                    compacted.append(candidate)
            rows = compacted
            target_index = compacted_target_index if compacted_target_index is not None else len(rows)
            if target_index == len(rows):
                rows.append(target)

    target = deepcopy(rows[target_index])
    # Merge matching rows from date aliases and aggregate legacy records.  Do
    # not copy their sibling dates; those records remain independently visible.
    for candidate, candidate_rows, candidate_indexes, _ in matches:
        if record is not None and candidate.id == record.id:
            continue
        for index in candidate_indexes:
            target = _merge_nonempty_row(target, candidate_rows[index])
    target["日期"] = day
    rows[target_index] = target
    payload["daily"] = rows
    return payload, target


def wechat_status(dataset_id: str) -> dict[str, Any]:
    return {
        "configured": any(payment_status(dataset_id, store).get("configured") for store in ("A", "B")),
        "dataset_id": dataset_id,
        "sync_time": f"{config.WECHAT_SYNC_HOUR:02d}:{config.WECHAT_SYNC_MINUTE:02d}",
        "timezone": config.WECHAT_TIMEZONE,
        "amount_mode": config.WECHAT_AMOUNT_MODE,
        "store_a": payment_status(dataset_id, "A"),
        "store_b": payment_status(dataset_id, "B"),
    }


def collect_store_totals(dataset_id: str, day: str) -> dict[str, Any]:
    if config.WECHAT_AMOUNT_MODE not in {"order", "settlement"}:
        raise WeChatPayError("WECHAT_AMOUNT_MODE 只能是 order 或 settlement。")
    stores: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for store in ("A", "B"):
        merchant = merchant_for_store(dataset_id, store)
        if merchant is None:
            continue
        bill = WeChatPayClient(merchant).request_trade_bill(day)
        stores[store] = summarize_rows(bill.rows, mode=config.WECHAT_AMOUNT_MODE)
        hashes[store] = bill.sha1
    if not stores:
        raise WeChatPayError("当前账本的两家店都还没有配置微信支付商户资料。")
    return {"stores": stores, "hashes": hashes, "unmatched_count": 0, "mode": "per-store"}


def _migrate_legacy_auto_override(row: dict[str, Any], prefix: str) -> None:
    """v25曾把微信API金额写进“微信覆盖”。检测到旧同步标记时迁移到“微信自动”。"""
    if _entered(row.get(f"{prefix}微信自动")):
        return
    if not _entered(row.get("微信账单同步时间")):
        return
    if _entered(row.get(f"{prefix}微信覆盖")):
        row[f"{prefix}微信自动"] = row.get(f"{prefix}微信覆盖")
        row[f"{prefix}微信覆盖"] = ""


def apply_wechat_sync(
    db: Session,
    *,
    dataset_id: str,
    bill_date: str,
    actor: AppUser,
    source: str = "wechat_bill",
    force: bool = False,
) -> dict[str, Any]:
    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id).with_for_update())
    if dataset is None:
        raise WeChatPayError("微信同步指定的账本不存在。")

    bill_date = _canonical_day(bill_date)
    collected = collect_store_totals(dataset_id, bill_date)
    matches = _find_day_record_matches(db, dataset_id, bill_date)
    record = matches[0][0] if matches else None
    # A zero-value bill must not create a new placeholder record.  This is
    # particularly important for old ledgers whose real total is stored under
    # a non-date aggregate key: creating a canonical zero row would otherwise
    # hide that value in clients which only read the newest record.
    has_nonzero_api = any(
        abs(_num(summary.get("amount"))) > Decimal("0.000000001")
        for summary in collected.get("stores", {}).values()
    )
    if (record is None or record.is_deleted) and not has_nonzero_api:
        skipped = [
            f"{'A店' if store == 'A' else 'B店'}(API为0)"
            for store, summary in collected.get("stores", {}).items()
            if abs(_num(summary.get("amount"))) <= Decimal("0.000000001")
        ]
        return {
            "changed": False,
            "dataset_id": dataset_id,
            "bill_date": bill_date,
            "record_version": int(record.version) if record is not None else 0,
            "revenue": "0.00",
            "stores": collected["stores"],
            "skipped_stores": skipped,
            "mode": collected["mode"],
            "force": bool(force),
        }
    before_payload = deepcopy(record.payload) if record else None
    before_version = int(record.version if record else 0)
    payload, row = _prepare_day_payload(record, matches, bill_date)
    previous_revenue = _legacy_revenue(row)
    # Normalize the legacy total before deciding whether a non-forced monthly
    # fill is allowed to write.  Without this, 收益=0 + 总金额=2539 would look
    # empty to the guard and be replaced by an API amount.
    if previous_revenue is not None and (
        not _entered(row.get("收益")) or abs(_num(row.get("收益"))) <= Decimal("0.000000001")
    ):
        row["收益"] = money_text(previous_revenue)
    had_breakdown = _has_breakdown(row)

    now_text = datetime.now(timezone.utc).isoformat()
    skipped_stores: list[str] = []
    wrote_api_value = False
    for store, summary in collected["stores"].items():
        prefix = "A店" if store == "A" else "B店"
        # A zero API result is never allowed to erase an existing value.
        if abs(_num(summary.get("amount"))) <= Decimal("0.000000001"):
            skipped_stores.append(f"{prefix}(API为0)")
            continue
        # Never replace a day that already has a non-zero manually entered
        # store total. API sync is allowed to fill only an empty/zero day.
        existing_store_revenue = row.get(f"{prefix}收入")
        existing_total = row.get("收益")
        has_existing_income = (
            (_entered(existing_store_revenue) and abs(_num(existing_store_revenue)) > Decimal("0.000000001"))
            or (
                # A newer zero placeholder may explicitly contain
                # ``A店收入=0``/``B店收入=0`` next to a legacy total-only
                # value.  When there is no raw payment detail, the non-zero
                # total is still authoritative and must not be replaced by a
                # non-forced API fill.
                _entered(existing_total)
                and abs(_num(existing_total)) > Decimal("0.000000001")
                and not had_breakdown
            )
        )
        if not force and source != "wechat_bill_auto" and has_existing_income:
            skipped_stores.append(prefix)
            continue
        _migrate_legacy_auto_override(row, prefix)
        row[f"{prefix}微信自动"] = money_text(summary["amount"])
        wrote_api_value = True
        if force or source == "wechat_bill_auto":
            # 强制更新和每日自动任务都以官方账单为准，清掉手动覆盖。
            row[f"{prefix}微信覆盖"] = ""
        row[f"{prefix}微信支付金额"] = money_text(summary["payment_amount"])
        row[f"{prefix}微信退款金额"] = money_text(summary["refund_amount"])
        row[f"{prefix}微信支付笔数"] = int(summary["payment_count"])
        row[f"{prefix}微信退款笔数"] = int(summary["refund_count"])
    row["微信账单日期"] = bill_date
    row["微信账单同步时间"] = now_text
    row["微信账单口径"] = config.WECHAT_AMOUNT_MODE
    row["微信账单SHA1"] = ";".join(
        f"{key}:{value}" for key, value in sorted(collected["hashes"].items()) if value
    )
    row["微信账单强制更新"] = bool(force)
    # Do not recalculate a total-only legacy row from an all-zero payment
    # breakdown.  The old desktop app stored its income in 总金额; preserving
    # that value is what keeps the dashboard and ledger consistent.  Once a
    # real split/API value exists, the normal shared-cost revenue calculation
    # remains authoritative.
    if wrote_api_value or had_breakdown or _has_breakdown(row):
        recalc_revenue_breakdown(row)
    elif previous_revenue is not None:
        row["收益"] = money_text(previous_revenue)
    elif not _entered(row.get("收益")):
        row["收益"] = "0.00"
    payload["daily"] = payload.get("daily") if isinstance(payload.get("daily"), list) else [row]
    # ``_prepare_day_payload`` already placed the target row in this list;
    # ensure the updated object is retained even when a malformed payload had
    # no list at all.
    rows = payload["daily"]
    target_seen = False
    for index, candidate in enumerate(rows):
        if isinstance(candidate, dict) and _canonical_day(candidate.get("日期")) == bill_date:
            rows[index] = row
            target_seen = True
            break
    if not target_seen:
        rows.append(row)
    payload["daily"] = rows
    checksum = payload_checksum(payload)

    if record and not record.is_deleted and record.payload == payload and record.checksum == checksum:
        return {
            "changed": False,
            "dataset_id": dataset_id,
            "bill_date": bill_date,
            "record_version": record.version,
            "revenue": row.get("收益", 0),
            "stores": collected["stores"],
            "skipped_stores": skipped_stores,
            "mode": collected["mode"],
            "force": bool(force),
        }

    sequence = _next_sequence(db, dataset_id)
    if record is None:
        record = SyncRecord(
            dataset_id=dataset_id,
            record_type="day",
            record_key=bill_date,
            payload=payload,
            checksum=checksum,
            version=1,
            sequence=sequence,
            is_deleted=False,
        )
        db.add(record)
        action = "create"
    else:
        record.payload = payload
        record.checksum = checksum
        record.version += 1
        record.sequence = sequence
        record.is_deleted = False
        action = "update"

    event_id = f"wechat-{bill_date}-{uuid4()}"
    audit_record_key = str(record.record_key or bill_date)
    db.add(
        AuditLog(
            dataset_id=dataset_id,
            record_type="day",
            record_key=audit_record_key,
            action=action,
            source=source,
            event_id=event_id,
            actor_user_id=actor.id,
            actor_username=actor.username,
            device_id="wechat-pay-api",
            from_version=before_version,
            to_version=record.version,
            sequence=sequence,
            before_payload=before_payload,
            after_payload=payload,
            checksum=checksum,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(record)
    return {
        "changed": True,
        "dataset_id": dataset_id,
        "bill_date": bill_date,
        "record_version": record.version,
        "revenue": row.get("收益", 0),
        "stores": collected["stores"],
        "skipped_stores": skipped_stores,
        "mode": collected["mode"],
        "force": bool(force),
    }
