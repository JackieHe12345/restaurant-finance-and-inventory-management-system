from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_dataset_api import DatasetApiTests as _Fixture
from app.money import money_text, normalize_payload
from app import database, main
from app.excel_io import build_internal_workbook, WorkbookRecord, payload_checksum
from app.inventory_balance import ledger_events, replay_quantities, guard_inventory_balance
from app.models import SyncRecord
from fastapi import HTTPException

DAY = '2026-10-29'
NOW = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)


def document(table='entries', quantity=10, hour=9, **fields):
    doc_id = str(uuid4())
    row = {'id': str(uuid4()), 'document_id': doc_id, 'document_no': 'TEST' + doc_id[:6],
           'date': DAY, 'recorded_at': f'{DAY}T{hour:02}:00:00.000Z',
           'category': '食材', 'name': '牛肉', 'unit': '斤', 'quantity': quantity,
           'note': '实盘' if table == 'overrides' else '', 'voided': False}
    if table == 'entries':
        row.update(unit_price=2, total=quantity * 2, source='manual', price_known=True)
    elif table == 'adjustments':
        row['kind'] = 'normal'
    else:
        row.update(previous_quantity=10, price_known=False)
    row.update(fields)
    return row


class InventoryApiTests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    tearDownClass = classmethod(_Fixture.tearDownClass.__func__)
    create_dataset = _Fixture.create_dataset
    create_role_headers = _Fixture.create_role_headers
    put_record = _Fixture.put_record

    def setUp(self):
        self.dataset_id = 'inv-' + str(uuid4())[:8]
        self.create_dataset(self.dataset_id, '库存验证')
        self.url = f'/api/v1/datasets/{self.dataset_id}/records/global/inventory'
        self.clock = patch.object(main, 'utcnow', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def save(self, payload, version=0, headers=None):
        return self.client.put(self.url, headers=headers or self.headers,
                               json={'payload': payload, 'expected_version': version})

    def test_metadata_roundtrip_void_and_cash_no_duplicate_purchase(self):
        self.put_record(self.dataset_id, 'day', DAY, {'daily': [{'日期': DAY, '食材成本': 80,
                         '食材明细': json.dumps([{'name': '牛肉', 'quantity': 4, 'unit': '斤', 'total': 80}])}]})
        receipt = document(extra_metadata={'original': [1, 2]})
        payload = {'entries': [receipt], 'extensions': {'keep': ['value']}, 'item_settings': [
            {'category': '食材', 'name': '牛肉', 'unit': '斤', 'min_quantity': 2}]}
        saved = self.save(payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        with database.SessionLocal() as db:
            summary = main._cash_flow_summary_db(db, self.dataset_id, {'opening_date': '2026-10-28', 'opening_balance': 1000}, now=NOW)
        self.assertEqual(summary['current_balance'], money_text(900))
        receipt.update(voided=True, void_reason='重复录入', voided_at=NOW.isoformat())
        voided = self.save(payload, saved.json()['version'])
        self.assertEqual(voided.status_code, 200, voided.text)
        loaded = self.client.get(self.url, headers=self.headers).json()['payload']
        self.assertEqual(loaded, normalize_payload(payload))
        with database.SessionLocal() as db:
            summary = main._cash_flow_summary_db(db, self.dataset_id, {'opening_date': '2026-10-28', 'opening_balance': 1000}, now=NOW)
        self.assertEqual(summary['daily_expenses'], money_text(80))
        self.assertEqual(summary['inventory_expenses'], money_text(0))
        self.assertEqual(summary['current_balance'], money_text(920))
        exported = self.client.get(f'/api/v1/datasets/{self.dataset_id}/workbooks/internal', headers=self.headers)
        imported = self.client.post(f'/api/v1/datasets/{self.dataset_id}/workbooks/internal', headers=self.headers,
                                   files={'file': ('inventory.xlsx', exported.content)})
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['payload'], normalize_payload(payload))

    def test_multiline_issue_and_late_receipt_do_not_hide_shortage(self):
        receipt = document()
        saved = self.save({'entries': [receipt]})
        issue = document('adjustments', 6, 10)
        second = {**issue, 'id': str(uuid4())}
        candidate = {'entries': [receipt], 'adjustments': [issue, second]}
        denied = self.save(candidate, saved.json()['version'])
        self.assertEqual(denied.status_code, 422, denied.text)
        self.assertIn('库存不足', denied.text)
        # Replenishment after the issue cannot retroactively cover its shortage.
        candidate['entries'].append(document(quantity=10, hour=11))
        denied = self.save(candidate, saved.json()['version'])
        self.assertEqual(denied.status_code, 422, denied.text)
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['version'], saved.json()['version'])

    def test_void_receipt_cannot_hide_new_shortage_with_stocktake(self):
        receipt, issue = document(), document('adjustments', 5, 10, kind='loss')
        count = document('overrides', 20, 11, previous_quantity=5)
        payload = {'entries': [receipt], 'adjustments': [issue], 'overrides': [count]}
        saved = self.save(payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        receipt.update(voided=True, void_reason='错误入库', voided_at=NOW.isoformat())
        denied = self.save(payload, saved.json()['version'])
        self.assertEqual(denied.status_code, 422, denied.text)
        self.assertIn('新增短缺', denied.text)

    def test_derived_purchase_can_be_issued_and_source_changes_are_replayed(self):
        source_day = '2026-10-28'
        source = {'daily': [{'日期': '2026/10/28', '食材成本': 100, '食材明细': '牛肉 5托盘 100'}]}
        self.put_record(self.dataset_id, 'day', source_day, source)
        issue = document('adjustments', 4, 10, unit='托盘')
        saved = self.save({'adjustments': [issue]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn('entries', saved.json()['payload'])
        # Editing the source purchase changes virtual receipts immediately;
        # it does not create a second manually persisted receipt.
        source['daily'][0]['食材明细'] = [{'名称': '牛肉', '数量': 3, '单位': '托盘', '总价': 60}]
        source['daily'][0]['食材成本'] = 60
        self.put_record(self.dataset_id, 'day', source_day, source)
        candidate = {'adjustments': [issue, document('adjustments', 1, 11, unit='托盘')]}
        denied = self.save(candidate, saved.json()['version'])
        self.assertEqual(denied.status_code, 422, denied.text)
        source['daily'][0].update(食材明细='', 食材成本=0)
        self.put_record(self.dataset_id, 'day', source_day, source)
        self.assertEqual(self.save(candidate, saved.json()['version']).status_code, 422)

    def test_stocktake_previous_balance_and_reason_are_authoritative(self):
        receipt = document()
        saved = self.save({'entries': [receipt]})
        count = document('overrides', 6, 10, previous_quantity=9)
        payload = {'entries': [receipt], 'overrides': [count]}
        self.assertEqual(self.save(payload, saved.json()['version']).status_code, 422)
        count['previous_quantity'] = 10
        count['note'] = ''
        self.assertEqual(self.save(payload, saved.json()['version']).status_code, 422)
        count['note'] = '实盘差异'
        counted = self.save(payload, saved.json()['version'])
        self.assertEqual(counted.status_code, 200, counted.text)
        count.update(voided=True, void_reason='撤销', voided_at=NOW.isoformat())
        self.assertEqual(self.save(payload, counted.json()['version']).status_code, 422)

    def test_documents_cannot_be_mutated_deleted_or_partially_voided(self):
        first = document(quantity=2)
        second = {**first, 'id': str(uuid4()), 'name': '猪肉'}
        payload = {'entries': [first, second]}
        saved = self.save(payload)
        version = saved.json()['version']
        for candidate in ({'entries': [first]}, {'entries': [{**first, 'quantity': 4, 'total': 8}, second]},
                          {'entries': [first, second, deepcopy(first)]}):
            response = self.save(candidate, version)
            self.assertEqual(response.status_code, 422, response.text)
        first.update(voided=True, void_reason='重复', voided_at=NOW.isoformat())
        self.assertEqual(self.save(payload, version).status_code, 422)
        second.update(voided=True, void_reason='重复', voided_at=NOW.isoformat())
        response = self.save(payload, version)
        self.assertEqual(response.status_code, 200, response.text)
        deleted = self.client.post(self.url + '/delete', headers=self.headers,
                                   json={'expected_version': response.json()['version']})
        self.assertEqual(deleted.status_code, 403, deleted.text)

    def test_entry_append_independent_of_old_record_age_and_void_window(self):
        headers = self.create_role_headers(self.dataset_id, 'entry-' + self.dataset_id, 'entry')
        receipt = document(hour=8)
        payload = {'entries': [receipt], 'updated_at': 'old'}
        with patch.object(main, 'utcnow', return_value=NOW.replace(hour=8)):
            saved = self.save(payload)
        payload['entries'].append(document(quantity=2, hour=10))
        payload['updated_at'] = NOW.isoformat()
        appended = self.save(payload, saved.json()['version'], headers)
        self.assertEqual(appended.status_code, 200, appended.text)
        receipt.update(voided=True, void_reason='重复', voided_at=NOW.isoformat())
        self.assertEqual(self.save(payload, appended.json()['version'], headers).status_code, 403)
        viewer = self.create_role_headers(self.dataset_id, 'viewer-' + self.dataset_id, 'viewer')
        self.assertEqual(self.save(payload, appended.json()['version'], viewer).status_code, 403)
        unchanged = self.client.get(self.url, headers=self.headers).json()['payload']
        unchanged['item_settings'] = [{'category': '食材', 'name': '牛肉', 'unit': '斤', 'min_quantity': 2}]
        self.assertEqual(self.save(unchanged, appended.json()['version'], headers).status_code, 403)

    def test_v2_exact_optimistic_version_is_required(self):
        payload = {'entries': [document()]}
        saved = self.save(payload)
        version = saved.json()['version']
        zero = self.save({**payload, 'adjustments': [document('adjustments', 1, 10)]}, 0)
        self.assertEqual(zero.status_code, 409, zero.text)
        first = self.save({**payload, 'adjustments': [document('adjustments', 6, 10)]}, version)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.save({**payload, 'adjustments': [document('adjustments', 6, 10)]}, version)
        self.assertEqual(second.status_code, 409, second.text)
        legacy = document('adjustments', 100, 10)
        legacy = {k: v for k, v in legacy.items() if k not in {'document_id', 'document_no'}}
        downgraded = self.save({**first.json()['payload'], 'adjustments': [*first.json()['payload']['adjustments'], legacy]}, first.json()['version'])
        self.assertEqual(downgraded.status_code, 422, downgraded.text)
        self.assertIn('更新 App', downgraded.text)

    def test_legacy_new_issue_also_cannot_exceed_stock(self):
        legacy = {'id': 'legacy-out', 'date': DAY, 'category': '食材', 'name': '牛肉', 'unit': '斤', 'quantity': 1, 'kind': 'normal'}
        denied = self.save({'adjustments': [legacy]})
        self.assertEqual(denied.status_code, 422, denied.text)

    def test_conflict_resolution_does_not_bypass_inventory_guards(self):
        payload = {'entries': [document()]}
        saved = self.save(payload)
        candidate = {**payload, 'adjustments': [document('adjustments', 20, 10)]}
        conflicted = self.save(candidate, saved.json()['version'] + 1)
        self.assertEqual(conflicted.status_code, 409, conflicted.text)
        conflict_id = conflicted.json()['detail']['conflict_id']
        response = self.client.post(f'/api/v1/conflicts/{conflict_id}/resolve', headers=self.headers,
                                    json={'resolution': 'use_local'})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn('库存不足', response.text)
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['version'], saved.json()['version'])

    def test_client_time_cannot_extend_entry_void_clock(self):
        headers = self.create_role_headers(self.dataset_id, 'entry-time-' + self.dataset_id, 'entry')
        receipt = document(hour=23)
        saved = self.save({'entries': [receipt]}, headers=headers)
        self.assertEqual(saved.status_code, 200, saved.text)
        receipt.update(voided=True, void_reason='重复', voided_at=NOW.replace(hour=11).isoformat())
        with patch.object(main, 'utcnow', return_value=NOW.replace(hour=11)):
            denied = self.save({'entries': [receipt]}, saved.json()['version'], headers)
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_entry_cannot_change_settings_before_first_v2_document(self):
        headers = self.create_role_headers(self.dataset_id, 'settings-' + self.dataset_id, 'entry')
        denied = self.save({'item_settings': [{'category': '食材', 'name': '牛肉', 'unit': '斤', 'min_quantity': 2}]}, headers=headers)
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_legacy_dirty_rows_survive_addition_and_invalid_v2_import_rejected(self):
        legacy = {'entries': [{'id': 'dirty', 'name': '旧食材', 'quantity': -1}], 'adjustments': [{'id': 'old', 'name': '旧食材'}]}
        def upload(payload):
            content = build_internal_workbook(dataset_id=self.dataset_id, schema_version=2,
                records=[WorkbookRecord('global', 'inventory', payload, payload_checksum(payload))])
            return self.client.post(f'/api/v1/datasets/{self.dataset_id}/workbooks/internal', headers=self.headers,
                                    files={'file': ('inventory.xlsx', content)})
        self.assertEqual(upload(legacy).status_code, 200)
        version = self.client.get(self.url, headers=self.headers).json()['version']
        good = deepcopy(legacy)
        good['entries'].append(document())
        saved = self.save(good, version)
        self.assertEqual(saved.status_code, 200, saved.text)
        good['entries'][-1]['quantity'] = -2
        invalid = upload(good)
        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['payload']['entries'][0], legacy['entries'][0])

    def test_invalid_new_fields_and_duplicate_ids(self):
        for field, value in [('quantity', 0), ('unit', ''), ('unit_price', -1), ('unit_price', 'NaN'),
                             ('total', 'Infinity'), ('document_id', 'bad'), ('recorded_at', DAY),
                             ('voided', 'false'), ('date', '2026-10-28'), ('source', 'purchase'),
                             ('document_id', ['invalid']), ('document_no', {'invalid': True}),
                             ('void_reason', ['invalid'])]:
            response = self.save({'entries': [document(**{field: value})]})
            self.assertEqual(response.status_code, 422, (field, response.text))
        row = document(unit_price=0, total=0)
        self.assertEqual(self.save({'entries': [row, deepcopy(row)]}).status_code, 422)
        accepted = self.save({'entries': [row]})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        for invalid_row in (None, 'invalid', []):
            invalid = self.save({'entries': [row, invalid_row]}, accepted.json()['version'])
            self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_future_purchase_not_available_and_dish_only_day_consumes_stock(self):
        self.put_record(self.dataset_id, 'day', '2026-10-30', {'daily': [{'日期': '2026-10-30', '食材明细': '牛肉 100斤 200'}]})
        denied = self.save({'adjustments': [document('adjustments', 1, 10)]})
        self.assertEqual(denied.status_code, 422, denied.text)
        self.put_record(self.dataset_id, 'day', DAY, {'dishes': [{'日期': DAY, '菜品数据': [
            {'菜品名称': '牛肉面', '份数': 20, '食材明细': [{'名称': '牛肉', '数量': 3, '单位': '斤'}]}]}]})
        receipt = document(recorded_at='')
        # Old untimed receipt precedes dish usage; a timestamped receipt today
        # would occur after historical daily dish events by the contract.
        receipt = {k: v for k, v in receipt.items() if k not in {'document_id', 'document_no', 'recorded_at'}}
        seeded = self.save({'entries': [receipt]})
        self.assertEqual(seeded.status_code, 200, seeded.text)
        good = self.save({'entries': [receipt], 'adjustments': [document('adjustments', 7, 10)]}, seeded.json()['version'])
        self.assertEqual(good.status_code, 200, good.text)


del _Fixture  # Prevent pytest's unittest collector running imported tests twice.


class QuantityReplayTests(unittest.TestCase):
    def test_real_browser_canonical_dish_fixture(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/canonical_dish_fixture.json').read_text())
        for case in fixture['cases']:
            with self.subTest(case=case['name']):
                events = ledger_events({}, case['records'])
                self.assertEqual([row['quantity'] for row in events['outbounds']], case['expected'])

    def test_dish_source_follows_canonical_daily_record(self):
        def dishes(quantity):
            return [{'日期': DAY, '菜品数据': [{'食材明细': f'牛肉 {quantity}斤 20'}]}]
        records = [
            {'record_key': 'source', 'sequence': 2, 'version': 1,
             'payload': {'daily': [{'日期': DAY, '食材明细': '牛肉 10斤 20'}], 'dishes': dishes(8)}},
            {'record_key': 'dish-only-other', 'sequence': 3, 'version': 1, 'payload': {'dishes': dishes(2)}}]
        events = ledger_events({}, records)
        self.assertEqual([row['quantity'] for row in events['outbounds']], [8])
        del records[0]['payload']['dishes']
        self.assertEqual(ledger_events({}, records)['outbounds'], [])
        # With no daily source, an exact canonical-key record wins. Without
        # that exact key, the last packed source remains the fallback.
        records[0] = {'record_key': DAY, 'sequence': 1, 'payload': {'dishes': dishes(6)}}
        self.assertEqual([row['quantity'] for row in ledger_events({}, records)['outbounds']], [6])
        records[0]['record_key'] = 'packed-old'
        self.assertEqual([row['quantity'] for row in ledger_events({}, records)['outbounds']], [2])

    def test_zero_quantity_legacy_receipt_does_not_change_dish_category(self):
        inventory = {'entries': [{'id': 'empty', 'date': DAY, 'category': '佐料', 'name': '牛肉', 'unit': '斤', 'quantity': 0}]}
        events = ledger_events(inventory, [{'record_key': DAY, 'payload': {'dishes': [
            {'日期': DAY, '菜品数据': [{'食材明细': '牛肉 2斤 20'}]}]}}])
        self.assertEqual(events['receipts'], [])
        self.assertEqual(events['outbounds'][0]['category'], '食材')
        self.assertEqual(replay_quantities(receipts=inventory['entries'])['balances'], {})

    def test_web_canonical_multi_source_purchase_fixture(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/canonical_purchase_fixture.json').read_text())
        events = ledger_events({}, fixture['records'])
        self.assertEqual([{'date': row['date'], 'quantity': row['quantity']} for row in events['receipts']],
                         [{'date': row['date'], 'quantity': row['quantity']} for row in fixture['expected']])
        self.assertEqual(sum(row['quantity'] for row in events['receipts']), 14)

    def test_legacy_dates_details_custom_units_and_dishes_only(self):
        days = [{'record_key': '2026-10-20', 'payload': {
            'daily': [{'日期': '2026/10/20', '食材明细': '牛肉 10kg 100，豆腐 2托盘 20'},
                      {'日期': '2026/10/21', '食材明细': '[{"名称":"牛肉","数量":2,"单位":"kg"}]'}],
            'dishes': [{'日期': '2026/10/22', '菜品数据': json.dumps([{'份数': 50, '食材明细': '牛肉 3kg 30'}])}]}}]
        events = ledger_events({}, days)
        result = replay_quantities(**{k: events[k] for k in ('receipts', 'outbounds', 'adjustments', 'overrides')}, as_of=DAY)
        self.assertEqual(result['balances'][('食材', '牛肉', 'kg')], 9)
        self.assertEqual(result['balances'][('食材', '豆腐', '托盘')], 2)

    def test_legacy_void_boolean_strings(self):
        base = {'name': '牛肉', 'category': '食材', 'unit': '斤', 'date': DAY, 'quantity': 2}
        result = replay_quantities(receipts=[{**base, 'id': str(i), 'voided': value}
                                    for i, value in enumerate([True, 1, 'true', '1', False, 'false', '0', 0])])
        self.assertEqual(result['balances'][('食材', '牛肉', '斤')], 8)

    def test_earlier_large_deficit_does_not_authorize_new_later_shortage(self):
        base = {'category': '食材', 'name': '牛肉', 'unit': '斤'}
        old = {'entries': [{**base, 'id': 'r', 'date': '2026-10-28', 'quantity': 120}],
               'adjustments': [{**base, 'id': 'old-shortage', 'date': '2026-10-27', 'quantity': 100},
                               {**base, 'id': 'out', 'date': DAY, 'quantity': 10}]}
        candidate = deepcopy(old)
        candidate['entries'][0].update(voided=True)
        with self.assertRaises(HTTPException):
            guard_inventory_balance(old, candidate, [], [], today=DAY)


if __name__ == '__main__':
    unittest.main()
