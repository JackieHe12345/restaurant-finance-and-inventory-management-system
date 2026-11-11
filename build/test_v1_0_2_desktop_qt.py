"""Nov 10 widget regressions using extracted production classes and isolated fixtures."""
import ast
import calendar
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate, QDateTime, QEvent, QTime, QTimer
from PySide6.QtGui import QColor, QFocusEvent, QFont, QHelpEvent

getcontext().prec = 256
SOURCE = Path(os.environ.get('DESKTOP_SOURCE', str(Path(__file__).resolve().parents[1] / 'desktop/restaurant_cost_manager.py')))
TREE = ast.parse(SOURCE.read_text())
SCOPE = dict(globals())
SCOPE.update(MONEY_CENT=Decimal('.01'), MAX_ABS_AMOUNT=Decimal('999999999999.99'),
             Figure=lambda: object(), FigureCanvas=lambda figure: QWidget(),
             _payload_and_hash=lambda payload: ('{}', 'isolated-fixture'),
             _inventory_operation_stamp=lambda rows: '2026-11-10T04:00:00Z')
FUNCTIONS = {'decimal_number', 'decimal_divide', 'money_amount', 'money_input', 'month_comparison_text',
             '_elapsed_reference', 'elapsed_month_days',
             'apply_py_charm_run_style', 'workbook_month_kpis', 'calc_dashboard_month_kpis'}
CLASSES = {'DashboardTab', 'ForecastInfoButton', 'ForecastSummaryPanel', 'CashPositionTab'}
NODES = [n for n in TREE.body if (isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS)
         or (isinstance(n, ast.ClassDef) and n.name in CLASSES)]
assert {n.name for n in NODES} == FUNCTIONS | CLASSES
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), SCOPE)
APP = QApplication.instance() or QApplication([])
REAL_CALC_KPIS = SCOPE['calc_dashboard_month_kpis']

