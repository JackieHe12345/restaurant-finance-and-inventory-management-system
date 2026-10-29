from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_dataset_api import DatasetApiTests as _Fixture
from app import main, database
from app.money import money, money_text, price_text, product, normalize_payload, MoneyError
from app.models import SyncRecord, EntryTiming
from app.excel_io import payload_checksum

NOW = datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
DAY = '2026-10-29'

class ExactMoneyApiTests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    tearDownClass = classmethod(_Fixture.tearDownClass.__func__)
    create_dataset = _Fixture.create_dataset
    create_role_headers = _Fixture.create_role_headers

    def setUp(self):
        self.dataset_id = 'money-' + uuid4().hex[:8]
        self.create_dataset(self.dataset_id, '精确金额')
        self.base = '/api/v1/datasets/' + self.dataset_id
        self.url = self.base + '/records/day/' + DAY
        self.clock = patch.object(main, 'utcnow', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def save(self, payload, headers=None):
        return self.client.put(self.url, headers=headers or self.headers, json={'payload': payload})

    def test_decimal_half_up_limits_and_fractional_quantity_cost(self):
        self.assertEqual(money_text(money('0.1') + money('0.2')), '0.30')
        self.assertEqual(money_text('1.005'), '1.01')
        self.assertEqual(money_text('-1.005'), '-1.01')
        self.assertEqual(price_text('1.0000005'), '1.000001')
        self.assertEqual(product('0.000001', '10000.000000'), Decimal('0.01'))
        self.assertEqual(money_text('999999999999.99'), '999999999999.99')
        for value in ('NaN', 'Infinity', '-Infinity', True, '1000000000000', '1e999', 'bad'):
            with self.subTest(value=value), self.assertRaises(MoneyError):
                money(value)

    def test_http_numeric_lexeme_nested_money_and_unknown_metadata(self):
        # Digits beyond binary-double precision must reach the Decimal parser.
        raw = '{"payload":{"daily":[{"日期":"2026-10-29","A店现金":999999999999.984999,"食材明细":[{"name":"牛肉","quantity":0.25,"total":1.005,"unit_price":4.0000005,"unit":"斤","metadata":{"amount":1.005}}],"新客人数量":2,"总客人数":3}],"metadata":{"amount":1.005}}}'
        saved = self.client.put(self.url, headers={**self.headers, 'Content-Type': 'application/json'}, content=raw)
        self.assertEqual(saved.status_code, 200, saved.text)
        value = saved.json()['payload']
        row = value['daily'][0]
        self.assertEqual(row['A店现金'], '999999999999.98')
        self.assertEqual(row['食材明细'][0]['total'], '1.01')
        self.assertEqual(row['食材明细'][0]['unit_price'], '4.000001')
        self.assertEqual(row['食材明细'][0]['quantity'], .25)
        self.assertEqual(row['食材明细'][0]['metadata'], {'amount': 1.005})
        self.assertEqual(value['metadata'], {'amount': 1.005})
        self.assertEqual(row['新客人数量'], 2)

    def test_json_media_types_preserve_numeric_lexeme(self):
        raw = '{"payload":{"daily":[{"日期":"2026-10-29","收益":1.004999999999999999999}]}}'
        for media_type in ('application/json', 'Application/JSON', 'application/vnd.api+json', None):
            headers = {**self.headers, **({'Content-Type': media_type} if media_type else {})}
            response = self.client.put(self.url, headers=headers, content=raw)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['payload']['daily'][0]['收益'], '1.00')

    def test_aggregate_cash_can_exceed_single_input_limit(self):
        opening = self.client.put(self.base + '/cash-position', headers=self.headers,
            json={'opening_balance': '999999999999.99', 'opening_date': '2026-10-28'})
        self.assertEqual(opening.status_code, 200, opening.text)
        self.assertEqual(self.save({'daily': [{'日期': DAY, 'A店现金': '999999999999.99',
            'B店现金': '999999999999.99'}]}).status_code, 200)
        response = self.client.get(self.base + '/cash-position', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['income'], '1999999999999.98')
        self.assertEqual(response.json()['current_balance'], '2999999999999.97')

    def test_derived_totals_over_limit_save_and_reload_with_source_details(self):
        row = {'日期': DAY, 'A店现金': '999999999999.99', 'B店现金': '999999999999.99',
               'A店收入': '999999999999.99', 'B店收入': '999999999999.99',
               '总现金': '1999999999999.98', '收益': '1999999999999.98',
               '食材成本': '1999999999999.98', '食材明细': [
                   {'name': '米', 'total': '999999999999.99'}, {'name': '面', 'total': '999999999999.99'}]}
        result = self.save({'daily': [row]})
        self.assertEqual(result.status_code, 200, result.text)
        loaded = self.client.get(self.url, headers=self.headers).json()['payload']['daily'][0]
        self.assertEqual(loaded['收益'], '1999999999999.98')
        self.assertEqual(loaded['食材成本'], '1999999999999.98')
        invalid = deepcopy(row); invalid['A店现金'] = '1000000000000.00'
        self.assertEqual(self.save({'daily': [invalid]}).status_code, 422)
        self.assertEqual(self.save({'daily': [{'日期': DAY, '收益': '2000000000000.00'}]}).status_code, 422)

    def test_exact_nested_old_text_is_not_changed_or_unlocked(self):
        entry = self.create_role_headers(self.dataset_id, 'e-' + self.dataset_id, 'entry')
        raw = '[{"name":"米","quantity":1,"unit":"斤","total":1.004999999999999999999}]'
        original = {'daily': [{'日期': DAY, '食材明细': raw}]}
        with database.SessionLocal() as db:
            db.add(SyncRecord(dataset_id=self.dataset_id, record_type='day', record_key=DAY,
                payload=original, checksum=payload_checksum(original), version=1, sequence=1,
                updated_at=NOW-timedelta(hours=1), created_at=NOW-timedelta(hours=1)))
            db.commit()
        incoming = deepcopy(original)
        incoming['daily'][0]['食材明细'] = '[{"name":"米","quantity":1,"unit":"斤","total":"1.00"}]'
        incoming['daily'][0].update({'新客人数量': 1, '总客人数': 2})
        result = self.save(incoming, entry)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['payload']['daily'][0]['食材明细'], raw)
        incoming['daily'][0]['食材明细'] = incoming['daily'][0]['食材明细'].replace('1.00', '1.01')
        self.assertEqual(self.save(incoming, entry).status_code, 403)

    def test_nested_dish_json_keeps_fractional_quantity_serializable(self):
        items = [{'name': '大豆油 2桶', 'quantity': .5, 'unit': '桶', 'total': 25,
                  'extension': {'amount': 1.005, 'ratio': .125}}]
        payload = {'daily': [{'日期': DAY, '食材成本': 130, '食材明细': json.dumps([
            {'name': '大豆油 2桶', 'quantity': 2, 'unit': '桶', 'price': 50, 'total': 100},
            {'name': '大豆油', 'quantity': 3, 'unit': '桶', 'price': 10, 'total': 30}])}],
            'dishes': [{'日期': DAY, '菜品数据': json.dumps([{'菜品名称': '大豆油 2桶', '食材明细': items}])}]}
        result = self.save(payload)
        self.assertEqual(result.status_code, 200, result.text)
        row = json.loads(result.json()['payload']['dishes'][0]['菜品数据'])[0]['食材明细'][0]
        self.assertEqual(row['quantity'], .5)
        self.assertIsInstance(row['quantity'], float)
        self.assertEqual(row['total'], '25.00')
        self.assertEqual(row['extension'], {'amount': 1.005, 'ratio': .125})

    def test_cash_is_exact_and_automatic_purchase_is_not_double_charged(self):
        saved = self.save({'daily': [{'日期': DAY, 'A店现金': '0.10', 'B店现金': '0.20', '食材成本': '0.10',
            '食材明细': '[{"name":"牛肉","quantity":1,"unit":"斤","total":"0.10"}]'}]})
        self.assertEqual(saved.status_code, 200, saved.text)
        value = self.client.get(self.base + '/cash-position', headers=self.headers).json()
        self.assertEqual(value['income'], '0.30')
        self.assertEqual(value['daily_expenses'], '0.10')
        self.assertEqual(value['inventory_expenses'], '0.00')
        self.assertEqual(value['current_balance'], '0.20')
        self.assertTrue(all(not isinstance(row['amount'], float) for row in value['entries']))

    def test_bad_money_rejects_entire_write_and_keeps_version(self):
        saved = self.save({'daily': [{'日期': DAY, '收益': '1.005'}]})
        self.assertEqual(saved.status_code, 200)
        version = saved.json()['version']
        for value in ('NaN', 'Infinity', True, '1000000000000', 'bad'):
            response = self.save({'daily': [{'日期': DAY, '收益': value, '新客人数量': 1, '总客人数': 1}]})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.client.get(self.url, headers=self.headers).json()['version'], version)
        self.assertEqual(self.client.get(self.url, headers=self.headers).json()['payload']['daily'][0]['收益'], '1.01')

    def test_invalid_text_prices_and_boolean_cash_are_rejected(self):
        for text in ('牛肉 1斤 NaN', '牛肉 1斤 Infinity', '牛肉 1斤 1000000000000'):
            response = self.save({'daily': [{'日期': DAY, '食材明细': text}]})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.client.put(self.base + '/cash-position', headers=self.headers,
                                   json={'opening_balance': True})
        self.assertEqual(response.status_code, 422, response.text)

    def test_numeric_history_and_json_string_precision_do_not_reopen_clocks(self):
        entry = self.create_role_headers(self.dataset_id, 'e-' + self.dataset_id, 'entry')
        original = {'daily': [{'日期': DAY, 'A店现金': 12.3, '食材成本': 3,
            '食材明细': '[ {"name":"牛肉", "quantity":2.000, "total":3.0, "unit":"斤", "unknown":{"v":1.2300}} ]'}]}
        with database.SessionLocal() as db:
            db.add(SyncRecord(dataset_id=self.dataset_id, record_type='day', record_key=DAY,
                payload=original, checksum=payload_checksum(original), version=1, sequence=1,
                updated_at=NOW-timedelta(hours=1), created_at=NOW-timedelta(hours=1)))
            db.commit()
        incoming = deepcopy(original)
        incoming['daily'][0].update({'A店现金': '12.30', '食材成本': '3.00', '新客人数量': 2, '总客人数': 5,
            '食材明细': '[{"name":"牛肉","quantity":2,"total":"3.00","unit":"斤","unknown":{"v":1.23}}]'})
        response = self.save(incoming, entry)
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()['payload']['daily'][0]
        self.assertEqual(row['食材明细'], original['daily'][0]['食材明细'])
        self.assertEqual(type(row['A店现金']), float)  # Existing raw data was not migrated.
        changed = deepcopy(incoming); changed['daily'][0]['A店现金'] = '12.31'
        self.assertEqual(self.save(changed, entry).status_code, 403)
        with patch.object(main, 'utcnow', return_value=NOW+timedelta(minutes=31)):
            changed = deepcopy(incoming); changed['daily'][0]['总客人数'] = 6
            self.assertEqual(self.save(changed, entry).status_code, 403)

    def test_text_amount_format_only_is_not_a_locked_detail_edit(self):
        entry = self.create_role_headers(self.dataset_id, 'e-' + self.dataset_id, 'entry')
        saved = self.save({'daily': [{'日期': DAY, '食材成本': '3', '食材明细': '牛肉 1斤 3'}]}, entry)
        self.assertEqual(saved.status_code, 200)
        with patch.object(main, 'utcnow', return_value=NOW+timedelta(minutes=31)):
            response = self.save({'daily': [{'日期': DAY, '食材成本': '3.00', '食材明细': '牛肉 1斤 3.00', '新客人数量': 1, '总客人数': 2}]}, entry)
            self.assertEqual(response.status_code, 200, response.text)


