from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select
from test_dataset_api import DatasetApiTests as _Fixture
from app import database, main
from app.models import AuditLog, EntryTiming, InventoryNameCorrection, SyncRecord

NOW = datetime(2026, 10, 29, 9, tzinfo=timezone.utc)
DAY = '2026-10-28'
BAD, GOOD = '大豆油 2桶', '大豆油'


class NameCorrectionTests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    tearDownClass = classmethod(_Fixture.tearDownClass.__func__)
    create_dataset = _Fixture.create_dataset
    create_role_headers = _Fixture.create_role_headers
    put_record = _Fixture.put_record

    def setUp(self):
        self.dataset_id = 'names-' + uuid4().hex[:8]
        self.create_dataset(self.dataset_id, '品名更正测试')
        self.base = f'/api/v1/datasets/{self.dataset_id}'
        self.url = self.base + '/inventory/name-corrections'
        self.spec = {'category': '食材', 'old_name': BAD, 'new_name': GOOD}
        clock = patch.object(main, 'utcnow', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def seed(self, counts=False, text=False):
        details = f'{BAD} 2桶 100.00 备注：{BAD}; {GOOD} 3桶 45.00' if text else [
            {'name': BAD, 'quantity': 2, 'unit': '桶', 'total': 100, 'note': BAD, 'unknown': {'keep': 1}},
            {'name': GOOD, 'quantity': 3, 'unit': '桶', 'total': 45}]
        payload = {'daily': [{'日期': DAY, '食材成本': 145, '收益': 300, '新客人数量': 2,
                              '总客人数': 8, '食材明细': details}], 'extension': {'keep': True}}
        self.put_record(self.dataset_id, 'day', DAY, payload)
        if counts:
            self.put_record(self.dataset_id, 'global', 'inventory', {'entries': [], 'overrides': [
                {'id': 'old-count', 'date': '2026-10-29', 'recorded_at': '2026-10-29T01:00:00Z',
                 'category': '食材', 'name': BAD, 'unit': '桶', 'quantity': 5, 'previous_quantity': 2, 'note': '旧名实盘'},
                {'id': 'target-count', 'date': '2026-10-29', 'recorded_at': '2026-10-29T02:00:00Z',
                 'category': '食材', 'name': GOOD, 'unit': '桶', 'quantity': 7, 'previous_quantity': 3, 'note': '目标实盘'}]})
        return self.load("day", DAY)["payload"]

    def preview(self, spec=None, headers=None):
        return self.client.post(self.url + '/preview', headers=headers or self.headers, json=spec or self.spec)

    def request(self, spec=None, preview=None):
        spec = spec or self.spec
        preview = preview or self.preview(spec).json()
        return {**spec, 'preview_token': preview['preview_token'], 'reason': '统一精确品名',
                'request_id': str(uuid4()), 'confirm_merge': True}

    def apply(self, body, headers=None):
        return self.client.post(self.url + '/apply', headers=headers or self.headers, json=body)

    def load(self, kind, key):
        return self.client.get(self.base + f'/records/{kind}/{key}', headers=self.headers).json()

    def test_merge_counts_and_user_actual_quantity_are_separate(self):
        original = self.seed(counts=True)
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 14}]}
        preview = self.preview(spec)
        self.assertEqual(preview.status_code, 200, preview.text)
        value = preview.json()
        self.assertTrue(value['can_apply'], value)
        self.assertEqual(value['inventory_effects'][0]['combined_quantity'], 12)
        self.assertEqual(value['inventory_effects'][0]['after_quantity'], 14)
        self.assertEqual(value['inventory_effects'][0]['delta'], 2)
        self.assertEqual(len(value['stocktake_adjustments']), 3)
        result = self.apply(self.request(spec, value))
        self.assertEqual(result.status_code, 200, result.text)
        inventory = self.load('global', 'inventory')['payload']
        self.assertEqual([row['quantity'] for row in inventory['overrides']], [8, 12, 14])
        self.assertEqual(inventory['overrides'][-1]['previous_quantity'], 12)
        self.assertFalse(inventory['overrides'][-1]['price_known'])
        self.assertEqual(inventory['overrides'][0]['name_correction_history'][0]['old_quantity'], 5)
        expected = deepcopy(original)
        expected['daily'][0]['食材明细'][0]['name'] = GOOD
        self.assertEqual(self.load('day', DAY)['payload'], expected)

    def test_two_plus_three_can_be_saved_as_seven_without_existing_inventory(self):
        self.seed(text=True)
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 7, 'unit_price': 12}]}
        value = self.preview(spec).json()
        self.assertTrue(value['can_apply'], value)
        self.assertEqual(value['inventory_effects'][0]['combined_quantity'], 5)
        result = self.apply(self.request(spec, value))
        self.assertEqual(result.status_code, 200, result.text)
        count = self.load('global', 'inventory')['payload']['overrides'][0]
        self.assertEqual((count['quantity'], count['previous_quantity'], count['unit_price']), (7, 5, '12.000000'))
        self.assertTrue(count['price_known'])
        self.assertEqual(self.load('day', DAY)['payload']['daily'][0]['食材明细'],
                         f'{GOOD} 2桶 100.00 备注：{BAD}; {GOOD} 3桶 45.00')

    def test_zero_actual_and_invalid_final_values(self):
        self.seed()
        for finals in ([{'unit': '桶', 'quantity': -1}], [{'unit': '桶', 'quantity': True}],
                       [{'unit': '桶', 'quantity': 'Infinity'}],
                       [{'unit': '桶', 'quantity': 1}, {'unit': '桶', 'quantity': 2}]):
            self.assertEqual(self.preview({**self.spec, 'final_quantities': finals}).status_code, 422)
        unknown = self.preview({**self.spec, 'final_quantities': [{'unit': '公斤', 'quantity': 1}]}).json()
        self.assertFalse(unknown['can_apply'])
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 0}]}
        result = self.apply(self.request(spec))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.load('global', 'inventory')['payload']['overrides'][0]['quantity'], 0)

    def test_units_merge_independently_and_actual_values_stay_separate(self):
        self.put_record(self.dataset_id, 'day', DAY, {'daily': [{'日期': DAY, '食材明细': [
            {'name': BAD, 'quantity': 2, 'unit': '桶', 'total': 20},
            {'name': GOOD, 'quantity': 3, 'unit': '桶', 'total': 30},
            {'name': BAD, 'quantity': 3, 'unit': '斤', 'total': 9},
            {'name': GOOD, 'quantity': 4, 'unit': '斤', 'total': 12}]}]})
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 7}, {'unit': '斤', 'quantity': 10}]}
        value = self.preview(spec).json()
        self.assertTrue(value['can_apply'], value)
        effects = {row['unit']: row for row in value['inventory_effects']}
        self.assertEqual((effects['桶']['combined_quantity'], effects['斤']['combined_quantity']), (5, 7))
        self.assertEqual(self.apply(self.request(spec, value)).status_code, 200)
        counts = {row['unit']: row for row in self.load('global', 'inventory')['payload']['overrides']}
        self.assertEqual((counts['桶']['quantity'], counts['斤']['quantity']), (7, 10))
        self.assertEqual((counts['桶']['previous_quantity'], counts['斤']['previous_quantity']), (5, 7))

    def test_existing_target_in_different_unit_or_settings_still_requires_confirmation(self):
        self.put_record(self.dataset_id, 'day', DAY, {'daily': [{'日期': DAY, '食材明细': [
            {'name': BAD, 'quantity': 2, 'unit': '斤', 'total': 20},
            {'name': GOOD, 'quantity': 3, 'unit': '公斤', 'total': 30}]}]})
        preview = self.preview().json()
        self.assertTrue(preview['can_apply'], preview)
        self.assertTrue(preview['requires_merge_confirmation'])
        self.assertEqual({row['unit']: row['after_quantity'] for row in preview['inventory_effects']}, {'斤': 2, '公斤': 3})
        body = self.request(preview=preview)
        body['confirm_merge'] = False
        self.assertEqual(self.apply(body).status_code, 422)
        self.put_record(self.dataset_id, 'day', DAY, {'daily': [{'日期': DAY, '食材明细': f'{BAD} 2斤 20'}]})
        self.put_record(self.dataset_id, 'global', 'inventory', {'item_settings': [
            {'category': '食材', 'name': GOOD, 'unit': '斤', 'min_quantity': 1}]})
        self.assertTrue(self.preview().json()['requires_merge_confirmation'])

    def test_identical_threshold_deduplicates_and_conflicting_threshold_blocks(self):
        self.seed()
        setting = {'category': '食材', 'unit': '桶', 'min_quantity': 2, 'unknown': {'keep': True}}
        self.put_record(self.dataset_id, 'global', 'inventory', {'item_settings': [
            {**setting, 'name': BAD}, {**setting, 'name': GOOD}]})
        value = self.preview().json()
        self.assertTrue(value['can_apply'], value)
        applied = self.apply(self.request(preview=value))
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(self.load('global', 'inventory')['payload']['item_settings'], [{**setting, 'name': GOOD}])
        self.seed()
        self.put_record(self.dataset_id, 'global', 'inventory', {'item_settings': [
            {**setting, 'name': BAD}, {**setting, 'name': GOOD, 'min_quantity': 3}]})
        conflict = self.preview().json()
        self.assertFalse(conflict['can_apply'])
        self.assertTrue(any('安全库存' in message for message in conflict['blockers']))

    def test_cross_category_ambiguity_and_malformed_matching_records_block(self):
        self.seed()
        self.put_record(self.dataset_id, 'global', 'inventory', {'entries': [
            {'id': 'spice', 'date': DAY, 'category': '佐料', 'name': BAD, 'unit': '袋',
             'quantity': 1, 'unit_price': 1, 'total': 1}]})
        payload = self.load('day', DAY)['payload']
        payload['dishes'] = [{'日期': DAY, '菜品数据': [{'食材明细': [{'name': BAD, 'quantity': 1, 'unit': '箱'}]}]}]
        self.put_record(self.dataset_id, 'day', DAY, payload)
        ambiguous = self.preview().json()
        self.assertFalse(ambiguous['can_apply'])
        self.assertTrue(any('分类' in message for message in ambiguous['blockers']))
        with database.SessionLocal() as db:
            inventory = main.get_record(db, self.dataset_id, 'global', 'inventory')
            inventory.payload = {'entries': {'name': BAD, 'quantity': 3}}
            db.commit()
        malformed = self.preview()
        self.assertEqual(malformed.status_code, 200, malformed.text)
        self.assertFalse(malformed.json()['can_apply'])
        with database.SessionLocal() as db:
            inventory = main.get_record(db, self.dataset_id, 'global', 'inventory')
            inventory.payload = {'entries': [{'name': BAD, 'quantity': float('nan'), 'unit': '桶'}]}
            db.commit()
        self.assertEqual(self.preview().status_code, 422)

    def test_existing_negative_balance_can_be_corrected_by_explicit_actual_count(self):
        self.put_record(self.dataset_id, 'day', DAY, {'dishes': [{'日期': DAY,
            '菜品数据': [{'食材明细': [{'name': BAD, 'quantity': 2, 'unit': '桶'}]}]}]})
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 7}]}
        preview = self.preview(spec).json()
        self.assertTrue(preview['can_apply'], preview)
        self.assertEqual(preview['inventory_effects'][0]['combined_quantity'], -2)
        self.assertEqual(preview['inventory_effects'][0]['delta'], 9)
        self.assertEqual(self.apply(self.request(spec, preview)).status_code, 200)

    def test_idempotency_survives_audit_deletion_and_rejects_different_body(self):
        self.seed()
        request = self.request()
        first = self.apply(request)
        self.assertEqual(first.status_code, 200, first.text)
        with database.SessionLocal() as db:
            db.execute(delete(AuditLog).where(AuditLog.dataset_id == self.dataset_id))
            db.commit()
        retry = self.apply(request)
        self.assertEqual(first.json(), retry.json())
        self.assertEqual(self.apply({**request, 'reason': 'changed'}).status_code, 409)

    def test_new_purchase_final_change_and_midnight_invalidate_preview(self):
        self.seed()
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 7}]}
        request = self.request(spec)
        self.assertEqual(self.apply({**request, 'final_quantities': [{'unit': '桶', 'quantity': 8}]}).status_code, 409)
        with patch.object(main, 'utcnow', return_value=NOW + timedelta(days=1)):
            self.assertEqual(self.apply(request).status_code, 409)
        self.put_record(self.dataset_id, 'day', '2026-10-27', {'daily': [{'日期': '2026-10-27', '食材明细': f'{BAD} 1桶 30'}]})
        self.assertEqual(self.apply(request).status_code, 409)
        self.assertEqual(self.load('day', DAY)['payload']['daily'][0]['食材明细'][0]['name'], BAD)

    def test_preview_permissions_and_apply_admin_only(self):
        self.seed()
        editor = self.create_role_headers(self.dataset_id, 'edit-' + self.dataset_id, 'editor')
        entry = self.create_role_headers(self.dataset_id, 'entry-' + self.dataset_id, 'entry')
        viewer = self.create_role_headers(self.dataset_id, 'view-' + self.dataset_id, 'viewer')
        self.assertEqual(self.preview(headers=editor).status_code, 200)
        self.assertEqual(self.preview(headers=entry).status_code, 403)
        self.assertEqual(self.preview(headers=viewer).status_code, 403)
        request = self.request()
        self.assertEqual(self.apply(request, editor).status_code, 403)
        request['confirm_merge'] = False
        self.assertEqual(self.apply(request).status_code, 422)

    def test_legacy_edit_clock_not_reopened_and_audit_has_reason(self):
        self.seed(text=True)
        old_time = NOW - timedelta(hours=2)
        with database.SessionLocal() as db:
            row = main.get_record(db, self.dataset_id, 'day', DAY)
            row.updated_at = old_time
            db.execute(delete(EntryTiming).where(EntryTiming.dataset_id == self.dataset_id))
            db.commit()
        request = self.request()
        applied = self.apply(request)
        self.assertEqual(applied.status_code, 200, applied.text)
        saved = self.load('day', DAY)
        self.assertEqual(datetime.fromisoformat(saved['updated_at']).replace(tzinfo=timezone.utc), old_time)
        headers = self.create_role_headers(self.dataset_id, 'clock-' + self.dataset_id, 'entry')
        changed = deepcopy(saved['payload'])
        changed['daily'][0]['食材明细'] = changed['daily'][0]['食材明细'].replace('100.00', '110.00')
        denied = self.client.put(self.base + f'/records/day/{DAY}', headers=headers,
                                 json={'payload': changed, 'expected_version': saved['version']})
        self.assertEqual(denied.status_code, 403, denied.text)
        with database.SessionLocal() as db:
            logs = db.scalars(select(AuditLog).where(AuditLog.dataset_id == self.dataset_id,
                                                    AuditLog.event_id == request['request_id'])).all()
            self.assertTrue(logs)
            self.assertTrue(all(main.audit_out(log)['reason'] == request['reason'] for log in logs))

    def test_failure_rolls_back_all_records_and_operation_receipt(self):
        self.seed(counts=True)
        before_day, before_inventory = self.load('day', DAY), self.load('global', 'inventory')
        request = self.request()
        with patch.object(main, 'add_audit', side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):
                self.apply(request)
        self.assertEqual(self.load('day', DAY), before_day)
        self.assertEqual(self.load('global', 'inventory'), before_inventory)
        with database.SessionLocal() as db:
            self.assertIsNone(db.scalar(select(InventoryNameCorrection).where(InventoryNameCorrection.dataset_id == self.dataset_id)))

    def test_shared_date_sources_preserve_canonical_and_old_clocks(self):
        self.put_record(self.dataset_id, 'day', 'packed-old', {'daily': [{'日期': DAY, '食材明细': f'{BAD} 2桶 100', '收益': 200}]})
        self.put_record(self.dataset_id, 'day', DAY, {'daily': [{'日期': DAY, '食材明细': f'{GOOD} 3桶 45', '收益': 300}]})
        before_current = self.load('day', DAY)
        preview = self.preview().json()
        self.assertTrue(preview['can_apply'], preview)
        applied = self.apply(self.request(preview=preview))
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(len(applied.json()['changed_records']), 2)
        current = self.load('day', DAY)
        self.assertEqual(current['payload'], before_current['payload'])
        self.assertEqual(current['updated_at'], before_current['updated_at'])
        self.assertGreater(current['sequence'], self.load('day', 'packed-old')['sequence'])

    def test_json_numeric_tokens_notes_substrings_and_dish_titles_preserved(self):
        raw = '[ {"name":"大豆油 2桶", "quantity":2.000, "total":1e2, "note":"大豆油 2桶", "unknown": {"v":1.2300}}, {"name":"大豆油 2桶装","quantity":9,"unit":"桶"} ]'
        payload = {'daily': [{'日期': DAY, '食材明细': raw}], 'dishes': [{'日期': DAY, '菜品数据': json.dumps([
            {'菜品名称': BAD, '食材明细': [{'name': BAD, 'quantity': 1, 'unit': ''}]}], ensure_ascii=False)}]}
        self.put_record(self.dataset_id, 'day', DAY, payload)
        with database.SessionLocal() as db:
            record = main.get_record(db, self.dataset_id, 'day', DAY)
            record.payload = payload
            db.commit()
        applied = self.apply(self.request())
        self.assertEqual(applied.status_code, 200, applied.text)
        saved = self.load('day', DAY)['payload']
        self.assertEqual(saved['daily'][0]['食材明细'], raw.replace('"name":"大豆油 2桶"', '"name":"大豆油"'))
        self.assertEqual(json.loads(saved['dishes'][0]['菜品数据'])[0]['菜品名称'], BAD)

    def test_deleted_inventory_final_count_block_and_dataset_delete_cascades(self):
        self.seed()
        self.put_record(self.dataset_id, 'global', 'inventory', {'entries': []})
        self.client.post(self.base + '/records/global/inventory/delete', headers=self.headers, json={})
        spec = {**self.spec, 'final_quantities': [{'unit': '桶', 'quantity': 7}]}
        self.assertFalse(self.preview(spec).json()['can_apply'])
        self.assertEqual(self.apply(self.request()).status_code, 200)
        deleted = self.client.delete(self.base, headers=self.headers, params={'confirm_name': '品名更正测试'})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        with database.SessionLocal() as db:
            self.assertIsNone(db.scalar(select(InventoryNameCorrection).where(InventoryNameCorrection.dataset_id == self.dataset_id)))


del _Fixture
