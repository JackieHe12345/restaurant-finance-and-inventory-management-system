"""Inventory document validation; unchanged legacy rows are grandfathered.

This module deliberately does not normalize the payload: extensions and original
historical representations must survive every client and workbook round trip.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import math
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from .money import product, money, price_text, MoneyError

TABLES = ("entries", "adjustments", "overrides")
VOID_FIELDS = {"voided", "void_reason", "voided_at"}


def is_voided(row: dict) -> bool:
    value = row.get("voided")
    return value is True or value == 1 or str(value).lower() in {"true", "1"}


def fail(message: str) -> None:
    raise HTTPException(status_code=422, detail=f"库存单据：{message}")


def is_document(row: Any) -> bool:
    return isinstance(row, dict) and bool(row.get("document_id") or row.get("document_no"))


def has_documents(payload: Any) -> bool:
    return isinstance(payload, dict) and any(
        is_document(row) for key in TABLES for row in rows(payload, key)
    )


def rows(payload: Any, key: str) -> list:
    value = payload.get(key, []) if isinstance(payload, dict) else []
    return value if isinstance(value, list) else []


def row_id(row: Any) -> str:
    return str(row.get("id") or "") if isinstance(row, dict) else ""


def number(value: Any, label: str, *, positive: bool = False) -> Decimal:
    if value in (None, "") or isinstance(value, bool):
        fail(f"{label}必须填写有效数字。")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label}必须填写有效数字。")
    if not result.is_finite() or result.copy_abs() > Decimal("1e100") or result < 0 or (positive and result == 0):
        fail(f"{label}必须是{'大于零' if positive else '非负'}的有限数字。")
    return result


def stamp(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, AttributeError):
        fail(f"{label}须为 UTC ISO 时间。")


def identity(row: dict) -> tuple[str, str, str]:
    return (str(row.get("category") or row.get("分类") or "食材"),
            str(row.get("name") or row.get("名称") or "").strip(),
            str(row.get("unit") or row.get("单位") or "").strip())


def _validate_identity(row: dict) -> None:
    category, name, unit = identity(row)
    if category not in {"食材", "佐料"} or not name or not unit:
        fail("每行须填写食材／佐料分类、名称和单位。")


def _void(row: dict, table: str) -> None:
    if "voided" in row and not isinstance(row["voided"], bool):
        fail("voided 必须是布尔值。")
    if row.get("voided"):
        if table == "overrides":
            fail("盘点单不能作废，请新增盘点单纠正。")
        if not str(row.get("void_reason") or "").strip():
            fail("作废必须填写原因。")
        stamp(row.get("voided_at"), "作废时间")


def _validate_row(row: Any, table: str, *, today: str, restoration: bool, new: bool) -> None:
    if not isinstance(row, dict) or not row_id(row):
        fail("新增行必须具有唯一 id。")
    _validate_identity(row)
    quantity = number(row.get("quantity", row.get("数量")), "数量", positive=table != "overrides")
    day = str(row.get("date") or row.get("日期") or "")
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except ValueError:
        fail("业务日期必须是 YYYY-MM-DD。")
    document = is_document(row)
    if document:
        try:
            UUID(str(row.get("document_id") or ""))
        except ValueError:
            fail("document_id 必须是 UUID。")
        if not str(row.get("document_no") or "").strip():
            fail("必须填写单据编号。")
        stamp(row.get("recorded_at"), "记账时间")
        if new and not restoration and day != today:
            fail("新单据只能提交今天，请刷新日期后重试。")
    _void(row, table)
    if table == "entries":
        if row.get("source", "manual") != "manual":
            fail("自动采购应在原食材明细中修改，不能另存为库存入库单。")
        unknown = row.get("price_known") is False
        # Old unknown-cost receipts remain importable. Newly posted V2 receipts
        # require an explicit price (including a deliberate zero).
        if document and new and not restoration and unknown:
            fail("新入库单必须填写单价，包括零元入库。")
        if not unknown:
            price = number(row.get("unit_price", row.get("单价")), "入库单价")
            total = number(row.get("total", row.get("总价")), "入库总价")
            if money(total) != product(quantity, price):
                fail("入库总价须等于数量乘单价。")
        else:
            for field in ("unit_price", "total"):
                if row.get(field) not in (None, ""):
                    number(row[field], field)
    elif table == "adjustments":
        if row.get("kind", "loss") not in {"normal", "loss"}:
            fail("出库用途须为领用或损耗。")
    else:
        if not str(row.get("note") or "").strip():
            fail("盘点必须填写原因。")
        if "previous_quantity" in row:
            # A book balance can be negative in historical data.
            try:
                previous = Decimal(str(row["previous_quantity"]))
                if not previous.is_finite():
                    raise ValueError
            except (InvalidOperation, ValueError):
                fail("盘点账面数量必须是有限数字。")
        for field in ("unit_price", "total"):
            if row.get(field) not in (None, ""):
                number(row[field], field)
        if row.get("price_known") is True and row.get("unit_price") in (None, ""):
            fail("盘盈已定价时必须填写单价。")
    if "price_known" in row and not isinstance(row["price_known"], bool):
        fail("price_known 必须是布尔值。")


def validate_inventory(payload: dict, previous: dict | None, *, today: str, restoration: bool = False) -> None:
    previous = previous if isinstance(previous, dict) else {}
    document_mode = has_documents(previous) or has_documents(payload)
    old_ids = Counter(row_id(row) for key in TABLES for row in rows(previous, key) if row_id(row))
    new_ids = Counter(row_id(row) for key in TABLES for row in rows(payload, key) if row_id(row))
    for key, count in new_ids.items():
        if count > 1 and count > old_ids[key]:
            duplicated_documents = any(is_document(row) and row_id(row) == key
                                       for table in TABLES for row in rows(payload, table))
            if not restoration or duplicated_documents:
                fail("行 id 重复，不能重复提交同一行。")
    changed_documents = set()
    for table in TABLES:
        if table in payload and not isinstance(payload[table], list):
            if payload[table] != previous.get(table):
                fail(f"{table} 必须是数组。")
        old_rows, new_rows = rows(previous, table), rows(payload, table)
        old_by_id = {row_id(row): row for row in old_rows if row_id(row)}
        new_by_id = {row_id(row): row for row in new_rows if row_id(row)}
        if not restoration:
            for old in old_rows:
                if is_document(old) and row_id(old) not in new_by_id:
                    fail("已保存单据不能删除，请作废入／出库单，或新增盘点单纠正。")
        for row in new_rows:
            if row in old_rows:
                continue  # Preserve even malformed legacy rows byte-for-byte.
            if not isinstance(row, dict):
                fail("库存行必须是对象。")
            old = old_by_id.get(row_id(row))
            for field in ("document_id", "document_no", "recorded_at", "void_reason", "voided_at"):
                if field in row and not isinstance(row[field], str):
                    fail(f"{field} 必须是文本。")
            if document_mode and old is None and not is_document(row) and not restoration:
                fail("本账本已使用新版库存单据，请更新 App／刷新网页后再录入，不能用旧版无单号记录覆盖。")
            if old and is_voided(old) and not is_voided(row) and not restoration:
                fail("不能撤销已保存的作废操作。")
            if table == "entries" and row.get("voided") and row.get("source", "manual") != "manual":
                fail("自动采购只能在原食材明细中改正。")
            if old_ids[row_id(row)] > 1 and not restoration:
                fail("此历史行 id 重复，请先由管理员核对记录。")
            if is_document(row):
                changed_documents.add(row.get("document_id"))
            if old and is_document(old) and not restoration:
                if {k: v for k, v in old.items() if k not in VOID_FIELDS} != {k: v for k, v in row.items() if k not in VOID_FIELDS}:
                    fail("已保存单据不可直接修改，请作废后重新录入。")
                if old.get("voided") or not row.get("voided"):
                    fail("已保存单据仅能作废，不能撤销作废或改写记录。")
            # Voiding an untouched legacy row must not force repair of its
            # old invalid amounts, but still requires the new void metadata.
            only_void = old and {k: v for k, v in old.items() if k not in VOID_FIELDS} == {k: v for k, v in row.items() if k not in VOID_FIELDS}
            if only_void:
                _void(row, table)
            elif not restoration or is_document(row):
                _validate_row(row, table, today=today, restoration=restoration, new=old is None)
    # A multi-line document is one operation. Partial voids and document-id
    # reuse must not quietly turn it into several different operations.
    for document_id in changed_documents:
        group = [(table, row) for table in TABLES for row in rows(payload, table)
                 if isinstance(row, dict) and row.get("document_id") == document_id]
        if len({(table, row.get("date"), row.get("document_no"), row.get("recorded_at"), bool(row.get("voided")), row.get("void_reason", ""), row.get("voided_at", "")) for table, row in group}) != 1:
            fail("同一单据的日期、编号、时间和作废状态必须一致。")
        if not restoration:
            existing = [row for table in TABLES for row in rows(previous, table)
                        if isinstance(row, dict) and row.get("document_id") == document_id]
            if existing and {row_id(row) for row in existing} != {row_id(row) for _, row in group}:
                fail("已保存单据不能追加行，请创建新单据。")
    settings = rows(payload, "item_settings")
    if "item_settings" in payload and not isinstance(payload["item_settings"], list):
        fail("安全库存配置必须是数组。")
    old_settings = Counter(identity(row) for row in rows(previous, "item_settings") if isinstance(row, dict))
    new_settings = Counter(identity(row) for row in settings if isinstance(row, dict))
    if any(count > 1 and count > old_settings[key] for key, count in new_settings.items()):
        fail("同一食材、分类和单位的安全库存不能重复。")
    seen = set()
    for row in settings:
        if row in rows(previous, "item_settings"):
            if isinstance(row, dict):
                seen.add(identity(row))
            continue
        if not isinstance(row, dict):
            fail("安全库存配置无效。")
        _validate_identity(row)
        if identity(row) in seen:
            fail("同一食材、分类和单位的安全库存不能重复。")
        seen.add(identity(row))
        number(row.get("min_quantity"), "安全库存")


def inventory_clock_times(previous: dict, payload: dict, field_times: dict, *, now: datetime, fallback: datetime) -> dict:
    times = dict(field_times)
    for table in TABLES:
        old_ids = {row_id(row) for row in rows(previous, table)}
        for row in [*rows(previous, table), *rows(payload, table)]:
            if row_id(row):
                key = f"inventory:{table}:{row_id(row)}"
                times.setdefault(key, (fallback if row_id(row) in old_ids else now).isoformat())
    return times


def guard_entry_inventory(previous: dict, payload: dict, *, now: datetime, fallback: datetime, field_times: dict) -> None:
    """Entry users may append today; existing rows keep their 30-minute clock."""
    if rows(previous, "item_settings") != rows(payload, "item_settings"):
        raise HTTPException(status_code=403, detail="安全库存设置仅对修改权限和管理员开放。")
    for table in TABLES:
        for old in rows(previous, table):
            if old in rows(payload, table):
                continue
            saved = fallback
            key = f"inventory:{table}:{row_id(old)}"
            if field_times.get(key):
                saved = stamp(field_times[key], "首次保存时间")
            if (now - saved).total_seconds() >= 1800:
                raise HTTPException(status_code=403, detail="录入权限仅可在该库存记录保存后 30 分钟内作废或修改。")
    for key, old in previous.items():
        if key not in {*TABLES, "item_settings", "updated_at", "schema_version"} and payload.get(key) != old:
            raise HTTPException(status_code=403, detail="录入权限不能修改已有库存扩展配置。")
