"""Pure, lossless ingredient-name correction planning.

Only named fields or parsed name spans change. Financial rows are never rebuilt
from inventory totals, and JSON strings retain every untouched source token.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any

from .inventory_balance import _day, _canonical_daily_selection, detail_items, ledger_events, replay_quantities, numeric
from .inventory_validation import identity, is_voided

NAME_KEYS = ('name', '名称', '食材名称', '佐料名称', '词条名称')
TABLES = ('entries', 'adjustments', 'overrides', 'item_settings')


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def snapshot_token(records: list[dict], category: str, old: str, new: str, finals=(), today='') -> str:
    snapshot = [{key: row.get(key) for key in ('id', 'record_type', 'record_key', 'version', 'sequence', 'is_deleted', 'payload')}
                for row in records]
    return hashlib.sha256(stable_json({'category': category, 'old_name': old, 'new_name': new,
                                     'records': snapshot, 'final_quantities': finals, 'business_date': today}).encode()).hexdigest()


def _replace_trimmed(value: str, new: str) -> str:
    return value[:len(value) - len(value.lstrip())] + new + value[len(value.rstrip()):]


def _changed_strings(before, after, path=()):
    result = {}
    if isinstance(before, str) and before != after:
        if not isinstance(after, str):
            raise ValueError('JSON 字段类型发生改变')
        result[path] = after
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            raise ValueError('JSON 明细行数发生改变')
        for index, (left, right) in enumerate(zip(before, after)):
            result.update(_changed_strings(left, right, (*path, index)))
    elif isinstance(before, dict) and isinstance(after, dict):
        if before.keys() != after.keys():
            raise ValueError('JSON 明细字段发生改变')
        for key in before:
            result.update(_changed_strings(before[key], after[key], (*path, key)))
    elif before != after:
        raise ValueError('更名不得修改原数量或金额')
    return result


def replace_json_strings(raw: str, before: Any, after: Any) -> str:
    """Patch changed string tokens, retaining punctuation/numeric spellings."""
    changes = _changed_strings(before, after)
    if not changes:
        return raw
    decoder, patches, seen = json.JSONDecoder(), [], set()
    def skip(pos):
        while pos < len(raw) and raw[pos].isspace():
            pos += 1
        return pos
    def walk(pos, path):
        pos = skip(pos)
        if raw[pos] == '{':
            pos = skip(pos + 1)
            if raw[pos] == '}':
                return pos + 1
            while True:
                key, end = decoder.raw_decode(raw, pos)
                pos = walk(skip(end) + 1, (*path, key))
                pos = skip(pos)
                if raw[pos] == '}':
                    return pos + 1
                pos = skip(pos + 1)
        if raw[pos] == '[':
            pos, index = skip(pos + 1), 0
            if raw[pos] == ']':
                return pos + 1
            while True:
                pos = skip(walk(pos, (*path, index)))
                if raw[pos] == ']':
                    return pos + 1
                pos, index = skip(pos + 1), index + 1
        value, end = decoder.raw_decode(raw, pos)
        if path in changes:
            if path in seen or not isinstance(value, str):
                raise ValueError('匹配品名的 JSON 字段重复或格式不明确')
            seen.add(path)
            patches.append((pos, end, json.dumps(changes[path], ensure_ascii=False)))
        return end
    walk(0, ())
    if seen != set(changes):
        raise ValueError('无法定位 JSON 更名字段')
    for start, end, value in sorted(patches, reverse=True):
        raw = raw[:start] + value + raw[end:]
    return raw


def _text_item(token: str) -> tuple[str, str, tuple[int, int]]:
    note = re.search(r'\s+备注[:：]', token)
    core = token[:note.start()] if note else token
    start, end = len(core) - len(core.lstrip()), len(core.rstrip())
    clean = core[start:end]
    match = re.match(r'^(.*?)\s+[-+]?\d+(?:\.\d+)?\s*([^\d\s,，;；]*)\s+[-+]?\d+(?:\.\d+)?$', clean)
    if match:
        name, unit = match.group(1).rstrip(), match.group(2)
    else:
        amount = re.match(r'^(.+?)(?:\s+)?[-+]?\d+(?:\.\d+)?$', clean) if not re.fullmatch(r'[-+]?\d+(?:\.\d+)?', clean) else None
        name, unit = (amount.group(1).rstrip() if amount else clean), ''
    return name, unit, (start, start + len(name))


class Planner:
    def __init__(self, records, category, old, new, today):
        self.records, self.category, self.old, self.new, self.today = records, category, old, new, today
        self.payloads = {(row['record_type'], row['record_key']): deepcopy(row['payload']) for row in records if not row.get('is_deleted')}
        self.originals = {key: deepcopy(value) for key, value in self.payloads.items()}
        self.changes, self.blockers, self.warnings, self.adjustments = [], [], [], []
        self.target_seen = False
        self.summary = dict.fromkeys(('records', 'purchases', 'manual_receipts', 'outbounds', 'stocktakes', 'dishes', 'dictionary', 'settings'), 0)
        self.inventory = self.originals.get(('global', 'inventory'), {})
        if not isinstance(self.inventory, dict):
            self.issue('库存原始记录格式异常，请先核对。')
            self.inventory = {}
        dictionary_payload = self.originals.get(('global', 'ingredients'), {})
        if not isinstance(dictionary_payload, dict):
            self.issue('食材词典格式异常，请先核对。')
            dictionary_payload = {}
        self.ingredients = dictionary_payload.get('ingredients', [])
        if not isinstance(self.ingredients, list):
            self.issue('食材词典行格式异常，请先核对。')
            self.ingredients = []
        self.days = [row for row in records if row['record_type'] == 'day' and not row.get('is_deleted')]
        self.before_events = ledger_events(self.inventory, self.days, self.ingredients)
        self.exact, self.named, self.dictionary = {}, {}, {}
        for row in self.before_events['receipts']:
            category, name, unit = identity(row)
            self.exact.setdefault((name, unit), set()).add(category)
            self.named.setdefault(name, set()).add(category)
        for row in self.ingredients if isinstance(self.ingredients, list) else []:
            if isinstance(row, dict):
                name = str(row.get('词条名称') or row.get('食材名称') or '').strip()
                self.dictionary.setdefault(name, set()).add(str(row.get('分类') or '食材'))

    def issue(self, message):
        if message not in self.blockers:
            self.blockers.append(message)

    def classify(self, name, unit):
        categories = self.exact.get((name, unit)) or self.named.get(name) or self.dictionary.get(name) or {'食材'}
        if len(categories) != 1 and name in {self.old, self.new}:
            self.issue(f'“{name}”同时出现在不同分类，无法确定菜品用量归属。')
        return '佐料' if categories == {'佐料'} else '食材'

    def change(self, record, path, section, date, before, after, row=None, description=''):
        item = {'record_type': record['record_type'], 'record_key': record['record_key'], 'date': date,
                'section': section, 'path': path, 'before_name': before, 'after_name': after}
        if row:
            for key, aliases in (('quantity', ('quantity', '数量')), ('unit', ('unit', '单位')),
                                 ('amount', ('total', '总价'))):
                for alias in aliases:
                    if alias in row:
                        item[key] = row[alias]
                        break
        if description:
            item['description'] = description
        self.changes.append(item)
        self.summary[section] += 1

    def details(self, raw, record, path, section, date, fixed_category=None):
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
            except (ValueError, TypeError):
                decoded = None
            if isinstance(decoded, (list, dict)):
                changed = self.details(decoded, record, path, section, date, fixed_category)
                try:
                    return replace_json_strings(raw, decoded, changed)
                except ValueError as exc:
                    self.issue(f'{date or record["record_key"]}：{exc}。')
                    return raw
            if raw.lstrip().startswith(('[', '{')) and self.old in raw:
                self.issue(f'{date or record["record_key"]} 的相关 JSON 明细无法解析，请先修正。')
                return raw
            tokens = re.split(r'([,，;；\n])', raw)
            for index in range(0, len(tokens), 2):
                name, unit, (start, end) = _text_item(tokens[index])
                category = fixed_category or self.classify(name, unit)
                if name == self.new and category == self.category:
                    self.target_seen = True
                if name == self.old and category == self.category:
                    self.change(record, f'{path}/text/{index // 2}', section, date, name, self.new,
                                {'unit': unit}, '保留原数量、金额、分隔符和备注')
                    tokens[index] = tokens[index][:start] + self.new + tokens[index][end:]
            return ''.join(tokens)
        if isinstance(raw, list):
            return [self.details(item, record, f'{path}/{index}', section, date, fixed_category)
                    for index, item in enumerate(raw)]
        if isinstance(raw, dict):
            item = deepcopy(raw)
            names = [(key, value) for key, value in raw.items() if key in NAME_KEYS and isinstance(value, str) and value.strip()]
            name = next((str(raw[key]).strip() for key in NAME_KEYS if isinstance(raw.get(key), str) and raw[key].strip()), '')
            unit = str(raw.get('unit') or raw.get('单位') or '').strip()
            category = fixed_category or self.classify(name, unit)
            if name == self.new and category == self.category:
                self.target_seen = True
            if name == self.old and category == self.category:
                if len({value.strip() for _, value in names}) > 1:
                    self.issue(f'{date or record["record_key"]} 的相关明细有互相矛盾的名称字段。')
                    return item
                for key, value in names:
                    item[key] = _replace_trimmed(value, self.new)
                self.change(record, path, section, date, name, self.new, raw)
            return item
        return raw

    def dishes(self, raw, record, path, date):
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw or '[]')
            except (ValueError, TypeError):
                if self.old in raw:
                    self.issue(f'{date or record["record_key"]} 的相关菜品 JSON 无法解析。')
                return raw
            changed = self.dishes(decoded, record, path, date)
            try:
                return replace_json_strings(raw, decoded, changed) if raw.strip() else raw
            except ValueError as exc:
                self.issue(str(exc))
                return raw
        if isinstance(raw, list):
            result = deepcopy(raw)
            for index, dish in enumerate(result):
                if isinstance(dish, dict) and '食材明细' in dish:
                    dish['食材明细'] = self.details(dish['食材明细'], record, f'{path}/{index}/食材明细', 'dishes', date)
            return result
        if self.old in str(raw):
            self.issue(f'{date or record["record_key"]} 的相关菜品数据不是明细数组。')
        return raw

    def transform(self):
        for record in self.records:
            key = record['record_type'], record['record_key']
            if key not in self.payloads:
                continue
            payload = self.payloads[key]
            if not isinstance(payload, dict):
                if self.old in str(payload):
                    self.issue(f'{key[1]} 的相关原始来源不是对象，不能遗漏执行更正。')
                continue
            if key[0] == 'day':
                daily = payload.get('daily')
                if 'daily' in payload and not isinstance(daily, list) and self.old in str(daily):
                    self.issue(f'{key[1]} 的相关采购行格式异常。')
                daily = daily if isinstance(daily, list) else [payload]
                for index, row in enumerate(daily):
                    if not isinstance(row, dict):
                        continue
                    day = _day(row.get('日期') or key[1])
                    for field, category in (('食材明细', '食材'), ('佐料明细', '佐料')):
                        if field in row and category == self.category:
                            row[field] = self.details(row[field], record, f'/daily/{index}/{field}', 'purchases', day, category)
                for index, row in enumerate(payload.get('dishes', []) if isinstance(payload.get('dishes'), list) else []):
                    if isinstance(row, dict) and '菜品数据' in row:
                        row['菜品数据'] = self.dishes(row['菜品数据'], record, f'/dishes/{index}/菜品数据', _day(row.get('日期') or key[1]))
                if 'dishes' in payload and not isinstance(payload['dishes'], list) and self.old in str(payload['dishes']):
                    self.issue(f'{key[1]} 的相关菜品行格式异常。')
            elif key == ('global', 'inventory'):
                for table, section in (('entries', 'manual_receipts'), ('adjustments', 'outbounds'), ('overrides', 'stocktakes'), ('item_settings', 'settings')):
                    if table in payload and not isinstance(payload[table], list) and self.old in str(payload[table]):
                        self.issue(f'相关库存 {table} 行格式异常，不能遗漏来源执行更正。')
                    for index, row in enumerate(payload.get(table, []) if isinstance(payload.get(table), list) else []):
                        if not isinstance(row, dict):
                            continue
                        category, name, unit = identity(row)
                        if category == self.category and name == self.new:
                            self.target_seen = True
                        if category == self.category and name == self.old:
                            names = {str(row[field]).strip() for field in ('name', '名称') if row.get(field) not in (None, '')}
                            if len(names) > 1:
                                self.issue('相关库存行有互相矛盾的名称字段，请先核对。')
                            for field in ('name', '名称'):
                                if isinstance(row.get(field), str) and row[field].strip() == self.old:
                                    row[field] = _replace_trimmed(row[field], self.new)
                            self.change(record, f'/{table}/{index}', section, _day(row.get('date') or row.get('日期')), name, self.new, row)
            elif key == ('global', 'ingredients'):
                for index, row in enumerate(payload.get('ingredients', []) if isinstance(payload.get('ingredients'), list) else []):
                    if isinstance(row, dict) and str(row.get('分类') or '食材') == self.category:
                        for field in ('词条名称', '食材名称', 'name', '名称'):
                            if isinstance(row.get(field), str) and row[field].strip() == self.new:
                                self.target_seen = True
                            if isinstance(row.get(field), str) and row[field].strip() == self.old:
                                row[field] = _replace_trimmed(row[field], self.new)
                                self.change(record, f'/ingredients/{index}/{field}', 'dictionary', '', self.old, self.new, row)
        return self

    def candidate_days(self):
        return [{**row, 'payload': self.payloads[(row['record_type'], row['record_key'])]} for row in self.days]

    def events(self, payloads=None):
        payloads = self.payloads if payloads is None else payloads
        inventory = payloads.get(('global', 'inventory'), {})
        inventory = inventory if isinstance(inventory, dict) else {}
        dictionary = payloads.get(('global', 'ingredients'), {})
        ingredients = dictionary.get('ingredients', []) if isinstance(dictionary, dict) else []
        days = [{**row, 'payload': payloads[(row['record_type'], row['record_key'])]} for row in self.days]
        return ledger_events(inventory, days, ingredients)

    @staticmethod
    def ordered(events, strict_names=()):
        result = []
        for priority, table, kind in ((0, 'receipts', 'receipt'), (1, 'outbounds', 'dish'),
                                      (2, 'adjustments', 'adjustment'), (3, 'overrides', 'override')):
            for index, row in enumerate(events[table]):
                if is_voided(row):
                    continue
                day, key = _day(row.get('date') or row.get('日期')), identity(row)
                if not day or not key[1]:
                    continue
                order, rank = index, priority
                if kind != 'dish' and row.get('recorded_at'):
                    try:
                        parsed = datetime.fromisoformat(str(row['recorded_at']).replace('Z', '+00:00'))
                        if parsed.tzinfo is None:
                            raise ValueError
                        order, rank = parsed.timestamp(), 4
                    except (ValueError, TypeError, OverflowError):
                        if key[1] in strict_names:
                            raise ValueError(f'{day} {key[1]} 的事件时间不明确，无法安全合并。')
                result.append((day, rank, order, index, kind, key, row))
        return sorted(result, key=lambda event: event[:4])

    def merge_stocktakes(self):
        # Carry raw positions through normalization, without adding anything
        # to stored rows. Old inventories need not have unique modern IDs.
        inventory = deepcopy(self.inventory)
        for index, row in enumerate(inventory.get('overrides', []) if isinstance(inventory.get('overrides'), list) else []):
            if isinstance(row, dict):
                row['_correction_index'] = index
        events = ledger_events(inventory, self.days, self.ingredients)
        all_rows = [row for table in ('receipts', 'outbounds', 'adjustments', 'overrides') for row in events[table] if not is_voided(row)]
        source_units = {identity(row)[2] for row in all_rows if identity(row)[:2] == (self.category, self.old)}
        target_units = {identity(row)[2] for row in all_rows if identity(row)[:2] == (self.category, self.new)}
        merge_units = source_units & target_units
        self.requires_merge = bool(self.target_seen or target_units or self.new in self.dictionary and self.category in self.dictionary[self.new])
        if self.requires_merge:
            self.warnings.append('目标品名已存在；合并后 FIFO 批次分摊和历史出库成本会重新计算，原采购数量、单价和金额不变。')
        for table in ('entries', 'adjustments', 'overrides'):
            for row in self.inventory.get(table, []) if isinstance(self.inventory.get(table), list) else []:
                if not isinstance(row, dict) or is_voided(row):
                    continue
                category, name, unit = identity(row)
                if category != self.category or name not in {self.old, self.new}:
                    continue
                try:
                    quantity = float(row.get('quantity', row.get('数量')))
                    if not math.isfinite(quantity) or quantity < 0 or not _day(row.get('date') or row.get('日期')):
                        raise ValueError
                except (ValueError, TypeError, OverflowError):
                    self.issue(f'“{name}”存在数量或日期无效的历史库存行，无法验证更正结果。')
        candidate_inventory = self.payloads.get(('global', 'inventory'), {})
        candidate_inventory = candidate_inventory if isinstance(candidate_inventory, dict) else {}
        settings = candidate_inventory.get('item_settings', [])
        if not isinstance(settings, list):
            self.issue('安全库存配置格式异常，请先核对。')
            settings = []
        for unit in {identity(row)[2] for row in settings if isinstance(row, dict)}:
            matches = [row for row in settings if isinstance(row, dict) and identity(row) == (self.category, self.new, unit)]
            old_settings = self.inventory.get('item_settings', [])
            old_matches = [row for row in old_settings if isinstance(row, dict) and identity(row) == (self.category, self.old, unit)] if isinstance(old_settings, list) else []
            if old_matches and len(matches) > 1:
                if all(row == matches[0] for row in matches[1:]):
                    kept = False
                    deduplicated = []
                    for row in settings:
                        if row == matches[0]:
                            if kept:
                                continue
                            kept = True
                        deduplicated.append(row)
                    settings = deduplicated
                    candidate_inventory['item_settings'] = settings
                    self.warnings.append(f'{self.new}（{unit}）完全相同的安全库存配置合并为一条，原值保留于审计。')
                else:
                    self.issue(f'{self.new}（{unit}）的安全库存阈值或扩展字段冲突，请先保留一条明确配置后再预览。')
        counts = [row for row in events['overrides'] if identity(row)[:2] in {(self.category, self.old), (self.category, self.new)}
                  and identity(row)[2] in merge_units and not is_voided(row)]
        if counts:
            for warning in events['warnings']:
                if warning['name'] in {'', self.old, self.new}:
                    self.issue(f'{warning["date"]} {warning["name"]}：{warning["reason"]}，不能据此合并盘点。')
            daily, _ = _canonical_daily_selection(self.days)
            detail_field = '食材明细' if self.category == '食材' else '佐料明细'
            for day, row in daily.items():
                for item in detail_items(row.get(detail_field)):
                    if item['name'] in {self.old, self.new} and (item['quantity'] <= 0 or not item['unit']):
                        self.issue(f'{day} {item["name"]}采购缺少明确数量／单位，不能据此合并盘点。')
        try:
            ordered = self.ordered(events, {self.old, self.new})
        except ValueError as exc:
            self.issue(str(exc))
            return
        balances = {}
        inventory_record = next((row for row in self.records if (row['record_type'], row['record_key']) == ('global', 'inventory')), None)
        for day, rank, order, index, kind, key, row in ordered:
            quantity = max(0.0, numeric(row.get('quantity', row.get('数量'))))
            before = balances.get(key, 0.0)
            if kind == 'override':
                if key[0] == self.category and key[1] in {self.old, self.new} and key[2] in merge_units:
                    other = (key[0], self.new if key[1] == self.old else self.old, key[2])
                    other_quantity = balances.get(other, 0.0)
                    combined, previous = quantity + other_quantity, before + other_quantity
                    if combined < -1e-8:
                        self.issue(f'{day} {self.new}（{key[2]}）合并实盘会为负数，不能自动更正。')
                    else:
                        combined = max(0.0, combined)
                        raw_index = row['_correction_index']
                        original = self.inventory['overrides'][raw_index]
                        target = self.payloads[('global', 'inventory')]['overrides'][raw_index]
                        if not isinstance(target.get('name_correction_history', []), list):
                            self.issue('盘点已有无法识别的更正元数据，请先核对。')
                        target['quantity'] = combined
                        if '数量' in target:
                            target['数量'] = combined
                        target['previous_quantity'] = previous
                        adjustment = {'record_key': 'inventory', 'path': f'/overrides/{raw_index}', 'date': day,
                                      'unit': key[2], 'old_quantity': original.get('quantity', original.get('数量')),
                                      'new_quantity': combined, 'new_previous_quantity': previous,
                                      'description': f'原{key[1]}实盘加另一品名当时余额 {other_quantity:g}；保留两项合计库存'}
                        if 'previous_quantity' in original:
                            adjustment['old_previous_quantity'] = original['previous_quantity']
                        self.adjustments.append(adjustment)
                        if key[1] == self.new and inventory_record:
                            self.change(inventory_record, adjustment['path'], 'stocktakes', day, self.new, self.new, target,
                                        '目标品名原盘点同步换算为合计实盘')
                balances[key] = quantity
            elif kind == 'receipt':
                balances[key] = before + quantity
            else:
                balances[key] = before - quantity

    def verify(self):
        after = self.events()
        before_result = replay_quantities(**{key: self.before_events[key] for key in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=self.today)
        after_result = replay_quantities(**{key: after[key] for key in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=self.today)
        units = {key[2] for key in before_result['balances'] if key[:2] in {(self.category, self.old), (self.category, self.new)}}
        self.effects = []
        for unit in sorted(units):
            source = before_result['balances'].get((self.category, self.old, unit), 0.0)
            target = before_result['balances'].get((self.category, self.new, unit), 0.0)
            result = after_result['balances'].get((self.category, self.new, unit), 0.0)
            if abs(result - source - target) > 1e-7:
                self.issue(f'{self.new}（{unit}）更正后库存与原两项合计不符。')
            self.effects.append({'category': self.category, 'unit': unit, 'source_quantity': source,
                                 'target_quantity': target, 'combined_quantity': source + target, 'after_quantity': result})
        # Category inference for dishes must remain stable after a name merge.
        before_dishes = [(row.get('id'), identity(row), row['quantity']) for row in self.before_events['outbounds']]
        after_dishes = [(row.get('id'), identity(row), row['quantity']) for row in after['outbounds']]
        expected = [(row_id, (category, self.new if category == self.category and name == self.old else name, unit), quantity)
                    for row_id, (category, name, unit), quantity in before_dishes]
        if after_dishes != expected:
            self.issue('更正会改变菜品的分类、单位或用量归属，不能自动合并。')
        # Prove the combined balance after every event, not only at the end;
        # a later absolute count must not hide an earlier quantity difference.
        try:
            old_order, new_order = self.ordered(self.before_events, {self.old, self.new}), self.ordered(after, {self.old, self.new})
            if len(old_order) != len(new_order):
                raise ValueError('更正前后的库存事件数量不同。')
            left, right = {}, {}
            for old_event, new_event in zip(old_order, new_order):
                for event, state in ((old_event, left), (new_event, right)):
                    key, kind, row = event[5], event[4], event[6]
                    quantity = max(0.0, numeric(row.get('quantity', row.get('数量'))))
                    state[key] = quantity if kind == 'override' else state.get(key, 0.0) + (quantity if kind == 'receipt' else -quantity)
                key = old_event[5]
                mapped = (key[0], self.new if key[:2] == (self.category, self.old) else key[1], key[2])
                expected_quantity = left.get(mapped, 0.0)
                if mapped[:2] == (self.category, self.new):
                    expected_quantity += left.get((self.category, self.old, mapped[2]), 0.0)
                if abs(right.get(mapped, 0.0) - expected_quantity) > 1e-7:
                    raise ValueError('更正无法保持每个历史事件后的合计库存。')
        except ValueError as exc:
            self.issue(str(exc))

    def final_counts(self, finals, now):
        self.finals = finals
        for effect in self.effects:
            effect['delta'] = 0.0
        if not finals:
            return
        by_unit = {row['unit']: row for row in self.effects}
        for item in finals:
            if item['unit'] not in by_unit:
                self.issue(f'单位“{item["unit"]}”不属于本次受影响库存。')
        if self.blockers:
            return
        inventory = self.payloads.setdefault(('global', 'inventory'), {})
        if not isinstance(inventory.get('overrides', []), list):
            self.issue('盘点原始记录格式异常，请先核对。')
            return
        counts = inventory.setdefault('overrides', [])
        latest = now.timestamp()
        for table in ('entries', 'adjustments', 'overrides'):
            for row in inventory.get(table, []) if isinstance(inventory.get(table), list) else []:
                if isinstance(row, dict) and _day(row.get('date') or row.get('日期')) == self.today and row.get('recorded_at'):
                    try:
                        parsed = datetime.fromisoformat(str(row['recorded_at']).replace('Z', '+00:00'))
                        if parsed.tzinfo is None:
                            raise ValueError
                        latest = max(latest, parsed.timestamp() + .001)
                    except (ValueError, TypeError, OverflowError):
                        self.issue('当前日有无法确定先后顺序的库存记录，不能追加本次盘点。')
        if self.blockers:
            return
        recorded_at = datetime.fromtimestamp(latest, timezone.utc).isoformat(timespec='microseconds')
        record = {'record_type': 'global', 'record_key': 'inventory'}
        for index, item in enumerate(finals):
            effect = by_unit[item['unit']]
            price = item.get('unit_price')
            row = {'id': f'correction-preview-{index}', 'document_id': 'preview', 'document_no': '预览盘点',
                   'date': self.today, 'recorded_at': recorded_at, 'category': self.category, 'name': self.new,
                   'unit': item['unit'], 'quantity': item['quantity'], 'previous_quantity': effect['combined_quantity'],
                   'note': '品名更正后的实际库存', 'price_known': price is not None, 'unit_price': price, 'voided': False}
            path = f'/overrides/{len(counts)}'
            counts.append(row)
            self.adjustments.append({'record_key': 'inventory', 'path': path, 'date': self.today, 'unit': item['unit'],
                                     'old_quantity': effect['combined_quantity'], 'new_quantity': item['quantity'],
                                     'new_previous_quantity': effect['combined_quantity'], 'new_record': True,
                                     'description': '在历史合并后新增今日盘点，以本次填写的实际数量为最终库存；差额不改变原采购支出。'})
            self.change(record, path, 'stocktakes', self.today, self.new, self.new, row, '新增实际库存盘点')
            effect['after_quantity'], effect['delta'] = item['quantity'], item['quantity'] - effect['combined_quantity']
        after = self.events()
        balances = replay_quantities(**{key: after[key] for key in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=self.today)['balances']
        for item in finals:
            if abs(balances.get((self.category, self.new, item['unit']), 0) - item['quantity']) > 1e-7:
                self.issue('新增盘点未得到指定的最终库存，不能执行更正。')
        self.warnings.append('先将原品名和目标品名库存按单位相加，再按本次实际数量新增盘点；盘盈单价未填时记为待定价。')

    def response(self):
        changed = [key for key in self.payloads if self.payloads[key] != self.originals.get(key)]
        self.summary['records'] = len(changed)
        if not changed:
            self.issue('没有找到需要更正的精确品名。')
        return {'category': self.category, 'old_name': self.old, 'new_name': self.new,
                'preview_token': snapshot_token(self.records, self.category, self.old, self.new, self.finals, self.today),
                'can_apply': not self.blockers and bool(changed), 'requires_merge_confirmation': self.requires_merge,
                'summary': self.summary, 'changes': self.changes, 'warnings': self.warnings,
                'blockers': self.blockers, 'stocktake_adjustments': self.adjustments, 'inventory_effects': self.effects}


def plan_correction(records: list[dict], category: str, old: str, new: str, today: str, finals=(), now=None) -> tuple[dict, dict]:
    planner = Planner(records, category, old, new, today).transform()
    if old == new:
        planner.issue('新旧品名相同，无需更正。')
    if not any(item['before_name'] == old and item['after_name'] == new for item in planner.changes):
        planner.issue('没有找到需要更正的精确品名。')
    planner.merge_stocktakes()
    planner.verify()
    planner.final_counts(list(finals), now or datetime.now(timezone.utc))
    return planner.response(), planner.payloads
