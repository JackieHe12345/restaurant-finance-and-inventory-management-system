"""Pure quantity replay shared in parity tests with the two client FIFO engines.

replay_quantities accepts the same four event arrays as InventoryFIFO.replay.
ledger_events converts saved day payloads (no ORM dependency). No cost is inferred.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import math
import re
from typing import Any

from .inventory_validation import TABLES, fail, has_documents, identity, is_document, is_voided, row_id, rows

EPSILON = 1e-8
UNITS = '斤 公斤 个 袋 打 盒 两 克 千克 瓶 箱 只 条 份 件 颗 根 把 扎 碗 盘 升 ml L 毫升 斤两 kg KG g mL'.split()


def numeric(value: Any) -> float:
    try:
        value = float(value or 0)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _day(value: Any) -> str:
    text = str(value or '').strip()
    try:
        match = re.match(r'^(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*(?:日)?(?:$|[T\s])', text)
        return date(*map(int, match.groups())).isoformat() if match else ''
    except ValueError:
        return ''


def detail_items(raw: Any, units: tuple | list = ()) -> list[dict]:
    """Match desktop _inventory_detail_items and web parseDetailItems aliases."""
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            pass
    if isinstance(value, list):
        return [{'name': str(row.get('name') or row.get('名称') or row.get('食材名称') or '').strip(),
                 'quantity': numeric(row.get('quantity', row.get('数量', 0))),
                 'unit': str(row.get('unit') or row.get('单位') or '').strip()}
                for row in value if isinstance(row, dict)]
    names = sorted(set(UNITS + list(units)), key=lambda unit: (-len(unit), unit))
    pattern = re.compile(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*(' + '|'.join(re.escape(unit) for unit in names if unit) + r')?\s+(\d+(?:\.\d+)?)$')
    result = []
    for token in re.split(r'[,，;；\n]', str(raw or '')):
        clean = re.split(r'\s+备注[:：]', token.strip(), maxsplit=1)[0].strip()
        if not clean:
            continue
        match = pattern.match(clean)
        if not match:
            # Units may be maintained only in a client's local dictionary.
            # This unambiguous quantity/unit/total form needs no guessing or
            # conversion; preserve the literal custom unit as its own identity.
            match = re.match(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*([^\d\s.,，;；]+)\s+(\d+(?:\.\d+)?)$', clean)
        if match:
            result.append({'name': match.group(1).strip(), 'quantity': numeric(match.group(2)), 'unit': match.group(3) or ''})
        else:
            amount = re.match(r'^(.+?)(?:\s+)?(\d+(?:\.\d+)?)$', clean) if not re.fullmatch(r'\d+(?:\.\d+)?', clean) else None
            result.append({'name': amount.group(1).strip() if amount else clean, 'quantity': 0, 'unit': ''})
    return result


def _entered(value: Any) -> bool:
    # JS String(array) joins values; an empty array is a blank field while
    # the string "[]" is an explicit saved empty detail and replaces history.
    def js_string(item):
        if item is None:
            return ''
        if isinstance(item, list):
            return ','.join(js_string(child) for child in item)
        if isinstance(item, dict):
            return '[object Object]'
        return str(item)
    text = js_string(value)
    return value is not None and bool(text.strip()) and text.lower() not in {'nan', 'none'}


def _canonical_daily_selection(records: list[dict]) -> tuple[dict, dict]:
    """Mirror web normalizeRecords' input-order rank and nonempty field merge.

