"""Monthly forecast and headline regressions using isolated, in-memory ledger data."""
import ast
import calendar
import os
import json
import re
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
import unittest

import pandas as pd

getcontext().prec = 256
getcontext().rounding = ROUND_HALF_UP
SOURCE = Path(os.environ.get('DESKTOP_SOURCE', str(Path(__file__).resolve().parents[1] / 'desktop/restaurant_cost_manager.py')))
TREE = ast.parse(SOURCE.read_text())
NAMES = {'decimal_number', 'decimal_divide', '_elapsed_reference', 'elapsed_month_days',
         'month_comparison_text', 'calc_dashboard_month_kpis', 'calc_month_summary', 'calc_day_metrics',
         'day_has_meaningful_data', 'safe_float', 'get_monthly_fixed_breakdown',
         'money_amount', 'money_value_was_entered', 'workbook_month_kpis', '_inventory_day_sheet', '_internal_payload_for_identity',
         'reported_day_revenue', 'recalculate_revenue_fields'}
SCOPE = dict(Decimal=Decimal, InvalidOperation=InvalidOperation, ROUND_HALF_UP=ROUND_HALF_UP,
             MONEY_CENT=Decimal('.01'), datetime=datetime, timedelta=timedelta, calendar=calendar, pd=pd)
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
assert {n.name for n in NODES} == NAMES
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), SCOPE)


