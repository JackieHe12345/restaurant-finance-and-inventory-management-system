"""Offline native Analytics presentation regressions; no real workbooks or network."""
import ast
import os
from pathlib import Path
from decimal import Decimal
import calendar
import re
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pandas as pd
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate, QEvent, QTimer, QSize, QRect
from PySide6.QtGui import QColor
import matplotlib
matplotlib.rcParams['font.family'] = ['PingFang SC', 'Arial Unicode MS', 'DejaVu Sans']
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import FuncFormatter

SOURCE = Path(os.environ.get('DESKTOP_SOURCE', str(Path(__file__).resolve().parents[1]/'desktop/restaurant_cost_manager.py')))
TREE = ast.parse(SOURCE.read_text())
NAMES = {'AnalyticsFlowLayout', 'MoreStatsTab', 'ForecastInfoButton', 'ForecastSummaryPanel', 'WheelPassThroughTableWidget'}
SCOPE = dict(globals(), decimal_number=lambda value: Decimal(str(value)))
NODES = [node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name in NAMES]
assert {node.name for node in NODES} == NAMES
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), 'exec'), SCOPE)
APP = QApplication.instance() or QApplication([])

class AnalyticsWidgets(unittest.TestCase):
    def build(self):
        cls = SCOPE['MoreStatsTab']
        with patch.object(cls, 'refresh', return_value=None):
            tab = cls()
        self.addCleanup(lambda: (tab.close(), tab.deleteLater(), APP.processEvents()))
        return tab

    def process(self):
        for _ in range(8):
            APP.processEvents()

    def test_filters_wrap_and_charts_reflow_without_changing_selections(self):
        tab = self.build()
        expected_months = tab._selected_months()
        expected_metrics = tab._selected_metrics()
        for width, columns in ((1440, 2), (640, 1), (960, 1), (1280, 2), (720, 1)):
            tab.resize(width, 900); tab.show(); self.process()
            tab._reflow_statistics_layout(); self.process()
            self.assertEqual(tab._analytics_columns, columns, width)
            self.assertEqual(tab.stats_scroll.horizontalScrollBar().maximum(), 0, width)
            self.assertEqual(tab._selected_months(), expected_months)
            self.assertEqual(tab._selected_metrics(), expected_metrics)
            self.assertIs(tab.analytics_grid.itemAtPosition(0 if columns == 2 else 1, 1 if columns == 2 else 0).widget(), tab.canvas_compare)
            for box in tab.month_checks:
                self.assertGreater(box.width(), 0)
                self.assertGreater(box.height(), 0)
            self.assertLessEqual(tab.canvas_trend.width(), tab.stats_scroll.viewport().width())

    def test_flow_controls_do_not_overlap(self):
        widget = QWidget(); flow = SCOPE['AnalyticsFlowLayout'](widget)
        buttons = [QPushButton(text) for text in ['选择月份', '一月', '二月', '三月', '全选', '上个月', '下个月']]
        for button in buttons:flow.addWidget(button)
        widget.resize(280, 250); widget.show(); self.process()
        for index, button in enumerate(buttons):
            self.assertGreaterEqual(button.x(), 0)
            self.assertLessEqual(button.geometry().right(), widget.width())
            for other in buttons[index+1:]:
                self.assertFalse(button.geometry().intersects(other.geometry()))
        self.assertGreater(flow.heightForWidth(280), flow.heightForWidth(800))
        widget.close(); widget.deleteLater()

    def test_hidden_table_export_uses_current_filters_and_empty_resets(self):
        tab = self.build()
        rows = pd.DataFrame([{'日期':'2026-10-02', '收入':Decimal('12.34')}])
        with patch.object(tab, 'refresh_inventory_balance'), patch.object(tab, 'refresh_outbound_stats'), \
             patch.object(tab, '_refresh_food_button_options'), patch.object(tab, '_refresh_consumption_button_options'), \
             patch.object(tab, '_update_month_forecast'), patch.object(tab, 'draw_business_trend'), \
             patch.object(tab, 'draw_business_compare'), patch.object(tab, 'draw_business_weekday'), \
             patch.object(tab, '_business_frame', return_value=rows), \
             patch.object(tab, 'update_business_table', side_effect=lambda frame, metrics: tab._set_table(frame)):
            tab.view_checks['table'].setChecked(False)
            tab.refresh()
            self.assertTrue(tab.table_stats.isHidden())
            self.assertEqual(tab._last_table_export.iloc[0]['收入'], Decimal('12.34'))
            self.assertTrue(tab.btn_export.isEnabled())
            self.assertIn('1 条来源记录', tab.analysis_context.text())
            for checkbox in tab.month_checks:
                checkbox.blockSignals(True); checkbox.setChecked(False); checkbox.blockSignals(False)
            tab.refresh()
            self.assertTrue(tab._last_table_export.empty)
            self.assertFalse(tab.btn_export.isEnabled())

    def test_secondary_sections_collapse_without_resetting_selection(self):
        tab = self.build()
        tab.selected_food_items = {'保留原样的用户食材'}
        group = tab.food_group
        self.assertTrue(group._analysis_body.isHidden())
        group._analysis_toggle.setChecked(True)
        self.assertFalse(group._analysis_body.isHidden())
        group._analysis_toggle.setChecked(False)
        self.assertTrue(group._analysis_body.isHidden())
        self.assertEqual(tab.selected_food_items, {'保留原样的用户食材'})
        self.assertTrue(tab._is_food_analysis_active())

    def test_mixed_units_notice_and_source_record_count(self):
        tab = self.build()
        for name, checkbox in zip(tab.metric_names, tab.metric_checks):
            checkbox.blockSignals(True); checkbox.setChecked(name in ('收入', '总客人数')); checkbox.blockSignals(False)
        tab._update_analysis_context(pd.DataFrame([{'日期':'2026-10-01'}, {'日期':'2026-10-02'}]))
        self.assertFalse(tab.analysis_unit_warning.isHidden())
        self.assertIn('2 条来源记录', tab.analysis_context.text())
        for name, checkbox in zip(tab.metric_names, tab.metric_checks):
            checkbox.blockSignals(True); checkbox.setChecked(name in ('收入', '净利润')); checkbox.blockSignals(False)
        tab._update_analysis_context(pd.DataFrame())
        self.assertTrue(tab.analysis_unit_warning.isHidden())

    def test_plot_keeps_exact_source_points_and_zero_reference(self):
        tab = self.build()
        source=[Decimal('0.10'), Decimal('-0.20'), Decimal('0.30')]
        tab._plot_series(tab.canvas_trend, ['2026-10-01','2026-10-02','2026-10-03'], {'收入':source}, '合成数据')
        axis=tab.canvas_trend.figure.axes[0]
        self.assertEqual(list(axis.lines[0].get_ydata()), [0.1,-0.2,0.3])
        self.assertEqual(source, [Decimal('0.10'),Decimal('-0.20'),Decimal('0.30')])
        self.assertEqual(list(axis.lines[-1].get_ydata()), [0,0])
        self.assertFalse(axis.spines['top'].get_visible())
        self.assertFalse(axis.spines['right'].get_visible())
        self.assertEqual(len(axis._restaurant_value_annotations),3)

if __name__ == '__main__':
    unittest.main(verbosity=2)