Do not sum duplicate sources. A later lower-rank packed record is ignored,
and a higher-rank blank field cannot erase a previous detail. Financial
breakdown calculations are intentionally outside this inventory adapter.
"""
    result, ranks, sources = {}, {}, {}
    legacy_fields = {'日期', '收益', '总金额', '收入', '总收入', 'A店收入', 'B店收入',
                     '学生外卖', 'A店外卖', 'B店外卖', '总客人数', '食材成本', '佐料成本'}
    for record_index, record in enumerate(records):
        payload = record.get('payload', record)
        if not isinstance(payload, dict):
            continue
        source_rows = rows(payload, 'daily') if isinstance(payload.get('daily'), list) else ([payload] if legacy_fields.intersection(payload) else [])
        for row_index, row in enumerate(source_rows):
            if not isinstance(row, dict):
                continue
            day = _day(row.get('日期') or record.get('record_key'))
            if not day:
                continue
            rank = (numeric(record.get('sequence') if record.get('sequence') is not None else record.get('seq')),
                    numeric(record.get('version') if record.get('version') is not None else record.get('current_version')), record_index, row_index)
            if day in ranks and rank < ranks[day]:
                continue
            previous = dict(result.get(day, {}))
            for field, value in row.items():
                if not _entered(previous.get(field)) or _entered(value):
                    previous[field] = value
            previous['日期'] = day
            result[day], ranks[day] = previous, rank
            sources[day] = record
    return result, sources


def canonical_daily_rows(records: list[dict]) -> dict[str, dict]:
    return _canonical_daily_selection(records)[0]


def ledger_events(inventory: dict, days: list[dict], ingredients: list[dict] = (), units: list[str] = ()) -> dict:
    """days = [{record_key: YYYY-MM-DD, payload: {daily:[], dishes:[]}}]."""
    def stock_rows(table):
        normalized = []
        for row in rows(inventory, table):
            if not isinstance(row, dict):
                continue
            category, name, unit = identity(row)
            if table == 'entries' and (not name or numeric(row.get('quantity', row.get('数量'))) <= 0):
                continue
            normalized.append({**row, 'category': '佐料' if category == '佐料' else '食材',
                               'name': name, 'unit': unit, 'date': _day(row.get('date') or row.get('日期'))})
        return normalized
    receipts = stock_rows('entries')
    units = list(units) + [identity(row)[2] for table in TABLES for row in rows(inventory, table) if isinstance(row, dict)]
    daily, day_sources = _canonical_daily_selection(days)
    dishes, warnings, records_by_key = {}, [], {}
    for record in days:
        records_by_key[str(record.get('record_key') or '').strip()] = record
        payload = record.get('payload', record)
        if not isinstance(payload, dict):
            continue
        for row in rows(payload, 'dishes'):
            if isinstance(row, dict):
                day = _day(row.get('日期') or record.get('record_key'))
                if day:
                    dishes[day] = row
    # Web currentRecord(day,date) uses the canonical daily source first, then
    # an exact-key record. Only dates without either use the last packed dish
    # row. A selected source with no dishes means empty, not a fallback to an
    # older/different record's usage.
    for day in set(daily) | set(dishes):
        selected = day_sources.get(day)
        if selected is None:
            selected = records_by_key.get(day)
        if selected is None:
            continue
        payload = selected.get('payload', selected)
        matched = [row for row in rows(payload, 'dishes') if isinstance(row, dict)
                   and _day(row.get('日期') or selected.get('record_key')) == day]
        dishes[day] = matched[-1] if matched else {'菜品数据': []}
    for day, row in sorted(daily.items()):
        for index, item in enumerate(detail_items(row.get('食材明细'), units)):
            if item['name'] and item['unit'] and item['quantity'] > 0:
                receipts.append({**item, 'id': f'purchase:{day}:{index}', 'date': day, 'category': '食材', 'source': 'purchase'})
    exact, named, dictionary = {}, {}, {}
    for row in receipts:
        category, name, unit = identity(row)
        exact.setdefault((name, unit), set()).add(category)
        named.setdefault(name, set()).add(category)
    for row in ingredients if isinstance(ingredients, (list, tuple)) else []:
        if isinstance(row, dict):
            dictionary.setdefault(str(row.get('词条名称') or row.get('食材名称') or '').strip(), set()).add(str(row.get('分类') or '食材'))
    outbounds = []
    for day, row in sorted(dishes.items()):
        value = row.get('菜品数据', '')
        if isinstance(value, str):
            try:
                value = json.loads(value or '[]')
            except (ValueError, TypeError):
                warnings.append({'date': day, 'name': '', 'reason': '菜品数据无法解析'})
                continue
        if not isinstance(value, list):
            warnings.append({'date': day, 'name': '', 'reason': '菜品数据不是明细数组'})
            continue
        for dish_index, dish in enumerate(value):
            if not isinstance(dish, dict):
                warnings.append({'date': day, 'name': '', 'reason': '菜品行格式无效'})
                continue
            for item_index, item in enumerate(detail_items(dish.get('食材明细'), units)):
                name, unit, quantity = item['name'], item['unit'], item['quantity']
                if not name or quantity <= 0:
                    if name:
                        warnings.append({'date': day, 'name': name, 'reason': '菜品食材缺少有效用量'})
                    continue
                categories = exact.get((name, unit)) or named.get(name) or dictionary.get(name) or {'食材'}
                outbounds.append({**item, 'category': '佐料' if categories == {'佐料'} else '食材',
                                  'date': day, 'id': f'dish:{day}:{dish_index}:{item_index}'})
    return {'receipts': receipts, 'outbounds': outbounds, 'adjustments': stock_rows('adjustments'),
            'overrides': stock_rows('overrides'), 'warnings': warnings}


def replay_quantities(receipts=(), outbounds=(), adjustments=(), overrides=(), *, as_of: str | None = None) -> dict:
    """Return balances, per-event shortage and book balances before stocktakes.