class MonthlyWidgets(unittest.TestCase):
    def test_open_native_views_refresh_at_midnight_without_cloud_changes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        source_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
        method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == '_refresh_statistics_after_date_change')
        scope = dict(SCOPE)
        class Now(datetime):
            day = datetime(2026, 10, 31, 23, 59, 59)
            @classmethod
            def now(cls, tz=None): return cls.day
        scope['datetime'] = Now
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), scope)
        refresh = scope['_refresh_statistics_after_date_change']
        window = SimpleNamespace(_last_statistics_date=Now.now().date(), dashboard=SimpleNamespace(refresh_all=Mock()),
                                 more_stats=SimpleNamespace(refresh=Mock()), statusBar=lambda: SimpleNamespace(showMessage=Mock()))
        refresh(window)
        window.dashboard.refresh_all.assert_not_called()
        Now.day = datetime(2026, 11, 1, 0, 0, 1)
        with patch.object(QApplication, 'activeModalWidget', return_value=object()):
            refresh(window)
        window.dashboard.refresh_all.assert_not_called()
        refresh(window)
        window.dashboard.refresh_all.assert_called_once_with()
        window.more_stats.refresh.assert_called_once_with()
        self.assertEqual(window._last_statistics_date, datetime(2026, 11, 1).date())
        refresh(window)
        window.dashboard.refresh_all.assert_called_once_with()
        # A failed disk read is retried on the following timer tick instead of
        # marking the new date as already rendered.
        Now.day = datetime(2027, 1, 1)
        window.dashboard.refresh_all.side_effect = OSError('isolated fixture read error')
        refresh(window)
        self.assertEqual(window._last_statistics_date, datetime(2026, 11, 1).date())
        window.dashboard.refresh_all.side_effect = None
        refresh(window)
        self.assertEqual(window._last_statistics_date, datetime(2027, 1, 1).date())

    def test_clock_schedules_the_local_midnight_boundary(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        source_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
        method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == '_check_statistics_clock')
        clock = Mock()
        scope = dict(SCOPE, QDateTime=clock)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), scope)
        window = SimpleNamespace(_statistics_date_timer=Mock(), _refresh_statistics_after_date_change=Mock())
        for time, delay in ((QTime(23, 59, 59, 735), 265), (QTime(0, 0, 0), 5000)):
            clock.currentDateTime.return_value = QDateTime(QDate(2026, 10, 31), time)
            scope['_check_statistics_clock'](window)
            window._statistics_date_timer.start.assert_called_with(delay)
        self.assertEqual(window._refresh_statistics_after_date_change.call_count, 2)

    def test_headline_order_amount_margin_and_responsive_layout(self):
        cls = SCOPE['DashboardTab']
        with patch.object(cls, 'refresh_all', return_value=None):
            tab = cls()
        current = dict(avg_revenue=Decimal('200'), avg_gross=Decimal('100'), gross_margin=Decimal('50'), avg_net=Decimal('55.555555'), net_margin=Decimal('17.857142'), projected_net=Decimal('4400'), net=Decimal('500'), forecast_status='')
        previous = dict(avg_revenue=Decimal('100'), avg_gross=Decimal('50'), gross_margin=Decimal('50'), avg_net=Decimal('48.387097'), net_margin=Decimal('48.387097'), projected_net=Decimal('1500'), net=Decimal('1500'), forecast_status='该月已结束')
        self.addCleanup(lambda: SCOPE.update(calc_dashboard_month_kpis=REAL_CALC_KPIS))
        SCOPE['calc_dashboard_month_kpis'] = lambda *args: dict(current=current, previous=previous)
        tab._refresh_month_headlines(2026, 11, None, None)
        self.assertEqual(len({card.styleSheet() for card in tab.headline_cards}), 1)
        captions = [card.findChildren(QLabel)[0].text() for card in tab.headline_cards]
        self.assertEqual(captions, ['日均收入', '日均毛利润 (毛利率)', '预计月底盈亏\n(根据 本月预计成本 和 本月预计收入 计算)', '日均净利润 (净利率)', '净利润 (净利率)'])
        self.assertEqual(tab.headline_values['avg_gross'].text(), '100.00 元 (50.0%)')
        self.assertEqual(tab.headline_comparisons['avg_revenue'].text(), '比上个月多了 100.0%')
        self.assertEqual(tab.headline_comparisons['net'].text(), '比上个月少了 66.7%')
        self.assertEqual(tab.headline_values['avg_net'].text(), '55.56 元 (17.9%)')
        self.assertEqual(tab.headline_values['net'].text(), '500.00 元 (17.9%)')
        for width, columns in [(1450, 5), (1280, 5), (1000, 3), (550, 1)]:
            tab.resize(width, 900); tab.show()
            for _ in range(8): APP.processEvents()
            tab._reflow_dashboard_layout()
            for _ in range(8): APP.processEvents()
            for index in range(5):
                self.assertIs(tab.headline_layout.itemAtPosition(index // columns, index % columns).widget(), tab.headline_cards[index])
            self.assertEqual(tab.dashboard_scroll.horizontalScrollBar().maximum(), 0, width)
            for card in tab.headline_cards:
                labels = card.findChildren(QLabel)
                for label in labels:
                    self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), (width, label.text()))
                for index, label in enumerate(labels):
                    for other in labels[index + 1:]:
                        self.assertFalse(label.geometry().intersects(other.geometry()), (width, label.text(), other.text()))
        tab.close(); tab.deleteLater(); APP.processEvents()

    def test_closed_month_actual_net_matches_full_report_and_more_stats(self):
        import pandas as pd
        from types import SimpleNamespace
        cls = SCOPE['DashboardTab']
        with patch.object(cls, 'refresh_all', return_value=None):
            tab = cls()
        class Now(datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 11, 10, 12, tzinfo=tz)
        frame = pd.DataFrame([{'日期': '2026-10-02', '收益': '1000'}])
        day = dict(收益=Decimal('1000'), 毛利=Decimal('500'), 净利润=Decimal('480'),
                   固定分摊=Decimal('20'), 变动成本=Decimal('500'), 总成本=Decimal('520'))
        summary = {'本月收益': Decimal('1000'), '本月毛利': Decimal('500'), '本月净利': Decimal('-100'),
                   '本月总成本': Decimal('1100'), '本月固定成本': Decimal('600'), '本月变动成本': Decimal('500'),
                   '活跃天数': 1, '日均天数': 31}
        overrides = dict(pd=pd, datetime=Now, load_daily=lambda: frame.copy(),
                         load_monthly_fixed=lambda: pd.DataFrame(columns=['月份']),
                         safe_float=lambda value: Decimal(str(value)), day_has_meaningful_data=lambda row: True,
                         calc_day_metrics=lambda *args: day, calc_week_summary=lambda *args: None,
                         calc_year_summary=lambda *args: None, dish_total_cost_for_date=lambda *args: (0, False),
                         calc_dashboard_month_kpis=REAL_CALC_KPIS,
                         calc_month_summary=lambda y, m, *args, **kwargs: summary if m == 10 else None)
        tab.date_edit.blockSignals(True); tab.date_edit.setDate(QDate(2026, 10, 2)); tab.date_edit.blockSignals(False)
        tab.update_charts = lambda *args: None
        with patch.dict(SCOPE, overrides):
            tab.refresh_all()
            self.assertEqual(tab.month_forecast_panel.net_value.text(), '-100.00 元')
            self.assertIn('实际净利润', tab.month_forecast_panel.status_label.text())
            self.assertEqual(tab.headline_values['projected_net'].text(), '-100.00 元')
            self.assertEqual(tab.headline_values['avg_net'].text(), '-3.23 元 (-10.0%)')
            self.assertEqual(tab.lbl_month_avg_net.text(), '-3.23 元 (-10.0%)/天')
            source_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MoreStatsTab')
            method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == '_update_month_forecast')
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), SCOPE)
            stats = SimpleNamespace(_selected_months=lambda: [10], _current_year=lambda: 2026,
                                    month_forecast_panel=SCOPE['ForecastSummaryPanel']())
            SCOPE['_update_month_forecast'](stats)
            self.assertEqual(stats.month_forecast_panel.net_value.text(), '-100.00 元')
            self.assertIn('实际净利润', stats.month_forecast_panel.status_label.text())
            stats.month_forecast_panel.close(); stats.month_forecast_panel.deleteLater()
        tab.close(); tab.deleteLater(); APP.processEvents()

    def test_native_date_ticks_do_not_collide_at_small_and_large_widths(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        source_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MoreStatsTab')
        method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == '_fit_date_axis_labels')
        method.decorator_list = []
        scope = dict(SCOPE)
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), scope)
        fit = scope['_fit_date_axis_labels']
        figure = Figure(figsize=(8, 3), dpi=100)
        canvas = FigureCanvasAgg(figure); axis = figure.add_subplot(111)
        labels = [f'2026-10-{day:02d}' for day in range(1, 32)]
        axis.plot(range(31), range(31))
        axis.set_xticks(range(31)); axis.set_xticklabels(labels, rotation=45, ha='right')
        for width in (3.2, 8, 4, 10):
            figure.set_size_inches(width, 3); figure.tight_layout(); canvas.draw()
            fit(canvas, axis); canvas.draw()
            visible = axis.get_xticklabels()
            boxes = [label.get_window_extent(canvas.get_renderer()) for label in visible]
            self.assertEqual(visible[0].get_text(), labels[0])
            self.assertEqual(visible[-1].get_text(), labels[-1])
            for left, right in zip(boxes, boxes[1:]):
                self.assertLessEqual(left.x1 + 9, right.x0)
            self.assertEqual(len(axis.lines[0].get_xdata()), 31)
    def test_today_only_data_never_creates_a_zero_revenue_loss_forecast(self):
        import pandas as pd
        from types import SimpleNamespace
        cls = SCOPE['DashboardTab']
        with patch.object(cls, 'refresh_all', return_value=None):
            tab = cls()
        class Now(datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 11, 10, 12, tzinfo=tz)
        frame = pd.DataFrame([{'日期': '2026-11-10', '收益': '1000'}])
        day = dict(收益=Decimal('1000'), 毛利=Decimal('500'), 净利润=Decimal('450'),
                   固定分摊=Decimal('50'), 变动成本=Decimal('500'), 总成本=Decimal('550'))
        summary = {'本月收益': Decimal('1000'), '本月毛利': Decimal('500'), '本月净利': Decimal('450'),
                   '本月总成本': Decimal('550'), '本月固定成本': Decimal('50'), '本月变动成本': Decimal('500'),
                   '活跃天数': 1, '日均天数': 9}
        overrides = dict(pd=pd, datetime=Now, load_daily=lambda: frame.copy(),
                         load_monthly_fixed=lambda: pd.DataFrame(columns=['月份']),
                         safe_float=lambda value: Decimal(str(value)), day_has_meaningful_data=lambda row: True,
                         calc_day_metrics=lambda *args: day, calc_week_summary=lambda *args: None,
                         calc_year_summary=lambda *args: None, dish_total_cost_for_date=lambda *args: (0, False),
                         calc_dashboard_month_kpis=REAL_CALC_KPIS,
                         calc_month_summary=lambda y, m, *args, **kwargs: summary if m == 11 else {'本月总成本': Decimal('1600'), '本月收益': Decimal('0'), '本月净利': Decimal('-1600')})
        tab.date_edit.blockSignals(True); tab.date_edit.setDate(QDate(2026, 11, 10)); tab.date_edit.blockSignals(False)
        tab.update_charts = lambda *args: None
        with patch.dict(SCOPE, overrides):
            tab.refresh_all()
            self.assertEqual(tab.month_forecast_panel.revenue_value.text(), '—')
            self.assertEqual(tab.month_forecast_panel.net_value.text(), '—')
            self.assertEqual(tab.month_forecast_panel.break_even_value.text(), '—')
            self.assertIn('已完成日期', tab.month_forecast_panel.status_label.text())
            self.assertEqual(tab.lbl_month_avg_rev.text(), '—')
            self.assertIn('450.00', tab.lbl_month_net.text())
            # The other shared statistics view must have the same unavailable result.
            source_class = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MoreStatsTab')
            method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == '_update_month_forecast')
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), SCOPE)
            stats = SimpleNamespace(_selected_months=lambda: [11], _current_year=lambda: 2026,
                                    month_forecast_panel=SCOPE['ForecastSummaryPanel']())
            SCOPE['_update_month_forecast'](stats)
            self.assertEqual(stats.month_forecast_panel.revenue_value.text(), '—')
            self.assertEqual(stats.month_forecast_panel.net_value.text(), '—')
            stats.month_forecast_panel.close(); stats.month_forecast_panel.deleteLater()
        tab.close(); tab.deleteLater(); APP.processEvents()

    def test_forecast_formula_keeps_wrapped_height_and_scroll_reachability(self):
        SCOPE['apply_py_charm_run_style'](APP)
        cls = SCOPE['DashboardTab']
        with patch.object(cls, 'refresh_all', return_value=None):
            tab = cls()
        for label in (tab.lbl_day_revenue, tab.lbl_day_a_revenue, tab.lbl_day_b_revenue):
            label.setText('0.00 元 (SD: 0.00 元)')
        tab.lbl_year_revenue.setText('1,000.00 元')
        tab.lbl_year_gross.setText('820.00 元 (82.0%)')
        tab.month_forecast_panel.set_values(status='2026年11月暂无经营数据')
        window = QMainWindow()
        shell = QWidget(); shell_layout = QHBoxLayout(shell)
        navigation = QWidget(); navigation.setFixedWidth(190)
        shell_layout.addWidget(navigation); shell_layout.addWidget(tab)
        window.setCentralWidget(shell); window.resize(1440, 960); window.show()
        for _ in range(8): APP.processEvents()
        panel = tab.month_forecast_panel
        # Exercise exactly the narrow forecast column that was clipped in the
        # full 1440 x 960 packaged screenshot, then allow its layout to settle.
        panel.setMaximumWidth(235)
        for _ in range(8): APP.processEvents()
        labels = [label for label in panel.findChildren(QLabel) if not label.isHidden()]
        for label in labels:
            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), label.text())
        rects = [(label, label.geometry().translated(label.parentWidget().mapTo(panel, label.geometry().topLeft()) - label.geometry().topLeft()))
                 for label in labels]
        for index, (label, rect) in enumerate(rects):
            for other, other_rect in rects[index + 1:]:
                self.assertFalse(rect.intersects(other_rect), (label.text(), other.text()))
        self.assertGreater(tab.dashboard_scroll.verticalScrollBar().maximum(), 0)
        tab.dashboard_scroll.ensureWidgetVisible(panel.status_label, 0, 0)
        for _ in range(4): APP.processEvents()
        position = panel.status_label.mapTo(tab.dashboard_scroll.viewport(), panel.status_label.rect().bottomLeft())
        self.assertGreaterEqual(position.y(), 0)
        self.assertLess(position.y(), tab.dashboard_scroll.viewport().height())
        window.close(); window.deleteLater(); APP.processEvents()

    def test_report_note_spaces_and_break_even_label(self):
        panel = SCOPE['ForecastSummaryPanel']()
        self.assertEqual(panel.net_note_label.text(), '(根据 本月预计成本 和 本月预计收入 计算)')
        self.assertEqual(panel.break_even_title_label.text().splitlines()[0], '平本 需要 日均收入 增加')
        panel.set_values(6000, -1000, 50)
        self.assertEqual(panel.net_value.text(), '-1,000.00 元')
        panel.close(); panel.deleteLater()

    def test_forecast_explanation_on_hover_focus_and_click(self):
        cls = SCOPE['DashboardTab']
        with patch.object(cls, 'refresh_all', return_value=None):
            tab = cls()
        tab.show()
        APP.processEvents()
        for button in (tab.headline_cards[2].findChild(QToolButton), tab.month_forecast_panel.net_info_button):
            self.assertEqual(button.accessibleName(), '预计月底盈亏计算说明')
            self.assertEqual(button.focusPolicy(), Qt.StrongFocus)
            for wording in ('截至昨日', '固定支出', '含佐料', '其他成本', '较高', '次月 1 日'):
                self.assertIn(wording, button.toolTip())
            point = button.rect().center()
            QApplication.sendEvent(button, QHelpEvent(QEvent.ToolTip, point, button.mapToGlobal(point)))
            self.assertEqual(QToolTip.text(), button.toolTip())
            with patch.object(QToolTip, 'showText') as popup:
                QApplication.sendEvent(button, QFocusEvent(QEvent.FocusIn, Qt.TabFocusReason))
                button.click()
                self.assertEqual(popup.call_count, 2)
        tab.close(); tab.deleteLater()

    def test_forecast_panel_displays_shared_break_even_result(self):
        panel = SCOPE['ForecastSummaryPanel']()
        for increase, displayed in ((Decimal('20'), '20.00 元'), (None, '—'), (0, '0.00 元')):
            values = dict(projected_revenue=6000, projected_net=-300, forecast_status='', break_even_increase=increase)
            panel.set_month_forecast(values)
            self.assertEqual(panel.break_even_value.text(), displayed)
        panel.close(); panel.deleteLater()

    def test_cash_correction_removed_manual_force_kept_unlocked(self):
        tab = SCOPE['CashPositionTab']()
        self.assertFalse(hasattr(tab, 'correction_toggle'))
        self.assertFalse(hasattr(tab, 'correction_form'))
        self.assertFalse(hasattr(tab, 'save'))
        self.assertNotIn('余额校正', [label.text() for label in tab.findChildren(QLabel)])
        tab.set_role('entry'); self.assertFalse(tab.add_item_button.isEnabled())
        tab.set_role('admin'); self.assertTrue(tab.add_item_button.isEnabled())
        historic = dict(id='historic', date='2026-11-01', type='余额强制修改', amount=Decimal('100'), mode='force', system_locked=True)
        tab._payload = dict(base_balance=Decimal('10'), as_of_date='2026-10-01', transactions=[historic])
        tab._payload_hash = 'expected'
        tab.refresh = lambda: None
        saved = []
        SCOPE['save_cash_position_record'] = lambda payload, **kwargs: saved.append((payload, kwargs))
        def accept_force(dialog):
            combo = dialog.findChild(QComboBox)
            self.assertIn('余额强制修改', [combo.itemText(i) for i in range(combo.count())])
            combo.setCurrentText('余额强制修改')
            inputs = dialog.findChildren(QLineEdit)
            amount = next(widget for widget in inputs if widget.placeholderText() == '修正后的余额')
            amount.setText('5000.00')
            return QDialog.Accepted
        with patch.object(QDialog, 'exec', accept_force):
            tab.add_item()
        self.assertEqual(len(saved), 1)
        payload, args = saved[0]
        self.assertEqual(payload['transactions'][0], historic)
        self.assertEqual(args['expected_hash'], 'expected')
        entry = payload['transactions'][1]
        self.assertEqual(entry['amount'], Decimal('5000.00'))
        self.assertEqual(entry['mode'], 'force')
        self.assertFalse(entry['system_locked'])
        self.assertEqual(entry['type'], '余额强制修改')
        tab.close(); tab.deleteLater()

    def test_historical_lock_remains_while_new_force_can_be_deleted(self):
        tab = SCOPE['CashPositionTab']()
        historic = dict(id='historic', date='2026-11-01', type='余额强制修改', amount='100', mode='force', system_locked=True)
        manual = dict(id='manual', date='2026-11-02', type='余额强制修改', amount='200', mode='force', system_locked=False)
        tab._payload = dict(transactions=[historic, manual]); tab.refresh = lambda: None
        saved = []
        SCOPE['save_cash_position_record'] = lambda payload, **kwargs: saved.append(payload)
        tab.table.setRowCount(2)
        for row, entry in enumerate((historic, manual)):
            item = QTableWidgetItem(entry['date']); item.setData(Qt.UserRole, entry['id']); tab.table.setItem(row, 0, item)
        tab.table.selectRow(0)
        with patch.object(QMessageBox, 'information', return_value=QMessageBox.Ok) as notice:
            tab.delete_item()
        self.assertEqual(saved, [])
        self.assertIn('锁定', notice.call_args.args[-1])
        tab.table.selectRow(1)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            tab.delete_item()
        self.assertEqual(saved[-1]['transactions'], [historic])
        tab.close(); tab.deleteLater()

if __name__ == '__main__': unittest.main(verbosity=2)