del _Fixture

class MoneyStorageTests(unittest.TestCase):
    def test_engine_legacy_numeric_lexemes_survive_unrelated_update(self):
        from sqlalchemy import create_engine, MetaData, Table, Column, Integer, JSON, select, text
        from app.money import storage_json_loads, storage_json_dumps, LegacyMoneyNumber
        engine = create_engine('sqlite+pysqlite://', json_serializer=storage_json_dumps,
                               json_deserializer=storage_json_loads)
        table = Table('money_storage', MetaData(), Column('id', Integer, primary_key=True), Column('payload', JSON))
        table.metadata.create_all(engine)
        original = '{"daily":[{"日期":"2026-10-29","A店现金":999999999999.984999,"食材成本":1.005,"新客人数量":"","总客人数":""}],"entries":[{"id":"old","unit_price":1.230000,"total":1.005}],"extension":{"literal":"999999999999.984999","quantity":2.5}}'
        with engine.begin() as connection:
            connection.execute(text('INSERT INTO money_storage(id,payload) VALUES(1,:payload)'), {'payload': original})
            loaded = connection.scalar(select(table.c.payload))
            self.assertIsInstance(loaded['daily'][0]['A店现金'], LegacyMoneyNumber)
            self.assertEqual(money_text(loaded['daily'][0]['A店现金']), '999999999999.98')
            incoming = json.loads(json.dumps(loaded))
            incoming['daily'][0].update({'新客人数量': 2, '总客人数': 3})
            candidate = normalize_payload(incoming, loaded)
            candidate['entries'][0]['name'] = '更正品名'
            connection.execute(table.update().values(payload=candidate))
            stored_text = connection.scalar(text('SELECT payload FROM money_storage'))
        stored = json.loads(stored_text, parse_float=Decimal)
        self.assertEqual(stored['daily'][0]['A店现金'], Decimal('999999999999.984999'))
        self.assertEqual(stored['entries'][0]['unit_price'], Decimal('1.230000'))
        self.assertIsInstance(stored['daily'][0]['食材成本'], Decimal)
        self.assertEqual(stored['daily'][0]['食材成本'], Decimal('1.005'))
        self.assertEqual(stored['extension']['literal'], '999999999999.984999')
        self.assertIn('"unit_price":1.230000', stored_text)
        self.assertIn('"A店现金":999999999999.984999', stored_text)
        engine.dispose()

    def test_storage_serializer_is_structural_and_new_money_stays_string(self):
        from app.money import storage_json_dumps, LegacyMoneyNumber
        text = storage_json_dumps({'old': LegacyMoneyNumber('1.230000'), 'new': '1.23',
                                   'literal': '1.230000,"hacked":true', 'list': [LegacyMoneyNumber('2.50')]})
        value = json.loads(text, parse_float=Decimal)
        self.assertEqual(value['old'], Decimal('1.230000'))
        self.assertEqual(value['new'], '1.23')
        self.assertEqual(value['literal'], '1.230000,"hacked":true')
        self.assertEqual(value['list'], [Decimal('2.50')])
        with self.assertRaises(MoneyError):
            storage_json_dumps({'bad': LegacyMoneyNumber('1,"hacked":true')})

    def test_internal_export_preserves_database_numeric_money_token(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.money import storage_json_loads
        from app.excel_io import build_internal_workbook, WorkbookRecord
        payload = storage_json_loads('{"daily":[{"日期":"2026-10-29","收益":999999999999.984999}]}')
        content = build_internal_workbook(dataset_id='exact', schema_version=3,
            records=[WorkbookRecord('day', DAY, payload, '')])
        workbook = load_workbook(BytesIO(content))
        body = workbook['__day_records']['C2'].value
        workbook.close()
        self.assertIn('"收益":999999999999.984999', body)
        self.assertEqual(json.loads(body, parse_float=Decimal)['daily'][0]['收益'], Decimal('999999999999.984999'))
