"""v1.0.1 audit regressions. In-memory SQLite, synthetic XLSX, no network."""
from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

# Never inherit a production database or start the payment scheduler.
os.environ.update(DATABASE_URL="sqlite+pysqlite://", WECHAT_AUTO_SYNC="false")
os.environ.setdefault("SECRET_KEY", "v1_0_1-regression-only")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "Admin123!")

import test_dataset_api as fixture
from openpyxl import load_workbook
from app import database, main
from app.excel_io import (WorkbookRecord, WorkbookFormatError, build_user_workbook,
                          parse_internal_workbook, payload_checksum)
from app.inventory_balance import canonical_daily_rows, ledger_events, replay_quantities
from app.models import SyncRecord

NOW = datetime(2026, 11, 4, 4, tzinfo=timezone.utc)


class V101BackendTests(unittest.TestCase):
    create_dataset = fixture.DatasetApiTests.create_dataset
    create_role_headers = fixture.DatasetApiTests.create_role_headers

    @classmethod
    def setUpClass(cls):
        fixture.DatasetApiTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.DatasetApiTests.tearDownClass.__func__(cls)

    def setUp(self):
        self.dataset = self._testMethodName.replace("test_", "n5-").replace("_", "-")[:48]
        self.create_dataset(self.dataset, self.dataset)
        self.base = "/api/v1/datasets/" + self.dataset
        self.clock = patch.object(main, "utcnow", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def put(self, key, payload, headers=None, **body):
        return self.client.put(self.base + "/records/day/" + key,
                              headers=headers or self.headers, json={"payload": payload, **body})

    def rows(self):
        result = self.client.get(self.base + "/records", headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def grant(self):
        viewer = self.create_role_headers(self.dataset, self.dataset, "viewer")
        user = self.client.get("/api/v1/auth/me", headers=viewer).json()
        response = self.client.post("/api/v1/temporary-permissions", headers=self.headers, json={
            "user_id": user["id"], "dataset_id": self.dataset, "permission_role": "editor",
            "business_start_date": "2026-11-04", "business_end_date": "2026-11-04",
            "starts_at": (NOW-timedelta(hours=1)).isoformat(), "ends_at": (NOW+timedelta(hours=1)).isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        return viewer

    def test_b01_mixed_dates_cannot_elevate_whole_record(self):
        viewer = self.grant()
        old = {"daily": [{"日期": "2026-10-01", "收益": "100.00"}]}
        self.assertEqual(self.put("2026-10-01", old).status_code, 200)
        forged = {"daily": [{"日期": "2026-10-01", "收益": "999.00"}, {"日期": "2026-11-04"}]}
        result = self.put("2026-10-01", forged, viewer)
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.rows()[0]["payload"], old)

    def test_b01_fixed_dishes_and_removed_dates_are_authorized(self):
        viewer = self.grant()
        old = {"daily": [{"日期": "2026-11-04", "收益": "100.00"}],
               "fixed_expenses": [{"日期": "2026-10-01", "金额": "10.00"}],
               "dishes": [{"日期": "2026-10-02", "总成本": "20.00"}]}
        self.assertEqual(self.put("2026-11-04", old).status_code, 200)
        for table in ("fixed_expenses", "dishes"):
            with self.subTest(table=table):
                incoming = deepcopy(self.rows()[0]["payload"])
                incoming[table] = []
                response = self.put("2026-11-04", incoming, viewer)
                self.assertEqual(response.status_code, 403, response.text)
        response = self.client.post(self.base + "/records/day/2026-11-04/delete", headers=viewer, json={})
        self.assertEqual(response.status_code, 403, response.text)

    def test_b01_unchanged_legacy_dates_do_not_block_permitted_edit(self):
        viewer = self.grant()
        old = {"daily": [{"日期": "2026-10-01", "收益": "100.00"}, {"日期": "2026-11-04", "收益": "50.00"}]}
        self.assertEqual(self.put("2026-10-01", old).status_code, 200)
        incoming = deepcopy(old)
        incoming["daily"][1]["收益"] = "60.00"
        response = self.put("2026-10-01", incoming, viewer)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["payload"]["daily"][0], old["daily"][0])

    def test_b01_edit_cannot_promote_old_source_on_ungranted_day(self):
        viewer = self.grant()
        packed = {"daily": [{"日期": "2026-10-01", "收益": "100.00"}, {"日期": "2026-11-04", "收益": "50.00"}]}
        self.put("2026-10-01", packed)
        self.put("2026-10-02", {"daily": [{"日期": "2026-10-01", "收益": "200.00"}]})
        incoming = deepcopy(packed)
        incoming["daily"][1]["收益"] = "60.00"
        result = self.put("2026-10-01", incoming, viewer)
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(canonical_daily_rows(self.rows())["2026-10-01"]["收益"], "200.00")

    def test_b01_identical_daily_values_cannot_change_dish_source(self):
        viewer = self.grant()
        daily = {"日期": "2026-10-01", "收益": "100.00"}
        def dish(quantity):
            return {"日期": "2026-10-01", "菜品数据": json.dumps([
                {"菜品名称": "米饭", "食材明细": f"米 {quantity}斤 1.00", "成本": "1.00"}], ensure_ascii=False)}
        packed = {"daily": [daily, {"日期": "2026-11-04", "收益": "50.00"}], "dishes": [dish(1)]}
        self.put("2026-10-01", packed)
        self.put("2026-10-02", {"daily": [daily], "dishes": [dish(2)]})
        incoming = deepcopy(packed)
        incoming["daily"][1]["收益"] = "60.00"
        result = self.put("2026-10-01", incoming, viewer)
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(ledger_events({}, self.rows(), [])["outbounds"][0]["quantity"], 2)

    def test_b02_locked_derived_totals_cannot_change_alone(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        original = {"daily": [{"日期": "2026-11-04", "食材明细": "米 1斤 10.00", "食材成本": "10.00",
                               "A店现金": "100.00", "A店收入": "100.00"}]}
        self.assertEqual(self.put("2026-11-04", original, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            for field, amount in (("食材成本", "99.00"), ("A店收入", "999.00")):
                incoming = deepcopy(original)
                incoming["daily"][0][field] = amount
                response = self.put("2026-11-04", incoming, entry)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.rows()[0]["payload"], original)

    def test_b02_append_does_not_authorize_arbitrary_total(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "食材明细": "米 1斤 10.00", "食材成本": "10.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            incoming = {**row, "食材明细": row["食材明细"] + ", 菜 1斤 5.00", "食材成本": "999.00"}
            response = self.put("2026-11-04", {"daily": [incoming]}, entry)
            self.assertEqual(response.status_code, 422, response.text)
            incoming["食材成本"] = "15.00"
            response = self.put("2026-11-04", {"daily": [incoming]}, entry)
            self.assertEqual(response.status_code, 200, response.text)

    def test_b02_legacy_total_only_and_unknown_prices_remain_compatible(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        detail = json.dumps([{"name": "米", "quantity": "2", "unit": "斤", "price": "", "total": "", "note": "备注,另加5"}], ensure_ascii=False)
        row = {"日期": "2026-11-04", "食材明细": detail, "食材成本": "0.00", "A店收入": "100.00", "其他": "15.80"}
        response = self.put("2026-11-04", {"daily": [row]}, entry)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["payload"]["daily"][0], row)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            self.assertEqual(self.put("2026-11-04", {"daily": [{**row, "当日备注": "新备注"}]}, entry).status_code, 200)
            response = self.put("2026-11-04", {"daily": [{**row, "A店收入": "200.00"}]}, entry)
            self.assertEqual(response.status_code, 403, response.text)
            disguised = {**row, "其他明细": json.dumps([{"name": "1", "quantity": "", "unit": "", "price": "", "total": "5.80", "note": ""}]), "其他": "5.80"}
            response = self.put("2026-11-04", {"daily": [disguised]}, entry)
            self.assertEqual(response.status_code, 403, response.text)

    def test_b02_payment_formula_zero_override_and_invalid_total(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "A店现金": "100.00", "A店微信自动": "80.00", "A店微信覆盖": "0.00",
               "B店支付宝增加": "20.00", "A店外卖": "5.00", "学生外卖": "3.00",
               "A店收入": "105.00", "B店收入": "20.00", "总现金": "100.00", "总线上": "28.00", "收益": "128.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        response = self.put("2026-11-04", {"daily": [{**row, "A店现金": "101.00", "A店收入": "999.00"}]}, entry)
        self.assertEqual(response.status_code, 422, response.text)

    def test_b02_legacy_raw_channels_do_not_bypass_total_locks(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "A店微信自动": "100.00", "A店收入": "100.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            response = self.put("2026-11-04", {"daily": [{**row, "A店微信自动": "999.00", "A店收入": "999.00"}]}, entry)
        self.assertEqual(response.status_code, 403, response.text)

    def test_b02_legacy_store_total_keeps_lock_when_channels_appear(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "A店收入": "100.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            changed = {**row, "A店现金": "999.00", "A店收入": "999.00"}
            result = self.put("2026-11-04", {"daily": [changed]}, entry)
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.rows()[0]["payload"], {"daily": [row]})

    def test_b02_legacy_grand_total_keeps_lock_when_channels_appear(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "收益": "100.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            changed = {**row, "A店现金": "999.00", "A店收入": "999.00", "收益": "999.00"}
            result = self.put("2026-11-04", {"daily": [changed]}, entry)
        self.assertEqual(result.status_code, 403, result.text)
        self.assertEqual(self.rows()[0]["payload"], {"daily": [row]})

    def test_b02_equivalent_total_conversion_preserves_clock(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "A店收入": "100.00"}
        self.assertEqual(self.put("2026-11-04", {"daily": [row]}, entry).status_code, 200)
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            converted = {**row, "A店现金": "100.00"}
            result = self.put("2026-11-04", {"daily": [converted]}, entry)
            self.assertEqual(result.status_code, 200, result.text)
            changed = {**converted, "A店现金": "999.00", "A店收入": "999.00"}
            result = self.put("2026-11-04", {"daily": [changed]}, entry)
            self.assertEqual(result.status_code, 403, result.text)

    def test_b02_legacy_amount_without_space_and_unpriced_quantity(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "其他明细": "水15.80", "其他": "15.80",
               "食材明细": "米 2斤", "食材成本": "0.00"}
        result = self.put("2026-11-04", {"daily": [row]}, entry)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["payload"]["daily"][0], row)

    def test_b02_json_format_upgrade_keeps_old_item_clock_and_allows_append(self):
        entry = self.create_role_headers(self.dataset, self.dataset, "entry")
        row = {"日期": "2026-11-04", "食材明细": "米 1斤 10.00, 米 1公斤 20.00", "食材成本": "30.00"}
        result = self.put("2026-11-04", {"daily": [row]}, entry)
        self.assertEqual(result.status_code, 200, result.text)
        items = [{"name": "米", "quantity": "1", "unit": unit, "price": price, "total": total, "note": ""}
                 for unit, price, total in (("斤", "10.000000", "10.00"), ("公斤", "20.000000", "20.00"))]
        items.append({"name": "菜", "quantity": "1", "unit": "斤", "price": "5.000000", "total": "5.00", "note": ""})
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=1)):
            incoming = {**row, "食材明细": json.dumps(items, ensure_ascii=False), "食材成本": "35.00"}
            result = self.put("2026-11-04", {"daily": [incoming]}, entry)
            self.assertEqual(result.status_code, 200, result.text)
            for field, value in (("quantity", "2"), ("total", "11.00"), ("note", "改备注"), ("unit", "公斤")):
                changed = deepcopy(items)
                changed[0][field] = value
                result = self.put("2026-11-04", {"daily": [{**incoming, "食材明细": json.dumps(changed, ensure_ascii=False)}]}, entry)
                self.assertEqual(result.status_code, 403, (field, result.text))
        with patch.object(main, "utcnow", return_value=NOW+timedelta(hours=13)):
            items.append({"name": "盐", "quantity": "1", "unit": "斤", "price": "1.000000", "total": "1.00", "note": ""})
            result = self.put("2026-11-04", {"daily": [{**incoming, "食材明细": json.dumps(items, ensure_ascii=False), "食材成本": "36.00"}]}, entry)
            self.assertEqual(result.status_code, 403, result.text)

    def test_b03_all_cash_aliases_hidden_and_cursor_progresses(self):
        for key in ("cash_position", "cash_balance", "base_balance"):
            response = self.client.put(self.base + "/records/global/" + key, headers=self.headers,
                                       json={"payload": {"opening_balance": "54321.00", "transactions": []}})
            self.assertEqual(response.status_code, 200, response.text)
        self.put("2026-11-04", {"daily": [{"日期": "2026-11-04", "收益": "1.00"}]})
        for role in ("viewer", "entry"):
            headers = self.create_role_headers(self.dataset, self.dataset + role, role)
            for key in ("cash_position", "cash_balance", "base_balance"):
                result = self.client.get(self.base + "/records/global/" + key, headers=headers)
                self.assertEqual(result.status_code, 403, result.text)
            rows = self.client.get(self.base + "/records?limit=1", headers=headers).json()
            self.assertEqual([row["record_type"] for row in rows], ["day"])
            cursor, seen = 0, []
            for _ in range(4):
                page = self.client.get(self.base + f"/changes?after_sequence={cursor}&limit=1", headers=headers).json()
                self.assertGreater(page["next_sequence"], cursor)
                cursor = page["next_sequence"]
                seen.extend(page["items"])
                if not page["has_more"]:
                    break
            self.assertEqual([row["record_type"] for row in seen], ["day"])
        self.assertEqual(len(self.rows()), 4)

    def test_b04_deleted_canonical_restores_and_retires_alias(self):
        with database.SessionLocal() as db:
            for key, deleted, version, seq in (("cash_position", True, 7, 7), ("cash_balance", False, 5, 8)):
                payload = {"opening_balance": "100.00", "opening_date": "2026-10-01", "transactions": []}
                db.add(SyncRecord(dataset_id=self.dataset, record_type="global", record_key=key,
                                  payload=payload, checksum=payload_checksum(payload), version=version, sequence=seq, is_deleted=deleted))
            db.commit()
        response = self.client.put(self.base + "/cash-position", headers=self.headers,
                                   json={"opening_balance": "101.00", "opening_date": "2026-10-01", "expected_version": 5})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["opening_balance"], "101.00")
        self.assertEqual([row["record_key"] for row in self.rows()], ["cash_position"])
        all_rows = self.client.get(self.base + "/records?include_deleted=true", headers=self.headers).json()
        self.assertTrue(next(row for row in all_rows if row["record_key"] == "cash_balance")["is_deleted"])
        stale = self.client.put(self.base + "/cash-position", headers=self.headers,
                                json={"opening_balance": "999.00", "expected_version": 5})
        self.assertEqual(stale.status_code, 409, stale.text)

    def seed_cash_aliases(self, *, same_time=False, tied_rank=False, canonical_live=False):
        with database.SessionLocal() as db:
            for key, version, sequence, amount, age in (
                ("cash_position", 7, 7, "70.00", 3),
                ("base_balance", 5, 8, "100.00", 2),
                ("cash_balance", 5 if tied_rank else 8, 8 if tied_rank else 9, "200.00", 1),
            ):
                payload = {"opening_balance": amount, "opening_date": "2026-10-01", "transactions": []}
                db.add(SyncRecord(
                    dataset_id=self.dataset, record_type="global", record_key=key,
                    payload=payload, checksum=payload_checksum(payload),
                    version=version, sequence=sequence,
                    is_deleted=(key == "cash_position" and not canonical_live),
                    created_at=NOW-timedelta(hours=4),
                    updated_at=NOW-timedelta(hours=1 if same_time else age),
                ))
            db.commit()

    def test_b04_three_aliases_get_then_save_and_stale_version(self):
        self.seed_cash_aliases()
        visible = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        self.assertEqual((visible["record"]["record_key"], visible["opening_balance"]), ("cash_balance", "200.00"))
        body = {"opening_balance": "201.00", "opening_date": "2026-10-01",
                "expected_version": visible["record"]["version"]}
        saved = self.client.put(self.base + "/cash-position", headers=self.headers, json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["opening_balance"], "201.00")
        self.assertEqual(saved.json()["record"]["record_key"], "cash_position")
        # The old alias's v8 must not become the restored canonical's v8.
        self.assertGreater(saved.json()["record"]["version"], body["expected_version"])
        self.assertEqual([row["record_key"] for row in self.rows()], ["cash_position"])
        all_rows = self.client.get(self.base + "/records?include_deleted=true", headers=self.headers).json()
        self.assertEqual({row["record_key"] for row in all_rows if row["is_deleted"]}, {"cash_balance", "base_balance"})
        stale = self.client.put(self.base + "/cash-position", headers=self.headers, json={**body, "opening_balance": "999.00"})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.client.get(self.base + "/cash-position", headers=self.headers).json()["opening_balance"], "201.00")

    def test_b04_alias_timestamp_tie_uses_sequence(self):
        self.seed_cash_aliases(same_time=True)
        visible = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        self.assertEqual(visible["record"]["record_key"], "cash_balance")
        saved = self.client.put(self.base + "/cash-position", headers=self.headers, json={
            "opening_balance": "201.00", "opening_date": "2026-10-01",
            "expected_version": visible["record"]["version"]})
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_b04_complete_alias_tie_uses_stable_identity(self):
        self.seed_cash_aliases(same_time=True, tied_rank=True)
        for _ in range(2):
            visible = self.client.get(self.base + "/cash-position", headers=self.headers).json()
            self.assertEqual((visible["record"]["record_key"], visible["opening_balance"]), ("base_balance", "100.00"))
        saved = self.client.put(self.base + "/cash-position", headers=self.headers, json={
            "opening_balance": "101.00", "opening_date": "2026-10-01",
            "expected_version": visible["record"]["version"]})
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_b04_live_canonical_wins_over_newer_alias(self):
        self.seed_cash_aliases(canonical_live=True)
        visible = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        self.assertEqual((visible["record"]["record_key"], visible["opening_balance"]), ("cash_position", "70.00"))
        saved = self.client.put(self.base + "/cash-position", headers=self.headers, json={
            "opening_balance": "71.00", "opening_date": "2026-10-01",
            "expected_version": visible["record"]["version"]})
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_b04_alias_changed_after_read_rejects_old_version(self):
        self.seed_cash_aliases()
        visible = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        current = visible["record"]
        updated = self.client.put(self.base + "/records/global/" + current["record_key"], headers=self.headers,
                                  json={"payload": {**current["payload"], "opening_balance": "300.00"},
                                        "expected_version": current["version"]})
        self.assertEqual(updated.status_code, 200, updated.text)
        stale = self.client.put(self.base + "/cash-position", headers=self.headers, json={
            "opening_balance": "999.00", "opening_date": "2026-10-01", "expected_version": current["version"]})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.client.get(self.base + "/cash-position", headers=self.headers).json()["opening_balance"], "300.00")

    def test_b05_duplicate_dates_follow_canonical_merging(self):
        self.put("2026-10-01", {"daily": [{"日期": "2026-10-01", "收益": "100.00", "其他": "10.00", "食材成本": "3.00"}]})
        self.put("2026-10-02", {"daily": [{"日期": "2026-10-01", "收益": "150.00", "其他": "20.00", "食材成本": ""}]})
        row = canonical_daily_rows(self.rows())["2026-10-01"]
        cash = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        self.assertEqual(cash["income"], row["收益"])
        self.assertEqual(cash["daily_expenses"], "23.00")
        self.assertEqual(cash["days"], 1)

    def test_b05_user_excel_duplicate_rows_count_once(self):
        payload = {"daily": [{"日期": "2026-10-01", "收益": "100.00", "其他": "10.00"},
                             {"日期": "2026-10-01", "收益": "150.00", "其他": "20.00"}]}
        book = build_user_workbook(dataset_id=self.dataset, schema_version=2, year=2026,
                                   records=[WorkbookRecord("day", "2026-10-01", payload, payload_checksum(payload))])
        result = self.client.post(self.base + "/workbooks/user?year=2026", headers=self.headers,
                                  files={"file": ("daily.xlsx", book)})
        self.assertEqual(result.status_code, 200, result.text)
        cash = self.client.get(self.base + "/cash-position", headers=self.headers).json()
        self.assertEqual((cash["income"], cash["daily_expenses"]), ("150.00", "20.00"))
        self.assertEqual(cash["days"], 1)

    def ranked_backup(self):
        for key, amount, quantity in (("2026-10-02", "50.00", 5), ("2026-10-01", "100.00", 10)):
            self.put(key, {"daily": [{"日期": "2026-10-02", "收益": amount, "食材明细": f"米 {quantity}斤 {amount}", "食材成本": amount}]})
        response = self.client.get(self.base + "/workbooks/internal", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.content

    def restore(self, content, base=None):
        response = self.client.post((base or self.base) + "/workbooks/internal", headers=self.headers,
                                    files={"file": ("backup.xlsx", content)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_ranked(self, base=None):
        rows = self.client.get((base or self.base) + "/records", headers=self.headers).json()
        self.assertEqual(canonical_daily_rows(rows)["2026-10-02"]["收益"], "100.00")
        events = ledger_events({}, rows, [])
        balance = replay_quantities(**{key: events[key] for key in ("receipts", "outbounds", "adjustments", "overrides")})["balances"]
        self.assertEqual(balance[("食材", "米", "斤")], 10)

    def test_b07_backup_new_ledger_and_full_restore_keep_business_order(self):
        content = self.ranked_backup()
        target = self.dataset + "-target"
        self.create_dataset(target, target)
        target_base = "/api/v1/datasets/" + target
        self.restore(content, target_base)
        self.assert_ranked(target_base)
        before = [(row["record_key"], row["sequence"], row["version"]) for row in self.rows()]
        counts = self.restore(content)
        self.assertEqual(counts["unchanged"], 2)
        self.assertEqual(before, [(row["record_key"], row["sequence"], row["version"]) for row in self.rows()])
        result = self.client.post(self.base + "/records/bulk-delete", headers=self.headers,
                                  json={"start_date": "2026-10-01", "end_date": "2026-10-02"})
        self.assertEqual(result.status_code, 200, result.text)
        self.restore(content)
        self.assert_ranked()

    def test_b07_partial_restore_keeps_unchanged_winner(self):
        content = self.ranked_backup()
        result = self.client.post(self.base + "/records/day/2026-10-02/delete", headers=self.headers, json={})
        self.assertEqual(result.status_code, 200, result.text)
        self.restore(content)
        self.assert_ranked()

    def test_b07_partial_restore_keeps_shared_dish_only_date(self):
        def payload(day, quantity):
            return {"daily": [{"日期": day, "收益": "100.00"}], "dishes": [
                {"日期": "2026-10-03", "菜品数据": json.dumps([
                    {"菜品名称": "米饭", "食材明细": f"米 {quantity}斤 1.00", "成本": "1.00"}], ensure_ascii=False)}]}
        self.put("2026-10-02", payload("2026-10-02", 5))
        self.put("2026-10-01", payload("2026-10-01", 10))
        content = self.client.get(self.base + "/workbooks/internal", headers=self.headers).content
        self.assertEqual(ledger_events({}, self.rows(), [])["outbounds"][0]["quantity"], 10)
        deleted = self.client.post(self.base + "/records/day/2026-10-02/delete", headers=self.headers, json={})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.restore(content)
        self.assertEqual(ledger_events({}, self.rows(), [])["outbounds"][0]["quantity"], 10)

    def test_b07_optional_order_validation_and_legacy_workbooks(self):
        content = self.ranked_backup()
        workbook = load_workbook(BytesIO(content))
        sheet = workbook["__day_records"]
        self.assertEqual(sheet.cell(1, 5).value, "source_order")
        sheet.cell(3, 5).value = sheet.cell(2, 5).value
        stream = BytesIO(); workbook.save(stream)
        with self.assertRaises(WorkbookFormatError):
            parse_internal_workbook(stream.getvalue())
        for name in ("__day_records", "__month_records", "__global_records"):
            workbook[name].delete_cols(5)
        stream = BytesIO(); workbook.save(stream)
        self.assertEqual(len(parse_internal_workbook(stream.getvalue()).records), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