class MonthlyHeadlines(unittest.TestCase):
    def setUp(self):
        self.daily = [
            {'日期': '2026-10-02', '收益': '3100', '食材成本': '279', '佐料成本': '62',
             '水电': '62', '其他': '31', '手续费': '31'},
            {'日期': '2026-11-01', '收益': '900', '食材成本': '90', '佐料成本': '45', '水电': '9'},
            {'日期': '2026-11-09', '收益': '900'},
            {'日期': '2026-11-10', '收益': '1000', '食材成本': '2000', '佐料成本': '1000',
             '其他': '1000', '手续费': '200'},
            {'日期': '2026-11-20', '收益': '90000', '食材成本': '90000'},
        ]
        self.fixed = [{'月份': '2026-10', '人工总额': '900', '水费支出': '30.03', '预计水费': '1000'},
                      {'月份': '2026-11', '人工总额': '900'}]

    def calculate(self, year=2026, month=11, as_of='2026-11-10'):
        daily = pd.DataFrame(self.daily).fillna('') if self.daily else pd.DataFrame(columns=['日期'])
        fixed = pd.DataFrame(self.fixed).fillna('') if self.fixed else pd.DataFrame(columns=['月份'])
        return SCOPE['calc_dashboard_month_kpis'](year, month, daily, fixed, as_of=as_of)

    def test_prior_fixed_current_ingredients_prior_other(self):
        result = self.calculate()
        current, previous = result['current'], result['previous']
        self.assertEqual(current['avg_revenue'], Decimal('200'))
        self.assertEqual(current['avg_gross'], Decimal('1665') / 9)
        self.assertEqual(current['gross_margin'], Decimal('92.5'))
        self.assertEqual(current['projected_revenue'], Decimal('6000'))
        # max(930.03, 900) + max(341/31, 135/9)*30 + max(124/31, 9/9)*30.
        self.assertEqual(current['projected_net'], Decimal('4499.97'))
        self.assertEqual(current['net'], Decimal('-2444'))
        self.assertEqual(current['avg_net'], Decimal('-2444') / 9)
        self.assertEqual(current['net_margin'], Decimal('-2444') / 2800 * 100)
        self.assertEqual(previous['avg_revenue'], Decimal('100'))
        self.assertEqual(previous['projected_net'], Decimal('1704.97'))
        self.assertEqual(previous['avg_net'], Decimal('1704.97') / 31)
        self.assertTrue(previous['is_closed'])
        self.assertEqual(SCOPE['month_comparison_text'](current['avg_revenue'], previous['avg_revenue']), '比上个月多了 100.0%')

    def test_current_fixed_prior_ingredients_current_other(self):
        self.fixed[1]['人工总额'] = '1200.55'
        self.daily[0]['食材成本'] = '589'  # with seasonings: 651/31 = 21 per day
        self.daily[1].update(水电='18', 其他='63', 手续费='9')  # 90/9 = 10 per day
        self.assertEqual(self.calculate()['current']['projected_net'], Decimal('6000') - Decimal('1200.55') - 21*30 - 10*30)

    def test_no_intermediate_rounding_and_missing_current_fixed(self):
        self.fixed = [{'月份': '2026-10', '人工总额': '99.99'}]
        self.daily = [{'日期': '2026-10-20', '食材成本': '2.99', '佐料成本': '0.01'},
                      {'日期': '2026-11-06', '收益': '100.01', '其他': '1.01'}]
        current = self.calculate(as_of='2026-11-08')['current']
        self.assertEqual(current['projected_revenue'], Decimal('100.01')*30/7)
        self.assertEqual(current['projected_net'].quantize(Decimal('.01')),
                         (Decimal('100.01')*30/7 - Decimal('99.99') - Decimal('3')*30/31 - Decimal('1.01')*30/7).quantize(Decimal('.01')))

    def test_exact_half_cents_survive_repeating_daily_rates(self):
        self.fixed = [{'月份': '2026-10', '人工总额': '0'}]
        for revenue, expected in (('.02', '-0.075'), ('.16', '0.075')):
            self.daily = [{'日期': '2026-11-20', '收益': revenue, '食材成本': '.01', '其他': '.08'}]
            projected = self.calculate(as_of='2026-11-29')['current']['projected_net']
            self.assertEqual(projected, Decimal(expected))
            self.assertEqual(f'{projected:.2f}', '-0.08' if expected[0] == '-' else '0.08')

    def test_break_even_uses_unrounded_completed_revenue_and_gross(self):
        self.fixed = [{'月份': '2026-10', '房租总额': '10.00'}]
        self.daily = [{'日期': '2026-11-02', '收益': '.02', '食材成本': '.01', '其他': '.08'},
                      {'日期': '2026-11-29', '收益': '10000.00'}]
        result = self.calculate(as_of='2026-11-29')['current']
        self.assertEqual(result['projected_net'], Decimal('-10.075'))
        self.assertEqual(result['break_even_increase'], Decimal('10.075') * 2 / 30)
        self.daily[0]['食材成本'] = '.02'
        self.assertIsNone(self.calculate(as_of='2026-11-29')['current']['break_even_increase'])
        self.daily[0]['收益'] = '-10'
        self.assertIsNone(self.calculate(as_of='2026-11-29')['current']['break_even_increase'])
        self.daily[0]['收益'] = '100'
        self.assertEqual(self.calculate(as_of='2026-11-29')['current']['break_even_increase'], 0)
        self.fixed[0]['房租总额'] = '0'
        self.daily[0].update(收益='.14', 食材成本='.13', 其他='.16')
        increase = self.calculate(as_of='2026-11-29')['current']['break_even_increase']
        self.assertEqual(increase, Decimal('.075'))
        self.assertEqual(f'{increase:.2f}', '0.08')

    def test_channel_and_legacy_income_survive_monthly_calculation(self):
        self.fixed = [{'月份': '2026-10', '人工总额': '0'}]
        for fields, expected in [({'A店微信自动': '20', 'A店微信增加': '3'}, 23),
                                 ({'总金额': '98', 'A店现金': '10'}, 10),
                                 ({'A店微信增加': '100', 'A店微信覆盖': '0', '收益': '100'}, 0),
                                 ({'收益': '0', '收入': '4'}, 4),
                                 ({'总收入': '9'}, 9), ({'B店收入': '12'}, 12),
                                 ({'收益': '0', '总金额': '8'}, 8), ({'总现金': '2', '总线上': '3'}, 5)]:
            with self.subTest(fields=fields):
                self.daily = [{'日期': '2026-11-01', **fields}]
                current = self.calculate(as_of='2026-11-02')['current']
                self.assertEqual(current['projected_net'], Decimal(expected * 30))
                self.assertEqual(current['net'], Decimal(expected))

    def test_saved_zero_and_missing_history(self):
        self.daily = [{'日期': '2026-11-09', '收益': '900', '佐料成本': '90'}]
        self.fixed = []
        current = self.calculate()['current']
        self.assertEqual(current['projected_revenue'], Decimal('3000'))
        self.assertIsNone(current['projected_net'])
        self.assertIn('缺少上月', current['forecast_status'])
        self.fixed = [{'月份': '2026-10', '人工总额': '0.00'}]
        result = self.calculate()
        self.assertEqual(result['current']['projected_net'], Decimal('2700'))
        self.assertEqual(result['previous']['net'], Decimal(0))
        self.fixed = []
        self.daily.append({'日期': '2026-10-01', '收益': '30'})
        self.assertEqual(self.calculate()['current']['projected_net'], Decimal('2700'))

    def test_closed_month_does_not_need_older_forecast_baseline(self):
        result = self.calculate(2026, 10, '2026-11-01')
        self.assertIsNone(result['previous']['net'])
        self.assertTrue(result['current']['is_closed'])
        self.assertEqual(result['current']['projected_net'], Decimal('1704.97'))
        self.assertEqual(result['current']['projected_revenue'], Decimal('3100'))
        self.assertIn('实际净利润', result['current']['forecast_status'])

    def test_leap_month_calendar_days_and_year_rollover(self):
        self.fixed = [{'月份': '2023-12', '人工总额': '100'}, {'月份': '2024-01', '人工总额': '20'}]
        self.daily = [{'日期': '2024-01-02', '收益': '310', '食材成本': '31'},
                      {'日期': '2024-02-01', '收益': '280', '手续费': '56'}]
        january = self.calculate(2024, 1, '2024-01-31')
        self.assertFalse(january['current']['is_closed'])
        self.assertIsNotNone(january['current']['projected_net'])
        self.assertEqual(january['previous']['projected_net'], -100)
        result = self.calculate(2024, 2, '2024-02-29')
        self.assertEqual(result['current']['avg_revenue'], Decimal('10'))
        self.assertEqual(result['current']['projected_net'], Decimal('290') - 20 - 29 - 2*29)
        self.assertEqual(result['previous']['projected_net'], Decimal('259'))
        february = self.calculate(2024, 2, '2024-03-01')['current']
        self.assertTrue(february['is_closed'])
        self.assertEqual(february['projected_net'], 224)
        december = self.calculate(2023, 12, '2024-01-01')['current']
        self.assertTrue(december['is_closed'])
        self.assertEqual(december['projected_net'], -100)

    def test_january_annual_mirror_reads_same_dataset_december_without_switching_workbook(self):
        class Now(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2027, 1, 8)
        internal = {
            '__day_records': pd.DataFrame([
                {'dataset_id': 'book', '日期': '2026-11-30', 'source_order': 1,
                 'payload_json': '{"daily":[{"日期":"2026-12-01","食材成本":"310"},{"日期":"2026-12-02","食材成本":"420"}]}'},
                {'dataset_id': 'book', '日期': '2026-12-02', 'source_order': 3,
                 'payload_json': '{"daily":[{"食材成本":"620"}]}'},
                {'dataset_id': 'unrelated', '日期': '2026-12-02', 'source_order': 4,
                 'payload_json': '{"daily":[{"食材成本":"31000.00"}]}'},
            ]),
            '__month_records': pd.DataFrame([
                {'dataset_id': 'book', '月份': '2026-12', 'payload_json': '{"monthly_fixed":[{"人工总额":"100.00"},{"人工总额":"0.00"}]}'},
                {'dataset_id': 'unrelated', '月份': '2026-12', 'payload_json': '{"monthly_fixed":[{"人工总额":"9000.00"}]}'},
            ]),
        }
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'internal.xlsx'
            path.touch()
            scope = dict(SCOPE, datetime=Now, os=os, re=re, INTERNAL_FILE_PATH=str(path), ACTIVE_DATASET_ID='book',
                         _inventory_read_frames=lambda path: internal, _decode_internal_payload=lambda raw, context: json.loads(raw))
            exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), scope)
            daily = pd.DataFrame([{'日期': '2027-01-05', '收益': '700'}])
            fixed = pd.DataFrame(columns=['月份'])
            result = scope['workbook_month_kpis'](2027, 1, daily, fixed)
            self.assertEqual(result['current']['projected_net'], Decimal('2170'))
            self.assertEqual(result['previous']['net'], Decimal('-930'))
            self.assertEqual(daily['日期'].tolist(), ['2027-01-05'])
            self.assertTrue(fixed.empty)

    def test_day_one_today_only_and_future(self):
        first = self.calculate(as_of='2026-11-01')['current']
        self.assertIsNone(first['avg_net'])
        self.assertIsNone(first['projected_net'])
        self.assertEqual(first['net'], -144)
        self.daily = [row for row in self.daily if row['日期'] >= '2026-11-10']
        today_only = self.calculate()['current']
        self.assertIsNone(today_only['avg_revenue'])
        self.assertIsNone(today_only['avg_gross'])
        self.assertIsNone(today_only['projected_net'])
        future = self.calculate(as_of='2026-10-31')['current']
        self.assertIsNone(future['net'])
        self.assertIsNone(future['avg_net'])
        self.assertIsNone(future['projected_net'])

    def test_known_zero_revenue_and_zero_margin(self):
        self.daily = [{'日期': '2026-11-05', '其他': '18'}]
        current = self.calculate()['current']
        self.assertEqual(current['projected_revenue'], Decimal(0))
        self.assertEqual(current['projected_net'], Decimal('-990.03'))
        self.assertIsNone(current['net_margin'])
        self.assertEqual(current['gross_margin'], 0)

    def test_negative_profit_zero_and_missing_comparisons(self):
        compare = SCOPE['month_comparison_text']
        self.assertEqual(compare(-50, -100), '比上个月多了 50.0%')
        self.assertEqual(compare(-150, -100), '比上个月少了 50.0%')
        self.assertEqual(compare(50, -100), '比上个月多了 150.0%')
        self.assertEqual(compare(-50, 100), '比上个月少了 150.0%')
        self.assertEqual(compare(0, 0), '与上个月持平 0.0%')
        self.assertEqual(compare(1, 0), '上个月为 0，无法计算百分比')
        self.assertEqual(compare(1, None), '暂无上月可比数据')
        self.assertEqual(compare(None, 1), '暂无可比数据')

if __name__ == '__main__': unittest.main(verbosity=2)