Every shortage is the *new* unmatched quantity at an outbound, not the running
negative balance. A later receipt or stocktake cannot erase an earlier shortage.
"""
    events, balances, shortages, before_counts = [], {}, {}, {}
    for priority, kind, values in ((0, 'receipt', receipts), (1, 'dish', outbounds), (2, 'adjustment', adjustments), (3, 'override', overrides)):
        for index, row in enumerate(values):
            if not isinstance(row, dict) or is_voided(row):
                continue
            day, key = _day(row.get('date') or row.get('日期')), identity(row)
            if not day or not key[1] or (as_of and day > as_of):
                continue
            order, event_priority = index, priority
            if row.get('recorded_at'):
                try:
                    parsed = datetime.fromisoformat(str(row['recorded_at']).replace('Z', '+00:00'))
                    order, event_priority = parsed.timestamp(), 4
                except (ValueError, TypeError, OverflowError):
                    pass
            events.append((day, event_priority, order, index, kind, key, row))
    for day, priority, order, index, kind, key, row in sorted(events, key=lambda event: event[:4]):
        quantity = max(0.0, numeric(row.get('quantity', row.get('数量'))))
        if kind != 'override' and quantity <= 0:
            continue
        before = balances.get(key, 0.0)
        event_key = (kind, row_id(row) or f'{day}:{index}', key)
        if kind == 'receipt':
            balances[key] = before + quantity
        elif kind == 'override':
            before_counts[event_key] = before
            balances[key] = quantity
        else:
            shortages[event_key] = max(0.0, quantity - max(0.0, before))
            balances[key] = before - quantity
    return {'balances': balances, 'shortages': shortages, 'before_counts': before_counts}


def guard_inventory_balance(previous: dict, candidate: dict, days: list[dict], ingredients: list[dict], *, today: str, units: list[str] = ()) -> None:
    """Guard new outbounds from either client generation; restores are explicit."""
    targets, new_counts = set(), []
    document_mode = has_documents(previous) or has_documents(candidate)
    for table in TABLES:
        old = {row_id(row): row for row in rows(previous, table) if row_id(row)}
        for row in rows(candidate, table):
            if not isinstance(row, dict):
                continue
            before = old.get(row_id(row))
            new_document = is_document(row) and before is None
            void_receipt = table == 'entries' and is_voided(row) and before and not is_voided(before)
            changed_outbound = table == 'adjustments' and before != row
            changed_receipt = document_mode and table == 'entries' and before and before != row
            if changed_outbound or void_receipt or changed_receipt:
                targets.add(identity(row))
            if new_document and table == 'overrides':
                new_counts.append(row)
        if document_mode and table == 'entries':
            remaining_ids = {row_id(row) for row in rows(candidate, table)}
            targets.update(identity(row) for key, row in old.items() if key not in remaining_ids)
    if not targets and not new_counts:
        return
    names = {key[1] for key in targets} | {identity(row)[1] for row in new_counts}
    for table in TABLES:
        for row in rows(candidate, table):
            if not isinstance(row, dict) or is_voided(row) or identity(row)[1] not in names:
                continue
            try:
                quantity = float(row.get('quantity', row.get('数量')))
                if not math.isfinite(quantity) or quantity < 0 or not _day(row.get('date') or row.get('日期')):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                fail(f"{identity(row)[1]}存在数量或日期无效的历史库存记录，请管理员核对后再操作。")
    current = ledger_events(candidate, days, ingredients, units)
    for warning in current['warnings']:
        if warning['date'] <= today and (not warning['name'] or warning['name'] in names):
            fail(f"{warning['date']} {warning['name']} 的{warning['reason']}，请先在菜品明细核对后再出库／盘点。")
    after = replay_quantities(**{key: current[key] for key in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=today)
    old_events = ledger_events(previous, days, ingredients, units)
    before = replay_quantities(**{key: old_events[key] for key in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=today)
    for event, missing in after['shortages'].items():
        if missing > before['shortages'].get(event, 0.0) + EPSILON:
            key = event[2]
            fail(f"{key[1]}库存不足，此操作会新增短缺 {missing - before['shortages'].get(event, 0):g} {key[2]}；请刷新并核对入库、菜品用量和盘点记录。")
    for row in new_counts:
        key = ('override', row_id(row), identity(row))
        expected = after['before_counts'].get(key)
        if expected is None or 'previous_quantity' not in row or abs(numeric(row['previous_quantity']) - expected) > EPSILON:
            fail(f"{identity(row)[1]}盘点账面数量已变化，请刷新库存后重新盘点。")
