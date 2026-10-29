"""Atomic administrative ingredient-name correction endpoints."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .money_routes import ExactMoneyRoute
from .money import price_text, decimal_value, MoneyError
from .database import get_db
from .models import AppUser, EntryTiming, InventoryNameCorrection, SyncRecord
from .security import current_user, require_admin
from .excel_io import payload_checksum
from .ingredient_corrections import plan_correction, stable_json
from .inventory_balance import _day, _canonical_daily_selection

router = APIRouter(prefix='/api/v1/datasets/{dataset_id}/inventory/name-corrections', route_class=ExactMoneyRoute)


class FinalQuantity(BaseModel):
    unit: str = Field(min_length=1, max_length=80)
    quantity: float = Field(ge=0, allow_inf_nan=False)
    unit_price: str | None = None

    @field_validator('unit_price', mode='before')
    @classmethod
    def exact_unit_price(cls, value):
        if value is None:
            return None
        if decimal_value(value, limit=None) < 0:
            raise ValueError('单价不能为负数')
        return price_text(value)

    @field_validator('quantity', mode='before')
    @classmethod
    def numeric_not_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError('数量和单价必须是数字')
        return value


class CorrectionSpec(BaseModel):
    category: Literal['食材', '佐料']
    old_name: str = Field(min_length=1, max_length=200)
    new_name: str = Field(min_length=1, max_length=200)
    final_quantities: list[FinalQuantity] = Field(default_factory=list, max_length=100)


class CorrectionApply(CorrectionSpec):
    preview_token: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)
    request_id: UUID
    confirm_merge: bool = False


def _spec(body):
    old, new = body.old_name.strip(), body.new_name.strip()
    if not old or not new or any(char in old + new for char in '\x00\r\n'):
        raise HTTPException(status_code=422, detail='品名不能为空，也不能含换行或控制字符。')
    units = [item.unit.strip() for item in body.final_quantities]
    if any(not unit for unit in units) or len(set(units)) != len(units):
        raise HTTPException(status_code=422, detail='实际库存单位不能为空或重复。')
    return body.category, old, new


def _rows(db, dataset_id):
    return list(db.scalars(select(SyncRecord).where(SyncRecord.dataset_id == dataset_id)
                           .order_by(SyncRecord.sequence, SyncRecord.id)).all())


def _snapshot(rows):
    return [{key: getattr(row, key) for key in ('id', 'record_type', 'record_key', 'version', 'sequence', 'is_deleted', 'payload')}
            for row in rows]


def _dates(row):
    if row['record_type'] != 'day' or row.get('is_deleted') or not isinstance(row['payload'], dict):
        return set()
    payload = row['payload']
    result = {_day(row['record_key'])}
    for table in ('daily', 'dishes'):
        for item in payload.get(table, []) if isinstance(payload.get(table), list) else []:
            if isinstance(item, dict):
                result.add(_day(item.get('日期') or row['record_key']))
    if not isinstance(payload.get('daily'), list):
        result.add(_day(payload.get('日期') or row['record_key']))
    return result - {''}


def _canonical_view(records):
    days = [row for row in records if row['record_type'] == 'day' and not row.get('is_deleted')]
    daily, sources = _canonical_daily_selection(days)
    by_key = {row['record_key']: row for row in days}
    dishes = {}
    for row in days:
        payload = row['payload']
        for item in payload.get('dishes', []) if isinstance(payload, dict) and isinstance(payload.get('dishes'), list) else []:
            if isinstance(item, dict):
                day = _day(item.get('日期') or row['record_key'])
                if day:
                    dishes[day] = item
    for day in set(daily) | set(dishes):
        selected = sources.get(day) or by_key.get(day)
        if selected is not None:
            payload = selected['payload']
            if not isinstance(payload, dict):
                dishes[day] = {'菜品数据': []}
                continue
            matches = [item for item in payload.get('dishes', []) if isinstance(item, dict)
                       and _day(item.get('日期') or selected['record_key']) == day] if isinstance(payload.get('dishes'), list) else []
            dishes[day] = matches[-1] if matches else {'菜品数据': []}
    return daily, dishes


def _write_set(records, payloads, preview):
    """Refresh only the shared-date connected component, preserving its order."""
    originals = {(row['record_type'], row['record_key']): row['payload'] for row in records}
    selected = {key for key, value in payloads.items() if value != originals.get(key)}
    dates = set().union(*(_dates(row) for row in records if (row['record_type'], row['record_key']) in selected)) if selected else set()
    while True:
        added = [row for row in records if not row.get('is_deleted') and row['record_type'] == 'day'
                 and _dates(row) & dates and (row['record_type'], row['record_key']) not in selected]
        if not added:
            break
        for row in added:
            selected.add((row['record_type'], row['record_key']))
            dates |= _dates(row)
    planned = [{**row, 'payload': payloads.get((row['record_type'], row['record_key']), row['payload'])} for row in records]
    next_sequence = max((row['sequence'] for row in records), default=0) + 1
    ranked = []
    for row in planned:
        key = row['record_type'], row['record_key']
        if key in selected:
            ranked.append({**row, 'sequence': next_sequence, 'version': row['version'] + 1})
            next_sequence += 1
        else:
            ranked.append(row)
    # Names have already been transformed in `planned`. This comparison is
    # intentionally full-field: revenue, costs, notes and dish titles must not
    # change merely because a corrected source receives a new sync sequence.
    if _canonical_view(planned) != _canonical_view(ranked):
        preview['blockers'].append('历史共享日期来源无法安全保序；更正会切换收入、采购或菜品来源，请先核对重复记录。')
        preview['can_apply'] = False
    refreshed = len(selected) - preview['summary']['records']
    if refreshed > 0:
        preview['warnings'].append(f'另有 {refreshed} 条共享日期来源仅刷新同步版本以保留原顺序，业务内容与原录入时间不变。')
    return selected


def _plan(rows, body, now):
    from . import main
    category, old, new = _spec(body)
    snapshot = _snapshot(rows)
    finals = [{**item.model_dump(), 'unit': item.unit.strip()} for item in body.final_quantities]
    try:
        preview, payloads = plan_correction(snapshot, category, old, new,
                                           now.astimezone(main._business_timezone()).date().isoformat(), finals, now)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=f'相关原始记录格式不完整，无法安全更正：{exc}') from exc
    if finals and any(row.record_type == 'global' and row.record_key == 'inventory' and row.is_deleted for row in rows):
        preview['blockers'].append('库存总表已被删除，请管理员先恢复并核对库存后再填写实际数量。')
        preview['can_apply'] = False
    selected = _write_set(snapshot, payloads, preview)
    return preview, payloads, selected


def _detail_positions(payload, key):
    from . import main
    result = []
    for row in main._daily_payload_rows(payload, key):
        day = str(row.get('日期') or key or '').strip()
        for field, category in (('食材明细', 'food'), ('佐料明细', 'spice'), ('其他明细', 'other'), ('其它明细', 'other')):
            counters = {}
            for item in main._detail_value_items(row.get(field)):
                base, _ = main._detail_item_base_and_label(item)
                ordinal = counters.get(base, 0)
                counters[base] = ordinal + 1
                result.append(f'{day}|{category}|{base}|{ordinal}')
    return result


def _migrate_timing(db, dataset_id, row, after):
    from . import main
    if row.record_type != 'day':
        return
    old_ids, new_ids = _detail_positions(row.payload, row.record_key), _detail_positions(after, row.record_key)
    if old_ids == new_ids:
        return
    if len(old_ids) != len(new_ids):
        raise HTTPException(status_code=422, detail='更正前后明细数量不同，无法保留原录入时钟。')
    timing = main._timing_row(db, dataset_id, 'day', row.record_key)
    if timing is None:
        timing = EntryTiming(dataset_id=dataset_id, record_type='day', record_key=row.record_key,
                             detail_item_times={}, detail_field_times={})
        db.add(timing)
    times = dict(timing.detail_item_times or {})
    fallback = main._timing_fallback(row, main.utcnow()).isoformat()
    for key in old_ids:
        times.setdefault(key, fallback)
    mapped = {}
    for old, new in zip(old_ids, new_ids):
        timestamp = times[old]
        if new not in mapped or main._as_utc(timestamp) < main._as_utc(mapped[new]):
            mapped[new] = timestamp
    times.update(mapped)
    timing.detail_item_times = times


@router.post('/preview')
def preview_correction(dataset_id: str, body: CorrectionSpec,
                       user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    from . import main
    if user.role not in {'admin', 'editor'}:
        raise HTTPException(status_code=403, detail='品名更正预览仅对修改权限和管理员开放。')
    main.authorized_dataset(db, user, dataset_id, for_update=True)
    preview, _, _ = _plan(_rows(db, dataset_id), body, main.utcnow())
    return preview


@router.post('/apply')
def apply_correction(dataset_id: str, body: CorrectionApply,
                     user: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    from . import main
    category, old, new = _spec(body)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail='请填写品名更正原因。')
    request_id = str(body.request_id)
    request = {**body.model_dump(mode='json'), 'category': category, 'old_name': old, 'new_name': new, 'reason': reason,
               'final_quantities': [{**item.model_dump(), 'unit': item.unit.strip()} for item in body.final_quantities]}
    request_hash = hashlib.sha256(stable_json(request).encode()).hexdigest()
    main.authorized_dataset(db, user, dataset_id, for_update=True)
    existing = db.scalar(select(InventoryNameCorrection).where(
        InventoryNameCorrection.dataset_id == dataset_id, InventoryNameCorrection.request_id == request_id))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail='该请求编号已用于其他更正，请重新预览并生成新请求。')
        return existing.response_payload
    rows, now = _rows(db, dataset_id), main.utcnow()
    preview, payloads, selected = _plan(rows, body, now)
    if body.preview_token != preview['preview_token']:
        raise HTTPException(status_code=409, detail='账本在预览后已有更新，请重新预览；本次没有修改任何记录。')
    if not preview['can_apply']:
        raise HTTPException(status_code=422, detail={'message': '当前更正不能执行。', 'blockers': preview['blockers']})
    if preview['requires_merge_confirmation'] and not body.confirm_merge:
        raise HTTPException(status_code=422, detail='请先确认将两个品名的库存按单位相加，并按预览换算盘点。')
    inventory = payloads.get(('global', 'inventory'), {})
    for item in preview['stocktake_adjustments']:
        index = int(item['path'].rsplit('/', 1)[1])
        target = inventory['overrides'][index]
        if item.get('new_record'):
            from uuid import uuid5
            target.update(id=str(uuid5(body.request_id, item['unit'])), document_id=request_id,
                          document_no='GM' + now.strftime('%Y%m%d') + request_id[:6].upper(),
                          note=reason, correction_request_id=request_id)
            continue
        original = next(row.payload['overrides'][index] for row in rows
                        if (row.record_type, row.record_key) == ('global', 'inventory'))
        history = list(target.get('name_correction_history', []))
        history.append({'request_id': request_id, 'reason': reason, 'corrected_at': now.isoformat(),
                        'old_name': original.get('name', original.get('名称')), 'new_name': new,
                        'old_quantity': item['old_quantity'], 'new_quantity': item['new_quantity'],
                        'had_previous_quantity': 'previous_quantity' in original,
                        'old_previous_quantity': original.get('previous_quantity'),
                        'new_previous_quantity': item['new_previous_quantity']})
        target['name_correction_history'] = history
    sequence = main.next_sequence(db, dataset_id)
    changed_records = []
    existing_keys = {(row.record_type, row.record_key) for row in rows}
    for record_type, record_key in sorted(selected - existing_keys):
        rows.append(SyncRecord(dataset_id=dataset_id, record_type=record_type, record_key=record_key,
                               payload={}, version=0, sequence=0, updated_at=now))
    for row in rows:
        key = row.record_type, row.record_key
        if key not in selected:
            continue
        after = payloads[key]
        before = deepcopy(row.payload)
        _migrate_timing(db, dataset_id, row, after)
        version, checksum = row.version + 1, payload_checksum(after)
        # updated_at is also the fallback business edit-window anchor. A
        # global administrative correction must not reopen those windows.
        # Sync sequence/version and immutable new audit rows carry the actual
        # correction time; clients must not infer it from this preserved clock.
        if row.version == 0:
            row.payload, row.checksum, row.version, row.sequence = after, checksum, version, sequence
            db.add(row)
        else:
            db.execute(update(SyncRecord).where(SyncRecord.id == row.id).values(
                payload=after, checksum=checksum, version=version, sequence=sequence,
                updated_at=row.updated_at), execution_options={'synchronize_session': False})
        main.add_audit(db, user=user, dataset_id=dataset_id, record_type=row.record_type,
            record_key=row.record_key, action='name_correction' if before != after else 'name_correction_reindex',
            source='inventory_name_correction', event_id=request_id, device_id='',
            from_version=0 if key not in existing_keys else row.version, to_version=version, sequence=sequence,
            before_payload=before, after_payload=after, checksum=checksum, occurred_at=now)
        changed_records.append({'record_type': row.record_type, 'record_key': row.record_key, 'version': version})
        sequence += 1
    response = {'applied': True, 'request_id': request_id, 'summary': preview['summary'],
                'changed_records': changed_records,
                'message': '品名更正已一次性完成，并按确认的实际库存保存；原采购金额和录入时钟已保留。'}
    db.add(InventoryNameCorrection(dataset_id=dataset_id, request_id=request_id, request_hash=request_hash,
                                  request_payload=request, response_payload=response, actor_user_id=user.id, reason=reason))
    db.commit()
    return response
