"""Nov 10 monthly headline regression tests; no app, network, or user data."""
import ast
import calendar
import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
import unittest

getcontext().prec = 256
SOURCE = Path(os.environ.get('DESKTOP_SOURCE', str(Path(__file__).resolve().parents[1] / 'desktop/restaurant_cost_manager.py')))
TREE = ast.parse(SOURCE.read_text())
NAMES = {'decimal_number', 'decimal_divide', '_elapsed_reference', 'elapsed_month_days',
         'month_comparison_text', 'calc_dashboard_month_kpis'}
SCOPE = dict(Decimal=Decimal, InvalidOperation=InvalidOperation, datetime=datetime,
             timedelta=timedelta, calendar=calendar)
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
assert {n.name for n in NODES} == NAMES
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), SCOPE)

class Rows:
    def __init__(self, rows): self.rows = rows
    def iterrows(self): return iter(enumerate(self.rows))

class MonthlyHeadlines(unittest.TestCase):
    def setUp(self):
        self.summaries = {
            (2026, 9): {'本月收益': Decimal('1100'), '本月净利': Decimal('100'), '本月总成本': Decimal('1000')},
            (2026, 10): {'本月收益': Decimal('3100'), '本月净利': Decimal('1500'), '本月总成本': Decimal('1600')},
            (2026, 11): {'本月收益': Decimal('2800'), '本月净利': Decimal('500'), '本月总成本': Decimal('2300')},
        }
        self.rows = [
            {'日期': '2026-10-02', '收益': '3100', '毛利': '1550'},
            {'日期': '2026-11-01', '收益': '900', '毛利': '450'},
            {'日期': '2026-11-09', '收益': '900', '毛利': '450'},
            {'日期': '2026-11-10', '收益': '1000', '毛利': '500'},
            {'日期': '2026-11-20', '收益': '90000', '毛利': '45000'},
        ]
        SCOPE['calc_month_summary'] = lambda y, m, daily, fixed: self.summaries.get((y, m))
        SCOPE['day_has_meaningful_data'] = lambda row: bool(row.get('收益') or row.get('毛利'))
        SCOPE['calc_day_metrics'] = lambda day, daily, fixed: next(row for _, row in daily.iterrows() if row['日期'] == day)

    def calculate(self):
        return SCOPE['calc_dashboard_month_kpis'](2026, 11, Rows(self.rows), None, as_of='2026-11-10')

    def test_completed_calendar_days_and_real_prior_cost(self):
        result = self.calculate()
        self.assertEqual(result['current']['avg_revenue'], Decimal('200'))
        self.assertEqual(result['current']['avg_gross'], Decimal('100'))
        self.assertEqual(result['current']['gross_margin'], Decimal('50'))
        self.assertEqual(result['current']['projected_net'], Decimal('4400'))
        self.assertEqual(result['current']['net'], Decimal('500'))
        self.assertEqual(result['previous']['avg_revenue'], Decimal('100'))
        self.assertEqual(result['previous']['projected_net'], Decimal('1500'))
        self.assertEqual(result['current']['avg_net'], Decimal('500') / 9)
        self.assertEqual(result['current']['net_margin'], Decimal('500') / 2800 * 100)
        self.assertEqual(result['previous']['avg_net'], Decimal('1500') / 31)
        self.assertTrue(result['previous']['is_closed'])
        self.assertEqual(SCOPE['month_comparison_text'](result['current']['avg_revenue'], result['previous']['avg_revenue']), '比上个月多了 100.0%')

    def test_missing_prior_month_never_uses_current_cost(self):
        del self.summaries[(2026, 10)]
        result = self.calculate()
        self.assertIsNone(result['current']['projected_net'])
        self.assertEqual(result['current']['avg_revenue'], Decimal('200'))
        self.assertEqual(SCOPE['month_comparison_text'](result['current']['net'], result['previous']['net']), '暂无上月可比数据')

    def test_closed_month_does_not_need_older_forecast_baseline(self):
        del self.summaries[(2026, 9)]
        result = self.calculate()
        self.assertEqual(result['current']['projected_net'], Decimal('4400'))
        self.assertEqual(result['previous']['projected_net'], Decimal('1500'))
        self.assertEqual(result['previous']['avg_revenue'], Decimal('100'))

    def test_month_boundary_and_leap_month_days(self):
        self.summaries = {
            (2023, 12): {'本月收益': Decimal('10'), '本月净利': Decimal('0'), '本月总成本': Decimal('10')},
            (2024, 1): {'本月收益': Decimal('310'), '本月净利': Decimal('290'), '本月总成本': Decimal('20')},
            (2024, 2): {'本月收益': Decimal('280'), '本月净利': Decimal('250'), '本月总成本': Decimal('30')},
        }
        self.rows = [{'日期': '2024-01-05', '收益': '310', '毛利': '155'},
                     {'日期': '2024-02-01', '收益': '280', '毛利': '140'}]
        result = SCOPE['calc_dashboard_month_kpis'](2024, 2, Rows(self.rows), None, as_of='2024-02-29')
        self.assertEqual(result['current']['avg_revenue'], Decimal('10'))
        self.assertEqual(result['current']['projected_net'], Decimal('270'))
        self.assertEqual(result['previous']['projected_net'], Decimal('290'))
        january = SCOPE['calc_dashboard_month_kpis'](2024, 1, Rows(self.rows), None, as_of='2024-02-29')
        self.assertEqual(january['current']['projected_net'], Decimal('290'))

    def test_first_of_next_month_switches_to_actual_including_year_boundary(self):
        october = SCOPE['calc_dashboard_month_kpis'](2026, 10, Rows(self.rows), None, as_of='2026-10-31')['current']
        self.assertFalse(october['is_closed'])
        self.assertNotEqual(october['projected_net'], october['net'])
        closed = SCOPE['calc_dashboard_month_kpis'](2026, 10, Rows(self.rows), None, as_of='2026-11-01')['current']
        self.assertTrue(closed['is_closed'])
        self.assertEqual(closed['projected_net'], Decimal('1500'))
        self.assertEqual(closed['projected_revenue'], Decimal('3100'))
        self.assertIn('实际净利润', closed['forecast_status'])
        self.summaries[(2026, 12)] = {'本月收益': Decimal('100'), '本月净利': Decimal('-23'), '本月总成本': Decimal('123')}
        december = SCOPE['calc_dashboard_month_kpis'](2026, 12, Rows(self.rows), None, as_of='2027-01-01')['current']
        self.assertTrue(december['is_closed'])
        self.assertEqual(december['projected_net'], Decimal('-23'))

    def test_day_one_zero_revenue_and_future_remain_unavailable(self):
        first = SCOPE['calc_dashboard_month_kpis'](2026, 11, Rows(self.rows), None, as_of='2026-11-01')['current']
        self.assertIsNone(first['avg_net'])
        self.assertIsNone(first['projected_net'])
        self.assertEqual(first['net'], Decimal('500'))
        self.summaries[(2026, 11)]['本月收益'] = Decimal(0)
        self.assertIsNone(self.calculate()['current']['net_margin'])
        future = SCOPE['calc_dashboard_month_kpis'](2026, 11, Rows(self.rows), None, as_of='2026-10-31')['current']
        self.assertIsNone(future['net'])
        self.assertIsNone(future['avg_net'])
        self.assertIsNone(future['projected_net'])

    def test_no_finished_day_is_unavailable(self):
        self.rows = [row for row in self.rows if not row['日期'].startswith('2026-11-0')]
        result = self.calculate()
        self.assertIsNone(result['current']['avg_revenue'])
        self.assertIsNone(result['current']['avg_gross'])
        self.assertIsNone(result['current']['projected_net'])
        self.assertEqual(result['current']['net'], Decimal('500'))

    def test_recorded_zero_cost_is_known_but_absent_month_is_missing(self):
        import pandas as pd
        scope = dict(SCOPE)
        class Now(datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 11, 10, 12, tzinfo=tz)
        empty_fixed = {
            '固定支出合计': Decimal(0), '人工': Decimal(0), '房租及物业': Decimal(0),
            '实际使用水费': None, '实际使用电费': None, '计入成本水费': Decimal(0),
            '计入成本电费': Decimal(0), '计入成本煤气费': Decimal(0), '其它固定成本': Decimal(0),
        }
        scope.update(pd=pd, datetime=Now, get_monthly_fixed_breakdown=lambda *args: empty_fixed)
        exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), scope)
        node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'calc_month_summary')
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), scope)
        daily = pd.DataFrame(columns=['日期'])
        fixed = pd.DataFrame([{'月份': '2026-10', '人工总额': '0.00'}])
        result = scope['calc_month_summary'](2026, 10, daily, fixed)
        self.assertIsNotNone(result)
        self.assertEqual(result['本月总成本'], 0)
        self.assertEqual(result['本月净利'], 0)
        self.assertIsNone(scope['calc_month_summary'](2026, 9, daily, fixed))
        future_fixed = pd.DataFrame([{'月份': '2026-12', '人工总额': '0.00'}])
        self.assertIsNone(scope['calc_month_summary'](2026, 12, daily, future_fixed))
        scope['calc_day_metrics'] = lambda day, daily, fixed: dict(收益=Decimal('900'), 毛利=Decimal('450'), 变动成本=Decimal('450'))
        scope['day_has_meaningful_data'] = lambda row: True
        scope['money_amount'] = lambda value=0: Decimal(str(value))
        current_daily = pd.DataFrame([{'日期': '2026-11-09', '收益': '900'}])
        result = scope['calc_dashboard_month_kpis'](2026, 11, current_daily, fixed, as_of='2026-11-10')
        self.assertEqual(result['current']['projected_net'], Decimal('3000'))
        self.assertEqual(result['previous']['net'], 0)

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
