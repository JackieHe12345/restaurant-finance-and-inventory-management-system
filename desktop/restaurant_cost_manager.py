# -*- coding: utf-8 -*-

import os
import sys
import json
import calendar
import errno
import traceback
import re
import tempfile
import shutil
import hashlib
import uuid
import subprocess
import time
import plistlib
from contextlib import contextmanager
from datetime import datetime, timedelta

import fcntl

# Monetary arithmetic uses decimal values constructed from text. Configure the
# default context as well, so background sync threads share the same precision.
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, DefaultContext, getcontext
DefaultContext.prec = 256
DefaultContext.rounding = ROUND_HALF_UP
getcontext().prec = 256
getcontext().rounding = ROUND_HALF_UP
MAX_ABS_AMOUNT = Decimal('999999999999.99')
MAX_UNIT_PRICE = Decimal('999999999999.999999')
MONEY_CENT = Decimal('0.01')
PRICE_UNIT = Decimal('0.000001')
MONEY_FIELDS = frozenset({
    '收益','总金额','收入','总收入','总现金','总线上','A店收入','B店收入',
    'A店现金','B店现金','A店微信增加','A店微信自动','A店微信覆盖','A店支付宝增加','A店支付宝覆盖',
    'B店微信增加','B店微信自动','B店微信覆盖','B店支付宝增加','B店支付宝覆盖','学生外卖','A店外卖','B店外卖',
    'A店微信支付金额','A店微信退款金额','B店微信支付金额','B店微信退款金额',
    '食材成本','佐料成本','水电','其他','其它','手续费','成本','总成本','金额','总价',
    '人工总额','房租总额','水电费','水费支出','电费支出','实际使用水费','实际使用电费','预计水费','预计电费',
    '煤气费','预计煤气费','其它固定成本','可用余额','向股东借款',
    'base_balance','opening_balance','shareholder_loan','amount','total','cost','known_cost','balance',
    'revenue','food_cost','spice_cost','total_cost','fixed_cost','gross_profit','net_profit',
    'allocated_cost','original_total','remaining_cost','current_balance','income','expense','running_balance','previous_month_balance','单份成本',
})
PRICE_FIELDS = frozenset({'price','unit_price','单价','单位价'})
DETAIL_JSON_FIELDS = frozenset({'食材明细','佐料明细','其他明细','其它明细','菜品数据'})
QUANTITY_FIELDS = frozenset({'quantity','数量','previous_quantity','remaining','debt','received','dish','normal','loss',
                           'unknown_quantity','shortage_quantity','change','balance_after','source_quantity','target_quantity',
                           'combined_quantity','after_quantity','delta','份数','新客人数量','总客人数','老客人数'})


def decimal_number(value=0):
    """Read legacy numeric values via their decimal spelling, never Decimal(float)."""
    if value is None or str(value).strip() == '':
        return Decimal(0)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('请输入有效的十进制数字。') from exc
    if not result.is_finite():
        raise ValueError('金额或数量必须是有限数字。')
    return result


def money_amount(value=0):
    if isinstance(value, bool) or str(value).strip().lower() in {'nan','inf','infinity','-inf','-infinity'}:
        raise ValueError('金额必须是有限的十进制数字，不能是布尔值。')
    result = decimal_number(value).quantize(MONEY_CENT, rounding=ROUND_HALF_UP)
    return abs(result) if not result else result


def unit_price_value(value=0):
    if isinstance(value, bool) or str(value).strip().lower() in {'nan','inf','infinity','-inf','-infinity'}:
        raise ValueError('单价必须是有限的十进制数字，不能是布尔值。')
    result = decimal_number(value).quantize(PRICE_UNIT, rounding=ROUND_HALF_UP)
    return abs(result) if not result else result


def money_input(value=0):
    result = money_amount(value)
    if abs(decimal_number(value)) > MAX_ABS_AMOUNT or abs(result) > MAX_ABS_AMOUNT:
        raise ValueError('金额不能超过 ±999,999,999,999.99 元。')
    return result


def unit_price_input(value=0):
    result = unit_price_value(value)
    if abs(decimal_number(value)) > MAX_UNIT_PRICE or abs(result) > MAX_UNIT_PRICE:
        raise ValueError('单价整数部分最多12位，小数最多6位。')
    return result


def derived_money_field(key, row):
    def entered(field):return field in row and row[field] is not None and str(row[field]).strip() != ''
    channels={slot:[slot+suffix for suffix in ('现金','微信增加','微信自动','微信覆盖','支付宝增加','支付宝覆盖','外卖')] for slot in ('A店','B店')}
    if key in ('A店收入','B店收入'):return any(entered(field) for field in channels[key[:2]])
    if key == '总现金':return any(entered(field) for field in ('A店现金','B店现金'))
    if key == '总线上':return any(entered(field) for field in channels['A店'][1:]+channels['B店'][1:]+['学生外卖'])
    if key in ('收益','总金额','收入','总收入'):return any(entered(field) for field in channels['A店']+channels['B店']+['学生外卖'])
    if key in ('食材成本','佐料成本'):
        detail=row.get('食材明细' if key=='食材成本' else '佐料明细')
        if isinstance(detail,str):
            try:detail=json.loads(detail)
            except ValueError:return bool(detail.strip())
        return isinstance(detail,(list,dict)) and bool(detail)
    return False


def validate_money_changes(value, previous=None, field=''):
    """Validate changed stored money; unchanged historical over-limit values remain readable."""
    if isinstance(value, dict):
        previous = previous if isinstance(previous, dict) else {}
        for key, item in value.items():
            if derived_money_field(key, value):
                money_amount(item)
            elif key in MONEY_FIELDS | PRICE_FIELDS | DETAIL_JSON_FIELDS | MONEY_CONTAINERS | MONEY_ENVELOPES:
                validate_money_changes(item, previous.get(key), str(key))
    elif isinstance(value, (list, tuple)):
        previous = previous if isinstance(previous, (list, tuple)) else []
        by_id = {str(row.get('id')): row for row in previous if isinstance(row, dict) and row.get('id')}
        for index, item in enumerate(value):
            old = by_id.get(str(item.get('id'))) if isinstance(item, dict) and item.get('id') else (previous[index] if index < len(previous) else None)
            validate_money_changes(item, old)
    elif field in DETAIL_JSON_FIELDS and isinstance(value, str) and value.strip().startswith(('[','{')):
        try:
            parsed = exact_json_loads(value)
            old = exact_json_loads(previous) if isinstance(previous, str) else previous
        except (ValueError, TypeError):return
        validate_money_changes(parsed, old)
    elif field in DETAIL_JSON_FIELDS and isinstance(value, str) and value != previous:
        for token in re.split(r'[,，;；\n]+', value):
            body=re.split(r'\s+备注[:：]', token, maxsplit=1)[0].strip()
            match=re.search(r'\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*$', body)
            if match:
                try:money_input(match.group(1))
                except ValueError as exc:raise ExcelFormatError(str(exc)) from exc
    elif field in MONEY_FIELDS | PRICE_FIELDS and value is not None and str(value).strip() != '':
        amount = unit_price_value(value) if field in PRICE_FIELDS else money_amount(value)
        limit = MAX_UNIT_PRICE if field in PRICE_FIELDS else MAX_ABS_AMOUNT
        if abs(amount) > limit:
            try:unchanged = amount == (unit_price_value(previous) if field in PRICE_FIELDS else money_amount(previous))
            except (ValueError, InvalidOperation):unchanged = False
            if not unchanged:raise ExcelFormatError(f'【{field}】超出允许范围：金额上限999,999,999,999.99元，单价整数最多12位。')


def money_text(value=0):
    return format(money_amount(value), '.2f')


def price_text(value=0):
    return format(unit_price_value(value), '.6f')


def decimal_divide(numerator, denominator):
    return decimal_number(numerator) / decimal_number(denominator)


def decimal_sum(values):
    return sum((decimal_number(value) for value in values), Decimal(0))


MONEY_CONTAINERS = frozenset({'daily','monthly_fixed','fixed_expenses','dishes','entries','adjustments','overrides','transactions','final_quantities','records','changed_records'})
MONEY_ENVELOPES = frozenset({'payload','merged_payload','before','after'})


def _plain_decimal_numbers(value):
    if isinstance(value, dict):return {key:_plain_decimal_numbers(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)):return [_plain_decimal_numbers(item) for item in value]
    if isinstance(value, Decimal):return int(value) if value == value.to_integral_value() else float(value)
    return value


def money_payload(value, field='', normalize_details=False):
    """Canonical money only in known financial rows; extension metadata is untouched."""
    if field in MONEY_FIELDS | PRICE_FIELDS and value is not None and str(value).strip() != '':
        return price_text(value) if field in PRICE_FIELDS else money_text(value)
    if field in DETAIL_JSON_FIELDS and isinstance(value, str) and value.strip().startswith(('[','{')):
        if not normalize_details:return value
        try:parsed = json.loads(value, parse_float=Decimal)
        except (ValueError, TypeError):return value
        canonical = money_payload(parsed, normalize_details=normalize_details)
        if canonical == parsed:return value
        return json.dumps(canonical, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if isinstance(value, dict):
        result = {}
        for key,item in value.items():
            key = str(key)
            if key in MONEY_FIELDS | PRICE_FIELDS | DETAIL_JSON_FIELDS:result[key] = money_payload(item, key, normalize_details)
            elif key in MONEY_CONTAINERS | MONEY_ENVELOPES:result[key] = money_payload(item, normalize_details=normalize_details)
            else:result[key] = _plain_decimal_numbers(item)
        return result
    if isinstance(value, (list,tuple)):return [money_payload(item, normalize_details=normalize_details) for item in value]
    return _plain_decimal_numbers(value)


def prepare_money_save(value, previous=None, field=''):
    """Only changed detail JSON is normalized; customer-only edits keep exact source text."""
    if field in DETAIL_JSON_FIELDS and isinstance(value, str):
        return value if value == previous else money_payload(value, field, normalize_details=True)
    if isinstance(value, dict):
        old = previous if isinstance(previous, dict) else {}
        result = dict(value)
        for key,item in value.items():
            if key in MONEY_FIELDS | PRICE_FIELDS | DETAIL_JSON_FIELDS | MONEY_CONTAINERS | MONEY_ENVELOPES:
                result[key] = prepare_money_save(item, old.get(key), str(key))
        return result
    if isinstance(value, (list,tuple)):
        old = previous if isinstance(previous, (list,tuple)) else []
        keyed = {}
        for row in old:
            if isinstance(row, dict):
                identity = next(((key,str(row[key])) for key in ('id','日期','date','月份') if row.get(key) not in (None,'')),None)
                if identity:keyed[identity]=row
        result=[]
        for index,item in enumerate(value):
            identity = next(((key,str(item[key])) for key in ('id','日期','date','月份') if isinstance(item,dict) and item.get(key) not in (None,'')),None)
            before = keyed.get(identity) if identity else old[index] if index < len(old) else None
            result.append(prepare_money_save(item,before))
        return result
    return money_payload(value, field)


def exact_json_dumps(value, **kwargs):
    kwargs.setdefault('allow_nan', False)
    return json.dumps(money_payload(value), **kwargs)


def exact_json_loads(value, **kwargs):
    kwargs.setdefault('parse_float', Decimal)
    kwargs.setdefault('parse_constant', lambda value: (_ for _ in ()).throw(ValueError('JSON含无效数字：'+value)))
    return money_payload(json.loads(value, **kwargs))


def read_excel_exact(*args, **kwargs):
    # dtype=object preserves monetary text cells. Legacy numeric cells remain
    # readable and are converted via Decimal(str(value)) by the business layer.
    kwargs.setdefault('dtype', object)
    return pd.read_excel(*args, **kwargs)


def money_statistics_frame(frame):
    """CSV exports use the same decimal rounding as the displayed ledger."""
    clean=frame.copy().astype(object)
    for column in clean.columns:
        label=str(column)
        def display(value):
            if not isinstance(value, Decimal):return value
            if any(word in label for word in ('数量','份数','出库量','使用量','消耗量','采购量')):return format(value,'f')
            return price_text(value) if '单价' in label and '客单价' not in label else money_text(value)
        clean[column]=clean[column].map(display)
    return clean


def money_excel_frame(frame):
    """Write money as text cells: Excel numbers cannot preserve arbitrary decimals."""
    clean = frame.copy().astype(object)
    for column in clean.columns:
        if str(column) in MONEY_FIELDS | PRICE_FIELDS | DETAIL_JSON_FIELDS:
            clean[column] = clean[column].map(lambda value: money_payload(value, str(column)))
        else:
            clean[column] = clean[column].map(lambda value: format(value, 'f') if isinstance(value, Decimal) else value)
    return clean


# 1. 强制系统环境使用 PySide6
os.environ['QT_API'] = 'pyside6'

import matplotlib

matplotlib.use('QtAgg')
matplotlib.rcParams['font.sans-serif'] = ['PingFang SC', 'Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False

import pandas as pd
from openpyxl import load_workbook
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtWidgets import QScrollArea

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDateEdit, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFormLayout, QGroupBox, QGridLayout, QComboBox,
    QDialog, QInputDialog, QFileDialog, QCheckBox, QAbstractItemView, QTextEdit,
    QFrame, QSizePolicy, QListWidget, QListWidgetItem, QDateTimeEdit
)
from PySide6.QtCore import Qt, QDate, QDateTime, QEvent, QStandardPaths, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIntValidator

# Keep the product version in the source as well as in the packaged bundle.  The
# delivery version for this build is Oct30LingChen.
APP_VERSION = "Oct30LingChen"

# A cloud login can be valid while the first background record refresh is still
# in flight.  Require several failed cycles and a short grace period before
# interrupting the user with an offline dialog.
OFFLINE_WARNING_DELAY_SECONDS = 20.0
OFFLINE_MIN_FAILURES = 3
STARTUP_CONNECTION_GRACE_SECONDS = 30.0

# ===================== 双程序连接与服务器监测 =====================
"""餐饮成本管家与云同步助手共用的本机连接、云端服务器状态监测。

主程序不再显示泛泛的“互联网是否可用”。它只显示：
1. 是否已经与云同步助手建立本机连接；
2. 在已连接同步助手时，当前配置的 API 服务器是否可达。
"""

import json
import os
import socket
import threading
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit


CHECK_INTERVAL_SECONDS = 3.0
PEER_STALE_SECONDS = 12.0
MAIN_PORT = int(os.environ.get("RESTAURANT_MAIN_STATUS_PORT", "47650"))
ASSISTANT_PORT = int(os.environ.get("RESTAURANT_ASSISTANT_STATUS_PORT", "47651"))
SYNC_ASSISTANT_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".restaurant_finance_sync", "config.json"
)
DESKTOP_RELOGIN_SECONDS = 2 * 60 * 60


def _configured_api_url() -> str:
    try:
        with open(SYNC_ASSISTANT_CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("api_url") or "").strip().rstrip("/")


def check_server() -> bool:
    """快速检查同步 API 主机端口，避免一次 HTTP 卡顿造成长时间误报断线。"""
    api_url = _configured_api_url()
    if not api_url.startswith(("http://", "https://")):
        return False
    try:
        parsed = urlsplit(api_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if host:
            with socket.create_connection((host, port), timeout=1):
                return True
    except (OSError, ValueError):
        pass
    try:
        request = Request(
            api_url + "/api/v1/health",
            headers={"Accept": "application/json", "User-Agent": "RestaurantFinance/1", "Connection": "close"},
        )
        with urlopen(request, timeout=1.5) as response:
            _ = response.status
            return True
    except HTTPError:
        return True
    except (URLError, OSError, ValueError, TimeoutError):
        return False


class LocalConnectionMonitor:
    """后台监测器；所有网络操作都在线程中进行，不会卡住 GUI。"""

    def __init__(
        self,
        role: str,
        *,
        interval_seconds: float = CHECK_INTERVAL_SECONDS,
        main_port: int = MAIN_PORT,
        assistant_port: int = ASSISTANT_PORT,
        server_checker: Callable[[], bool] | None = None,
    ) -> None:
        if role not in {"cost_manager", "sync_assistant"}:
            raise ValueError(f"未知程序角色：{role}")
        self.role = role
        self.peer_role = "sync_assistant" if role == "cost_manager" else "cost_manager"
        self.listen_port = main_port if role == "cost_manager" else assistant_port
        self.peer_port = assistant_port if role == "cost_manager" else main_port
        self.interval_seconds = max(0.2, float(interval_seconds))
        self.server_checker = server_checker or check_server

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._threads: list[threading.Thread] = []
        self._started = False
        self._peer_probe_ok = False
        self._peer_pid: int | None = None
        self._last_peer_seen = 0
        self._server_connected: bool | None = None
        self._last_checked_at: float | None = None
        self._listener_error = ""
        self._server_failures = 0

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        listener = threading.Thread(
            target=self._listener_loop,
            name=f"{self.role}-local-listener",
            daemon=True,
        )
        checker = threading.Thread(
            target=self._check_loop,
            name=f"{self.role}-connection-checker",
            daemon=True,
        )
        self._threads = [listener, checker]
        listener.start()
        checker.start()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        server = self._server
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        self._notify_peer_disconnect()
        for thread in self._threads:
            thread.join(timeout=1.5)

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            peer_pid = self._peer_pid
            incoming_fresh = (
                self._last_peer_seen > 0
                and now - self._last_peer_seen <= PEER_STALE_SECONDS
            )
            peer_connected = bool(self._peer_probe_ok or incoming_fresh)
        if peer_connected and peer_pid and not self._process_is_alive(peer_pid):
            with self._lock:
                if self._peer_pid == peer_pid:
                    self._peer_probe_ok = False
                    self._peer_pid = None
                    self._last_peer_seen = 0
            peer_connected = False
        with self._lock:
            return {
                "peer_connected": peer_connected,
                "server_connected": self._server_connected,
                "last_checked_at": self._last_checked_at,
                "listener_error": self._listener_error,
                "retry_seconds": int(self.interval_seconds),
            }

    @staticmethod
    def _process_is_alive(pid: int) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except (PermissionError, OSError, ValueError):
            return True

    def _mark_peer_disconnected(self) -> None:
        with self._lock:
            self._peer_probe_ok = False
            self._peer_pid = None
            self._last_peer_seen = 0

    def _listener_loop(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", self.listen_port))
            server.listen(4)
            server.settimeout(0.5)
            self._server = server
        except OSError as exc:
            with self._lock:
                self._listener_error = str(exc)
            try:
                server.close()
            except OSError:
                pass
            return

        while not self._stop.is_set():
            try:
                connection, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                connection.settimeout(1)
                payload = self._receive_json(connection)
                if str(payload.get("role") or "") != self.peer_role:
                    continue
                event = str(payload.get("event") or "ping")
                if event == "disconnect":
                    self._mark_peer_disconnected()
                    connection.sendall(
                        exact_json_dumps({"role": self.role, "event": "ack"}).encode("utf-8")
                        + b"\n"
                    )
                    continue
                try:
                    peer_pid = int(payload.get("pid") or 0) or None
                except (TypeError, ValueError):
                    peer_pid = None
                with self._lock:
                    self._last_peer_seen = time.monotonic()
                    self._peer_pid = peer_pid
                response = exact_json_dumps(
                    {"role": self.role, "event": "pong", "pid": os.getpid()},
                    ensure_ascii=False,
                ).encode("utf-8") + b"\n"
                connection.sendall(response)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            finally:
                try:
                    connection.close()
                except OSError:
                    pass

    @staticmethod
    def _receive_json(connection: socket.socket) -> dict[str, Any]:
        chunks = bytearray()
        while len(chunks) < 4096:
            part = connection.recv(1024)
            if not part:
                break
            chunks.extend(part)
            if b"\n" in part:
                break
        raw = bytes(chunks).split(b"\n", 1)[0]
        value = exact_json_loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("连接响应格式不正确")
        return value

    def _probe_peer(self) -> bool:
        try:
            with socket.create_connection(
                ("127.0.0.1", self.peer_port), timeout=1
            ) as connection:
                connection.settimeout(1)
                request = exact_json_dumps(
                    {"role": self.role, "event": "ping", "pid": os.getpid()},
                    ensure_ascii=False,
                ).encode("utf-8") + b"\n"
                connection.sendall(request)
                response = self._receive_json(connection)
                role_matches = str(response.get("role") or "") == self.peer_role
                if role_matches:
                    try:
                        peer_pid = int(response.get("pid") or 0) or None
                    except (TypeError, ValueError):
                        peer_pid = None
                    with self._lock:
                        self._peer_pid = peer_pid
                return role_matches
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def _notify_peer_disconnect(self) -> None:
        try:
            with socket.create_connection(
                ("127.0.0.1", self.peer_port), timeout=0.35
            ) as connection:
                connection.settimeout(0.35)
                payload = exact_json_dumps(
                    {"role": self.role, "event": "disconnect", "pid": os.getpid()},
                    ensure_ascii=False,
                ).encode("utf-8") + b"\n"
                connection.sendall(payload)
                try:
                    self._receive_json(connection)
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
        except OSError:
            pass

    def _check_loop(self) -> None:
        while not self._stop.is_set():
            cycle_started = time.monotonic()
            peer_ok = self._probe_peer()
            try:
                server_ok = bool(self.server_checker())
            except Exception:
                server_ok = False
            with self._lock:
                self._peer_probe_ok = peer_ok
                if peer_ok:
                    self._last_peer_seen = time.monotonic()
                if server_ok:
                    self._server_failures = 0
                    self._server_connected = True
                else:
                    self._server_failures += 1
                    if self._server_connected is None or self._server_failures >= 2:
                        self._server_connected = False
                self._last_checked_at = time.time()
            elapsed = time.monotonic() - cycle_started
            self._stop.wait(max(0, self.interval_seconds - elapsed))


__all__ = [
    "ASSISTANT_PORT",
    "CHECK_INTERVAL_SECONDS",
    "LocalConnectionMonitor",
    "MAIN_PORT",
    "check_server",
]
# ===================== 连接监测器结束 =====================


# ===================== 内置云同步 =====================
class CloudSyncError(RuntimeError):
    def __init__(self, message, status_code=0):
        super().__init__(message)
        self.status_code = int(status_code or 0)


def load_embedded_sync_config():
    try:
        with open(SYNC_ASSISTANT_CONFIG_PATH, 'r', encoding='utf-8') as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_embedded_sync_config(config):
    folder = os.path.dirname(SYNC_ASSISTANT_CONFIG_PATH)
    os.makedirs(folder, exist_ok=True)
    temporary = SYNC_ASSISTANT_CONFIG_PATH + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, SYNC_ASSISTANT_CONFIG_PATH)


def desktop_cloud_login_required(config=None):
    """Require a fresh password when the previous clean close was over two hours ago."""
    config = config if isinstance(config, dict) else load_embedded_sync_config()
    if not all(str(config.get(key) or '').strip() for key in ('api_url', 'username', 'password')):
        return True
    closed_at = str(config.get('last_closed_at') or '').strip()
    if not closed_at:
        return True
    try:
        closed = datetime.fromisoformat(closed_at)
        now = datetime.now(closed.tzinfo) if closed.tzinfo else datetime.now()
        return max(0, (now - closed).total_seconds()) >= DESKTOP_RELOGIN_SECONDS
    except (TypeError, ValueError, OverflowError):
        return True


def _cloud_api_base(config):
    value = str(config.get('api_url') or '').strip().rstrip('/')
    if value.endswith('/api/v1'):
        value = value[:-7]
    if not value.startswith(('http://', 'https://')):
        raise CloudSyncError('API 地址必须以 http:// 或 https:// 开头。')
    return value + '/api/v1'


def cloud_api_request(config, path, method='GET', payload=None, token='', timeout=12):
    headers = {'Accept': 'application/json', 'User-Agent': 'RestaurantFinance/embedded-sync'}
    body = None
    if payload is not None:
        body = exact_json_dumps(money_payload(payload), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = Request(_cloud_api_base(config) + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return exact_json_loads(raw.decode('utf-8')) if raw else None
    except HTTPError as exc:
        try:
            detail = exact_json_loads(exc.read().decode('utf-8')).get('detail')
            if isinstance(detail, dict):
                detail = detail.get('message') or exact_json_dumps(detail, ensure_ascii=False)
        except Exception:
            detail = ''
        raise CloudSyncError(str(detail or f'云端请求失败（{exc.code}）'), exc.code) from exc
    except (URLError, OSError, ValueError, TimeoutError) as exc:
        raise CloudSyncError(f'无法连接云端 API：{exc}') from exc


def cloud_api_upload_workbook(config, path, route, *, year=None, token='', timeout=30):
    """Upload one xlsx workbook using the same authenticated API as the sync loop."""
    path = os.path.abspath(os.path.expanduser(str(path or '').strip()))
    if not path.lower().endswith('.xlsx') or not os.path.isfile(path):
        raise CloudSyncError('请选择存在的 .xlsx 文件。')
    try:
        with open(path, 'rb') as handle:
            content = handle.read()
    except OSError as exc:
        raise CloudSyncError(f'无法读取 Excel：{exc}') from exc
    if not content:
        raise CloudSyncError('Excel 文件为空。')
    boundary = f'----RestaurantFinance{uuid.uuid4().hex}'
    filename = os.path.basename(path).replace('"', '') or 'workbook.xlsx'
    body = b''.join([
        f'--{boundary}\r\n'.encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n',
        content,
        f'\r\n--{boundary}--\r\n'.encode(),
    ])
    query = f'?year={int(year)}' if year is not None else ''
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'User-Agent': 'RestaurantFinance/embedded-sync',
    }
    request = Request(_cloud_api_base(config) + route + query, data=body, headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return exact_json_loads(raw.decode('utf-8')) if raw else {}
    except HTTPError as exc:
        try:
            payload = exact_json_loads(exc.read().decode('utf-8'))
            detail = payload.get('detail') if isinstance(payload, dict) else ''
        except Exception:
            detail = ''
        raise CloudSyncError(str(detail or f'云端请求失败（{exc.code}）'), exc.code) from exc
    except (URLError, OSError, ValueError, TimeoutError) as exc:
        raise CloudSyncError(f'无法连接云端 API：{exc}') from exc


def cloud_api_multipart(config, route, *, fields=None, files=None, token='', timeout=45):
    """Send a small multipart/form-data request to the cloud API."""
    fields = fields or {}
    files = files or {}
    boundary = f'----RestaurantFinance{uuid.uuid4().hex}'
    parts = []
    for name, value in fields.items():
        parts.extend([
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode('utf-8'), b'\r\n',
        ])
    for name, path in files.items():
        if not path:
            continue
        resolved = os.path.abspath(os.path.expanduser(str(path)))
        if not os.path.isfile(resolved):
            raise CloudSyncError(f'文件不存在：{resolved}')
        with open(resolved, 'rb') as handle:
            content = handle.read()
        if len(content) > 2 * 1024 * 1024:
            raise CloudSyncError(f'微信支付文件超过 2 MB：{os.path.basename(resolved)}')
        filename = os.path.basename(resolved).replace('"', '')
        parts.extend([
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            b'Content-Type: application/octet-stream\r\n\r\n',
            content, b'\r\n',
        ])
    parts.append(f'--{boundary}--\r\n'.encode())
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'User-Agent': 'RestaurantFinance/embedded-sync-v26',
    }
    request = Request(_cloud_api_base(config) + route, data=b''.join(parts), headers=headers, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return exact_json_loads(raw.decode('utf-8')) if raw else {}
    except HTTPError as exc:
        try:
            payload = exact_json_loads(exc.read().decode('utf-8'))
            detail = payload.get('detail') if isinstance(payload, dict) else ''
            if isinstance(detail, dict):
                detail = detail.get('message') or exact_json_dumps(detail, ensure_ascii=False)
        except Exception:
            detail = ''
        raise CloudSyncError(str(detail or f'云端请求失败（{exc.code}）'), exc.code) from exc
    except (URLError, OSError, ValueError, TimeoutError) as exc:
        raise CloudSyncError(f'无法连接云端 API：{exc}') from exc


def _embedded_payload_hash(payload):
    raw = exact_json_dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False,
                     sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _embedded_local_records():
    path = str(globals().get('INTERNAL_FILE_PATH') or '').strip()
    if not path or not os.path.exists(path):
        return {}
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
    result = {}
    mapping = {
        'day': ('__day_records', '日期'),
        'month': ('__month_records', '月份'),
        'global': ('__global_records', '记录类型'),
    }
    for record_type, (sheet_name, key_column) in mapping.items():
        frame = frames.get(sheet_name, pd.DataFrame())
        if frame.empty:
            continue
        for _, row in frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != FIXED_CLOUD_DATASET_ID:
                continue
            key = str(row.get(key_column, '')).strip()
            if not key:
                continue
            try:
                payload = exact_json_loads(str(row.get('payload_json', '') or '{}'))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            result[(record_type, key)] = {
                'record_type': record_type,
                'record_key': key,
                'payload': payload if isinstance(payload, dict) else {},
                'checksum': str(row.get('sha256', '')).strip() or _embedded_payload_hash(payload),
            }
    return result


def _embedded_apply_cloud_records(records, replace_all=False):
    path = str(globals().get('INTERNAL_FILE_PATH') or '').strip()
    if not path:
        return False
    mapping = {
        'day': ('__day_records', '日期'),
        'month': ('__month_records', '月份'),
        'global': ('__global_records', '记录类型'),
    }
    changed = False
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
        if replace_all:
            for sheet_name, _key_column in mapping.values():
                frame = frames[sheet_name]
                frames[sheet_name] = frame[
                    frame['dataset_id'].astype(str) != FIXED_CLOUD_DATASET_ID
                ].copy().reset_index(drop=True)
            changed = True
        for record in records:
            record_type = str(record.get('record_type') or '')
            key = str(record.get('record_key') or '')
            if record_type not in mapping or not key:
                continue
            sheet_name, key_column = mapping[record_type]
            before = _internal_payload_for_identity(
                frames, FIXED_CLOUD_DATASET_ID, (record_type, key)
            )
            if record.get('is_deleted'):
                frames[sheet_name] = _replace_internal_record(
                    frames[sheet_name], FIXED_CLOUD_DATASET_ID, key_column, key
                )
                changed = changed or before is not None
                continue
            payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
            payload_json, digest = _payload_and_hash(payload)
            frames[sheet_name] = _replace_internal_record(
                frames[sheet_name], FIXED_CLOUD_DATASET_ID, key_column, key,
                payload_json, digest,
            )
            changed = changed or before != payload
        if changed:
            meta = frames.get('__meta', pd.DataFrame(columns=INTERNAL_META_COLUMNS))
            meta = meta[meta['dataset_id'].astype(str) != FIXED_CLOUD_DATASET_ID].copy()
            frames['__meta'] = pd.concat([meta, pd.DataFrame([{
                'dataset_id': FIXED_CLOUD_DATASET_ID,
                'schema_version': 2,
                'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }])], ignore_index=True)
            _write_internal_frames(path, frames)
    return changed


class EmbeddedCloudSyncWorker:
    def __init__(self, interval_seconds=2.0):
        self.interval_seconds = max(1, float(interval_seconds))
        self._lock = threading.Lock()
        self._transaction_lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._token = ''
        self._auth_signature = None
        self._datasets = []
        self._datasets_checked_at = 0
        self._permissions_checked_at = 0
        self._state = {
            'configured': False, 'connected': False, 'role': '', 'datasets': [],
            'dataset_id': '', 'last_sync_at': '', 'error': '', 'conflicts': [],
            'temporary_permissions': [],
            # The connection to the server is a separate step from having a
            # usable internet connection.  A successful login proves that the
            # latter exists, so the UI can show a truthful in-progress state
            # instead of flashing an incorrect red "not connected" pill.
            'internet_connected': False,
            # A healthy connection stays healthy while a background sync is
            # running.  Keeping this separate prevents the UI from flashing
            # yellow/red for every normal polling cycle.
            'syncing': False,
            # Measured from the newest record-list request.  It is a useful
            # live network indicator, rather than a made-up broadband speed.
            'latency_ms': None,
            'download_kbps': None,
            # The UI uses these counters to distinguish a transient first
            # handshake from a persistent outage.  They are intentionally kept
            # in memory and are never written to the user's config file.
            'consecutive_failures': 0,
            'last_success_monotonic': None,
        }

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name='embedded-cloud-sync', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def wake(self):
        self._wake.set()

    def upload_workbook(self, path, operation, year=None):
        config = load_embedded_sync_config()
        self._login(config)
        self._refresh_datasets(config)
        role = str(self.snapshot().get('role') or '')
        if role != 'admin':
            raise CloudSyncError('只有管理员账号可以上传或合并 Excel。')
        dataset_id = str(config.get('dataset_id') or '')
        allowed = {str(item.get('id') or '') for item in self._datasets}
        if dataset_id not in allowed:
            dataset_id = str(next(iter(allowed), '') or '')
        if not dataset_id:
            raise CloudSyncError('当前账号没有可用账本。')
        config['dataset_id'] = dataset_id
        route = f'/datasets/{quote(dataset_id, safe="")}/workbooks/{operation}'
        result = cloud_api_upload_workbook(config, path, route, year=year, token=self._token)
        self.wake()
        return result

    def _current_dataset_id(self, config):
        self._refresh_datasets(config)
        dataset_id = str(config.get('dataset_id') or '')
        allowed = {str(item.get('id') or '') for item in self._datasets}
        if dataset_id not in allowed:
            raise CloudSyncError('当前账本不可用，请重新选择账本。')
        return dataset_id

    def get_audit_logs(self, start_date='', end_date=''):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') not in {'admin', 'editor'}:
            raise CloudSyncError('只有管理员或修改权限账号可以查看修改记录。')
        dataset_id = self._current_dataset_id(config)
        query = f'dataset_id={quote(dataset_id, safe="")}&hours=8784&limit=5000'
        if start_date:
            query += f'&start_date={quote(str(start_date), safe="")}'
        if end_date:
            query += f'&end_date={quote(str(end_date), safe="")}'
        result = cloud_api_request(config, f'/audit?{query}', token=self._token)
        return result if isinstance(result, list) else list((result or {}).get('items') or [])

    def delete_audit_log(self, audit_id):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员可以删除修改记录。')
        return cloud_api_request(
            config, f'/audit/{quote(str(audit_id), safe="")}', 'DELETE', token=self._token
        )

    def list_temporary_permissions(self):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员可以管理临时权限。')
        users = cloud_api_request(config, '/users', token=self._token) or []
        grants = cloud_api_request(config, '/temporary-permissions', token=self._token) or []
        self._refresh_datasets(config)
        return {'users': users, 'grants': grants, 'datasets': list(self._datasets)}

    def create_temporary_permission(self, payload):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员可以管理临时权限。')
        return cloud_api_request(config, '/temporary-permissions', 'POST', payload, self._token)

    def delete_temporary_permission(self, permission_id):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员可以管理临时权限。')
        return cloud_api_request(
            config, f'/temporary-permissions/{quote(str(permission_id), safe="")}',
            'DELETE', token=self._token,
        )

    def sync_wechat_bill(self, bill_date, force=False):
        config = load_embedded_sync_config()
        self._login(config)
        role = str(self.snapshot().get('role') or '')
        if role not in {'admin', 'editor', 'entry'}:
            raise CloudSyncError('当前账号只读，不能同步微信账单。')
        dataset_id = self._current_dataset_id(config)
        result = cloud_api_request(
            config,
            f'/datasets/{quote(dataset_id, safe="")}/wechat/sync?bill_date={quote(str(bill_date), safe="")}&force={"true" if force else "false"}',
            'POST', token=self._token, timeout=45,
        )
        self.wake()
        return result if isinstance(result, dict) else {}

    def sync_missing_wechat_month(self, month):
        """只处理指定月份截至昨天的空白/零收入日期。"""
        try:
            year, month_number = (int(part) for part in str(month).split('-'))
            first = datetime(year, month_number, 1).date()
            last = datetime(year, month_number, calendar.monthrange(year, month_number)[1]).date()
        except (TypeError, ValueError):
            raise CloudSyncError(f'月份格式无效：{month}')
        yesterday = datetime.now().date() - timedelta(days=1)
        end = min(last, yesterday)
        if first > end:
            return {'changed_days': 0, 'skipped': 0, 'month': str(month)}
        changed_days = skipped = 0
        for offset in range((end - first).days + 1):
            day = first + timedelta(days=offset)
            result = self.sync_wechat_bill(day.isoformat(), force=False)
            if result.get('changed'):
                changed_days += 1
            skipped += len(result.get('skipped_stores') or [])
        return {'changed_days': changed_days, 'skipped': skipped, 'month': str(month)}

    def get_store_settings(self):
        config = load_embedded_sync_config(); self._login(config)
        dataset_id = self._current_dataset_id(config)
        result = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/store-settings', token=self._token)
        return result if isinstance(result, dict) else {}

    def save_store_settings(self, store_a_name, store_b_name, auto_sync=True):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') not in {'admin', 'editor', 'entry'}:
            raise CloudSyncError('当前账号只读，不能修改店铺设置。')
        dataset_id = self._current_dataset_id(config)
        result = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/store-settings', 'PUT', {
            'store_a_name': str(store_a_name).strip(), 'store_b_name': str(store_b_name).strip(),
            'wechat_auto_sync': bool(auto_sync),
        }, self._token)
        self.wake(); return result if isinstance(result, dict) else {}

    def upload_store_wechat(self, store, mchid, public_key_id, paths):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以上传微信支付证书。')
        dataset_id = self._current_dataset_id(config)
        files = {
            'apiclient_cert': paths.get('cert'), 'apiclient_key': paths.get('key'), 'pub_key': paths.get('pub'),
            'apiclient_p12': paths.get('p12'), 'readme_cn': paths.get('readme'),
        }
        return cloud_api_multipart(
            config, f'/datasets/{quote(dataset_id, safe="")}/stores/{str(store).upper()}/wechat-config',
            fields={'mchid': mchid, 'public_key_id': public_key_id}, files=files,
            token=self._token, timeout=45,
        )

    def test_store_wechat(self, store, bill_date):
        config = load_embedded_sync_config(); self._login(config)
        dataset_id = self._current_dataset_id(config)
        return cloud_api_request(
            config,
            f'/datasets/{quote(dataset_id, safe="")}/stores/{str(store).upper()}/wechat-config/test?bill_date={quote(str(bill_date), safe="")}',
            'POST', token=self._token, timeout=45,
        )

    def delete_store_wechat(self, store):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以删除微信支付配置。')
        dataset_id = self._current_dataset_id(config)
        return cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/stores/{str(store).upper()}/wechat-config', 'DELETE', token=self._token)

    def bulk_delete_range(self, start_date, end_date):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以批量删除数据。')
        dataset_id = self._current_dataset_id(config)
        result = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/records/bulk-delete', 'POST', {
            'start_date': str(start_date), 'end_date': str(end_date),
            'delete_month_records': False, 'delete_inventory_in_range': True,
        }, self._token, timeout=30)
        self.wake(); return result if isinstance(result, dict) else {}

    def delete_whole_month(self, month):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以删除整月数据。')
        dataset_id = self._current_dataset_id(config)
        result = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/records/delete-month', 'POST', {
            'month': str(month), 'delete_inventory_in_month': True,
        }, self._token, timeout=30)
        self.wake(); return result if isinstance(result, dict) else {}

    def copy_entire_ledger(self, target_dataset_id, source_name, target_name):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以整体覆盖另一个账本。')
        source_id = self._current_dataset_id(config)
        result = cloud_api_request(config, f'/datasets/{quote(source_id, safe="")}/copy-to-ledger', 'POST', {
            'target_dataset_id': str(target_dataset_id), 'confirm_source_name': str(source_name),
            'confirm_target_name': str(target_name),
        }, self._token, timeout=60)
        return result if isinstance(result, dict) else {}

    def upload_internal_to_dataset(self, path, target_dataset_id):
        config = load_embedded_sync_config(); self._login(config)
        if str(self.snapshot().get('role') or '') != 'admin':
            raise CloudSyncError('只有管理员账号可以整体替换账本。')
        self._refresh_datasets(config)
        allowed = {str(item.get('id') or '') for item in self._datasets}
        if str(target_dataset_id) not in allowed:
            raise CloudSyncError('目标账本不可用。')
        target = next((item for item in self._datasets if str(item.get('id') or '') == str(target_dataset_id)), None)
        if not target:
            raise CloudSyncError('目标账本不可用。')
        target_name = str(target.get('name') or target_dataset_id)
        route = f'/datasets/{quote(str(target_dataset_id), safe="")}/workbooks/internal-overwrite'
        return cloud_api_multipart(
            config, route, fields={'confirm_target_name': target_name, 'confirm_again': target_name},
            files={'file': path}, token=self._token, timeout=60,
        )

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _set_state(self, **values):
        with self._lock:
            self._state.update(values)

    def _run(self):
        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                self._cycle()
                # ``_cycle`` returns normally for both a successful sync and
                # an intentionally unconfigured worker.  The latter is
                # represented by configured=False and should not trigger an
                # offline warning.
                snapshot = self.snapshot()
                if snapshot.get('connected'):
                    consecutive_failures = 0
                    self._set_state(
                        consecutive_failures=0,
                        last_success_monotonic=time.monotonic(),
                        internet_connected=True,
                    )
                else:
                    consecutive_failures = 0
                    self._set_state(consecutive_failures=0)
            except CloudSyncError as exc:
                consecutive_failures += 1
                if exc.status_code == 401:
                    self._token = ''
                self._set_state(
                    connected=False,
                    syncing=False,
                    error=str(exc),
                    consecutive_failures=consecutive_failures,
                    # An HTTP response (including an authentication error)
                    # proves that the device is online.  For the first few
                    # retries after a known-good login, keep the connecting
                    # state rather than prematurely declaring no network.
                    internet_connected=(bool(exc.status_code) or consecutive_failures < OFFLINE_MIN_FAILURES),
                )
            except Exception as exc:
                consecutive_failures += 1
                self._set_state(
                    connected=False,
                    syncing=False,
                    error=f'内置同步异常：{exc}',
                    consecutive_failures=consecutive_failures,
                    internet_connected=consecutive_failures < OFFLINE_MIN_FAILURES,
                )
            self._wake.wait(self.interval_seconds)
            self._wake.clear()

    def _login(self, config):
        signature = (config.get('api_url'), config.get('username'), config.get('password'))
        if self._token and signature == self._auth_signature:
            # Scheduled permissions can start or end while the App remains
            # open. Refresh /auth/me regularly instead of requiring relogin.
            if time.monotonic() - self._permissions_checked_at >= 10:
                user = cloud_api_request(config, '/auth/me', token=self._token) or {}
                self._permissions_checked_at = time.monotonic()
                self._set_state(
                    role=str(user.get('role') or 'viewer'), username=str(user.get('username') or config.get('username') or ''),
                    temporary_permissions=list(user.get('temporary_permissions') or []),
                )
            return
        if signature != self._auth_signature:
            self._datasets = []
            self._datasets_checked_at = 0
            self._permissions_checked_at = 0
        result = cloud_api_request(config, '/auth/login', 'POST', {
            'username': str(config.get('username') or '').strip(),
            'password': str(config.get('password') or ''),
        })
        self._token = str(result.get('access_token') or '')
        if not self._token:
            raise CloudSyncError('服务器没有返回登录令牌。')
        self._auth_signature = signature
        user = result.get('user') or {}
        self._permissions_checked_at = time.monotonic()
        self._set_state(
            role=str(user.get('role') or 'viewer'), username=str(user.get('username') or config.get('username') or ''),
            temporary_permissions=list(user.get('temporary_permissions') or []),
        )

    def _effective_role(self, role, dataset_id, identity):
        """Resolve a temporary grant for one exact day record."""
        record_type, record_key = identity
        if role in {'admin', 'editor'} or record_type != 'day':
            return role
        day = str(record_key or '')[:10].replace('/', '-')
        rank = {'viewer': 0, 'entry': 1, 'editor': 2, 'admin': 3}
        best = role if role in rank else 'viewer'
        now = datetime.now().astimezone()
        for grant in self.snapshot().get('temporary_permissions') or []:
            if str(grant.get('dataset_id') or '') != str(dataset_id):
                continue
            try:
                starts = datetime.fromisoformat(str(grant.get('starts_at') or '').replace('Z', '+00:00'))
                ends = datetime.fromisoformat(str(grant.get('ends_at') or '').replace('Z', '+00:00'))
                if starts.tzinfo is None:
                    starts = starts.astimezone()
                if ends.tzinfo is None:
                    ends = ends.astimezone()
                active = starts <= now < ends
            except (TypeError, ValueError):
                active = False
            grant_role = str(grant.get('permission_role') or '')
            if (active and str(grant.get('business_start_date') or '') <= day
                    <= str(grant.get('business_end_date') or '')
                    and rank.get(grant_role, 0) > rank.get(best, 0)):
                best = grant_role
        return best

    def _refresh_datasets(self, config):
        if self._datasets and time.monotonic() - self._datasets_checked_at < 30:
            return
        response = cloud_api_request(config, '/datasets', token=self._token)
        self._datasets = response if isinstance(response, list) else list((response or {}).get('items') or [])
        self._datasets_checked_at = time.monotonic()
        if not self._datasets:
            raise CloudSyncError('当前账号没有可用账本。')

    def _fetch_cloud_records(self, config, dataset_id):
        records, offset = [], 0
        while True:
            path = f'/datasets/{quote(dataset_id, safe="")}/records?include_deleted=true&offset={offset}&limit=5000'
            response = cloud_api_request(config, path, token=self._token)
            batch = response if isinstance(response, list) else list((response or {}).get('items') or [])
            records.extend(batch)
            if len(batch) < 5000:
                return records
            offset += len(batch)

    @staticmethod
    def _cloud_marker(record):
        if not record:
            return None
        if record.get('is_deleted'):
            return f"deleted:{record.get('version', 0)}"
        return str(record.get('checksum') or '') or _embedded_payload_hash(record.get('payload'))

    def _put_local(self, config, dataset_id, local, cloud, expected_version):
        record_type, key = local['record_type'], local['record_key']
        path = (f'/datasets/{quote(dataset_id, safe="")}/records/'
                f'{quote(record_type, safe="")}/{quote(key, safe="")}')
        return cloud_api_request(config, path, 'PUT', {
            'event_id': str(uuid.uuid4()),
            'expected_version': int(expected_version or 0),
            'occurred_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'source': 'embedded_desktop',
            'payload': local['payload'],
            'checksum': local['checksum'],
        }, self._token)

    def _delete_cloud(self, config, dataset_id, cloud):
        record_type, key = cloud['record_type'], cloud['record_key']
        path = (f'/datasets/{quote(dataset_id, safe="")}/records/'
                f'{quote(record_type, safe="")}/{quote(key, safe="")}/delete')
        return cloud_api_request(config, path, 'POST', {
            'event_id': str(uuid.uuid4()),
            'expected_version': int(cloud.get('version') or 0),
            'occurred_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'source': 'embedded_desktop',
        }, self._token)

    def _sync_records(self, config, dataset_id, cloud_records, role):
        local_map = _embedded_local_records()
        cloud_map = {
            (str(item.get('record_type') or ''), str(item.get('record_key') or '')): item
            for item in cloud_records
            if item.get('record_type') in {'day', 'month', 'global'} and item.get('record_key')
        }
        baselines_by_dataset = config.setdefault('embedded_baselines', {})
        baseline = baselines_by_dataset.get(dataset_id)
        switching = str(config.get('embedded_last_dataset_id') or '') not in ('', dataset_id)
        if not isinstance(baseline, dict):
            baseline = {}

        active_cloud = [item for item in cloud_records if not item.get('is_deleted')]
        if switching:
            _embedded_apply_cloud_records(cloud_records, replace_all=True)
            local_map = _embedded_local_records()
            baselines_by_dataset[dataset_id] = self._build_baseline(local_map, cloud_map)
            config['embedded_last_dataset_id'] = dataset_id
            config['embedded_baselines'] = baselines_by_dataset
            save_embedded_sync_config(config)
            return []
        if not baseline:
            if active_cloud or switching or not local_map:
                _embedded_apply_cloud_records(cloud_records, replace_all=True)
            elif role in {'admin', 'editor', 'entry'} or self.snapshot().get('temporary_permissions'):
                for local in local_map.values():
                    identity = (local['record_type'], local['record_key'])
                    if self._effective_role(role, dataset_id, identity) in {'admin', 'editor', 'entry'}:
                        self._put_local(config, dataset_id, local, None, 0)
                cloud_records = self._fetch_cloud_records(config, dataset_id)
                cloud_map = {
                    (str(item.get('record_type') or ''), str(item.get('record_key') or '')): item
                    for item in cloud_records if item.get('record_key')
                }
            local_map = _embedded_local_records()
            baseline = self._build_baseline(local_map, cloud_map)
            baselines_by_dataset[dataset_id] = baseline
            config['embedded_last_dataset_id'] = dataset_id
            config['embedded_baselines'] = baselines_by_dataset
            save_embedded_sync_config(config)
            return []

        apply_from_cloud, conflicts, pushed = [], [], False
        identities = set(local_map) | set(cloud_map) | {
            tuple(key.split('\u0000', 1)) for key in baseline if '\u0000' in key
        }
        for identity in sorted(identities):
            local, cloud = local_map.get(identity), cloud_map.get(identity)
            key_text = '\u0000'.join(identity)
            previous = baseline.get(key_text, {})
            local_hash = local.get('checksum') if local else None
            cloud_hash = self._cloud_marker(cloud)
            local_changed = local_hash != previous.get('local_hash')
            cloud_changed = cloud_hash != previous.get('cloud_hash')
            if local_changed and cloud_changed:
                if local and cloud and not cloud.get('is_deleted') and local_hash == cloud_hash:
                    continue
                conflicts.append('/'.join(identity))
                continue
            if cloud_changed:
                if cloud:
                    apply_from_cloud.append(cloud)
                continue
            if local_changed:
                record_role = self._effective_role(role, dataset_id, identity)
                if record_role not in {'admin', 'editor', 'entry'}:
                    conflicts.append('/'.join(identity))
                    continue
                if local:
                    self._put_local(config, dataset_id, local, cloud, (cloud or {}).get('version', 0))
                elif cloud and not cloud.get('is_deleted'):
                    self._delete_cloud(config, dataset_id, cloud)
                pushed = True

        if apply_from_cloud:
            _embedded_apply_cloud_records(apply_from_cloud)
        if pushed:
            cloud_records = self._fetch_cloud_records(config, dataset_id)
            cloud_map = {
                (str(item.get('record_type') or ''), str(item.get('record_key') or '')): item
                for item in cloud_records if item.get('record_key')
            }
        local_map = _embedded_local_records()
        fresh = self._build_baseline(local_map, cloud_map)
        for conflict in conflicts:
            identity = tuple(conflict.split('/', 1))
            key_text = '\u0000'.join(identity)
            if key_text in baseline:
                fresh[key_text] = baseline[key_text]
        baselines_by_dataset[dataset_id] = fresh
        config['embedded_last_dataset_id'] = dataset_id
        config['embedded_baselines'] = baselines_by_dataset
        save_embedded_sync_config(config)
        return conflicts

    def _build_baseline(self, local_map, cloud_map):
        result = {}
        for identity in set(local_map) | set(cloud_map):
            local, cloud = local_map.get(identity), cloud_map.get(identity)
            result['\u0000'.join(identity)] = {
                'local_hash': local.get('checksum') if local else None,
                'cloud_hash': self._cloud_marker(cloud),
                'cloud_version': int((cloud or {}).get('version') or 0),
            }
        return result

    def _assert_clean_for_name_correction(self, config, dataset_id):
        baseline = (config.get('embedded_baselines') or {}).get(dataset_id)
        local = _embedded_local_records()
        if not isinstance(baseline, dict) or (local and not baseline):
            raise CloudSyncError('请先等待账本同步完成，再进行品名更正。')
        identities = set(local) | {tuple(key.split('\u0000', 1)) for key in baseline if '\u0000' in key}
        if any((local.get(identity) or {}).get('checksum') != baseline.get('\u0000'.join(identity), {}).get('local_hash') for identity in identities):
            raise CloudSyncError('存在尚未同步的本地更改，请先完成同步后再更正品名。')
        if any(_file_signature(path) != signature for path, signature in list(USER_MIRROR_SIGNATURES.items())):
            raise CloudSyncError('用户 Excel 有尚未同步的更改，请先完成读取与同步后再更正品名。')
        if self.snapshot().get('conflicts'):
            raise CloudSyncError('账本存在同步冲突，请先处理冲突。')

    def _correction_context(self, expected_dataset, apply=False):
        if not self.snapshot().get('connected'):
            raise CloudSyncError('品名更正需要在线连接，离线时不能进行全局更正。')
        config = load_embedded_sync_config(); self._login(config)
        dataset_id = self._current_dataset_id(config)
        if str(dataset_id) != str(expected_dataset):
            raise CloudSyncError('当前账本已改变，请关闭窗口后重新预览。')
        role = str(self.snapshot().get('role') or '')
        if role not in ({'admin'} if apply else {'admin', 'editor'}):
            raise CloudSyncError('仅管理员可执行品名更正；修改权限账号可以预览。')
        self._assert_clean_for_name_correction(config, dataset_id)
        return config, dataset_id

    def preview_inventory_name_correction(self, fields, expected_dataset):
        with self._transaction_lock:
            config, dataset_id = self._correction_context(expected_dataset)
            return cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/inventory/name-corrections/preview', 'POST', fields, self._token, timeout=60)

    def _pull_after_name_correction(self, config, dataset_id, records=None):
        records = self._fetch_cloud_records(config, dataset_id) if records is None else records
        _embedded_apply_cloud_records(records, replace_all=True)
        sync_internal_to_user_excels(update_baseline=True)
        local = _embedded_local_records()
        cloud = {(str(row.get('record_type')), str(row.get('record_key'))):row for row in records if row.get('record_key')}
        config.setdefault('embedded_baselines', {})[dataset_id] = self._build_baseline(local, cloud)
        config['embedded_last_dataset_id'] = dataset_id
        config.pop('name_correction_pending_pull', None)
        save_embedded_sync_config(config)
        self._set_state(error='', conflicts=[], syncing=False, connected=True, last_sync_at=datetime.now().strftime('%H:%M:%S'))

    def apply_inventory_name_correction(self, payload, expected_dataset):
        # The same lock guards the ordinary sync cycle. No per-record upload may
        # run between the server transaction and the mandatory full pull.
        with self._transaction_lock:
            config, dataset_id = self._correction_context(expected_dataset, apply=True)
            config['name_correction_pending_pull'] = dataset_id
            save_embedded_sync_config(config)
            try:
                result = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/inventory/name-corrections/apply', 'POST', payload, self._token, timeout=90)
                self._pull_after_name_correction(config, dataset_id)
                return result
            except Exception:
                # A timeout can follow a committed transaction. Persist recovery
                # before sending, and force a pull before any later upload.
                self._set_state(connected=False, syncing=False, error='品名更正尚未完成本地刷新，等待重新读取云端账本。')
                self.wake()
                raise

    def _cycle(self):
        with self._transaction_lock:
            return self._cycle_unlocked()

    def _cycle_unlocked(self):
        config = load_embedded_sync_config()
        configured = bool(config.get('enabled', True) and config.get('api_url')
                          and config.get('username') and config.get('password'))
        if not configured:
            self._token = ''
            self._set_state(configured=False, connected=False, syncing=False, error='请先配置 API、账号和密码。')
            return
        was_connected = bool(self.snapshot().get('connected'))
        self._set_state(
            configured=True,
            # Do not turn an established connection off merely because the
            # next background poll has started.  A real exception in _run is
            # the only condition that changes it to disconnected.
            connected=was_connected,
            internet_connected=True,
            syncing=True,
            error='' if not was_connected else str(self.snapshot().get('error') or ''),
        )
        self._login(config)
        self._refresh_datasets(config)
        allowed_ids = [str(item.get('id') or '') for item in self._datasets]
        dataset_id = str(config.get('dataset_id') or '')
        if dataset_id not in allowed_ids:
            default = next((item for item in self._datasets if item.get('is_default')), self._datasets[0])
            dataset_id = str(default.get('id') or '')
            config['dataset_id'] = dataset_id
            save_embedded_sync_config(config)
        role = str(self.snapshot().get('role') or 'viewer')
        fetch_started = time.perf_counter()
        records = self._fetch_cloud_records(config, dataset_id)
        fetch_seconds = max(time.perf_counter() - fetch_started, 0.001)
        try:
            received_bytes = len(exact_json_dumps(records, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        except (TypeError, ValueError):
            received_bytes = 0
        if config.get('name_correction_pending_pull') == dataset_id:
            self._pull_after_name_correction(config, dataset_id, records); conflicts = []
        else:
            conflicts = self._sync_records(config, dataset_id, records, role)
        if role == 'entry':
            # Run on the sync worker, never from the GUI countdown timer.
            try:
                windows = cloud_api_request(config, f'/datasets/{quote(dataset_id, safe="")}/entry-windows', token=self._token)
                self._set_state(customer_entry_windows={str(row.get('record_key')): row.get('customer_fields', {}) for row in windows if isinstance(row, dict) and row.get('record_type') == 'day'}, customer_windows_dataset=dataset_id)
            except CloudSyncError:
                pass  # Older servers have no customer clocks; server still validates saves.
        self._set_state(
            configured=True, connected=True, datasets=list(self._datasets),
            dataset_id=dataset_id, conflicts=conflicts,
            last_sync_at=datetime.now().strftime('%H:%M:%S'),
            syncing=False,
            latency_ms=round(fetch_seconds * 1000),
            download_kbps=round(received_bytes / 1024 / fetch_seconds, 1),
            error=('检测到同步冲突：' + '、'.join(conflicts[:3])) if conflicts else '',
        )


class CloudSettingsDialog(QDialog):
    def __init__(self, parent=None, require_login=False):
        super().__init__(parent)
        self.require_login = bool(require_login)
        self.offline_requested = False
        self.setWindowTitle('登录餐饮成本管家' if self.require_login else '网站连接设置')
        self.resize(560, 330)
        self.config = load_embedded_sync_config()
        self.datasets = list(self.config.get('datasets_cache') or [])
        self._tested_signature = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.api_edit = QLineEdit(str(self.config.get('api_url') or ''))
        self.api_edit.setPlaceholderText('例如：https://example.com')
        self.username_edit = QLineEdit(str(self.config.get('username') or ''))
        self.password_edit = QLineEdit('' if self.require_login else str(self.config.get('password') or ''))
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText('请输入密码' if self.require_login else '')
        self.dataset_combo = QComboBox()
        form.addRow('API 地址', self.api_edit)
        form.addRow('用户名', self.username_edit)
        form.addRow('密码', self.password_edit)
        form.addRow('使用账本', self.dataset_combo)
        layout.addLayout(form)
        self.result_label = QLabel(
            '距离上次关闭已超过两小时，请重新输入密码。账号有多份账本时，可在此选择。'
            if self.require_login else
            '账号有多份账本时，可在此选择。连接信息仅保存在本机。'
        )
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        actions = QHBoxLayout()
        self.test_button = QPushButton('测试登录并读取账本')
        cancel = QPushButton('退出软件' if self.require_login else '取消')
        save = QPushButton('保存并开始同步')
        actions.addWidget(self.test_button)
        actions.addStretch()
        if self.require_login:
            offline = QPushButton('离线只读打开')
            offline.clicked.connect(self.open_offline)
            actions.addWidget(offline)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)
        self.test_button.clicked.connect(self.test_connection)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save_and_accept)
        self._render_datasets(str(self.config.get('dataset_id') or ''))

    def open_offline(self):
        self.offline_requested = True
        self.accept()

    def _current_config(self):
        return {
            **self.config,
            'enabled': True,
            'api_url': self.api_edit.text().strip().rstrip('/'),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text(),
        }

    def _render_datasets(self, selected=''):
        self.dataset_combo.clear()
        for item in self.datasets:
            dataset_id = str(item.get('id') or '')
            self.dataset_combo.addItem(str(item.get('name') or dataset_id), dataset_id)
        index = self.dataset_combo.findData(selected)
        if index >= 0:
            self.dataset_combo.setCurrentIndex(index)

    def test_connection(self):
        self.test_button.setEnabled(False)
        self.result_label.setText('正在登录并读取可用账本……')
        QApplication.processEvents()
        try:
            config = self._current_config()
            login = cloud_api_request(config, '/auth/login', 'POST', {
                'username': config['username'], 'password': config['password'],
            })
            token = str(login.get('access_token') or '')
            datasets = cloud_api_request(config, '/datasets', token=token)
            self.datasets = datasets if isinstance(datasets, list) else list((datasets or {}).get('items') or [])
            if not self.datasets:
                raise CloudSyncError('登录成功，但该账号没有可用账本。')
            self._render_datasets(str(self.config.get('dataset_id') or ''))
            role = str((login.get('user') or {}).get('role') or 'viewer')
            self._tested_signature = (
                config['api_url'], config['username'], config['password']
            )
            self.result_label.setText(f'连接成功：{len(self.datasets)} 份账本，账号权限 {role}。')
        except CloudSyncError as exc:
            self._tested_signature = None
            self.datasets = []
            self._render_datasets()
            self.result_label.setText(str(exc))
        finally:
            self.test_button.setEnabled(True)

    def save_and_accept(self):
        config = self._current_config()
        signature = (config['api_url'], config['username'], config['password'])
        if self._tested_signature != signature:
            self.test_connection()
        dataset_id = str(self.dataset_combo.currentData() or '')
        if not self.datasets or not dataset_id:
            return
        config = self._current_config()
        config['dataset_id'] = dataset_id
        config['datasets_cache'] = self.datasets
        config.pop('last_closed_at', None)
        save_embedded_sync_config(config)
        self.accept()


class CloudWorkbookDialog(QDialog):
    """Admin-only workbook actions exposed by the unified desktop program."""

    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.setWindowTitle('管理员 Excel 操作')
        self.resize(560, 300)
        layout = QVBoxLayout(self)
        intro = QLabel(
            '选择一份 .xlsx 后上传到当前云端账本。合并会累加金额、数量和明细，'
            '保留原账本单价；替换会按提示覆盖对应范围。'
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.year_edit = QLineEdit(str(datetime.now().year))
        self.year_edit.setValidator(QIntValidator(2000, 2200, self))
        form.addRow('用户 Excel 年份', self.year_edit)
        layout.addLayout(form)
        self.result_label = QLabel('请先确认云端已连接；操作期间不会关闭本地数据。')
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        actions = QGridLayout()
        self.merge_button = QPushButton('上传并合并用户 Excel')
        self.replace_user_button = QPushButton('上传并替换该年用户 Excel')
        self.replace_internal_button = QPushButton('上传并替换当前账本内部 Excel')
        actions.addWidget(self.merge_button, 0, 0)
        actions.addWidget(self.replace_user_button, 0, 1)
        actions.addWidget(self.replace_internal_button, 1, 0, 1, 2)
        layout.addLayout(actions)
        close_button = QPushButton('关闭')
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, alignment=Qt.AlignRight)
        self.merge_button.clicked.connect(lambda: self._choose_and_upload('user-merge', True))
        self.replace_user_button.clicked.connect(lambda: self._choose_and_upload('user', True))
        self.replace_internal_button.clicked.connect(lambda: self._choose_and_upload('internal', False))

    def _choose_and_upload(self, operation, needs_year):
        if str(self.worker.snapshot().get('role') or '') != 'admin':
            QMessageBox.warning(self, '权限不足', '只有管理员账号可以上传或合并 Excel。')
            return
        year = None
        if needs_year:
            try:
                year = int(self.year_edit.text())
            except ValueError:
                QMessageBox.warning(self, '年份错误', '请输入 2000 至 2200 之间的年份。')
                return
            if not 2000 <= year <= 2200:
                QMessageBox.warning(self, '年份错误', '请输入 2000 至 2200 之间的年份。')
                return
        title = '选择要上传的用户 Excel' if needs_year else '选择要替换内部数据的 Excel'
        path, _ = QFileDialog.getOpenFileName(self, title, os.path.expanduser('~'), 'Excel Files (*.xlsx)')
        if not path:
            return
        if operation == 'user' and QMessageBox.question(
            self, '确认替换', f'确定替换 {year} 年用户 Excel 吗？缺少的日期和月份会被删除。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        if operation == 'internal' and QMessageBox.question(
            self, '确认替换', '确定用这份文件整体替换当前云端账本内部数据吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.merge_button.setEnabled(False)
        self.replace_user_button.setEnabled(False)
        self.replace_internal_button.setEnabled(False)
        self.result_label.setText('正在上传并校验 Excel……')
        QApplication.processEvents()
        try:
            result = self.worker.upload_workbook(path, operation, year=year)
            mode = str(result.get('mode') or '完成') if isinstance(result, dict) else '完成'
            self.result_label.setText(f'上传完成：{mode}。同步线程会自动刷新本地数据。')
        except CloudSyncError as exc:
            self.result_label.setText(str(exc))
            QMessageBox.warning(self, '上传失败', str(exc))
        finally:
            self.merge_button.setEnabled(True)
            self.replace_user_button.setEnabled(True)
            self.replace_internal_button.setEnabled(True)


EMBEDDED_SYNC_INSTANCE = None
DESKTOP_OFFLINE_ONLY_SESSION = False


def trigger_embedded_sync_now():
    if EMBEDDED_SYNC_INSTANCE is not None:
        EMBEDDED_SYNC_INSTANCE.wake()


# ===================== 内置云同步结束 =====================


class ExcelAccessError(RuntimeError):
    """Raised when the selected workbook cannot be safely read or written."""


class ExcelFormatError(RuntimeError):
    """Raised when a selected workbook is not a compatible data workbook."""


PERMISSION_RECOVERY_CALLBACK = None


# ===================== 全局防崩溃拦截器 =====================
def global_exception_handler(exc_type, exc_value, exc_tb):
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"【系统拦截到异常】\n{err_msg}")

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Critical)
    if isinstance(exc_value, ExcelAccessError):
        msg_box.setWindowTitle("无法访问 Excel 数据文件")
        msg_box.setText(str(exc_value))
        recover_button = msg_box.addButton("读取或创建用户 Excel（获取访问权限）", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Close)
    elif isinstance(exc_value, ExcelFormatError):
        msg_box.setWindowTitle("Excel 数据文件格式不正确")
        msg_box.setText(str(exc_value))
    else:
        msg_box.setWindowTitle("系统运行异常")
        msg_box.setText("软件遇到了一个意外错误，但已被成功拦截。")
    msg_box.setDetailedText(err_msg)
    msg_box.exec()
    if isinstance(exc_value, ExcelAccessError) and msg_box.clickedButton() is recover_button:
        if callable(PERMISSION_RECOVERY_CALLBACK):
            PERMISSION_RECOVERY_CALLBACK()


sys.excepthook = global_exception_handler


def apply_py_charm_run_style(app):
    """Shared restrained desktop theme, including dialogs and secondary modules."""
    app.setStyle('Fusion')
    app.setFont(QFont('PingFang SC', 12))
    app.setStyleSheet("""
        QWidget { color:#263445; font-size:13px; }
        QMainWindow, QDialog { background:#f5f6f8; }
        QLabel { background:transparent; }
        QPushButton { background:#ffffff; border:1px solid #cbd3dd; border-radius:3px; padding:5px 10px; min-height:22px; }
        QPushButton:hover { background:#eef3f8; border-color:#91a6bb; }
        QPushButton:pressed { background:#e3ebf3; }
        QPushButton:disabled { color:#98a2af; background:#f4f5f7; border-color:#e0e4e9; }
        QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QTextEdit { background:white; border:1px solid #cbd3dd; border-radius:3px; padding:4px 6px; selection-background-color:#dce9f7; selection-color:#223e5b; }
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus { border-color:#47769e; }
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled { background:#f3f5f7; color:#8b96a3; }
        QComboBox::drop-down { border:0; width:20px; }
        QGroupBox { background:#ffffff; border:1px solid #d7dde5; border-radius:3px; margin-top:14px; padding:12px 8px 8px; font-weight:600; }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; color:#34465a; }
        QTableView, QTableWidget, QListWidget { background:#ffffff; alternate-background-color:#f7f9fb; gridline-color:#e0e5eb; border:1px solid #d6dde5; selection-background-color:#dce9f7; selection-color:#203b56; }
        QHeaderView::section { background:#edf1f5; color:#3c4b5d; border:0; border-right:1px solid #d9e0e8; border-bottom:1px solid #cdd6df; padding:7px 9px; font-weight:600; }
        QTableView::item { padding:4px 6px; }
        QTabWidget::pane { background:white; border:1px solid #d6dde5; }
        QTabBar::tab { background:#f1f3f6; border:1px solid #d6dde5; padding:7px 12px; color:#536274; }
        QTabBar::tab:selected { background:white; color:#24527d; border-bottom:2px solid #47769e; }
        QScrollArea { background:transparent; border:0; }
        QScrollBar:vertical { background:#f0f2f5; width:11px; margin:0; }
        QScrollBar::handle:vertical { background:#b9c3ce; border-radius:3px; min-height:28px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QStatusBar { background:#edf1f5; color:#657486; border-top:1px solid #d8dfe7; }
        QListWidget#financeNavigation { border:0; background:#f1f4f7; padding:5px; }
        QListWidget#financeNavigation::item { border-radius:3px; padding:5px 8px; }
        QListWidget#financeNavigation::item:selected { background:#dce7f1; color:#214e75; }
        QTabWidget#financeWorkspace::pane { border:0; background:#f5f6f8; }
    """)


class FinanceWorkspace(QTabWidget):
    """Sidebar presentation while preserving all existing module/tab identities."""
    def __init__(self):
        super().__init__()
        self.setObjectName('financeWorkspace')
        self.tabBar().hide()
        self.navigation = QListWidget()
        self.navigation.setObjectName('financeNavigation')
        self.navigation.setFixedWidth(184)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.navigation.itemClicked.connect(self._open_navigation_item)
        self.currentChanged.connect(self._select_navigation_item)
        self._navigation_ready = False

    def build_navigation(self):
        self._navigation_ready = True
        self.navigation.blockSignals(True)
        self.navigation.clear()
        groups = {0:'经营总览', 2:'日常业务', 7:'库存与分析', 9:'系统管理'}
        for index in range(self.count()):
            if not self.isTabVisible(index): continue
            if index in groups:
                heading = QListWidgetItem(groups[index]); heading.setFlags(Qt.NoItemFlags)
                heading.setForeground(QColor('#788697')); heading.setSizeHint(QSize(160, 32))
                self.navigation.addItem(heading)
            item = QListWidgetItem(self.tabText(index).strip())
            item.setData(Qt.UserRole, index); item.setSizeHint(QSize(160, 36))
            self.navigation.addItem(item)
        self.navigation.blockSignals(False)
        self._select_navigation_item(self.currentIndex())
        return self.navigation

    def _open_navigation_item(self, item):
        index = item.data(Qt.UserRole)
        if index is not None: self.setCurrentIndex(index)

    def _select_navigation_item(self, index):
        self.navigation.blockSignals(True)
        for row in range(self.navigation.count()):
            if self.navigation.item(row).data(Qt.UserRole) == index:
                self.navigation.setCurrentRow(row); break
        self.navigation.blockSignals(False)

    def setTabVisible(self, index, visible):
        changed = self.isTabVisible(index) != visible
        super().setTabVisible(index, visible)
        if changed and self._navigation_ready: self.build_navigation()

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.navigation.setEnabled(enabled)

# ===================== 动态文件存储与配置层 =====================
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".restaurant_finance_config.json")
FILE_PATH = ""  # 当前用户 Excel：用户可以直接打开、查看和备份的年度文件
INTERNAL_FILE_PATH = ""  # 内部 Excel：由软件维护，集中保存所有年度的历史数据
DEFAULT_INTERNAL_EXCEL_FILENAME = "(勿删) 成本管理软件内部数据.xlsx"
# 云端始终只使用这一套主数据集。更换内部 Excel 时，程序会自动把新文件
# 里的本地 dataset_id 归一到此 ID；用户不需要接触或维护 Dataset ID。
FIXED_CLOUD_DATASET_ID = "df31aca7-1c26-44a7-8f9f-638c2a3d98ec"
# 两个主程序共用同一个云同步助手；此版本是接收跨设备整份账套切换请求的管理员端。
MAIN_PROGRAM_ROLE = "unified"
MAIN_PROGRAM_ROLE_LABEL = "餐饮成本管家桌面版"
NETWORK_ACCESS_DECIDED = False
NETWORK_EDIT_ALLOWED = False
# ``initialize_cloud_cache_from_server`` performs a successful authenticated
# request before the main window is created.  Preserve that fact so the new
# window does not briefly report a healthy login as "offline" while its worker
# performs the first background refresh.
DESKTOP_STARTUP_CONNECTION_STATE = {}
REMOTE_REPLACEMENT_REQUEST_ID_KEY = "REMOTE_WORKBOOK_REPLACEMENT_REQUEST_ID"
REMOTE_REPLACEMENT_STATUS_KEY = "REMOTE_WORKBOOK_REPLACEMENT_STATUS"
ACTIVE_USER_EXCEL_YEAR = None

# 店铺显示名称：内部数据字段继续使用稳定的 A店/B店 键，显示名称可自由修改。
STORE_DISPLAY_NAMES = {"A": "A店", "B": "B店"}

def store_display_name(slot):
    return STORE_DISPLAY_NAMES.get(str(slot).upper(), f"{str(slot).upper()}店")

def set_store_display_names(a_name=None, b_name=None):
    a = str(a_name or '').strip()
    b = str(b_name or '').strip()
    if a:
        STORE_DISPLAY_NAMES['A'] = a
    if b:
        STORE_DISPLAY_NAMES['B'] = b

def _store_text(template):
    return str(template).replace('A店', store_display_name('A')).replace('B店', store_display_name('B'))

def apply_store_names_to_widget(root):
    """只改静态 UI 文案；底层字段仍保持 A店/B店，改名不会破坏历史数据。"""
    widgets = [root] + root.findChildren(QWidget) if isinstance(root, QWidget) else []
    for obj in widgets:
        if isinstance(obj, (QLabel, QPushButton, QCheckBox)):
            current = obj.text()
            template = getattr(obj, '_store_name_template', None)
            if template is None and ('A店' in current or 'B店' in current):
                template = current
                obj._store_name_template = template
            if template is not None:
                obj.setText(_store_text(template))
        if isinstance(obj, QGroupBox):
            current = obj.title()
            template = getattr(obj, '_store_title_template', None)
            if template is None and ('A店' in current or 'B店' in current):
                template = current
                obj._store_title_template = template
            if template is not None:
                obj.setTitle(_store_text(template))
        if isinstance(obj, QComboBox):
            templates = getattr(obj, '_store_item_templates', None)
            if templates is None:
                originals = [obj.itemText(i) for i in range(obj.count())]
                if any(('A店' in text or 'B店' in text) for text in originals):
                    templates = originals
                    obj._store_item_templates = templates
            if templates is not None and len(templates) == obj.count():
                current_index = obj.currentIndex()
                for i, template in enumerate(templates):
                    obj.setItemText(i, _store_text(template))
                obj.setCurrentIndex(current_index)
        if isinstance(obj, QTableWidget):
            templates = getattr(obj, '_store_header_templates', None)
            if templates is None:
                originals = [obj.horizontalHeaderItem(i).text() if obj.horizontalHeaderItem(i) else '' for i in range(obj.columnCount())]
                if any(('A店' in text or 'B店' in text) for text in originals):
                    templates = originals
                    obj._store_header_templates = templates
            if templates is not None and len(templates) == obj.columnCount():
                obj.setHorizontalHeaderLabels([_store_text(text) for text in templates])


def require_network_edit():
    if NETWORK_ACCESS_DECIDED and not NETWORK_EDIT_ALLOWED:
        raise ExcelAccessError('当前没有可用的云端连接，软件处于只读模式。网络恢复后才能保存修改。')
ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID  # 用户 Excel 与内部 Excel 共用的固定身份
USER_META_SHEET = '__app_meta'
USER_META_COLUMNS = ['key', 'value']

# 第4阶段：内部 Excel 是唯一的本地事实来源；年度 Excel 只是自动生成的镜像。
APP_BASELINE_RECORD_HASHES = {}
APP_BASELINE_SHEET_FRAMES = {}
USER_MIRROR_SIGNATURES = {}
LAST_INTERNAL_MTIME_NS = None

# 这些表仍沿用旧版文件格式，确保已有账本无需迁移即可继续使用。
STANDARD_SHEET_COLUMNS = {
    'daily': [
        # 旧版 12 列保持原顺序，避免已有 Excel 的列位置被打乱。
        '日期', '收益', '新客人数量', '总客人数', '食材成本', '食材明细',
        '佐料成本', '佐料明细', '水电', '其他', '其他明细', '当日备注',
        # 分店/支付及微信账单审计字段追加在后面。
        '总现金', 'A店现金', 'B店现金', '总线上',
        'A店微信增加', 'A店微信自动', 'A店微信覆盖', 'A店支付宝增加', 'A店支付宝覆盖',
        'B店微信增加', 'B店微信自动', 'B店微信覆盖', 'B店支付宝增加', 'B店支付宝覆盖',
        'A店收入', 'B店收入', '学生外卖', 'A店外卖', 'B店外卖', '手续费',
        'A店微信支付金额', 'A店微信退款金额', 'A店微信支付笔数', 'A店微信退款笔数',
        'B店微信支付金额', 'B店微信退款金额', 'B店微信支付笔数', 'B店微信退款笔数',
        '微信账单日期', '微信账单同步时间', '微信账单口径', '微信账单SHA1', '微信账单未归属笔数', '微信账单强制更新',
    ],
    'monthly_fixed': [
        '月份', '人工总额', '房租总额', '水费支出', '电费支出', '水电费',
        '实际使用水费', '实际使用电费', '煤气费', '其它固定成本', '月度备注',
        '预计水费', '预计电费', '预计煤气费',
    ],
    # 旧工作簿没有“计入可用余额”列时，读取层会按 True 兼容，保持旧现金口径。
    'fixed_expenses': ['日期', '类别', '明细', '金额', '计入可用余额'],
    'fixed_categories': ['类别名称'],
    'ingredients': ['词条名称', '分类'],
    'dishes': ['日期', '菜品明细', '菜品数据', '总成本', '备注'],
}
DATE_SHEET_COLUMNS = {
    'daily': '日期',
    'fixed_expenses': '日期',
    'dishes': '日期',
}


def _read_path_config():
    """Read configuration defensively, including configuration written by older versions."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_path_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_saved_path():
    data = _read_path_config()
    # FILE_PATH is kept for backward compatibility with the previous release.
    path = data.get("USER_EXCEL_PATH") or data.get("FILE_PATH") or ""
    # Do not call exists() here: on macOS a TCC/sandbox denial can look like a missing
    # path.  The startup validator below distinguishes a real missing file from one
    # that must be reselected to recover access.
    return str(path).strip() or None


def _default_internal_excel_path():
    """Return the new default internal workbook path in Downloads."""
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(downloads_dir):
        downloads_dir = os.path.expanduser("~")
    return os.path.join(downloads_dir, DEFAULT_INTERNAL_EXCEL_FILENAME)


def _legacy_default_internal_excel_path():
    """Return the old app-owned default path for safe one-time migration."""
    app_data_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not app_data_dir:
        app_data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "餐饮成本管家")
    return os.path.join(app_data_dir, "餐饮成本管家_内部数据.xlsx")


def get_internal_excel_path_from_config():
    path = _read_path_config().get("INTERNAL_FILE_PATH", "")
    if path:
        configured_path = os.path.abspath(os.path.expanduser(path))
        legacy_path = os.path.abspath(_legacy_default_internal_excel_path())
        # The previous release stored its untouched default under Application
        # Support. Move/copy that legacy default into Downloads, but preserve any
        # renamed or explicitly moved internal workbook exactly as the user chose.
        if configured_path == legacy_path:
            preferred_path = _default_internal_excel_path()
            if os.path.exists(preferred_path):
                return preferred_path
            if os.path.exists(configured_path):
                try:
                    os.makedirs(os.path.dirname(preferred_path), exist_ok=True)
                    shutil.copy2(configured_path, preferred_path)
                    return preferred_path
                except OSError:
                    return configured_path
            return preferred_path
        return configured_path

    return _default_internal_excel_path()


def save_path_config(path, active_year=None, internal_path=None):
    """Persist the current user file plus the annual file map without losing old settings."""
    data = _read_path_config()
    previous_internal_path = str(data.get("INTERNAL_FILE_PATH") or "").strip()
    path = os.path.abspath(os.path.expanduser(str(path))) if path else ""
    if internal_path is None:
        internal_path = INTERNAL_FILE_PATH or previous_internal_path or get_internal_excel_path_from_config()
    internal_path = os.path.abspath(os.path.expanduser(str(internal_path))) if internal_path else ""

    year_map = data.get("YEARLY_USER_EXCEL_PATHS", {})
    if not isinstance(year_map, dict):
        year_map = {}
    if active_year is not None and path:
        year_map[str(int(active_year))] = path

    data.update({
        "FILE_PATH": path,  # allow a prior version of the app to still find the current file
        "USER_EXCEL_PATH": path,
        "INTERNAL_FILE_PATH": internal_path,
        "YEARLY_USER_EXCEL_PATHS": year_map,
    })
    if active_year is not None:
        data["ACTIVE_USER_EXCEL_YEAR"] = int(active_year)
    data["DATASET_ID"] = FIXED_CLOUD_DATASET_ID
    data["CLOUD_DATASET_ID"] = FIXED_CLOUD_DATASET_ID
    data["MAIN_PROGRAM_ROLE"] = MAIN_PROGRAM_ROLE
    data["MAIN_PROGRAM_DIR"] = os.path.dirname(os.path.abspath(__file__))

    # Only mark a source change when the main program actually changes the internal
    # workbook path. Re-saving the same path must not be misreported as a new switch.
    if internal_path and os.path.normcase(os.path.abspath(os.path.expanduser(previous_internal_path or internal_path))) != os.path.normcase(internal_path):
        changed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        request_id = str(uuid.uuid4())
        data["INTERNAL_PATH_CHANGE_SOURCE"] = "main_app"
        data["INTERNAL_PATH_CHANGE_ID"] = request_id
        data["INTERNAL_PATH_CHANGED_AT"] = changed_at
        data["CLOUD_OVERRIDE_REQUEST_ID"] = request_id
        data["CLOUD_OVERRIDE_REQUEST_PATH"] = internal_path
        data["CLOUD_OVERRIDE_REQUEST_MODE"] = "local_over_cloud"
        data["CLOUD_OVERRIDE_REQUEST_STATUS"] = "pending"
        data["CLOUD_OVERRIDE_REQUESTED_AT"] = changed_at
        data["CLOUD_OVERRIDE_REQUEST_MESSAGE"] = "主程序已更换内部 Excel，等待网站内置同步更新云端。"

    _write_path_config(data)


def normalize_excel_path(path):
    """Return an absolute workbook path, or fail before any file operation."""
    path = str(path or '').strip()
    if not path:
        raise ExcelAccessError("尚未选择 Excel 数据文件。请先选择或新建一个数据文件。")
    return os.path.abspath(os.path.expanduser(path))


def _internal_sync_lock_path(path):
    """必须与独立同步助手使用完全相同的跨进程锁文件名。"""
    path = normalize_excel_path(path)
    return os.path.join(
        os.path.dirname(path),
        f'.{os.path.basename(path)}.restaurant-sync.lock',
    )


@contextmanager
def internal_sync_lock(path, timeout=8.0):
    """避免成本软件与云同步助手同时替换内部 Excel。"""
    lock_path = _internal_sync_lock_path(path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, 'a+', encoding='utf-8')
    deadline = time.monotonic() + max(0, float(timeout))
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise ExcelAccessError('网站数据正在同步，请稍等几秒后再保存。')
            time.sleep(0.1)
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _file_signature(path):
    try:
        stat = os.stat(path)
        return stat.st_size, stat.st_mtime_ns
    except OSError:
        return None


def _excel_temporary_lock_exists(path):
    path = normalize_excel_path(path)
    return os.path.exists(os.path.join(os.path.dirname(path), f'~${os.path.basename(path)}'))


def excel_access_message(path, operation="写入", exc=None):
    """Build a useful macOS-specific message without changing system permissions."""
    path = normalize_excel_path(path)
    reason = ""
    if exc and getattr(exc, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
        reason = "\n系统拒绝了该文件的写入访问。"
    elif exc:
        reason = f"\n系统返回：{exc}"

    return (
        f"无法{operation} Excel 数据文件：\n{path}\n\n"
        "请依次检查：\n"
        "1. 完全退出 Microsoft Excel，确保这个文件没有被打开；\n"
        "2. Finder → 显示简介：取消“已锁定”，并确认当前用户拥有“读与写”权限；\n"
        "3. 点击下方“重新选择用户 Excel”，在系统文件选择框中重新选择该文件；"
        "macOS 会在需要时弹出访问授权提示；\n"
        "4. 如果文件在“下载”“桌面”“文稿”、iCloud/OneDrive、U 盘或共享盘，"
        "请在“系统设置 → 隐私与安全性 → 文件与文件夹”中允许本软件访问。"
        f"{reason}"
    )


def ensure_excel_writable(path):
    """Verify both file and containing-directory write access without changing data."""
    path = normalize_excel_path(path)
    parent_dir = os.path.dirname(path) or os.curdir
    if not os.path.exists(path):
        if not os.path.isdir(parent_dir) or not os.access(parent_dir, os.W_OK):
            raise ExcelAccessError(excel_access_message(path, "创建"))
    else:
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError as exc:
            raise ExcelAccessError(excel_access_message(path, "写入", exc)) from exc
        else:
            os.close(fd)

    # The atomic-save implementation replaces a temporary sibling file, so checking
    # only the .xlsx handle is insufficient (and was the old packaged-App failure mode).
    probe = None
    try:
        fd, probe = tempfile.mkstemp(prefix='.restaurant_finance_access_', dir=parent_dir)
        os.close(fd)
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, "写入", exc)) from exc
    finally:
        if probe and os.path.exists(probe):
            try:
                os.remove(probe)
            except OSError:
                pass
    return path


def validate_data_excel(path, require_write=False):
    """Validate a selected workbook without modifying it."""
    path = normalize_excel_path(path)
    if not path.lower().endswith('.xlsx'):
        raise ExcelFormatError("请选择 .xlsx 格式的本软件数据文件。")
    try:
        os.stat(path)
    except OSError as exc:
        if getattr(exc, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise ExcelAccessError(excel_access_message(path, '读取', exc)) from exc
        raise ExcelFormatError(f"找不到所选 Excel 文件：\n{path}")
    if not os.path.isfile(path):
        raise ExcelFormatError(f"所选路径不是 Excel 文件：\n{path}")

    if require_write:
        ensure_excel_writable(path)

    try:
        with pd.ExcelFile(path) as xl:
            if 'daily' not in xl.sheet_names:
                raise ExcelFormatError("所选 Excel 没有“daily”工作表，不是本软件可读取的数据文件。")
        headers = read_excel_exact(path, sheet_name='daily', nrows=0)
        if '日期' not in headers.columns:
            raise ExcelFormatError("所选 Excel 的“daily”工作表缺少“日期”列，无法作为本软件的数据文件。")
    except ExcelFormatError:
        raise
    except PermissionError as exc:
        raise ExcelAccessError(excel_access_message(path, "读取", exc)) from exc
    except Exception as exc:
        raise ExcelFormatError(
            f"无法读取所选 Excel，文件可能已损坏或不是有效的 .xlsx 文件：\n{path}\n\n系统返回：{exc}"
        ) from exc
    return path


def write_excel_sheet(path, sheet_name, df):
    """Atomically replace one sheet while preserving every other sheet in the workbook."""
    path = ensure_excel_writable(path)
    temp_path = None
    try:
        # ExcelWriter otherwise edits the selected file in place.  A sibling temporary
        # workbook makes a failed write much less likely to damage the user's only copy.
        fd, temp_path = tempfile.mkstemp(
            prefix='.restaurant_finance_', suffix='.xlsx', dir=os.path.dirname(path) or os.curdir
        )
        os.close(fd)
        shutil.copy2(path, temp_path)
        with pd.ExcelWriter(temp_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            money_excel_frame(df).to_excel(writer, sheet_name=sheet_name, index=False)
        # Validate the temporary result before replacing the source file.
        with pd.ExcelFile(temp_path):
            pass
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, "写入", exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def read_user_workbook_metadata(path):
    """Read the hidden identity sheet without treating a legacy workbook as invalid."""
    path = normalize_excel_path(path)
    try:
        with pd.ExcelFile(path) as workbook:
            if USER_META_SHEET not in workbook.sheet_names:
                return {}
            frame = read_excel_exact(workbook, sheet_name=USER_META_SHEET)
        if not set(USER_META_COLUMNS).issubset(frame.columns):
            return {}
        return {
            str(row.get('key', '')).strip(): str(row.get('value', '')).strip()
            for _, row in frame.iterrows() if str(row.get('key', '')).strip()
        }
    except Exception:
        # Old user files never had this sheet; a normal data validation still happens
        # before the caller uses the workbook.
        return {}


def write_user_workbook_metadata(path, family_id, user_year):
    """Atomically add/update a veryHidden identity sheet while preserving user sheets."""
    path = ensure_excel_writable(path)
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(
            prefix='.restaurant_finance_meta_', suffix='.xlsx', dir=os.path.dirname(path) or os.curdir
        )
        os.close(fd)
        shutil.copy2(path, temp_path)
        workbook = load_workbook(temp_path)
        if USER_META_SHEET in workbook.sheetnames:
            sheet = workbook[USER_META_SHEET]
            sheet.delete_rows(1, sheet.max_row)
        else:
            sheet = workbook.create_sheet(USER_META_SHEET)
        sheet.append(USER_META_COLUMNS)
        sheet.append(['family_id', str(family_id)])
        sheet.append(['user_year', str(int(user_year))])
        sheet.append(['schema_version', '2'])
        sheet.sheet_state = 'veryHidden'
        workbook.save(temp_path)
        with pd.ExcelFile(temp_path):
            pass
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, '写入用户 Excel 元数据', exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def ensure_user_workbook_metadata(path, user_year, family_id=None):
    metadata = read_user_workbook_metadata(path)
    saved_family_id = metadata.get('family_id', '').strip()
    family_id = saved_family_id or str(family_id or uuid.uuid4())
    saved_year = metadata.get('user_year', '').strip()
    if saved_family_id != family_id or saved_year != str(int(user_year)):
        write_user_workbook_metadata(path, family_id, user_year)
    return family_id


def normalize_date_column(df, column='日期'):
    """Keep dates comparable across Excel date cells and yyyy-MM-dd text cells."""
    clean = df.copy()
    if column not in clean.columns:
        return clean
    raw = clean[column]
    parsed = pd.to_datetime(raw, errors='coerce')
    text = raw.fillna('').astype(str).str.strip()
    normalized = parsed.dt.strftime('%Y-%m-%d')
    clean[column] = normalized.where(parsed.notna(), text)
    return clean


def sort_rows_by_date(df, column='日期'):
    """Stable chronological sorting; blank/invalid dates remain at the end."""
    clean = normalize_date_column(df, column)
    if clean.empty or column not in clean.columns:
        return clean.reset_index(drop=True)
    sort_column = '__data_date_sort__'
    while sort_column in clean.columns:
        sort_column += '_'
    clean[sort_column] = pd.to_datetime(clean[column], errors='coerce')
    return (
        clean.sort_values(sort_column, kind='mergesort', na_position='last')
        .drop(columns=[sort_column])
        .reset_index(drop=True)
    )


def normalize_month_column(df, column='月份'):
    """Keep monthly keys in yyyy-MM form (not yyyy-MM-01) while sorting them."""
    clean = df.copy()
    if column not in clean.columns:
        return clean
    raw = clean[column]
    parsed = pd.to_datetime(raw, errors='coerce')
    text = raw.fillna('').astype(str).str.strip()
    normalized = parsed.dt.strftime('%Y-%m')
    clean[column] = normalized.where(parsed.notna(), text)
    return clean


def sort_rows_by_month(df, column='月份'):
    clean = normalize_month_column(df, column)
    if clean.empty or column not in clean.columns:
        return clean.reset_index(drop=True)
    sort_column = '__month_sort__'
    while sort_column in clean.columns:
        sort_column += '_'
    clean[sort_column] = pd.to_datetime(clean[column] + '-01', errors='coerce')
    return (
        clean.sort_values(sort_column, kind='mergesort', na_position='last')
        .drop(columns=[sort_column])
        .reset_index(drop=True)
    )


def new_standard_sheet_frames():
    """Return independent empty frames for every sheet used by the application."""
    return {name: pd.DataFrame(columns=columns) for name, columns in STANDARD_SHEET_COLUMNS.items()}


def normalize_sheet_frame(sheet_name, df):
    """Normalize old workbooks without discarding user-created extra columns."""
    clean = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if sheet_name == 'ingredients' and '食材名称' in clean.columns and '词条名称' not in clean.columns:
        clean = clean.rename(columns={'食材名称': '词条名称'})
    if sheet_name == 'fixed_expenses' and 'include_cash_balance' in clean.columns:
        # The App's Chinese field is canonical.  Older web payloads could
        # contain a stale English alias which must not override a later App
        # checkbox choice.  Keep the alias only as a legacy fallback, then
        # remove it from both the in-memory data and user Excel mirror.
        alias = clean['include_cash_balance']
        if '计入可用余额' not in clean.columns:
            clean['计入可用余额'] = alias
        else:
            canonical = clean['计入可用余额']
            blank = canonical.isna() | canonical.astype(str).str.strip().str.lower().isin(
                {'', 'nan', 'none'}
            )
            clean.loc[blank, '计入可用余额'] = alias.loc[blank]
        clean = clean.drop(columns=['include_cash_balance'])
    for detail_field in (('食材明细', '佐料明细', '其他明细') if sheet_name == 'daily' else ('菜品数据',) if sheet_name == 'dishes' else ()):
        if detail_field in clean.columns:
            clean[detail_field] = clean[detail_field].map(lambda value: exact_json_dumps(value, ensure_ascii=False) if isinstance(value, list) else value)
    for column in STANDARD_SHEET_COLUMNS.get(sheet_name, []):
        if column not in clean.columns:
            clean[column] = ''
    date_column = DATE_SHEET_COLUMNS.get(sheet_name)
    if date_column:
        clean = normalize_date_column(clean, date_column)
    elif sheet_name == 'monthly_fixed' and '月份' in clean.columns:
        clean['月份'] = clean['月份'].fillna('').astype(str).str.strip()
    return clean.astype(object).fillna('')


def sort_data_workbook(path):
    """Chronologically sort every date/month sheet in a user workbook in place.

    This runs both after an explicit load and at every application startup, which fixes
    the old behavior where only a newly selected workbook was sorted.
    """
    path = validate_data_excel(path, require_write=True)
    counts = {}
    try:
        with pd.ExcelFile(path) as workbook:
            existing_sheets = set(workbook.sheet_names)
        sort_columns = {**DATE_SHEET_COLUMNS, 'monthly_fixed': '月份'}
        for sheet_name, column in sort_columns.items():
            if sheet_name not in existing_sheets:
                continue
            source = read_excel_exact(path, sheet_name=sheet_name)
            ordered = sort_rows_by_month(source, column) if sheet_name == 'monthly_fixed' else sort_rows_by_date(source, column)
            # Always write the canonical order.  It also normalizes mixed Excel/text dates.
            write_excel_sheet(path, sheet_name, ordered)
            counts[sheet_name] = len(ordered)
    except ExcelAccessError:
        raise
    except PermissionError as exc:
        raise ExcelAccessError(excel_access_message(path, "写入", exc)) from exc
    except Exception as exc:
        raise ExcelFormatError(
            f"无法按时间整理所选 Excel：\n{path}\n\n系统返回：{exc}"
        ) from exc
    return counts


def sort_imported_daily_sheet(path):
    """Backward-compatible name used by the existing UI; now sorts all dated sheets."""
    return sort_data_workbook(path).get('daily', 0)


def init_excel_structure(path, overwrite_existing=False):
    """Create missing app sheets safely; never overwrite a bad existing file by accident."""
    path = normalize_excel_path(path)
    standard_sheets = new_standard_sheet_frames()

    def write_new_workbook():
        try:
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                for sheet_name, sheet_df in standard_sheets.items():
                    money_excel_frame(sheet_df).to_excel(writer, sheet_name=sheet_name, index=False)
        except OSError as exc:
            raise ExcelAccessError(excel_access_message(path, "创建", exc)) from exc

    if os.path.exists(path):
        ensure_excel_writable(path)
        try:
            with pd.ExcelFile(path) as xl:
                existing_sheets = list(xl.sheet_names)
        except PermissionError as exc:
            raise ExcelAccessError(excel_access_message(path, "读取", exc)) from exc
        except Exception as exc:
            if not overwrite_existing:
                raise ExcelFormatError(
                    f"已有 Excel 无法安全读取，因此软件没有改动它：\n{path}\n\n系统返回：{exc}"
                ) from exc
            write_new_workbook()
            return

        missing_sheets = [name for name in standard_sheets if name not in existing_sheets]
        if missing_sheets:
            try:
                with pd.ExcelWriter(path, engine='openpyxl', mode='a', if_sheet_exists='error') as writer:
                    for sheet_name in missing_sheets:
                        money_excel_frame(standard_sheets[sheet_name]).to_excel(writer, sheet_name=sheet_name, index=False)
            except OSError as exc:
                raise ExcelAccessError(excel_access_message(path, "写入", exc)) from exc
    else:
        ensure_excel_writable(path)
        write_new_workbook()


# ===================== 用户 Excel / 内部 Excel 同步层 =====================
# 内部文件故意使用紧凑 JSON 记录，而不是给用户再复制一份可编辑的账本：
# 每一条日记录包含该日所有有关的 sheet 行，因而能真正做到“某天不对应就整天覆盖”。
INTERNAL_DAY_COLUMNS = ['dataset_id', '日期', 'payload_json', 'sha256']
INTERNAL_MONTH_COLUMNS = ['dataset_id', '月份', 'payload_json', 'sha256']
INTERNAL_GLOBAL_COLUMNS = ['dataset_id', '记录类型', 'payload_json', 'sha256']
INTERNAL_META_COLUMNS = ['dataset_id', 'schema_version', 'last_synced_at']
INTERNAL_AUDIT_COLUMNS = ['dataset_id', 'audit_id', 'created_at', 'payload_json', 'sha256']
INTERNAL_INFO_SHEET = '内部数据说明'
INTERNAL_AUDIT_PREFIX = 'audit/'
INTERNAL_AUDIT_RETENTION_DAYS = 366
INTERNAL_AUDIT_MEMORY_CACHE = {}


def _desktop_cloud_role():
    """Return the logged-in cloud role for local audit/permission decisions."""
    try:
        return str(EMBEDDED_SYNC_INSTANCE.snapshot().get('role') or '')
    except Exception:
        return ''


def _desktop_effective_role(day_text='', snapshot=None):
    """Return the permanent or currently active scheduled role for a day."""
    try:
        snapshot = snapshot or EMBEDDED_SYNC_INSTANCE.snapshot()
    except Exception:
        snapshot = snapshot or {}
    role = str(snapshot.get('role') or '')
    if role in {'admin', 'editor'} or not day_text:
        return role
    dataset_id = str(snapshot.get('dataset_id') or '')
    day_text = str(day_text)[:10].replace('/', '-')
    rank = {'viewer': 0, 'entry': 1, 'editor': 2, 'admin': 3}
    best = role if role in rank else 'viewer'
    now = datetime.now().astimezone()
    for grant in snapshot.get('temporary_permissions') or []:
        if str(grant.get('dataset_id') or '') != dataset_id:
            continue
        try:
            starts = datetime.fromisoformat(str(grant.get('starts_at') or '').replace('Z', '+00:00'))
            ends = datetime.fromisoformat(str(grant.get('ends_at') or '').replace('Z', '+00:00'))
            if starts.tzinfo is None:
                starts = starts.astimezone()
            if ends.tzinfo is None:
                ends = ends.astimezone()
        except (TypeError, ValueError):
            continue
        grant_role = str(grant.get('permission_role') or '')
        if (starts <= now < ends
                and str(grant.get('business_start_date') or '') <= day_text
                <= str(grant.get('business_end_date') or '')
                and rank.get(grant_role, 0) > rank.get(best, 0)):
            best = grant_role
    return best


def _default_internal_frames():
    return {
        INTERNAL_INFO_SHEET: pd.DataFrame([{
            '项目': '餐饮成本管家内部数据',
            '说明': '本文件是本地唯一数据来源；各年度 Excel 由它自动生成。请不要手动编辑或删除。',
        }]),
        '__day_records': pd.DataFrame(columns=INTERNAL_DAY_COLUMNS),
        '__month_records': pd.DataFrame(columns=INTERNAL_MONTH_COLUMNS),
        '__global_records': pd.DataFrame(columns=INTERNAL_GLOBAL_COLUMNS),
        # Server audit rows are cached only in this hidden, internal sheet.
        # It is not a normal user-workbook sheet and is never synchronised as
        # a business record.
        '__audit_records': pd.DataFrame(columns=INTERNAL_AUDIT_COLUMNS),
        '__meta': pd.DataFrame(columns=INTERNAL_META_COLUMNS),
    }


def _json_value(value):
    """Convert pandas/openpyxl scalar values to deterministic JSON-safe values."""
    if value is None:
        return ''
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, float):
        return '' if pd.isna(value) else value
    if isinstance(value, (int, bool, str)):
        return value
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'item'):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    return str(value)


def _canonical_records(frame):
    records = []
    for record in frame.to_dict(orient='records'):
        records.append({str(key): _json_value(value) for key, value in record.items()})
    return sorted(
        records,
        key=lambda item: exact_json_dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
    )


def _payload_and_hash(payload):
    raw = exact_json_dumps(money_payload(payload), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return raw, hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _internal_payload_for_identity(frames, dataset_id, identity):
    """读取一条内部业务记录；修改日志用它保存修改前后的完整数据。"""
    record_type, key = identity
    mapping = {
        'day': ('__day_records', '日期'),
        'month': ('__month_records', '月份'),
        'global': ('__global_records', '记录类型'),
    }
    sheet_name, key_column = mapping[record_type]
    frame = frames.get(sheet_name, pd.DataFrame())
    if not {'dataset_id', key_column, 'payload_json'}.issubset(frame.columns):
        return None
    rows = frame[
        (frame['dataset_id'].astype(str) == str(dataset_id))
        & (frame[key_column].astype(str) == str(key))
    ]
    if rows.empty:
        return None
    return _decode_internal_payload(rows.iloc[-1].get('payload_json', ''), f'{record_type}/{key}')


def _prune_internal_audit_records(frames, dataset_id, now=None):
    """修改日志只保留最近 366 天；同步助手会把这些删除同步到云端。"""
    now = (now or datetime.now().astimezone()).astimezone()
    cutoff = now - timedelta(days=INTERNAL_AUDIT_RETENTION_DAYS)
    frame = frames.get('__global_records', pd.DataFrame()).copy()
    if frame.empty or '记录类型' not in frame.columns:
        return []
    expired_indexes = []
    expired_keys = []
    for index, row in frame.iterrows():
        if str(row.get('dataset_id', '')).strip() != str(dataset_id):
            continue
        key = str(row.get('记录类型', '')).strip()
        if not key.startswith(INTERNAL_AUDIT_PREFIX):
            continue
        try:
            payload = exact_json_loads(str(row.get('payload_json', '') or '{}'))
            changed_at = str(payload.get('audit_log', {}).get('changed_at', '')).strip()
            stamp = datetime.fromisoformat(changed_at)
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if stamp.astimezone() < cutoff:
            expired_indexes.append(index)
            expired_keys.append(key)
    if expired_indexes:
        frames['__global_records'] = frame.drop(index=expired_indexes).reset_index(drop=True)
    return expired_keys


def _prune_internal_audit_storage(dataset_id=FIXED_CLOUD_DATASET_ID, now=None):
    """Prune expired audit rows even when the audit screen is only being read.

    Retention must not depend on a later business-data edit.  This helper keeps
    the local baseline and cloud-sync pending marker in step with the physical
    workbook after removing rows during startup/read-only inspection.
    """
    path = normalize_excel_path(INTERNAL_FILE_PATH or '')
    if not path or not os.path.exists(path):
        return []
    expired = []
    try:
        with internal_sync_lock(path):
            frames = _read_internal_frames(path)
            expired = _prune_internal_audit_records(frames, dataset_id, now=now)
            if not expired:
                return []
            meta = frames.get('__meta', pd.DataFrame(columns=INTERNAL_META_COLUMNS))
            meta = meta[meta['dataset_id'].astype(str) != str(dataset_id)].copy()
            frames['__meta'] = pd.concat([
                meta,
                pd.DataFrame([{
                    'dataset_id': dataset_id,
                    'schema_version': 2,
                    'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }]),
            ], ignore_index=True)
            _write_internal_frames(path, frames)
    except (OSError, ExcelAccessError, ExcelFormatError, ValueError):
        return []

    for key in expired:
        APP_BASELINE_RECORD_HASHES.pop(('global', key), None)
    global LAST_INTERNAL_MTIME_NS
    signature = _file_signature(path)
    LAST_INTERNAL_MTIME_NS = signature[1] if signature else None
    _set_internal_sync_pending(True)
    trigger_embedded_sync_now()
    return expired


def _append_internal_audit_records(frames, dataset_id, identities, before_payloads,
                                   source_screen, now=None):
    """把真正发生变化的修改写入内部 Excel；空保存不会调用本函数。"""
    now = (now or datetime.now().astimezone()).astimezone()
    created_keys = []
    for identity in sorted(identities):
        before = before_payloads.get(identity)
        after = _internal_payload_for_identity(frames, dataset_id, identity)
        if before == after:
            continue
        operation = '新增' if before is None else ('删除' if after is None else '修改')
        event_id = str(uuid.uuid4())
        key = f"{INTERNAL_AUDIT_PREFIX}{now.strftime('%Y%m%dT%H%M%S%f')}-{event_id}"
        payload = {'audit_log': {
            'event_id': event_id,
            'changed_at': now.isoformat(timespec='seconds'),
            'retention_days': INTERNAL_AUDIT_RETENTION_DAYS,
            'source': '本地餐饮成本管家',
            'source_screen': str(source_screen),
            'operator': os.environ.get('USER', ''),
            'operation': operation,
            'record_type': identity[0],
            'record_key': identity[1],
            'before_payload': before,
            'after_payload': after,
        }}
        payload_json, digest = _payload_and_hash(payload)
        frames['__global_records'] = _replace_internal_record(
            frames['__global_records'], dataset_id, '记录类型', key,
            payload_json, digest,
        )
        created_keys.append(key)
    return created_keys


def _audit_cache_rows_for_dates(rows, start_date='', end_date=''):
    """Return server audit rows in business-date range, newest first."""
    start_text, end_text = str(start_date or ''), str(end_date or '')
    filtered = []
    for row in rows or []:
        stamp_text = str(row.get('created_at') or row.get('occurred_at') or '')
        try:
            stamp = datetime.fromisoformat(stamp_text.replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
            day_text = stamp.astimezone().strftime('%Y-%m-%d')
        except (TypeError, ValueError):
            day_text = stamp_text[:10]
        if start_text and day_text < start_text:
            continue
        if end_text and day_text > end_text:
            continue
        filtered.append(dict(row))
    return sorted(
        filtered,
        key=lambda item: str(item.get('created_at') or item.get('occurred_at') or ''),
        reverse=True,
    )


def _load_internal_audit_cache(dataset_id):
    """Read audit history only from the dedicated hidden internal Excel sheet."""
    dataset_id = str(dataset_id or FIXED_CLOUD_DATASET_ID)
    if dataset_id in INTERNAL_AUDIT_MEMORY_CACHE:
        return [dict(row) for row in INTERNAL_AUDIT_MEMORY_CACHE[dataset_id]]
    path = normalize_excel_path(INTERNAL_FILE_PATH or '')
    if not path or not os.path.exists(path):
        INTERNAL_AUDIT_MEMORY_CACHE[dataset_id] = []
        return []
    try:
        # This opens one small, hidden cache sheet—not the user Excel and not
        # every business sheet—so reopening “修改记录” stays responsive.
        with internal_sync_lock(path):
            with pd.ExcelFile(path) as workbook:
                frame = (
                    read_excel_exact(workbook, sheet_name='__audit_records')
                    if '__audit_records' in workbook.sheet_names
                    else pd.DataFrame(columns=INTERNAL_AUDIT_COLUMNS)
                )
    except Exception:
        frame = pd.DataFrame(columns=INTERNAL_AUDIT_COLUMNS)
    rows = []
    for record in frame.to_dict(orient='records'):
        if str(record.get('dataset_id') or '').strip() != dataset_id:
            continue
        try:
            payload = exact_json_loads(str(record.get('payload_json') or '{}'))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get('id') or '').strip():
            rows.append(payload)
    rows = _audit_cache_rows_for_dates(rows)
    INTERNAL_AUDIT_MEMORY_CACHE[dataset_id] = rows
    return [dict(row) for row in rows]


def _replace_internal_audit_cache(dataset_id, audit_rows):
    """Atomically cache one dataset's audit rows in internal Excel only."""
    dataset_id = str(dataset_id or FIXED_CLOUD_DATASET_ID)
    normalized_rows, storage_rows = [], []
    for audit in audit_rows or []:
        if not isinstance(audit, dict):
            continue
        audit_id = str(audit.get('id') or '').strip()
        if not audit_id:
            continue
        clean = dict(audit)
        payload_json, digest = _payload_and_hash(clean)
        normalized_rows.append(clean)
        storage_rows.append({
            'dataset_id': dataset_id,
            'audit_id': audit_id,
            'created_at': str(clean.get('created_at') or clean.get('occurred_at') or ''),
            'payload_json': payload_json,
            'sha256': digest,
        })
    normalized_rows = _audit_cache_rows_for_dates(normalized_rows)
    path = normalize_excel_path(INTERNAL_FILE_PATH or '')
    if not path:
        INTERNAL_AUDIT_MEMORY_CACHE[dataset_id] = normalized_rows
        return False
    changed = False
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
        existing = frames.get('__audit_records', pd.DataFrame(columns=INTERNAL_AUDIT_COLUMNS))
        own = existing[existing['dataset_id'].astype(str) == dataset_id]
        old_markers = sorted(
            (str(row.get('audit_id') or ''), str(row.get('sha256') or ''))
            for row in own.to_dict(orient='records')
        )
        new_markers = sorted((row['audit_id'], row['sha256']) for row in storage_rows)
        if old_markers != new_markers:
            preserved = existing[existing['dataset_id'].astype(str) != dataset_id].copy()
            incoming = pd.DataFrame(storage_rows, columns=INTERNAL_AUDIT_COLUMNS)
            frames['__audit_records'] = pd.concat([preserved, incoming], ignore_index=True)
            _write_internal_frames(path, frames)
            changed = True
    INTERNAL_AUDIT_MEMORY_CACHE[dataset_id] = normalized_rows
    return changed


def _delete_internal_audit_cache_row(dataset_id, audit_id):
    dataset_id, audit_id = str(dataset_id or FIXED_CLOUD_DATASET_ID), str(audit_id or '')
    return _replace_internal_audit_cache(
        dataset_id,
        [row for row in _load_internal_audit_cache(dataset_id)
         if str(row.get('id') or '') != audit_id],
    )


def _valid_date_keys(frame, column='日期'):
    if column not in frame.columns:
        return set()
    return {
        str(value).strip() for value in frame[column]
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value).strip())
    }


def _valid_month_keys(frame):
    if '月份' not in frame.columns:
        return set()
    return {
        str(value).strip() for value in frame['月份']
        if re.fullmatch(r'\d{4}-\d{2}', str(value).strip())
    }


def _read_user_workbook_frames(path):
    """Read a compatible user workbook into normalized frames without modifying it."""
    path = validate_data_excel(path, require_write=False)
    frames = new_standard_sheet_frames()
    try:
        with pd.ExcelFile(path) as workbook:
            sheet_names = set(workbook.sheet_names)
            for sheet_name in STANDARD_SHEET_COLUMNS:
                if sheet_name in sheet_names:
                    frames[sheet_name] = normalize_sheet_frame(
                        sheet_name, read_excel_exact(workbook, sheet_name=sheet_name)
                    )
    except PermissionError as exc:
        raise ExcelAccessError(excel_access_message(path, '读取', exc)) from exc
    except Exception as exc:
        raise ExcelFormatError(f"无法读取用户 Excel：\n{path}\n\n系统返回：{exc}") from exc
    return frames


def _ensure_internal_storage_access(path):
    """Create and probe the app-owned directory before any internal-store write."""
    parent_dir = os.path.dirname(path)
    try:
        os.makedirs(parent_dir, exist_ok=True)
        if os.path.exists(path):
            ensure_excel_writable(path)
        else:
            probe_fd, probe_path = tempfile.mkstemp(prefix='.restaurant_finance_internal_', dir=parent_dir)
            os.close(probe_fd)
            os.remove(probe_path)
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, '创建内部数据文件', exc)) from exc


def _read_internal_frames(path):
    frames = _default_internal_frames()
    if not os.path.exists(path):
        return frames
    try:
        with pd.ExcelFile(path) as workbook:
            sheet_names = set(workbook.sheet_names)
            column_sets = {
                '__day_records': INTERNAL_DAY_COLUMNS,
                '__month_records': INTERNAL_MONTH_COLUMNS,
                '__global_records': INTERNAL_GLOBAL_COLUMNS,
                '__audit_records': INTERNAL_AUDIT_COLUMNS,
                '__meta': INTERNAL_META_COLUMNS,
            }
            for sheet_name, columns in column_sets.items():
                if sheet_name in sheet_names:
                    frame = read_excel_exact(workbook, sheet_name=sheet_name)
                    for column in columns:
                        if column not in frame.columns:
                            frame[column] = ''
                    frames[sheet_name] = frame[columns].astype(object).fillna('')
    except PermissionError as exc:
        raise ExcelAccessError(excel_access_message(path, '读取内部数据文件', exc)) from exc
    except Exception as exc:
        raise ExcelAccessError(
            f"无法读取内部 Excel 数据文件：\n{path}\n\n"
            f"用户 Excel 没有被改动。系统返回：{exc}"
        ) from exc
    _validate_internal_frames_integrity(frames)
    return frames


def _validate_internal_frames_integrity(frames):
    """Reject damaged JSON/checksums before internal data can rebuild annual mirrors."""
    mapping = {
        '__day_records': ('日期', r'\d{4}-\d{2}-\d{2}'),
        '__month_records': ('月份', r'\d{4}-\d{2}'),
        '__global_records': ('记录类型', r'.+'),
    }
    seen = set()
    meta_frame = frames.get('__meta', pd.DataFrame())
    meta_ids = set()
    if 'dataset_id' in meta_frame.columns:
        meta_ids = {
            str(value).strip() for value in meta_frame['dataset_id']
            if str(value).strip() and str(value).strip().lower() not in ('nan', 'none')
        }
    for sheet_name, (key_column, key_pattern) in mapping.items():
        frame = frames.get(sheet_name, pd.DataFrame())
        for row_index, row in frame.iterrows():
            dataset_id = str(row.get('dataset_id', '')).strip()
            key = str(row.get(key_column, '')).strip()
            payload_text = str(row.get('payload_json', '') or '')
            digest = str(row.get('sha256', '')).strip().lower()
            if not any((dataset_id, key, payload_text, digest)):
                continue
            if not meta_ids:
                raise ExcelFormatError('内部 Excel 有业务记录，但 __meta 中没有 dataset_id。')
            if not dataset_id or dataset_id not in meta_ids:
                raise ExcelFormatError(f'内部 Excel 的 {sheet_name} 第 {row_index + 2} 行 dataset_id 无效。')
            if not re.fullmatch(key_pattern, key):
                raise ExcelFormatError(f'内部 Excel 的 {sheet_name} 第 {row_index + 2} 行键值无效。')
            identity = (dataset_id, sheet_name, key)
            if identity in seen:
                raise ExcelFormatError(f'内部 Excel 存在重复记录：{sheet_name}/{key}')
            seen.add(identity)
            # sha256 只是同步助手用于比较内容的内部字段，不再作为阻止启动的门槛。
            # 用户或旧版本改动 Excel 后，直接以实际 payload_json 重新计算；下次保存
            # 内部 Excel 时会自然写回正确值。
            actual = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()
            if digest != actual:
                frame.at[row_index, 'sha256'] = actual
                digest = actual
            try:
                payload = exact_json_loads(payload_text)
            except (TypeError, ValueError) as exc:
                raise ExcelFormatError(f'内部 Excel 的 {sheet_name}/{key} JSON 已损坏。') from exc
            if not isinstance(payload, dict):
                raise ExcelFormatError(f'内部 Excel 的 {sheet_name}/{key} payload 必须是对象。')


def validate_internal_excel(path, require_write=False):
    """Validate an existing compact internal workbook without changing its name."""
    path = normalize_excel_path(path)
    try:
        os.stat(path)
    except OSError as exc:
        if getattr(exc, 'errno', None) in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise ExcelAccessError(excel_access_message(path, '读取内部数据文件', exc)) from exc
        raise ExcelFormatError(f"找不到内部 Excel：\n{path}") from exc
    if not os.path.isfile(path):
        raise ExcelFormatError(f"所选路径不是内部 Excel：\n{path}")
    if require_write:
        ensure_excel_writable(path)
    try:
        with pd.ExcelFile(path) as workbook:
            required = {'__day_records', '__month_records', '__global_records', '__meta'}
            if not required.issubset(set(workbook.sheet_names)):
                raise ExcelFormatError(
                    "所选文件不是本软件的内部 Excel，缺少内部数据工作表。"
                )
    except ExcelFormatError:
        raise
    except PermissionError as exc:
        raise ExcelAccessError(excel_access_message(path, '读取内部数据文件', exc)) from exc
    except Exception as exc:
        raise ExcelFormatError(f"无法读取内部 Excel：\n{path}\n\n系统返回：{exc}") from exc
    return path


def _write_internal_frames(path, frames):
    """Atomically write the internal compact store; its sheets are deliberately hidden."""
    _ensure_internal_storage_access(path)
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix='.restaurant_finance_internal_', suffix='.xlsx',
                                         dir=os.path.dirname(path))
        os.close(fd)
        with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
            for sheet_name, frame in frames.items():
                money_excel_frame(frame).to_excel(writer, sheet_name=sheet_name, index=False)
            for sheet_name in ('__day_records', '__month_records', '__global_records', '__audit_records', '__meta'):
                writer.book[sheet_name].sheet_state = 'veryHidden'
        with pd.ExcelFile(temp_path):
            pass
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, '写入内部数据文件', exc)) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _rebind_internal_dataset_id_unlocked(path, target_dataset_id=FIXED_CLOUD_DATASET_ID):
    """Atomically normalize one valid internal workbook to the fixed cloud Dataset ID.

    The caller must already hold ``internal_sync_lock(path)``. A workbook containing
    multiple independent dataset identities is rejected rather than silently merged.
    """
    path = normalize_excel_path(path)
    target_dataset_id = str(target_dataset_id or FIXED_CLOUD_DATASET_ID).strip()
    try:
        uuid.UUID(target_dataset_id)
    except ValueError as exc:
        raise ExcelFormatError(f'固定 Dataset ID 无效：{target_dataset_id}') from exc

    frames = _read_internal_frames(path)
    existing_ids = _internal_dataset_ids(frames)
    if len(existing_ids) > 1:
        raise ExcelFormatError(
            '所选内部 Excel 同时包含多套 dataset_id，不能自动合并成一个云端数据集。'
        )

    if existing_ids == {target_dataset_id}:
        meta = frames.get('__meta', pd.DataFrame())
        valid_meta = meta[meta.get('dataset_id', pd.Series(dtype=object)).astype(str) == target_dataset_id]
        if len(valid_meta) == 1:
            return False

    for sheet_name in ('__day_records', '__month_records', '__global_records', '__audit_records'):
        frame = frames.get(sheet_name, pd.DataFrame()).copy()
        if 'dataset_id' not in frame.columns:
            frame['dataset_id'] = ''
        if not frame.empty:
            frame.loc[:, 'dataset_id'] = target_dataset_id
        frames[sheet_name] = frame

    old_meta = frames.get('__meta', pd.DataFrame()).copy()
    schema_version = '2'
    last_synced_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not old_meta.empty:
        if 'schema_version' in old_meta.columns:
            values = [str(value).strip() for value in old_meta['schema_version'] if str(value).strip()]
            if values:
                schema_version = values[-1]
        if 'last_synced_at' in old_meta.columns:
            values = [str(value).strip() for value in old_meta['last_synced_at'] if str(value).strip()]
            if values:
                last_synced_at = values[-1]
    frames['__meta'] = pd.DataFrame([{
        'dataset_id': target_dataset_id,
        'schema_version': schema_version,
        'last_synced_at': last_synced_at,
    }], columns=INTERNAL_META_COLUMNS)

    _write_internal_frames(path, frames)
    verified = _read_internal_frames(path)
    if _internal_dataset_ids(verified) != {target_dataset_id}:
        raise ExcelFormatError('内部 Excel 的 Dataset ID 归一化后复核失败。')
    return True


def rebind_internal_dataset_id(path, target_dataset_id=FIXED_CLOUD_DATASET_ID):
    """Lock and normalize an internal workbook to the fixed cloud Dataset ID."""
    path = normalize_excel_path(path)
    with internal_sync_lock(path):
        return _rebind_internal_dataset_id_unlocked(path, target_dataset_id)


def _internal_has_business_records(frames):
    """Return whether an internal workbook contains any actual synchronized record."""
    return any(
        not frames.get(sheet_name, pd.DataFrame()).empty
        for sheet_name in ('__day_records', '__month_records', '__global_records')
    )


def get_dataset_id():
    """Return the one fixed cloud/local dataset identity used by this installation."""
    data = _read_path_config()
    if (
        str(data.get('DATASET_ID', '')).strip() != FIXED_CLOUD_DATASET_ID
        or str(data.get('CLOUD_DATASET_ID', '')).strip() != FIXED_CLOUD_DATASET_ID
    ):
        data['DATASET_ID'] = FIXED_CLOUD_DATASET_ID
        data['CLOUD_DATASET_ID'] = FIXED_CLOUD_DATASET_ID
        _write_path_config(data)
    return FIXED_CLOUD_DATASET_ID


def _set_internal_sync_pending(pending):
    data = _read_path_config()
    data['INTERNAL_SYNC_PENDING'] = bool(pending)
    _write_path_config(data)


def _internal_records_for_key(frame, dataset_id, key_column, key):
    return frame[(frame['dataset_id'] == dataset_id) & (frame[key_column] == key)]


def _replace_internal_record(frame, dataset_id, key_column, key, payload_json=None, digest=None):
    mask = (frame['dataset_id'] == dataset_id) & (frame[key_column] == key)
    frame = frame.loc[~mask].copy()
    if payload_json is not None:
        row = {'dataset_id': dataset_id, key_column: key, 'payload_json': payload_json, 'sha256': digest}
        frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
    return frame


def _user_day_payload(frames, day):
    payload = {}
    for sheet_name, date_column in DATE_SHEET_COLUMNS.items():
        subset = frames[sheet_name][frames[sheet_name][date_column].astype(str) == day]
        payload[sheet_name] = _canonical_records(subset)
    return payload


def _user_month_payload(frames, month):
    subset = frames['monthly_fixed'][frames['monthly_fixed']['月份'].astype(str) == month]
    return {'monthly_fixed': _canonical_records(subset)}


def _import_user_excel_to_internal_unlocked(user_path=None, active_year=None, dataset_id=None, internal_path=None,
                                            tracked_days=None, sync_months=True, sync_globals=True):
    """Explicitly import one user workbook into the internal source of truth.

    第4阶段只在“新建空内部库”或用户主动点击“合并其它年份”时调用。
    正常启动、保存和20秒刷新绝不会让年度 Excel 反向覆盖内部数据。
    """
    user_path = normalize_excel_path(user_path or FILE_PATH)
    internal_path = normalize_excel_path(internal_path or INTERNAL_FILE_PATH or get_internal_excel_path_from_config())
    user_frames = _read_user_workbook_frames(user_path)
    internal_frames = _read_internal_frames(internal_path)
    dataset_id = str(dataset_id or read_user_workbook_metadata(user_path).get('family_id') or get_dataset_id())

    active_year = int(active_year or ACTIVE_USER_EXCEL_YEAR or datetime.now().year)
    explicit_days = None if tracked_days is None else {
        str(day).strip() for day in tracked_days
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(day).strip())
    }
    # A user workbook is authoritative only for its active annual partition.  Older
    # legacy files can contain accidental cross-year rows; they must never make this
    # sync delete a different year's internal history.
    tracked_years = {active_year}
    if explicit_days:
        tracked_years = {int(day[:4]) for day in explicit_days}
    all_user_dates = set()
    for sheet_name, column in DATE_SHEET_COLUMNS.items():
        dates = _valid_date_keys(user_frames[sheet_name], column)
        if explicit_days is None:
            all_user_dates.update(day for day in dates if int(day[:4]) == active_year)
        else:
            all_user_dates.update(day for day in dates if day in explicit_days)
    user_months = {
        month for month in _valid_month_keys(user_frames['monthly_fixed'])
        if int(month[:4]) == active_year
    }
    if not sync_months:
        user_months = set()

    day_frame = internal_frames['__day_records']
    existing_days = {
        str(value) for value in day_frame.loc[day_frame['dataset_id'] == dataset_id, '日期']
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value))
        and ((str(value) in explicit_days) if explicit_days is not None else int(str(value)[:4]) in tracked_years)
    }
    changed_days = 0
    for day in sorted(existing_days | all_user_dates):
        if int(day[:4]) not in tracked_years:
            continue
        if day not in all_user_dates:
            internal_frames['__day_records'] = _replace_internal_record(
                internal_frames['__day_records'], dataset_id, '日期', day
            )
            changed_days += 1
            continue
        payload_json, digest = _payload_and_hash(_user_day_payload(user_frames, day))
        existing = _internal_records_for_key(internal_frames['__day_records'], dataset_id, '日期', day)
        if len(existing) != 1 or str(existing.iloc[0].get('sha256', '')) != digest:
            internal_frames['__day_records'] = _replace_internal_record(
                internal_frames['__day_records'], dataset_id, '日期', day, payload_json, digest
            )
            changed_days += 1

    changed_months = 0
    if sync_months:
        month_frame = internal_frames['__month_records']
        existing_months = {
            str(value) for value in month_frame.loc[month_frame['dataset_id'] == dataset_id, '月份']
            if re.fullmatch(r'\d{4}-\d{2}', str(value)) and int(str(value)[:4]) in tracked_years
        }
        for month in sorted(existing_months | user_months):
            if int(month[:4]) not in tracked_years:
                continue
            if month not in user_months:
                internal_frames['__month_records'] = _replace_internal_record(
                    internal_frames['__month_records'], dataset_id, '月份', month
                )
                changed_months += 1
                continue
            payload_json, digest = _payload_and_hash(_user_month_payload(user_frames, month))
            existing = _internal_records_for_key(internal_frames['__month_records'], dataset_id, '月份', month)
            if len(existing) != 1 or str(existing.iloc[0].get('sha256', '')) != digest:
                internal_frames['__month_records'] = _replace_internal_record(
                    internal_frames['__month_records'], dataset_id, '月份', month, payload_json, digest
                )
                changed_months += 1

    changed_globals = 0
    if sync_globals:
        for record_type in ('ingredients', 'fixed_categories'):
            payload_json, digest = _payload_and_hash({record_type: _canonical_records(user_frames[record_type])})
            existing = _internal_records_for_key(
                internal_frames['__global_records'], dataset_id, '记录类型', record_type
            )
            if len(existing) != 1 or str(existing.iloc[0].get('sha256', '')) != digest:
                internal_frames['__global_records'] = _replace_internal_record(
                    internal_frames['__global_records'], dataset_id, '记录类型', record_type, payload_json, digest
                )
                changed_globals += 1

    meta = internal_frames['__meta']
    meta = meta.loc[meta['dataset_id'] != dataset_id].copy()
    meta = pd.concat([meta, pd.DataFrame([{
        'dataset_id': dataset_id,
        'schema_version': '2',
        'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }])], ignore_index=True)
    internal_frames['__meta'] = meta
    _write_internal_frames(internal_path, internal_frames)
    _set_internal_sync_pending(False)
    return {'days': changed_days, 'months': changed_months, 'globals': changed_globals}


def sync_user_excel_to_internal(user_path=None, active_year=None, dataset_id=None, internal_path=None,
                                tracked_days=None, sync_months=True, sync_globals=True):
    """兼容旧调用名，但现在仅表示一次明确的导入操作。"""
    target_internal = normalize_excel_path(
        internal_path or INTERNAL_FILE_PATH or get_internal_excel_path_from_config()
    )
    with internal_sync_lock(target_internal):
        return _import_user_excel_to_internal_unlocked(
            user_path,
            active_year,
            dataset_id,
            target_internal,
            tracked_days,
            sync_months,
            sync_globals,
        )


def _write_explicit_internal_day_payloads_unlocked(day_payloads, dataset_id, internal_path):
    """Write selected day payloads without touching other years or month records."""
    internal_frames = _read_internal_frames(internal_path)
    changed_days = 0
    for day in sorted(day_payloads):
        payload_json, digest = _payload_and_hash(day_payloads[day])
        existing = _internal_records_for_key(
            internal_frames['__day_records'], dataset_id, '日期', day
        )
        if len(existing) != 1 or str(existing.iloc[0].get('sha256', '')) != digest:
            internal_frames['__day_records'] = _replace_internal_record(
                internal_frames['__day_records'], dataset_id, '日期', day, payload_json, digest
            )
            changed_days += 1

    meta = internal_frames['__meta']
    meta = meta.loc[meta['dataset_id'] != dataset_id].copy()
    meta = pd.concat([meta, pd.DataFrame([{
        'dataset_id': dataset_id,
        'schema_version': '2',
        'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }])], ignore_index=True)
    internal_frames['__meta'] = meta
    _write_internal_frames(internal_path, internal_frames)
    _set_internal_sync_pending(False)
    return changed_days


def _write_explicit_internal_day_payloads(day_payloads, dataset_id, internal_path):
    internal_path = normalize_excel_path(internal_path)
    with internal_sync_lock(internal_path):
        return _write_explicit_internal_day_payloads_unlocked(
            day_payloads, dataset_id, internal_path
        )


def _internal_dataset_ids(frames):
    """Return dataset identities present in any internal record table."""
    dataset_ids = set()
    for sheet_name in ('__day_records', '__month_records', '__global_records', '__meta'):
        frame = frames.get(sheet_name, pd.DataFrame())
        if 'dataset_id' not in frame.columns:
            continue
        for value in frame['dataset_id']:
            dataset_id = str(value).strip()
            if dataset_id and dataset_id.lower() not in ('nan', 'none'):
                dataset_ids.add(dataset_id)
    return dataset_ids


def _internal_years_for_dataset(frames, dataset_id):
    """Find all annual user workbooks represented by one internal dataset."""
    years = set()
    day_frame = frames.get('__day_records', pd.DataFrame())
    if {'dataset_id', '日期'}.issubset(day_frame.columns):
        for _, row in day_frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != dataset_id:
                continue
            day = str(row.get('日期', '')).strip()
            if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', day):
                years.add(int(day[:4]))

    month_frame = frames.get('__month_records', pd.DataFrame())
    if {'dataset_id', '月份'}.issubset(month_frame.columns):
        for _, row in month_frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != dataset_id:
                continue
            month = str(row.get('月份', '')).strip()
            if re.fullmatch(r'20\d{2}-\d{2}', month):
                years.add(int(month[:4]))
    return sorted(years)


def _decode_internal_payload(payload_text, context):
    """Decode one compact internal JSON payload with a useful recovery error."""
    try:
        payload = exact_json_loads(str(payload_text or '{}'))
    except (TypeError, ValueError) as exc:
        raise ExcelFormatError(f"内部 Excel 的{context}记录无法恢复，JSON 数据已损坏。") from exc
    if not isinstance(payload, dict):
        raise ExcelFormatError(f"内部 Excel 的{context}记录格式不正确，无法恢复用户 Excel。")
    return payload


def _restored_user_frames_for_year(internal_frames, dataset_id, year):
    """Rebuild one normal user workbook from the compact internal records."""
    collected = {sheet_name: [] for sheet_name in STANDARD_SHEET_COLUMNS}
    year_text = str(int(year))

    day_frame = internal_frames.get('__day_records', pd.DataFrame())
    if {'dataset_id', '日期', 'payload_json'}.issubset(day_frame.columns):
        for _, row in day_frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != dataset_id:
                continue
            day = str(row.get('日期', '')).strip()
            if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', day) or day[:4] != year_text:
                continue
            payload = _decode_internal_payload(row.get('payload_json', ''), f'{day} 日')
            for sheet_name, date_column in DATE_SHEET_COLUMNS.items():
                records = payload.get(sheet_name, [])
                if records in (None, ''):
                    continue
                if not isinstance(records, list):
                    raise ExcelFormatError(f"内部 Excel 的 {day} 日「{sheet_name}」记录格式不正确。")
                for record in records:
                    if not isinstance(record, dict):
                        raise ExcelFormatError(f"内部 Excel 的 {day} 日「{sheet_name}」记录无法恢复。")
                    restored_record = dict(record)
                    record_day = str(restored_record.get(date_column, '')).strip()
                    if record_day != day:
                        restored_record[date_column] = day
                    collected[sheet_name].append(restored_record)

    month_frame = internal_frames.get('__month_records', pd.DataFrame())
    if {'dataset_id', '月份', 'payload_json'}.issubset(month_frame.columns):
        for _, row in month_frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != dataset_id:
                continue
            month = str(row.get('月份', '')).strip()
            if not re.fullmatch(r'20\d{2}-\d{2}', month) or month[:4] != year_text:
                continue
            payload = _decode_internal_payload(row.get('payload_json', ''), f'{month} 月')
            records = payload.get('monthly_fixed', [])
            if records in (None, ''):
                continue
            if not isinstance(records, list):
                raise ExcelFormatError(f"内部 Excel 的 {month} 月度记录格式不正确。")
            for record in records:
                if not isinstance(record, dict):
                    raise ExcelFormatError(f"内部 Excel 的 {month} 月度记录无法恢复。")
                restored_record = dict(record)
                if str(restored_record.get('月份', '')).strip() != month:
                    restored_record['月份'] = month
                collected['monthly_fixed'].append(restored_record)

    global_frame = internal_frames.get('__global_records', pd.DataFrame())
    if {'dataset_id', '记录类型', 'payload_json'}.issubset(global_frame.columns):
        global_records = {}
        for _, row in global_frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != dataset_id:
                continue
            record_type = str(row.get('记录类型', '')).strip()
            if record_type not in ('ingredients', 'fixed_categories'):
                continue
            payload = _decode_internal_payload(row.get('payload_json', ''), f'{record_type} 字典')
            records = payload.get(record_type, [])
            if records in (None, ''):
                continue
            if not isinstance(records, list):
                raise ExcelFormatError(f"内部 Excel 的「{record_type}」字典格式不正确。")
            global_records[record_type] = records

        for record_type, records in global_records.items():
            for record in records:
                if isinstance(record, dict):
                    collected[record_type].append(dict(record))

    restored = {}
    for sheet_name, columns in STANDARD_SHEET_COLUMNS.items():
        restored[sheet_name] = normalize_sheet_frame(
            sheet_name,
            pd.DataFrame(collected[sheet_name], columns=columns)
            if not collected[sheet_name] else pd.DataFrame(collected[sheet_name]),
        )
        ordered_columns = columns + [
            column for column in restored[sheet_name].columns if column not in columns
        ]
        restored[sheet_name] = restored[sheet_name][ordered_columns]
        if sheet_name == 'monthly_fixed':
            restored[sheet_name] = sort_rows_by_month(restored[sheet_name], '月份')
        elif sheet_name in DATE_SHEET_COLUMNS:
            restored[sheet_name] = sort_rows_by_date(restored[sheet_name], DATE_SHEET_COLUMNS[sheet_name])
    return restored


def _internal_record_hashes(internal_frames, dataset_id):
    """Return the compact record checksums used as the app's optimistic-lock baseline."""
    result = {}
    mapping = {
        '__day_records': ('day', '日期'),
        '__month_records': ('month', '月份'),
        '__global_records': ('global', '记录类型'),
    }
    for sheet_name, (record_type, key_column) in mapping.items():
        frame = internal_frames.get(sheet_name, pd.DataFrame())
        if not {'dataset_id', key_column, 'sha256'}.issubset(frame.columns):
            continue
        for _, row in frame.iterrows():
            if str(row.get('dataset_id', '')).strip() != str(dataset_id):
                continue
            key = str(row.get(key_column, '')).strip()
            if key:
                result[(record_type, key)] = str(row.get('sha256', '')).strip().lower()
    return result


def _set_app_baseline_from_internal(internal_frames, dataset_id, year):
    """Remember exactly what each editor screen was loaded from."""
    global APP_BASELINE_RECORD_HASHES, APP_BASELINE_SHEET_FRAMES, LAST_INTERNAL_MTIME_NS
    APP_BASELINE_RECORD_HASHES = _internal_record_hashes(internal_frames, dataset_id)
    restored = _restored_user_frames_for_year(internal_frames, dataset_id, year)
    APP_BASELINE_SHEET_FRAMES = {
        sheet_name: frame.copy(deep=True) for sheet_name, frame in restored.items()
    }
    signature = _file_signature(INTERNAL_FILE_PATH)
    LAST_INTERNAL_MTIME_NS = signature[1] if signature else None


def _set_user_mirror_pending(pending):
    data = _read_path_config()
    data['USER_MIRROR_SYNC_PENDING'] = bool(pending)
    _write_path_config(data)


def _derived_annual_path(base_path, year):
    base_path = normalize_excel_path(base_path)
    folder, filename = os.path.split(base_path)
    stem, extension = os.path.splitext(filename)
    stem = re.sub(r'([_\-\s]?20\d{2})$', '', stem).rstrip('_- ') or '餐饮管家数据'
    return os.path.join(folder, f'{stem}_{int(year)}{extension or ".xlsx"}')


def _known_user_mirror_targets(internal_frames, dataset_id, years=None):
    config = _read_path_config()
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    year_map = dict(year_map) if isinstance(year_map, dict) else {}
    known_years = set(_internal_years_for_dataset(internal_frames, str(dataset_id)))
    for year_text in year_map:
        try:
            known_years.add(int(year_text))
        except (TypeError, ValueError):
            pass
    if ACTIVE_USER_EXCEL_YEAR:
        known_years.add(int(ACTIVE_USER_EXCEL_YEAR))
    if years is not None:
        requested = {int(year) for year in years}
        known_years &= requested
        known_years |= requested

    base_path = FILE_PATH or config.get('USER_EXCEL_PATH') or config.get('FILE_PATH')
    targets = {}
    for year in sorted(known_years):
        mapped = year_map.get(str(year))
        if int(year) == int(ACTIVE_USER_EXCEL_YEAR or -1) and FILE_PATH:
            mapped = FILE_PATH
        if not mapped and base_path:
            mapped = _derived_annual_path(base_path, year)
        if mapped:
            target = normalize_excel_path(mapped)
            if target != normalize_excel_path(INTERNAL_FILE_PATH):
                targets[year] = target
    return targets


def _user_excel_mirror_frame(sheet_name, frame):
    """Return the public annual-Excel shape for one internal sheet.

    Cash-flow inclusion is an application setting, not a user-accounting field.
    It deliberately remains in the internal store so a desktop/web save cannot
    lose it while refreshing the user's yearly workbook.
    """
    clean = normalize_sheet_frame(sheet_name, frame)
    if sheet_name == 'fixed_expenses':
        columns = ['日期', '类别', '明细', '金额']
        for column in columns:
            if column not in clean.columns:
                clean[column] = ''
        return clean[columns].copy()
    return clean


def _write_user_mirror_atomically(
    path, frames, dataset_id, year, *, allow_family_override=False
):
    """Overwrite all standard sheets from internal data in one atomic file replacement.

    ``allow_family_override`` is reserved for the explicit “switch internal Excel”
    transaction. Normal background refreshes still refuse to overwrite a workbook
    belonging to another data family; an explicitly confirmed whole-store switch may
    replace that metadata because the selected internal workbook is authoritative.
    """
    path = normalize_excel_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if _excel_temporary_lock_exists(path):
        raise ExcelAccessError(
            f'年度用户 Excel 正在被 Microsoft Excel 打开，暂时不能刷新：\n{path}\n\n'
            '请关闭 Excel；软件会在下一次20秒检查时自动补写。'
        )
    if os.path.exists(path):
        saved_family = read_user_workbook_metadata(path).get('family_id', '')
        if (
            saved_family
            and saved_family != str(dataset_id)
            and not allow_family_override
        ):
            raise ExcelAccessError(
                f'不会覆盖属于另一套数据的年度 Excel：\n{path}'
            )
        ensure_excel_writable(path)

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(
            prefix='.restaurant_finance_mirror_',
            suffix='.xlsx',
            dir=os.path.dirname(path),
        )
        os.close(fd)
        if os.path.exists(path):
            shutil.copy2(path, temp_path)
            with pd.ExcelWriter(temp_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                for sheet_name in STANDARD_SHEET_COLUMNS:
                    money_excel_frame(_user_excel_mirror_frame(sheet_name, frames[sheet_name])).to_excel(
                        writer, sheet_name=sheet_name, index=False
                    )
        else:
            with pd.ExcelWriter(temp_path, engine='openpyxl') as writer:
                for sheet_name in STANDARD_SHEET_COLUMNS:
                    money_excel_frame(_user_excel_mirror_frame(sheet_name, frames[sheet_name])).to_excel(
                        writer, sheet_name=sheet_name, index=False
                    )

        workbook = load_workbook(temp_path)
        if USER_META_SHEET in workbook.sheetnames:
            sheet = workbook[USER_META_SHEET]
            sheet.delete_rows(1, sheet.max_row)
        else:
            sheet = workbook.create_sheet(USER_META_SHEET)
        sheet.append(USER_META_COLUMNS)
        sheet.append(['family_id', str(dataset_id)])
        sheet.append(['user_year', str(int(year))])
        sheet.append(['schema_version', '2'])
        sheet.sheet_state = 'veryHidden'
        workbook.save(temp_path)
        workbook.close()
        validate_data_excel(temp_path, require_write=False)
        os.replace(temp_path, path)
        temp_path = None
    except (ExcelAccessError, ExcelFormatError):
        raise
    except OSError as exc:
        raise ExcelAccessError(excel_access_message(path, '刷新年度用户 Excel', exc)) from exc
    except Exception as exc:
        raise ExcelFormatError(f'无法从内部数据刷新年度用户 Excel：\n{path}\n\n系统返回：{exc}') from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def recreate_user_mirror_from_internal(path, year=None, dataset_id=None, internal_path=None):
    """Recreate a deleted annual mirror without asking it to supply any business data."""
    path = normalize_excel_path(path)
    internal_path = normalize_excel_path(
        internal_path or INTERNAL_FILE_PATH or get_internal_excel_path_from_config()
    )
    with internal_sync_lock(internal_path):
        validate_internal_excel(internal_path, require_write=False)
        internal_frames = _read_internal_frames(internal_path)
        available_ids = _internal_dataset_ids(internal_frames)
        selected_id = str(dataset_id or ACTIVE_DATASET_ID or _read_path_config().get('DATASET_ID', '')).strip()
        if selected_id not in available_ids:
            if len(available_ids) == 1:
                selected_id = next(iter(available_ids))
            else:
                raise ExcelFormatError('无法确定要用哪一个内部 dataset_id 重建年度 Excel。')
        try:
            year = int(
                year if year is not None
                else _read_path_config().get('ACTIVE_USER_EXCEL_YEAR')
            )
        except (TypeError, ValueError):
            year = datetime.now().year
        frames = _restored_user_frames_for_year(
            internal_frames, selected_id, year
        )
        _write_user_mirror_atomically(path, frames, selected_id, year)
    return path


def _sync_internal_to_user_excels_unlocked(years=None, update_baseline=False, internal_frames=None):
    global USER_MIRROR_SIGNATURES, LAST_INTERNAL_MTIME_NS
    internal_frames = internal_frames or _read_internal_frames(INTERNAL_FILE_PATH)
    dataset_id = str(ACTIVE_DATASET_ID or get_dataset_id())
    targets = _known_user_mirror_targets(internal_frames, dataset_id, years)
    all_current_targets = set(
        _known_user_mirror_targets(internal_frames, dataset_id, None).values()
    )
    USER_MIRROR_SIGNATURES = {
        path: signature
        for path, signature in USER_MIRROR_SIGNATURES.items()
        if path in all_current_targets
    }
    refreshed = {}
    for year, path in targets.items():
        frames = _restored_user_frames_for_year(internal_frames, dataset_id, year)
        _write_user_mirror_atomically(path, frames, dataset_id, year)
        refreshed[year] = path
        USER_MIRROR_SIGNATURES[path] = _file_signature(path)

    if refreshed:
        config = _read_path_config()
        year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
        year_map = dict(year_map) if isinstance(year_map, dict) else {}
        year_map.update({str(year): path for year, path in refreshed.items()})
        config['YEARLY_USER_EXCEL_PATHS'] = year_map
        config['USER_MIRROR_SYNC_PENDING'] = False
        _write_path_config(config)
    signature = _file_signature(INTERNAL_FILE_PATH)
    LAST_INTERNAL_MTIME_NS = signature[1] if signature else None
    if update_baseline and ACTIVE_USER_EXCEL_YEAR:
        _set_app_baseline_from_internal(
            internal_frames, dataset_id, ACTIVE_USER_EXCEL_YEAR
        )
    return refreshed


def sync_internal_to_user_excels(years=None, update_baseline=False):
    internal_path = normalize_excel_path(INTERNAL_FILE_PATH or get_internal_excel_path_from_config())
    with internal_sync_lock(internal_path):
        return _sync_internal_to_user_excels_unlocked(years, update_baseline)


def _sheet_rows_for_key(frame, key_column, key):
    if key_column not in frame.columns:
        return []
    subset = frame[frame[key_column].astype(str).str.strip() == str(key)]
    return _canonical_records(subset)


def _changed_keys_for_sheet(sheet_name, incoming, active_year):
    baseline = APP_BASELINE_SHEET_FRAMES.get(
        sheet_name, pd.DataFrame(columns=incoming.columns)
    )
    if sheet_name in DATE_SHEET_COLUMNS:
        key_column = DATE_SHEET_COLUMNS[sheet_name]
        keys = _valid_date_keys(incoming, key_column) | _valid_date_keys(baseline, key_column)
        keys = {key for key in keys if int(key[:4]) == int(active_year)}
        return {
            key for key in keys
            if _sheet_rows_for_key(incoming, key_column, key)
            != _sheet_rows_for_key(baseline, key_column, key)
        }
    if sheet_name == 'monthly_fixed':
        keys = _valid_month_keys(incoming) | _valid_month_keys(baseline)
        keys = {key for key in keys if int(key[:4]) == int(active_year)}
        return {
            key for key in keys
            if _sheet_rows_for_key(incoming, '月份', key)
            != _sheet_rows_for_key(baseline, '月份', key)
        }
    if sheet_name in ('ingredients', 'fixed_categories'):
        return {sheet_name} if _canonical_records(incoming) != _canonical_records(baseline) else set()
    raise ExcelFormatError(f'不支持保存工作表：{sheet_name}')


def _replace_frame_keys(latest, incoming, key_column, keys, sheet_name):
    latest = normalize_sheet_frame(sheet_name, latest)
    incoming = normalize_sheet_frame(sheet_name, incoming)
    if not keys:
        return latest
    kept = latest[~latest[key_column].astype(str).str.strip().isin(keys)]
    added = incoming[incoming[key_column].astype(str).str.strip().isin(keys)]
    merged = pd.concat([kept, added], ignore_index=True, sort=False)
    merged = normalize_sheet_frame(sheet_name, merged)
    if sheet_name == 'monthly_fixed':
        return sort_rows_by_month(merged, key_column)
    return sort_rows_by_date(merged, key_column)


def _day_payload_is_empty(payload):
    return not any(payload.get(sheet_name) for sheet_name in DATE_SHEET_COLUMNS)


def _commit_user_sheet_to_internal(sheet_name, incoming, sort_column=None):
    """Save only changed logical records to internal first, guarded by baseline hashes."""
    global APP_BASELINE_RECORD_HASHES, APP_BASELINE_SHEET_FRAMES, LAST_INTERNAL_MTIME_NS
    if not INTERNAL_FILE_PATH:
        raise ExcelAccessError('尚未选择内部 Excel，无法保存。')
    active_year = int(ACTIVE_USER_EXCEL_YEAR or datetime.now().year)
    dataset_id = str(ACTIVE_DATASET_ID or get_dataset_id())
    clean = normalize_sheet_frame(sheet_name, incoming)
    if sort_column:
        clean = (
            sort_rows_by_month(clean, sort_column)
            if sheet_name == 'monthly_fixed'
            else sort_rows_by_date(clean, sort_column)
        )
    changed_keys = _changed_keys_for_sheet(sheet_name, clean, active_year)
    if not changed_keys:
        if _read_path_config().get('USER_MIRROR_SYNC_PENDING', False):
            refreshed = sync_internal_to_user_excels(update_baseline=False)
            return {'records': 0, 'mirrors': len(refreshed)}
        return {'records': 0, 'mirrors': 0}

    with internal_sync_lock(INTERNAL_FILE_PATH):
        internal_frames = _read_internal_frames(INTERNAL_FILE_PATH)
        current_hashes = _internal_record_hashes(internal_frames, dataset_id)
        if sheet_name in DATE_SHEET_COLUMNS:
            identities = {('day', key) for key in changed_keys}
        elif sheet_name == 'monthly_fixed':
            identities = {('month', key) for key in changed_keys}
        else:
            identities = {('global', sheet_name)}
        conflicting = sorted(
            identity for identity in identities
            if current_hashes.get(identity) != APP_BASELINE_RECORD_HASHES.get(identity)
        )
        if conflicting:
            details = '\n'.join(f'  - {kind}/{key}' for kind, key in conflicting[:20])
            raise ExcelAccessError(
                '这些记录已被网页或其它设备修改，本次本地保存没有覆盖它们：\n'
                f'{details}\n\n请等待软件自动刷新后重新输入。'
            )

        before_payloads = {
            identity: _internal_payload_for_identity(internal_frames, dataset_id, identity)
            for identity in identities
        }

        latest_frames = _restored_user_frames_for_year(
            internal_frames, dataset_id, active_year
        )
        if sheet_name in DATE_SHEET_COLUMNS:
            latest_frames[sheet_name] = _replace_frame_keys(
                latest_frames[sheet_name], clean,
                DATE_SHEET_COLUMNS[sheet_name], changed_keys, sheet_name
            )
            for day in sorted(changed_keys):
                payload = _user_day_payload(latest_frames, day)
                validate_money_changes(payload, before_payloads.get(('day', day)))
                payload = prepare_money_save(payload, before_payloads.get(('day', day)))
                if _day_payload_is_empty(payload):
                    internal_frames['__day_records'] = _replace_internal_record(
                        internal_frames['__day_records'], dataset_id, '日期', day
                    )
                else:
                    payload_json, digest = _payload_and_hash(payload)
                    internal_frames['__day_records'] = _replace_internal_record(
                        internal_frames['__day_records'], dataset_id, '日期', day,
                        payload_json, digest
                    )
        elif sheet_name == 'monthly_fixed':
            latest_frames[sheet_name] = _replace_frame_keys(
                latest_frames[sheet_name], clean, '月份', changed_keys, sheet_name
            )
            for month in sorted(changed_keys):
                payload = _user_month_payload(latest_frames, month)
                validate_money_changes(payload, before_payloads.get(('month', month)))
                payload = prepare_money_save(payload, before_payloads.get(('month', month)))
                if not payload.get('monthly_fixed'):
                    internal_frames['__month_records'] = _replace_internal_record(
                        internal_frames['__month_records'], dataset_id, '月份', month
                    )
                else:
                    payload_json, digest = _payload_and_hash(payload)
                    internal_frames['__month_records'] = _replace_internal_record(
                        internal_frames['__month_records'], dataset_id, '月份', month,
                        payload_json, digest
                    )
        else:
            latest_frames[sheet_name] = clean.copy(deep=True)
            payload = {sheet_name: _canonical_records(clean)}
            validate_money_changes(payload, before_payloads.get(('global', sheet_name)))
            payload = prepare_money_save(payload, before_payloads.get(('global', sheet_name)))
            payload_json, digest = _payload_and_hash(payload)
            internal_frames['__global_records'] = _replace_internal_record(
                internal_frames['__global_records'], dataset_id, '记录类型', sheet_name,
                payload_json, digest
            )

        # 修改日志也是内部 Excel 的正式数据：只记录真正的前后差异，
        # 同步助手会将它们作为 global 记录自动上传。
        expired_audit_keys = _prune_internal_audit_records(
            internal_frames, dataset_id
        )
        created_audit_keys = []
        if _desktop_cloud_role() != 'admin':
            created_audit_keys = _append_internal_audit_records(
                internal_frames, dataset_id, identities, before_payloads, sheet_name
            )

        meta = internal_frames['__meta']
        meta = meta.loc[meta['dataset_id'].astype(str) != dataset_id].copy()
        meta = pd.concat([meta, pd.DataFrame([{
            'dataset_id': dataset_id,
            'schema_version': '2',
            'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }])], ignore_index=True)
        internal_frames['__meta'] = meta
        _write_internal_frames(INTERNAL_FILE_PATH, internal_frames)

        new_hashes = _internal_record_hashes(internal_frames, dataset_id)
        for identity in identities:
            if identity in new_hashes:
                APP_BASELINE_RECORD_HASHES[identity] = new_hashes[identity]
            else:
                APP_BASELINE_RECORD_HASHES.pop(identity, None)
        for audit_key in expired_audit_keys:
            APP_BASELINE_RECORD_HASHES.pop(('global', audit_key), None)
        for audit_key in created_audit_keys:
            APP_BASELINE_RECORD_HASHES[('global', audit_key)] = new_hashes[
                ('global', audit_key)
            ]
        APP_BASELINE_SHEET_FRAMES[sheet_name] = clean.copy(deep=True)
        signature = _file_signature(INTERNAL_FILE_PATH)
        LAST_INTERNAL_MTIME_NS = signature[1] if signature else None

        try:
            mirror_years = None if sheet_name in ('ingredients', 'fixed_categories') else [active_year]
            refreshed = _sync_internal_to_user_excels_unlocked(
                mirror_years, update_baseline=False, internal_frames=internal_frames
            )
        except Exception as exc:
            _set_user_mirror_pending(True)
            raise ExcelAccessError(
                '内部数据已经安全保存，但年度用户 Excel 暂时无法刷新。\n'
                '请关闭 Microsoft Excel；软件会每20秒自动补写。\n\n'
                f'系统返回：{exc}'
            ) from exc
        _set_user_mirror_pending(False)
        return {'records': len(identities), 'mirrors': len(refreshed)}


def _restore_filename_for_year(config, year):
    """Prefer the old configured basename, falling back to a clear annual name."""
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    mapped_path = year_map.get(str(int(year))) if isinstance(year_map, dict) else None
    candidate = os.path.basename(os.path.expanduser(str(mapped_path))) if mapped_path else ''
    if not candidate:
        candidate = os.path.basename(os.path.expanduser(str(
            config.get('USER_EXCEL_PATH') or config.get('FILE_PATH') or ''
        )))
    if not candidate or candidate in ('.', os.path.sep):
        return f'餐饮管家数据_{int(year)}.xlsx'

    stem, extension = os.path.splitext(candidate)
    extension = extension or '.xlsx'
    if not extension.lower().endswith('xlsx'):
        extension = '.xlsx'
    stem = re.sub(r'([_\-\s]?20\d{2})$', '', stem).rstrip('_- ') or '餐饮管家数据'
    if mapped_path:
        # Keep an explicitly registered annual basename exactly when possible;
        # e.g. the first year may historically be named without a year suffix.
        return candidate if extension.lower() == '.xlsx' else f'{stem}{extension}'
    return f'{stem}_{int(year)}{extension}'


def _new_restore_target(target_dir, filename, internal_path, dataset_id, multiple_datasets):
    """Choose a non-destructive target path; never overwrite an existing file."""
    stem, extension = os.path.splitext(filename)
    extension = extension or '.xlsx'
    if multiple_datasets:
        stem = f'{stem}_恢复_{dataset_id[:8]}'
    candidate = os.path.abspath(os.path.join(target_dir, f'{stem}{extension}'))
    if candidate == os.path.abspath(internal_path) or os.path.exists(candidate):
        suffix = '_恢复' if not multiple_datasets else ''
        index = 1
        while True:
            extra = f'{suffix}_{index}' if index > 1 else suffix
            candidate = os.path.abspath(os.path.join(target_dir, f'{stem}{extra}{extension}'))
            if candidate != os.path.abspath(internal_path) and not os.path.exists(candidate):
                break
            index += 1
    return candidate


def restore_user_excels_from_internal(parent=None):
    """Restore annual user workbooks from the selected all-years internal store."""
    config = _read_path_config()
    configured_path = config.get('INTERNAL_FILE_PATH') or get_internal_excel_path_from_config()
    configured_path = normalize_excel_path(configured_path)
    if os.path.exists(configured_path):
        internal_path = validate_internal_excel(configured_path, require_write=False)
    else:
        start_dir = os.path.dirname(configured_path) if os.path.isdir(os.path.dirname(configured_path)) else os.path.expanduser('~')
        selected_path, _ = QFileDialog.getOpenFileName(
            parent,
            '选择用于恢复用户 Excel 的内部 Excel',
            start_dir,
            'Excel Files (*.xlsx)',
        )
        if not selected_path:
            return None
        internal_path = validate_internal_excel(selected_path, require_write=False)

    with internal_sync_lock(internal_path):
        internal_frames = _read_internal_frames(internal_path)
    all_dataset_ids = sorted(_internal_dataset_ids(internal_frames))
    if not all_dataset_ids:
        raise ExcelFormatError('内部 Excel 中没有找到可恢复的用户数据。')

    preferred_dataset_id = str(config.get('DATASET_ID', '')).strip()
    if preferred_dataset_id and preferred_dataset_id in all_dataset_ids:
        dataset_ids = [preferred_dataset_id]
    else:
        dataset_ids = all_dataset_ids
    dataset_years = {
        dataset_id: _internal_years_for_dataset(internal_frames, dataset_id)
        for dataset_id in dataset_ids
    }
    dataset_years = {dataset_id: years for dataset_id, years in dataset_years.items() if years}
    if not dataset_years:
        raise ExcelFormatError('内部 Excel 中没有找到可恢复的年度用户 Excel 数据。')

    target_dir = os.path.dirname(internal_path)
    multiple_datasets = len(dataset_years) > 1
    restored = []
    for dataset_id, years in dataset_years.items():
        for year in years:
            filename = _restore_filename_for_year(config, year)
            target_path = _new_restore_target(
                target_dir, filename, internal_path, dataset_id, multiple_datasets
            )
            frames = _restored_user_frames_for_year(internal_frames, dataset_id, year)
            init_excel_structure(target_path)
            for sheet_name, frame in frames.items():
                write_excel_sheet(target_path, sheet_name, frame)
            write_user_workbook_metadata(target_path, dataset_id, year)
            validate_data_excel(target_path, require_write=True)
            restored.append({'dataset_id': dataset_id, 'year': year, 'path': target_path})

    active_dataset_id = preferred_dataset_id if preferred_dataset_id in dataset_years else next(iter(dataset_years))
    try:
        active_year = int(config.get('ACTIVE_USER_EXCEL_YEAR', ''))
    except (TypeError, ValueError):
        active_year = None
    active_candidates = [item for item in restored if item['dataset_id'] == active_dataset_id]
    active_item = next((item for item in active_candidates if item['year'] == active_year), None) or active_candidates[0]

    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    if not isinstance(year_map, dict):
        year_map = {}
    for item in active_candidates:
        year_map[str(item['year'])] = item['path']
    config.update({
        'FILE_PATH': active_item['path'],
        'USER_EXCEL_PATH': active_item['path'],
        'INTERNAL_FILE_PATH': internal_path,
        'YEARLY_USER_EXCEL_PATHS': year_map,
        'ACTIVE_USER_EXCEL_YEAR': int(active_item['year']),
        'DATASET_ID': active_dataset_id,
        'INTERNAL_SYNC_PENDING': False,
    })
    _write_path_config(config)
    return {
        'internal_path': internal_path,
        'active_path': active_item['path'],
        'restored': restored,
    }


def _merge_numeric_record_values(records, key):
    total = 0
    found = False
    for record in records:
        value = record.get(key, '')
        try:
            number = money_amount(value) if key in MONEY_FIELDS else decimal_number(value)
            total += number
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else ''


def _merge_daily_payload_records(current_records, imported_records):
    """Add two same-day daily records, preserving text details and all numeric fields."""
    records = list(current_records or []) + list(imported_records or [])
    if not records:
        return []
    numeric_fields = {
        '收益', '总现金', 'A店现金', 'B店现金', '总线上',
        'A店微信增加', 'A店支付宝增加', 'B店微信增加', 'B店支付宝增加',
        'A店收入', 'B店收入', '学生外卖', 'A店外卖', 'B店外卖', '新客人数量', '总客人数',
        '食材成本', '佐料成本', '水电', '其他',
        'A店微信支付金额', 'A店微信退款金额', 'A店微信支付笔数', 'A店微信退款笔数',
        'B店微信支付金额', 'B店微信退款金额', 'B店微信支付笔数', 'B店微信退款笔数',
        '微信账单未归属笔数',
    }
    override_fields = {'A店微信自动', 'B店微信自动', 'A店微信覆盖', 'A店支付宝覆盖', 'B店微信覆盖', 'B店支付宝覆盖'}
    merged = {}
    keys = sorted({str(key) for record in records for key in record.keys()})
    for key in keys:
        if key in numeric_fields:
            merged[key] = _merge_numeric_record_values(records, key)
        elif key in override_fields:
            values = [record.get(key, '') for record in records]
            entered_values = [value for value in values if money_value_was_entered(value)]
            merged[key] = entered_values[-1] if entered_values else ''
        elif key == '日期':
            merged[key] = str(records[0].get(key, '')).strip()
        else:
            values = [str(record.get(key, '')).strip() for record in records]
            values = [value for value in values if value and value.lower() != 'nan']
            merged[key] = '；'.join(values)
    return [merged]


def _merged_day_payload(current_frames, imported_frames, day):
    """Build a day payload where daily money/counts add and detail rows stack."""
    current_payload = _user_day_payload(current_frames, day)
    imported_payload = _user_day_payload(imported_frames, day)
    payload = {}
    for sheet_name in DATE_SHEET_COLUMNS:
        current_records = current_payload.get(sheet_name, [])
        imported_records = imported_payload.get(sheet_name, [])
        if sheet_name == 'daily':
            records = _merge_daily_payload_records(current_records, imported_records)
        else:
            records = current_records + imported_records
            records = _canonical_records(pd.DataFrame(records)) if records else []
        payload[sheet_name] = records
    return payload


def _infer_user_excel_year(path, fallback=None):
    path = os.path.abspath(os.path.expanduser(path))
    config = _read_path_config()
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    if isinstance(year_map, dict):
        for year_text, mapped_path in year_map.items():
            try:
                if os.path.abspath(os.path.expanduser(str(mapped_path))) == path:
                    return int(year_text)
            except (TypeError, ValueError):
                pass
    match = re.search(r'(20\d{2})(?:\D*)$', os.path.splitext(os.path.basename(path))[0])
    if match:
        return int(match.group(1))
    try:
        daily = read_excel_exact(path, sheet_name='daily', usecols=['日期'])
        years = sorted({int(day[:4]) for day in _valid_date_keys(normalize_date_column(daily), '日期')})
        if datetime.now().year in years:
            return datetime.now().year
        if len(years) == 1:
            return years[0]
        if years:
            return years[-1]
    except Exception:
        pass
    return int(fallback or datetime.now().year)


def configure_active_user_excel(path, active_year=None, sort_first=True, family_id=None,
                                sync_internal=True, internal_path=None):
    """Activate an annual mirror; existing internal data always wins.

    ``sync_internal=False`` is used only during startup while the user is choosing
    or recovering the internal workbook.  It prevents a missing internal file from
    being silently recreated before the user sees the required choice dialog.
    """
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID
    candidate_path = validate_data_excel(path, require_write=True)
    candidate_internal_path = normalize_excel_path(
        internal_path or INTERNAL_FILE_PATH or get_internal_excel_path_from_config()
    )
    candidate_year = int(active_year or _infer_user_excel_year(candidate_path))
    internal_frames = None
    internal_ids = set()
    if os.path.exists(candidate_internal_path):
        with internal_sync_lock(candidate_internal_path):
            validate_internal_excel(candidate_internal_path, require_write=True)
            _rebind_internal_dataset_id_unlocked(
                candidate_internal_path, FIXED_CLOUD_DATASET_ID
            )
            internal_frames = _read_internal_frames(candidate_internal_path)
            internal_ids = (
                _internal_dataset_ids(internal_frames)
                if _internal_has_business_records(internal_frames)
                else set()
            )

    metadata_family = read_user_workbook_metadata(candidate_path).get('family_id', '')
    preferred_family = FIXED_CLOUD_DATASET_ID
    if internal_ids:
        if preferred_family not in internal_ids:
            if len(internal_ids) == 1:
                preferred_family = next(iter(internal_ids))
            else:
                raise ExcelFormatError(
                    '内部 Excel 中有多套数据，所选年度文件无法确定应对应哪一套。'
                )
    candidate_family_id = ensure_user_workbook_metadata(
        candidate_path, candidate_year, preferred_family or None
    )

    old_state = (FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID)
    try:
        FILE_PATH = candidate_path
        INTERNAL_FILE_PATH = candidate_internal_path
        ACTIVE_USER_EXCEL_YEAR = candidate_year
        ACTIVE_DATASET_ID = candidate_family_id
        if sync_internal:
            if internal_ids:
                # The annual file may have been edited manually; replace it from internal.
                sync_internal_to_user_excels(
                    years=[candidate_year], update_baseline=True
                )
            else:
                # Only a genuinely empty/new internal store may bootstrap from a user file.
                if sort_first:
                    sort_data_workbook(candidate_path)
                sync_user_excel_to_internal(
                    candidate_path,
                    candidate_year,
                    candidate_family_id,
                    candidate_internal_path,
                )
                sync_internal_to_user_excels(
                    years=[candidate_year], update_baseline=True
                )
        save_path_config(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, INTERNAL_FILE_PATH)
        return FILE_PATH
    except Exception:
        FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID = old_state
        raise


def _yearly_user_workbook_path(year):
    base_path = normalize_excel_path(FILE_PATH)
    folder, filename = os.path.split(base_path)
    stem, extension = os.path.splitext(filename)
    stem = re.sub(r'([_\-\s]?20\d{2})$', '', stem).rstrip('_- ')
    if not stem:
        stem = '餐饮管家数据'
    return os.path.join(folder, f'{stem}_{int(year)}{extension or ".xlsx"}')


def _copy_reference_sheets(source_path, target_path):
    """A new year starts clean, but keeps the user's ingredient/category dictionaries."""
    if not source_path or not os.path.exists(source_path):
        return
    frames = _read_user_workbook_frames(source_path)
    for sheet_name in ('ingredients', 'fixed_categories'):
        write_excel_sheet(target_path, sheet_name, frames[sheet_name])


def ensure_user_excel_for_year(year):
    """Switch to, or automatically create, the annual user Excel for ``year``."""
    global FILE_PATH, ACTIVE_USER_EXCEL_YEAR
    year = int(year)
    if FILE_PATH and ACTIVE_USER_EXCEL_YEAR == year and os.path.exists(FILE_PATH):
        return FILE_PATH

    config = _read_path_config()
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    year_map = year_map if isinstance(year_map, dict) else {}
    mapped_path = year_map.get(str(year))
    previous_path = FILE_PATH

    if mapped_path:
        mapped_path = normalize_excel_path(mapped_path)
        if not os.path.exists(mapped_path):
            recreate_user_mirror_from_internal(
                mapped_path,
                year=year,
                dataset_id=ACTIVE_DATASET_ID or None,
                internal_path=INTERNAL_FILE_PATH,
            )
        mapped_family_id = read_user_workbook_metadata(mapped_path).get('family_id', '')
        if mapped_family_id and ACTIVE_DATASET_ID and mapped_family_id != ACTIVE_DATASET_ID:
            raise ExcelAccessError(
                f"已登记的 {year} 年文件不属于当前用户 Excel 数据组：\n{mapped_path}\n\n"
                "请使用“重新选择数据来源”切换到这套数据，或创建新的用户 Excel。"
            )
        return configure_active_user_excel(mapped_path, year, family_id=ACTIVE_DATASET_ID or None)

    target_path = _yearly_user_workbook_path(year)
    if os.path.exists(target_path):
        existing_family_id = read_user_workbook_metadata(target_path).get('family_id', '')
        if existing_family_id and ACTIVE_DATASET_ID and existing_family_id != ACTIVE_DATASET_ID:
            raise ExcelAccessError(
                f"检测到同名的 {year} 年 Excel，但它属于另一套数据：\n{target_path}\n\n"
                "请通过“重新选择数据来源”明确载入它，避免把不同账本混在一起。"
            )
        # A previous run may have created the annual file before the path map was
        # persisted.  Reuse that exact file so entering a new year remains automatic.
        return configure_active_user_excel(
            target_path,
            year,
            family_id=ACTIVE_DATASET_ID or existing_family_id or None,
        )

    # Requirement: when a truly new calendar year is entered, create a clean user
    # workbook automatically instead of putting 2027 rows into the 2026 workbook.
    init_excel_structure(target_path)
    _copy_reference_sheets(previous_path, target_path)
    family_id = ACTIVE_DATASET_ID or get_dataset_id()
    ensure_user_workbook_metadata(target_path, year, family_id)
    return configure_active_user_excel(target_path, year, family_id=family_id)


def ensure_widget_user_excel_year(widget, date_value):
    """Ask the main window to activate the right annual workbook for a date picker."""
    year = date_value.year() if isinstance(date_value, QDate) else int(str(date_value)[:4])
    if ACTIVE_USER_EXCEL_YEAR == year:
        return True
    main_window = widget.window() if hasattr(widget, 'window') else None
    if main_window is not None and hasattr(main_window, 'ensure_user_excel_year'):
        return bool(main_window.ensure_user_excel_year(year, widget))
    try:
        ensure_user_excel_for_year(year)
        return True
    except (ExcelAccessError, ExcelFormatError) as exc:
        QMessageBox.warning(widget, '无法切换年度用户 Excel', str(exc))
        return False


def save_current_user_sheet(sheet_name, df, sort_column=None):
    """Commit to internal first; regenerate annual Excel only after that succeeds."""
    require_network_edit()
    if not FILE_PATH:
        raise ExcelAccessError('尚未选择年度用户 Excel，无法保存。')
    return _commit_user_sheet_to_internal(sheet_name, df, sort_column)


# ===================== 数据读写层 =====================
def require_active_user_excel(require_write=False):
    """Use the annual mirror, recreating it from internal data when it was deleted."""
    if not FILE_PATH:
        raise ExcelAccessError('尚未选择用户 Excel。请读取已有文件或创建新的用户 Excel。')
    if not os.path.exists(FILE_PATH) and INTERNAL_FILE_PATH and os.path.exists(INTERNAL_FILE_PATH):
        recreate_user_mirror_from_internal(
            FILE_PATH,
            year=ACTIVE_USER_EXCEL_YEAR,
            dataset_id=ACTIVE_DATASET_ID or None,
            internal_path=INTERNAL_FILE_PATH,
        )
    try:
        return validate_data_excel(FILE_PATH, require_write=require_write)
    except ExcelFormatError as exc:
        # A packaged macOS app can see a previously granted file as “missing” when
        # its TCC permission has not been restored.  Route both real missing files
        # and that denial through the same Load/Create recovery dialog.
        if not os.path.exists(FILE_PATH):
            raise ExcelAccessError(
                f"当前用户 Excel 找不到或软件没有访问权限：\n{FILE_PATH}\n\n"
                "请重新读取已有用户 Excel，或创建一个新的用户 Excel。"
            ) from exc
        raise


def load_daily():
    path = require_active_user_excel()
    df = read_excel_exact(path, sheet_name='daily')
    df = normalize_sheet_frame('daily', df)
    df = normalize_date_column(df, '日期')
    return df.astype(object).fillna('')


def save_daily(df):
    # 第4阶段：内部记录先落盘，年度 Excel 随后由内部记录自动生成。
    save_current_user_sheet('daily', df, '日期')


def load_monthly_fixed():
    path = require_active_user_excel()
    try:
        df = read_excel_exact(path, sheet_name='monthly_fixed')
        return normalize_sheet_frame('monthly_fixed', df)
    except Exception:
        return pd.DataFrame(columns=STANDARD_SHEET_COLUMNS['monthly_fixed'])


def save_monthly_fixed(df):
    save_current_user_sheet('monthly_fixed', df, '月份')


FIXED_EXPENSE_COLUMNS = ['日期', '类别', '明细', '金额', '计入可用余额']
FIXED_EXPENSE_CASH_COLUMN = '计入可用余额'
# This control value belongs to the app/cloud internal record.  It is not a
# business-accounting column for the annual user Excel mirror.
USER_FIXED_EXPENSE_COLUMNS = ['日期', '类别', '明细', '金额']
DEFAULT_FIXED_CATEGORIES = ['水费', '电费', '煤气费', '人工', '房租及物业费', '其它']
DAILY_FIXED_CATEGORIES = tuple(DEFAULT_FIXED_CATEGORIES)
LEGACY_FIXED_CATEGORY_MAP = {
    '水电费': '水费',
    '房租': '房租及物业费',
    '房租费': '房租及物业费',
    '物业费': '房租及物业费',
}


def normalize_fixed_category(category):
    category = str(category).strip()
    return LEGACY_FIXED_CATEGORY_MAP.get(category, category)


def fixed_expense_includes_cash(value):
    """Normalize the per-expense cash-flow flag, defaulting legacy rows to True."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return True
    return text not in {'0', 'false', 'no', 'n', '否', '不', '不计入', '不计入可用余额'}


def load_fixed_expenses():
    """读取逐日固定成本；首次升级时把旧月度总额迁移为月初明细。"""
    # The internal store owns the “include in cash balance” checkbox.  Read
    # fixed expenses from it whenever available so user Excel never needs to
    # carry that permission/control field.
    internal_path = normalize_excel_path(INTERNAL_FILE_PATH or '')
    if internal_path and os.path.exists(internal_path):
        try:
            with internal_sync_lock(internal_path):
                internal_frames = _read_internal_frames(internal_path)
            internal_rows = _restored_user_frames_for_year(
                internal_frames,
                str(ACTIVE_DATASET_ID or FIXED_CLOUD_DATASET_ID),
                int(ACTIVE_USER_EXCEL_YEAR or datetime.now().year),
            ).get('fixed_expenses', pd.DataFrame(columns=FIXED_EXPENSE_COLUMNS))
            if not internal_rows.empty:
                clean_internal = internal_rows.copy()
                for col in FIXED_EXPENSE_COLUMNS:
                    if col not in clean_internal.columns:
                        clean_internal[col] = ''
                clean_internal = clean_internal[FIXED_EXPENSE_COLUMNS].astype(object).fillna('')
                clean_internal[FIXED_EXPENSE_CASH_COLUMN] = clean_internal[
                    FIXED_EXPENSE_CASH_COLUMN
                ].map(fixed_expense_includes_cash)
                clean_internal = normalize_date_column(clean_internal, '日期')
                clean_internal['类别'] = clean_internal['类别'].apply(normalize_fixed_category)
                return clean_internal
        except Exception:
            # Preserve the old user-workbook fallback for a legacy or damaged
            # internal file; normal operation remains internal-first.
            pass
    path = require_active_user_excel()

    try:
        xl = pd.ExcelFile(path)
        if 'fixed_expenses' in xl.sheet_names:
            df = read_excel_exact(path, sheet_name='fixed_expenses')
            for col in FIXED_EXPENSE_COLUMNS:
                if col not in df.columns:
                    df[col] = ''
            df = df[FIXED_EXPENSE_COLUMNS].astype(object).fillna('')
            df[FIXED_EXPENSE_CASH_COLUMN] = df[FIXED_EXPENSE_CASH_COLUMN].map(fixed_expense_includes_cash)
            df = normalize_date_column(df, '日期')
            df['类别'] = df['类别'].apply(normalize_fixed_category)
            return df
    except Exception:
        pass

    # 兼容旧文件：原来的人工/水电/煤气只有月度总额，将其迁移成可见明细。
    migrated = []
    df_fixed = load_monthly_fixed()
    for _, row in df_fixed.iterrows():
        month = str(row.get('月份', '')).strip()
        if not re.match(r'^\d{4}-\d{2}$', month):
            continue
        for category, column in (
                ('人工', '人工总额'), ('水费', '水电费'), ('煤气费', '煤气费'), ('其它', '其它固定成本'),
                ('房租及物业费', '房租总额')):
            amount = money_amount(row.get(column, 0))
            if amount:
                migrated.append({
                    '日期': f"{month}-01",
                    '类别': category,
                    '明细': '旧版月度总额（自动迁移）',
                    '金额': amount,
                    FIXED_EXPENSE_CASH_COLUMN: True,
                })
    df = pd.DataFrame(migrated, columns=FIXED_EXPENSE_COLUMNS)
    save_fixed_expenses(df)
    return df.astype(object).fillna('')


def save_fixed_expenses(df):
    clean = df.copy()
    for col in FIXED_EXPENSE_COLUMNS:
        if col not in clean.columns:
            clean[col] = ''
    clean = clean[FIXED_EXPENSE_COLUMNS]
    clean['类别'] = clean['类别'].apply(normalize_fixed_category)
    clean[FIXED_EXPENSE_CASH_COLUMN] = clean[FIXED_EXPENSE_CASH_COLUMN].map(fixed_expense_includes_cash)
    save_current_user_sheet('fixed_expenses', clean, '日期')


def load_fixed_categories():
    path = require_active_user_excel()
    categories = []
    try:
        xl = pd.ExcelFile(path)
        if 'fixed_categories' in xl.sheet_names:
            df = read_excel_exact(path, sheet_name='fixed_categories')
            if '类别名称' not in df.columns:
                df['类别名称'] = ''
            categories = [normalize_fixed_category(v) for v in df['类别名称'] if str(v).strip()]
    except Exception:
        categories = []

    found = []
    try:
        expenses = load_fixed_expenses()
        found = [normalize_fixed_category(v) for v in expenses.get('类别', []) if str(v).strip()]
    except Exception:
        found = []

    ordered = []
    for category in DEFAULT_FIXED_CATEGORIES + categories + found:
        category = normalize_fixed_category(category)
        if category and category not in ordered:
            ordered.append(category)
    return ordered or list(DEFAULT_FIXED_CATEGORIES)


def save_fixed_categories(categories):
    clean = []
    for category in categories:
        category = normalize_fixed_category(category)
        if category and category not in clean:
            clean.append(category)
    if not clean:
        clean = list(DEFAULT_FIXED_CATEGORIES)
    df = pd.DataFrame({'类别名称': clean})
    save_current_user_sheet('fixed_categories', df)


def apply_fixed_category_renames(rename_map):
    rename_map = {
        normalize_fixed_category(old): normalize_fixed_category(new)
        for old, new in rename_map.items()
        if normalize_fixed_category(old) and normalize_fixed_category(new)
    }
    if not rename_map:
        return 0
    df = load_fixed_expenses()
    changed = 0
    for idx, row in df.iterrows():
        old = normalize_fixed_category(row.get('类别', ''))
        if old in rename_map:
            df.at[idx, '类别'] = rename_map[old]
            changed += 1
    if changed:
        save_fixed_expenses(df)
        for month_str in sorted(set(str(v)[:7] for v in df['日期'] if re.match(r'^\d{4}-\d{2}', str(v)))):
            sync_monthly_fixed_from_expenses(month_str, df)
    return changed


def fixed_expense_totals(month_str, df_expenses=None, cash_only=False):
    df = load_fixed_expenses() if df_expenses is None else df_expenses
    month_df = df[df['日期'].astype(str).str.startswith(month_str)]
    if cash_only and FIXED_EXPENSE_CASH_COLUMN in month_df.columns:
        month_df = month_df[month_df[FIXED_EXPENSE_CASH_COLUMN].map(fixed_expense_includes_cash)]
    totals = {category: 0 for category in load_fixed_categories()}
    for _, row in month_df.iterrows():
        category = normalize_fixed_category(row.get('类别', ''))
        totals[category] = totals.get(category, 0) + money_amount(row.get('金额', 0))
    return totals


def fixed_total_for_categories(totals, categories):
    return sum(totals.get(normalize_fixed_category(category), 0) for category in categories)


def format_fixed_expense_note_date(day_str):
    try:
        return datetime.strptime(str(day_str), "%Y-%m-%d").strftime("%b %d")
    except Exception:
        return str(day_str)


def rent_property_note_from_expenses(month_str, df_expenses=None):
    df = load_fixed_expenses() if df_expenses is None else df_expenses
    month_df = df[df['日期'].astype(str).str.startswith(month_str)].copy()
    if month_df.empty:
        return ""
    month_df['类别'] = month_df['类别'].apply(normalize_fixed_category)
    month_df = month_df[month_df['类别'] == '房租及物业费'].sort_values('日期')
    notes = []
    for _, row in month_df.iterrows():
        detail = str(row.get('明细', '')).strip()
        amount = money_amount(row.get('金额', 0))
        if detail:
            body = detail if re.search(r'\d', detail) else f"{detail} {amount:g}"
        else:
            body = f"{amount:g}"
        notes.append(f"{format_fixed_expense_note_date(row.get('日期', ''))} {body}".strip())
    return "；".join(notes)


def sync_monthly_fixed_from_expenses(month_str, df_expenses=None):
    """把逐日明细合计同步到旧汇总列，确保全部既有统计继续正确工作。"""
    totals = fixed_expense_totals(month_str, df_expenses)
    df = normalize_sheet_frame('monthly_fixed', load_monthly_fixed())
    existing = df[df['月份'] == month_str]
    if existing.empty:
        df = pd.concat([df, pd.DataFrame([{
            '月份': month_str, '人工总额': 0, '房租总额': 0,
            '水费支出': 0, '电费支出': 0, '水电费': 0,
            '实际使用水费': '', '实际使用电费': '',
            '煤气费': 0, '其它固定成本': 0, '月度备注': ''
        }])], ignore_index=True)
        idx = df.index[-1]
    else:
        idx = existing.index[0]
    df.loc[idx, '人工总额'] = totals.get('人工', 0)
    df.loc[idx, '房租总额'] = totals.get('房租及物业费', 0)
    df.loc[idx, '水费支出'] = totals.get('水费', 0)
    df.loc[idx, '电费支出'] = totals.get('电费', 0)
    df.loc[idx, '水电费'] = totals.get('水费', 0) + totals.get('电费', 0)
    df.loc[idx, '煤气费'] = totals.get('煤气费', 0)
    mapped_categories = {'水费', '电费', '煤气费', '人工', '房租及物业费', '其它'}
    custom_other = sum(value for category, value in totals.items() if category not in mapped_categories)
    df.loc[idx, '其它固定成本'] = totals.get('其它', 0) + custom_other
    df.loc[idx, '月度备注'] = rent_property_note_from_expenses(month_str, df_expenses)
    save_monthly_fixed(df)


def load_ingredients():
    path = require_active_user_excel()
    try:
        df = read_excel_exact(path, sheet_name='ingredients')
        if '食材名称' in df.columns and '词条名称' not in df.columns:
            df.rename(columns={'食材名称': '词条名称'}, inplace=True)
        if '分类' not in df.columns: df['分类'] = '食材'
        df.dropna(subset=['词条名称'], inplace=True)
        return df
    except Exception:
        return pd.DataFrame(columns=['词条名称', '分类'])


def save_ingredients(df):
    save_current_user_sheet('ingredients', df)


DISH_COLUMNS = ['日期', '菜品明细', '菜品数据', '总成本', '备注']


def load_dishes():
    path = require_active_user_excel()
    try:
        df = read_excel_exact(path, sheet_name='dishes')
        for col in DISH_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[DISH_COLUMNS].astype(object).fillna('')
        df = normalize_date_column(df, '日期')
        return df
    except Exception:
        return pd.DataFrame(columns=DISH_COLUMNS)


def save_dishes(df):
    clean = df.copy()
    for col in DISH_COLUMNS:
        if col not in clean.columns:
            clean[col] = ''
    clean = clean[DISH_COLUMNS].astype(object).fillna('')
    save_current_user_sheet('dishes', clean, '日期')


def detail_total_cost(detail_text):
    total = 0
    for part in re.split(r'[,，]', str(detail_text or '')):
        clean, _note = split_item_note(part)
        nums = re.findall(r'(\d+(?:\.\d+)?)', clean)
        if nums:
            total += money_amount(nums[-1])
    return total


def dish_rows_from_record(record):
    """读取一天的菜品数据，并兼容旧版没有“份数/分区”的记录。"""
    if record is None:
        return []
    raw_data = record.get('菜品数据', '')
    raw_json = exact_json_dumps(raw_data, ensure_ascii=False) if isinstance(raw_data, list) else str(raw_data or '').strip()
    if raw_json and raw_json.lower() != 'nan':
        try:
            data = exact_json_loads(raw_json)
            rows = []
            for item in data if isinstance(data, list) else []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('菜品名称', '')).strip()
                detail_value = item.get('食材明细', '')
                ingredients = exact_json_dumps(detail_value, ensure_ascii=False) if isinstance(detail_value, list) else str(detail_value).strip()
                note = str(item.get('备注', '')).strip()
                raw_cost = item.get('成本', detail_total_cost(ingredients))
                cost = money_amount(raw_cost if raw_cost not in (None, '') else 0)
                raw_servings = item.get('份数', 0)
                servings = safe_float(raw_servings if raw_servings not in (None, '') else 0)
                servings = int(servings) if (servings == int(servings)) else servings
                section = str(item.get('分区', '菜品') or '菜品').strip()
                if section not in ('菜品', '固定项目'):
                    section = '菜品'
                if name or ingredients or note or cost or servings:
                    rows.append({
                        '菜品名称': name,
                        '份数': servings,
                        '食材明细': ingredients,
                        '成本': cost,
                        '备注': note,
                        '分区': section,
                    })
            if rows:
                return rows
        except Exception:
            pass

    text = str(record.get('菜品明细', '') or '').strip()
    if not text or text.lower() == 'nan':
        return []
    parts = [p.strip() for p in re.split(r'[\n,，;；]+', text) if p.strip()]
    return [
        {
            '菜品名称': part,
            '份数': 0,
            '食材明细': '',
            '成本': 0,
            '备注': '',
            '分区': '菜品',
        }
        for part in parts
    ]

def dish_total_cost_for_date(day_str, df_dishes=None):
    df = load_dishes() if df_dishes is None else df_dishes
    if df.empty:
        return 0, False
    records = df[df['日期'].astype(str) == str(day_str)]
    if records.empty:
        return 0, False
    record = records.iloc[-1]
    total = money_amount(record.get('总成本', 0))
    if total <= 0:
        total = sum(row.get('成本', 0) for row in dish_rows_from_record(record))
    return total, total > 0


# ===================== 业务计算层 =====================
def money_value_was_entered(value):
    """空白表示未填写；数字 0 也属于用户明确填写的实际使用金额。"""
    text = str(value).strip()
    return bool(text and text.lower() not in ('nan', 'none'))


def get_monthly_fixed_breakdown(year, month, df_fixed=None):
    """返回实际支出与成本口径；实际水电优先，其次预计，最后实际支出。"""
    df = load_monthly_fixed() if df_fixed is None else df_fixed
    row = df[df['月份'] == f"{year}-{month:02d}"]
    empty = {
        '人工': 0, '房租及物业': 0,
        '水费支出': 0, '电费支出': 0,
        '实际使用水费': None, '预计水费': None,
        '实际使用电费': None, '预计电费': None,
        '计入成本水费': 0, '计入成本电费': 0,
        '煤气费': 0, '预计煤气费': None, '计入成本煤气费': 0,
        '其它固定成本': 0, '固定成本合计': 0, '固定支出合计': 0,
    }
    if row.empty:
        return {key: Decimal(0) if value == 0 else value for key, value in empty.items()}

    record = row.iloc[0]
    labour = money_amount(record.get('人工总额', 0))
    rent = money_amount(record.get('房租总额', 0))
    gas_spent = money_amount(record.get('煤气费', 0))
    other_fixed = money_amount(record.get('其它固定成本', 0))

    water_spent_raw = record.get('水费支出', '')
    electric_spent_raw = record.get('电费支出', '')
    if money_value_was_entered(water_spent_raw) or money_value_was_entered(electric_spent_raw):
        water_spent = money_amount(water_spent_raw)
        electric_spent = money_amount(electric_spent_raw)
    else:
        water_spent = money_amount(record.get('水电费', 0))
        electric_spent = 0

    actual_water_raw = record.get('实际使用水费', '')
    expected_water_raw = record.get('预计水费', '')
    actual_electric_raw = record.get('实际使用电费', '')
    expected_electric_raw = record.get('预计电费', '')
    expected_gas_raw = record.get('预计煤气费', '')
    actual_water = money_amount(actual_water_raw) if money_value_was_entered(actual_water_raw) else None
    expected_water = money_amount(expected_water_raw) if money_value_was_entered(expected_water_raw) else None
    actual_electric = money_amount(actual_electric_raw) if money_value_was_entered(actual_electric_raw) else None
    expected_electric = money_amount(expected_electric_raw) if money_value_was_entered(expected_electric_raw) else None
    expected_gas = money_amount(expected_gas_raw) if money_value_was_entered(expected_gas_raw) else None

    effective_water = actual_water if actual_water is not None else (expected_water if expected_water is not None else water_spent)
    effective_electric = actual_electric if actual_electric is not None else (expected_electric if expected_electric is not None else electric_spent)
    effective_gas = expected_gas if expected_gas is not None else gas_spent
    effective_total = labour + rent + effective_water + effective_electric + effective_gas + other_fixed
    spent_total = labour + rent + water_spent + electric_spent + gas_spent + other_fixed
    return {
        '人工': labour, '房租及物业': rent,
        '水费支出': water_spent, '电费支出': electric_spent,
        '实际使用水费': actual_water, '预计水费': expected_water,
        '实际使用电费': actual_electric, '预计电费': expected_electric,
        '计入成本水费': effective_water, '计入成本电费': effective_electric,
        '煤气费': gas_spent, '预计煤气费': expected_gas, '计入成本煤气费': effective_gas,
        '其它固定成本': other_fixed,
        '固定成本合计': effective_total, '固定支出合计': spent_total,
    }

def get_monthly_fixed_for_date(year, month, df_fixed=None):
    breakdown = get_monthly_fixed_breakdown(year, month, df_fixed)
    utility_cost = breakdown['计入成本水费'] + breakdown['计入成本电费']
    return (
        breakdown['人工'], breakdown['房租及物业'], utility_cost,
        breakdown['计入成本煤气费'], breakdown['其它固定成本']
    )


def safe_float(val):
    """Compatibility name for existing callers; all results are exact Decimal."""
    if str(val).strip().lower() in {'nan','<na>'}:return Decimal(0)
    return decimal_number(val)


def recalculate_revenue_fields(record):
    """Recalculate A/B store totals from raw cash/online fields; override values win when present."""
    def amount(name):
        return money_amount(record.get(name, 0))

    def effective(add_name, override_name):
        override = record.get(override_name, '')
        return amount(override_name) if money_value_was_entered(override) else amount(add_name)

    a_cash = amount('A店现金')
    b_cash = amount('B店现金')
    def effective_wechat(prefix):
        manual = record.get(f'{prefix}微信覆盖', '')
        automatic = record.get(f'{prefix}微信自动', '')
        added = record.get(f'{prefix}微信增加', '')
        if money_value_was_entered(manual):
            return money_amount(manual)
        if money_value_was_entered(automatic):
            return money_amount(automatic) + money_amount(added)
        return money_amount(added)
    a_wechat = effective_wechat('A店')
    a_alipay = effective('A店支付宝增加', 'A店支付宝覆盖')
    b_wechat = effective_wechat('B店')
    b_alipay = effective('B店支付宝增加', 'B店支付宝覆盖')
    student_takeout = amount('学生外卖')
    a_takeout = amount('A店外卖')
    b_takeout = amount('B店外卖')
    record['总现金'] = a_cash + b_cash
    record['总线上'] = a_wechat + a_alipay + b_wechat + b_alipay + student_takeout + a_takeout + b_takeout
    record['A店收入'] = a_cash + a_wechat + a_alipay + a_takeout
    record['B店收入'] = b_cash + b_wechat + b_alipay + b_takeout
    record['收益'] = record['A店收入'] + record['B店收入'] + student_takeout
    return record


def format_customer_count(val):
    text = str(val).strip()
    if not text or text.lower() == 'nan':
        return ""
    try:
        number = decimal_number(text)
    except ValueError:
        return text
    return str(int(number)) if (number == int(number)) else text


def split_item_note(text):
    text = str(text).strip()
    match = re.search(r'\s+备注[:：](.*)$', text)
    if not match:
        return text, ""
    return text[:match.start()].strip(), match.group(1).strip()


def join_item_note(text, note):
    text = str(text).strip()
    note = str(note).strip()
    return f"{text} 备注:{note}" if note else text


def parse_named_amount(text):
    """Parse one ``名称 + 金额`` detail item.

    A space before the amount is optional on purpose.  Daily ledger entries
    are commonly typed as ``采购办公用品100`` on a phone or a compact
    keyboard; the trailing number is still the amount and the preceding text
    remains the description.  The caller owns validation/messages so this
    small helper can also be reused by read-only detail views.
    """
    clean = str(text or '').strip()
    match = re.fullmatch(r'(?P<name>.*?\S)\s*(?P<amount>[+-]?\d+(?:\.\d+)?)', clean)
    if not match:
        return None
    return match.group('name').strip(), money_amount(match.group('amount'))


def calculate_break_even_daily_revenue_increase(projected_net, gross_margin, days_in_month):
    """Return the extra daily Revenue needed to reach break-even.

    ``gross_margin`` is a decimal (for example ``0.35``), not a percent.
    A profit already forecast needs no increase.  A zero/negative gross
    margin cannot turn extra Revenue into profit, so it deliberately returns
    ``None`` instead of presenting a misleading amount.
    """
    try:
        projected_net = decimal_number(projected_net)
        gross_margin = decimal_number(gross_margin)
        days_in_month = int(days_in_month)
    except (TypeError, ValueError, OverflowError):
        return None
    if projected_net >= 0:
        return 0
    if gross_margin <= 0 or days_in_month <= 0:
        return None
    return decimal_divide(decimal_divide(-projected_net, gross_margin), days_in_month)


def day_has_meaningful_data(row):
    """Return whether a daily row contains entered business data.

    Shared fixed-cost allocation is still shown for an empty selected date, but
    empty/zero rows must not inflate active-day averages or standard deviation.
    """
    if row is None:
        return False
    numeric_keys = (
        '收益', '总金额', '收入', '总收入', 'A店收入', 'B店收入', '学生外卖', 'A店外卖', 'B店外卖',
        'A店现金', 'B店现金', '总现金', '总线上', '食材成本', '佐料成本',
        '水电', '其他', '手续费', '总客人数', '新客人数量',
    )
    for key in numeric_keys:
        value = row.get(key, '') if hasattr(row, 'get') else ''
        if str(value).strip() and abs(safe_float(value)) > Decimal('1e-9'):
            return True
    return any(
        str(row.get(key, '')).strip()
        for key in ('食材明细', '佐料明细', '其他明细', '当日备注')
        if hasattr(row, 'get')
    )


def _elapsed_reference(value=None):
    """Coerce a date-like value to a Python ``date`` for deterministic averages."""
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    # PySide6 QDate exposes ``toPython`` on supported versions.
    if hasattr(value, 'toPython'):
        try:
            converted = value.toPython()
            if isinstance(converted, datetime):
                return converted.date()
            if hasattr(converted, 'year') and hasattr(converted, 'month') and hasattr(converted, 'day'):
                return datetime(int(converted.year), int(converted.month), int(converted.day)).date()
        except (TypeError, ValueError, OverflowError):
            pass
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
        try:
            return datetime(int(value.year), int(value.month), int(value.day)).date()
        except (TypeError, ValueError, OverflowError):
            pass
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError, OverflowError):
        return datetime.now().date()


def elapsed_month_days(year, month, anchor_date=None, as_of=None):
    """Return inclusive calendar days elapsed in a month.

    Completed months use their full length; the current month runs through the
    day before the reference date; future months return one as a divide-by-zero guard. The
    ``anchor_date`` name is retained for callers from earlier desktop builds.
    """
    try:
        year, month = int(year), int(month)
        reference = _elapsed_reference(as_of if as_of is not None else anchor_date)
        days_in_month = calendar.monthrange(year, month)[1]
        if (year, month) < (reference.year, reference.month):
            return days_in_month
        if (year, month) > (reference.year, reference.month):
            return 1
        return max(1, min(reference.day - 1, days_in_month))
    except (TypeError, ValueError, OverflowError):
        return 1


def elapsed_week_days(target_date, as_of=None):
    """Return inclusive calendar days elapsed in the week containing *target_date*."""
    try:
        reference = _elapsed_reference(as_of)
        target = _elapsed_reference(target_date)
        week_start = target - timedelta(days=target.weekday())
        week_end = week_start + timedelta(days=6)
        if reference < week_start:
            return 1
        if reference > week_end:
            return 7
        return max(1, (reference - week_start).days)
    except (TypeError, ValueError, OverflowError):
        return 1


def elapsed_year_days(year, anchor_date=None, as_of=None):
    """Return inclusive calendar days elapsed in a year."""
    try:
        year = int(year)
        reference = _elapsed_reference(as_of if as_of is not None else anchor_date)
        days_in_year = 366 if calendar.isleap(year) else 365
        if year < reference.year:
            return days_in_year
        if year > reference.year:
            return 1
        return max(1, (reference - datetime(year, 1, 1).date()).days)
    except (TypeError, ValueError, OverflowError):
        return 1


def calc_day_metrics(day_str, df_daily=None, df_fixed=None):
    df = load_daily() if df_daily is None else df_daily
    row = df[df['日期'] == day_str]
    if row.empty:
        # Keep a selected blank day visible as zero revenue with its shared
        # fixed-cost allocation, matching the web dashboard behaviour.
        row = pd.Series({'日期': day_str, '收益': 0, '总金额': 0})
    else:
        row = row.iloc[0]

    date_obj = datetime.strptime(day_str, "%Y-%m-%d")
    fixed = get_monthly_fixed_breakdown(date_obj.year, date_obj.month, df_fixed)
    l = fixed['人工']
    r = fixed['房租及物业']
    water_fixed = fixed['计入成本水费']
    electric_fixed = fixed['计入成本电费']
    g = fixed['计入成本煤气费']
    of = fixed['其它固定成本']
    dim = calendar.monthrange(date_obj.year, date_obj.month)[1]

    # Daily profit allocates the actual paid fixed costs across calendar days.
    daily_fixed = decimal_divide(fixed['固定支出合计'], dim) if dim > 0 else 0

    # Older app versions could save a total-only entry under 总金额.
    # Prefer the current 收益 value, but preserve that legacy income when
    # 收益 is blank/zero and no channel breakdown exists.
    rev = money_amount(row.get('收益', 0))
    if abs(rev) < Decimal('1e-9') and abs(money_amount(row.get('总金额', 0))) > Decimal('1e-9'):
        rev = money_amount(row.get('总金额', 0))
    food = money_amount(row.get('食材成本', 0))
    spice = money_amount(row.get('佐料成本', 0))
    daily_water = money_amount(row.get('水电', 0))
    other = money_amount(row.get('其他', 0))
    fees = money_amount(row.get('手续费', 0))
    new_customers = safe_float(row.get('新客人数量', 0))
    total_customers = safe_float(row.get('总客人数', 0))
    returning_customers = max(total_customers - new_customers, 0)

    var_cost = food + spice + daily_water + other + fees
    total_cost = var_cost + daily_fixed
    gross = rev - (food + spice + fees)
    net = rev - total_cost

    return {
        '收益': rev, '毛利': gross, '总成本': total_cost, '净利润': net, '固定分摊': daily_fixed,
        '变动成本': var_cost, '食材成本': food, '佐料成本': spice,
        '新客人数量': new_customers, '总客人数': total_customers,
        '老客人数': returning_customers,
        '新客比例(%)': decimal_divide(new_customers, total_customers) * 100 if total_customers else 0,
        '老客比例(%)': decimal_divide(returning_customers, total_customers) * 100 if total_customers else 0,
        '客单价(平均)': decimal_divide(rev, total_customers) if total_customers else 0,
        '开销明细': {k: v for k, v in
                      {'食材成本': food, '佐料成本': spice, '日结水电': daily_water, '其他': other, '手续费／抽成': fees,
                      '人工分摊': decimal_divide(l, dim) if dim else 0, '房租分摊': decimal_divide(r, dim) if dim else 0,
                      '水费分摊（实际使用）' if fixed['实际使用水费'] is not None else '水费分摊（支出）': decimal_divide(water_fixed, dim) if dim else 0,
                      '电费分摊（实际使用）' if fixed['实际使用电费'] is not None else '电费分摊（支出）': decimal_divide(electric_fixed, dim) if dim else 0,
                      '月煤气分摊': decimal_divide(g, dim) if dim else 0,
                      '其它固定分摊': decimal_divide(of, dim) if dim else 0}.items() if v > 0}
    }


def calc_week_summary(day_str, df_daily=None, df_fixed=None):
    df = load_daily() if df_daily is None else df_daily
    fixed_df = load_monthly_fixed() if df_fixed is None else df_fixed
    target_date = datetime.strptime(day_str, "%Y-%m-%d").date()
    start_of_week = target_date - pd.Timedelta(days=target_date.weekday())
    end_of_week = start_of_week + pd.Timedelta(days=6)
    date_values = pd.to_datetime(df['日期'], errors='coerce')
    today = datetime.now().date()
    # Pre-created rows for future dates must not inflate the current week or
    # make an unelapsed day appear to have revenue/cost data.
    week_df = df[
        (date_values.dt.date >= start_of_week)
        & (date_values.dt.date <= end_of_week)
        & (date_values.dt.date <= today)
    ]
    if week_df.empty: return None

    metrics = [
        calc_day_metrics(row['日期'], df, fixed_df)
        for _, row in week_df.iterrows()
        if day_has_meaningful_data(row)
    ]
    if not metrics: return None

    total_net = sum(m['净利润'] for m in metrics)
    total_fixed = sum(m['固定分摊'] for m in metrics)
    elapsed_days = elapsed_week_days(target_date)
    return {
        '本周收益': sum(m['收益'] for m in metrics), '本周毛利': sum(m['毛利'] for m in metrics),
        '本周总成本': sum(m['总成本'] for m in metrics), '本周变动成本': sum(m['变动成本'] for m in metrics),
        '本周固定成本': total_fixed, '本周净利': total_net,
        '日均净利': decimal_divide(total_net, elapsed_days), '活跃天数': len(metrics), '日均天数': elapsed_days
    }


def calc_month_summary(year, month, df_daily=None, df_fixed=None):
    df = load_daily() if df_daily is None else df_daily
    fixed_df = load_monthly_fixed() if df_fixed is None else df_fixed
    date_values = pd.to_datetime(df['日期'], errors='coerce')
    today = datetime.now().date()
    month_df = df[
        (date_values.dt.year == int(year))
        & (date_values.dt.month == int(month))
        & (date_values.dt.date <= today)
    ]
    if month_df.empty: return None

    metrics = []
    food_sum, spice_sum, water_sum, other_sum = 0, 0, 0, 0
    for _, row in month_df.iterrows():
        m = calc_day_metrics(row['日期'], df, fixed_df)
        if m and day_has_meaningful_data(row):
            metrics.append(m)
            food_sum += money_amount(row.get('食材成本', 0))
            spice_sum += money_amount(row.get('佐料成本', 0))
            water_sum += money_amount(row.get('水电', 0))
            other_sum += money_amount(row.get('其他', 0))

    if not metrics: return None

    total_variable = sum(m['变动成本'] for m in metrics)
    active_days = len(metrics)
    fixed = get_monthly_fixed_breakdown(year, month, fixed_df)
    dim = calendar.monthrange(year, month)[1]
    total_fixed = fixed['固定支出合计']
    total_cost = total_variable + total_fixed
    total_net = sum(m['收益'] for m in metrics) - total_cost

    elapsed_days = elapsed_month_days(year, month)
    return {
        '本月收益': sum(m['收益'] for m in metrics), '本月毛利': sum(m['毛利'] for m in metrics),
        '本月总成本': total_cost, '本月变动成本': total_variable,
        '本月固定成本': total_fixed, '本月净利': total_net,
        '日均净利': decimal_divide(total_net, elapsed_days), '活跃天数': active_days, '日均天数': elapsed_days,
        '开销明细': {k: v for k, v in
                     {'食材成本': food_sum, '佐料成本': spice_sum, '日结水电': water_sum, '其他': other_sum,
                      '人工总额(分摊)': (decimal_divide(fixed['人工'], dim)) * active_days if dim else 0,
                      '房租总额(分摊)': (decimal_divide(fixed['房租及物业'], dim)) * active_days if dim else 0,
                      '水费(实际使用分摊)' if fixed['实际使用水费'] is not None else '水费(支出分摊)': (decimal_divide(fixed['计入成本水费'], dim)) * active_days if dim else 0,
                      '电费(实际使用分摊)' if fixed['实际使用电费'] is not None else '电费(支出分摊)': (decimal_divide(fixed['计入成本电费'], dim)) * active_days if dim else 0,
                      '月煤气费(分摊)': (decimal_divide(fixed['计入成本煤气费'], dim)) * active_days if dim else 0,
                      '其它固定成本(分摊)': (decimal_divide(fixed['其它固定成本'], dim)) * active_days if dim else 0}.items() if v > 0}
    }


def calc_year_summary(year, df_daily=None, df_fixed=None):
    df = load_daily() if df_daily is None else df_daily
    fixed_df = load_monthly_fixed() if df_fixed is None else df_fixed
    date_values = pd.to_datetime(df['日期'], errors='coerce')
    today = datetime.now().date()
    year_df = df[
        (date_values.dt.year == int(year))
        & (date_values.dt.date <= today)
    ]
    if year_df.empty: return None

    metrics, unique_months = [], set()
    for _, row in year_df.iterrows():
        m = calc_day_metrics(row['日期'], df, fixed_df)
        if m and day_has_meaningful_data(row):
            metrics.append(m)
            unique_months.add(row['日期'][:7])

    if not metrics: return None
    total_variable = sum(m['变动成本'] for m in metrics)
    # Do not charge an annual snapshot with fixed-cost rows from months that
    # have not happened yet.  The current month keeps its configured monthly
    # amount, matching the month overview's existing fixed-cost convention.
    reference = datetime.now().date()
    paid_fixed_total = sum(
        get_monthly_fixed_breakdown(year, month, fixed_df)['固定支出合计']
        for month in range(1, 13)
        if year < reference.year or (year == reference.year and month <= reference.month)
    )
    total_fixed = paid_fixed_total
    total_cost = total_variable + total_fixed
    total_net = sum(m['收益'] for m in metrics) - total_cost
    elapsed_days = elapsed_year_days(year)
    return {
        '本年收益': sum(m['收益'] for m in metrics), '本年毛利': sum(m['毛利'] for m in metrics),
        '本年总成本': total_cost,
        '本年总支出': total_variable + paid_fixed_total,
        '本年变动成本': total_variable,
        '本年固定成本': total_fixed, '本年净利': total_net,
        '本年固定支出': paid_fixed_total,
        '月均净利': decimal_divide(total_net, len(unique_months)), '日均净利': decimal_divide(total_net, elapsed_days),
        '活跃天数': len(metrics), '日均天数': elapsed_days, '活跃月数': len(unique_months)
    }



# ===================== 全局单位列表（三处同步） =====================
UNITS_LIST = ['斤', '公斤', '个', '袋', '打', '盒', '两', '克', '千克', '瓶', '箱', '只', '条', '份', '件', '颗', '根', '把', '扎', '碗', '盘', '升', 'ml', 'L']


def get_unit_pattern():
    """根据全局单位列表生成解析用正则，确保新增/修改单位后录入解析同步。"""
    legacy_units = ['公斤', '千克', '毫升', '升', '斤两', 'kg', 'KG', 'g', 'ml', 'mL', 'L']
    units = []
    for unit in UNITS_LIST + legacy_units:
        unit = str(unit).strip()
        if unit and unit not in units:
            units.append(unit)
    units.sort(key=len, reverse=True)
    return '(' + '|'.join(re.escape(unit) for unit in units) + ')'


_INVENTORY_READ_CACHE = {}


def _inventory_read_frames(path):
    # FIFO preview may run on each input edit. Reuse the immutable read snapshot
    # until either local save or cloud synchronization replaces the workbook.
    stat = os.stat(path)
    signature = (path, stat.st_mtime_ns, stat.st_size)
    if _INVENTORY_READ_CACHE.get('signature') != signature:
        with internal_sync_lock(path):
            frames = _read_internal_frames(path)
        _INVENTORY_READ_CACHE.clear()
        _INVENTORY_READ_CACHE.update(signature=signature, frames=frames)
    return _INVENTORY_READ_CACHE['frames']


def _load_inventory_payload():
    path = str(INTERNAL_FILE_PATH or '').strip()
    if not path or not os.path.exists(path):
        return {}
    frames = _inventory_read_frames(path)
    payload = _internal_payload_for_identity(
        frames, FIXED_CLOUD_DATASET_ID, ('global', 'inventory')
    ) or {}
    return payload if isinstance(payload, dict) else {}


def _inventory_key(category, name, unit):
    return str(category or '食材'), str(name or '').strip(), str(unit or '').strip()


def _inventory_is_voided(row):
    return str(row.get('voided', '')).strip().lower() in {'true', '1'}


def load_inventory_adjustments(include_voided=False):
    return [dict(row) for row in _load_inventory_payload().get('adjustments', [])
            if isinstance(row, dict) and str(row.get('name') or row.get('名称') or '').strip()
            and (include_voided or not _inventory_is_voided(row))]


def _inventory_adjustment_kind(row):
    raw = str(row.get('kind') or row.get('adjustment_kind') or row.get('类型') or 'loss').lower()
    return 'normal' if raw in ('normal', 'normal_use', '正常使用') else 'loss'


def load_inventory_overrides(include_voided=False):
    return [dict(row) for row in _load_inventory_payload().get('overrides', [])
            if isinstance(row, dict) and str(row.get('name') or row.get('名称') or '').strip()
            and (include_voided or not _inventory_is_voided(row))]


def _inventory_normalize_entries(rows, include_voided=False):
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or (not include_voided and _inventory_is_voided(row)):
            continue
        name = str(row.get('name') or row.get('名称') or '').strip()
        date = str(row.get('date') or row.get('日期') or '').strip()
        try:
            date = datetime.strptime(date.replace('/', '-')[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            continue
        try:
            quantity = decimal_number(row.get('quantity', row.get('数量', 0)) or 0)
        except (TypeError, ValueError):
            continue
        if not name or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) or not (0 < quantity < float('inf')):
            continue
        raw_total = row.get('total', row.get('总价', ''))
        raw_price = row.get('unit_price', row.get('单价', ''))
        total = _inventory_optional_price(raw_total) if raw_total not in ('', None) else None
        price = _inventory_optional_price(raw_price)
        if raw_total in ('', None) and price is not None:
            total = money_amount(quantity * unit_price_value(price))
        if total is not None: total = money_amount(total)
        price_known = row.get('price_known') is not False and total is not None
        stable_id = 'legacy:' + hashlib.sha256((str(index) + exact_json_dumps(row, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:20]
        result.append({**row, 'id': str(row.get('id') or stable_id), 'date': date,
                       'category': '佐料' if str(row.get('category') or row.get('分类')) == '佐料' else '食材',
                       'name': name, 'quantity': quantity, 'unit': str(row.get('unit') or row.get('单位') or '').strip(),
                       'unit_price': unit_price_value(price if price is not None else total / quantity) if price_known else None,
                       'total': total if price_known else None, 'price_known': price_known,
                       'note': str(row.get('note') or row.get('备注') or '').strip()})
    return result


def load_inventory_entries(include_voided=False):
    return _inventory_normalize_entries(_load_inventory_payload().get('entries', []), include_voided)


def save_inventory_entries(entries, adjustments=None, overrides=None, item_settings=None, expected_hash=None):
    require_network_edit()
    path = normalize_excel_path(INTERNAL_FILE_PATH)
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
        identity = ('global', 'inventory')
        previous_payload = _internal_payload_for_identity(frames, FIXED_CLOUD_DATASET_ID, identity) or {}
        if expected_hash is not None and _payload_and_hash(previous_payload)[1] != expected_hash:
            raise ExcelAccessError('库存已被其他窗口或设备更新，请刷新库存后重新提交；未保存的单据仍保留。')
        payload = {**previous_payload,
            'entries': list(entries),
            'adjustments': list(previous_payload.get('adjustments') or []) if adjustments is None else list(adjustments),
            'overrides': list(previous_payload.get('overrides') or []) if overrides is None else list(overrides),
            'updated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        }
        if item_settings is not None:
            payload['item_settings'] = list(item_settings)
        validate_money_changes(payload, previous_payload)
        payload = prepare_money_save(payload, previous_payload)
        payload_json, digest = _payload_and_hash(payload)
        frames['__global_records'] = _replace_internal_record(frames['__global_records'], FIXED_CLOUD_DATASET_ID, '记录类型', 'inventory', payload_json, digest)
        if _desktop_cloud_role() != 'admin':
            _append_internal_audit_records(frames, FIXED_CLOUD_DATASET_ID, [identity], {identity: previous_payload}, '库存单据')
        meta = frames.get('__meta', pd.DataFrame(columns=INTERNAL_META_COLUMNS))
        meta = meta[meta['dataset_id'].astype(str) != FIXED_CLOUD_DATASET_ID].copy()
        frames['__meta'] = pd.concat([meta, pd.DataFrame([{'dataset_id': FIXED_CLOUD_DATASET_ID, 'schema_version': 2,
            'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}])], ignore_index=True)
        _write_internal_frames(path, frames)
    _set_internal_sync_pending(True)
    trigger_embedded_sync_now()


def _inventory_save_payload(payload, expected_hash=None):
    # Read-modify-write callers keep all historical/voided rows and all unknown
    # metadata. Only the inventory arrays/settings are user-editable here.
    save_inventory_entries(payload.get('entries', []), payload.get('adjustments', []),
                           payload.get('overrides', []), payload.get('item_settings', []), expected_hash=expected_hash)


def save_inventory_adjustments(adjustments):
    save_inventory_entries(_load_inventory_payload().get('entries', []), adjustments=adjustments)


def save_inventory_overrides(overrides):
    save_inventory_entries(_load_inventory_payload().get('entries', []), overrides=overrides)


def _inventory_day_sheet(sheet_name):
    """Use the browser's canonical source for inventory purchase/dish adapters.

    Cloud records arrive in sequence order, which the internal Excel preserves.
    Older stores lack sequence/version columns; original row order is their rank.
    Stored daily data and financial-report merge behavior remain unchanged.
    """
    path = str(INTERNAL_FILE_PATH or '').strip()
    if path and os.path.exists(path):
        frames = _inventory_read_frames(path)
        frame = frames.get('__day_records', pd.DataFrame())
        if {'dataset_id', '日期', 'payload_json'}.issubset(frame.columns):
            selected = frame[frame['dataset_id'].astype(str) == str(FIXED_CLOUD_DATASET_ID)]
            daily_rows, daily_ranks, daily_sources, direct_sources, dish_fallback = {}, {}, {}, {}, {}
            records = []
            def js_text(value):
                if isinstance(value, list): return ','.join('' if item is None else js_text(item) for item in value)
                if isinstance(value, dict): return '[object Object]'
                return str(value)
            def entered(value):
                return value is not None and js_text(value).strip() != '' and js_text(value).lower() not in ('nan', 'none')
            def normalize_day(value):
                date = pd.to_datetime(str(value or '').strip(), errors='coerce')
                return '' if pd.isna(date) else date.strftime('%Y-%m-%d')
            legacy_fields = {'日期', '收益', '总金额', '收入', '总收入', 'A店收入', 'B店收入', '学生外卖', 'A店外卖', 'B店外卖', '总客人数', '食材成本', '佐料成本'}
            for record_index, (_, row) in enumerate(selected.iterrows()):
                key = str(row.get('日期') or '').strip()
                payload = _decode_internal_payload(row.get('payload_json'), key)
                records.append((key, payload)); direct_sources[key] = record_index
                source_rows = payload.get('daily', [])
                if not isinstance(source_rows, list): source_rows = []
                if 'daily' not in payload and legacy_fields.intersection(payload): source_rows = [payload]
                for row_index, item in enumerate(source_rows):
                    if not isinstance(item, dict): continue
                    date = normalize_day(item.get('日期') or key)
                    if not date: continue
                    normalized = {**item, '日期': date}
                    rank = (safe_float(row.get('sequence', row.get('seq', 0))), safe_float(row.get('version', row.get('current_version', 0))), record_index, row_index)
                    if date not in daily_ranks or rank >= daily_ranks[date]:
                        previous = daily_rows.get(date)
                        daily_rows[date] = normalized if previous is None else {**previous, **{field: value for field, value in normalized.items() if entered(value)}}
                        daily_ranks[date] = rank; daily_sources[date] = record_index
                for item in payload.get('dishes', []) if isinstance(payload.get('dishes', []), list) else []:
                    if not isinstance(item, dict): continue
                    date = normalize_day(item.get('日期') or key)
                    if date: dish_fallback[date] = {**item, '日期': date}
            if sheet_name == 'daily': return pd.DataFrame([daily_rows[date] for date in sorted(daily_rows)])
            if sheet_name == 'dishes':
                result = []
                for date in sorted(set(daily_sources) | set(dish_fallback)):
                    source_index = daily_sources.get(date, direct_sources.get(date))
                    if source_index is None:
                        if date in dish_fallback: result.append(dish_fallback[date])
                        continue
                    key, payload = records[source_index]
                    # An existing canonical source with no matching dishes means
                    # no consumption; a later packed/dishes-only row cannot revive it.
                    matches = [item for item in payload.get('dishes', []) if isinstance(item, dict) and normalize_day(item.get('日期') or key) == date] if isinstance(payload.get('dishes', []), list) else []
                    if matches: result.append({**matches[-1], '日期': date})
                return pd.DataFrame(result)
            return pd.DataFrame()
    return load_daily() if sheet_name == 'daily' else load_dishes()


def _inventory_optional_price(value):
    if isinstance(value, bool) or str(value).strip().lower() in {'nan','inf','infinity','-inf','-infinity'}:
        return None
    if value in ('', None):
        return None
    try:
        result = decimal_number(value)
        return result if 0 <= result < float('inf') else None
    except (ValueError, TypeError):
        return None


def _inventory_detail_items(raw):
    """Accept both web JSON details and desktop text without guessing quantities."""
    value = raw
    if isinstance(raw, str):
        try:
            value = exact_json_loads(raw)
        except (ValueError, TypeError):
            value = raw
    if isinstance(value, list):
        result = []
        for row in value:
            if not isinstance(row, dict):
                continue
            quantity = safe_float(row.get('quantity', row.get('数量', 0)))
            total = row.get('total', row.get('总价', ''))
            price = row.get('price', row.get('unit_price', row.get('单价', '')))
            result.append({'name': str(row.get('name') or row.get('名称') or row.get('食材名称') or '').strip(),
                           'quantity': quantity, 'unit': str(row.get('unit') or row.get('单位') or '').strip(),
                           'total': total, 'unit_price': price, 'note': str(row.get('note') or row.get('备注') or '')})
        return result
    result = []
    pattern = re.compile(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + get_unit_pattern() + r'?\s+(\d+(?:\.\d+)?)$')
    for token in re.split(r'[,，;；\n]', str(raw or '')):
        clean, note = split_item_note(token.strip())
        if not clean:
            continue
        match = pattern.match(clean)
        if match:
            quantity, total = decimal_number(match.group(2)), decimal_number(match.group(4))
            result.append({'name': match.group(1).strip(), 'quantity': quantity, 'unit': match.group(3) or '',
                           'total': total, 'unit_price': total / quantity if quantity else '', 'note': note})
        else:
            amount = re.match(r'^(.+?)(?:\s+)?(\d+(?:\.\d+)?)$', clean) if not re.fullmatch(r'\d+(?:\.\d+)?', clean) else None
            result.append({'name': amount.group(1).strip() if amount else clean, 'quantity': 0, 'unit': '', 'total': decimal_number(amount.group(2)) if amount else '', 'unit_price': '', 'note': note})
    return result


def _inventory_dish_rows(record):
    raw = record.get('菜品数据', '')
    if isinstance(raw, str):
        try:
            raw = exact_json_loads(raw)
        except (ValueError, TypeError):
            raw = None
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    return dish_rows_from_record(record)


def _inventory_operation_stamp(rows):
    # Milliseconds in UTC, monotonic relative to prior operations even if the
    # device clock moved backwards between two saves.
    latest = datetime.now().timestamp()
    for row in rows:
        try:
            latest = max(latest, datetime.fromisoformat(str(row.get('recorded_at') or '').replace('Z', '+00:00')).timestamp() + 0.001)
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.utcfromtimestamp(latest).isoformat(timespec='milliseconds') + 'Z'


def _inventory_purchase_entries():
    """Purchases are virtual receipts: editing/deleting the purchase updates stock once."""
    entries, pending = [], []
    for row_index, (_, record) in enumerate(_inventory_day_sheet('daily').iterrows()):
        day = str(record.get('日期') or '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            continue
        for index, item in enumerate(_inventory_detail_items(record.get('食材明细', ''))):
            name, quantity, unit = item['name'], item['quantity'], item['unit']
            if not name:
                continue
            if not unit or not (0 < quantity < float('inf')):
                pending.append({'date': day, 'detail': name})
                continue
            total, price = item['total'], item['unit_price']
            amount = _inventory_optional_price(total) if total not in ('', None) else (quantity * unit_price_value(_inventory_optional_price(price)) if _inventory_optional_price(price) is not None else None)
            price_known = amount is not None
            if price_known:
                total, price = money_amount(amount), unit_price_value(_inventory_optional_price(price) if _inventory_optional_price(price) is not None else amount / quantity)
            entries.append({'id': f'purchase:{day}:{row_index}:{index}', 'date': day, 'category': '食材',
                            'name': name, 'quantity': quantity, 'unit': unit,
                            'unit_price': price if price_known else None, 'total': total if price_known else None,
                            'price_known': price_known, 'note': item['note'], 'source': 'purchase'})
    return entries, pending


def _inventory_receipts(payload=None):
    purchases, _pending = _inventory_purchase_entries()
    payload = _load_inventory_payload() if payload is None else payload
    return _inventory_normalize_entries(payload.get('entries', []), include_voided=True) + purchases


def _inventory_fifo(entries, usage, adjustments=(), overrides=(), as_of=None):
    """Replay stock in business-date / operation order, preserving receipt traceability."""
    states, movements, events = {}, [], []
    def number(row, field, alias=''):
        try:
            value = decimal_number(row.get(field, row.get(alias, 0)) or 0)
            return value if value == value and abs(value) != float('inf') else 0
        except (TypeError, ValueError):
            return 0
    def identity(row):
        return _inventory_key(row.get('category') or row.get('分类'), row.get('name') or row.get('名称'), row.get('unit') or row.get('单位'))
    def state_for(key):
        if key not in states:
            states[key] = {'lots': [], 'debt': 0, 'received': 0, 'dish': 0, 'normal': 0, 'loss': 0, 'last_date': '', 'total': 0}
        return states[key]
    for priority, kind, rows in ((0, 'receipt', entries), (1, 'dish', usage), (2, 'adjustment', adjustments), (3, 'override', overrides)):
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or _inventory_is_voided(row):
                continue
            day = str(row.get('date') or row.get('日期') or '').strip()
            try:
                day = datetime.strptime(day.replace('/', '-')[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                continue
            key = identity(row)
            if key[1] and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) and (not as_of or day <= as_of):
                event_priority, order = priority, index
                if row.get('recorded_at'):
                    try:
                        order = datetime.fromisoformat(str(row['recorded_at']).replace('Z', '+00:00')).timestamp()
                        event_priority = 4
                    except (ValueError, TypeError, OverflowError):
                        pass
                events.append((day, event_priority, order, index, kind, key, row))
    def take(state, quantity):
        remaining, known_cost, unknown, layers = quantity, 0, 0, []
        for lot in state['lots']:
            amount = min(remaining, lot['remaining'])
            if amount <= Decimal('1e-9'):
                continue
            lot['remaining'] -= amount
            remaining -= amount
            if lot['unit_price'] is None:
                unknown += amount
            else:
                lot['consumed_quantity'] += amount
                allocated = money_amount(lot['original_total'] * lot['consumed_quantity'] / lot['original_quantity'])
                allocation = allocated - lot['allocated_cost']
                lot['allocated_cost'] = allocated
                lot['remaining_cost'] = lot['original_total'] - allocated
                known_cost += allocation
            layers.append({**lot, 'quantity': amount, 'cost': None if lot['unit_price'] is None else allocation})
            if remaining <= Decimal('1e-9'):
                break
        state['lots'] = [lot for lot in state['lots'] if lot['remaining'] > Decimal('1e-9')]
        shortage = max(0, remaining)
        if remaining > Decimal('1e-9'):
            state['debt'] += remaining
            unknown += remaining
            layers.append({'date': '', 'quantity': remaining, 'unit_price': None, 'id': 'shortage', 'source': 'shortage'})
        return known_cost, unknown, layers, shortage
    def layer(row, day, index, quantity, price, source, original_quantity=None, original_total=None):
        original_quantity = quantity if original_quantity is None else original_quantity
        consumed = original_quantity - quantity
        total = money_amount(original_total if original_total is not None else original_quantity * price) if price is not None else None
        allocated = money_amount(total * consumed / original_quantity) if total is not None and original_quantity else Decimal(0)
        return {**row, 'date': day, 'id': str(row.get('id') or f'{source}:{index}'), 'remaining': quantity,
                'unit_price': unit_price_value(price) if price is not None else None, 'source': str(row.get('source') or source),
                'original_quantity': original_quantity, 'original_total': total, 'consumed_quantity': consumed,
                'allocated_cost': allocated, 'remaining_cost': total - allocated if total is not None else None}
    def emit(row, day, key, kind, quantity, direction, cost, unknown, layers, shortage=0):
        movements.append({**row, 'date': day, 'category': key[0], 'name': key[1], 'unit': key[2],
                          'quantity': quantity, 'kind': kind, 'direction': direction,
                          'change': quantity if direction == 'in' else -quantity,
                          'known_cost': cost, 'unknown_quantity': unknown, 'shortage_quantity': shortage,
                          'cost': None if unknown > Decimal('1e-9') else cost, 'layers': layers,
                          'balance_after': sum(lot['remaining'] for lot in state_for(key)['lots']) - state_for(key)['debt']})
    for day, priority, order, index, kind, key, row in sorted(events, key=lambda event: event[:4]):
        row = {**row, 'id': str(row.get('id') or f'legacy:{kind}:{index}')}
        state = state_for(key)
        quantity = max(0, number(row, 'quantity', '数量'))
        if kind == 'receipt':
            if quantity <= 0:
                continue
            raw_total = row.get('total', row.get('总价', ''))
            raw_price = row.get('unit_price', row.get('单价', ''))
            amount = _inventory_optional_price(raw_total) if raw_total not in ('', None) else (quantity * unit_price_value(_inventory_optional_price(raw_price)) if _inventory_optional_price(raw_price) is not None else None)
            price_known = row.get('price_known') is not False and amount is not None
            total = money_amount(amount) if price_known else Decimal(0)
            price = unit_price_value(_inventory_optional_price(raw_price) if _inventory_optional_price(raw_price) is not None else total / quantity) if price_known else None
            state['received'] += quantity
            state['total'] += total
            state['last_date'] = day
            replenishment = min(quantity, state['debt'])
            state['debt'] -= replenishment
            remaining = quantity - replenishment
            lot = layer(row, day, index, remaining, price, 'manual', quantity, total)
            if remaining > Decimal('1e-9'):
                state['lots'].append(lot)
            emit(row, day, key, 'receipt', quantity, 'in', total, 0 if price_known else quantity,
                 [{**lot, 'quantity': quantity}])
        elif kind == 'override':
            current = sum(lot['remaining'] for lot in state['lots']) - state['debt']
            difference = quantity - current
            if difference < -Decimal('1e-9'):
                cost, unknown, layers, shortage = take(state, -difference)
                emit({**row, 'previous_quantity': current}, day, key, 'stocktake', -difference, 'out', cost, unknown, layers, shortage)
            elif difference > Decimal('1e-9'):
                price = _inventory_optional_price(row.get('unit_price', row.get('单价', '')))
                if row.get('price_known') is False:
                    price = None
                if price is not None: price = unit_price_value(price)
                paid_debt = min(difference, state['debt'])
                state['debt'] -= paid_debt
                lot = layer(row, day, index, difference - paid_debt, price, 'stocktake', difference)
                if lot['remaining'] > Decimal('1e-9'):
                    state['lots'].append(lot)
                emit({**row, 'previous_quantity': current}, day, key, 'stocktake', difference, 'in',
                     money_amount(difference * price) if price is not None else 0, difference if price is None else 0,
                     [{**lot, 'quantity': difference}])
            else:
                emit({**row, 'previous_quantity': current}, day, key, 'stocktake', 0, 'in', 0, 0, [])
        elif quantity > 0:
            movement_kind = _inventory_adjustment_kind(row) if kind == 'adjustment' else 'dish'
            state[movement_kind] += quantity
            cost, unknown, layers, shortage = take(state, quantity)
            emit(row, day, key, movement_kind, quantity, 'out', cost, unknown, layers, shortage)
    return {'states': states, 'movements': movements}


def _inventory_fifo_snapshot(usage=None, adjustments=None, payload=None, as_of=None):
    payload = _load_inventory_payload() if payload is None else payload
    return _inventory_fifo(_inventory_receipts(payload), _inventory_consumption_rows() if usage is None else usage,
                           payload.get('adjustments', []) if adjustments is None else adjustments, payload.get('overrides', []),
                           as_of=as_of or datetime.now().strftime('%Y-%m-%d'))


def _inventory_fifo_description(movement):
    layers = movement.get('layers', [])
    return '；'.join(
        (f"{layer.get('document_no') or layer['date']} {layer['quantity']:g} × {layer['unit_price']:.6f}元" if layer['unit_price'] is not None else
         f"{layer['quantity']:g}{movement.get('unit', '')}成本未知（{'缺入库记录' if not layer['date'] else '原入库价未知'}）")
        for layer in layers
    )


def _inventory_fifo_average_price(movement):
    """A display-only exact average; never feed the rounded display into costing."""
    if decimal_number(movement.get('unknown_quantity', 0)) > Decimal('1e-9'):
        return None
    quantity = decimal_number(movement.get('quantity', sum(decimal_number(row.get('quantity', 0)) for row in movement.get('layers', []))))
    return decimal_number(movement.get('known_cost', 0)) / quantity if quantity > Decimal('1e-9') else None


def _inventory_fifo_cost_text(movement):
    if movement.get('unknown_quantity', 0) > Decimal('1e-9'):
        return f"已知 {movement.get('known_cost', 0):.2f}；另 {movement['unknown_quantity']:g}{movement.get('unit', '')} 未知"
    text = f"{movement.get('known_cost', 0):.2f}"
    average = _inventory_fifo_average_price(movement)
    if average is not None and movement.get('direction') != 'in':
        text += f"；均价 {money_amount(average):.2f} 元/{movement.get('unit') or '单位'}"
    return text


def _inventory_fifo_table_rows(movements):
    names = {'receipt': '采购入库', 'dish': '菜品出库', 'normal': '领用出库', 'loss': '损耗出库', 'stocktake': '盘点'}
    return [[m['date'], names.get(m['kind'], m['kind']), m['name'], f"{m['quantity']:g}{m['unit']}",
             _inventory_fifo_description(m), _inventory_fifo_cost_text(m)] for m in movements if m.get('kind') in ('dish', 'normal', 'loss')]


def _inventory_consumption_rows(dishes_override=None):
    result = []
    dishes = _inventory_day_sheet('dishes') if dishes_override is None else dishes_override
    exact, named = {}, {}
    for entry in _inventory_receipts():
        exact.setdefault((entry['name'], entry['unit']), set()).add(entry['category'])
        named.setdefault(entry['name'], set()).add(entry['category'])
    dictionary = {}
    try:
        for _, item in load_ingredients().iterrows():
            dictionary.setdefault(str(item.get('词条名称') or '').strip(), set()).add(str(item.get('分类') or '食材'))
    except Exception:
        pass
    for _, record in dishes.iterrows():
        day = str(record.get('日期') or '')
        for dish_index, dish in enumerate(_inventory_dish_rows(record)):
            for item_index, item in enumerate(_inventory_detail_items(dish.get('食材明细', ''))):
                name, unit, quantity = item['name'], item['unit'], item['quantity']
                if not name or not (0 < quantity < float('inf')):
                    continue
                categories = exact.get((name, unit)) or named.get(name) or dictionary.get(name) or {'食材'}
                result.append({'id': f'dish:{day}:{dish_index}:{item_index}', 'date': day,
                               'category': '佐料' if categories == {'佐料'} else '食材', 'name': name,
                               'quantity': quantity, 'unit': unit, 'dish': str(dish.get('菜品名称') or '未命名菜品'),
                               'servings': safe_float(dish.get('份数', 0))})
    return result


def calculate_inventory_balances():
    payload = _load_inventory_payload()
    snapshot = _inventory_fifo_snapshot(payload=payload)
    settings = {_inventory_key(row.get('category'), row.get('name'), row.get('unit')): row
                for row in payload.get('item_settings', []) if isinstance(row, dict)}
    balances = []
    for (category, name, unit), state in snapshot['states'].items():
        remaining = sum(lot['remaining'] for lot in state['lots']) - state['debt']
        unknown = sum(lot['remaining'] for lot in state['lots'] if lot['unit_price'] is None)
        known = sum(lot['remaining_cost'] for lot in state['lots'] if lot['unit_price'] is not None)
        threshold = _inventory_optional_price(settings.get((category, name, unit), {}).get('min_quantity'))
        status = '负库存' if remaining < -Decimal('1e-9') else '缺货' if remaining <= Decimal('1e-9') else '低于安全库存' if threshold is not None and remaining < threshold else '正常'
        if unknown > Decimal('1e-9'):
            status += ' / 待定价'
        balances.append({'分类': category, '名称': name, '单位': unit, '累计入库': state['received'],
                         '累计消耗': state['dish'], '正常使用': state['normal'], '损耗': state['loss'],
                         '当前剩余': remaining, '入库金额': state['total'], '最近入库': state['last_date'],
                         '安全库存': threshold, '已知库存价值': known, '待定价数量': unknown,
                         '下批单价': state['lots'][0]['unit_price'] if state['lots'] else None, '库存状态': status})
    return sorted(balances, key=lambda row: (row['分类'], row['名称'], row['单位']))


def refresh_all_unit_combos(rename_map=None, source_callback=None):
    """刷新当前所有已打开界面的单位下拉框。"""
    app = QApplication.instance()
    if not app:
        if source_callback:
            source_callback(rename_map)
        return

    refresh_methods = []
    clean_ingredient_widgets = set()
    for widget in app.allWidgets():
        try:
            if callable(getattr(widget, '_refresh_ingredient_unit_combos', None)) and hasattr(widget, '_snapshot'):
                if not widget.has_unsaved_changes():
                    clean_ingredient_widgets.add(id(widget))
        except Exception:
            pass
        for method_name in ('_refresh_unit_combos', '_refresh_ingredient_unit_combos'):
            method = getattr(widget, method_name, None)
            if callable(method):
                refresh_methods.append((widget, method))

    called = set()
    for widget, method in refresh_methods:
        key = (id(widget), getattr(method, '__name__', ''))
        if key in called:
            continue
        called.add(key)
        method(rename_map)
        if id(widget) in clean_ingredient_widgets and callable(getattr(widget, '_get_table_state', None)):
            widget._snapshot = widget._get_table_state()

    if source_callback and not any(getattr(method, '__self__', None) is getattr(source_callback, '__self__', None)
                                   and getattr(method, '__name__', '') == getattr(source_callback, '__name__', '')
                                   for _, method in refresh_methods):
        source_callback(rename_map)


def unit_join(quantity, unit):
    unit = str(unit).strip()
    quantity = str(quantity).strip()
    if not unit:
        return quantity
    if re.search(r'\s', unit) or re.match(r'^\d', unit):
        return f"{quantity} {unit}"
    return f"{quantity}{unit}"


def unit_candidates(extra_units=None):
    units = []
    for unit in list(UNITS_LIST) + list(extra_units or []):
        unit = str(unit).strip()
        if unit and unit not in units:
            units.append(unit)
    units.sort(key=len, reverse=True)
    return units


def parse_cost_detail_part(part, extra_units=None):
    part = str(part).strip()
    if not part:
        return None
    pattern = '(' + '|'.join(re.escape(unit) for unit in unit_candidates(extra_units)) + ')'
    match = re.match(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + pattern + r'\s+(\d+(?:\.\d+)?)$', part)
    if not match:
        match = re.match(r'^(.*?)\s+(\d+(?:\.\d+)?)\s+(.+?)\s+(\d+(?:\.\d+)?)$', part)
    if not match:
        return None
    return {
        "name": match.group(1).strip(),
        "qty": match.group(2).strip(),
        "unit": (match.group(3) or "").strip(),
        "total": match.group(4).strip(),
        "raw": part,
    }


def scan_unit_usages(target_units):
    target_units = {str(unit).strip() for unit in target_units if str(unit).strip()}
    if not target_units:
        return []
    try:
        df = load_daily()
    except Exception:
        return []
    usages = []
    for _, row in df.iterrows():
        day = str(row.get('日期', '')).strip()
        if not day:
            continue
        for category, col in (("食材", "食材明细"), ("佐料", "佐料明细")):
            detail = str(row.get(col, '') or '')
            if detail == 'nan':
                continue
            for part in re.split(r'[,，]', detail):
                parsed = parse_cost_detail_part(part, target_units)
                if parsed and parsed["unit"] in target_units and parsed["name"]:
                    usages.append({
                        "date": day,
                        "category": category,
                        "name": parsed["name"],
                        "unit": parsed["unit"],
                    })
    usages.sort(key=lambda item: item["date"], reverse=True)
    return usages


def format_usage_date(day_str):
    try:
        dt = datetime.strptime(str(day_str), "%Y-%m-%d")
    except Exception:
        return str(day_str)
    if dt.year == datetime.now().year:
        return f"本年{dt.month}月{dt.day}日"
    return f"{dt.year}年{dt.month}月{dt.day}日"


def format_unit_usage_details(usages):
    by_date = {}
    for usage in usages:
        day_bucket = by_date.setdefault(usage["date"], {})
        key = (usage["category"], usage["unit"])
        day_bucket.setdefault(key, []).append(usage["name"])
    lines = []
    for day in sorted(by_date.keys(), reverse=True):
        parts = []
        category_order = {"食材": 0, "佐料": 1}
        for (category, unit), names in sorted(by_date[day].items(), key=lambda item: (category_order.get(item[0][0], 9), item[0][1])):
            deduped = []
            for name in names:
                if name not in deduped:
                    deduped.append(name)
            quoted_names = "，".join(f"“{name}”" for name in deduped)
            parts.append(f"{quoted_names}{category}正在使用单位“{unit}”")
        lines.append(f"{format_usage_date(day)} " + "；".join(parts) + "。")
    return "\n".join(lines)


def show_large_detail_dialog(parent, title, details):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(900, 650)
    layout = QVBoxLayout(dlg)
    editor = QTextEdit()
    editor.setReadOnly(True)
    editor.setPlainText(details)
    editor.setStyleSheet("font-size: 17px; line-height: 1.45;")
    layout.addWidget(editor)
    btn = QPushButton("OK")
    btn.setMinimumHeight(38)
    btn.clicked.connect(dlg.accept)
    layout.addWidget(btn)
    dlg.exec()


def msgbox_role(name):
    role = getattr(QMessageBox, name, None)
    if role is None and hasattr(QMessageBox, "ButtonRole"):
        role = getattr(QMessageBox.ButtonRole, name)
    return role


def show_usage_message(parent, title, text, details, allow_yes=False):
    while True:
        box = QMessageBox(parent)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Warning)
        box.setText(text)
        box.setStyleSheet("QLabel { font-size: 16px; } QPushButton { min-height: 32px; font-size: 14px; }")
        detail_btn = box.addButton("Show Detail", msgbox_role("ActionRole"))
        if allow_yes:
            yes_btn = box.addButton("Yes", msgbox_role("YesRole"))
            no_btn = box.addButton("No", msgbox_role("NoRole"))
            box.setDefaultButton(no_btn)
        else:
            ok_btn = box.addButton("OK", msgbox_role("AcceptRole"))
            box.setDefaultButton(ok_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked == detail_btn:
            show_large_detail_dialog(parent, title, details)
            continue
        if allow_yes:
            return clicked == yes_btn
        return False


def replace_units_in_detail(detail_str, rename_map):
    if not str(detail_str).strip() or str(detail_str) == 'nan':
        return detail_str
    parts = []
    changed = False
    for part in re.split(r'[,，]', str(detail_str)):
        raw = part.strip()
        parsed = parse_cost_detail_part(raw, rename_map.keys())
        if parsed and parsed["unit"] in rename_map:
            new_unit = rename_map[parsed["unit"]]
            parts.append(f"{parsed['name']} {unit_join(parsed['qty'], new_unit)} {parsed['total']}")
            changed = True
        else:
            parts.append(raw)
    return ", ".join(parts) if changed else detail_str


def apply_unit_renames_to_daily(rename_map):
    rename_map = {str(k).strip(): str(v).strip() for k, v in rename_map.items() if str(k).strip() and str(v).strip()}
    if not rename_map:
        return 0
    df = load_daily()
    changed_rows = 0
    for idx, row in df.iterrows():
        changed = False
        for col in ("食材明细", "佐料明细"):
            before = str(row.get(col, '') or '')
            after = replace_units_in_detail(before, rename_map)
            if after != before:
                df.at[idx, col] = after
                changed = True
        if changed:
            changed_rows += 1
    if changed_rows:
        save_daily(df)
    return changed_rows


class UnitTableWidget(QTableWidget):
    """单位管理表格：手动处理行拖动，避免 Qt 内部移动误删目标行。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed_row = None
        self._pressed_y = None
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["删除", "单位名称"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.setColumnWidth(0, 58)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setVisible(True)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.SelectedClicked
        )
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setAlternatingRowColors(True)

    def _event_pos(self, event):
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

    def add_unit_row(self, name="", original=None):
        row = self.rowCount()
        self.insertRow(row)
        del_item = QTableWidgetItem()
        del_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        del_item.setCheckState(Qt.Unchecked)
        self.setItem(row, 0, del_item)

        name_item = QTableWidgetItem(str(name))
        name_item.setData(Qt.UserRole, str(name if original is None else original))
        name_item.setFlags(name_item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled)
        self.setItem(row, 1, name_item)
        self.setRowHeight(row, 30)
        return row

    def mousePressEvent(self, event):
        pos = self._event_pos(event)
        self._pressed_row = self.rowAt(pos.y())
        self._pressed_y = pos.y()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        pos = self._event_pos(event)
        source = self._pressed_row
        start_y = self._pressed_y
        self._pressed_row = None
        self._pressed_y = None
        super().mouseReleaseEvent(event)
        if source is None or source < 0 or source >= self.rowCount() or start_y is None:
            return
        if abs(pos.y() - start_y) < 12:
            return
        target = self.rowAt(pos.y())
        if target < 0:
            target = self.rowCount()
        elif target > source:
            target += 1
        self.move_row(source, target)

    def move_row(self, source, target):
        if source < 0 or source >= self.rowCount():
            return
        if target > source:
            target -= 1
        target = max(0, min(target, self.rowCount() - 1))
        if target == source:
            return

        row_items = [self.takeItem(source, col) for col in range(self.columnCount())]
        self.removeRow(source)
        self.insertRow(target)
        for col, item in enumerate(row_items):
            self.setItem(target, col, item)
        self.setRowHeight(target, 30)
        self.selectRow(target)


def _wheel_delta_for_scrollbar(event, bar):
    pixel_delta = event.pixelDelta()
    if not pixel_delta.isNull():
        return pixel_delta.y()
    angle_delta = event.angleDelta().y()
    if angle_delta:
        step = max(bar.singleStep(), 20)
        return int(round((angle_delta / 120) * step * 3))
    return 0


def _scrollbar_has_room_for_wheel(bar, delta):
    if delta > 0:
        return bar.value() > bar.minimum()
    if delta < 0:
        return bar.value() < bar.maximum()
    return False


def _apply_wheel_to_scrollbar(bar, delta):
    if not delta:
        return False
    old_value = bar.value()
    new_value = max(bar.minimum(), min(bar.maximum(), old_value - delta))
    if new_value == old_value:
        return False
    bar.setValue(new_value)
    return True


def _find_parent_scroll_area(widget):
    parent = widget.parent()
    while parent and not isinstance(parent, QScrollArea):
        parent = parent.parent()
    return parent


class WheelPassThroughTableWidget(QTableWidget):
    """统计表先滚自己，滚到边界后再滚外层页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.installEventFilter(self)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return self.handle_wheel_event(event)
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if not self.handle_wheel_event(event):
            super().wheelEvent(event)

    def handle_wheel_event(self, event, outer_scroll=None):
        own_bar = self.verticalScrollBar()
        delta = _wheel_delta_for_scrollbar(event, own_bar)
        if not delta:
            return False

        if _scrollbar_has_room_for_wheel(own_bar, delta):
            _apply_wheel_to_scrollbar(own_bar, delta)
            event.accept()
            return True

        scroll_area = outer_scroll or _find_parent_scroll_area(self)
        if scroll_area:
            _apply_wheel_to_scrollbar(scroll_area.verticalScrollBar(), delta)
            event.accept()
            return True
        return False


class ConfirmCloseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.allow_close_without_prompt = False
        self.close_handler = None

    def reject(self):
        if not self.allow_close_without_prompt and self.close_handler and not self.close_handler():
            return
        super().reject()

    def closeEvent(self, event):
        if not self.allow_close_without_prompt and self.close_handler and not self.close_handler():
            event.ignore()
            return
        event.accept()


def open_unit_manager_dialog(parent, units, used_units, refresh_callback):
    """打开通用的单位增加/修改/删除弹窗。"""
    dlg = ConfirmCloseDialog(parent)
    dlg.setWindowTitle("增加/修改/删除 单位")
    dlg.resize(520, 560)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("拖动整行可排序 | 直接双击单位名称可编辑 | 勾选后可删除"))

    table = UnitTableWidget()
    base_units = [str(u).strip() for u in units if str(u).strip()]
    for unit in base_units:
        table.add_unit_row(unit)
    layout.addWidget(table)

    btn_layout = QHBoxLayout()
    btn_add = QPushButton("新增单位")
    btn_del = QPushButton("删除勾选")
    btn_up = QPushButton("上移")
    btn_down = QPushButton("下移")
    btn_save = QPushButton("保存修改")
    btn_cancel = QPushButton("取消")
    for b in [btn_add, btn_del, btn_up, btn_down, btn_save, btn_cancel]:
        b.setMinimumHeight(32)
    btn_layout.addWidget(btn_add)
    btn_layout.addWidget(btn_del)
    btn_layout.addWidget(btn_up)
    btn_layout.addWidget(btn_down)
    btn_layout.addStretch()
    btn_layout.addWidget(btn_save)
    btn_layout.addWidget(btn_cancel)
    layout.addLayout(btn_layout)

    def row_unit(row):
        item = table.item(row, 1)
        if not item:
            return "", ""
        original = str(item.data(Qt.UserRole) or "").strip()
        current = item.text().strip()
        return original, current

    def table_rows():
        rows = []
        for row in range(table.rowCount()):
            original, name = row_unit(row)
            rows.append((row, original, name))
        return rows

    def build_changes():
        new_units = []
        seen_units = set()
        duplicates = []
        rename_map = {}
        present_originals = set()
        blanked = []

        for _, original, name in table_rows():
            if not name:
                if original:
                    blanked.append(original)
                continue
            if name in seen_units:
                if original:
                    present_originals.add(original)
                    if original != name:
                        rename_map[original] = name
                    continue
                duplicates.append(name)
                continue
            seen_units.add(name)
            new_units.append(name)
            if original:
                present_originals.add(original)
                if original != name:
                    rename_map[original] = name

        deleted_units = [unit for unit in base_units if unit not in present_originals]
        order_changed = new_units != list(units)
        return {
            "new_units": new_units,
            "rename_map": rename_map,
            "deleted_units": deleted_units,
            "duplicates": duplicates,
            "blanked": blanked,
            "order_changed": order_changed,
        }

    def has_unsaved_changes():
        changes = build_changes()
        return bool(changes["rename_map"] or changes["deleted_units"] or changes["order_changed"] or changes["blanked"] or changes["duplicates"])

    def summarize_changes(changes):
        parts = []
        if changes["rename_map"]:
            rename_parts = [f"“{old}”改成了“{new}”" for old, new in changes["rename_map"].items()]
            parts.append("您把" + "，".join(rename_parts))
        if changes["order_changed"] and not changes["rename_map"] and not changes["deleted_units"]:
            parts.append("您调整了单位顺序")
        if changes["deleted_units"]:
            parts.append("删除了" + "，".join(f"“{unit}”" for unit in changes["deleted_units"]))
        if not parts:
            parts.append("您修改了单位列表")
        return "，".join(parts) + "。按 No 返回操作，按 Yes 保存作出的修改。"

    def add_row():
        text, ok = QInputDialog.getText(dlg, "新增单位", "请输入新的单位名称（多个可用逗号隔开）：")
        if not ok or not text.strip():
            return
        inputs = [u.strip() for u in text.replace('，', ',').split(',') if u.strip()]
        existing = set(unit for _, _, unit in table_rows() if unit) | set(units)
        added, duplicated = [], []
        for unit in inputs:
            if unit in existing:
                duplicated.append(unit)
                continue
            units.append(unit)
            base_units.append(unit)
            table.add_unit_row(unit, unit)
            existing.add(unit)
            added.append(unit)
        if added:
            refresh_all_unit_combos({}, refresh_callback)
            QMessageBox.information(dlg, "已新增", f"已自动保存新增单位：{'、'.join(added)}")
        if duplicated:
            QMessageBox.warning(dlg, "提示", f"以下单位已存在：{'、'.join(duplicated)}")

    def checked_rows():
        rows = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                rows.append(row)
        return rows

    def move_selected(delta):
        row = table.currentRow()
        if row < 0:
            return
        target = row + delta
        if target < 0 or target >= table.rowCount():
            return
        table.move_row(row, target if delta < 0 else target + 1)

    def do_delete():
        rows = checked_rows()
        if not rows:
            QMessageBox.information(dlg, "提示", "请勾选要删除的单位。")
            return

        items = [row_unit(row) for row in rows]
        to_delete = [original or current for original, current in items if original or current]
        usages = scan_unit_usages(to_delete)
        if usages:
            details = format_unit_usage_details(usages)
            show_usage_message(
                dlg,
                "单位正在使用，不能删除",
                f"以下单位正在历史记录中使用，不能删除：{'、'.join(sorted(set(u['unit'] for u in usages)))}",
                details,
                allow_yes=False
            )
            return
        if to_delete and QMessageBox.question(
                dlg, "确认删除",
                f"将从单位列表中移除：{'、'.join(to_delete)}\n\n这些修改会在点击“保存修改”后生效。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return

        for row in sorted(rows, reverse=True):
            table.removeRow(row)

    def save_changes(from_close=False):
        changes = build_changes()
        if changes["duplicates"]:
            QMessageBox.warning(dlg, "提示", f"单位不能重复：{'、'.join(sorted(set(changes['duplicates'])))}")
            return False
        if changes["blanked"]:
            usages = scan_unit_usages(changes["blanked"])
            if usages:
                show_usage_message(
                    dlg,
                    "单位正在使用，不能改成空白",
                    f"以下单位正在历史记录中使用，不能改成空白：{'、'.join(sorted(set(u['unit'] for u in usages)))}",
                    format_unit_usage_details(usages),
                    allow_yes=False
                )
                return False
        if not changes["new_units"]:
            QMessageBox.warning(dlg, "提示", "至少保留一个单位。")
            return False

        delete_usages = scan_unit_usages(changes["deleted_units"])
        if delete_usages:
            show_usage_message(
                dlg,
                "单位正在使用，不能删除",
                f"以下单位正在历史记录中使用，不能删除：{'、'.join(sorted(set(u['unit'] for u in delete_usages)))}",
                format_unit_usage_details(delete_usages),
                allow_yes=False
            )
            return False

        rename_usages = scan_unit_usages(changes["rename_map"].keys())
        if rename_usages:
            ok = show_usage_message(
                dlg,
                "修改单位会同步历史记录",
                "以下单位正在历史记录中使用。按 Yes 会把这些历史记录里的单位一起改成新名称；按 No 返回继续调整。",
                format_unit_usage_details(rename_usages),
                allow_yes=True
            )
            if not ok:
                return False
            if QMessageBox.warning(
                    dlg,
                    "最终确认同步修改",
                    "这是第二次确认。\n\n确定要保存单位改名，并同步修改所有历史食材/佐料明细里的单位吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return False
        elif from_close:
            if QMessageBox.warning(
                    dlg,
                    "再次确认保存",
                    "这是第二次确认。\n\n确定保存这些单位修改并关闭窗口吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return False

        if changes["rename_map"]:
            apply_unit_renames_to_daily(changes["rename_map"])
        units.clear()
        units.extend(changes["new_units"])
        refresh_all_unit_combos(changes["rename_map"], refresh_callback)
        return True

    def save_and_close():
        if save_changes(False):
            dlg.allow_close_without_prompt = True
            dlg.accept()

    def handle_close_request():
        if not has_unsaved_changes():
            return True
        changes = build_changes()
        if QMessageBox.question(
                dlg,
                "单位修改尚未保存",
                summarize_changes(changes),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return False
        return save_changes(True)

    btn_add.clicked.connect(add_row)
    btn_del.clicked.connect(do_delete)
    btn_up.clicked.connect(lambda: move_selected(-1))
    btn_down.clicked.connect(lambda: move_selected(1))
    btn_save.clicked.connect(save_and_close)
    btn_cancel.clicked.connect(dlg.reject)
    dlg.close_handler = handle_close_request
    dlg.exec()


# ===================== 启动引导界面 =====================
class StartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("餐饮成本管家 - 数据初始化")
        self.resize(620, 280)
        self.selected_path = None

        layout = QVBoxLayout(self)

        title = QLabel(" 欢迎使用餐饮成本管家")
        title.setStyleSheet("font-size:16px; font-weight: bold; color: #344c66;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.info_label = QLabel(
            "这是您第一次运行，或者系统未能找到之前使用的用户 Excel。\n"
            "请选择读取已有文件、通过内部 Excel 找回，或创建一个新的用户 Excel："
        )
        self.info_label.setStyleSheet("font-size: 14px; margin-top: 10px; margin-bottom: 20px;")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        btn_layout = QHBoxLayout()
        self.btn_select = QPushButton(" 读取已有的用户 Excel")
        self.btn_restore = QPushButton(" 通过内部 Excel 找回")
        self.btn_create = QPushButton(" 创建新的用户 Excel")

        self.btn_select.setStyleSheet("padding: 10px; font-weight: bold; font-size: 13px;")
        self.btn_restore.setStyleSheet(
            "padding: 10px; font-weight: bold; font-size: 13px; background-color: #596d82; color: white;"
        )
        self.btn_create.setStyleSheet(
            "padding: 10px; font-weight: bold; font-size: 13px; background-color: #315f88; color: white;")

        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_create)
        layout.addLayout(btn_layout)

        self.btn_select.clicked.connect(self.select_file)
        self.btn_restore.clicked.connect(self.restore_from_internal)
        self.btn_create.clicked.connect(self.create_file)

    def restore_from_internal(self):
        try:
            result = restore_user_excels_from_internal(self)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, "无法通过内部 Excel 恢复", str(exc))
            return
        if not result or not result.get('active_path'):
            return

        restored = result.get('restored', [])
        details = "\n".join(
            f"{item['year']} 年：{item['path']}" for item in restored
        )
        QMessageBox.information(
            self,
            "恢复完成",
            f"已从内部 Excel 恢复 {len(restored)} 个年度用户 Excel：\n\n{details}\n\n"
            "点击“确定”后将自动打开当前年度用户 Excel。",
        )
        self.selected_path = result['active_path']
        self.accept()

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择用户 Excel", os.path.expanduser("~"),
                                                   "Excel Files (*.xlsx)")
        if file_path:
            try:
                validate_data_excel(file_path, require_write=True)
                is_valid = True
            except ExcelAccessError as exc:
                QMessageBox.critical(self, "无法访问 Excel", str(exc))
                return
            except ExcelFormatError:
                is_valid = False

            if not is_valid:
                ans1 = QMessageBox.warning(
                    self,
                    " 格式不符警告",
                    "检测到您选择的不是本软件的标准记账 Excel 文件（或文件已损坏）。\n如果继续，该文件将被强制改造，【里面的原有内容可能会丢失】。\n\n您确定要继续吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if ans1 == QMessageBox.Yes:
                    ans2 = QMessageBox.critical(
                        self,
                        " 最终确认 (不可逆)",
                        "【最后警告】\n继续操作将不可逆地修改此文件，原有数据极有可能被清空覆盖！\n如果您选错了文件，请立即点击“No”。\n\n真的要摧毁原格式并继续吗？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if ans2 == QMessageBox.Yes:
                        try:
                            # This path is destructive only after the two explicit confirmations above.
                            init_excel_structure(file_path, overwrite_existing=True)
                            validate_data_excel(file_path, require_write=True)
                        except (ExcelAccessError, ExcelFormatError) as exc:
                            QMessageBox.critical(self, "无法初始化 Excel", str(exc))
                            return
                    else:
                        return
                else:
                    return

            self.selected_path = normalize_excel_path(file_path)
            self.accept()

    def create_file(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Documents")
        default_path = os.path.join(default_dir, "餐饮管家数据_总店.xlsx")
        file_path, _ = QFileDialog.getSaveFileName(self, "创建新的用户 Excel", default_path, "Excel Files (*.xlsx)")
        if file_path:
            if not file_path.endswith('.xlsx'): file_path += '.xlsx'
            try:
                init_excel_structure(file_path)
                validate_data_excel(file_path, require_write=True)
            except (ExcelAccessError, ExcelFormatError) as exc:
                QMessageBox.critical(self, "无法创建 Excel", str(exc))
                return
            self.selected_path = normalize_excel_path(file_path)
            self.accept()



def _unique_archived_excel_path(path_value, label):
    """Return a same-folder timestamped archive path without overwriting anything."""
    source = normalize_excel_path(path_value)
    folder, filename = os.path.split(source)
    stem, extension = os.path.splitext(filename)
    extension = extension or '.xlsx'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_label = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff_-]+', '_', str(label)).strip('_') or '旧数据'
    candidate = os.path.join(folder, f'{stem}_{safe_label}_{stamp}{extension}')
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f'{stem}_{safe_label}_{stamp}_{counter}{extension}')
        counter += 1
    return candidate


def _user_data_years(frames):
    """Return calendar years that actually occur in one visible user workbook."""
    years = set()
    for sheet_name, date_column in DATE_SHEET_COLUMNS.items():
        frame = frames.get(sheet_name, pd.DataFrame())
        for day in _valid_date_keys(frame, date_column):
            try:
                years.add(int(day[:4]))
            except (TypeError, ValueError):
                pass
    month_frame = frames.get('monthly_fixed', pd.DataFrame())
    for month in _valid_month_keys(month_frame):
        try:
            years.add(int(month[:4]))
        except (TypeError, ValueError):
            pass
    return sorted(years)


def _write_cloud_override_request(internal_path, source_kind, message=''):
    """记录主程序切换请求；同步助手会自动用新内部 Excel 整体覆盖云端。"""
    config = _read_path_config()
    now = datetime.now().astimezone().isoformat(timespec='seconds')
    resolved_path = normalize_excel_path(internal_path)
    request_id = str(uuid.uuid4())
    config.update({
        'DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'STARTUP_SOURCE_KIND': str(source_kind),
        'STARTUP_SOURCE_SELECTED_AT': now,
        'INTERNAL_FILE_PATH': resolved_path,
        'INTERNAL_PATH_CHANGE_NOTICE': str(message),
        'INTERNAL_PATH_CHANGE_SOURCE': 'main_app',
        'INTERNAL_PATH_CHANGE_ID': request_id,
        'INTERNAL_PATH_CHANGED_AT': now,
        'CLOUD_OVERRIDE_REQUEST_ID': request_id,
        'CLOUD_OVERRIDE_REQUEST_PATH': resolved_path,
        'CLOUD_OVERRIDE_REQUEST_MODE': 'local_over_cloud',
        'CLOUD_OVERRIDE_REQUEST_STATUS': 'pending',
        'CLOUD_OVERRIDE_REQUESTED_AT': now,
        'CLOUD_OVERRIDE_REQUEST_MESSAGE': str(message) or '主程序已更换内部 Excel，等待网站内置同步更新云端。',
    })
    _write_path_config(config)
    return request_id


def _activate_existing_internal_and_rebuild_users(internal_path, suggested_user_path=None):
    """Use an existing internal workbook and silently recreate every missing year mirror."""
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

    internal_path = validate_internal_excel(internal_path, require_write=True)
    with internal_sync_lock(internal_path):
        _rebind_internal_dataset_id_unlocked(internal_path, FIXED_CLOUD_DATASET_ID)
        internal_frames = _read_internal_frames(internal_path)

    years = _internal_years_for_dataset(internal_frames, FIXED_CLOUD_DATASET_ID)
    config = _read_path_config()
    try:
        configured_year = int(config.get('ACTIVE_USER_EXCEL_YEAR', ''))
    except (TypeError, ValueError):
        configured_year = None
    current_year = datetime.now().year
    active_year = (
        current_year if current_year in years
        else (configured_year if configured_year in years else (years[-1] if years else current_year))
    )

    active_path = _startup_user_target_from_internal(
        internal_path, active_year, suggested_user_path
    )
    FILE_PATH = normalize_excel_path(active_path)
    INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
    ACTIVE_USER_EXCEL_YEAR = int(active_year)
    ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID

    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    year_map = dict(year_map) if isinstance(year_map, dict) else {}
    year_map[str(active_year)] = FILE_PATH
    config.update({
        'FILE_PATH': FILE_PATH,
        'USER_EXCEL_PATH': FILE_PATH,
        'INTERNAL_FILE_PATH': INTERNAL_FILE_PATH,
        'YEARLY_USER_EXCEL_PATHS': year_map,
        'ACTIVE_USER_EXCEL_YEAR': int(active_year),
        'DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'INTERNAL_SYNC_PENDING': False,
    })
    _write_path_config(config)

    targets = _known_user_mirror_targets(
        internal_frames, FIXED_CLOUD_DATASET_ID, years or [active_year]
    )
    if active_year not in targets:
        targets[active_year] = FILE_PATH
    missing_before = {
        int(year): path for year, path in targets.items() if not os.path.exists(path)
    }

    refreshed = {}
    with internal_sync_lock(INTERNAL_FILE_PATH):
        for year, target in sorted(targets.items()):
            restored = _restored_user_frames_for_year(
                internal_frames, FIXED_CLOUD_DATASET_ID, int(year)
            )
            _write_user_mirror_atomically(
                target,
                restored,
                FIXED_CLOUD_DATASET_ID,
                int(year),
                allow_family_override=True,
            )
            refreshed[int(year)] = normalize_excel_path(target)
        _set_app_baseline_from_internal(
            internal_frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
        )

    config = _read_path_config()
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    year_map = dict(year_map) if isinstance(year_map, dict) else {}
    year_map.update({str(year): target for year, target in refreshed.items()})
    config.update({
        'FILE_PATH': refreshed.get(ACTIVE_USER_EXCEL_YEAR, FILE_PATH),
        'USER_EXCEL_PATH': refreshed.get(ACTIVE_USER_EXCEL_YEAR, FILE_PATH),
        'INTERNAL_FILE_PATH': INTERNAL_FILE_PATH,
        'YEARLY_USER_EXCEL_PATHS': year_map,
        'ACTIVE_USER_EXCEL_YEAR': int(ACTIVE_USER_EXCEL_YEAR),
        'DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'USER_MIRROR_SYNC_PENDING': False,
    })
    FILE_PATH = config['USER_EXCEL_PATH']
    _write_path_config(config)
    return missing_before


def _create_internal_automatically_from_user(user_path, internal_path):
    """Recreate a missing internal workbook from the surviving current-year user workbook."""
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

    user_path = validate_data_excel(user_path, require_write=True)
    year = _infer_user_excel_year(user_path, datetime.now().year)
    internal_path = normalize_excel_path(internal_path)
    if os.path.normcase(internal_path) == os.path.normcase(user_path):
        internal_path = _unique_new_internal_path_for_user(user_path)
    if os.path.exists(internal_path):
        raise ExcelAccessError(f'准备新建的内部 Excel 已存在：\n{internal_path}')

    write_user_workbook_metadata(user_path, FIXED_CLOUD_DATASET_ID, year)
    _write_internal_frames(internal_path, _default_internal_frames())

    FILE_PATH = normalize_excel_path(user_path)
    INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
    ACTIVE_USER_EXCEL_YEAR = int(year)
    ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID
    sync_user_excel_to_internal(
        FILE_PATH,
        ACTIVE_USER_EXCEL_YEAR,
        FIXED_CLOUD_DATASET_ID,
        INTERNAL_FILE_PATH,
    )
    frames = _read_internal_frames(INTERNAL_FILE_PATH)
    _set_app_baseline_from_internal(
        frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
    )
    save_path_config(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, INTERNAL_FILE_PATH)
    _write_cloud_override_request(
        INTERNAL_FILE_PATH,
        'auto_recreated_internal_from_user',
        '启动时检测到内部 Excel 丢失，已由现存用户 Excel 自动重建。',
    )
    trigger_sync_assistant_now()
    return INTERNAL_FILE_PATH


def prepare_startup_files_without_unnecessary_choice(saved_user_path, configured_internal_path):
    """Implement the three startup cases requested by the user.

    Returns (ready, notice_title, notice_message). The source chooser is required only
    when neither configured workbook survives.
    """
    user_path = normalize_excel_path(saved_user_path) if saved_user_path else ''
    internal_path = normalize_excel_path(configured_internal_path) if configured_internal_path else ''
    user_exists = bool(user_path and os.path.isfile(user_path))
    internal_exists = bool(internal_path and os.path.isfile(internal_path))

    if internal_exists:
        missing = _activate_existing_internal_and_rebuild_users(
            internal_path, user_path or None
        )
        if missing:
            details = '\n'.join(
                f'• {year} 年：{target}' for year, target in sorted(missing.items())
            )
            return True, '已自动恢复用户 Excel', (
                '检测到以下年度用户 Excel 丢失，已直接根据内部 Excel 自动重建：\n\n'
                + details
                + '\n\n无需重新选择数据来源。'
            )
        return True, '', ''

    if user_exists:
        created = _create_internal_automatically_from_user(user_path, internal_path)
        return True, '已自动重建内部 Excel', (
            '检测到内部 Excel 丢失，但当前用户 Excel仍然存在。\n\n'
            f'程序已自动新建内部 Excel：\n{created}\n\n'
            '无需重新选择数据来源。'
        )

    return False, '', ''


def _cloud_cache_paths(dataset_id, year=None):
    """Return app-owned cache files; cloud startup must never ask users for Excel."""
    year = int(year or datetime.now().year)
    app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not app_data:
        app_data = os.path.join(
            os.path.expanduser('~'), 'Library', 'Application Support', '餐饮成本管家'
        )
    folder = os.path.join(app_data, 'cloud-cache')
    os.makedirs(folder, exist_ok=True)
    cache_id = hashlib.sha256(str(dataset_id).encode('utf-8')).hexdigest()[:12]
    return (
        os.path.join(folder, f'账本缓存_{cache_id}.xlsx'),
        os.path.join(folder, f'用户缓存_{year}_{cache_id}.xlsx'),
    )


def initialize_cloud_cache_from_server():
    """Download the selected cloud ledger into an invisible app-owned local cache."""
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID, DESKTOP_STARTUP_CONNECTION_STATE

    # Do not carry a previous successful probe across a failed retry.  The
    # caller may invoke this function more than once during startup.
    DESKTOP_STARTUP_CONNECTION_STATE = {}

    config = load_embedded_sync_config()
    worker = EmbeddedCloudSyncWorker()
    worker._login(config)
    worker._refresh_datasets(config)
    allowed_ids = [str(item.get('id') or '') for item in worker._datasets]
    dataset_id = str(config.get('dataset_id') or '')
    if dataset_id not in allowed_ids:
        default = next(
            (item for item in worker._datasets if item.get('is_default')),
            worker._datasets[0],
        )
        dataset_id = str(default.get('id') or '')
    if not dataset_id:
        raise CloudSyncError('当前账号没有可用账本。')

    records = worker._fetch_cloud_records(config, dataset_id)
    path_config = _read_path_config()
    try:
        preferred_year = int(path_config.get('ACTIVE_USER_EXCEL_YEAR') or datetime.now().year)
    except (TypeError, ValueError):
        preferred_year = datetime.now().year
    internal_path, user_path = _cloud_cache_paths(dataset_id, preferred_year)

    # Rebuild only the app-owned cache. Never overwrite a user-selected workbook.
    _write_internal_frames(internal_path, _default_internal_frames())
    INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
    FILE_PATH = normalize_excel_path(user_path)
    ACTIVE_USER_EXCEL_YEAR = int(preferred_year)
    ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID
    _embedded_apply_cloud_records(records, replace_all=True)

    # Discard legacy mirror locations so a cloud login cannot silently write to an
    # Excel file the user previously selected in the old desktop-only workflow.
    path_config.update({
        'FILE_PATH': FILE_PATH,
        'USER_EXCEL_PATH': FILE_PATH,
        'INTERNAL_FILE_PATH': INTERNAL_FILE_PATH,
        'YEARLY_USER_EXCEL_PATHS': {str(preferred_year): FILE_PATH},
        'ACTIVE_USER_EXCEL_YEAR': int(preferred_year),
        'DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_CACHE_DATASET_ID': dataset_id,
        'STARTUP_SOURCE_KIND': 'automatic_cloud_cache',
    })
    _write_path_config(path_config)
    _activate_existing_internal_and_rebuild_users(INTERNAL_FILE_PATH, FILE_PATH)

    local_map = _embedded_local_records()
    cloud_map = {
        (str(item.get('record_type') or ''), str(item.get('record_key') or '')): item
        for item in records
        if item.get('record_type') in {'day', 'month', 'global'} and item.get('record_key')
    }
    config = load_embedded_sync_config()
    baselines = config.get('embedded_baselines')
    baselines = dict(baselines) if isinstance(baselines, dict) else {}
    baselines[dataset_id] = worker._build_baseline(local_map, cloud_map)
    config.update({
        'dataset_id': dataset_id,
        'datasets_cache': list(worker._datasets),
        'embedded_last_dataset_id': dataset_id,
        'embedded_baselines': baselines,
    })
    save_embedded_sync_config(config)

    # Keep the authenticated result for MainWindow.  Creating a second worker
    # with its default ``connected=False`` state used to produce a red
    # "网络未连接" pill (and, on slower machines, a warning dialog) immediately
    # after the login dialog had already succeeded.
    startup_snapshot = worker.snapshot()
    DESKTOP_STARTUP_CONNECTION_STATE = {
        'configured': True,
        'connected': True,
        'role': str(startup_snapshot.get('role') or 'viewer'),
        'datasets': list(worker._datasets),
        'dataset_id': dataset_id,
        'last_sync_at': datetime.now().strftime('%H:%M:%S'),
        'error': '',
        'conflicts': [],
        'consecutive_failures': 0,
        'last_success_monotonic': time.monotonic(),
    }
    return True

class StartupSourceDialog(QDialog):
    """When the visible user workbook is missing, choose one authoritative source once."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择启动数据来源")
        self.resize(620, 250)
        self.choice = None

        layout = QVBoxLayout(self)
        title = QLabel("请选择用哪一份 Excel 开启软件")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:700; color:#344c66;")
        layout.addWidget(title)

        info = QLabel(
            "• 使用用户 Excel：选择一份用户账本，它将成为当前数据来源；程序会为它创建新的内部 Excel。\n"
            "• 使用内部 Excel：选择一份内部数据文件，程序会据此重新生成用户 Excel。\n\n"
            "所选来源会成为本地事实来源；同步助手检测到路径变化后，会弹窗询问是否用它覆盖云端。"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignLeft)
        info.setStyleSheet("font-size:13px; line-height:1.45;")
        layout.addWidget(info)

        buttons = QHBoxLayout()
        self.user_button = QPushButton("使用用户 Excel")
        self.internal_button = QPushButton("使用内部 Excel")
        self.cancel_button = QPushButton("取消并退出")
        for button in (self.user_button, self.internal_button, self.cancel_button):
            button.setMinimumHeight(36)
            button.setStyleSheet("padding:8px 14px; font-weight:600;")
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.user_button.clicked.connect(lambda: self._finish("user"))
        self.internal_button.clicked.connect(lambda: self._finish("internal"))
        self.cancel_button.clicked.connect(self.reject)

    def _finish(self, choice):
        self.choice = choice
        self.accept()


def _unique_new_internal_path_for_user(user_path):
    """Create a new internal filename without overwriting an older internal workbook."""
    user_path = normalize_excel_path(user_path)
    folder = os.path.dirname(user_path)
    preferred = os.path.join(folder, DEFAULT_INTERNAL_EXCEL_FILENAME)
    if not os.path.exists(preferred):
        return preferred
    stem, extension = os.path.splitext(DEFAULT_INTERNAL_EXCEL_FILENAME)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    candidate = os.path.join(folder, f'{stem}_从用户Excel_{stamp}{extension}')
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(
            folder, f'{stem}_从用户Excel_{stamp}_{counter}{extension}'
        )
        counter += 1
    return candidate


def _startup_user_target_from_internal(internal_path, year, suggested_path=None):
    """Prefer the deleted user's original path; otherwise derive a separate visible file."""
    internal_path = normalize_excel_path(internal_path)
    if suggested_path:
        try:
            candidate = normalize_excel_path(suggested_path)
        except ExcelAccessError:
            candidate = ''
        if candidate and os.path.normcase(candidate) != os.path.normcase(internal_path):
            if not candidate.lower().endswith('.xlsx'):
                candidate += '.xlsx'
            return candidate
    return _switch_user_excel_target('', internal_path, year)


def _write_source_choice_config(user_path, internal_path, year, source_kind):
    """保存主程序的数据源选择，并排队自动用新内部 Excel 整体覆盖云端。"""
    config = _read_path_config()
    selected_at = datetime.now().astimezone().isoformat(timespec='seconds')
    resolved_internal = normalize_excel_path(internal_path)
    request_id = str(uuid.uuid4())
    config.update({
        'FILE_PATH': normalize_excel_path(user_path),
        'USER_EXCEL_PATH': normalize_excel_path(user_path),
        'INTERNAL_FILE_PATH': resolved_internal,
        'YEARLY_USER_EXCEL_PATHS': {str(int(year)): normalize_excel_path(user_path)},
        'ACTIVE_USER_EXCEL_YEAR': int(year),
        'DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'CLOUD_DATASET_ID': FIXED_CLOUD_DATASET_ID,
        'STARTUP_SOURCE_KIND': str(source_kind),
        'STARTUP_SOURCE_SELECTED_AT': selected_at,
        'INTERNAL_PATH_CHANGE_SOURCE': 'main_app',
        'INTERNAL_PATH_CHANGE_ID': request_id,
        'INTERNAL_PATH_CHANGED_AT': selected_at,
        'CLOUD_OVERRIDE_REQUEST_ID': request_id,
        'CLOUD_OVERRIDE_REQUEST_PATH': resolved_internal,
        'CLOUD_OVERRIDE_REQUEST_MODE': 'local_over_cloud',
        'CLOUD_OVERRIDE_REQUEST_STATUS': 'pending',
        'CLOUD_OVERRIDE_REQUESTED_AT': selected_at,
        'CLOUD_OVERRIDE_REQUEST_MESSAGE': '主程序已选择新的内部 Excel，等待网站内置同步更新云端。',
    })
    _write_path_config(config)


def startup_from_user_excel(parent=None):
    """Use one selected user workbook as authoritative and create a fresh internal store."""
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

    user_path, _ = QFileDialog.getOpenFileName(
        parent,
        "选择用户 Excel",
        os.path.expanduser("~"),
        "Excel Files (*.xlsx)",
    )
    if not user_path:
        return False
    try:
        user_path = validate_data_excel(user_path, require_write=True)
    except (ExcelAccessError, ExcelFormatError) as exc:
        QMessageBox.critical(parent, "无法使用用户 Excel", str(exc))
        return False

    year = _infer_user_excel_year(user_path)
    answer = QMessageBox.warning(
        parent,
        "确认使用用户 Excel",
        "将以这份用户 Excel 为准开启软件。\n\n"
        "程序会创建一份新的内部 Excel；网站内置同步随后会自动更新云端数据。\n"
        "已有的其他内部 Excel 不会被删除。\n\n"
        f"用户 Excel：\n{user_path}\n\n是否继续？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer != QMessageBox.Yes:
        return False

    old_state = (FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID)
    old_config = _read_path_config()
    internal_path = _unique_new_internal_path_for_user(user_path)
    created_internal = False
    try:
        sort_data_workbook(user_path)
        write_user_workbook_metadata(
            user_path, FIXED_CLOUD_DATASET_ID, int(year)
        )
        _write_internal_frames(internal_path, _default_internal_frames())
        created_internal = True

        FILE_PATH = normalize_excel_path(user_path)
        INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
        ACTIVE_USER_EXCEL_YEAR = int(year)
        ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID

        sync_user_excel_to_internal(
            FILE_PATH,
            ACTIVE_USER_EXCEL_YEAR,
            FIXED_CLOUD_DATASET_ID,
            INTERNAL_FILE_PATH,
        )
        frames = _read_internal_frames(INTERNAL_FILE_PATH)
        _set_app_baseline_from_internal(
            frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
        )
        _write_source_choice_config(
            FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, 'user_excel'
        )
        trigger_sync_assistant_now()
        return True
    except Exception as exc:
        FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID = old_state
        try:
            _write_path_config(old_config)
        except OSError:
            pass
        if created_internal and os.path.exists(internal_path):
            try:
                os.remove(internal_path)
            except OSError:
                pass
        QMessageBox.critical(
            parent,
            "无法使用用户 Excel 开启软件",
            f"没有完成切换，原配置保持不变。\n\n系统返回：{exc}",
        )
        return False


def startup_from_internal_excel(parent=None, suggested_user_path=None):
    """Use one selected internal workbook as authoritative and regenerate the user workbook."""
    global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

    start_dir = (
        os.path.dirname(get_internal_excel_path_from_config())
        if get_internal_excel_path_from_config()
        else os.path.expanduser("~")
    )
    internal_path, _ = QFileDialog.getOpenFileName(
        parent,
        "选择内部 Excel",
        start_dir,
        "Excel Files (*.xlsx)",
    )
    if not internal_path:
        return False
    try:
        internal_path = validate_internal_excel(internal_path, require_write=True)
    except (ExcelAccessError, ExcelFormatError) as exc:
        QMessageBox.critical(parent, "无法使用内部 Excel", str(exc))
        return False

    try:
        with internal_sync_lock(internal_path):
            _rebind_internal_dataset_id_unlocked(
                internal_path, FIXED_CLOUD_DATASET_ID
            )
            frames = _read_internal_frames(internal_path)
    except (ExcelAccessError, ExcelFormatError) as exc:
        QMessageBox.critical(parent, "无法读取内部 Excel", str(exc))
        return False

    years = _internal_years_for_dataset(frames, FIXED_CLOUD_DATASET_ID)
    year = (
        datetime.now().year
        if datetime.now().year in years
        else (years[-1] if years else datetime.now().year)
    )
    user_path = _startup_user_target_from_internal(
        internal_path, year, suggested_user_path
    )

    answer = QMessageBox.warning(
        parent,
        "确认使用内部 Excel",
        "将以这份内部 Excel 为准开启软件。\n\n"
        "程序会据此新建或覆盖用户 Excel；网站内置同步随后会自动更新云端数据。\n\n"
        f"内部 Excel：\n{internal_path}\n\n"
        f"将生成用户 Excel：\n{user_path}\n\n是否继续？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer != QMessageBox.Yes:
        return False

    old_state = (FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID)
    old_config = _read_path_config()
    user_backup = None
    try:
        if os.path.exists(user_path):
            fd, user_backup = tempfile.mkstemp(
                prefix='.restaurant_user_startup_backup_', suffix='.xlsx'
            )
            os.close(fd)
            shutil.copy2(user_path, user_backup)

        FILE_PATH = normalize_excel_path(user_path)
        INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
        ACTIVE_USER_EXCEL_YEAR = int(year)
        ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID

        restored = _restored_user_frames_for_year(
            frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
        )
        _write_user_mirror_atomically(
            FILE_PATH,
            restored,
            FIXED_CLOUD_DATASET_ID,
            ACTIVE_USER_EXCEL_YEAR,
            allow_family_override=True,
        )
        _set_app_baseline_from_internal(
            frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
        )
        _write_source_choice_config(
            FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, 'internal_excel'
        )
        trigger_sync_assistant_now()
        return True
    except Exception as exc:
        if user_backup and os.path.exists(user_backup):
            try:
                shutil.copy2(user_backup, user_path)
            except OSError:
                pass
        elif os.path.exists(user_path):
            try:
                os.remove(user_path)
            except OSError:
                pass
        FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID = old_state
        try:
            _write_path_config(old_config)
        except OSError:
            pass
        QMessageBox.critical(
            parent,
            "无法使用内部 Excel 开启软件",
            f"没有完成切换，原配置保持不变。\n\n系统返回：{exc}",
        )
        return False
    finally:
        if user_backup and os.path.exists(user_backup):
            try:
                os.remove(user_backup)
            except OSError:
                pass


def choose_startup_source_once(suggested_user_path=None, parent=None):
    """Show exactly one source-choice dialog; cancellation exits instead of looping."""
    dialog = StartupSourceDialog(parent)
    if dialog.exec() != QDialog.Accepted or not dialog.choice:
        return False
    if dialog.choice == 'user':
        return startup_from_user_excel(parent)
    return startup_from_internal_excel(parent, suggested_user_path)


class InternalStartupDialog(QDialog):
    """Required first-launch choice for the compact all-years internal workbook."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择内部 Excel")
        self.resize(560, 210)
        self.choice = None

        layout = QVBoxLayout(self)
        title = QLabel(" 找不到之前的内部 Excel")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight: bold; color: #344c66;")
        layout.addWidget(title)
        info = QLabel(
            "内部 Excel 用于高效保存所有年份的数据，平时不需要直接查看。\n"
            "请选择创建一个只同步当前年份的新文件，或读取已有的内部 Excel："
        )
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        self.btn_create = QPushButton("创建新内部 Excel\n（只能得到当年数据）")
        self.btn_read = QPushButton("读取已有内部 Excel")
        for button in (self.btn_create, self.btn_read):
            button.setMinimumHeight(36)
            button.setStyleSheet("padding: 8px; font-weight: bold; font-size: 13px;")
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.btn_create.clicked.connect(lambda: self._finish("create"))
        self.btn_read.clicked.connect(lambda: self._finish("read"))

    def _finish(self, choice):
        self.choice = choice
        self.accept()


def initialize_internal_excel_for_startup():
    """Load the internal source of truth and rebuild every known annual mirror."""
    global INTERNAL_FILE_PATH, ACTIVE_DATASET_ID

    def activate_existing_internal(internal_path):
        global INTERNAL_FILE_PATH, ACTIVE_DATASET_ID
        INTERNAL_FILE_PATH = normalize_excel_path(internal_path)
        with internal_sync_lock(INTERNAL_FILE_PATH):
            before_frames = _read_internal_frames(INTERNAL_FILE_PATH)
            had_business_records = _internal_has_business_records(before_frames)
            _rebind_internal_dataset_id_unlocked(
                INTERNAL_FILE_PATH, FIXED_CLOUD_DATASET_ID
            )
            frames = _read_internal_frames(INTERNAL_FILE_PATH)
            dataset_ids = (
                _internal_dataset_ids(frames) if had_business_records else set()
            )
        if not dataset_ids:
            # A truly empty internal workbook is a one-time migration case.
            sync_user_excel_to_internal(
                FILE_PATH,
                ACTIVE_USER_EXCEL_YEAR,
                ACTIVE_DATASET_ID,
                INTERNAL_FILE_PATH,
            )
            with internal_sync_lock(INTERNAL_FILE_PATH):
                frames = _read_internal_frames(INTERNAL_FILE_PATH)
                dataset_ids = _internal_dataset_ids(frames)
        if ACTIVE_DATASET_ID not in dataset_ids:
            if len(dataset_ids) == 1:
                ACTIVE_DATASET_ID = next(iter(dataset_ids))
            else:
                raise ExcelFormatError(
                    '内部 Excel 中存在多套数据，当前年度 Excel 无法自动确定所属数据集。'
                )
        ensure_user_workbook_metadata(
            FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID
        )
        # This is the decisive direction: internal -> every annual user workbook.
        sync_internal_to_user_excels(update_baseline=True)
        save_path_config(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, INTERNAL_FILE_PATH)

    candidate = normalize_excel_path(INTERNAL_FILE_PATH or get_internal_excel_path_from_config())
    candidate_error = None

    if os.path.exists(candidate):
        try:
            validate_internal_excel(candidate, require_write=True)
        except (ExcelAccessError, ExcelFormatError) as exc:
            candidate_error = exc
        else:
            activate_existing_internal(candidate)
            return True

    if candidate_error:
        QMessageBox.warning(
            None,
            "无法读取之前的内部 Excel",
            f"{candidate_error}\n\n请创建新的内部 Excel，或在下面选择读取已有的内部 Excel。",
        )

    dialog = InternalStartupDialog()
    if dialog.exec() != QDialog.Accepted or not dialog.choice:
        return False

    if dialog.choice == "create":
        current_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(current_dir):
            current_dir = os.path.expanduser("~")
        default_path = os.path.join(current_dir, DEFAULT_INTERNAL_EXCEL_FILENAME)
        internal_path, _ = QFileDialog.getSaveFileName(
            None, "创建新的内部 Excel", default_path, "Excel Files (*.xlsx)"
        )
        if not internal_path:
            return False
        if not internal_path.lower().endswith('.xlsx'):
            internal_path += '.xlsx'
        internal_path = normalize_excel_path(internal_path)
        if os.path.exists(internal_path):
            QMessageBox.warning(
                None,
                "不会覆盖已有内部 Excel",
                "所选位置已有文件。请改用新的文件名，或返回后选择“读取已有内部 Excel”。",
            )
            return False
        try:
            _write_internal_frames(internal_path, _default_internal_frames())
            sync_user_excel_to_internal(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID, internal_path)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(None, "创建内部 Excel 失败", str(exc))
            return False
    else:
        start_dir = os.path.dirname(FILE_PATH) if FILE_PATH else os.path.expanduser("~")
        internal_path, _ = QFileDialog.getOpenFileName(
            None, "读取已有内部 Excel", start_dir, "Excel Files (*.xlsx)"
        )
        if not internal_path:
            return False
        try:
            internal_path = validate_internal_excel(internal_path, require_write=True)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(None, "无法读取内部 Excel", str(exc))
            return False

    activate_existing_internal(internal_path)
    return True


# ===================== 多选词条(带金额输入) 弹窗 =====================
class ItemSelectDialog(QDialog):
    """选择食材/佐料弹窗，支持数量、单位、单价和总价。"""
    # 可用的单位列表
    UNITS = UNITS_LIST  # 引用全局单位列表
    
    def __init__(self, current_selection="", category="食材", parent=None):
        super().__init__(parent)
        self.category = category
        self.setWindowTitle(f" 选择当天的{self.category}")
        self.resize(820, 550)
        self.selected_items_str = ""
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", f"{self.category}名称", "数量", "单位", "单价 (元)", "总价 (元)", "备注"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 70)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 80)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 100)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 100)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton(" 全选")
        self.btn_add = QPushButton(" 新增到字库")
        self.btn_del_unit = QPushButton(" 增加/修改/删除 单位")
        self.btn_del = QPushButton(" 删除该词条")
        row_buttons = [self.btn_select_all, self.btn_add, self.btn_del_unit, self.btn_del]
        for btn in row_buttons:
            btn.setMinimumHeight(36)
            btn.setStyleSheet("padding: 6px 16px; font-size: 14px;")
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.btn_confirm = QPushButton(" 确认带回")
        self.btn_confirm.setStyleSheet("background-color: #315f88; color: white; font-weight: bold; padding: 8px; font-size: 14px;")
        layout.addWidget(self.btn_confirm)

        self.btn_select_all.clicked.connect(self.toggle_select_all)
        self.btn_add.clicked.connect(self.add_item)
        self.btn_del_unit.clicked.connect(self.modify_delete_unit)
        self.btn_del.clicked.connect(self.del_item)
        self.btn_confirm.clicked.connect(self.confirm_selection)
        self.load_data(current_selection)

    def load_data(self, current_selection):
        self.table.setRowCount(0)
        df = load_ingredients()
        df_cat = df[df['分类'] == self.category]
        # 数据文件存储的是“名称 数量单位 总价”；单价由总价÷数量还原。
        current_data = {}  # name -> (qty, unit, unit_price, total_price, note)
        for x in current_selection.replace('，', ',').split(','):
            x = x.strip()
            if not x: continue
            x, note = split_item_note(x)
            # 尝试带单位的格式: "牛肉 5斤 50"
            m = re.match(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + get_unit_pattern() + r'?\s+(\d+(?:\.\d+)?)$', x)
            if m:
                name = m.group(1).strip()
                qty = m.group(2)
                unit = m.group(3) or ''
                total_price = m.group(4)
                unit_price = decimal_number(total_price) / decimal_number(qty) if decimal_number(qty) > 0 else 0
                current_data[name] = (qty, unit, f"{unit_price:.6f}", total_price, note)
            else:
                # 旧格式: "牛肉 50"
                m = re.match(r'^(.*?)\s*(\d+(?:\.\d+)?)$', x)
                if m:
                    current_data[m.group(1).strip()] = ('', '', '', m.group(2), note)
                elif x:
                    current_data[x] = ('', '', '', '', note)

        row = 0
        for item in df_cat['词条名称']:
            name = str(item).strip()
            if not name: continue
            self.table.insertRow(row)
            
            # 勾选框（放在第0列）
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            
            # 名称（第1列）
            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemIsEnabled)
            
            if name in current_data:
                chk_item.setCheckState(Qt.Checked)
                qty, unit, unit_price, total_price, note = current_data[name]
            else:
                chk_item.setCheckState(Qt.Unchecked)
                qty, unit, unit_price, total_price, note = '', '', '', '', ''
            
            self.table.setItem(row, 0, chk_item)
            self.table.setItem(row, 1, name_item)
            
            # 数量输入框（第2列）
            qty_edit = QLineEdit()
            qty_edit.setPlaceholderText("数量")
            qty_edit.setText(str(qty) if qty else '')
            self.table.setCellWidget(row, 2, qty_edit)
            
            # 单位下拉框（第3列）
            unit_combo = QComboBox()
            unit_combo.addItems([''] + self.UNITS)
            if unit in self.UNITS:
                unit_combo.setCurrentText(unit)
            self.table.setCellWidget(row, 3, unit_combo)
            
            # 单价输入框（第4列）
            price_edit = QLineEdit()
            price_edit.setPlaceholderText("填单价")
            price_edit.setText(str(unit_price) if unit_price else '')
            self.table.setCellWidget(row, 4, price_edit)

            # 总价输入框（第5列）
            total_edit = QLineEdit()
            total_edit.setPlaceholderText("填总价")
            total_edit.setText(str(total_price) if total_price else '')
            self.table.setCellWidget(row, 5, total_edit)

            note_edit = QLineEdit()
            note_edit.setPlaceholderText("备注")
            note_edit.setText(str(note) if note else '')
            self.table.setCellWidget(row, 6, note_edit)

            # 和“食材明细”一致：修改数量或单价时自动计算总价。
            qty_edit.textChanged.connect(lambda _text, r=row: self._calculate_total(r))
            price_edit.textChanged.connect(lambda _text, r=row: self._calculate_total(r))
            
            row += 1

    def toggle_select_all(self):
        """全选/取消全选切换"""
        all_checked = True
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() != Qt.Checked:
                all_checked = False
                break
        new_state = Qt.Unchecked if all_checked else Qt.Checked
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk:
                chk.setCheckState(new_state)

    def modify_delete_unit(self):
        """修改/删除单位（可拖拽排序、双击编辑、勾选删除）"""
        used_units = set()
        for row in range(self.table.rowCount()):
            unit_widget = self.table.cellWidget(row, 3)
            if unit_widget and isinstance(unit_widget, QComboBox) and unit_widget.currentText().strip():
                used_units.add(unit_widget.currentText().strip())
        open_unit_manager_dialog(self, self.UNITS, used_units, self._refresh_unit_combos)

    
    def _refresh_unit_combos(self, rename_map=None):
        """刷新所有行的单位下拉框"""
        rename_map = rename_map or {}
        for row in range(self.table.rowCount()):
            unit_widget = self.table.cellWidget(row, 3)
            if unit_widget:
                current = unit_widget.currentText()
                current = rename_map.get(current, current)
                unit_widget.blockSignals(True)
                unit_widget.clear()
                unit_widget.addItems([''] + self.UNITS)
                if current in self.UNITS:
                    unit_widget.setCurrentText(current)
                unit_widget.blockSignals(False)

    def add_item(self):
        text, ok = QInputDialog.getText(self, f"新增{self.category}", f"请输入新{self.category}名称:")
        if ok and text.strip():
            df = load_ingredients()
            new_val = text.strip()
            if not df[(df['词条名称'] == new_val) & (df['分类'] == self.category)].empty:
                QMessageBox.warning(self, "提示", f"该{self.category}已存在！")
                return
            df = pd.concat([df, pd.DataFrame([{'词条名称': new_val, '分类': self.category}])], ignore_index=True)
            save_ingredients(df)
            current_checked = self._get_current_inputs()
            current_checked.append(new_val)
            self.load_data(", ".join(current_checked))

    def del_item(self):
        checked_names = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if chk and chk.checkState() == Qt.Checked and name_item:
                checked_names.append(name_item.text())
        if not checked_names: return QMessageBox.information(self, "提示", "请先打勾选中要删除的词条。")
        if QMessageBox.question(self, "删除确认",
                                f"确定要删除选中的 {len(checked_names)} 个词条吗？") == QMessageBox.Yes:
            df = load_ingredients()
            mask = df['词条名称'].astype(str).str.strip().isin(checked_names) & (df['分类'] == self.category)
            df = df[~mask]
            save_ingredients(df)
            self.load_data("")

    def _get_current_inputs(self):
        """返回格式: ["牛肉 5斤 50", "鸡蛋 2打 40", "盐 10"]"""
        selected = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if not chk or not name_item:
                continue
            if chk.checkState() == Qt.Checked:
                name = name_item.text()
                qty_widget = self.table.cellWidget(row, 2)
                unit_widget = self.table.cellWidget(row, 3)
                total_widget = self.table.cellWidget(row, 5)
                note_widget = self.table.cellWidget(row, 6)
                
                qty = qty_widget.text().strip() if qty_widget else ''
                unit = unit_widget.currentText().strip() if unit_widget else ''
                total = total_widget.text().strip() if total_widget else ''
                note = note_widget.text().strip() if note_widget else ''
                
                if qty and total:
                    # 带单位格式: 牛肉 5斤 50
                    selected.append(join_item_note(f"{name} {unit_join(qty, unit)} {total}", note))
                elif total:
                    # 旧格式: 牛肉 50
                    selected.append(join_item_note(f"{name} {total}", note))
                else:
                    selected.append(join_item_note(name, note))
        return selected

    def _calculate_total(self, row):
        """Keep a typed total intact and derive its unit price when possible.

        Older entries can contain only a total price (for example ``牛肉 100``).
        When the user subsequently enters a quantity, the total is the known
        value and must not be treated as zero merely because the unit-price
        cell is still blank.  In that case derive the unit price first; when a
        unit price is already present, quantity × unit price remains the
        authoritative calculation.
        """
        qty_widget = self.table.cellWidget(row, 2)
        price_widget = self.table.cellWidget(row, 4)
        total_widget = self.table.cellWidget(row, 5)
        if not qty_widget or not price_widget or not total_widget:
            return
        qty_text = qty_widget.text().strip()
        price_text = price_widget.text().strip()
        total_text = total_widget.text().strip()
        if not qty_text:
            return
        try:
            qty = decimal_number(qty_text)
            if qty <= 0:
                return
            if price_text:
                total_widget.setText(f"{qty * unit_price_value(price_text):.2f}")
            elif total_text:
                # Preserve the entered total and show the recovered unit price.
                price_widget.setText(f"{decimal_number(total_text) / qty:.6f}".rstrip('0').rstrip('.'))
        except ValueError:
            return

    def confirm_selection(self):
        # 和“食材明细”一致：单价×数量与总价冲突时，由用户选择以哪一个为准。
        needs_review = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if not chk or chk.checkState() != Qt.Checked or not name_item:
                continue
            qty_widget = self.table.cellWidget(row, 2)
            unit_widget = self.table.cellWidget(row, 3)
            price_widget = self.table.cellWidget(row, 4)
            total_widget = self.table.cellWidget(row, 5)
            qty_text = qty_widget.text().strip() if qty_widget else ''
            unit = unit_widget.currentText().strip() if unit_widget else ''
            price_text = price_widget.text().strip() if price_widget else ''
            total_text = total_widget.text().strip() if total_widget else ''
            try:
                qty = decimal_number(qty_text) if qty_text else 0
                unit_price = unit_price_input(price_text) if price_text else 0
                total_price = money_input(total_text) if total_text else 0
            except ValueError:
                QMessageBox.warning(
                    self, "输入类型错误",
                    f"「{name_item.text()}」的数量、单价和总价必须填写纯数字！"
                )
                return
            if qty > 0 and unit_price > 0 and total_price > 0:
                calculated_total = money_amount(qty * unit_price)
                if abs(calculated_total - total_price) > Decimal('0.005'):
                    needs_review.append(
                        (row, name_item.text(), qty_text, unit, qty, unit_price,
                         total_price, calculated_total)
                    )

        if needs_review:
            conflict_msgs = [
                f"「{name}」: {qty_text}{unit} x {unit_price:.6f} = "
                f"{calculated_total:.2f} ≠ 输入总价 {total_price:.2f}"
                for _, name, qty_text, unit, _, unit_price, total_price, calculated_total
                in needs_review
            ]
            msg = (
                f"以下{self.category}的「单价 x 数量」与输入的总价不符：\n"
                + "\n".join(conflict_msgs)
                + "\n\n按「Yes」= 以「单价 x 数量」为准，自动修正总价"
                + "\n按「No」 = 以「总价」为准，自动修正单价"
            )
            choice = QMessageBox.question(
                self, "金额不符", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )

            if choice == QMessageBox.Yes:
                for row, *_rest, calculated_total in needs_review:
                    self.table.cellWidget(row, 5).setText(f"{calculated_total:.2f}")
                changed = "\n".join(
                    f"「{name}」: {qty_text}{unit} x {unit_price:.6f} = {calculated_total:.2f}"
                    for _, name, qty_text, unit, _, unit_price, _, calculated_total
                    in needs_review
                )
                confirm_msg = "已按「单价 x 数量」修正总价：\n" + changed
            else:
                for row, _, _, _, qty, _, total_price, _ in needs_review:
                    self.table.cellWidget(row, 4).setText(f"{total_price / qty:.2f}")
                changed = "\n".join(
                    f"「{name}」: 新单价 {total_price / qty:.2f}"
                    for _, name, _, _, qty, _, total_price, _ in needs_review
                )
                confirm_msg = "已按「总价 ÷ 数量」修正单价：\n" + changed

            if QMessageBox.question(
                    self, "确认修改", confirm_msg + "\n\n确定按此方式带回吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes) != QMessageBox.Yes:
                return

        self.selected_items_str = ", ".join(self._get_current_inputs())
        self.accept()
class InventoryNameCorrectionDialog(QDialog):
    def __init__(self, inventory, category='食材', old_name=''):
        super().__init__(inventory)
        self.inventory = inventory; self.preview = None; self._busy = False; self._final_inputs = {}; self._preview_fields = None
        self.worker = EMBEDDED_SYNC_INSTANCE
        self.dataset_id = str(self.worker.snapshot().get('dataset_id') or '')
        self.request_id = str(uuid.uuid4())
        self.setWindowTitle('品名更正'); self.resize(1120, 760)
        self.setObjectName('inventoryNameCorrectionDialog')
        layout = QVBoxLayout(self)
        hint = QLabel('合并后实际库存由您核对填写；系统将与原两项合计的差额记为本次库存校正，原采购数量和金额保留。更正同步原采购、出入库、菜品明细和词典；不同单位分别填写。')
        hint.setWordWrap(True); layout.addWidget(hint)
        form = QGridLayout()
        self.category = QComboBox(); self.category.addItems(['食材','佐料']); self.category.setCurrentText(category)
        self.old_name = QLineEdit(old_name); self.old_name.setObjectName('correctionOldName')
        self.new_name = QLineEdit(); self.new_name.setObjectName('correctionNewName'); self.new_name.setPlaceholderText('填写正确品名，不填写数量或单位')
        for column, (label, widget) in enumerate([('类别',self.category),('原品名',self.old_name),('正确品名',self.new_name)]):
            form.addWidget(QLabel(label),0,column); form.addWidget(widget,1,column)
        layout.addLayout(form)
        self.reason = QLineEdit(); self.reason.setObjectName('correctionReason'); self.reason.setPlaceholderText('更正原因（必填，将写入修改记录）'); layout.addWidget(self.reason)
        self.summary = QLabel('填写正确品名和原因后，点击预览影响。'); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.results = QTabWidget(); layout.addWidget(self.results,1)
        self.changes = inventory._table(['原记录日期','区段','原品名','正确品名','数量','单位','金额','说明'], 'correctionChanges')
        self.changes.horizontalHeader().setStretchLastSection(True); self.results.addTab(self.changes,'受影响记录')
        self.counts = inventory._table(['日期','单位','原实盘量','更正后实盘量','原账面量','更正后账面量','说明'], 'correctionStocktakes')
        self.counts.horizontalHeader().setStretchLastSection(True); self.results.addTab(self.counts,'盘点换算')
        self.effects = inventory._table(['类别','单位','原品名库存','目标品名库存','原合计','合并后实际库存','校正差额','盘盈单价（可空）'], 'correctionEffects'); self.effects.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.results.addTab(self.effects,'填写实际库存')
        self.warnings = QLabel(''); self.warnings.setWordWrap(True); layout.addWidget(self.warnings)
        self.merge = QCheckBox('我已核对同名合并及盘点换算，确认合并；先进先出批次分摊可能重新计算。'); self.merge.setVisible(False); self.merge.toggled.connect(self._update_apply); layout.addWidget(self.merge)
        actions = QHBoxLayout(); self.preview_button=QPushButton('预览影响'); self.apply_button=QPushButton('确认更正'); self.apply_button.setEnabled(False); self.cancel_button=QPushButton('关闭')
        actions.addWidget(self.preview_button); actions.addStretch(); actions.addWidget(self.cancel_button); actions.addWidget(self.apply_button); layout.addLayout(actions)
        self.preview_button.clicked.connect(self.preview_changes); self.apply_button.clicked.connect(self.apply_changes); self.cancel_button.clicked.connect(self.reject)
        for widget in (self.old_name,self.new_name): widget.textChanged.connect(self._invalidate)
        self.reason.textChanged.connect(self._invalidate_quantities)
        self.category.currentTextChanged.connect(self._invalidate)

    def _fields(self):
        fields={'category':self.category.currentText(),'old_name':self.old_name.text().strip(),'new_name':self.new_name.text().strip()}
        if self._final_inputs:
            quantities=[]
            for unit, values in self._final_inputs.items():
                quantity=_inventory_optional_price(values['quantity']); price=_inventory_optional_price(values['unit_price'])
                if quantity is None:raise ValueError(f'{unit or "无单位"}：请填写非负的合并后实际库存，零库存请填0。')
                if values['unit_price'].strip() and price is None:raise ValueError(f'{unit or "无单位"}：盘盈单价需为非负数字，留空表示待定价。')
                quantities.append({'unit':unit,'quantity':quantity,'unit_price':unit_price_input(price) if price is not None else None})
            fields['final_quantities']=quantities
        return fields

    def _invalidate(self, *_):
        self.preview=None; self._preview_fields=None; self._final_inputs={}; self.request_id=str(uuid.uuid4()); self.apply_button.setEnabled(False)
        self.merge.setChecked(False); self.merge.hide(); self.summary.setText('输入已改变，请重新预览影响。')
        for table in (self.changes,self.counts,self.effects): table.setRowCount(0)
        self.warnings.clear()

    def _invalidate_quantities(self, *_):
        self.preview=None; self._preview_fields=None; self.apply_button.setEnabled(False); self.merge.setChecked(False)
        self.summary.setText('实际库存、单价或原因已改变，请重新预览后确认。')

    def _set_final_input(self, unit, field, value):
        self._final_inputs[unit][field]=value
        self._invalidate_quantities()

    def _populate_effects(self, effects):
        for row in range(self.effects.rowCount()):
            for col in (5,7):
                old=self.effects.cellWidget(row,col)
                if old is not None:
                    old.hide(); self.effects.removeCellWidget(row,col); old.setParent(None); old.deleteLater()
        self.effects.setRowCount(0)
        self.effects.setRowCount(len(effects))
        for row,item in enumerate(effects):
            unit=str(item.get('unit') or '')
            if unit not in self._final_inputs:
                self._final_inputs[unit]={'quantity':str(item.get('combined_quantity',0)),'unit_price':''}
            values=[item.get(key) for key in ('category','unit','source_quantity','target_quantity','combined_quantity')]
            for col,value in enumerate(values):self.effects.setItem(row,col,self.inventory._read_item(value))
            for col,field in ((5,'quantity'),(7,'unit_price')):
                edit=QLineEdit(self._final_inputs[unit][field]); edit.setAlignment(Qt.AlignRight)
                edit.setPlaceholderText('实际库存（可填0）' if field=='quantity' else '留空：待定价')
                edit.setObjectName('correctionFinalQuantity' if field=='quantity' else 'correctionGainPrice')
                edit.textChanged.connect(lambda text,u=unit,f=field:self._set_final_input(u,f,text))
                self.effects.setCellWidget(row,col,edit)
            delta=item.get('delta',safe_float(item.get('after_quantity'))-safe_float(item.get('combined_quantity')))
            self.effects.setItem(row,6,self.inventory._read_item(f'{delta:+g}'))
        self.effects.resizeRowsToContents()

    def _update_apply(self, *_):
        data=self.preview or {}; admin=str(self.worker.snapshot().get('role'))=='admin'
        self.apply_button.setEnabled(not self._busy and admin and bool(data.get('can_apply')) and (not data.get('requires_merge_confirmation') or self.merge.isChecked()))

    def _run(self, action, success):
        if self._busy:return
        self._busy=True
        for widget in (self.category,self.old_name,self.new_name,self.reason,self.preview_button,self.cancel_button,self.merge):widget.setEnabled(False)
        self._update_apply(); result={'done':False}
        def work():
            try:result['value']=action()
            except Exception as exc:result['error']=exc
            finally:result['done']=True
        threading.Thread(target=work,daemon=True).start()
        def poll():
            if not result['done']:QTimer.singleShot(80,poll);return
            self._busy=False
            for widget in (self.category,self.old_name,self.new_name,self.reason,self.preview_button,self.cancel_button,self.merge):widget.setEnabled(True)
            if 'error' in result:
                error=result['error']; self.preview=None
                self.summary.setText(('记录已变化，请重新预览。\n' if getattr(error,'status_code',None)==409 else '')+str(error))
            else:success(result.get('value') or {})
            self._update_apply()
        poll()

    def _populate(self, table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col,value in enumerate(values):table.setItem(row,col,self.inventory._read_item('' if value is None else value))
        table.resizeRowsToContents()

    def preview_changes(self):
        try:fields=self._fields()
        except ValueError as exc:self.summary.setText(str(exc));return
        if not fields['old_name'] or not fields['new_name'] or not self.reason.text().strip():
            self.summary.setText('请填写原品名、正确品名和更正原因。');return
        self.request_id=str(uuid.uuid4())
        self.summary.setText('正在读取影响范围…')
        def show(data):
            self.preview=data; self._preview_fields=exact_json_loads(exact_json_dumps(fields,ensure_ascii=False)); counts=data.get('summary') or {}
            labels={'records':'原记录','purchases':'采购明细','manual_receipts':'手工入库','outbounds':'出库','stocktakes':'盘点','dishes':'菜品明细','dictionary':'词典','settings':'库存设置'}
            self.summary.setText('；'.join(f'{labels[key]} {counts.get(key,0)}' for key in labels))
            section_names={'purchases':'采购明细','manual_receipts':'手工入库','outbounds':'出库','stocktakes':'盘点','dishes':'菜品明细','dictionary':'食材词典','settings':'安全库存'}
            self._populate(self.changes,[[row.get('date') or ('食材词典' if row.get('section')=='dictionary' else '库存设置' if row.get('section')=='settings' else '账本记录'),section_names.get(row.get('section'),row.get('section') or '其他记录'),row.get('before_name'),row.get('after_name'),row.get('quantity'),row.get('unit'),row.get('amount'),row.get('description') or ''] for row in data.get('changes',[])])
            self._populate(self.counts,[[row.get('date'),row.get('unit'),row.get('old_quantity'),row.get('new_quantity'),row.get('old_previous_quantity'),row.get('new_previous_quantity'),row.get('description')] for row in data.get('stocktake_adjustments',[])])
            self._populate_effects(data.get('inventory_effects',[]))
            self.results.setCurrentWidget(self.effects)
            self.effects.doItemsLayout(); self.effects.viewport().update()
            messages=list(data.get('warnings') or [])+[f'无法执行：{value}' for value in data.get('blockers') or []]
            if str(self.worker.snapshot().get('role'))!='admin':messages.append('当前账号仅能预览；执行更正需要管理员。')
            messages.insert(0,'请在“填写实际库存”页核对数量；修改后再次点击预览。盘盈单价留空时成本标为待定价。')
            self.warnings.setText('\n'.join(messages)); self.merge.setVisible(bool(data.get('requires_merge_confirmation'))); self.merge.setChecked(False)
        self._run(lambda:self.worker.preview_inventory_name_correction(fields,self.dataset_id),show)

    def apply_changes(self):
        if not self.preview or not self.apply_button.isEnabled():return
        payload={**self._preview_fields,'preview_token':self.preview.get('preview_token'),'reason':self.reason.text().strip(),'request_id':self.request_id,'confirm_merge':self.merge.isChecked()}
        self.summary.setText('正在提交更正并重新读取账本…')
        def complete(data):
            window=self.inventory.window()
            if hasattr(window,'_refresh_for_current_excel'):window._refresh_for_current_excel()
            self.inventory.refresh_data(); self.inventory.search.setText(payload['new_name'])
            self.inventory.result_label.setText(data.get('message') or '品名已更正，账本已重新读取。')
            self.accept()
        self._run(lambda:self.worker.apply_inventory_name_correction(payload,self.dataset_id),complete)

    def reject(self):
        if not self._busy:super().reject()

    def closeEvent(self,event):
        if self._busy:event.ignore()
        else:super().closeEvent(event)


# ===================== 更多统计页面 =====================
class InventoryTab(QWidget):
    """Document-based inventory workspace; all edits append auditable records."""
    FLOW_NAMES = {'receipt': '入库', 'dish': '菜品领用', 'normal': '领用出库', 'loss': '损耗出库', 'stocktake': '盘点'}

    def __init__(self):
        super().__init__()
        self._loading = True
        self._payload = {}
        self._snapshot_inventory = {'states': {}, 'movements': []}
        self._balances = []
        self._journal_rows = []
        self._drafts = {}
        self.init_ui()
        self._loading = False
        self.refresh_data()
        self.add_receipt_row()
        self.add_outbound_row()
        self.add_stocktake_row()

    @staticmethod
    def _key(row):
        return _inventory_key(row.get('category') or row.get('分类'), row.get('name') or row.get('名称'), row.get('unit') or row.get('单位'))

    @staticmethod
    def _num(value):
        return _inventory_optional_price(value)

    @staticmethod
    def _text(value):
        return f'{value:,.6f}'.rstrip('0').rstrip('.') if isinstance(value, (int, float, Decimal)) else str(value if value is not None else '—')

    @staticmethod
    def _cell(table, row, column):
        widget = table.cellWidget(row, column)
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        item = table.item(row, column)
        return item.text().strip() if item else ''

    @staticmethod
    def _read_item(text, data=None):
        item = QTableWidgetItem(str(text))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if re.fullmatch(r'[+-]?[\d,]+(?:\.\d+)?', str(text)):
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setToolTip(str(text))
        if data is not None:
            item.setData(Qt.UserRole, data)
        return item

    def _table(self, columns, name, editable=False):
        table = QTableWidget(0, len(columns))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(columns)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed if editable else QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(True)
        table.setStyleSheet('QTableWidget { background: #ffffff; alternate-background-color: #f7f9fc; gridline-color: #dbe2eb; font-size: 13px; selection-background-color: #dbeafe; selection-color: #1e3a5f; } QTableWidget::item { padding: 5px 8px; } QHeaderView::section { background: #edf2f7; color: #334155; padding: 8px 10px; border: 0; border-right: 1px solid #dbe2eb; border-bottom: 1px solid #cbd5e1; font-weight: 600; }')
        table.verticalHeader().setMinimumSectionSize(34)
        # Stretch columns settle after first layout; resize wrapped rows again then.
        table._row_size_timer = QTimer(table)
        table._row_size_timer.setSingleShot(True)
        table._row_size_timer.timeout.connect(table.resizeRowsToContents)
        table.horizontalHeader().sectionResized.connect(lambda *_: table._row_size_timer.start(0))
        return table

    def _form_heading(self, layout, kind, prefix, title, hint):
        bar = QHBoxLayout()
        bar.addWidget(QLabel(title))
        number = QLineEdit()
        number.setReadOnly(True)
        number.setMinimumWidth(240)
        bar.addWidget(QLabel('单号'))
        bar.addWidget(number)
        bar.addStretch()
        layout.addLayout(bar)
        label = QLabel(hint)
        label.setWordWrap(True)
        label.setStyleSheet('color:#5F6B7A; padding:4px 0;')
        layout.addWidget(label)
        self._drafts[kind] = {'prefix': prefix, 'number_widget': number}
        self._reset_document(kind)

    def _reset_document(self, kind):
        draft = self._drafts[kind]
        draft['id'] = str(uuid.uuid4())
        draft['number'] = f"{draft['prefix']}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        draft['number_widget'].setText(draft['number'])

    def _buttons(self, layout, specs):
        bar = QHBoxLayout()
        buttons = []
        for label, callback in specs:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
            buttons.append(button)
        bar.addStretch()
        layout.addLayout(bar)
        return buttons

    def init_ui(self):
        self.setObjectName('inventoryWorkspace')
        self.setStyleSheet('QWidget#inventoryWorkspace { background: #f5f7fb; } QWidget#inventoryWorkspace QPushButton { padding: 6px 10px; } QWidget#inventoryWorkspace QTabBar::tab { padding: 8px 16px; }')
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel('库存管理')
        title.setStyleSheet('font-size:16px; font-weight:700;')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel('新单据日期'))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat('yyyy-MM-dd')
        self.date_edit.setEnabled(False)
        header.addWidget(self.date_edit)
        refresh = QPushButton('刷新库存')
        refresh.clicked.connect(self.refresh_data)
        header.addWidget(refresh)
        layout.addLayout(header)
        self.summary_label = QLabel('')
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.work_tabs = QTabWidget()
        layout.addWidget(self.work_tabs, 1)
        overview = QWidget(); box = QVBoxLayout(overview)
        filters = QHBoxLayout()
        self.search = QLineEdit(); self.search.setProperty('financeSearch', True); self.search.setPlaceholderText('搜索食材名称或单位')
        self.category_filter = QComboBox(); self.category_filter.addItems(['全部类别', '食材', '佐料'])
        self.status_filter = QComboBox(); self.status_filter.addItems(['全部状态', '正常', '低于安全库存', '缺货', '负库存', '待定价'])
        self.search_button = QPushButton('搜索'); self.search_button.setObjectName('inventorySearchButton')
        self.search_button.clicked.connect(self.refresh_overview)
        self.search.returnPressed.connect(self.refresh_overview)
        self.clear_search_button = QPushButton('清空')
        self.clear_search_button.clicked.connect(self.clear_overview_filters)
        for widget in (self.search, self.search_button, self.clear_search_button, self.category_filter, self.status_filter): filters.addWidget(widget)
        box.addLayout(filters)
        self.balance_table = self._table(['类别', '名称', '单位', '可用库存', '安全库存', '已知库存价值(元)', '待定价数量', '下批单价(元)', '状态'], 'inventoryOverviewTable')
        self.balance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for column, width in enumerate((76, 240, 76, 125, 125, 180, 140, 160, 220)):
            self.balance_table.setColumnWidth(column, width)
        box.addWidget(self.balance_table)
        overview_actions = self._buttons(box, [('查看批次与追溯', self.show_selected_batches), ('设置安全库存', self.edit_safety_stock), ('品名更正', self.open_name_correction), ('导出库存CSV', lambda: self.export_table(self.balance_table, '库存总览'))])
        self.safety_button = overview_actions[1]
        self.correction_button = overview_actions[2]
        self.balance_table.cellDoubleClicked.connect(lambda *_: self.show_selected_batches())
        self.search.textChanged.connect(self.refresh_overview)
        self.category_filter.currentTextChanged.connect(self.refresh_overview)
        self.status_filter.currentTextChanged.connect(self.refresh_overview)
        self.work_tabs.addTab(overview, '库存总览')

        receipt = QWidget(); box = QVBoxLayout(receipt)
        self._form_heading(box, 'receipt', 'RK', '新建入库单', '手工入库用于另外购入的食材，按填写金额计入采购支出。买食材已自动入库，请勿重复登记；原采购只能回买食材页面修改。')
        self.receipt_note = QLineEdit(); self.receipt_note.setPlaceholderText('供应来源或整单备注（可选）')
        box.addWidget(self.receipt_note)
        self.receipt_table = self._table(['类别', '食材名称', '入库数量', '单位', '采购单价(元)', '金额(元)', '行备注'], 'inventoryReceiptForm')
        self.receipt_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.receipt_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table = self.receipt_table
        box.addWidget(self.receipt_table)
        self.receipt_total = QLabel('入库总额：0.00 元')
        box.addWidget(self.receipt_total)
        self._buttons(box, [('增加明细行', self.add_receipt_row), ('移除选中明细', lambda: self.remove_form_row(self.receipt_table)), ('保存入库单', self.submit_receipt)])
        self.work_tabs.addTab(receipt, '入库单')

        outbound = QWidget(); box = QVBoxLayout(outbound)
        self._form_heading(box, 'outbound', 'CK', '新建出库单', '菜品用量已自动出库；本单用于额外领用或损耗，请勿重复登记同一用量。填写出库数量后按先进先出分摊，同一食材多行累计校验，超库存无法提交。')
        self.outbound_kind = QComboBox(); self.outbound_kind.addItems(['领用出库', '损耗出库'])
        self.outbound_note = QLineEdit(); self.outbound_note.setPlaceholderText('领用用途或损耗原因（必填）')
        bar = QHBoxLayout(); bar.addWidget(self.outbound_kind); bar.addWidget(self.outbound_note, 1); box.addLayout(bar)
        self.outbound_table = self._table(['食材 / 单位', '可用库存', '出库数量', '先进先出批次（数量 × 单价）', '成本(元)', '行备注'], 'inventoryOutboundForm')
        self.outbound_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed); self.outbound_table.setColumnWidth(0, 260)
        self.outbound_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.outbound_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed); self.outbound_table.setColumnWidth(4, 170)
        box.addWidget(self.outbound_table)
        self.outbound_total = QLabel('填写数量后显示批次及成本。'); self.outbound_total.setWordWrap(True); box.addWidget(self.outbound_total)
        self._buttons(box, [('增加明细行', self.add_outbound_row), ('移除选中明细', lambda: self.remove_form_row(self.outbound_table)), ('保存出库单', self.submit_outbound)])
        self.work_tabs.addTab(outbound, '出库单')

        stocktake = QWidget(); box = QVBoxLayout(stocktake)
        self._form_heading(box, 'stocktake', 'PD', '新建盘点单', '填写实际清点数量，系统记录账面数量和差异。盘盈可填写估值单价，留空则标记待定价；盘点不产生现金支出。')
        self.stocktake_note = QLineEdit(); self.stocktake_note.setPlaceholderText('盘点原因 / 差异说明（必填）'); box.addWidget(self.stocktake_note)
        self.stocktake_table = self._table(['食材 / 单位', '账面数量', '实盘数量', '盘盈 / 盘亏', '盘盈单价(可空)', '差异批次 / 成本'], 'inventoryStocktakeForm')
        self.stocktake_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed); self.stocktake_table.setColumnWidth(0, 260)
        self.stocktake_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        box.addWidget(self.stocktake_table)
        self.stocktake_hint = QLabel('每种食材在一张盘点单中只能出现一次。'); self.stocktake_hint.setWordWrap(True); box.addWidget(self.stocktake_hint)
        self._buttons(box, [('增加盘点行', self.add_stocktake_row), ('移除选中明细', lambda: self.remove_form_row(self.stocktake_table)), ('保存盘点单', self.submit_stocktake)])
        self.work_tabs.addTab(stocktake, '盘点单')

        journal = QWidget(); box = QVBoxLayout(journal)
        filters = QHBoxLayout()
        self.flow_search = QLineEdit(); self.flow_search.setProperty('financeSearch', True); self.flow_search.setPlaceholderText('搜索单号、食材或备注')
        self.flow_kind = QComboBox(); self.flow_kind.addItems(['全部类型', '入库', '领用出库', '损耗出库', '菜品领用', '盘点'])
        self.flow_from = QDateEdit(QDate.currentDate().addMonths(-1)); self.flow_to = QDateEdit(QDate.currentDate())
        for w in (self.flow_from, self.flow_to): w.setCalendarPopup(True); w.setDisplayFormat('yyyy-MM-dd')
        for w in (self.flow_search, self.flow_kind, QLabel('从'), self.flow_from, QLabel('至'), self.flow_to): filters.addWidget(w)
        box.addLayout(filters)
        self.flow_table = self._table(['日期 / 单号', '类型 / 状态', '名称', '入库数量', '出库数量', '单位', '批次与单价', '已知成本 / 待定价', '原因 / 备注'], 'inventoryJournalTable')
        self.flow_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed); self.flow_table.setColumnWidth(0, 210)
        self.flow_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.flow_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed); self.flow_table.setColumnWidth(7, 180)
        self.flow_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed); self.flow_table.setColumnWidth(8, 180)
        box.addWidget(self.flow_table)
        self._buttons(box, [('查看单据 / 批次', self.show_selected_document), ('查看采购来源', self.open_purchase_source), ('作废选中手工单据', self.void_selected_document), ('导出流水CSV', lambda: self.export_table(self.flow_table, '库存流水'))])
        self.work_tabs.addTab(journal, '出入库流水')
        for widget in (self.flow_search,): widget.textChanged.connect(self.refresh_journal)
        self.flow_kind.currentTextChanged.connect(self.refresh_journal)
        for widget in (self.flow_from, self.flow_to): widget.dateChanged.connect(self.refresh_journal)
        self.flow_table.cellDoubleClicked.connect(lambda *_: self.show_selected_document())
        self.result_label = QLabel(''); self.result_label.setWordWrap(True); layout.addWidget(self.result_label)

    def _line(self, table, row, column, text='', changed=None):
        edit = QLineEdit(str(text)); edit.setMinimumWidth(80)
        edit.textChanged.connect(changed or self.refresh_previews)
        table.setCellWidget(row, column, edit)
        return edit

    def _item_combo(self, table, row):
        combo = QComboBox(); combo.setMinimumWidth(220)
        combo.addItem('请选择食材', None)
        for item in self._balances:
            key = self._key(item)
            combo.addItem(f"{key[0]} · {key[1]} / {key[2] or '无单位'}", key)
        combo.currentIndexChanged.connect(self.refresh_previews)
        table.setCellWidget(row, 0, combo)
        return combo

    def add_receipt_row(self, _checked=False):
        row = self.receipt_table.rowCount(); self.receipt_table.insertRow(row)
        category = QComboBox(); category.addItems(['食材', '佐料']); self.receipt_table.setCellWidget(row, 0, category)
        self.receipt_table.setItem(row, 0, self._read_item('', str(uuid.uuid4())))
        for column in (1, 2, 4, 6): self._line(self.receipt_table, row, column)
        unit = QComboBox(); unit.setEditable(True); unit.addItems([''] + list(dict.fromkeys(UNITS_LIST))); self.receipt_table.setCellWidget(row, 3, unit)
        unit.currentTextChanged.connect(self.refresh_previews)
        self.receipt_table.setItem(row, 5, self._read_item('—'))
        self.receipt_table.setRowHeight(row, 40)

    def add_outbound_row(self, _checked=False):
        row = self.outbound_table.rowCount(); self.outbound_table.insertRow(row)
        self.outbound_table.setItem(row, 0, self._read_item('', str(uuid.uuid4())))
        self._item_combo(self.outbound_table, row)
        self._line(self.outbound_table, row, 2)
        self._line(self.outbound_table, row, 5)
        for col in (1, 3, 4): self.outbound_table.setItem(row, col, self._read_item('—'))
        self.outbound_table.setRowHeight(row, 45)

    def add_stocktake_row(self, _checked=False):
        row = self.stocktake_table.rowCount(); self.stocktake_table.insertRow(row)
        self.stocktake_table.setItem(row, 0, self._read_item('', str(uuid.uuid4())))
        self._item_combo(self.stocktake_table, row)
        self._line(self.stocktake_table, row, 2)
        self._line(self.stocktake_table, row, 4)
        for col in (1, 3, 5): self.stocktake_table.setItem(row, col, self._read_item('—'))
        self.stocktake_table.setRowHeight(row, 45)

    def remove_form_row(self, table):
        row = table.currentRow()
        if row >= 0: table.removeRow(row); self.refresh_previews()

    def has_unsaved_changes(self):
        if self._loading: return False
        if any(widget.text().strip() for widget in (self.receipt_note, self.outbound_note, self.stocktake_note)): return True
        for table, columns in ((self.receipt_table, (1, 2, 4, 6)), (self.outbound_table, (2, 5)), (self.stocktake_table, (2, 4))):
            if any(self._cell(table, row, col) for row in range(table.rowCount()) for col in columns): return True
        return False

    def _metadata(self, kind, note):
        rows = sum((list(self._payload.get(key, [])) for key in ('entries', 'adjustments', 'overrides')), [])
        return {'document_id': self._drafts[kind]['id'], 'document_no': self._drafts[kind]['number'],
                'recorded_at': _inventory_operation_stamp(rows), 'date': datetime.now().strftime('%Y-%m-%d'), 'note': note}

    def _copy_payload(self):
        return exact_json_loads(exact_json_dumps(self._payload, ensure_ascii=False))

    def _state_quantity(self, key):
        state = self._snapshot_inventory['states'].get(tuple(key), {})
        return sum(lot['remaining'] for lot in state.get('lots', [])) - state.get('debt', 0)

    def _receipt_rows(self, validate=False):
        rows = []
        meta = self._metadata('receipt', self.receipt_note.text().strip())
        for row in range(self.receipt_table.rowCount()):
            name, quantity_text, unit, price_text = (self._cell(self.receipt_table, row, col) for col in (1, 2, 3, 4))
            if not any((name, quantity_text, price_text)): continue
            quantity, price = self._num(quantity_text), self._num(price_text)
            if not name or not unit or quantity is None or quantity <= 0 or price is None:
                if validate: raise ValueError(f'入库第{row + 1}行需填写名称、单位、大于0的数量和非负单价（免费请填0）。')
                continue
            if not (0 <= quantity * price < float('inf')):
                if validate: raise ValueError(f'入库第{row + 1}行金额超出有效范围。')
                continue
            if validate:
                unit_price_input(price); money_input(quantity * unit_price_value(price))
            line_note = self._cell(self.receipt_table, row, 6)
            rows.append({**meta, 'id': self.receipt_table.item(row, 0).data(Qt.UserRole), 'category': self._cell(self.receipt_table, row, 0),
                         'name': name, 'unit': unit, 'quantity': quantity, 'unit_price': unit_price_value(price), 'total': money_amount(quantity * unit_price_value(price)),
                         'source': 'manual', 'price_known': True, 'note': '；'.join(filter(None, (meta['note'], line_note)))})
        if validate and not rows: raise ValueError('请至少填写一行入库明细。')
        return rows

    def _refresh_stock_for_submission(self):
        if _payload_and_hash(_load_inventory_payload())[1] != _payload_and_hash(self._payload)[1]:
            raise ExcelAccessError('库存已更新，请刷新后提交；当前填写仍保留。')
        self._snapshot_inventory = _inventory_fifo_snapshot(payload=self._payload)

    def _outbound_rows(self, validate=False):
        if validate: self._refresh_stock_for_submission()
        rows, used = [], {}
        meta = self._metadata('outbound', self.outbound_note.text().strip())
        if validate and not meta['note']: raise ValueError('请填写领用用途或损耗原因。')
        for row in range(self.outbound_table.rowCount()):
            combo = self.outbound_table.cellWidget(row, 0); key = combo.currentData() if combo else None
            text = self._cell(self.outbound_table, row, 2)
            if not text: continue
            quantity = self._num(text)
            if key is None or quantity is None or quantity <= 0:
                if validate: raise ValueError(f'出库第{row + 1}行需选择食材并填写大于0的数量。')
                continue
            key = tuple(key); used[key] = used.get(key, 0) + quantity
            if validate and used[key] > self._state_quantity(key) + Decimal('1e-9'):
                raise ValueError(f'{key[1]}本单合计出库{used[key]:g}{key[2]}，超过可用库存{self._state_quantity(key):g}{key[2]}。')
            rows.append({**meta, 'id': self.outbound_table.item(row, 0).data(Qt.UserRole), 'category': key[0], 'name': key[1], 'unit': key[2], 'quantity': quantity,
                         'kind': 'loss' if self.outbound_kind.currentIndex() == 1 else 'normal', 'source': 'manual',
                         'note': '；'.join(filter(None, (meta['note'], self._cell(self.outbound_table, row, 5))))})
        if validate and not rows: raise ValueError('请至少填写一行出库明细。')
        return rows

    def _stocktake_rows(self, validate=False):
        if validate: self._refresh_stock_for_submission()
        rows, seen = [], set()
        meta = self._metadata('stocktake', self.stocktake_note.text().strip())
        if validate and not meta['note']: raise ValueError('请填写盘点原因或差异说明。')
        for row in range(self.stocktake_table.rowCount()):
            combo = self.stocktake_table.cellWidget(row, 0); key = combo.currentData() if combo else None
            text, price_text = self._cell(self.stocktake_table, row, 2), self._cell(self.stocktake_table, row, 4)
            if not text: continue
            quantity, price = self._num(text), self._num(price_text)
            if key is None or quantity is None or (price_text and price is None):
                if validate: raise ValueError(f'盘点第{row + 1}行需选择食材，实盘数量与单价不能为负。')
                continue
            if validate and price is not None: unit_price_input(price)
            key = tuple(key)
            if key in seen:
                if validate: raise ValueError(f'{key[1]}在本盘点单重复出现，请合并为一行。')
                continue
            seen.add(key)
            rows.append({**meta, 'id': self.stocktake_table.item(row, 0).data(Qt.UserRole), 'category': key[0], 'name': key[1], 'unit': key[2],
                         'quantity': quantity, 'previous_quantity': self._state_quantity(key), 'unit_price': unit_price_value(price) if price is not None else None, 'price_known': price is not None})
        if validate and not rows: raise ValueError('请至少填写一行实盘数量；数量为零时请填0。')
        return rows

    def refresh_previews(self, *_args):
        if self._loading: return
        total = 0
        for row in range(self.receipt_table.rowCount()):
            qty, price = self._num(self._cell(self.receipt_table, row, 2)), self._num(self._cell(self.receipt_table, row, 4))
            value = money_amount(qty * unit_price_value(price)) if qty is not None and price is not None else None
            self.receipt_table.setItem(row, 5, self._read_item(f'{value:,.2f}' if value is not None else '—'))
            total += value or 0
        self.receipt_total.setText(f'入库总额：{total:,.2f} 元（保存后计入采购支出）')
        for kind, table, collector, array in (('outbound', self.outbound_table, self._outbound_rows, 'adjustments'), ('stocktake', self.stocktake_table, self._stocktake_rows, 'overrides')):
            draft = collector(False); candidate = self._copy_payload(); candidate.setdefault(array, []).extend(draft)
            snapshot = _inventory_fifo_snapshot(payload=candidate)
            selected = {item.get('id'): item for item in snapshot['movements'] if item.get('document_id') == self._drafts[kind]['id']}
            accumulated, invalid, known, unknown = {}, False, 0, 0
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 0); key = combo.currentData() if combo else None
                available = self._state_quantity(tuple(key)) if key is not None else None
                table.setItem(row, 1, self._read_item(self._text(available)))
                movement = selected.get(table.item(row, 0).data(Qt.UserRole))
                quantity = self._num(self._cell(table, row, 2))
                if kind == 'outbound':
                    if key is not None and quantity is not None:
                        key = tuple(key); accumulated[key] = accumulated.get(key, 0) + quantity
                        over = accumulated[key] > available + Decimal('1e-9'); invalid = invalid or over
                    else: over = False
                    table.setItem(row, 3, self._read_item('超过可用库存，无法提交' if over else _inventory_fifo_description(movement) if movement else '填写数量后预览'))
                    table.setItem(row, 4, self._read_item(_inventory_fifo_cost_text(movement) if movement else '—'))
                else:
                    difference = quantity - available if available is not None and quantity is not None else None
                    table.setItem(row, 3, self._read_item(f'{difference:+g}' if difference is not None else '—'))
                    table.setItem(row, 5, self._read_item((_inventory_fifo_description(movement) + '；成本 ' + _inventory_fifo_cost_text(movement)) if movement else '填写实盘数量后预览'))
                if movement: known += movement['known_cost']; unknown += movement['unknown_quantity']
            table.resizeRowsToContents()
            if kind == 'outbound':
                self.outbound_total.setText('本单存在超库存明细，无法提交。' if invalid else f'本单已知成本：{known:,.2f} 元' + ('；部分批次待定价' if unknown else ''))

    def _commit(self, candidate, kind, rows, table, note_widget, add_row):
        _inventory_save_payload(candidate, expected_hash=_payload_and_hash(self._payload)[1])
        number = self._drafts[kind]['number']
        self._loading = True; table.setRowCount(0); note_widget.clear(); self._reset_document(kind); self._loading = False
        self.refresh_data(); add_row()
        self.result_label.setText(f'{number} 已保存，共{len(rows)}行；正在同步云端。')

    def submit_receipt(self):
        try:
            rows = self._receipt_rows(True); candidate = self._copy_payload(); candidate.setdefault('entries', []).extend(rows)
            self._commit(candidate, 'receipt', rows, self.receipt_table, self.receipt_note, self.add_receipt_row)
        except (ValueError, ExcelAccessError, ExcelFormatError) as exc: QMessageBox.warning(self, '入库单未保存', str(exc))

    def submit_outbound(self):
        try:
            rows = self._outbound_rows(True); candidate = self._copy_payload(); candidate.setdefault('adjustments', []).extend(rows)
            self._commit(candidate, 'outbound', rows, self.outbound_table, self.outbound_note, self.add_outbound_row)
        except (ValueError, ExcelAccessError, ExcelFormatError) as exc: QMessageBox.warning(self, '出库单未保存', str(exc))

    def submit_stocktake(self):
        try:
            rows = self._stocktake_rows(True); candidate = self._copy_payload(); candidate.setdefault('overrides', []).extend(rows)
            self._commit(candidate, 'stocktake', rows, self.stocktake_table, self.stocktake_note, self.add_stocktake_row)
        except (ValueError, ExcelAccessError, ExcelFormatError) as exc: QMessageBox.warning(self, '盘点单未保存', str(exc))

    def refresh_data(self):
        self._loading = True
        self.date_edit.setDate(QDate.currentDate())
        self._payload = _load_inventory_payload()
        self._snapshot_inventory = _inventory_fifo_snapshot(payload=self._payload)
        self._balances = calculate_inventory_balances()
        for table in (self.outbound_table, self.stocktake_table):
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, 0); selected = combo.currentData()
                combo.blockSignals(True); combo.clear(); combo.addItem('请选择食材', None)
                for item in self._balances:
                    key = self._key(item); combo.addItem(f'{key[0]} · {key[1]} / {key[2] or "无单位"}', key)
                index = next((i for i in range(combo.count()) if combo.itemData(i) == selected), 0)
                combo.setCurrentIndex(index); combo.blockSignals(False)
        _purchases, pending = _inventory_purchase_entries()
        known = sum(row['已知库存价值'] for row in self._balances)
        unknown = sum(1 for row in self._balances if row['待定价数量'] > Decimal('1e-9'))
        self.summary_label.setText(f'共 {len(self._balances)} 种库存 · 已知库存价值 {known:,.2f} 元 · {unknown} 种待定价' + (f' · {len(pending)} 条采购未填数量/单位，请回买食材补齐' if pending else ''))
        self.safety_button.setEnabled(_desktop_cloud_role() in {'admin', 'editor'} and NETWORK_EDIT_ALLOWED)
        self.correction_button.setEnabled(_desktop_cloud_role() in {'admin','editor'} and bool(EMBEDDED_SYNC_INSTANCE and EMBEDDED_SYNC_INSTANCE.snapshot().get('connected')))
        self._loading = False
        self.refresh_overview(); self.refresh_journal(); self.refresh_previews()

    def open_name_correction(self):
        worker = EMBEDDED_SYNC_INSTANCE
        if not worker or not worker.snapshot().get('connected') or _desktop_cloud_role() not in {'admin','editor'}:
            QMessageBox.warning(self,'无法更正','品名更正仅供在线管理员或修改权限账号使用。');return
        window=self.window()
        unsaved=window._unsaved_sections() if hasattr(window,'_unsaved_sections') else (['库存单据'] if self.has_unsaved_changes() else [])
        if unsaved:
            QMessageBox.warning(self,'请先保存','请先保存或取消未保存内容：'+'、'.join(unsaved));return
        key=self._selected_key() or ('食材','','')
        InventoryNameCorrectionDialog(self,key[0],key[1]).exec()

    def clear_overview_filters(self):
        self.search.clear(); self.category_filter.setCurrentIndex(0); self.status_filter.setCurrentIndex(0)
        self.refresh_overview()

    def refresh_overview(self, *_args):
        if self._loading: return
        search = self.search.text().strip().casefold(); category = self.category_filter.currentText(); status = self.status_filter.currentText()
        rows = [row for row in self._balances if (category == '全部类别' or row['分类'] == category)
                and (not search or search in (row['名称'] + ' ' + row['单位']).casefold())
                and (status == '全部状态' or status in row['库存状态'])]
        self.balance_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [row['分类'], row['名称'], row['单位'] or '无单位', self._text(row['当前剩余']), self._text(row['安全库存']), f"{row['已知库存价值']:,.2f}", self._text(row['待定价数量']), ('待定价' if row['当前剩余'] > 0 and row['下批单价'] is None else self._text(row['下批单价'])), row['库存状态']]
            for col, value in enumerate(values): self.balance_table.setItem(index, col, self._read_item(value, self._key(row) if col == 0 else None))
        self.balance_table.resizeRowsToContents()

    def _all_journal_rows(self):
        rows = [dict(row) for row in self._snapshot_inventory['movements']]
        for array, kind in (('entries', 'receipt'), ('adjustments', 'normal')):
            source = _inventory_normalize_entries(self._payload.get(array, []), True) if array == 'entries' else self._payload.get(array, [])
            for index, row in enumerate(source):
                if not isinstance(row, dict) or not _inventory_is_voided(row): continue
                qty = safe_float(row.get('quantity', row.get('数量', 0)))
                date = pd.to_datetime(str(row.get('date') or row.get('日期') or ''), errors='coerce')
                if pd.isna(date): continue
                rows.append({**row, 'date': date.strftime('%Y-%m-%d'), 'id': str(row.get('id') or f'legacy:adjustment:{index}'), 'kind': kind if array == 'entries' else _inventory_adjustment_kind(row), 'direction': 'in' if array == 'entries' else 'out',
                             'quantity': qty, 'known_cost': 0, 'unknown_quantity': 0, 'layers': [], 'voided': True})
        return sorted(rows, key=lambda row: (str(row.get('date') or row.get('日期') or ''), str(row.get('recorded_at') or '')), reverse=True)

    def refresh_journal(self, *_args):
        if self._loading: return
        start, end = self.flow_from.date().toString('yyyy-MM-dd'), self.flow_to.date().toString('yyyy-MM-dd')
        search, kind = self.flow_search.text().strip().casefold(), self.flow_kind.currentText()
        self._journal_rows = [row for row in self._all_journal_rows() if start <= str(row.get('date') or row.get('日期') or '') <= end
            and (kind == '全部类型' or self.FLOW_NAMES.get(row['kind']) == kind)
            and (not search or search in ' '.join(str(row.get(key) or '') for key in ('document_no', 'name', 'note', 'void_reason')).casefold())]
        self.flow_table.setRowCount(len(self._journal_rows))
        for index, row in enumerate(self._journal_rows):
            voided = _inventory_is_voided(row)
            source = '已作废' if voided else '买食材自动入库' if row.get('source') == 'purchase' else '菜品自动出库' if row['kind'] == 'dish' else '手工入库' if row['kind'] == 'receipt' else '手工领用' if row['kind'] == 'normal' else '手工损耗' if row['kind'] == 'loss' else '盘点单'
            note = str(row.get('note') or row.get('dish') or '') + (f"；作废原因：{row.get('void_reason', '')}" if voided else '')
            values = [str(row.get('date') or row.get('日期') or '') + '\n' + str(row.get('document_no') or '历史记录 / 自动记录'),
                self.FLOW_NAMES.get(row['kind'], row['kind']) + '\n' + source, row.get('name') or row.get('名称') or '',
                self._text(row['quantity']) if row['direction'] == 'in' else '—', self._text(row['quantity']) if row['direction'] == 'out' else '—', row.get('unit') or row.get('单位') or '无单位',
                '已作废，不参与库存' if voided else _inventory_fifo_description(row), '—' if voided else _inventory_fifo_cost_text(row), note]
            for col, value in enumerate(values): self.flow_table.setItem(index, col, self._read_item(value, row if col == 0 else None))
        self.flow_table.resizeRowsToContents()

    def _selected_key(self):
        row = self.balance_table.currentRow(); item = self.balance_table.item(row, 0)
        return tuple(item.data(Qt.UserRole)) if item and item.data(Qt.UserRole) else None

    def _selected_movement(self):
        item = self.flow_table.item(self.flow_table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def show_selected_batches(self):
        key = self._selected_key()
        if key is None: QMessageBox.information(self, '选择库存', '请先选中一行库存。'); return
        self.show_batch_dialog(key)

    def show_batch_dialog(self, key):
        state = self._snapshot_inventory['states'].get(tuple(key), {})
        dialog = QDialog(self); dialog.setWindowTitle(f'{key[1]} / {key[2] or "无单位"} · 批次与追溯'); dialog.resize(1120, 680)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f'{key[0]} · {key[1]} · 可用库存 {self._state_quantity(key):g}{key[2]}'))
        tabs = QTabWidget(); layout.addWidget(tabs)
        lots = self._table(['入库日期', '单号 / 来源', '剩余数量', '单位', '原单价(元)', '已知价值(元)', '备注'], 'inventoryBatchDetails')
        lots.horizontalHeader().setStretchLastSection(True)
        layers = state.get('lots', []); lots.setRowCount(len(layers))
        for index, lot in enumerate(layers):
            price = lot.get('unit_price'); values = [lot['date'], lot.get('document_no') or ('买食材自动入库' if lot.get('source') == 'purchase' else '历史入库 / 盘盈'), self._text(lot['remaining']), key[2] or '无单位', self._text(price), f"{lot['remaining_cost']:,.2f}" if price is not None else '待定价', lot.get('note', '')]
            for col, value in enumerate(values): lots.setItem(index, col, self._read_item(value))
        lots.resizeRowsToContents(); tabs.addTab(lots, '当前批次（按出库顺序）')
        trace = self._table(['日期', '单号', '类型', '变化数量', '批次 / 单价', '成本'], 'inventoryBatchTrace')
        trace.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch); trace.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed); trace.setColumnWidth(5, 180)
        movements = [row for row in self._all_journal_rows() if self._key(row) == tuple(key)]; trace.setRowCount(len(movements))
        for index, row in enumerate(movements):
            sign = '+' if row['direction'] == 'in' else '-'; values = [row.get('date', ''), row.get('document_no') or '历史 / 自动记录', self.FLOW_NAMES.get(row['kind']) + ('（作废）' if _inventory_is_voided(row) else ''), sign + self._text(row['quantity']), _inventory_fifo_description(row), '—' if _inventory_is_voided(row) else _inventory_fifo_cost_text(row)]
            for col, value in enumerate(values): trace.setItem(index, col, self._read_item(value))
        trace.resizeRowsToContents(); tabs.addTab(trace, '完整流水追溯')
        close = QPushButton('关闭'); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def show_selected_document(self):
        row = self._selected_movement()
        if not row: QMessageBox.information(self, '选择单据', '请先选中一条流水。'); return
        dialog = QDialog(self); dialog.setWindowTitle(str(row.get('document_no') or '历史 / 自动记录')); dialog.resize(1080, 560)
        layout = QVBoxLayout(dialog); label = QLabel(f"单号：{row.get('document_no') or '历史 / 自动记录'}\n时间：{row.get('recorded_at') or row.get('date', '')}\n备注：{row.get('note') or row.get('dish') or '—'}" + (f"\n作废原因：{row.get('void_reason', '')}" if _inventory_is_voided(row) else '')); label.setWordWrap(True); layout.addWidget(label)
        rows = [item for item in self._all_journal_rows() if item.get('document_id') == row.get('document_id')] if row.get('document_id') else [row]
        table = self._table(['类型', '名称', '数量', '单位', '先进先出分摊', '成本'], 'inventoryDocumentDetails'); table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch); table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed); table.setColumnWidth(5, 180); table.setRowCount(len(rows))
        for index, item in enumerate(rows):
            values = [self.FLOW_NAMES.get(item['kind']), item.get('name') or item.get('名称'), self._text(item['quantity']), item.get('unit') or item.get('单位'), _inventory_fifo_description(item), '—' if _inventory_is_voided(item) else _inventory_fifo_cost_text(item)]
            for col, value in enumerate(values): table.setItem(index, col, self._read_item(value))
        table.resizeRowsToContents(); layout.addWidget(table); close = QPushButton('关闭'); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def open_purchase_source(self):
        row = self._selected_movement()
        if not row or row.get('source') != 'purchase': QMessageBox.information(self, '采购来源', '请选择一条买食材自动入库流水；手工单据可使用“查看单据 / 批次”。'); return
        window = self.window(); target = getattr(window, 'ingredient_detail', None)
        if target is not None and hasattr(window, 'tabs'):
            date = QDate.fromString(row['date'], 'yyyy-MM-dd')
            window.tabs.setCurrentWidget(target)
            if window.tabs.currentWidget() is not target: return
            # MainWindow carries the previous tab's date during tab switching.
            # Apply the source date afterward so historical purchases open correctly.
            if hasattr(target, 'set_date_safely'): target.set_date_safely(date)
        else: QMessageBox.information(self, '采购来源', f"请打开买食材 / 食材明细，选择 {row['date']} 修改原采购；库存会自动更新。")

    def edit_safety_stock(self):
        if _desktop_cloud_role() not in {'admin', 'editor'}:
            QMessageBox.warning(self, '权限不足', '仅管理员或修改权限账号可设置安全库存。'); return
        key = self._selected_key()
        if key is None: QMessageBox.information(self, '选择库存', '请先选中一行库存。'); return
        original = next((item for item in self._payload.get('item_settings', []) if self._key(item) == key), {})
        dialog = QDialog(self); dialog.setWindowTitle(f'{key[1]} · 安全库存'); layout = QFormLayout(dialog)
        enabled = QCheckBox('启用安全库存提示'); enabled.setChecked('min_quantity' in original); layout.addRow(enabled)
        value = QLineEdit(str(original.get('min_quantity', ''))); value.setPlaceholderText(f'数量（{key[2]}）'); layout.addRow('安全库存数量', value)
        save = QPushButton('保存安全库存'); cancel = QPushButton('取消'); layout.addRow(save, cancel); cancel.clicked.connect(dialog.reject)
        def commit():
            try:
                number = self._num(value.text().strip())
                if enabled.isChecked() and number is None: raise ValueError('安全库存需填写非负数量。')
                candidate = self._copy_payload(); settings = [item for item in candidate.get('item_settings', []) if self._key(item) != key]
                if enabled.isChecked(): settings.append({**original, 'category': key[0], 'name': key[1], 'unit': key[2], 'min_quantity': number})
                candidate['item_settings'] = settings; _inventory_save_payload(candidate, expected_hash=_payload_and_hash(self._payload)[1]); self.refresh_data(); dialog.accept()
            except (ValueError, ExcelAccessError, ExcelFormatError) as exc: QMessageBox.warning(dialog, '未保存', str(exc))
        save.clicked.connect(commit); dialog.exec()

    def _void_candidate(self, selected, reason):
        if not reason.strip(): raise ValueError('作废原因不能为空。')
        if selected.get('source') == 'purchase': raise ValueError('自动采购入库请回买食材修改原记录，不能在库存作废。')
        if selected.get('kind') not in ('receipt', 'normal', 'loss'): raise ValueError('只允许作废手工入库单和手工出库单；盘点请新增盘点单纠正。')
        if _inventory_is_voided(selected): raise ValueError('此单据已经作废。')
        array = 'entries' if selected['kind'] == 'receipt' else 'adjustments'; candidate = self._copy_payload(); matched = 0
        for index, row in enumerate(candidate.get(array, [])):
            if not isinstance(row, dict): continue
            row_id = str(row.get('id') or ('legacy:' + hashlib.sha256((str(index) + exact_json_dumps(row, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:20] if array == 'entries' else f'legacy:adjustment:{index}'))
            match = row.get('document_id') == selected.get('document_id') if selected.get('document_id') else row_id and row_id == selected.get('id')
            if not match: continue
            if row.get('source') == 'purchase': raise ValueError('自动采购不能作废。')
            row.update(voided=True, void_reason=reason.strip(), voided_at=datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'); matched += 1
        if not matched: raise ValueError('找不到该单据；请刷新库存后重试。')
        baseline = _inventory_fifo(_inventory_receipts(self._payload), _inventory_consumption_rows(), self._payload.get('adjustments', []), self._payload.get('overrides', []))
        changed = _inventory_fifo(_inventory_receipts(candidate), _inventory_consumption_rows(), candidate.get('adjustments', []), candidate.get('overrides', []))
        def shortage_key(item):
            return (item.get('id'), item.get('kind'), item.get('date'), self._key(item))
        baseline_shortage = {shortage_key(item): item.get('shortage_quantity', 0) for item in baseline['movements']}
        if array == 'entries' and any(item.get('shortage_quantity', 0) > baseline_shortage.get(shortage_key(item), 0) + Decimal('1e-9') for item in changed['movements']):
            raise ValueError('该入库已被后续出库使用，作废会新增库存短缺。请先纠正相关出库或盘点单。')
        return candidate, matched, changed

    def void_selected_document(self):
        selected = self._selected_movement()
        if not selected: QMessageBox.information(self, '选择单据', '请先选中需要作废的手工单据。'); return
        role = _desktop_cloud_role()
        entry_allowed = False
        if role == 'entry':
            stamp = _parse_entry_stamp(selected.get('recorded_at'))
            entry_allowed = stamp is not None and datetime.now().astimezone() < stamp + timedelta(minutes=30)
        if role not in {'admin', 'editor'} and not entry_allowed:
            QMessageBox.warning(self, '权限不足', '录入账号仅可在单据保存后30分钟内作废；之后需要管理员或修改权限。'); return
        reason, ok = QInputDialog.getMultiLineText(self, '作废原因', '单据整单作废，原记录保留。请填写原因：')
        if not ok: return
        try:
            candidate, count, snapshot = self._void_candidate(selected, reason)
            key = self._key(selected); state = snapshot['states'].get(key, {}); remaining = sum(lot['remaining'] for lot in state.get('lots', [])) - state.get('debt', 0)
            question = f"作废 {selected.get('document_no') or '历史单据'}，共{count}行。\n{key[1]}作废后账面库存：{remaining:g}{key[2]}。\n后续有盘点时，当前库存可能保持不变。\n确认作废？"
            if QMessageBox.question(self, '确认作废', question, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
            _inventory_save_payload(candidate, expected_hash=_payload_and_hash(self._payload)[1]); self.refresh_data(); self.result_label.setText('单据已作废并保留原因、时间和原记录。')
        except (ValueError, ExcelAccessError, ExcelFormatError) as exc: QMessageBox.warning(self, '未作废', str(exc))

    @staticmethod
    def _csv_safe(value):
        text = str(value if value is not None else '')
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text

    def export_table(self, table, label):
        path, _ = QFileDialog.getSaveFileName(self, '导出CSV', f'{label}_{datetime.now():%Y%m%d}.csv', 'CSV 文件 (*.csv)')
        if not path: return
        try:
            import csv
            with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow([self._csv_safe(table.horizontalHeaderItem(col).text()) for col in range(table.columnCount())])
                for row in range(table.rowCount()): writer.writerow([self._csv_safe(table.item(row, col).text() if table.item(row, col) else '') for col in range(table.columnCount())])
            self.result_label.setText(f'已导出当前筛选结果：{path}')
        except OSError as exc: QMessageBox.warning(self, '导出失败', str(exc))


# ===================== 更多统计页面 =====================
class ForecastSummaryPanel(QWidget):
    """Compact, wrapping forecast display shared by desktop statistic views.

    Keeping titles and amounts in separate widgets means the explanatory text
    can wrap on narrow screens while every monetary value remains visibly
    right-aligned.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.revenue_note_label = QLabel("(本月截至目前的日均收入 x 本月总天数)")
        self.revenue_note_label.setWordWrap(True)
        layout.addWidget(self.revenue_note_label)

        self.revenue_value = self._add_amount_row(layout, "本月收入预测")
        # Keep one clearly visible blank line between the two forecast blocks.
        self.revenue_blank_line = QLabel(" ")
        layout.addWidget(self.revenue_blank_line)
        self.net_value = self._add_amount_row(layout, "预计月底盈亏")

        self.net_note_label = QLabel("(根据上月总成本和本月收入预测)")
        self.net_note_label.setWordWrap(True)
        layout.addWidget(self.net_note_label)
        self.net_blank_line = QLabel(" ")
        layout.addWidget(self.net_blank_line)

        self.break_even_title_label = QLabel(
            "平本需要 日均收入 (“收入”指“Revenue”) 增加\n"
            "( (预计月底盈亏/本月毛利率) / 本月天数 )"
        )
        self.break_even_title_label.setWordWrap(True)
        self.break_even_title_label.setToolTip(
            "预计月底为亏损时，以亏损绝对值计算需要增加的日均 Revenue；"
            "若本月毛利率不大于 0，则无法计算。"
        )
        layout.addWidget(self.break_even_title_label)
        self.break_even_value = self._add_amount_row(layout, "")

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#667085;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

    @staticmethod
    def _add_amount_row(layout, title):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        if title:
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            title_label.setMinimumWidth(0)
            title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout.addWidget(title_label, 1)
        else:
            row_layout.addStretch(1)
        value_label = QLabel("-")
        value_label.setMinimumWidth(0)
        value_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_label.setStyleSheet("font-weight:600;")
        row_layout.addWidget(value_label, 0)
        layout.addWidget(row)
        return value_label

    @staticmethod
    def _money(value):
        return f"{decimal_number(value):,.2f} 元" if value is not None else "—"

    def set_values(self, projected_revenue=None, projected_net=None, break_even_increase=None, status=""):
        self.revenue_value.setText(self._money(projected_revenue))
        # Expected month-end P/L is intentionally only an amount.  Its sign is
        # enough to distinguish profit from loss; no percentage belongs here.
        self.net_value.setText(self._money(projected_net))
        self.break_even_value.setText(self._money(break_even_increase))
        self.status_label.setText(str(status or ""))
        self.status_label.setVisible(bool(status))


class MoreStatsTab(QWidget):
    """用组合筛选代替固定“分析维度”。

    - 明细：展示每日经营数据、逐日食材采购或菜品实际食材消耗；
    - 平均：展示月度日均、星期日均、食材加权平均或消耗日均；
    - 月份、星期、指标、采购食材和消耗食材均可自由组合。
    """

    WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    RATE_METRICS = {"毛利率(%)", "净利率(%)", "新客比例(%)", "老客比例(%)", "客单价(平均)"}

    def __init__(self):
        super().__init__()
        self.selected_food_items = set()
        self.selected_consumption_items = set()
        today = QDate.currentDate()
        self._month_anchor = QDate(today.year(), today.month(), 1)
        self._last_table_export = pd.DataFrame()
        self.init_ui()
        self.refresh()

    # ---------- UI ----------
    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_scroll.setStyleSheet("QScrollArea { border: none; }")
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setSpacing(6)

        top = QGridLayout()
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(5)

        top.addWidget(QLabel("统计方式:"), 0, 0)
        self.check_detail = QCheckBox("明细")
        self.check_average = QCheckBox("平均")
        self.check_detail.setChecked(True)
        self.check_detail.setToolTip("按日显示经营数据；食材单价按实际采购日期显示。")
        self.check_average.setToolTip("显示月度日均、星期日均或食材加权平均。可与“明细”同时勾选。")
        top.addWidget(self.check_detail, 0, 1)
        top.addWidget(self.check_average, 0, 2)

        top.addWidget(QLabel("年份:"), 0, 3)
        self.combo_year = QComboBox()
        current_year = QDate.currentDate().year()
        self.combo_year.addItems([str(year) for year in range(2015, current_year + 6)])
        self.combo_year.setCurrentText(str(current_year))
        self.combo_year.setFixedWidth(95)
        top.addWidget(self.combo_year, 0, 4)

        self.btn_prev_year = QPushButton("上一年")
        self.btn_this_year = QPushButton("今年")
        self.btn_next_year = QPushButton("下一年")
        for button in (self.btn_prev_year, self.btn_this_year, self.btn_next_year):
            button.setStyleSheet("padding: 2px 8px;")
            top.addWidget(button, 0, top.columnCount())

        
        self.btn_export = QPushButton("导出CSV")
        self.btn_export.setStyleSheet("background-color: #596d82; color: white; padding: 4px 12px;")
        self.btn_export.setFixedWidth(105)
        top.addWidget(self.btn_export, 0, top.columnCount())
        top.setColumnStretch(top.columnCount(), 1)
        main_layout.addLayout(top)

        month_layout = QHBoxLayout()
        month_layout.addWidget(QLabel("月份:"))
        self.month_checks = []
        current_month = QDate.currentDate().month()
        for month in range(1, 13):
            checkbox = QCheckBox(f"{month}月")
            checkbox.setChecked(month == current_month)
            checkbox.stateChanged.connect(
                lambda _state, selected_month=month: self._on_month_check_changed(selected_month)
            )
            self.month_checks.append(checkbox)
            month_layout.addWidget(checkbox)

        self.btn_prev_month = QPushButton("上个月")
        self.btn_current_month = QPushButton("本月")
        self.btn_next_month = QPushButton("下个月")
        self.btn_q1 = QPushButton("Q1")
        self.btn_q2 = QPushButton("Q2")
        self.btn_q3 = QPushButton("Q3")
        self.btn_q4 = QPushButton("Q4")
        self.btn_q1.setToolTip("第一季度：1月－3月")
        self.btn_q2.setToolTip("第二季度：4月－6月")
        self.btn_q3.setToolTip("第三季度：7月－9月")
        self.btn_q4.setToolTip("第四季度：10月－12月")
        self.btn_month_all = QPushButton("全选")
        self.btn_month_none = QPushButton("全不选")
        for button in (
            self.btn_prev_month, self.btn_current_month, self.btn_next_month,
            self.btn_q1, self.btn_q2, self.btn_q3, self.btn_q4,
            self.btn_month_all, self.btn_month_none,
        ):
            button.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            month_layout.addWidget(button)
        month_layout.addStretch()
        main_layout.addLayout(month_layout)

        weekday_layout = QHBoxLayout()
        weekday_layout.addWidget(QLabel("星期:"))
        self.weekday_checks = []
        for index, name in enumerate(self.WEEKDAY_NAMES):
            checkbox = QCheckBox(name[-1])
            checkbox.setChecked(True)
            checkbox.setToolTip(name)
            self.weekday_checks.append(checkbox)
            weekday_layout.addWidget(checkbox)
        self.btn_weekday_all = QPushButton("全选")
        self.btn_weekday_none = QPushButton("全不选")
        self.btn_workday = QPushButton("工作日")
        self.btn_weekend = QPushButton("周末")
        for button in (
            self.btn_weekday_all, self.btn_weekday_none,
            self.btn_workday, self.btn_weekend,
        ):
            button.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            weekday_layout.addWidget(button)
        weekday_layout.addStretch()
        main_layout.addLayout(weekday_layout)

        self.business_group = QGroupBox("经营指标")
        metric_layout = QGridLayout(self.business_group)
        metric_layout.setHorizontalSpacing(12)
        metric_layout.setVerticalSpacing(3)
        self.metric_names = [
            "收入", "毛利润", "毛利率(%)", "净利润", "净利率(%)",
            "总客人数", "新客人数量", "老客人数", "新客比例(%)", "老客比例(%)",
            "客单价(平均)", "A店收入", "B店收入", "食材+佐料成本",
            "水电+其他", "固定成本", "(总成本-固定成本)", "总成本",
        ]
        self.metric_checks = []
        for index, name in enumerate(self.metric_names):
            checkbox = QCheckBox(name)
            checkbox.setChecked(name == "毛利润")
            checkbox.stateChanged.connect(
                lambda _state, metric=name: self._on_metric_check_changed(metric)
            )
            self.metric_checks.append(checkbox)
            metric_layout.addWidget(checkbox, index // 5, index % 5)
        self.btn_metric_none = QPushButton("全不选")
        self.btn_metric_none.setStyleSheet("padding: 2px 10px; font-size: 11px;")
        metric_layout.addWidget(self.btn_metric_none, (len(self.metric_names) + 4) // 5, 4)
        main_layout.addWidget(self.business_group)

        self.food_group = QGroupBox("食材采购")
        food_layout = QHBoxLayout(self.food_group)
        food_layout.addWidget(QLabel("食材指标:"))
        self.combo_food_metric = QComboBox()
        self.combo_food_metric.addItems([
            "单价随时间变化",
            "每月采购总价",
            "每月采购量",
            "每月平均单价",
        ])
        self.combo_food_metric.setFixedWidth(175)
        food_layout.addWidget(self.combo_food_metric)
        food_layout.addWidget(QLabel("食材（可多选）:"))
        self.btn_select_food = QPushButton("选择食材（未选择）")
        self.btn_select_food.setMinimumWidth(260)
        food_layout.addWidget(self.btn_select_food)
        self.btn_clear_food = QPushButton("清空食材")
        food_layout.addWidget(self.btn_clear_food)
        self.lbl_food_hint = QLabel("不选食材时显示经营指标；选了食材后，图表自动切换为该食材分析。同一食材不同单位会分开统计。")
        self.lbl_food_hint.setStyleSheet("color: #667085;")
        food_layout.addWidget(self.lbl_food_hint)
        food_layout.addStretch()
        main_layout.addWidget(self.food_group)

        self.consumption_group = QGroupBox("食材消耗（来自“当日做出的菜品”）")
        consumption_layout = QHBoxLayout(self.consumption_group)
        consumption_layout.addWidget(QLabel("消耗指标:"))
        self.combo_consumption_metric = QComboBox()
        self.combo_consumption_metric.addItems([
            "每日消耗量变化",
            "每月消耗总量",
            "每月日均消耗量",
            "累计消耗量",
        ])
        self.combo_consumption_metric.setFixedWidth(175)
        consumption_layout.addWidget(self.combo_consumption_metric)
        consumption_layout.addWidget(QLabel("食材（可多选）:"))
        self.btn_select_consumption = QPushButton("选择消耗食材（未选择）")
        self.btn_select_consumption.setMinimumWidth(260)
        consumption_layout.addWidget(self.btn_select_consumption)
        self.btn_clear_consumption = QPushButton("清空消耗食材")
        consumption_layout.addWidget(self.btn_clear_consumption)
        self.lbl_consumption_hint = QLabel(
            "按菜品中填写的实际总用量统计，不再乘菜品份数；不同单位分开统计，旧记录未填数量时不计入用量。"
        )
        self.lbl_consumption_hint.setStyleSheet("color: #667085;")
        consumption_layout.addWidget(self.lbl_consumption_hint)
        consumption_layout.addStretch()
        main_layout.addWidget(self.consumption_group)

        self.forecast_group = QGroupBox("平本收入预测")
        store_layout = QVBoxLayout(self.forecast_group)
        self.month_forecast_panel = ForecastSummaryPanel(self.forecast_group)
        self.month_forecast_panel.setStyleSheet("color:#475467;")
        store_layout.addWidget(self.month_forecast_panel)
        main_layout.addWidget(self.forecast_group)

        visible_layout = QHBoxLayout()
        visible_layout.addWidget(QLabel("显示内容:"))
        self.view_checks = {}
        for key, label in [
            ("trend", "趋势图"),
            ("compare", "月度/食材对比图"),
            ("weekday", "星期图"),
            ("table", "数据表"),
        ]:
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.refresh)
            self.view_checks[key] = checkbox
            visible_layout.addWidget(checkbox)
        self.btn_view_all = QPushButton("全选")
        self.btn_view_none = QPushButton("全不选")
        self.btn_view_table = QPushButton("只看表格")
        for button in (self.btn_view_all, self.btn_view_none, self.btn_view_table):
            button.setStyleSheet("padding: 2px 8px; font-size: 11px;")
            visible_layout.addWidget(button)
        visible_layout.addStretch()
        main_layout.addLayout(visible_layout)

        content = QWidget()
        self.stats_content = content
        grid = QGridLayout(content)
        self.canvas_trend = FigureCanvas(Figure())
        self.canvas_compare = FigureCanvas(Figure())
        self.canvas_weekday = FigureCanvas(Figure())
        for canvas in (self.canvas_trend, self.canvas_compare, self.canvas_weekday):
            canvas.setMinimumSize(620, 420)
        grid.addWidget(self.canvas_trend, 0, 0)
        grid.addWidget(self.canvas_compare, 0, 1)
        grid.addWidget(self.canvas_weekday, 1, 0, 1, 2)

        self.table_stats = WheelPassThroughTableWidget()
        self.table_stats.setMinimumHeight(300)
        self.table_stats.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_stats.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_stats.setAlternatingRowColors(True)
        grid.addWidget(self.table_stats, 2, 0, 1, 2)

        self.inventory_stats_group = QGroupBox('食材+佐料当前剩余量（累计入库－菜品出库－正常使用－损耗）')
        inventory_layout = QVBoxLayout(self.inventory_stats_group)
        inventory_hint = QLabel('不同单位分开统计；正常使用与损耗分别记录，直接覆盖调整不影响统计。该表始终显示当前账本的实时结余。')
        inventory_hint.setStyleSheet('color:#667085;')
        inventory_layout.addWidget(inventory_hint)
        self.table_inventory_balance = WheelPassThroughTableWidget()
        self.table_inventory_balance.setColumnCount(10)
        self.table_inventory_balance.setHorizontalHeaderLabels([
            '分类', '名称', '单位', '累计入库', '菜品出库', '正常使用', '损耗', '当前剩余', '库存状态', '最近入库'
        ])
        self.table_inventory_balance.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_inventory_balance.setAlternatingRowColors(True)
        self.table_inventory_balance.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_inventory_balance.setMinimumHeight(210)
        inventory_layout.addWidget(self.table_inventory_balance)
        grid.addWidget(self.inventory_stats_group, 3, 0, 1, 2)

        outbound_group = QGroupBox('正常消耗与损耗指标（跟随上方年份、月份和星期筛选）')
        outbound_layout = QVBoxLayout(outbound_group)
        outbound_hint = QLabel(
            '菜品页填写的是当天实际总用量，保存后直接算出库，不乘菜品份数；'
            '“正常使用调整”单独计入正常消耗，“损耗调整”只计损耗，直接覆盖调整不进统计。'
        )
        outbound_hint.setWordWrap(True)
        outbound_hint.setStyleSheet('color:#667085;')
        outbound_layout.addWidget(outbound_hint)
        self.outbound_tabs = QTabWidget()
        self.table_monthly_outbound = WheelPassThroughTableWidget()
        self.table_normal_adjustment = WheelPassThroughTableWidget()
        self.table_dish_servings = WheelPassThroughTableWidget()
        self.table_inventory_loss = WheelPassThroughTableWidget()
        for table in (self.table_monthly_outbound, self.table_normal_adjustment, self.table_dish_servings, self.table_inventory_loss):
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setMinimumHeight(220)
        self.outbound_tabs.addTab(self.table_monthly_outbound, '月度食材+佐料出库')
        self.outbound_tabs.addTab(self.table_normal_adjustment, '正常使用调整')
        self.outbound_tabs.addTab(self.table_dish_servings, '每日菜品份数')
        self.outbound_tabs.addTab(self.table_inventory_loss, '食材+佐料损耗')
        self.table_fifo_outbound = WheelPassThroughTableWidget()
        self.table_fifo_outbound.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_fifo_outbound.setAlternatingRowColors(True)
        self.table_fifo_outbound.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.outbound_tabs.addTab(self.table_fifo_outbound, '出库入库价 · 先进先出')
        outbound_layout.addWidget(self.outbound_tabs)
        grid.addWidget(outbound_group, 4, 0, 1, 2)

        main_layout.addWidget(content, 1)
        self.stats_scroll.setWidget(page)
        outer_layout.addWidget(self.stats_scroll)
        self._install_stats_wheel_filters()

        self.check_detail.stateChanged.connect(lambda _state: self._on_mode_changed(self.check_detail))
        self.check_average.stateChanged.connect(lambda _state: self._on_mode_changed(self.check_average))
        self.combo_year.currentTextChanged.connect(self._on_year_changed)
        self.combo_food_metric.currentTextChanged.connect(self.refresh)
        self.btn_select_food.clicked.connect(self._choose_food_items)
        self.btn_clear_food.clicked.connect(self._clear_food_items)
        self.combo_consumption_metric.currentTextChanged.connect(self.refresh)
        self.btn_select_consumption.clicked.connect(self._choose_consumption_items)
        self.btn_clear_consumption.clicked.connect(self._clear_consumption_items)
        self.btn_metric_none.clicked.connect(self._clear_business_metrics)
        self.btn_export.clicked.connect(self.export_data)

        self.btn_prev_year.clicked.connect(lambda: self._shift_year(-1))
        self.btn_this_year.clicked.connect(self._select_this_year)
        self.btn_next_year.clicked.connect(lambda: self._shift_year(1))
        self.btn_prev_month.clicked.connect(lambda: self._shift_month(-1))
        self.btn_current_month.clicked.connect(self._select_current_month)
        self.btn_next_month.clicked.connect(lambda: self._shift_month(1))
        self.btn_q1.clicked.connect(lambda: self._set_months([1, 2, 3]))
        self.btn_q2.clicked.connect(lambda: self._set_months([4, 5, 6]))
        self.btn_q3.clicked.connect(lambda: self._set_months([7, 8, 9]))
        self.btn_q4.clicked.connect(lambda: self._set_months([10, 11, 12]))
        self.btn_month_all.clicked.connect(lambda: self._set_months(range(1, 13)))
        self.btn_month_none.clicked.connect(lambda: self._set_months([]))

        self.btn_weekday_all.clicked.connect(lambda: self._set_weekdays([True] * 7))
        self.btn_weekday_none.clicked.connect(lambda: self._set_weekdays([False] * 7))
        self.btn_workday.clicked.connect(lambda: self._set_weekdays([True] * 5 + [False] * 2))
        self.btn_weekend.clicked.connect(lambda: self._set_weekdays([False] * 5 + [True] * 2))
        for checkbox in self.weekday_checks:
            checkbox.stateChanged.connect(self.refresh)

        self.btn_view_all.clicked.connect(lambda: self._set_visible_views(self.view_checks.keys()))
        self.btn_view_none.clicked.connect(lambda: self._set_visible_views([]))
        self.btn_view_table.clicked.connect(lambda: self._set_visible_views(["table"]))

    def _install_stats_wheel_filters(self):
        for widget in (
            self.stats_scroll.viewport(), self.stats_content,
            self.canvas_trend, self.canvas_compare, self.canvas_weekday,
            self.table_stats, self.table_stats.viewport(),
            self.table_inventory_balance, self.table_inventory_balance.viewport(),
        ):
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and hasattr(self, "stats_scroll"):
            if obj in (self.table_stats, self.table_stats.viewport()):
                return self.table_stats.handle_wheel_event(event, self.stats_scroll)
            if obj in (self.table_inventory_balance, self.table_inventory_balance.viewport()):
                return self.table_inventory_balance.handle_wheel_event(event, self.stats_scroll)
            bar = self.stats_scroll.verticalScrollBar()
            delta = _wheel_delta_for_scrollbar(event, bar)
            if delta:
                _apply_wheel_to_scrollbar(bar, delta)
                event.accept()
                return True
        return super().eventFilter(obj, event)

    # ---------- 选择器 ----------
    def _is_food_analysis_active(self):
        return bool(self.selected_food_items)

    def _is_consumption_analysis_active(self):
        return bool(self.selected_consumption_items)

    def _on_mode_changed(self, changed_checkbox):
        if not self.check_detail.isChecked() and not self.check_average.isChecked():
            changed_checkbox.blockSignals(True)
            changed_checkbox.setChecked(True)
            changed_checkbox.blockSignals(False)
        self.refresh()

    def _on_metric_check_changed(self, _metric):
        # 经营指标允许全部不选；此时图表和数据表统一输出 0。
        self.refresh()

    def _clear_business_metrics(self):
        for checkbox in self.metric_checks:
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self.refresh()

    def _selected_metrics(self):
        return [self.metric_names[i] for i, checkbox in enumerate(self.metric_checks) if checkbox.isChecked()]

    def _selected_months(self):
        return [month for month, checkbox in enumerate(self.month_checks, start=1) if checkbox.isChecked()]

    def _selected_weekdays(self):
        return [index for index, checkbox in enumerate(self.weekday_checks) if checkbox.isChecked()]

    def _selected_modes(self):
        return self.check_detail.isChecked(), self.check_average.isChecked()

    def _current_year(self):
        text = self.combo_year.currentText()
        return int(text) if text.isdigit() else QDate.currentDate().year()

    def _set_months(self, months, year=None):
        selected = {int(month) for month in months}
        for month, checkbox in enumerate(self.month_checks, start=1):
            checkbox.blockSignals(True)
            checkbox.setChecked(month in selected)
            checkbox.blockSignals(False)
        if year is not None:
            self._ensure_year_option(int(year))
            self.combo_year.blockSignals(True)
            self.combo_year.setCurrentText(str(int(year)))
            self.combo_year.blockSignals(False)
        if len(selected) == 1:
            month = next(iter(selected))
            self._month_anchor = QDate(self._current_year(), month, 1)
        self.refresh()

    def _on_month_check_changed(self, month):
        if self.month_checks[month - 1].isChecked():
            self._month_anchor = QDate(self._current_year(), month, 1)
        self.refresh()

    def _set_weekdays(self, states):
        for checkbox, state in zip(self.weekday_checks, states):
            checkbox.blockSignals(True)
            checkbox.setChecked(state)
            checkbox.blockSignals(False)
        self.refresh()

    def _set_visible_views(self, visible_keys):
        visible_keys = set(visible_keys)
        for key, checkbox in self.view_checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(key in visible_keys)
            checkbox.blockSignals(False)
        self.refresh()

    def _ensure_year_option(self, year):
        values = [self.combo_year.itemText(index) for index in range(self.combo_year.count())]
        if str(year) not in values:
            self.combo_year.addItem(str(year))
            model = sorted(
                [self.combo_year.itemText(index) for index in range(self.combo_year.count())],
                key=lambda value: int(value),
            )
            self.combo_year.blockSignals(True)
            self.combo_year.clear()
            self.combo_year.addItems(model)
            self.combo_year.blockSignals(False)

    def _shift_year(self, delta):
        year = self._current_year() + int(delta)
        self._ensure_year_option(year)
        self.combo_year.setCurrentText(str(year))

    def _select_this_year(self):
        year = QDate.currentDate().year()
        self._ensure_year_option(year)
        self.combo_year.setCurrentText(str(year))

    def _shift_month(self, delta):
        selected = self._selected_months()
        if len(selected) == 1:
            anchor = QDate(self._current_year(), selected[0], 1)
        else:
            anchor = self._month_anchor
        target = anchor.addMonths(int(delta))
        self._month_anchor = target
        self._set_months([target.month()], target.year())

    def _select_current_month(self):
        today = QDate.currentDate()
        self._month_anchor = QDate(today.year(), today.month(), 1)
        self._set_months([today.month()], today.year())

    def _on_year_changed(self):
        selected = self._selected_months()
        if len(selected) == 1:
            self._month_anchor = QDate(self._current_year(), selected[0], 1)
        self._refresh_food_button_options()
        self._refresh_consumption_button_options()
        self.refresh()

    def _food_names_for_year(self):
        daily = self._with_dates(load_daily())
        year = self._current_year()
        if daily.empty:
            return []
        daily = daily[daily["日期_dt"].dt.year == year]
        names = set()
        for _, row in daily.iterrows():
            for part in re.split(r"[,，]", str(row.get("食材明细", "") or "")):
                parsed = self._parse_food_part(part)
                if parsed:
                    names.add(parsed["食材"])
        return sorted(names)

    def _refresh_food_button_options(self):
        available = set(self._food_names_for_year())
        self.selected_food_items = {name for name in self.selected_food_items if name in available}
        self._update_food_button_text()

    def _update_food_button_text(self):
        selected = sorted(self.selected_food_items)
        if not selected:
            text = "选择食材（不选则看经营指标）"
        elif len(selected) <= 3:
            text = "已选：" + "、".join(selected)
        else:
            text = "已选：" + "、".join(selected[:3]) + f" 等 {len(selected)} 种"
        self.btn_select_food.setText(text)
        self.btn_select_food.setToolTip("、".join(selected))

    def _choose_food_items(self):
        names = self._food_names_for_year()
        if not names:
            QMessageBox.information(self, "没有食材记录", "所选年份没有可以分析的食材采购记录。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("选择食材（可多选）")
        dialog.resize(440, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("按住 Command/Shift 可以连续或追加选择，也可以直接逐项点击。"))
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for name in names:
            list_widget.addItem(name)
            item = list_widget.item(list_widget.count() - 1)
            item.setSelected(name in self.selected_food_items)
        layout.addWidget(list_widget, 1)

        actions = QHBoxLayout()
        select_all = QPushButton("全选")
        clear_all = QPushButton("清空")
        cancel = QPushButton("取消")
        confirm = QPushButton("确定")
        confirm.setDefault(True)
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)

        select_all.clicked.connect(list_widget.selectAll)
        clear_all.clicked.connect(list_widget.clearSelection)
        cancel.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.Accepted:
            return
        self.selected_food_items = {item.text() for item in list_widget.selectedItems()}
        if self.selected_food_items:
            self.selected_consumption_items.clear()
            self._update_consumption_button_text()
        self._update_food_button_text()
        self.refresh()

    def _clear_food_items(self):
        if not self.selected_food_items:
            return
        self.selected_food_items.clear()
        self._update_food_button_text()
        self.refresh()

    def _parse_consumption_parts(self, detail_text):
        """解析菜品使用食材；数量即菜品页填写的当日实际总用量。"""
        parts = []
        unit_regex = re.compile(
            r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + get_unit_pattern()
            + r'?\s+(\d+(?:\.\d+)?)$'
        )
        for raw_part in re.split(r'[,，]', str(detail_text or '')):
            raw_part = raw_part.strip()
            if not raw_part:
                continue
            clean, _note = split_item_note(raw_part)
            match = unit_regex.match(clean)
            if match:
                parts.append({
                    "食材": match.group(1).strip(),
                    "数量": safe_float(match.group(2)),
                    "单位": str(match.group(3) or "").strip() or "无单位",
                    "成本": money_amount(match.group(4)),
                    "数量已填写": True,
                })
                continue
            legacy = re.match(r'^(.*?)\s*(\d+(?:\.\d+)?)$', clean)
            if legacy and legacy.group(1).strip():
                parts.append({
                    "食材": legacy.group(1).strip(),
                    "数量": 0,
                    "单位": "无单位",
                    "成本": money_amount(legacy.group(2)),
                    "数量已填写": False,
                })
            elif clean:
                parts.append({
                    "食材": clean,
                    "数量": 0,
                    "单位": "无单位",
                    "成本": 0,
                    "数量已填写": False,
                })
        return parts

    def _consumption_names_for_year(self):
        dishes = self._with_dates(load_dishes())
        if dishes.empty:
            return []
        today = pd.Timestamp(datetime.now().date())
        dishes = dishes[
            (dishes["日期_dt"].dt.year == self._current_year())
            & (dishes["日期_dt"] <= today)
        ]
        names = set()
        for _, record in dishes.iterrows():
            for dish_row in dish_rows_from_record(record):
                for item in self._parse_consumption_parts(dish_row.get("食材明细", "")):
                    if item.get("数量已填写") and item.get("食材"):
                        names.add(str(item["食材"]))
        return sorted(names)

    def _refresh_consumption_button_options(self):
        available = set(self._consumption_names_for_year())
        self.selected_consumption_items = {
            name for name in self.selected_consumption_items if name in available
        }
        self._update_consumption_button_text()

    def _update_consumption_button_text(self):
        selected = sorted(self.selected_consumption_items)
        if not selected:
            text = "选择消耗食材（未选择）"
        elif len(selected) <= 3:
            text = "已选消耗：" + "、".join(selected)
        else:
            text = "已选消耗：" + "、".join(selected[:3]) + f" 等 {len(selected)} 种"
        self.btn_select_consumption.setText(text)
        self.btn_select_consumption.setToolTip("、".join(selected))

    def _choose_consumption_items(self):
        names = self._consumption_names_for_year()
        if not names:
            QMessageBox.information(
                self,
                "没有食材消耗记录",
                "所选年份的“当日做出的菜品”中，没有填写了具体数量的食材记录。",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("选择食材消耗（可多选）")
        dialog.resize(440, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("选择后会分析菜品模块记录的实际用量；同名食材的不同单位仍会分开显示。"))
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for name in names:
            list_widget.addItem(name)
            item = list_widget.item(list_widget.count() - 1)
            item.setSelected(name in self.selected_consumption_items)
        layout.addWidget(list_widget, 1)

        actions = QHBoxLayout()
        select_all = QPushButton("全选")
        clear_all = QPushButton("清空")
        cancel = QPushButton("取消")
        confirm = QPushButton("确定")
        confirm.setDefault(True)
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)

        select_all.clicked.connect(list_widget.selectAll)
        clear_all.clicked.connect(list_widget.clearSelection)
        cancel.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.Accepted:
            return
        self.selected_consumption_items = {
            item.text() for item in list_widget.selectedItems()
        }
        if self.selected_consumption_items:
            self.selected_food_items.clear()
            self._update_food_button_text()
        self._update_consumption_button_text()
        self.refresh()

    def _clear_consumption_items(self):
        if not self.selected_consumption_items:
            return
        self.selected_consumption_items.clear()
        self._update_consumption_button_text()
        self.refresh()

    # ---------- 数据整理 ----------
    def _with_dates(self, frame):
        frame = frame.copy()
        if frame.empty or "日期" not in frame.columns:
            return frame
        frame["日期"] = frame["日期"].astype(str)
        frame["日期_dt"] = pd.to_datetime(frame["日期"], errors="coerce")
        return frame.dropna(subset=["日期_dt"]).sort_values("日期_dt")

    def _filtered_daily(self, apply_weekday=True):
        frame = self._with_dates(load_daily())
        months = self._selected_months()
        weekdays = self._selected_weekdays()
        if frame.empty or not months:
            return frame.iloc[0:0].copy()
        frame = frame[
            (frame["日期_dt"].dt.year == self._current_year())
            & frame["日期_dt"].dt.month.isin(months)
            & (frame["日期_dt"] <= pd.Timestamp(datetime.now().date()))
        ]
        if apply_weekday:
            if not weekdays:
                return frame.iloc[0:0].copy()
            frame = frame[frame["日期_dt"].dt.weekday.isin(weekdays)]
        return frame.sort_values("日期_dt")

    def _business_frame(self):
        daily = self._filtered_daily()
        all_daily = load_daily()
        fixed = load_monthly_fixed()
        rows = []
        for _, row in daily.iterrows():
            day = str(row["日期"])
            metrics = calc_day_metrics(day, all_daily, fixed)
            if not metrics:
                continue
            dt = pd.to_datetime(day, errors="coerce")
            if pd.isna(dt):
                continue
            detail = metrics.get("开销明细", {})
            revenue = decimal_number(metrics.get("收益", 0) or 0)
            gross = decimal_number(metrics.get("毛利", 0) or 0)
            net = decimal_number(metrics.get("净利润", 0) or 0)
            total_customers = decimal_number(metrics.get("总客人数", 0) or 0)
            new_customers = decimal_number(metrics.get("新客人数量", 0) or 0)
            old_customers = decimal_number(metrics.get("老客人数", 0) or 0)
            food_cost = decimal_number(metrics.get("食材成本", 0) or 0)
            seasoning_cost = decimal_number(metrics.get("佐料成本", 0) or 0)
            total_cost = decimal_number(metrics.get("总成本", 0) or 0)
            fixed_cost = decimal_number(metrics.get("固定分摊", 0) or 0)
            rows.append({
                "日期": day,
                "日期_dt": dt,
                "月份": dt.strftime("%Y-%m"),
                "星期序号": int(dt.weekday()),
                "星期": self.WEEKDAY_NAMES[int(dt.weekday())],
                "收入": revenue,
                "毛利润": gross,
                "毛利率(%)": decimal_divide(gross, revenue) * 100 if revenue else 0,
                "净利润": net,
                "净利率(%)": decimal_divide(net, revenue) * 100 if revenue else 0,
                "总客人数": total_customers,
                "新客人数量": new_customers,
                "老客人数": old_customers,
                "新客比例(%)": decimal_divide(new_customers, total_customers) * 100 if total_customers else 0,
                "老客比例(%)": decimal_divide(old_customers, total_customers) * 100 if total_customers else 0,
                "客单价(平均)": decimal_divide(revenue, total_customers) if total_customers else 0,
                "A店收入": money_amount(row.get('A店收入', 0)),
                "B店收入": money_amount(row.get('B店收入', 0)),
                "食材成本": food_cost,
                "佐料成本": seasoning_cost,
                "食材+佐料成本": food_cost + seasoning_cost,
                "水电+其他": decimal_number(detail.get("日结水电", 0) or 0) + decimal_number(detail.get("其他", 0) or 0),
                "固定成本": fixed_cost,
                "(总成本-固定成本)": total_cost - fixed_cost,
                "总成本": total_cost,
            })
        return pd.DataFrame(rows)

    def _aggregate_business_metric(self, frame, metric, average=False):
        if frame.empty:
            return 0
        if metric == "新客比例(%)":
            total = decimal_number(frame["总客人数"].sum())
            return decimal_number(decimal_divide(frame['新客人数量'].sum(), total) * 100) if total else 0
        if metric == "老客比例(%)":
            total = decimal_number(frame["总客人数"].sum())
            return decimal_number(decimal_divide(frame['老客人数'].sum(), total) * 100) if total else 0
        if metric == "客单价(平均)":
            total = decimal_number(frame["总客人数"].sum())
            return decimal_number(decimal_divide(frame['收入'].sum(), total)) if total else 0
        if metric == "毛利率(%)":
            revenue = decimal_number(frame["收入"].sum())
            return decimal_number(decimal_divide(frame['毛利润'].sum(), revenue) * 100) if revenue else 0
        if metric == "净利率(%)":
            revenue = decimal_number(frame["收入"].sum())
            return decimal_number(decimal_divide(frame['净利润'].sum(), revenue) * 100) if revenue else 0
        if metric not in frame.columns:
            return 0
        return decimal_number(decimal_divide(decimal_sum(frame[metric]), len(frame)) if average else decimal_sum(frame[metric]))

    def _parse_food_part(self, part):
        part = str(part).strip()
        if not part:
            return None
        part, _note = split_item_note(part)
        unit_pattern = get_unit_pattern()
        match = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?)\s*" + unit_pattern + r"?\s+(\d+(?:\.\d+)?)$", part)
        if not match:
            match = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?)\s+(.+?)\s+(\d+(?:\.\d+)?)$", part)
        if not match:
            return None
        try:
            name = match.group(1).strip()
            quantity = decimal_number(match.group(2))
            unit = (match.group(3) or "").strip()
            total_price = money_amount(match.group(4))
        except (ValueError, IndexError):
            return None
        if not name or quantity <= 0:
            return None
        return {
            "食材": name,
            "数量": quantity,
            "单位": unit or "无单位",
            "总价": total_price,
            "单价": total_price / quantity,
        }

    def _food_frame(self):
        daily = self._filtered_daily()
        rows = []
        if daily.empty or not self.selected_food_items:
            return pd.DataFrame(rows)
        for _, row in daily.iterrows():
            day = str(row.get("日期", ""))
            dt = pd.to_datetime(day, errors="coerce")
            if pd.isna(dt):
                continue
            for part in re.split(r"[,，]", str(row.get("食材明细", "") or "")):
                parsed = self._parse_food_part(part)
                if not parsed or parsed["食材"] not in self.selected_food_items:
                    continue
                parsed.update({
                    "日期": day,
                    "日期_dt": dt,
                    "月份": dt.strftime("%Y-%m"),
                    "星期序号": int(dt.weekday()),
                    "星期": self.WEEKDAY_NAMES[int(dt.weekday())],
                    "系列": f"{parsed['食材']}（{parsed['单位']}）",
                })
                rows.append(parsed)
        return pd.DataFrame(rows).sort_values("日期_dt") if rows else pd.DataFrame(rows)

    def _food_group_value(self, frame, metric, average=False):
        if frame.empty:
            return 0
        quantity = decimal_number(frame["数量"].sum())
        total = decimal_number(frame["总价"].sum())
        active_days = max(int(frame["日期"].nunique()), 1)
        if metric in ("单价随时间变化", "每月平均单价"):
            return decimal_divide(total, quantity) if quantity else 0
        if metric == "每月采购总价":
            return decimal_divide(total, active_days) if average else total
        if metric == "每月采购量":
            return decimal_divide(quantity, active_days) if average else quantity
        return 0

    def _consumption_frame(self):
        dishes = self._with_dates(load_dishes())
        rows = []
        if dishes.empty or not self.selected_consumption_items:
            return pd.DataFrame(rows)
        months = self._selected_months()
        weekdays = self._selected_weekdays()
        dishes = dishes[
            (dishes["日期_dt"].dt.year == self._current_year())
            & dishes["日期_dt"].dt.month.isin(months)
            & dishes["日期_dt"].dt.weekday.isin(weekdays)
            & (dishes["日期_dt"] <= pd.Timestamp(datetime.now().date()))
        ]
        for _, record in dishes.iterrows():
            day = str(record.get("日期", ""))
            dt = pd.to_datetime(day, errors="coerce")
            if pd.isna(dt):
                continue
            for dish_row in dish_rows_from_record(record):
                dish_name = str(dish_row.get("菜品名称", "")).strip() or "未命名菜品"
                servings = safe_float(dish_row.get("份数", 0))
                for item in self._parse_consumption_parts(dish_row.get("食材明细", "")):
                    if not item.get("数量已填写"):
                        continue
                    food_name = str(item.get("食材", "")).strip()
                    if food_name not in self.selected_consumption_items:
                        continue
                    unit = str(item.get("单位", "") or "无单位").strip()
                    rows.append({
                        "日期": day,
                        "日期_dt": dt,
                        "月份": dt.strftime("%Y-%m"),
                        "星期序号": int(dt.weekday()),
                        "星期": self.WEEKDAY_NAMES[int(dt.weekday())],
                        "食材": food_name,
                        "数量": decimal_number(item.get("数量", 0) or 0),
                        "单位": unit,
                        "成本": decimal_number(item.get("成本", 0) or 0),
                        "菜品": dish_name,
                        "菜品份数": servings,
                        "系列": f"{food_name}（{unit}）",
                    })
        return pd.DataFrame(rows).sort_values("日期_dt") if rows else pd.DataFrame(rows)

    def _consumption_group_value(self, frame, metric, average=False):
        if frame.empty:
            return 0
        quantity = decimal_number(frame["数量"].sum())
        active_days = max(int(frame["日期"].nunique()), 1)
        if metric == "每月日均消耗量":
            return decimal_divide(quantity, active_days)
        if average:
            return decimal_divide(quantity, active_days)
        return quantity

    def _consumption_month_matrix(self, frame, metric, months=None):
        detail_mode, average_mode = self._selected_modes()
        month_list = [int(month) for month in (months if months is not None else self._selected_months())]
        labels = [f"{month}月" for month in month_list]
        series = {}
        if frame.empty:
            return labels, series
        for series_name in sorted(frame["系列"].unique()):
            group = frame[frame["系列"] == series_name]
            totals, averages = [], []
            for month in month_list:
                sub = group[group["日期_dt"].dt.month == month]
                totals.append(self._consumption_group_value(sub, metric, average=False))
                averages.append(self._consumption_group_value(sub, metric, average=True))
            if metric == "每月日均消耗量":
                series[series_name] = averages
            else:
                if detail_mode:
                    series[f"{series_name}（合计）"] = totals
                if average_mode:
                    series[f"{series_name}（消耗日均）"] = averages
        return labels, series

    # ---------- 绘图工具 ----------
    def _format_value(self, metric, value):
        if "(%)" in metric:
            return f"{decimal_number(value):,.2f}%"
        return f"{decimal_number(value):,.2f}"

    def _empty_canvas(self, canvas, message):
        figure = canvas.figure
        figure.clear()
        axis = figure.add_subplot(111)
        axis.axis("off")
        axis.text(0.5, 0.5, message, ha="center", va="center", fontsize=14, color="#667085")
        canvas.draw_idle()

    @staticmethod
    def _chart_value_text(value, series_name=""):
        """Return compact, non-scientific labels for chart data points."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        if pd.isna(number):
            return ""
        if "(%)" in str(series_name):
            return f"{number:,.2f}%"
        return f"{number:,.2f}"

    @staticmethod
    def _remember_value_annotation(axis, annotation):
        annotations = getattr(axis, "_restaurant_value_annotations", None)
        if annotations is None:
            annotations = []
            setattr(axis, "_restaurant_value_annotations", annotations)
        annotations.append(annotation)

    def _annotate_line_points(self, axis, x_positions, values, series_name="", series_index=0, display_texts=None):
        """Put a label beside every finite point and register it for collision avoidance."""
        base_offset = 8 + (series_index // 2) * 9
        direction = 1 if series_index % 2 == 0 else -1
        for point_index, (x_value, y_value) in enumerate(zip(x_positions, values)):
            try:
                number = float(y_value)
            except (TypeError, ValueError):
                continue
            if pd.isna(number):
                continue
            vertical_offset = direction * base_offset
            # A small left/centre/right fan keeps neighbouring long labels from sharing
            # exactly the same screen position before the collision resolver runs.
            horizontal_offset = ((point_index + series_index) % 3 - 1) * 4
            annotation = axis.annotate(
                (display_texts[point_index] if display_texts and point_index < len(display_texts) else self._chart_value_text(number, series_name)),
                (x_value, number),
                xytext=(horizontal_offset, vertical_offset),
                textcoords="offset points",
                ha="center",
                va="bottom" if vertical_offset >= 0 else "top",
                fontsize=8,
                clip_on=False,
                bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.72},
            )
            self._remember_value_annotation(axis, annotation)

    def _annotate_vertical_bars(self, axis, bars, values, series_name="", display_texts=None):
        """Put a numeric label at the end of every vertical bar, including zero bars."""
        for point_index, (bar, value) in enumerate(zip(bars, values)):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(number):
                continue
            offset = 5 if number >= 0 else -5
            annotation = axis.annotate(
                (display_texts[point_index] if display_texts and point_index < len(display_texts) else self._chart_value_text(number, series_name)),
                (bar.get_x() + bar.get_width() / 2, number),
                xytext=(0, offset),
                textcoords="offset points",
                ha="center",
                va="bottom" if number >= 0 else "top",
                fontsize=8,
                clip_on=False,
                bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.72},
            )
            self._remember_value_annotation(axis, annotation)

    def _annotate_horizontal_bars(self, axis, bars, values, series_name=""):
        """Put a numeric label at the end of every horizontal bar."""
        for bar, value in zip(bars, values):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(number):
                continue
            offset = 5 if number >= 0 else -5
            annotation = axis.annotate(
                self._chart_value_text(number, series_name),
                (number, bar.get_y() + bar.get_height() / 2),
                xytext=(offset, 0),
                textcoords="offset points",
                ha="left" if number >= 0 else "right",
                va="center",
                fontsize=8,
                clip_on=False,
                bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none", "alpha": 0.72},
            )
            self._remember_value_annotation(axis, annotation)

    def _finalize_annotated_chart(self, canvas, axis):
        """Draw, detect overlapping value labels, and iteratively move them apart."""
        figure = canvas.figure
        figure.tight_layout()
        annotations = list(getattr(axis, "_restaurant_value_annotations", []))
        if not annotations:
            canvas.draw_idle()
            return

        label_count = len(annotations)
        font_size = 8
        if label_count > 80:
            font_size = 6.5
        elif label_count > 45:
            font_size = 7
        for annotation in annotations:
            annotation.set_fontsize(font_size)

        # A synchronous draw is needed so Matplotlib can report real pixel bounding boxes.
        canvas.draw()
        for iteration in range(10):
            renderer = canvas.get_renderer()
            accepted_boxes = []
            moved = False
            for index, annotation in enumerate(annotations):
                current_box = annotation.get_window_extent(renderer).expanded(1.04, 1.10)
                if any(current_box.overlaps(previous) for previous in accepted_boxes):
                    x_offset, y_offset = annotation.get_position()
                    direction = 1 if (index + iteration) % 2 == 0 else -1
                    vertical_step = 7 + min(iteration, 5) * 2
                    horizontal_step = ((index + iteration) % 3 - 1) * 5
                    annotation.set_position((x_offset + horizontal_step, y_offset + direction * vertical_step))
                    moved = True
                accepted_boxes.append(current_box)
            if not moved:
                break
            canvas.draw()
        canvas.draw_idle()

    def _plot_series(self, canvas, labels, series, title, y_label="", default_chart="line", point_labels=None):
        figure = canvas.figure
        figure.clear()
        axis = figure.add_subplot(111)
        if not labels or not series:
            axis.axis("off")
            axis.text(0.5, 0.5, "当前筛选条件没有数据", ha="center", va="center", fontsize=14, color="#667085")
            canvas.draw_idle()
            return

        chart = default_chart
        x_positions = list(range(len(labels)))
        series_items = list(series.items())
        if chart == "line":
            for index, (name, values) in enumerate(series_items):
                axis.plot(x_positions, list(map(float, values)), marker="o", linewidth=1.8, label=name)
                self._annotate_line_points(axis, x_positions, values, name, index, (point_labels or {}).get(name))
        else:
            width = 0.78 / max(len(series_items), 1)
            center_shift = (len(series_items) - 1) / 2
            for index, (name, values) in enumerate(series_items):
                positions = [x + (index - center_shift) * width for x in x_positions]
                bars = axis.bar(positions, list(map(float, values)), width=width, label=name)
                self._annotate_vertical_bars(axis, bars, values, name, (point_labels or {}).get(name))

        axis.set_xticks(x_positions)
        axis.set_xticklabels(labels, rotation=45 if len(labels) > 8 else 0, ha="right" if len(labels) > 8 else "center")
        axis.set_title(title, fontsize=13)
        if y_label:
            axis.set_ylabel(y_label)
        axis.grid(True, axis="y", alpha=0.25)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.2f}"))
        axis.margins(y=0.16)
        if len(series_items) > 1 or series_items[0][0]:
            axis.legend(loc="best", fontsize=9)
        self._finalize_annotated_chart(canvas, axis)

    def _plot_horizontal_compare(self, canvas, labels, series, title):
        figure = canvas.figure
        figure.clear()
        axis = figure.add_subplot(111)
        if not labels or not series:
            axis.axis("off")
            axis.text(0.5, 0.5, "当前筛选条件没有数据", ha="center", va="center", fontsize=14, color="#667085")
            canvas.draw_idle()
            return
        positions = list(range(len(labels)))
        items = list(series.items())
        height = 0.78 / max(len(items), 1)
        shift = (len(items) - 1) / 2
        for index, (name, values) in enumerate(items):
            y_positions = [y + (index - shift) * height for y in positions]
            bars = axis.barh(y_positions, list(map(float, values)), height=height, label=name)
            self._annotate_horizontal_bars(axis, bars, values, name)
        axis.set_yticks(positions)
        axis.set_yticklabels(labels)
        axis.set_title(title, fontsize=13)
        axis.grid(True, axis="x", alpha=0.25)
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.2f}"))
        if len(items) > 1:
            axis.legend(loc="best", fontsize=9)
        self._finalize_annotated_chart(canvas, axis)

    # ---------- 经营指标视图 ----------
    def _profit_margin_label(self, metric, value, rate):
        _ = metric
        return f"{decimal_number(value):,.2f} ({decimal_number(rate):.2f}%)"

    def _business_month_series(self, frame, metrics, months=None):
        detail_mode, average_mode = self._selected_modes()
        month_list = [int(month) for month in (months if months is not None else self._selected_months())]
        labels = [f"{month}月" for month in month_list]
        if not metrics:
            return labels, {"未选择经营指标": [0] * len(labels)}, {}
        series = {}
        point_labels = {}
        for metric in metrics:
            total_values = []
            average_values = []
            margin_values = []
            for month in month_list:
                sub = frame[frame["日期_dt"].dt.month == month] if not frame.empty else frame
                total_values.append(self._aggregate_business_metric(sub, metric, average=False))
                average_values.append(self._aggregate_business_metric(sub, metric, average=True))
                if metric == "毛利润":
                    margin_values.append(self._aggregate_business_metric(sub, "毛利率(%)", average=False))
                elif metric == "净利润":
                    margin_values.append(self._aggregate_business_metric(sub, "净利率(%)", average=False))
            if metric in self.RATE_METRICS:
                series_name = metric
                series[series_name] = total_values
            else:
                if detail_mode:
                    series_name = f"{metric}（合计）"
                    series[series_name] = total_values
                    if margin_values:
                        point_labels[series_name] = [self._profit_margin_label(metric, value, rate) for value, rate in zip(total_values, margin_values)]
                if average_mode:
                    series_name = f"{metric}（日均）"
                    series[series_name] = average_values
                    if margin_values:
                        point_labels[series_name] = [self._profit_margin_label(metric, value, rate) for value, rate in zip(average_values, margin_values)]
        return labels, series, point_labels

    def draw_business_trend(self, frame, metrics):
        detail_mode, average_mode = self._selected_modes()

        if not metrics:
            if average_mode and not detail_mode:
                labels = [f"{month}月" for month in self._selected_months()]
                title = f"{self._current_year()}年 所选月份日均趋势"
            elif not frame.empty:
                labels = frame["日期_dt"].dt.strftime("%m-%d").tolist()
                title = f"{self._current_year()}年 所选日期明细趋势"
            else:
                labels = [f"{month}月" for month in self._selected_months()]
                title = f"{self._current_year()}年 经营指标趋势"
            self._plot_series(
                self.canvas_trend,
                labels,
                {"未选择经营指标": [0] * len(labels)},
                title,
                default_chart="line",
            )
            return

        if frame.empty:
            self._empty_canvas(self.canvas_trend, "当前筛选条件没有经营数据")
            return
        if average_mode and not detail_mode:
            labels, series, point_labels = self._business_month_series(frame, metrics)
            self._plot_series(
                self.canvas_trend, labels, series,
                f"{self._current_year()}年 所选月份日均趋势",
                default_chart="line", point_labels=point_labels,
            )
            return

        labels = frame["日期_dt"].dt.strftime("%m-%d").tolist()
        series = {metric: frame[metric].astype(float).tolist() for metric in metrics if metric in frame.columns}
        figure = self.canvas_trend.figure
        figure.clear()
        axis = figure.add_subplot(111)
        x_positions = list(range(len(labels)))
        for index, (metric, values) in enumerate(series.items()):
            line, = axis.plot(x_positions, list(map(float, values)), marker="o", linewidth=1.6, label=metric)
            display_texts = None
            if metric == "毛利润":
                display_texts = [self._profit_margin_label(metric, value, rate) for value, rate in zip(values, frame["毛利率(%)"].astype(float).tolist())]
            elif metric == "净利润":
                display_texts = [self._profit_margin_label(metric, value, rate) for value, rate in zip(values, frame["净利率(%)"].astype(float).tolist())]
            self._annotate_line_points(axis, x_positions, values, metric, index, display_texts)
            if average_mode:
                average_value = self._aggregate_business_metric(frame, metric, average=True)
                axis.axhline(
                    float(average_value), linestyle="--", linewidth=1.1,
                    color=line.get_color(), alpha=0.75,
                    label=f"{metric} 平均",
                )
        axis.set_xticks(x_positions)
        axis.set_xticklabels(labels, rotation=45 if len(labels) > 10 else 0, ha="right" if len(labels) > 10 else "center")
        axis.set_title(f"{self._current_year()}年 所选日期明细趋势")
        axis.grid(True, axis="y", alpha=0.25)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.2f}"))
        axis.margins(y=0.16)
        axis.legend(loc="best", fontsize=8)
        self._finalize_annotated_chart(self.canvas_trend, axis)

    def draw_business_compare(self, frame, metrics):
        labels, series, point_labels = self._business_month_series(frame, metrics, months=range(1, 13))
        self._plot_series(
            self.canvas_compare, labels, series,
            f"{self._current_year()}年 月度对比",
            default_chart="bar", point_labels=point_labels,
        )

    def draw_business_weekday(self, frame, metrics):
        detail_mode, average_mode = self._selected_modes()
        selected_weekdays = self._selected_weekdays()
        labels = [self.WEEKDAY_NAMES[index] for index in selected_weekdays]
        if not metrics:
            self._plot_series(
                self.canvas_weekday, labels, {"未选择经营指标": [0] * len(labels)},
                "星期分布", default_chart="bar",
            )
            return
        series = {}
        point_labels = {}
        for metric in metrics:
            totals, averages, margins = [], [], []
            for weekday in selected_weekdays:
                sub = frame[frame["星期序号"] == weekday] if not frame.empty else frame
                totals.append(self._aggregate_business_metric(sub, metric, average=False))
                averages.append(self._aggregate_business_metric(sub, metric, average=True))
                if metric == "毛利润":
                    margins.append(self._aggregate_business_metric(sub, "毛利率(%)", average=False))
                elif metric == "净利润":
                    margins.append(self._aggregate_business_metric(sub, "净利率(%)", average=False))
            if metric in self.RATE_METRICS:
                series[metric] = totals
            else:
                if detail_mode:
                    name = f"{metric}（合计）"
                    series[name] = totals
                    if margins:
                        point_labels[name] = [self._profit_margin_label(metric, value, rate) for value, rate in zip(totals, margins)]
                if average_mode:
                    name = f"{metric}（日均）"
                    series[name] = averages
                    if margins:
                        point_labels[name] = [self._profit_margin_label(metric, value, rate) for value, rate in zip(averages, margins)]
        self._plot_series(
            self.canvas_weekday, labels, series, "星期分布",
            default_chart="bar", point_labels=point_labels,
        )

    def update_business_table(self, frame, metrics):
        detail_mode, average_mode = self._selected_modes()
        rows = []
        display_metrics = metrics or ["未选择经营指标"]
        if detail_mode:
            for _, item in frame.iterrows():
                row = {"类型": "明细", "日期/月份": str(item["日期"]), "星期": str(item["星期"])}
                for metric in display_metrics:
                    if not metrics:
                        row[metric] = 0
                    elif metric == "毛利润":
                        row[metric] = self._profit_margin_label(metric, decimal_number(item.get(metric, 0) or 0), decimal_number(item.get("毛利率(%)", 0) or 0))
                    elif metric == "净利润":
                        row[metric] = self._profit_margin_label(metric, decimal_number(item.get(metric, 0) or 0), decimal_number(item.get("净利率(%)", 0) or 0))
                    else:
                        row[metric] = decimal_number(item.get(metric, 0) or 0)
                rows.append(row)
        if average_mode:
            for month in self._selected_months():
                sub = frame[frame["日期_dt"].dt.month == month] if not frame.empty else frame
                row = {"类型": "月平均", "日期/月份": f"{self._current_year()}-{month:02d}", "星期": "-"}
                for metric in display_metrics:
                    if not metrics:
                        row[metric] = 0
                    else:
                        value = self._aggregate_business_metric(sub, metric, average=True)
                        if metric == "毛利润":
                            row[metric] = self._profit_margin_label(metric, value, self._aggregate_business_metric(sub, "毛利率(%)", average=False))
                        elif metric == "净利润":
                            row[metric] = self._profit_margin_label(metric, value, self._aggregate_business_metric(sub, "净利率(%)", average=False))
                        else:
                            row[metric] = value
                rows.append(row)
        if not rows and not metrics:
            rows.append({"类型": "未选择", "日期/月份": "-", "星期": "-", "未选择经营指标": 0})
        self._set_table(pd.DataFrame(rows), metric_columns=display_metrics)

    # ---------- 食材采购视图 ----------
    def _food_month_matrix(self, frame, metric, months=None):
        detail_mode, average_mode = self._selected_modes()
        month_list = [int(month) for month in (months if months is not None else self._selected_months())]
        labels = [f"{month}月" for month in month_list]
        series = {}
        if frame.empty:
            return labels, series
        for series_name in sorted(frame["系列"].unique()):
            group = frame[frame["系列"] == series_name]
            totals, averages = [], []
            for month in month_list:
                sub = group[group["日期_dt"].dt.month == month]
                totals.append(self._food_group_value(sub, metric, average=False))
                averages.append(self._food_group_value(sub, metric, average=True))
            if metric in ("单价随时间变化", "每月平均单价"):
                series[series_name] = totals
            else:
                if detail_mode:
                    series[f"{series_name}（合计）"] = totals
                if average_mode:
                    series[f"{series_name}（日均）"] = averages
        return labels, series

    def draw_food_trend(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        if frame.empty:
            message = "请先选择至少一种食材" if not self.selected_food_items else "当前筛选条件没有所选食材记录"
            self._empty_canvas(self.canvas_trend, message)
            return

        if metric != "单价随时间变化" or (average_mode and not detail_mode):
            labels, series = self._food_month_matrix(frame, metric)
            self._plot_series(
                self.canvas_trend, labels, series,
                f"{self._current_year()}年 {metric}",
                default_chart="line",
            )
            return

        labels = sorted(frame["日期"].unique())
        label_index = {label: index for index, label in enumerate(labels)}
        figure = self.canvas_trend.figure
        figure.clear()
        axis = figure.add_subplot(111)
        for index, series_name in enumerate(sorted(frame["系列"].unique())):
            group = frame[frame["系列"] == series_name]
            daily_values = {}
            for day, sub in group.groupby("日期"):
                daily_values[day] = self._food_group_value(sub, metric, average=False)
            values = [daily_values.get(day, float("nan")) for day in labels]
            x_positions = list(range(len(labels)))
            line, = axis.plot(x_positions, list(map(float, values)), marker="o", linewidth=1.6, label=series_name)
            self._annotate_line_points(axis, x_positions, values, series_name, index)
            if average_mode:
                overall = self._food_group_value(group, metric, average=False)
                axis.axhline(
                    overall, linestyle="--", linewidth=1.1,
                    color=line.get_color(), alpha=0.75,
                    label=f"{series_name} 平均",
                )
        axis.set_xticks(range(len(labels)))
        axis.set_xticklabels([pd.to_datetime(day).strftime("%m-%d") for day in labels], rotation=45 if len(labels) > 10 else 0, ha="right" if len(labels) > 10 else "center")
        axis.set_title("食材单价随时间变化")
        axis.set_ylabel("单价")
        axis.grid(True, axis="y", alpha=0.25)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.2f}"))
        axis.margins(y=0.16)
        axis.legend(loc="best", fontsize=8)
        self._finalize_annotated_chart(self.canvas_trend, axis)

    def draw_food_compare(self, frame, metric):
        labels, series = self._food_month_matrix(frame, metric, months=range(1, 13))
        title = "所选食材月度对比"
        if metric in ("单价随时间变化", "每月平均单价"):
            title = "所选食材月度单价对比"
        self._plot_series(
            self.canvas_compare, labels, series,
            title,
            default_chart="bar",
        )

    def draw_food_weekday(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        weekdays = self._selected_weekdays()
        labels = [self.WEEKDAY_NAMES[index] for index in weekdays]
        series = {}
        if not frame.empty:
            for series_name in sorted(frame["系列"].unique()):
                group = frame[frame["系列"] == series_name]
                total_values = []
                average_values = []
                for weekday in weekdays:
                    sub = group[group["星期序号"] == weekday]
                    total_values.append(self._food_group_value(sub, metric, average=False))
                    average_values.append(self._food_group_value(sub, metric, average=True))
                if metric in ("单价随时间变化", "每月平均单价"):
                    series[series_name] = total_values
                else:
                    if detail_mode:
                        series[f"{series_name}（合计）"] = total_values
                    if average_mode:
                        series[f"{series_name}（日均）"] = average_values
        self._plot_series(self.canvas_weekday, labels, series, "星期分布", default_chart="bar")

    def update_food_table(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        rows = []
        if detail_mode and metric == "单价随时间变化":
            for _, item in frame.iterrows():
                rows.append({
                    "类型": "采购明细",
                    "日期/月份": str(item["日期"]),
                    "食材": str(item["食材"]),
                    "数量": decimal_number(item["数量"]),
                    "单位": str(item["单位"]),
                    "总价": money_amount(item["总价"]),
                    "单价": decimal_number(item["单价"]),
                })
        if not frame.empty and (average_mode or metric != "单价随时间变化"):
            for (month, series_name), sub in frame.groupby(["月份", "系列"]):
                first = sub.iloc[0]
                quantity = decimal_number(sub["数量"].sum())
                total = decimal_number(sub["总价"].sum())
                active_days = max(int(sub["日期"].nunique()), 1)
                rows.append({
                    "类型": "月度汇总",
                    "日期/月份": str(month),
                    "食材": str(first["食材"]),
                    "数量": quantity,
                    "单位": str(first["单位"]),
                    "总价": total,
                    "单价": decimal_divide(total, quantity) if quantity else 0,
                    "采购日均总价": decimal_divide(total, active_days),
                    "采购日均数量": decimal_divide(quantity, active_days),
                })
        self._set_table(pd.DataFrame(rows))

    # ---------- 食材消耗视图 ----------
    def draw_consumption_trend(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        if frame.empty:
            message = (
                "请先选择至少一种消耗食材"
                if not self.selected_consumption_items
                else "当前筛选条件没有所选食材的消耗记录"
            )
            self._empty_canvas(self.canvas_trend, message)
            return

        if metric in ("每月消耗总量", "每月日均消耗量") or (average_mode and not detail_mode):
            labels, series = self._consumption_month_matrix(frame, metric)
            self._plot_series(
                self.canvas_trend,
                labels,
                series,
                f"{self._current_year()}年 {metric}",
                y_label="消耗量",
                default_chart="line",
            )
            return

        labels = sorted(frame["日期"].unique())
        x_positions = list(range(len(labels)))
        figure = self.canvas_trend.figure
        figure.clear()
        axis = figure.add_subplot(111)
        for series_index, series_name in enumerate(sorted(frame["系列"].unique())):
            group = frame[frame["系列"] == series_name]
            daily = {
                day: decimal_number(sub["数量"].sum())
                for day, sub in group.groupby("日期")
            }
            values = [daily.get(day, 0) for day in labels]
            if metric == "累计消耗量":
                running = 0
                cumulative = []
                for value in values:
                    running += decimal_number(value)
                    cumulative.append(running)
                values = cumulative
            line, = axis.plot(x_positions, list(map(float, values)), marker="o", linewidth=1.6, label=series_name)
            self._annotate_line_points(axis, x_positions, values, series_name, series_index)
            if average_mode and metric != "累计消耗量":
                overall = self._consumption_group_value(group, metric, average=True)
                axis.axhline(
                    overall,
                    linestyle="--",
                    linewidth=1.1,
                    color=line.get_color(),
                    alpha=0.75,
                    label=f"{series_name} 消耗日均",
                )
        axis.set_xticks(x_positions)
        axis.set_xticklabels(
            [pd.to_datetime(day).strftime("%m-%d") for day in labels],
            rotation=45 if len(labels) > 10 else 0,
            ha="right" if len(labels) > 10 else "center",
        )
        axis.set_title("食材累计消耗量" if metric == "累计消耗量" else "食材每日消耗量变化")
        axis.set_ylabel("消耗量")
        axis.grid(True, axis="y", alpha=0.25)
        axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f"{value:,.2f}"))
        axis.margins(y=0.16)
        axis.legend(loc="best", fontsize=8)
        self._finalize_annotated_chart(self.canvas_trend, axis)

    def draw_consumption_compare(self, frame, metric):
        labels, series = self._consumption_month_matrix(frame, metric, months=range(1, 13))
        self._plot_series(
            self.canvas_compare,
            labels,
            series,
            "所选食材1－12月消耗量对比",
            y_label="消耗量",
            default_chart="bar",
        )

    def draw_consumption_weekday(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        weekdays = self._selected_weekdays()
        labels = [self.WEEKDAY_NAMES[index] for index in weekdays]
        series = {}
        if not frame.empty:
            for series_name in sorted(frame["系列"].unique()):
                group = frame[frame["系列"] == series_name]
                totals, averages = [], []
                for weekday in weekdays:
                    sub = group[group["星期序号"] == weekday]
                    totals.append(self._consumption_group_value(sub, metric, average=False))
                    averages.append(self._consumption_group_value(sub, metric, average=True))
                if metric == "每月日均消耗量":
                    series[series_name] = averages
                else:
                    if detail_mode:
                        series[f"{series_name}（合计）"] = totals
                    if average_mode:
                        series[f"{series_name}（消耗日均）"] = averages
        self._plot_series(
            self.canvas_weekday,
            labels,
            series,
            "食材消耗星期分布",
            y_label="消耗量",
            default_chart="bar",
        )

    def update_consumption_table(self, frame, metric):
        detail_mode, average_mode = self._selected_modes()
        rows = []
        if detail_mode and not frame.empty:
            for (day, series_name), sub in frame.groupby(["日期", "系列"]):
                first = sub.iloc[0]
                rows.append({
                    "类型": "每日消耗",
                    "日期/月份": str(day),
                    "食材": str(first["食材"]),
                    "数量": decimal_number(sub["数量"].sum()),
                    "单位": str(first["单位"]),
                    "记录成本": decimal_number(sub["成本"].sum()),
                    "使用于": "、".join(sorted(set(sub["菜品"].astype(str)))),
                })
        if average_mode or metric in ("每月消耗总量", "每月日均消耗量"):
            if not frame.empty:
                for (month, series_name), sub in frame.groupby(["月份", "系列"]):
                    first = sub.iloc[0]
                    quantity = decimal_number(sub["数量"].sum())
                    active_days = max(int(sub["日期"].nunique()), 1)
                    rows.append({
                        "类型": "月度汇总",
                        "日期/月份": str(month),
                        "食材": str(first["食材"]),
                        "数量": quantity,
                        "单位": str(first["单位"]),
                        "记录成本": decimal_number(sub["成本"].sum()),
                        "消耗日均": decimal_divide(quantity, active_days),
                        "使用于": "、".join(sorted(set(sub["菜品"].astype(str)))),
                    })
        if not frame.empty:
            for series_name, sub in frame.groupby("系列"):
                first = sub.iloc[0]
                quantity = decimal_number(sub["数量"].sum())
                active_days = max(int(sub["日期"].nunique()), 1)
                rows.append({
                    "类型": "所选期间总量",
                    "日期/月份": f"{sub['日期'].min()} 至 {sub['日期'].max()}",
                    "食材": str(first["食材"]),
                    "数量": quantity,
                    "单位": str(first["单位"]),
                    "记录成本": decimal_number(sub["成本"].sum()),
                    "消耗日均": decimal_divide(quantity, active_days),
                    "使用于": "、".join(sorted(set(sub["菜品"].astype(str)))),
                })
        self._set_table(pd.DataFrame(rows))

    # ---------- 表格与刷新 ----------
    def _set_table(self, frame, metric_columns=None):
        self._last_table_export = frame.copy()
        self.table_stats.clear()
        if frame.empty:
            self.table_stats.setRowCount(0)
            self.table_stats.setColumnCount(1)
            self.table_stats.setHorizontalHeaderLabels(["提示"])
            return
        columns = list(frame.columns)
        self.table_stats.setColumnCount(len(columns))
        self.table_stats.setHorizontalHeaderLabels(columns)
        self.table_stats.setRowCount(len(frame))
        for row_index, (_, row) in enumerate(frame.iterrows()):
            for column_index, column in enumerate(columns):
                value = row.get(column, "")
                if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    if pd.isna(value):
                        text = ""
                    elif metric_columns and column in metric_columns:
                        text = self._format_value(column, value)
                    else:
                        text = f"{decimal_number(value):,.2f}"
                else:
                    text = str(value)
                self.table_stats.setItem(row_index, column_index, QTableWidgetItem(text))
        self.table_stats.resizeRowsToContents()

    def refresh(self):
        if not hasattr(self, "canvas_trend"):
            return
        self.refresh_inventory_balance()
        self.refresh_outbound_stats()
        months = self._selected_months()
        weekdays = self._selected_weekdays()
        if not months:
            message = "请至少选择一个月份"
            for canvas in (self.canvas_trend, self.canvas_compare, self.canvas_weekday):
                self._empty_canvas(canvas, message)
            self._set_table(pd.DataFrame())
            return
        if not weekdays:
            message = "请至少选择一个星期"
            for canvas in (self.canvas_trend, self.canvas_compare, self.canvas_weekday):
                self._empty_canvas(canvas, message)
            self._set_table(pd.DataFrame())
            return

        visible = {key: checkbox.isChecked() for key, checkbox in self.view_checks.items()}
        for widget, key in (
            (self.canvas_trend, "trend"),
            (self.canvas_compare, "compare"),
            (self.canvas_weekday, "weekday"),
            (self.table_stats, "table"),
        ):
            widget.setVisible(visible.get(key, False))

        self._refresh_food_button_options()
        self._refresh_consumption_button_options()
        self._update_month_forecast()

        if self._is_consumption_analysis_active():
            frame = self._consumption_frame()
            metric = self.combo_consumption_metric.currentText()
            if visible.get("trend"):
                self.draw_consumption_trend(frame, metric)
            if visible.get("compare"):
                self.draw_consumption_compare(frame, metric)
            if visible.get("weekday"):
                self.draw_consumption_weekday(frame, metric)
            if visible.get("table"):
                self.update_consumption_table(frame, metric)
        elif self._is_food_analysis_active():
            frame = self._food_frame()
            metric = self.combo_food_metric.currentText()
            if visible.get("trend"):
                self.draw_food_trend(frame, metric)
            if visible.get("compare"):
                self.draw_food_compare(frame, metric)
            if visible.get("weekday"):
                self.draw_food_weekday(frame, metric)
            if visible.get("table"):
                self.update_food_table(frame, metric)
        else:
            frame = self._business_frame()
            metrics = self._selected_metrics()
            if visible.get("trend"):
                self.draw_business_trend(frame, metrics)
            if visible.get("compare"):
                self.draw_business_compare(frame, metrics)
            if visible.get("weekday"):
                self.draw_business_weekday(frame, metrics)
            if visible.get("table"):
                self.update_business_table(frame, metrics)

    def _update_month_forecast(self):
        months = self._selected_months()
        if not months:
            self.month_forecast_panel.set_values(status="请至少选择一个月份")
            return
        today = QDate.currentDate()
        preferred = today.month() if self._current_year() == today.year() and today.month() in months else months[0]
        frame = load_daily().copy()
        prefix = f"{self._current_year()}-{preferred:02d}-"
        frame = frame[frame['日期'].astype(str).str.startswith(prefix)]
        # Annual workbooks may contain pre-created rows for future dates. They
        # are not elapsed business days and must not change a live forecast.
        if not frame.empty:
            frame_dates = pd.to_datetime(frame['日期'], errors='coerce').dt.date
            reference_day = datetime.now().date()
            if (self._current_year(), preferred) == (reference_day.year, reference_day.month):
                frame = frame[frame_dates < reference_day]
            else:
                frame = frame[frame_dates <= reference_day]
        frame = frame[frame.apply(day_has_meaningful_data, axis=1)] if not frame.empty else frame
        if frame.empty:
            self.month_forecast_panel.set_values(status=f"{preferred}月暂无经营数据")
            return
        all_daily, fixed = load_daily(), load_monthly_fixed()
        metrics_for_month = [calc_day_metrics(str(day), all_daily, fixed) for day in frame['日期'].astype(str)]
        metrics_for_month = [item for item in metrics_for_month if item]
        revenue = sum(decimal_number(item.get('收益', 0) or 0) for item in metrics_for_month)
        if not metrics_for_month:
            self.month_forecast_panel.set_values(status=f"{preferred}月暂无经营数据")
            return
        days_in_month = calendar.monthrange(self._current_year(), preferred)[1]
        elapsed_days = max(1, elapsed_month_days(self._current_year(), preferred))
        projected_revenue = decimal_divide(revenue, elapsed_days) * days_in_month
        previous_date = datetime(self._current_year(), preferred, 1) - timedelta(days=1)
        previous_summary = calc_month_summary(previous_date.year, previous_date.month, all_daily, fixed)
        previous_total_cost = previous_summary.get('本月总成本', 0) if previous_summary else sum(item.get('总成本', 0) for item in metrics_for_month)
        projected_net = projected_revenue - previous_total_cost
        gross_profit = sum(decimal_number(item.get('毛利', 0) or 0) for item in metrics_for_month)
        gross_margin = decimal_divide(gross_profit, revenue) if revenue > 0 else 0
        break_even_increase = calculate_break_even_daily_revenue_increase(
            projected_net, gross_margin, days_in_month
        )
        self.month_forecast_panel.set_values(
            projected_revenue, projected_net, break_even_increase
        )

    def refresh_inventory_balance(self):
        rows = calculate_inventory_balances()
        self.table_inventory_balance.clearSpans()
        self.table_inventory_balance.setRowCount(len(rows))
        columns = ['分类', '名称', '单位', '累计入库', '累计消耗', '正常使用', '损耗', '当前剩余', '库存状态', '最近入库']
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(columns):
                value = row.get(column, '')
                text = f'{decimal_number(value):,.3f}'.rstrip('0').rstrip('.') if isinstance(value, (int, float, Decimal)) else str(value)
                item = QTableWidgetItem(text)
                if column == '当前剩余':
                    item.setForeground(QColor('#C74444' if row['库存状态'] == '已用完' else '#A36108' if row['库存状态'] == '库存偏低' else '#1F7A4D'))
                self.table_inventory_balance.setItem(row_index, column_index, item)
        if not rows:
            self.table_inventory_balance.setRowCount(1)
            self.table_inventory_balance.setSpan(0, 0, 1, 10)
            self.table_inventory_balance.setItem(0, 0, QTableWidgetItem('暂无入库记录。'))
        self.table_inventory_balance.resizeRowsToContents()

    @staticmethod
    def _fill_outbound_table(table, columns, rows, empty_message):
        table.clear()
        table.clearSpans()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        batch_column = next((index for index, label in enumerate(columns) if '入库批次与单价' in label), None)
        if batch_column is not None:
            # A long FIFO history must wrap in the available width instead of
            # pushing its cost column out of the visible viewport.
            table.setWordWrap(True)
            table.horizontalHeader().setStretchLastSection(False)
            table.horizontalHeader().setSectionResizeMode(batch_column, QHeaderView.Stretch)
            table.horizontalHeader().setSectionResizeMode(batch_column + 1, QHeaderView.Fixed)
            table.setColumnWidth(batch_column + 1, 190)
        if not rows:
            table.setRowCount(1)
            table.setSpan(0, 0, 1, len(columns))
            table.setItem(0, 0, QTableWidgetItem(empty_message))
            return
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    text = f'{decimal_number(value):,.3f}'.rstrip('0').rstrip('.')
                else:
                    text = str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row_index, column_index, item)
        table.resizeRowsToContents()

    def refresh_outbound_stats(self):
        year = self._current_year()
        months = set(self._selected_months())
        weekdays = set(self._selected_weekdays())
        today = datetime.now().date()

        def allowed(date_text):
            parsed = pd.to_datetime(str(date_text), errors='coerce')
            return (
                not pd.isna(parsed) and parsed.year == year
                and parsed.month in months and int(parsed.weekday()) in weekdays
                and parsed.date() <= today
            )

        fifo_rows = [row for row in _inventory_fifo_snapshot()['movements'] if allowed(row.get('date'))]
        self._fill_outbound_table(self.table_fifo_outbound,
            ['日期', '类型', '名称', '数量', '入库批次与单价(元)', '出库成本(元)'],
            _inventory_fifo_table_rows(fifo_rows), '当前筛选条件没有出库记录。')
        usage_rows = [row for row in _inventory_consumption_rows() if allowed(row.get('date'))]
        usage_groups = {}
        for row in usage_rows:
            month = str(row['date'])[:7]
            key = (month, row['category'], row['name'], row['unit'])
            group = usage_groups.setdefault(key, {'quantity': 0, 'dishes': set()})
            group['quantity'] += decimal_number(row.get('quantity') or 0)
            group['dishes'].add(str(row.get('dish') or '未命名菜品'))
        usage_table = [
            [month, category, name, quantity, unit or '无单位', '、'.join(sorted(group['dishes']))]
            for (month, category, name, unit), group in sorted(usage_groups.items())
            for quantity in [group['quantity']]
        ]

        servings_groups = {}
        try:
            dishes = load_dishes()
        except Exception:
            dishes = pd.DataFrame()
        for _, record in dishes.iterrows():
            date = str(record.get('日期') or '')
            if not allowed(date):
                continue
            for dish in dish_rows_from_record(record):
                name = str(dish.get('菜品名称') or '未命名菜品').strip()
                section = str(dish.get('分区') or '菜品')
                key = (date, section, name)
                servings_groups[key] = servings_groups.get(key, 0) + safe_float(dish.get('份数', 0))
        servings_table = [
            [date, section, name, servings]
            for (date, section, name), servings in sorted(servings_groups.items())
        ]

        normal_groups = {}
        loss_groups = {}
        for row in load_inventory_adjustments():
            quantity = safe_float(row.get('quantity', row.get('数量', 0)))
            date = str(row.get('date') or row.get('日期') or '')
            if quantity <= 0 or not allowed(date):
                continue
            category = str(row.get('category') or row.get('分类') or '食材')
            name = str(row.get('name') or row.get('名称') or '').strip()
            unit = str(row.get('unit') or row.get('单位') or '').strip()
            key = (str(date)[:7], category, name, unit)
            target = normal_groups if _inventory_adjustment_kind(row) == 'normal' else loss_groups
            target[key] = target.get(key, 0) + quantity
        normal_table = [
            [month, category, name, quantity, unit or '无单位']
            for (month, category, name, unit), quantity in sorted(normal_groups.items())
        ]
        usage_by_item = {}
        for row in usage_rows:
            key = (str(row['date'])[:7], row['category'], row['name'], row['unit'])
            usage_by_item[key] = usage_by_item.get(key, 0) + decimal_number(row.get('quantity') or 0)
        loss_table = []
        for key, loss in sorted(loss_groups.items()):
            month, category, name, unit = key
            dish_used = usage_by_item.get(key, 0)
            normal_used = normal_groups.get(key, 0)
            total_normal = dish_used + normal_used
            rate = decimal_divide(loss, total_normal + loss) * 100 if total_normal + loss else 0
            loss_table.append([month, category, name, loss, unit or '无单位', total_normal, f'{rate:.2f}%'])

        self._fill_outbound_table(
            self.table_monthly_outbound,
            ['月份', '分类', '名称', '出库量', '单位', '使用于'], usage_table,
            '当前筛选条件没有菜品出库记录。',
        )
        self._fill_outbound_table(
            self.table_normal_adjustment,
            ['月份', '分类', '名称', '正常使用量', '单位'], normal_table,
            '当前筛选条件没有正常使用调整记录。',
        )
        self._fill_outbound_table(
            self.table_dish_servings,
            ['日期', '分区', '菜品', '份数'], servings_table,
            '当前筛选条件没有菜品份数记录。',
        )
        self._fill_outbound_table(
            self.table_inventory_loss,
            ['月份', '分类', '名称', '损耗量', '单位', '正常消耗量', '损耗率'], loss_table,
            '当前筛选条件没有盘点损耗记录。',
        )

    def export_data(self):
        if self._last_table_export.empty:
            QMessageBox.information(self, "没有数据", "当前筛选条件没有可以导出的数据。")
            return
        default_name = f"更多统计_{self._current_year()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出统计数据", default_name, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            export_frame = money_statistics_frame(self._last_table_export)
            numeric_columns = export_frame.select_dtypes(include=["number"]).columns
            if len(numeric_columns):
                export_frame.loc[:, numeric_columns] = export_frame.loc[:, numeric_columns].round(2)
            export_frame.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.2f")
            QMessageBox.information(self, "导出完成", f"统计数据已导出：\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"无法导出 CSV：\n{exc}")

def fmt_margin(val, rev):
    if rev > 0: return f"{val:.2f} 元 ({decimal_divide(val, rev) * 100:.1f}%)"
    if val == 0: return "0.00 元 (0.0%)"
    return f"{val:.2f} 元 (-%)"


# ===================== 仪表盘页面 =====================
class DashboardTab(QWidget):
    def __init__(self, read_excel_callback=None, create_user_excel_callback=None,
                 ensure_year_callback=None, move_internal_callback=None,
                 switch_internal_callback=None, merge_other_year_callback=None):
        super().__init__()
        self.read_excel_callback = read_excel_callback
        self.create_user_excel_callback = create_user_excel_callback
        self.ensure_year_callback = ensure_year_callback
        self.move_internal_callback = move_internal_callback
        self.switch_internal_callback = switch_internal_callback
        self.merge_other_year_callback = merge_other_year_callback
        self._is_syncing_dates = False
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        # The dashboard is intentionally denser than data-entry pages.  It is
        # primarily a glanceable overview, so it should fit a normal desktop
        # window instead of becoming a stack of oversized panels.
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(4)
        self._dashboard_main_layout = main_layout
        # The old single horizontal toolbar forced a wide dashboard even when
        # the window was narrow.  A compact grid keeps all actions reachable
        # without creating a horizontal scrollbar.
        date_layout = QGridLayout()
        date_layout.setHorizontalSpacing(4)
        date_layout.setVerticalSpacing(2)

        self.btn_prev = QPushButton("◀ 前一天")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.btn_next = QPushButton("后一天 ▶")
        self.btn_today = QPushButton("今天")

        self.month_combo = QComboBox()
        self.month_combo.addItems([f"{i:02d}" for i in range(1, 13)])
        self.year_combo = QComboBox()
        self.year_combo.addItems([str(y) for y in range(2020, 2050)])
        self.month_combo.setCurrentText(f"{QDate.currentDate().month():02d}")
        self.year_combo.setCurrentText(str(QDate.currentDate().year()))


        date_layout.addWidget(QLabel(" 选择日:"), 0, 0)
        date_layout.addWidget(self.btn_prev, 0, 1)
        date_layout.addWidget(self.date_edit, 0, 2)
        date_layout.addWidget(self.btn_next, 0, 3)
        date_layout.addWidget(self.btn_today, 0, 4)
        date_layout.addWidget(QLabel(" 选择月:"), 1, 0)
        date_layout.addWidget(self.month_combo, 1, 1)
        date_layout.addWidget(QLabel(" 选择年:"), 1, 2)
        date_layout.addWidget(self.year_combo, 1, 3)
        self.btn_create_user_excel = QPushButton("建立新的用户 Excel")
        self.btn_create_user_excel.setToolTip("归档当前内部 Excel 和用户 Excel，并建立一套全新的空白账套")
        self.btn_create_user_excel.setFixedHeight(30)
        self.btn_create_user_excel.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; background-color: #315f88; color: white; font-weight: bold;"
        )
        self.btn_move_internal = QPushButton("移动内部 Excel")
        self.btn_move_internal.setToolTip("把内部 Excel 移动到您选择的位置")
        self.btn_move_internal.setFixedHeight(30)
        self.btn_move_internal.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_merge_other_year = QPushButton("合并用户 Excel")
        self.btn_merge_other_year.setToolTip("合并任意年份的用户 Excel；重复日期可逐条选择保留哪个版本")
        self.btn_merge_other_year.setFixedHeight(30)
        self.btn_merge_other_year.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_switch_internal = QPushButton("重新选择数据来源")
        self.btn_switch_internal.setToolTip(
            "选择用户 Excel 或内部 Excel 作为新的数据来源"
        )
        self.btn_switch_internal.setFixedHeight(30)
        self.btn_switch_internal.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; background-color: #596d82; color: white; font-weight: bold;"
        )
        # Keep the uncommon file-management actions on one compact line.  The
        # previous two full-width button rows made the top of the dashboard
        # look taller than the actual business overview.
        dashboard_actions = QWidget()
        dashboard_actions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions_layout = QHBoxLayout(dashboard_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        for button in (
                self.btn_create_user_excel, self.btn_move_internal,
                self.btn_switch_internal, self.btn_merge_other_year):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        date_layout.addWidget(dashboard_actions, 2, 0, 1, 5)
        self.date_edit.setFixedWidth(150)
        self.month_combo.setFixedWidth(76); self.year_combo.setFixedWidth(90)
        date_layout.setColumnStretch(5, 1)
        main_layout.addLayout(date_layout)

        self.summary_layout = QGridLayout()
        self.summary_layout.setHorizontalSpacing(8)
        self.summary_layout.setVerticalSpacing(8)
        day_group, week_group, month_group, year_group = QGroupBox(" 当日快照"), QGroupBox(" 本周概览"), QGroupBox(
            " 本月概览"), QGroupBox(" 本年概览")
        day_layout, week_layout, month_layout, year_layout = QFormLayout(), QFormLayout(), QFormLayout(), QFormLayout()
        for form_layout in (day_layout, week_layout, month_layout, year_layout):
            form_layout.setContentsMargins(8, 8, 8, 8)
            form_layout.setHorizontalSpacing(6)
            form_layout.setVerticalSpacing(4)
            form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        def add_blank_row(form_layout):
            spacer = QLabel("")
            # Preserve the visual grouping of related metrics without making
            # every dashboard card needlessly tall.
            spacer.setFixedHeight(4)
            form_layout.addRow(spacer)

        # Day
        self.lbl_day_revenue = QLabel("-")
        self.lbl_day_a_revenue = QLabel("-")
        self.lbl_day_b_revenue = QLabel("-")
        self.lbl_day_fixed = QLabel("-")
        self.lbl_day_var_cost = QLabel("-")
        self.lbl_day_cost = QLabel("-")
        self.lbl_day_avg_cost = QLabel("-")
        self.lbl_day_dish_cost = QLabel("-")
        self.lbl_day_gross = QLabel("-")
        self.lbl_day_net = QLabel("-")
        day_layout.addRow("总收入 (Revenue):", self.lbl_day_revenue)
        day_layout.addRow("A店收入:", self.lbl_day_a_revenue)
        day_layout.addRow("B店收入:", self.lbl_day_b_revenue)
        add_blank_row(day_layout)
        day_layout.addRow("固定成本:", self.lbl_day_fixed)
        day_layout.addRow(" (总成本 - 固定成本):", self.lbl_day_var_cost)
        day_layout.addRow("总成本:", self.lbl_day_cost)
        day_layout.addRow("日均总成本:", self.lbl_day_avg_cost)
        day_layout.addRow("“当日做出的菜品”所用成本:", self.lbl_day_dish_cost)
        add_blank_row(day_layout)
        gross_hint_label = QLabel(
            "毛利计算：优先用“当日做出的菜品成本”；没有菜品成本时，"
            "用（总成本 - 固定成本）。"
        )
        gross_hint_label.setWordWrap(True)
        gross_hint_label.setToolTip(
            "如有“当日做出的菜品成本”数据，则用该成本计算毛利润；"
            "如当日无该数据，则用（总成本 - 固定成本）计算毛利润。"
        )
        day_layout.addRow("净利 (净利率):", self.lbl_day_net)
        day_layout.addRow(gross_hint_label)
        day_layout.addRow("毛利 (毛利率):", self.lbl_day_gross)
        day_group.setLayout(day_layout)

        # Week
        self.lbl_week_revenue = QLabel("-")
        self.lbl_week_a_revenue = QLabel("-")
        self.lbl_week_b_revenue = QLabel("-")
        self.lbl_week_fixed = QLabel("-")
        self.lbl_week_var_cost = QLabel("-")
        self.lbl_week_cost = QLabel("-")
        self.lbl_week_gross = QLabel("-")
        self.lbl_week_net = QLabel("-")
        self.lbl_week_avg_rev = QLabel("-")
        self.lbl_week_avg_var = QLabel("-")
        self.lbl_week_avg_cost = QLabel("-")
        self.lbl_week_avg_gross = QLabel("-")
        self.lbl_week_avg_net = QLabel("-")
        week_layout.addRow("总收入 (Revenue):", self.lbl_week_revenue)
        week_layout.addRow("A店收入:", self.lbl_week_a_revenue)
        week_layout.addRow("B店收入:", self.lbl_week_b_revenue)
        add_blank_row(week_layout)
        week_layout.addRow("总固定成本:", self.lbl_week_fixed)
        week_layout.addRow(" (总成本 - 固定成本):", self.lbl_week_var_cost)
        week_layout.addRow("总成本:", self.lbl_week_cost)
        add_blank_row(week_layout)
        week_layout.addRow("毛利 (毛利率):", self.lbl_week_gross)
        week_layout.addRow("净利 (净利率):", self.lbl_week_net)
        add_blank_row(week_layout)
        week_layout.addRow("日均收入 (Revenue):", self.lbl_week_avg_rev)
        week_layout.addRow("日均 (总成本 - 固定成本):", self.lbl_week_avg_var)
        week_layout.addRow("日均总成本:", self.lbl_week_avg_cost)
        week_layout.addRow("日均毛利 (毛利率):", self.lbl_week_avg_gross)
        week_layout.addRow("日均净利 (净利率):", self.lbl_week_avg_net)
        week_group.setLayout(week_layout)

        # Month
        self.lbl_month_revenue = QLabel("-")
        self.lbl_month_a_revenue = QLabel("-")
        self.lbl_month_b_revenue = QLabel("-")
        self.lbl_month_fixed = QLabel("-")
        self.lbl_month_var_cost = QLabel("-")
        self.lbl_month_cost = QLabel("-")
        self.lbl_month_gross = QLabel("-")
        self.lbl_month_net = QLabel("-")
        self.lbl_month_avg_rev = QLabel("-")
        self.lbl_month_avg_var = QLabel("-")
        self.lbl_month_avg_cost = QLabel("-")
        self.lbl_month_avg_gross = QLabel("-")
        self.lbl_month_avg_net = QLabel("-")
        month_layout.addRow("总收入 (Revenue):", self.lbl_month_revenue)
        month_layout.addRow("A店收入:", self.lbl_month_a_revenue)
        month_layout.addRow("B店收入:", self.lbl_month_b_revenue)
        add_blank_row(month_layout)
        month_layout.addRow("总固定成本:", self.lbl_month_fixed)
        month_layout.addRow(" (总成本 - 固定成本):", self.lbl_month_var_cost)
        month_layout.addRow("总成本:", self.lbl_month_cost)
        add_blank_row(month_layout)
        month_layout.addRow("毛利 (毛利率):", self.lbl_month_gross)
        month_layout.addRow("净利 (净利率):", self.lbl_month_net)
        add_blank_row(month_layout)
        month_layout.addRow("日均收入 (Revenue):", self.lbl_month_avg_rev)
        month_layout.addRow("日均 (总成本 - 固定成本):", self.lbl_month_avg_var)
        month_layout.addRow("日均总成本:", self.lbl_month_avg_cost)
        month_layout.addRow("日均毛利 (毛利率):", self.lbl_month_avg_gross)
        month_layout.addRow("日均净利 (净利率):", self.lbl_month_avg_net)
        add_blank_row(month_layout)
        self.month_forecast_panel = ForecastSummaryPanel(month_group)
        self.lbl_month_forecast_revenue = self.month_forecast_panel.revenue_value
        self.lbl_month_forecast_net = self.month_forecast_panel.net_value
        self.lbl_month_forecast_break_even = self.month_forecast_panel.break_even_value
        month_layout.addRow(self.month_forecast_panel)
        month_group.setLayout(month_layout)

        # Year
        self.lbl_year_revenue = QLabel("-")
        self.lbl_year_a_revenue = QLabel("-")
        self.lbl_year_b_revenue = QLabel("-")
        self.lbl_year_fixed = QLabel("-")
        self.lbl_year_var_cost = QLabel("-")
        self.lbl_year_cost = QLabel("-")
        self.lbl_year_expense = QLabel("-")
        self.lbl_year_gross = QLabel("-")
        self.lbl_year_net = QLabel("-")
        self.lbl_year_avg_rev = QLabel("-")
        self.lbl_year_avg_var = QLabel("-")
        self.lbl_year_avg_cost = QLabel("-")
        self.lbl_year_avg_gross = QLabel("-")
        self.lbl_year_avg_net = QLabel("-")
        self.lbl_year_mo_gross = QLabel("-")
        self.lbl_year_mo_net = QLabel("-")
        year_layout.addRow("总收入 (Revenue):", self.lbl_year_revenue)
        year_layout.addRow("A店收入:", self.lbl_year_a_revenue)
        year_layout.addRow("B店收入:", self.lbl_year_b_revenue)
        add_blank_row(year_layout)
        year_layout.addRow("总固定成本:", self.lbl_year_fixed)
        year_layout.addRow(" (总成本 - 固定成本):", self.lbl_year_var_cost)
        year_layout.addRow("总成本:", self.lbl_year_cost)
        year_layout.addRow("总支出:", self.lbl_year_expense)
        add_blank_row(year_layout)
        year_layout.addRow("毛利 (毛利率):", self.lbl_year_gross)
        year_layout.addRow("净利 (净利率):", self.lbl_year_net)
        add_blank_row(year_layout)
        year_layout.addRow("日均收入 (Revenue):", self.lbl_year_avg_rev)
        year_layout.addRow("日均 (总成本 - 固定成本):", self.lbl_year_avg_var)
        year_layout.addRow("日均总成本:", self.lbl_year_avg_cost)
        year_layout.addRow("日均毛利 (毛利率):", self.lbl_year_avg_gross)
        year_layout.addRow("日均净利 (净利率):", self.lbl_year_avg_net)
        year_layout.addRow("月均毛利 (毛利率):", self.lbl_year_mo_gross)
        year_layout.addRow("月均净利 (净利率):", self.lbl_year_mo_net)
        year_group.setLayout(year_layout)

        for _label in [self.lbl_day_revenue, self.lbl_day_a_revenue, self.lbl_day_b_revenue, self.lbl_day_fixed, self.lbl_day_var_cost, self.lbl_day_cost, self.lbl_day_avg_cost, self.lbl_day_dish_cost, self.lbl_day_gross, self.lbl_day_net, self.lbl_week_revenue, self.lbl_week_a_revenue, self.lbl_week_b_revenue, self.lbl_week_fixed, self.lbl_week_var_cost, self.lbl_week_cost, self.lbl_week_gross, self.lbl_week_net, self.lbl_week_avg_rev, self.lbl_week_avg_var, self.lbl_week_avg_cost, self.lbl_week_avg_gross, self.lbl_week_avg_net, self.lbl_month_revenue, self.lbl_month_a_revenue, self.lbl_month_b_revenue, self.lbl_month_fixed, self.lbl_month_var_cost, self.lbl_month_cost, self.lbl_month_gross, self.lbl_month_net, self.lbl_month_avg_rev, self.lbl_month_avg_var, self.lbl_month_avg_cost, self.lbl_month_avg_gross, self.lbl_month_avg_net, self.lbl_month_forecast_revenue, self.lbl_month_forecast_net, self.lbl_month_forecast_break_even, self.lbl_year_revenue, self.lbl_year_a_revenue, self.lbl_year_b_revenue, self.lbl_year_fixed, self.lbl_year_var_cost, self.lbl_year_cost, self.lbl_year_expense, self.lbl_year_gross, self.lbl_year_net, self.lbl_year_avg_rev, self.lbl_year_avg_var, self.lbl_year_avg_cost, self.lbl_year_avg_gross, self.lbl_year_avg_net, self.lbl_year_mo_gross, self.lbl_year_mo_net]:
            _label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.summary_groups = [day_group, week_group, month_group, year_group]
        for g in self.summary_groups:
            # Use the same inherited dashboard font as Sep07V1.  The cards can
            # grow vertically inside the scroll area; only horizontal scrolling
            # remains disabled.
            g.setMinimumSize(0, 0)
            g.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        main_layout.addLayout(self.summary_layout)

        # ============ Charts Section ============
        self.chart_layout = QGridLayout()
        self.chart_layout.setHorizontalSpacing(8)
        self.chart_layout.setVerticalSpacing(8)
        self.pie_canvas_day, self.pie_canvas_month, self.bar_canvas = FigureCanvas(Figure()), FigureCanvas(
            Figure()), FigureCanvas(Figure())

        # Trend Chart with Dropdown Component
        self.trend_widget = QWidget()
        trend_vbox = QVBoxLayout(self.trend_widget)
        trend_vbox.setContentsMargins(0, 0, 0, 0)

        trend_header = QHBoxLayout()
        self.trend_combo = QComboBox()
        self.trend_combo.addItems(["净利润 (净利率)", "毛利润 (毛利率)", "食材成本 (包括佐料)", "收入 (Revenue)"])
        self.trend_combo.setStyleSheet("padding: 3px; border: 1px solid #ccc; border-radius: 4px;")
        trend_header.addWidget(QLabel(" 切换指标:"))
        trend_header.addWidget(self.trend_combo)
        trend_header.addStretch()

        self.trend_canvas = FigureCanvas(Figure())
        trend_vbox.addLayout(trend_header)
        trend_vbox.addWidget(self.trend_canvas)

        # Charts reflow between two columns and one column.  Bound their
        # height as well as their width: matplotlib otherwise asks for about
        # 500 px per chart, which makes the dashboard several screens tall.
        for chart_widget in (
                self.pie_canvas_day, self.trend_widget,
                self.pie_canvas_month, self.bar_canvas):
            chart_widget.setMinimumSize(0, 210)
            chart_widget.setMaximumHeight(250)
            chart_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.chart_widgets = [
            self.pie_canvas_day, self.trend_widget,
            self.pie_canvas_month, self.bar_canvas,
        ]
        main_layout.addLayout(self.chart_layout)

        # Keep vertical scrolling only when a short window truly needs it,
        # while always using the available width instead of exposing a
        # horizontal scrollbar.
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dashboard_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.dashboard_scroll.setStyleSheet("QScrollArea { border: none; }")
        self.dashboard_content = QWidget()
        self.dashboard_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.dashboard_content.setMinimumWidth(0)
        self.dashboard_content.setLayout(main_layout)
        self.dashboard_scroll.setWidget(self.dashboard_content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.dashboard_scroll)
        
        # 让图表不拦截鼠标滚轮，使整个仪表盘可以滚动
        self._enable_scroll_on_canvases()

        self.btn_prev.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(-1)))
        self.btn_next.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(1)))
        self.btn_today.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        self.date_edit.dateChanged.connect(self.sync_dates_from_day)
        self.month_combo.currentTextChanged.connect(self.sync_dates_from_combo)
        self.year_combo.currentTextChanged.connect(self.sync_dates_from_combo)
        self.trend_combo.currentTextChanged.connect(self.update_trend_chart_only)
        if self.create_user_excel_callback:
            self.btn_create_user_excel.clicked.connect(self.create_user_excel_callback)
        else:
            self.btn_create_user_excel.setEnabled(False)
        if self.move_internal_callback:
            self.btn_move_internal.clicked.connect(self.move_internal_callback)
        else:
            self.btn_move_internal.setEnabled(False)
        if self.switch_internal_callback:
            self.btn_switch_internal.clicked.connect(self.switch_internal_callback)
        else:
            self.btn_switch_internal.setEnabled(False)
        if self.merge_other_year_callback:
            self.btn_merge_other_year.clicked.connect(self.merge_other_year_callback)
        else:
            self.btn_merge_other_year.setEnabled(False)
        self._reflow_dashboard_layout()
        QTimer.singleShot(0, self._reflow_dashboard_layout)
        self.refresh_all()

    def sync_dates_from_day(self):
        if self._is_syncing_dates: return
        self._is_syncing_dates = True
        self.month_combo.setCurrentText(f"{self.date_edit.date().month():02d}")
        self.year_combo.setCurrentText(str(self.date_edit.date().year()))
        self._is_syncing_dates = False
        self._ensure_user_excel_year()
        self.refresh_all()

    def sync_dates_from_combo(self):
        if self._is_syncing_dates: return
        self._is_syncing_dates = True
        try:
            self.date_edit.setDate(QDate(int(self.year_combo.currentText()), int(self.month_combo.currentText()), 1))
        except:
            pass
        self._is_syncing_dates = False
        self._ensure_user_excel_year()
        self.refresh_all()

    def _ensure_user_excel_year(self):
        if not self.ensure_year_callback:
            return True
        try:
            return bool(self.ensure_year_callback(self.date_edit.date().year(), self))
        except ExcelAccessError as exc:
            QMessageBox.warning(self, "无法切换年度用户 Excel", str(exc))
            return False

    @staticmethod
    def _arrange_responsive_grid(layout, widgets, columns):
        """Move widgets into a compact grid without changing their parents."""
        columns = max(1, int(columns))
        for widget in widgets:
            layout.removeWidget(widget)
        for index in range(max(4, layout.columnCount())):
            layout.setColumnStretch(index, 0)
            layout.setColumnMinimumWidth(index, 0)
        for index in range(max(4, layout.rowCount())):
            layout.setRowStretch(index, 0)
            layout.setRowMinimumHeight(index, 0)
        for index, widget in enumerate(widgets):
            row, column = divmod(index, columns)
            layout.addWidget(widget, row, column)
            layout.setColumnStretch(column, 1)
            # The cards/charts already have a useful preferred size.  Giving
            # grid rows stretch makes them fill the scroll area's spare space
            # and is the reason the old dashboard looked excessively tall.
            layout.setRowStretch(row, 0)
        layout.setAlignment(Qt.AlignTop)
        layout.invalidate()

    def _reflow_dashboard_layout(self):
        """Fit dashboard cards and charts to the current viewport width."""
        if not hasattr(self, 'summary_layout') or not hasattr(self, 'chart_layout'):
            return
        viewport_width = self.width()
        if hasattr(self, 'dashboard_scroll'):
            viewport_width = self.dashboard_scroll.viewport().width() or viewport_width

        # Normal desktop windows should show the four summary cards in one
        # compact row.  Two rows are reserved for genuinely narrow windows;
        # this avoids turning a standard laptop dashboard into a long page.
        summary_columns = 4 if viewport_width >= 1180 else 2 if viewport_width >= 620 else 1
        chart_columns = 2 if viewport_width >= 720 else 1
        self._arrange_responsive_grid(self.summary_layout, self.summary_groups, summary_columns)
        self._arrange_responsive_grid(self.chart_layout, self.chart_widgets, chart_columns)
        if hasattr(self, 'dashboard_content'):
            self.dashboard_content.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_dashboard_layout()


    def _enable_scroll_on_canvases(self):
        """让 matplotlib canvas 不拦截鼠标滚轮事件，传递给 QScrollArea"""
        canvases = [
            self.pie_canvas_day, self.pie_canvas_month, 
            self.bar_canvas, self.trend_canvas
        ]
        for canvas in canvases:
            if hasattr(canvas, 'wheelEvent'):
                orig_wheel = canvas.wheelEvent
                def make_passthrough(orig):
                    def passthrough(event):
                        # 忽略 canvas 的滚轮事件，让父级 QScrollArea 处理
                        if hasattr(event, 'ignore'):
                            event.ignore()
                    return passthrough
                canvas.wheelEvent = make_passthrough(orig_wheel)

    def refresh_all(self):
        df_daily, df_fixed = load_daily(), load_monthly_fixed()
        day_str, year, month = self.date_edit.date().toString(
            "yyyy-MM-dd"), self.date_edit.date().year(), self.date_edit.date().month()

        def store_sum(frame, column):
            if frame is None or frame.empty or column not in frame.columns:
                return 0
            return sum(safe_float(v) for v in frame[column].tolist())

        def sd_value(values):
            values = [decimal_number(v) for v in values if v is not None]
            if not values:
                return 0
            mean = decimal_divide(sum(values), len(values))
            return (decimal_divide(sum(((value - mean) ** 2 for value in values)), len(values))) ** Decimal("0.5")

        def money_sd(value, values=(), suffix=" 元", include_sd=False):
            text = f"{decimal_number(value):,.2f}{suffix}"
            return f"{text} (SD: {sd_value(values):,.2f}{suffix})" if include_sd else text

        def margin_sd(value, revenue, values):
            return f"{decimal_number(value):,.2f} 元 ({(decimal_divide(decimal_number(value), decimal_number(revenue)) * 100) if revenue else 0:.1f}%)"

        # Snapshot SD is defined over the selected month's daily income series.
        # Exclude future dates in the current month and rows without business data;
        # otherwise a stale/future row can make the displayed SD misleading.
        month_rows_for_sd = df_daily[
            df_daily['日期'].astype(str).str.startswith(f"{year}-{month:02d}")
        ].copy()
        today = datetime.now().date()
        if not month_rows_for_sd.empty:
            parsed_dates = pd.to_datetime(month_rows_for_sd['日期'], errors='coerce').dt.date
            month_rows_for_sd = month_rows_for_sd[parsed_dates < today]
        active_daily_rows = [row for _, row in month_rows_for_sd.iterrows() if day_has_meaningful_data(row)]
        month_metric_rows = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for row in active_daily_rows]
        month_metric_rows = [item for item in month_metric_rows if item]

        # Day logic
        m = calc_day_metrics(day_str, df_daily, df_fixed)
        if m:
            day_row = df_daily[df_daily['日期'].astype(str) == day_str]
            self.lbl_day_revenue.setText(money_sd(m['收益'], [x['收益'] for x in month_metric_rows], include_sd=True))
            self.lbl_day_a_revenue.setText(money_sd(store_sum(day_row, 'A店收入'), [money_amount(row.get('A店收入', 0)) for row in active_daily_rows], include_sd=True))
            self.lbl_day_b_revenue.setText(money_sd(store_sum(day_row, 'B店收入'), [money_amount(row.get('B店收入', 0)) for row in active_daily_rows], include_sd=True))
            self.lbl_day_fixed.setText(money_sd(m['固定分摊'], [x['固定分摊'] for x in month_metric_rows]))
            self.lbl_day_var_cost.setText(money_sd(m['变动成本'], [x['变动成本'] for x in month_metric_rows]))
            self.lbl_day_cost.setText(money_sd(m['总成本'], [x['总成本'] for x in month_metric_rows]))
            self.lbl_day_avg_cost.setText(money_sd(m['总成本'], [x['总成本'] for x in month_metric_rows]) + "/天")
            dish_cost, has_dish_cost = dish_total_cost_for_date(day_str)
            self.lbl_day_dish_cost.setText(
                money_sd(dish_cost if has_dish_cost else 0,
                         [money_amount(x.get('食材成本', 0)) for x in month_metric_rows])
            )
            gross = m['收益'] - dish_cost if has_dish_cost else m['毛利']
            self.lbl_day_gross.setText(margin_sd(gross, m['收益'], [x['毛利'] for x in month_metric_rows]))
            self.lbl_day_net.setText(margin_sd(m['净利润'], m['收益'], [x['净利润'] for x in month_metric_rows]))
        else:
            for lbl in [self.lbl_day_revenue, self.lbl_day_a_revenue, self.lbl_day_b_revenue, self.lbl_day_fixed, self.lbl_day_var_cost,
                        self.lbl_day_cost, self.lbl_day_avg_cost, self.lbl_day_dish_cost, self.lbl_day_gross, self.lbl_day_net]:
                lbl.setText("-")

        # Week logic
        w = calc_week_summary(day_str, df_daily, df_fixed)
        if w and w['活跃天数'] > 0:
            target_date = datetime.strptime(day_str, "%Y-%m-%d").date()
            d = w.get('日均天数', elapsed_week_days(target_date))
            week_start = target_date - timedelta(days=target_date.weekday())
            week_end = week_start + timedelta(days=6)
            week_dates = pd.to_datetime(df_daily['日期'], errors='coerce').dt.date if not df_daily.empty else pd.Series(dtype=object)
            week_rows = df_daily[
                (week_dates >= week_start) & (week_dates <= week_end) & (week_dates <= today)
            ] if not df_daily.empty else df_daily
            week_rows = week_rows[week_rows.apply(day_has_meaningful_data, axis=1)] if not week_rows.empty else week_rows
            week_metric_rows = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in week_rows.iterrows()]
            week_metric_rows = [item for item in week_metric_rows if item]
            average_week_rows = week_rows[
                pd.to_datetime(week_rows['日期'], errors='coerce').dt.date < today
            ] if not week_rows.empty and week_start <= today <= week_end else week_rows
            average_week_metrics = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in average_week_rows.iterrows()]
            average_week_metrics = [item for item in average_week_metrics if item]
            average_week_revenue = sum(item['收益'] for item in average_week_metrics)
            average_week_variable = sum(item['变动成本'] for item in average_week_metrics)
            average_week_total = sum(item['总成本'] for item in average_week_metrics)
            average_week_gross = sum(item['毛利'] for item in average_week_metrics)
            average_week_net = sum(item['净利润'] for item in average_week_metrics)
            self.lbl_week_revenue.setText(money_sd(w['本周收益'], [x['收益'] for x in week_metric_rows]))
            self.lbl_week_a_revenue.setText(money_sd(store_sum(week_rows, 'A店收入'), [money_amount(row.get('A店收入', 0)) for _, row in week_rows.iterrows()]))
            self.lbl_week_b_revenue.setText(money_sd(store_sum(week_rows, 'B店收入'), [money_amount(row.get('B店收入', 0)) for _, row in week_rows.iterrows()]))
            self.lbl_week_fixed.setText(money_sd(w['本周固定成本'], [x['固定分摊'] for x in week_metric_rows]))
            self.lbl_week_var_cost.setText(money_sd(w['本周变动成本'], [x['变动成本'] for x in week_metric_rows]))
            self.lbl_week_cost.setText(money_sd(w['本周总成本'], [x['总成本'] for x in week_metric_rows]))
            self.lbl_week_gross.setText(margin_sd(w['本周毛利'], w['本周收益'], [x['毛利'] for x in week_metric_rows]))
            self.lbl_week_net.setText(margin_sd(w['本周净利'], w['本周收益'], [x['净利润'] for x in week_metric_rows]))
            self.lbl_week_avg_rev.setText(money_sd(decimal_divide(average_week_revenue, d)) + "/天")
            self.lbl_week_avg_var.setText(money_sd(decimal_divide(average_week_variable, d)) + "/天")
            self.lbl_week_avg_cost.setText(money_sd(decimal_divide(average_week_total, d)) + "/天")
            self.lbl_week_avg_gross.setText(margin_sd(decimal_divide(average_week_gross, d), decimal_divide(average_week_revenue, d), []) + "/天")
            self.lbl_week_avg_net.setText(margin_sd(decimal_divide(average_week_net, d), decimal_divide(average_week_revenue, d), []) + "/天")
        else:
            for lbl in [self.lbl_week_revenue, self.lbl_week_a_revenue, self.lbl_week_b_revenue, self.lbl_week_fixed, self.lbl_week_var_cost, self.lbl_week_cost,
                        self.lbl_week_gross, self.lbl_week_net, self.lbl_week_avg_rev, self.lbl_week_avg_var, self.lbl_week_avg_cost,
                        self.lbl_week_avg_gross, self.lbl_week_avg_net]:
                lbl.setText("-")

        # Month logic
        m_m = calc_month_summary(year, month, df_daily, df_fixed)
        if m_m and m_m['活跃天数'] > 0:
            d = m_m.get('日均天数', elapsed_month_days(year, month))
            month_rows = df_daily[df_daily['日期'].astype(str).str.startswith(f"{year}-{month:02d}")]
            if not month_rows.empty:
                month_dates = pd.to_datetime(month_rows['日期'], errors='coerce').dt.date
                month_rows = month_rows[month_dates <= today]
            month_rows = month_rows[month_rows.apply(day_has_meaningful_data, axis=1)] if not month_rows.empty else month_rows
            month_metric_rows = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in month_rows.iterrows()]
            month_metric_rows = [item for item in month_metric_rows if item]
            average_month_rows = month_rows[
                pd.to_datetime(month_rows['日期'], errors='coerce').dt.date < today
            ] if not month_rows.empty and (year, month) == (today.year, today.month) else month_rows
            average_month_metrics = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in average_month_rows.iterrows()]
            average_month_metrics = [item for item in average_month_metrics if item]
            average_month_revenue = sum(item['收益'] for item in average_month_metrics)
            average_month_variable = sum(item['变动成本'] for item in average_month_metrics)
            average_month_total = sum(item['总成本'] for item in average_month_metrics)
            average_month_gross = sum(item['毛利'] for item in average_month_metrics)
            average_month_net = sum(item['净利润'] for item in average_month_metrics)
            self.lbl_month_revenue.setText(money_sd(m_m['本月收益'], [x['收益'] for x in month_metric_rows]))
            self.lbl_month_a_revenue.setText(money_sd(store_sum(month_rows, 'A店收入'), [money_amount(row.get('A店收入', 0)) for _, row in month_rows.iterrows()]))
            self.lbl_month_b_revenue.setText(money_sd(store_sum(month_rows, 'B店收入'), [money_amount(row.get('B店收入', 0)) for _, row in month_rows.iterrows()]))
            self.lbl_month_fixed.setText(money_sd(m_m['本月固定成本'], [x['固定分摊'] for x in month_metric_rows]))
            self.lbl_month_var_cost.setText(money_sd(m_m['本月变动成本'], [x['变动成本'] for x in month_metric_rows]))
            self.lbl_month_cost.setText(money_sd(m_m['本月总成本'], [x['总成本'] for x in month_metric_rows]))
            self.lbl_month_gross.setText(margin_sd(m_m['本月毛利'], m_m['本月收益'], [x['毛利'] for x in month_metric_rows]))
            self.lbl_month_net.setText(margin_sd(m_m['本月净利'], m_m['本月收益'], [x['净利润'] for x in month_metric_rows]))
            self.lbl_month_avg_rev.setText(money_sd(decimal_divide(average_month_revenue, d), [x['收益'] for x in average_month_metrics]) + "/天")
            self.lbl_month_avg_var.setText(money_sd(decimal_divide(average_month_variable, d), [x['变动成本'] for x in average_month_metrics]) + "/天")
            self.lbl_month_avg_cost.setText(money_sd(decimal_divide(average_month_total, d), [x['总成本'] for x in average_month_metrics]) + "/天")
            self.lbl_month_avg_gross.setText(margin_sd(decimal_divide(average_month_gross, d), decimal_divide(average_month_revenue, d), [x['毛利'] for x in average_month_metrics]) + "/天")
            self.lbl_month_avg_net.setText(margin_sd(decimal_divide(average_month_net, d), decimal_divide(average_month_revenue, d), [x['净利润'] for x in average_month_metrics]) + "/天")
            days_in_month = calendar.monthrange(year, month)[1]
            projected_revenue = decimal_divide(average_month_revenue, d) * days_in_month
            previous_date = (datetime(year, month, 1) - timedelta(days=1))
            previous_summary = calc_month_summary(previous_date.year, previous_date.month, df_daily, df_fixed)
            previous_total_cost = previous_summary['本月总成本'] if previous_summary else m_m['本月总成本']
            projected_net = projected_revenue - previous_total_cost
            gross_margin = decimal_divide(m_m['本月毛利'], m_m['本月收益']) if m_m['本月收益'] > 0 else 0
            break_even_increase = calculate_break_even_daily_revenue_increase(
                projected_net, gross_margin, days_in_month
            )
            self.month_forecast_panel.set_values(
                projected_revenue, projected_net, break_even_increase
            )
        else:
            for lbl in [self.lbl_month_revenue, self.lbl_month_a_revenue, self.lbl_month_b_revenue, self.lbl_month_fixed, self.lbl_month_var_cost, self.lbl_month_cost,
                        self.lbl_month_gross, self.lbl_month_net, self.lbl_month_avg_rev, self.lbl_month_avg_var, self.lbl_month_avg_cost,
                        self.lbl_month_avg_gross, self.lbl_month_avg_net]:
                lbl.setText("-")
            self.month_forecast_panel.set_values(status=f"{year}年{month}月暂无经营数据")

        # Year logic
        y_y = calc_year_summary(year, df_daily, df_fixed)
        if y_y and y_y['活跃天数'] > 0:
            d = y_y.get('日均天数', elapsed_year_days(year))
            mo = y_y['活跃月数']
            year_rows = df_daily[df_daily['日期'].astype(str).str.startswith(f"{year}-")]
            if not year_rows.empty:
                year_dates = pd.to_datetime(year_rows['日期'], errors='coerce').dt.date
                year_rows = year_rows[year_dates <= today]
            year_rows = year_rows[year_rows.apply(day_has_meaningful_data, axis=1)] if not year_rows.empty else year_rows
            year_metric_rows = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in year_rows.iterrows()]
            year_metric_rows = [item for item in year_metric_rows if item]
            average_year_rows = year_rows[
                pd.to_datetime(year_rows['日期'], errors='coerce').dt.date < today
            ] if not year_rows.empty and year == today.year else year_rows
            average_year_metrics = [calc_day_metrics(str(row['日期']), df_daily, df_fixed) for _, row in average_year_rows.iterrows()]
            average_year_metrics = [item for item in average_year_metrics if item]
            average_year_revenue = sum(item['收益'] for item in average_year_metrics)
            average_year_variable = sum(item['变动成本'] for item in average_year_metrics)
            average_year_total = sum(item['总成本'] for item in average_year_metrics)
            average_year_gross = sum(item['毛利'] for item in average_year_metrics)
            average_year_net = sum(item['净利润'] for item in average_year_metrics)
            self.lbl_year_revenue.setText(money_sd(y_y['本年收益'], [x['收益'] for x in year_metric_rows]))
            self.lbl_year_a_revenue.setText(money_sd(store_sum(year_rows, 'A店收入'), [money_amount(row.get('A店收入', 0)) for _, row in year_rows.iterrows()]))
            self.lbl_year_b_revenue.setText(money_sd(store_sum(year_rows, 'B店收入'), [money_amount(row.get('B店收入', 0)) for _, row in year_rows.iterrows()]))
            self.lbl_year_fixed.setText(money_sd(y_y['本年固定成本'], [x['固定分摊'] for x in year_metric_rows]))
            self.lbl_year_var_cost.setText(money_sd(y_y['本年变动成本'], [x['变动成本'] for x in year_metric_rows]))
            self.lbl_year_cost.setText(money_sd(y_y['本年总成本'], [x['总成本'] for x in year_metric_rows]))
            self.lbl_year_expense.setText(money_sd(y_y['本年总支出'], [x['总成本'] for x in year_metric_rows]))
            self.lbl_year_gross.setText(margin_sd(y_y['本年毛利'], y_y['本年收益'], [x['毛利'] for x in year_metric_rows]))
            self.lbl_year_net.setText(margin_sd(y_y['本年净利'], y_y['本年收益'], [x['净利润'] for x in year_metric_rows]))
            self.lbl_year_avg_rev.setText(money_sd(decimal_divide(average_year_revenue, d)) + "/天")
            self.lbl_year_avg_var.setText(money_sd(decimal_divide(average_year_variable, d)) + "/天")
            self.lbl_year_avg_cost.setText(money_sd(decimal_divide(average_year_total, d)) + "/天")
            self.lbl_year_avg_gross.setText(margin_sd(decimal_divide(average_year_gross, d), decimal_divide(average_year_revenue, d), []) + "/天")
            self.lbl_year_avg_net.setText(margin_sd(decimal_divide(average_year_net, d), decimal_divide(average_year_revenue, d), []) + "/天")

            if mo > 0:
                self.lbl_year_mo_gross.setText(margin_sd(decimal_divide(y_y['本年毛利'], mo), decimal_divide(y_y['本年收益'], mo), [x['毛利'] for x in year_metric_rows]) + "/月")
                self.lbl_year_mo_net.setText(margin_sd(decimal_divide(y_y['本年净利'], mo), decimal_divide(y_y['本年收益'], mo), [x['净利润'] for x in year_metric_rows]) + "/月")
            else:
                self.lbl_year_mo_gross.setText("-");
                self.lbl_year_mo_net.setText("-")
        else:
            for lbl in [self.lbl_year_revenue, self.lbl_year_a_revenue, self.lbl_year_b_revenue, self.lbl_year_fixed, self.lbl_year_var_cost, self.lbl_year_cost,
                        self.lbl_year_expense,
                        self.lbl_year_gross, self.lbl_year_net, self.lbl_year_avg_rev, self.lbl_year_avg_var, self.lbl_year_avg_cost,
                        self.lbl_year_avg_gross, self.lbl_year_avg_net, self.lbl_year_mo_gross, self.lbl_year_mo_net]:
                lbl.setText("-")

        self.update_charts(day_str, year, month, df_daily, df_fixed)

    def update_charts(self, day_str, year, month, df_daily, df_fixed):
        self.pie_canvas_day.figure.clear()
        ax1 = self.pie_canvas_day.figure.add_subplot(111)
        m_day = calc_day_metrics(day_str, df_daily, df_fixed)
        if m_day and m_day['开销明细']:
            values, keys = list(m_day['开销明细'].values()), list(m_day['开销明细'].keys())
            total = sum(values)
            labels = [f"{k}: {v:.1f}元 ({v / total * 100:.1f}%)" for k, v in zip(keys, values)]
            wedges, _ = ax1.pie(list(map(float, values)), startangle=90, radius=0.9)
            ax1.axis('equal')
            ax1.set_title(f"{day_str} 开销占比")
            ax1.legend(wedges, labels, loc="center left", bbox_to_anchor=(0.85, 0.5), fontsize=9)
        else:
            ax1.text(0.5, 0.5, "当日无开销数据", ha='center', va='center')
        self.pie_canvas_day.figure.tight_layout(pad=1.5);
        self.pie_canvas_day.draw()

        self.pie_canvas_month.figure.clear()
        ax2 = self.pie_canvas_month.figure.add_subplot(111)
        m_month = calc_month_summary(year, month, df_daily, df_fixed)
        if m_month and m_month.get('开销明细'):
            values, keys = list(m_month['开销明细'].values()), list(m_month['开销明细'].keys())
            total = sum(values)
            labels = [f"{k}: {v:.1f}元 ({v / total * 100:.1f}%)" for k, v in zip(keys, values)]
            wedges, _ = ax2.pie(list(map(float, values)), startangle=90, radius=0.9)
            ax2.axis('equal')
            ax2.set_title(f"{year}年{month}月 累计开销占比")
            ax2.legend(wedges, labels, loc="center left", bbox_to_anchor=(0.85, 0.5), fontsize=9)
        else:
            ax2.text(0.5, 0.5, "本月无开销数据", ha='center', va='center')
        self.pie_canvas_month.figure.tight_layout(pad=1.5);
        self.pie_canvas_month.draw()

        month_df = df_daily[df_daily['日期'].astype(str).str.startswith(f"{year}-{month:02d}")].copy()
        if not month_df.empty:
            month_dates = pd.to_datetime(month_df['日期'], errors='coerce').dt.date
            month_df = month_df[month_dates <= datetime.now().date()]
        self.bar_canvas.figure.clear();
        ax4 = self.bar_canvas.figure.add_subplot(111)

        if not month_df.empty:
            month_df['日期_obj'] = pd.to_datetime(month_df['日期'])
            month_df['净利润'] = [calc_day_metrics(row['日期'], df_daily, df_fixed)['净利润'] for _, row in
                                  month_df.iterrows()]
            month_df['星期'] = month_df['日期_obj'].dt.dayofweek
            weekly_avg = month_df.groupby('星期')['净利润'].agg(lambda values: decimal_sum(values) / len(values)).reindex(range(7), fill_value=0)
            bars = ax4.bar(['周一', '周二', '周三', '周四', '周五', '周六', '周日'], list(map(float, weekly_avg.values)), color='#03A9F4',
                           width=0.6)
            ax4.set_title(f"{year}年{month}月 各星期平均净利润")
            ax4.set_ylabel("平均净利 (元)")
            min_h, max_h = float(min(weekly_avg.values)), float(max(weekly_avg.values))
            rng = max_h - min_h if max_h != min_h else abs(max_h) + 100
            ax4.set_ylim(min_h - rng * 0.3, max_h + rng * 0.3)
            for bar in bars:
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width() / 2, height + (rng * 0.05 if height >= 0 else -rng * 0.05),
                         f"{height:.0f}", ha='center', va='bottom' if height >= 0 else 'top')
        else:
            ax4.text(0.5, 0.5, "本月暂无数据", ha='center', va='center')

        self.bar_canvas.figure.tight_layout(pad=2.0)
        self.bar_canvas.draw()

        self.update_trend_chart_only()

    def update_trend_chart_only(self):
        df_daily, df_fixed = load_daily(), load_monthly_fixed()
        year = int(
            self.year_combo.currentText()) if self.year_combo.currentText().isdigit() else QDate.currentDate().year()
        month = int(
            self.month_combo.currentText()) if self.month_combo.currentText().isdigit() else QDate.currentDate().month()

        mode = self.trend_combo.currentText()
        self.trend_canvas.figure.clear()
        ax3 = self.trend_canvas.figure.add_subplot(111)

        days_in_month = calendar.monthrange(year, month)[1]
        x_labels = list(range(1, days_in_month + 1))

        vals, revs, actives = [], [], []
        for d in x_labels:
            day_value = datetime(year, month, d).date()
            m = (
                calc_day_metrics(f"{year}-{month:02d}-{d:02d}", df_daily, df_fixed)
                if day_value <= datetime.now().date() else None
            )
            if m:
                # 【终极防误判】只有这一天真正填了收入，或者有除了分摊固定成本之外的真实变动花销，才认为这天营业了
                is_active = (abs(m['收益']) > 0.01 or abs(m['变动成本']) > 0.01)
                actives.append(is_active)

                if "净利润" in mode:
                    vals.append(m['净利润']);
                    revs.append(m['收益'])
                elif "毛利润" in mode:
                    vals.append(m['毛利']);
                    revs.append(m['收益'])
                elif "食材" in mode:
                    vals.append(m['食材成本'] + m['佐料成本']);
                    revs.append(0)
                else:
                    vals.append(m['收益']);
                    revs.append(0)
            else:
                vals.append(0);
                revs.append(0);
                actives.append(False)

        color = '#00BCD4' if '净利润' in mode else (
            '#596d82' if '毛利润' in mode else ('#E91E63' if '食材' in mode else '#315f88'))

        ax3.plot(x_labels, list(map(float, vals)), marker='o', label=mode.split(' ')[0], color=color, linewidth=2)
        ax3.axhline(0, color='gray', linestyle='--', linewidth=0.8)
        ax3.set_title(f"{year}年{month}月 每日{mode.split(' ')[0]}走势")
        ax3.set_xlabel("日期 (日)");
        ax3.set_ylabel("金额 (元)")
        ax3.set_xticks(x_labels);
        ax3.tick_params(axis='x', labelsize=8)

        y_min, y_max = float(min(vals)), float(max(vals))
        pad = (y_max - y_min) * 0.4 if y_max != y_min else 800
        ax3.set_ylim(y_min - pad, y_max + pad)

        # 【终极排布逻辑】高低交错，绝不重叠
        for i, (d, val, rev, active) in enumerate(zip(x_labels, vals, revs, actives)):
            if active:
                if "利润" in mode and rev > 0:
                    txt = f"{val:.0f}\n({val / rev * 100:.1f}%)"
                elif "利润" in mode and rev == 0:
                    txt = f"{val:.0f}\n(0.0%)"
                else:
                    txt = f"{val:.0f}"

                # 单双数天数高度错开，彻底解决横向挤压的物理碰撞问题
                offset = pad * 0.12
                if i % 2 == 0:
                    y_pos = float(val) + offset if val >= 0 else float(val) - offset
                    va = 'bottom' if val >= 0 else 'top'
                else:
                    y_pos = float(val) - offset if val >= 0 else float(val) + offset
                    va = 'top' if val >= 0 else 'bottom'

                ax3.text(d, y_pos, txt, ha='center', va=va, fontsize=8)

        self.trend_canvas.figure.tight_layout(pad=2.0)
        self.trend_canvas.draw()


# ===================== 固定成本明细窗口 =====================
def open_fixed_category_manager_dialog(parent, refresh_callback=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("增加/修改/删除 固定成本类别")
    dlg.resize(520, 560)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("拖动整行可排序 | 双击类别名称可编辑 | 勾选后可删除"))

    table = UnitTableWidget()
    table.setHorizontalHeaderLabels(["删除", "类别名称"])
    original_categories = load_fixed_categories()
    for category in original_categories:
        table.add_unit_row(category)
    layout.addWidget(table)

    btn_layout = QHBoxLayout()
    btn_add = QPushButton("新增类别")
    btn_delete = QPushButton("删除勾选")
    btn_save = QPushButton("保存修改")
    btn_cancel = QPushButton("取消")
    for btn in (btn_add, btn_delete, btn_save, btn_cancel):
        btn.setMinimumHeight(32)
    btn_layout.addWidget(btn_add)
    btn_layout.addWidget(btn_delete)
    btn_layout.addStretch()
    btn_layout.addWidget(btn_save)
    btn_layout.addWidget(btn_cancel)
    layout.addLayout(btn_layout)

    def row_category(row):
        item = table.item(row, 1)
        if not item:
            return "", ""
        original = normalize_fixed_category(item.data(Qt.UserRole) or "")
        current = normalize_fixed_category(item.text())
        return original, current

    def current_rows():
        return [row_category(row) for row in range(table.rowCount())]

    def add_category():
        text, ok = QInputDialog.getText(dlg, "新增类别", "请输入新的固定成本类别（多个可用逗号隔开）：")
        if not ok or not text.strip():
            return
        existing = {current for _, current in current_rows() if current}
        duplicated = []
        for raw in text.replace('，', ',').split(','):
            category = normalize_fixed_category(raw)
            if not category:
                continue
            if category in existing:
                duplicated.append(category)
                continue
            row = table.add_unit_row(category)
            table.item(row, 1).setData(Qt.UserRole, category)
            existing.add(category)
        if duplicated:
            QMessageBox.warning(dlg, "提示", f"以下类别已存在：{'、'.join(duplicated)}")

    def delete_checked():
        rows = [
            row for row in range(table.rowCount())
            if table.item(row, 0) and table.item(row, 0).checkState() == Qt.Checked
        ]
        if not rows:
            QMessageBox.information(dlg, "提示", "请先勾选要删除的类别。")
            return
        used = set(load_fixed_expenses()['类别'].astype(str).map(normalize_fixed_category))
        blocked = []
        for row in rows:
            original, current = row_category(row)
            category = original or current
            if category in used:
                blocked.append(category)
        if blocked:
            QMessageBox.warning(
                dlg, "类别正在使用",
                f"以下类别已经在固定成本历史中使用，不能删除：{'、'.join(sorted(set(blocked)))}\n\n"
                "如果只是想改名，请直接双击类别名称修改后保存。"
            )
            return
        for row in sorted(rows, reverse=True):
            table.removeRow(row)

    def save_categories():
        new_categories, seen, duplicates, rename_map = [], set(), [], {}
        original_present = set()
        for original, current in current_rows():
            if not current:
                continue
            if current in seen:
                duplicates.append(current)
                continue
            seen.add(current)
            new_categories.append(current)
            if original:
                original_present.add(original)
                if original != current:
                    rename_map[original] = current
        if duplicates:
            QMessageBox.warning(dlg, "提示", f"类别不能重复：{'、'.join(sorted(set(duplicates)))}")
            return
        if not new_categories:
            QMessageBox.warning(dlg, "提示", "至少保留一个固定成本类别。")
            return

        used = set(load_fixed_expenses()['类别'].astype(str).map(normalize_fixed_category))
        deleted_used = [cat for cat in original_categories if cat not in original_present and cat in used]
        if deleted_used:
            QMessageBox.warning(
                dlg, "类别正在使用",
                f"以下类别已经在固定成本历史中使用，不能删除：{'、'.join(sorted(set(deleted_used)))}"
            )
            return

        if rename_map:
            if QMessageBox.question(
                    dlg, "同步历史类别",
                    "保存类别改名会同步修改所有固定成本历史明细里的类别。\n\n确定保存吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            apply_fixed_category_renames(rename_map)
        save_fixed_categories(new_categories)
        if callable(refresh_callback):
            refresh_callback()
        dlg.accept()

    btn_add.clicked.connect(add_category)
    btn_delete.clicked.connect(delete_checked)
    btn_save.clicked.connect(save_categories)
    btn_cancel.clicked.connect(dlg.reject)
    dlg.exec()


class FixedCostEditDialog(QDialog):
    def __init__(self, month_str, parent=None, changed_callback=None):
        super().__init__(parent)
        self.month_str = month_str
        self.changed_callback = changed_callback
        self.row_cache = {}
        self.next_new_id = 1
        self._loading = False
        self.setWindowTitle(f" {month_str} 增加/修改 固定成本")
        self.resize(980, 660)

        layout = QVBoxLayout(self)
        self.filter_layout = QHBoxLayout()
        layout.addLayout(self.filter_layout)

        try:
            year, month = [int(part) for part in self.month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            scope_text = f"显示范围：{self.month_str}-01 至 {self.month_str}-{last_day:02d}（整月固定成本支出）"
        except Exception:
            scope_text = f"显示范围：{self.month_str} 整月固定成本支出"
        self.lbl_scope = QLabel(scope_text)
        self.lbl_scope.setStyleSheet("color: #555; font-weight: bold;")
        layout.addWidget(self.lbl_scope)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["支出日期", "类别", "对象/说明", "金额(元)", "计入可用余额"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.SelectedClicked
        )
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        bottom_layout = QHBoxLayout()
        self.btn_add_row = QPushButton(" 新增一笔")
        self.btn_delete_row = QPushButton(" 删除选中支出")
        self.btn_save = QPushButton(" 保存修改")
        self.btn_close = QPushButton("关闭")
        self.lbl_total = QLabel("当前显示合计：0.00 元")
        self.lbl_total.setStyleSheet("font-weight: bold; font-size:16px; color: #111;")
        for btn in (self.btn_add_row, self.btn_delete_row, self.btn_save, self.btn_close):
            btn.setMinimumHeight(34)
        self.btn_save.setStyleSheet("background-color: #315f88; color: white; font-weight: bold;")
        bottom_layout.addWidget(self.btn_add_row)
        bottom_layout.addWidget(self.btn_delete_row)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.lbl_total)
        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

        self.btn_add_row.clicked.connect(self.add_row)
        self.btn_delete_row.clicked.connect(self.delete_selected)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_close.clicked.connect(self.accept)

        self.load_month_rows()
        self.rebuild_filters()
        self.refresh_table()

    def categories_for_month(self):
        categories = load_fixed_categories()
        for row in self.row_cache.values():
            category = normalize_fixed_category(row.get('类别', ''))
            if category and category not in categories:
                categories.append(category)
        return categories

    def rebuild_filters(self):
        while self.filter_layout.count():
            item = self.filter_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.filter_layout.addWidget(QLabel("显示类别："))
        self.category_checks = {}
        for category in self.categories_for_month():
            checkbox = QCheckBox(category)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.refresh_table)
            self.category_checks[category] = checkbox
            self.filter_layout.addWidget(checkbox)
        self.btn_select_all = QPushButton(" 全选")
        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.clicked.connect(self.select_none)
        self.btn_manage_categories = QPushButton(" 增加/修改/删除 类别")
        self.btn_manage_categories.clicked.connect(self.open_category_manager)
        self.filter_layout.addWidget(self.btn_select_all)
        self.filter_layout.addWidget(self.btn_select_none)
        self.filter_layout.addWidget(self.btn_manage_categories)
        self.filter_layout.addStretch()

    def selected_categories(self):
        return {
            category for category, checkbox in self.category_checks.items()
            if checkbox.isChecked()
        }

    def select_all(self):
        self.collect_visible_edits()
        for checkbox in self.category_checks.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
        self.refresh_table(collect=False)

    def select_none(self):
        self.collect_visible_edits()
        for checkbox in self.category_checks.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self.refresh_table(collect=False)

    def open_category_manager(self):
        self.collect_visible_edits()
        open_fixed_category_manager_dialog(self, self.on_categories_changed)

    def on_categories_changed(self):
        self.load_month_rows()
        self.rebuild_filters()
        self.refresh_table(collect=False)

    def load_month_rows(self):
        self.row_cache = {}
        expenses = load_fixed_expenses()
        month_expenses = expenses[expenses['日期'].astype(str).str.startswith(self.month_str)]
        for idx, row in month_expenses.iterrows():
            self.row_cache[int(idx)] = {
                '日期': str(row.get('日期', '')).strip(),
                '类别': normalize_fixed_category(row.get('类别', '')),
                '明细': str(row.get('明细', '')).strip(),
                '金额': money_amount(row.get('金额', 0)),
                FIXED_EXPENSE_CASH_COLUMN: fixed_expense_includes_cash(row.get(FIXED_EXPENSE_CASH_COLUMN, '')),
            }

    def collect_visible_edits(self):
        if self._loading or not hasattr(self, "table"):
            return
        for row in range(self.table.rowCount()):
            date_item = self.table.item(row, 0)
            if not date_item:
                continue
            source = date_item.data(Qt.UserRole)
            category_widget = self.table.cellWidget(row, 1)
            detail_item = self.table.item(row, 2)
            amount_item = self.table.item(row, 3)
            cash_widget = self.table.cellWidget(row, 4)
            cash_check = (
                cash_widget.findChild(QCheckBox)
                if cash_widget is not None and hasattr(cash_widget, 'findChild')
                else cash_widget
            )
            self.row_cache[source] = {
                '日期': date_item.text().strip(),
                '类别': normalize_fixed_category(category_widget.currentText() if category_widget else ''),
                '明细': detail_item.text().strip() if detail_item else '',
                '金额': amount_item.text().strip() if amount_item else '',
                FIXED_EXPENSE_CASH_COLUMN: bool(cash_check.isChecked()) if cash_check else True,
            }

    def refresh_table(self, collect=True):
        if collect:
            self.collect_visible_edits()
        selected = self.selected_categories() if hasattr(self, "category_checks") else set(load_fixed_categories())
        self._loading = True
        self.table.setRowCount(0)
        total = 0
        categories = self.categories_for_month()
        visible_rows = [
            (source, row) for source, row in self.row_cache.items()
            if normalize_fixed_category(row.get('类别', '')) in selected
        ]
        visible_rows.sort(key=lambda item: (str(item[1].get('日期', '')), str(item[1].get('类别', ''))))
        for source, data in visible_rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            date_item = QTableWidgetItem(str(data.get('日期', '')))
            date_item.setData(Qt.UserRole, source)
            self.table.setItem(row, 0, date_item)

            combo = QComboBox()
            category = normalize_fixed_category(data.get('类别', ''))
            combo_categories = list(categories)
            if category and category not in combo_categories:
                combo_categories.append(category)
            combo.addItems(combo_categories)
            if category:
                combo.setCurrentText(category)
            self.table.setCellWidget(row, 1, combo)
            self.table.setItem(row, 2, QTableWidgetItem(str(data.get('明细', ''))))
            try:
                amount = money_amount(data.get('金额', 0))
            except ValueError:
                amount = 0
            self.table.setItem(row, 3, QTableWidgetItem(f"{amount:.2f}" if amount else ""))
            cash_check = QCheckBox()
            cash_check.setChecked(fixed_expense_includes_cash(data.get(FIXED_EXPENSE_CASH_COLUMN, '')))
            cash_check.setToolTip("勾选后，这笔固定成本会从可用余额扣减")
            cash_cell = QWidget()
            cash_layout = QHBoxLayout(cash_cell)
            cash_layout.setContentsMargins(0, 0, 0, 0)
            cash_layout.setAlignment(Qt.AlignCenter)
            cash_layout.addWidget(cash_check)
            self.table.setCellWidget(row, 4, cash_cell)
            total += amount
        self._loading = False
        self.lbl_total.setText(f"当前显示合计：{total:.2f} 元")

    def add_row(self):
        self.collect_visible_edits()
        source = f"new-{self.next_new_id}"
        self.next_new_id += 1
        today = QDate.currentDate().toString("yyyy-MM-dd")
        day = today if today.startswith(self.month_str) else f"{self.month_str}-01"
        categories = load_fixed_categories()
        self.row_cache[source] = {
            '日期': day,
            '类别': categories[0] if categories else '',
            '明细': '',
            '金额': '',
            FIXED_EXPENSE_CASH_COLUMN: True,
        }
        category = self.row_cache[source]['类别']
        if category in getattr(self, "category_checks", {}):
            self.category_checks[category].blockSignals(True)
            self.category_checks[category].setChecked(True)
            self.category_checks[category].blockSignals(False)
        self.refresh_table(collect=False)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == source:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                break

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要删除的支出。")
            return
        self.collect_visible_edits()
        date_item = self.table.item(row, 0)
        source = date_item.data(Qt.UserRole) if date_item else None
        if source is None:
            return
        if QMessageBox.question(
                self, "删除确认", "确定删除选中的固定成本支出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.row_cache.pop(source, None)
        self.refresh_table(collect=False)

    def validated_rows(self):
        self.collect_visible_edits()
        rows = []
        for data in self.row_cache.values():
            day = str(data.get('日期', '')).strip()
            category = normalize_fixed_category(data.get('类别', ''))
            detail = str(data.get('明细', '')).strip()
            amount_text = data.get('金额', '')
            if not day and not category and not detail and not str(amount_text).strip():
                continue
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', day):
                QMessageBox.warning(self, "日期错误", f"支出日期格式必须是 yyyy-mm-dd：{day}")
                return None
            if not day.startswith(self.month_str):
                QMessageBox.warning(self, "月份错误", f"当前窗口是 {self.month_str}，不能保存其它月份的支出：{day}")
                return None
            if not category:
                QMessageBox.warning(self, "类别错误", "每笔固定成本都必须选择类别。")
                return None
            try:
                amount = money_input(amount_text)
            except ValueError:
                QMessageBox.warning(self, "金额错误", f"金额必须是纯数字：{amount_text}")
                return None
            if amount <= 0:
                QMessageBox.warning(self, "金额错误", "固定成本金额必须大于 0。")
                return None
            rows.append({
                '日期': day, '类别': category, '明细': detail, '金额': amount,
                FIXED_EXPENSE_CASH_COLUMN: fixed_expense_includes_cash(
                    data.get(FIXED_EXPENSE_CASH_COLUMN, True)
                ),
            })
        return rows

    def save_changes(self):
        rows = self.validated_rows()
        if rows is None:
            return
        expenses = load_fixed_expenses()
        other_months = expenses[~expenses['日期'].astype(str).str.startswith(self.month_str)].copy()
        month_df = pd.DataFrame(rows, columns=FIXED_EXPENSE_COLUMNS)
        combined = pd.concat([other_months, month_df], ignore_index=True)
        save_fixed_expenses(combined)
        sync_monthly_fixed_from_expenses(self.month_str, combined)
        if callable(self.changed_callback):
            self.changed_callback()
        self.load_month_rows()
        self.rebuild_filters()
        self.refresh_table(collect=False)
        QMessageBox.information(self, "保存成功", f"{self.month_str} 固定成本已保存。")


# ===================== 记账本页面 =====================
class LedgerTab(QWidget):
    def __init__(self):
        super().__init__()
        self._role = ''
        self._entry_windows_cache = {}
        self._entry_windows_cache_loaded_at = 0
        self._is_syncing_ledger_dates = False
        self._loaded_daily_record = {}
        self._snapshot_daily = {}
        self._snapshot_fixed = {}
        self._loading_daily = False
        self.init_ui()
        self._snapshot_daily = self.get_daily_ui_state()
        self._snapshot_fixed = self.get_fixed_ui_state()

    def init_ui(self):
        main_layout = QVBoxLayout()
        entry_group = QGroupBox(" 录入/编辑当日流水")
        entry_layout = QGridLayout()

        self.btn_entry_prev = QPushButton("◀ 前一天")
        self.entry_date = QDateEdit(QDate.currentDate())
        self.entry_date.setCalendarPopup(True)
        self.btn_entry_next = QPushButton("后一天 ▶")
        self.btn_entry_today = QPushButton("今天")
        date_hbox = QHBoxLayout()
        date_hbox.addWidget(self.btn_entry_prev)
        date_hbox.addWidget(self.entry_date)
        date_hbox.addWidget(self.btn_entry_next)
        date_hbox.addWidget(self.btn_entry_today)

        self.entry_revenue = QLineEdit()
        self.entry_revenue.setReadOnly(True)
        self.entry_revenue.setPlaceholderText("由9个收入输入框自动合计")
        self.entry_total_cash = QLineEdit(); self.entry_total_cash.setReadOnly(True)
        self.entry_a_cash = QLineEdit(); self.entry_b_cash = QLineEdit()
        self.entry_total_online = QLineEdit(); self.entry_total_online.setReadOnly(True)
        self.entry_fees = QLineEdit(); self.entry_available_balance = QLineEdit(); self.entry_shareholder_loan = QLineEdit()
        self.entry_a_wechat_add = QLineEdit(); self.entry_a_wechat_auto = QLineEdit(); self.entry_a_wechat_auto.setReadOnly(True); self.entry_a_wechat_override = QLineEdit()
        self.entry_a_alipay_add = QLineEdit(); self.entry_a_alipay_override = QLineEdit()
        self.entry_b_wechat_add = QLineEdit(); self.entry_b_wechat_auto = QLineEdit(); self.entry_b_wechat_auto.setReadOnly(True); self.entry_b_wechat_override = QLineEdit()
        self.entry_b_alipay_add = QLineEdit(); self.entry_b_alipay_override = QLineEdit()
        self.entry_a_revenue = QLineEdit(); self.entry_a_revenue.setReadOnly(True)
        self.entry_b_revenue = QLineEdit(); self.entry_b_revenue.setReadOnly(True)
        self.entry_student_takeout = QLineEdit(); self.entry_a_takeout = QLineEdit(); self.entry_b_takeout = QLineEdit()
        for widget in (
            self.entry_a_cash, self.entry_b_cash, self.entry_a_wechat_add, self.entry_a_wechat_override,
            self.entry_a_alipay_add, self.entry_a_alipay_override, self.entry_b_wechat_add,
            self.entry_b_wechat_override, self.entry_b_alipay_add, self.entry_b_alipay_override,
            self.entry_student_takeout, self.entry_a_takeout, self.entry_b_takeout,
        ):
            widget.setPlaceholderText("0.00")

        self.entry_new_customers = QLineEdit()
        self.entry_new_customers.setPlaceholderText("填整数")
        self.entry_new_customers.setValidator(QIntValidator(0, 9999999, self))
        self.entry_total_customers = QLineEdit()
        self.entry_total_customers.setPlaceholderText("填整数")
        self.entry_total_customers.setValidator(QIntValidator(0, 9999999, self))

        self.entry_food_detail = QLineEdit();
        self.entry_food_detail.setPlaceholderText("例: 牛肉 400 或 牛肉400")
        self.btn_manage_food = QPushButton(" 选择食材")
        food_detail_layout = QHBoxLayout();
        food_detail_layout.addWidget(self.entry_food_detail);
        food_detail_layout.addWidget(self.btn_manage_food)

        self.entry_spice_detail = QLineEdit();
        self.entry_spice_detail.setPlaceholderText("例: 盐 10 或 耗油25")
        self.btn_manage_spice = QPushButton(" 选择佐料")
        spice_detail_layout = QHBoxLayout();
        spice_detail_layout.addWidget(self.entry_spice_detail);
        spice_detail_layout.addWidget(self.btn_manage_spice)

        self.entry_other_detail = QLineEdit();
        self.entry_other_detail.setPlaceholderText("例: 纸巾20, 采购办公用品100")
        self.entry_daily_note = QLineEdit();
        self.entry_daily_note.setPlaceholderText("可填入其他补充说明 (选填)")
        for detail_widget in (
            self.entry_food_detail,
            self.entry_spice_detail,
            self.entry_other_detail,
            self.entry_daily_note,
        ):
            detail_widget.setMinimumHeight(32)
            detail_font = detail_widget.font()
            detail_font.setPointSize(max(detail_font.pointSize(), 12))
            detail_widget.setFont(detail_font)

        entry_layout.addWidget(QLabel("日期:"), 0, 0)
        entry_layout.addLayout(date_hbox, 0, 1)
        entry_layout.addWidget(QLabel("总收入（自动合计）:"), 0, 2)
        entry_layout.addWidget(self.entry_revenue, 0, 3)

        # Entry-only clocks live in a compact panel at the upper-right of the
        # bookkeeping editor.  There can be many independently timed detail
        # items, so the panel scrolls instead of stretching the entire form.
        self.entry_countdown_panel = QGroupBox("⏱ 录入倒计时")
        countdown_panel_layout = QVBoxLayout(self.entry_countdown_panel)
        countdown_panel_layout.setContentsMargins(8, 8, 8, 8)
        self.lbl_entry_countdown = QLabel("")
        self.lbl_entry_countdown.setTextFormat(Qt.PlainText)
        self.lbl_entry_countdown.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lbl_entry_countdown.setWordWrap(True)
        self.lbl_entry_countdown.setStyleSheet(
            "color:#8A4B08; font-weight:600; padding:3px;"
        )
        countdown_scroll = QScrollArea()
        countdown_scroll.setWidgetResizable(True)
        countdown_scroll.setFrameShape(QFrame.NoFrame)
        countdown_scroll.setMinimumHeight(170)
        countdown_scroll.setMaximumHeight(245)
        countdown_scroll.setWidget(self.lbl_entry_countdown)
        countdown_panel_layout.addWidget(countdown_scroll)
        self.entry_countdown_panel.setMinimumWidth(360)
        self.entry_countdown_panel.setMaximumWidth(520)
        self.entry_countdown_panel.setVisible(False)
        entry_layout.addWidget(self.entry_countdown_panel, 0, 4, 3, 2)
        entry_layout.setColumnStretch(1, 1)
        entry_layout.setColumnStretch(3, 1)

        # Keep the cash totals and the two store inputs in visibly separate
        # blocks.  This mirrors the paper/website layout and prevents the
        # read-only totals from being mistaken for additional inputs.
        cash_group = QGroupBox("收款汇总")
        cash_layout = QGridLayout(cash_group)
        cash_layout.setHorizontalSpacing(14)
        cash_layout.setVerticalSpacing(8)
        cash_fields = (
            ("总现金", self.entry_total_cash, True),
            ("总线上", self.entry_total_online, True),
            ("手续费／抽成", self.entry_fees, False),
        )
        for index, (label_text, widget, calculated) in enumerate(cash_fields):
            row, col = divmod(index, 2)
            label = QLabel(f"{label_text}:" )
            label.setStyleSheet("font-weight:600;")
            cash_layout.addWidget(label, row * 2, col * 2)
            cash_layout.addWidget(widget, row * 2, col * 2 + 1)
            if calculated:
                widget.setToolTip("按两家店的现金/线上输入自动汇总")
        # Keep both input columns equally wide; the final loan row naturally
        # occupies the left column while the right side remains breathing room.
        cash_layout.setColumnStretch(1, 1)
        cash_layout.setColumnStretch(3, 1)
        entry_layout.addWidget(cash_group, 1, 0, 2, 4)
        self.cash_summary_group = cash_group

        store_income_group = QGroupBox("两家店收入填写")
        store_income_group.setToolTip("按店填写微信、支付宝和现金；总收入会自动合计。")
        store_income_layout = QHBoxLayout(store_income_group)
        store_income_layout.setContentsMargins(12, 10, 12, 10)
        store_income_layout.setSpacing(14)
        for store_name, fields in (
            ("A店", (
                ("微信收入:", self.entry_a_wechat_override),
                ("支付宝收入:", self.entry_a_alipay_override),
                ("现金收入:", self.entry_a_cash),
                ("本店合计:", self.entry_a_revenue),
            )),
            ("B店", (
                ("微信收入:", self.entry_b_wechat_override),
                ("支付宝收入:", self.entry_b_alipay_override),
                ("现金收入:", self.entry_b_cash),
                ("本店合计:", self.entry_b_revenue),
            )),
        ):
            card = QGroupBox(store_name)
            card_layout = QFormLayout(card)
            card_layout.setContentsMargins(12, 9, 12, 9)
            card_layout.setHorizontalSpacing(12)
            card_layout.setVerticalSpacing(8)
            card_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for label_text, widget in fields:
                widget.setMinimumHeight(30)
                card_layout.addRow(label_text, widget)
            store_income_layout.addWidget(card, 1)
        store_hint = QLabel("微信、支付宝、现金按店填写；本店合计、总现金、总线上和总收入自动计算。")
        store_hint.setWordWrap(True)
        store_hint.setStyleSheet("color:#5F6B7A; padding-top:2px;")
        store_income_layout.addWidget(store_hint, 0)
        entry_layout.addWidget(store_income_group, 3, 0, 3, 4)
        self.store_income_group = store_income_group

        takeout_group = QGroupBox("外卖收入填写")
        takeout_layout = QHBoxLayout(takeout_group)
        for label_text, widget in (
            ("学生外卖", self.entry_student_takeout),
            ("A店外卖", self.entry_a_takeout),
            ("B店外卖", self.entry_b_takeout),
        ):
            box = QGroupBox(label_text); box_layout = QFormLayout(box)
            box_layout.addRow("金额:", widget); takeout_layout.addWidget(box, 1)
        entry_layout.addWidget(takeout_group, 6, 0, 1, 4)
        self.takeout_income_group = takeout_group

        entry_layout.addWidget(QLabel("新客人数量:"), 7, 0)
        entry_layout.addWidget(self.entry_new_customers, 7, 1)
        entry_layout.addWidget(QLabel("总客人数:"), 7, 2)
        entry_layout.addWidget(self.entry_total_customers, 7, 3)
        entry_layout.addWidget(QLabel("食材明细及金额:"), 8, 0)
        entry_layout.addLayout(food_detail_layout, 8, 1, 1, 3)
        entry_layout.addWidget(QLabel("佐料明细及金额:"), 9, 0)
        entry_layout.addLayout(spice_detail_layout, 9, 1, 1, 3)
        entry_layout.addWidget(QLabel("其它明细及金额:"), 10, 0)
        entry_layout.addWidget(self.entry_other_detail, 10, 1, 1, 3)
        entry_layout.addWidget(QLabel("当日备注:"), 11, 0)
        entry_layout.addWidget(self.entry_daily_note, 11, 1, 1, 3)

        self.btn_overwrite_record = QPushButton(" 覆盖当日记录 (完全替换原有数据)")
        self.btn_sync_wechat = QPushButton(" 用微信Api更新未填写收入")
        self.btn_force_sync_wechat = QPushButton(" 用微信Api覆盖当日收入")
        self.btn_sync_wechat.setVisible(False); self.btn_force_sync_wechat.setVisible(False)
        self.btn_sync_wechat.setStyleSheet(
            "background-color: #315f88; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_reset = QPushButton("↩ 撤销未保存的所有修改")
        self.btn_overwrite_record.setStyleSheet(
            "background-color: #596d82; color: white; font-weight: bold; padding: 6px;")

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_overwrite_record)
        btn_layout.addWidget(self.btn_sync_wechat)
        btn_layout.addWidget(self.btn_force_sync_wechat)
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()
        self.btn_overwrite_record.setText("保存当日流水")
        self.btn_overwrite_record.setToolTip("保存当前日期的完整流水，替换该日原有内容")
        entry_layout.addLayout(btn_layout, 12, 0, 1, 4)
        self.btn_force_sync_wechat.setStyleSheet(
            "background-color: #B83232; color: white; font-weight: bold; padding: 6px;"
        )
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #888; font-size: 12px;")
        entry_layout.addWidget(self.lbl_status, 13, 0, 1, 4)
        entry_group.setLayout(entry_layout)
        main_layout.addWidget(entry_group)

        fixed_group = QGroupBox(" 固定成本录入")
        fixed_layout = QGridLayout()

        self.fixed_year_combo = QComboBox()
        self.fixed_year_combo.addItems([str(y) for y in range(2020, 2050)])
        self.fixed_year_combo.setCurrentText(str(QDate.currentDate().year()))
        self.fixed_month_combo = QComboBox()
        self.fixed_month_combo.addItems([f"{i:02d}" for i in range(1, 13)])
        self.fixed_month_combo.setCurrentText(f"{QDate.currentDate().month():02d}")

        fixed_date_hbox = QHBoxLayout()
        fixed_date_hbox.addWidget(QLabel("年:"))
        fixed_date_hbox.addWidget(self.fixed_year_combo)
        fixed_date_hbox.addWidget(QLabel("月:"))
        fixed_date_hbox.addWidget(self.fixed_month_combo)
        fixed_date_hbox.addStretch()

        self.fixed_rent = QLineEdit()
        self.fixed_rent.setReadOnly(True)
        self.fixed_rent.setPlaceholderText("由固定成本明细里的房租及物业费自动汇总")
        self.fixed_note = QLineEdit()
        self.fixed_note.setReadOnly(True)
        self.fixed_note.setPlaceholderText("由房租及物业费明细自动汇总")
        self.fixed_actual_water = QLineEdit()
        self.fixed_actual_water.setPlaceholderText("留空则按预计／支出计算")
        self.fixed_expected_water = QLineEdit()
        self.fixed_expected_water.setPlaceholderText("实际使用未填时采用")
        self.fixed_actual_electric = QLineEdit()
        self.fixed_actual_electric.setPlaceholderText("留空则按预计／支出计算")
        self.fixed_expected_electric = QLineEdit()
        self.fixed_expected_electric.setPlaceholderText("实际使用未填时采用")
        self.fixed_expected_gas = QLineEdit()
        self.fixed_expected_gas.setPlaceholderText("留空则按煤气费实际支出")
        self.btn_save_actual_utilities = QPushButton("保存实际／预计水电煤气费")
        self.btn_save_actual_utilities.setStyleSheet(
            "background-color: #315f88; color: white; font-weight: bold; padding: 6px;"
        )
        self.btn_edit_fixed_expenses = QPushButton("查看/增加/修改 固定成本")
        self.btn_edit_fixed_expenses.setStyleSheet(
            "background-color: #315f88; color: white; font-weight: bold; padding: 6px;"
        )
        self.lbl_fixed_summary = QLabel("")
        self.lbl_fixed_summary.setStyleSheet("color: #555; font-weight: bold;")

        fixed_layout.addWidget(QLabel("选择月份:"), 0, 0);
        fixed_layout.addLayout(fixed_date_hbox, 0, 1, 1, 3)
        fixed_layout.addWidget(self.btn_edit_fixed_expenses, 1, 0, 1, 4, Qt.AlignLeft)
        fixed_layout.addWidget(QLabel("本月房租及物业合计:"), 2, 0)
        fixed_layout.addWidget(self.fixed_rent, 2, 1)
        fixed_layout.addWidget(QLabel("房租/物业备注汇总:"), 2, 2)
        fixed_layout.addWidget(self.fixed_note, 2, 3)
        fixed_layout.addWidget(QLabel("实际使用水费:"), 3, 0)
        fixed_layout.addWidget(self.fixed_actual_water, 3, 1)
        fixed_layout.addWidget(QLabel("预计水费:"), 3, 2)
        fixed_layout.addWidget(self.fixed_expected_water, 3, 3)
        fixed_layout.addWidget(QLabel("实际使用电费:"), 4, 0)
        fixed_layout.addWidget(self.fixed_actual_electric, 4, 1)
        fixed_layout.addWidget(QLabel("预计电费:"), 4, 2)
        fixed_layout.addWidget(self.fixed_expected_electric, 4, 3)
        fixed_layout.addWidget(QLabel("预计煤气费:"), 5, 0)
        fixed_layout.addWidget(self.fixed_expected_gas, 5, 1)
        fixed_layout.addWidget(self.btn_save_actual_utilities, 6, 0, 1, 4)
        fixed_layout.addWidget(self.lbl_fixed_summary, 7, 0, 1, 4)
        fixed_group.setLayout(fixed_layout)
        main_layout.addWidget(fixed_group)

        hist_group = QGroupBox(" 历史记录（双击回填编辑，选中可删除）")
        self.history_group = hist_group
        self.history_visible_rows = 25
        hist_layout = QVBoxLayout()
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel(" 选择表格查看日期: "))
        self.hist_year_combo, self.hist_month_combo = QComboBox(), QComboBox()
        self.hist_year_combo.addItems([str(y) for y in range(2020, 2050)]);
        self.hist_year_combo.setCurrentText(str(QDate.currentDate().year()))
        self.hist_month_combo.addItems([f"{i:02d}" for i in range(1, 13)]);
        self.hist_month_combo.setCurrentText(f"{QDate.currentDate().month():02d}")
        filter_layout.addWidget(QLabel("年:"));
        filter_layout.addWidget(self.hist_year_combo)
        filter_layout.addWidget(QLabel("月:"));
        filter_layout.addWidget(self.hist_month_combo);
        self.btn_view_month_history = QPushButton(" 大字查看本月历史记录")
        filter_layout.addWidget(self.btn_view_month_history)
        filter_layout.addStretch()
        hist_layout.addLayout(filter_layout)

        self.table = QTableWidget();
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels(
            ["日期", "总收入 (Revenue)", "A店收入", "B店收入", "新客人数量", "总客人数", "食材总价格", "佐料明细", "当日总固定成本", "其它明细", "当日备注", "当日毛利润(毛利率)", "当日净利润(净利率)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(30)
        # 汇总行之外，至少留出 25 条历史记录的可见空间；整个记账本页面
        # 已经在 QScrollArea 中，所以屏幕较小时直接滚动整页即可。
        self.table.setMinimumHeight(34 + 58 + self.history_visible_rows * 30 + 12)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.edit_selected_row)
        hist_layout.addWidget(self.table)

        btm_btn_layout = QHBoxLayout()
        self.btn_delete = QPushButton(" 删除选中行");
        self.btn_refresh_table = QPushButton(" 强制刷新表格")
        btm_btn_layout.addWidget(self.btn_delete);
        btm_btn_layout.addWidget(self.btn_refresh_table);
        btm_btn_layout.addStretch()
        hist_layout.addLayout(btm_btn_layout);
        hist_group.setLayout(hist_layout)
        hist_group.setMinimumHeight(self.table.minimumHeight() + 105)
        main_layout.addWidget(hist_group)

        # 包进滚动区域，实现全局滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content_widget = QWidget()
        content_widget.setLayout(main_layout)
        scroll.setWidget(content_widget)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        def set_today_and_load():
            self.set_entry_date_safely(QDate.currentDate())

        self.btn_entry_prev.clicked.connect(lambda: self.set_entry_date_safely(self.entry_date.date().addDays(-1)))
        self.btn_entry_next.clicked.connect(lambda: self.set_entry_date_safely(self.entry_date.date().addDays(1)))
        self.btn_entry_today.clicked.connect(set_today_and_load)

        self.btn_manage_food.clicked.connect(lambda: self.open_item_manager(self.entry_food_detail, "食材"))
        self.btn_manage_spice.clicked.connect(lambda: self.open_item_manager(self.entry_spice_detail, "佐料"))
        self.btn_overwrite_record.clicked.connect(lambda: self.save_record(mode="overwrite"))
        self.btn_sync_wechat.clicked.connect(lambda: self.sync_wechat_bill(False))
        self.btn_force_sync_wechat.clicked.connect(lambda: self.sync_wechat_bill(True))
        for widget in (
            self.entry_a_cash, self.entry_b_cash, self.entry_a_wechat_add, self.entry_a_wechat_override,
            self.entry_a_alipay_add, self.entry_a_alipay_override, self.entry_b_wechat_add,
            self.entry_b_wechat_override, self.entry_b_alipay_add, self.entry_b_alipay_override,
            self.entry_student_takeout, self.entry_a_takeout, self.entry_b_takeout,
        ):
            widget.textChanged.connect(self.sync_revenue_breakdown)
        self.btn_reset.clicked.connect(self.reset_form)
        self.btn_edit_fixed_expenses.clicked.connect(self.open_fixed_expense_editor)
        self.btn_save_actual_utilities.clicked.connect(self.save_actual_utility_costs)
        self.btn_view_month_history.clicked.connect(self.open_month_history_dialog)
        self.btn_delete.clicked.connect(self.delete_record)
        self.btn_refresh_table.clicked.connect(self.refresh_table)

        self._entry_timer = QTimer(self)
        self._entry_timer.setInterval(1000)
        self._entry_timer.timeout.connect(self._refresh_entry_countdown)
        self._entry_timer.start()

        self.entry_date.dateChanged.connect(self.on_entry_date_changed)

        self.fixed_year_combo.currentTextChanged.connect(lambda: self.sync_all_dates(source='fixed'))
        self.fixed_month_combo.currentTextChanged.connect(lambda: self.sync_all_dates(source='fixed'))
        self.hist_year_combo.currentTextChanged.connect(lambda: self.sync_all_dates(source='hist'))
        self.hist_month_combo.currentTextChanged.connect(lambda: self.sync_all_dates(source='hist'))

        self.refresh_table()
        self.load_fixed_cost_for_month()
        self.auto_load_daily_record()

    def set_role(self, role):
        """Apply cloud role visibility and editing rules to the bookkeeping tab."""
        next_role = str(role or '')
        role_changed = next_role != self._role
        self._role = next_role
        can_modify = self._role in {'admin', 'editor'}
        # Entry accounts may remove neither rows nor existing records.  The
        # network read-only pass can still disable this button when offline.
        self.btn_delete.setEnabled(can_modify)
        self._refresh_entry_window_cache(force=role_changed)
        self._refresh_entry_countdown()

    def _refresh_entry_window_cache(self, force=False):
        now = time.monotonic()
        if not force and now - self._entry_windows_cache_loaded_at < 2.0:
            return
        try:
            self._entry_windows_cache = _load_entry_windows()
        except Exception:
            self._entry_windows_cache = {}
        self._entry_windows_cache_loaded_at = now

    def _refresh_entry_countdown(self):
        if not hasattr(self, 'lbl_entry_countdown'):
            return
        if self._role != 'entry':
            self.lbl_entry_countdown.clear()
            self.lbl_entry_countdown.setVisible(False)
            if hasattr(self, 'entry_countdown_panel'):
                self.entry_countdown_panel.setVisible(False)
            return
        self._refresh_entry_window_cache()
        day_str = self.entry_date.date().toString('yyyy-MM-dd')
        state = self._entry_windows_cache.get(day_str, {})
        state = state if isinstance(state, dict) else {}
        now = datetime.now().astimezone()
        record = self._loaded_daily_record if isinstance(self._loaded_daily_record, dict) else {}
        lines = ['【9个收入输入框】']
        income_state = state.get('income', {})
        income_state = income_state if isinstance(income_state, dict) else {}
        cutoff = _entry_income_deadline(day_str)
        for slot in ENTRY_INCOME_SLOTS:
            was_filled, _value = _entry_income_slot_value(record, slot)
            slot_state = _entry_income_timing_state(
                income_state, slot, promote=False, allow_legacy=was_filled
            )
            saved_at = _parse_entry_stamp(slot_state.get('saved_at')) if isinstance(slot_state, dict) else None
            deadline = _parse_entry_stamp(slot_state.get('edit_deadline')) if isinstance(slot_state, dict) else None
            if saved_at is None and was_filled:
                saved_at = _entry_record_fallback(record, now - ENTRY_EDIT_WINDOW)
                deadline = saved_at + ENTRY_EDIT_WINDOW
            display_slot = _store_text(slot)
            if saved_at is not None:
                deadline = deadline or saved_at + ENTRY_EDIT_WINDOW
                if now < deadline:
                    lines.append(f'{display_slot}：可修改 {_entry_time_text((deadline - now).total_seconds())}')
                else:
                    lines.append(f'{display_slot}：已锁定')
            elif cutoff and now < cutoff:
                lines.append(f'{display_slot}：未录入，首录剩余 {_entry_time_text((cutoff - now).total_seconds())}')
            else:
                lines.append(f'{display_slot}：首次录入已截止')

        lines.append('【客人数（各自30分钟）】')
        for key, label in (('new', '新客'), ('total', '总客数')):
            customer = state.get('customers', {}).get(key, {})
            deadline = _parse_entry_stamp(customer.get('edit_deadline'))
            if deadline is not None:
                status = '已锁定' if now >= deadline else '可修改 ' + _entry_time_text((deadline - now).total_seconds())
            else:
                status = '未录入，首次保存后开始30分钟' if not _entry_customer_value(record, key)[0] else '已录入，保存时校验服务器权限'
            lines.append(f'{label}：{status}')
        detail_deadlines = state.get('detail_add_deadlines', {})
        detail_deadlines = detail_deadlines if isinstance(detail_deadlines, dict) else {}
        lines.append('【明细新增（分类独立）】')
        for category in ENTRY_DETAIL_KEYS:
            detail_deadline = _parse_entry_stamp(detail_deadlines.get(category))
            if detail_deadline is None:
                field = ENTRY_DETAIL_FIELD_MAP[category]
                cost_field = '其他' if category == '其它' else f'{category}成本'
                if _entry_detail_token_list(record.get(field, '')) or abs(safe_float(record.get(cost_field, 0))) > Decimal('1e-9'):
                    detail_deadline = _entry_record_fallback(record, now - ENTRY_ADD_WINDOW) + ENTRY_ADD_WINDOW
            if detail_deadline is None:
                lines.append(f'{category}：保存该分类首个明细后开始12小时')
            elif now < detail_deadline:
                lines.append(f'{category}：可新增 {_entry_time_text((detail_deadline - now).total_seconds())}')
            else:
                lines.append(f'{category}：新增已截止')

        details_state = state.get('details', {})
        details_state = details_state if isinstance(details_state, dict) else {}
        detail_lines = []
        for category in ENTRY_DETAIL_KEYS:
            raw = details_state.get(category)
            if isinstance(raw, dict) and isinstance(raw.get('items'), list):
                items = [item for item in raw.get('items', []) if isinstance(item, dict) and item.get('active', True)]
                legacy_cost = raw.get('legacy_cost')
            elif isinstance(raw, dict):
                items = [
                    value for key, value in raw.items()
                    if key not in {'items', 'legacy_cost'} and isinstance(value, dict)
                ]
                legacy_cost = raw.get('legacy_cost')
            else:
                items, legacy_cost = [], None

            # A day saved by an older build may have text but no per-item map.
            # Display those items using the same conservative migration clock
            # that validation will apply on the next successful save.
            known_text = {_entry_normalized_token(item.get('text')) for item in items}
            legacy_fallback = _entry_record_fallback(record, now - ENTRY_ADD_WINDOW)
            for token in _entry_detail_token_list(record.get(ENTRY_DETAIL_FIELD_MAP[category], '')):
                if _entry_normalized_token(token) not in known_text:
                    items.append({
                        'text': token,
                        'saved_at': legacy_fallback.isoformat(timespec='seconds'),
                        'edit_deadline': (legacy_fallback + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
                        'active': True,
                    })
            for item in items:
                text = str(item.get('text') or '').strip()
                if not text:
                    continue
                saved_at = _parse_entry_stamp(item.get('saved_at')) or legacy_fallback
                deadline = _parse_entry_stamp(item.get('edit_deadline')) or saved_at + ENTRY_EDIT_WINDOW
                status = (
                    f'可修改/删除 {_entry_time_text((deadline - now).total_seconds())}'
                    if now < deadline else '已锁定'
                )
                detail_lines.append(f'{category}·{text}：{status}')
            if isinstance(legacy_cost, dict) and legacy_cost.get('active', True):
                saved_at = _parse_entry_stamp(legacy_cost.get('saved_at')) or legacy_fallback
                deadline = _parse_entry_stamp(legacy_cost.get('edit_deadline')) or saved_at + ENTRY_EDIT_WINDOW
                status = (
                    f'可修改/删除 {_entry_time_text((deadline - now).total_seconds())}'
                    if now < deadline else '已锁定'
                )
                detail_lines.append(f'{category}·旧版金额：{status}')
        if detail_lines:
            lines.append('【已保存明细（各自30分钟）】')
            lines.extend(detail_lines)

        self.lbl_entry_countdown.setText('\n'.join(lines))
        self.lbl_entry_countdown.setVisible(True)
        if hasattr(self, 'entry_countdown_panel'):
            self.entry_countdown_panel.setVisible(True)

    # === 精准 UI 状态快照获取 ===
    def get_daily_ui_state(self):
        return {
            'date': self.entry_date.date().toString("yyyy-MM-dd"),
            'rev': self.entry_revenue.text().strip(),
            'total_cash': self.entry_total_cash.text().strip(),
            'a_cash': self.entry_a_cash.text().strip(), 'b_cash': self.entry_b_cash.text().strip(),
            'total_online': self.entry_total_online.text().strip(),
            'fees': self.entry_fees.text().strip(), 'available_balance': self.entry_available_balance.text().strip(),
            'shareholder_loan': self.entry_shareholder_loan.text().strip(),
            'a_wechat_add': self.entry_a_wechat_add.text().strip(),
            'a_wechat_auto': self.entry_a_wechat_auto.text().strip(),
            'a_wechat_override': self.entry_a_wechat_override.text().strip(),
            'a_alipay_add': self.entry_a_alipay_add.text().strip(),
            'a_alipay_override': self.entry_a_alipay_override.text().strip(),
            'b_wechat_add': self.entry_b_wechat_add.text().strip(),
            'b_wechat_auto': self.entry_b_wechat_auto.text().strip(),
            'b_wechat_override': self.entry_b_wechat_override.text().strip(),
            'b_alipay_add': self.entry_b_alipay_add.text().strip(),
            'b_alipay_override': self.entry_b_alipay_override.text().strip(),
            'a_revenue': self.entry_a_revenue.text().strip(), 'b_revenue': self.entry_b_revenue.text().strip(),
            'student_takeout': self.entry_student_takeout.text().strip(),
            'a_takeout': self.entry_a_takeout.text().strip(), 'b_takeout': self.entry_b_takeout.text().strip(),
            'new_customers': self.entry_new_customers.text().strip(),
            'total_customers': self.entry_total_customers.text().strip(),
            'food': self.entry_food_detail.text().strip(),
            'spice': self.entry_spice_detail.text().strip(),
            'other': self.entry_other_detail.text().strip(),
            'note': self.entry_daily_note.text().strip()
        }

    def get_fixed_ui_state(self):
        return {
            'month': f"{self.fixed_year_combo.currentText()}-{self.fixed_month_combo.currentText()}",
            'rent': self.fixed_rent.text().strip(),
            'note': self.fixed_note.text().strip(),
            'actual_water': self.fixed_actual_water.text().strip(),
            'actual_electric': self.fixed_actual_electric.text().strip(),
            'expected_water': self.fixed_expected_water.text().strip(),
            'expected_electric': self.fixed_expected_electric.text().strip(),
            'expected_gas': self.fixed_expected_gas.text().strip(),
        }

    # === 满血版：精准脏数据检测 ===
    def has_unsaved_changes(self):
        curr_daily = self.get_daily_ui_state()
        daily_dirty = False
        daily_content_keys = ['rev', 'fees', 'a_cash', 'b_cash', 'a_wechat_add', 'a_wechat_override', 'a_alipay_add', 'a_alipay_override', 'b_wechat_add', 'b_wechat_override', 'b_alipay_add', 'b_alipay_override', 'student_takeout', 'a_takeout', 'b_takeout', 'new_customers', 'total_customers', 'food', 'spice', 'other', 'note']

        if any(curr_daily[k] != self._snapshot_daily.get(k, "") for k in daily_content_keys):
            daily_dirty = True
        elif curr_daily['date'] != self._snapshot_daily.get('date', ""):
            if any(curr_daily[k] != "" for k in daily_content_keys):
                daily_dirty = True

        curr_fixed = self.get_fixed_ui_state()
        fixed_dirty = any(
            curr_fixed[key] != self._snapshot_fixed.get(key, "")
            for key in ('actual_water', 'expected_water', 'actual_electric', 'expected_electric', 'expected_gas')
        )

        return daily_dirty, fixed_dirty

    def daily_content_dirty(self):
        curr_daily = self.get_daily_ui_state()
        return any(
            curr_daily[k] != self._snapshot_daily.get(k, "")
            for k in ['rev', 'fees', 'a_cash', 'b_cash', 'a_wechat_add', 'a_wechat_override', 'a_alipay_add', 'a_alipay_override', 'b_wechat_add', 'b_wechat_override', 'b_alipay_add', 'b_alipay_override', 'student_takeout', 'a_takeout', 'b_takeout', 'new_customers', 'total_customers', 'food', 'spice', 'other', 'note']
        )

    def fixed_actual_content_dirty(self):
        curr_fixed = self.get_fixed_ui_state()
        return any(
            curr_fixed[key] != self._snapshot_fixed.get(key, "")
            for key in ('actual_water', 'expected_water', 'actual_electric', 'expected_electric', 'expected_gas')
        )

    def _activate_user_excel_for_date(self, date_value, for_save=False):
        """Route a cross-year edit to its own annual user Excel before reading it."""
        year = date_value.year() if isinstance(date_value, QDate) else int(str(date_value)[:4])
        if ACTIVE_USER_EXCEL_YEAR == year:
            return True
        window = self.window()
        if hasattr(window, 'ensure_user_excel_year'):
            return bool(window.ensure_user_excel_year(
                year,
                self,
                allow_current_ledger_date_change=not for_save,
                ignore_current_ledger_unsaved=for_save,
            ))
        try:
            ensure_user_excel_for_year(year)
            return True
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.warning(self, "无法切换年度用户 Excel", str(exc))
            return False

    def set_entry_date_safely(self, target_date):
        if not target_date.isValid():
            return False
        if not self.confirm_discard_daily_changes():
            return False
        if not self._activate_user_excel_for_date(target_date):
            return False
        self.entry_date.blockSignals(True)
        self.entry_date.setDate(target_date)
        self.entry_date.blockSignals(False)
        self.sync_all_dates(source='entry')
        self.auto_load_daily_record()
        return True

    def on_entry_date_changed(self):
        if self._is_syncing_ledger_dates:
            return
        if self.daily_content_dirty():
            ans = QMessageBox.warning(
                self, " 未保存提示",
                "检测到【当日流水】有尚未保存的修改。\n\n"
                "如果切换日期，这些修改将会丢失。\n您确定要放弃修改并切换吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans == QMessageBox.No:
                self.entry_date.blockSignals(True)
                self.entry_date.setDate(QDate.fromString(self._snapshot_daily.get('date', ""), "yyyy-MM-dd"))
                self.entry_date.blockSignals(False)
                return
        if not self._activate_user_excel_for_date(self.entry_date.date()):
            self.entry_date.blockSignals(True)
            self.entry_date.setDate(QDate.fromString(self._snapshot_daily.get('date', ''), "yyyy-MM-dd"))
            self.entry_date.blockSignals(False)
            return
        self.sync_all_dates(source='entry')
        self.auto_load_daily_record()

    def confirm_discard_daily_changes(self):
        if not self.daily_content_dirty():
            return True
        ans = QMessageBox.warning(
            self, " 未保存提示",
            "检测到【当日流水】有尚未保存的修改。\n\n"
            "如果切换日期，这些修改将会丢失。\n您确定要放弃修改并切换吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return ans == QMessageBox.Yes

    @staticmethod
    def _money_text(value):
        if not money_value_was_entered(value):
            return ''
        try:
            return f"{decimal_number(value):g}"
        except (TypeError, ValueError):
            return str(value).strip()


    def sync_revenue_breakdown(self):
        if self._loading_daily:
            return
        editable = [
            self.entry_a_cash, self.entry_b_cash, self.entry_a_wechat_add, self.entry_a_wechat_override,
            self.entry_a_alipay_add, self.entry_a_alipay_override, self.entry_b_wechat_add,
            self.entry_b_wechat_override, self.entry_b_alipay_add, self.entry_b_alipay_override,
            self.entry_student_takeout, self.entry_a_takeout, self.entry_b_takeout,
        ]
        if not any(widget.text().strip() for widget in editable):
            return
        def value(widget):
            try:
                return money_amount(widget.text()) if widget.text().strip() else 0
            except ValueError:
                return 0
        def effective_wechat(add_widget, auto_widget, override_widget):
            if override_widget.text().strip():
                return value(override_widget)
            if auto_widget.text().strip():
                return value(auto_widget) + value(add_widget)
            return value(add_widget)
        def effective_manual(add_widget, override_widget):
            return value(override_widget) if override_widget.text().strip() else value(add_widget)
        cash_a, cash_b = value(self.entry_a_cash), value(self.entry_b_cash)
        a_wechat = effective_wechat(self.entry_a_wechat_add, self.entry_a_wechat_auto, self.entry_a_wechat_override)
        a_alipay = effective_manual(self.entry_a_alipay_add, self.entry_a_alipay_override)
        b_wechat = effective_wechat(self.entry_b_wechat_add, self.entry_b_wechat_auto, self.entry_b_wechat_override)
        b_alipay = effective_manual(self.entry_b_alipay_add, self.entry_b_alipay_override)
        student_takeout = value(self.entry_student_takeout)
        a_takeout = value(self.entry_a_takeout)
        b_takeout = value(self.entry_b_takeout)
        a_revenue = cash_a + a_wechat + a_alipay + a_takeout
        b_revenue = cash_b + b_wechat + b_alipay + b_takeout
        self.entry_total_cash.setText(f"{cash_a + cash_b:.2f}")
        self.entry_total_online.setText(f"{a_wechat + a_alipay + b_wechat + b_alipay + student_takeout + a_takeout + b_takeout:.2f}")
        self.entry_a_revenue.setText(f"{a_revenue:.2f}")
        self.entry_b_revenue.setText(f"{b_revenue:.2f}")
        self.entry_revenue.setText(f"{a_revenue + b_revenue + student_takeout:.2f}")

    def auto_load_daily_record(self):
        day_str = self.entry_date.date().toString("yyyy-MM-dd")
        df = load_daily()
        record = df[df['日期'] == day_str]
        payment_map = {
            self.entry_total_cash: '总现金', self.entry_a_cash: 'A店现金', self.entry_b_cash: 'B店现金',
            self.entry_total_online: '总线上',
            self.entry_a_wechat_add: 'A店微信增加', self.entry_a_wechat_auto: 'A店微信自动', self.entry_a_wechat_override: 'A店微信覆盖',
            self.entry_a_alipay_add: 'A店支付宝增加', self.entry_a_alipay_override: 'A店支付宝覆盖',
            self.entry_b_wechat_add: 'B店微信增加', self.entry_b_wechat_auto: 'B店微信自动', self.entry_b_wechat_override: 'B店微信覆盖',
            self.entry_b_alipay_add: 'B店支付宝增加', self.entry_b_alipay_override: 'B店支付宝覆盖',
            self.entry_a_revenue: 'A店收入', self.entry_b_revenue: 'B店收入',
            self.entry_student_takeout: '学生外卖', self.entry_a_takeout: 'A店外卖', self.entry_b_takeout: 'B店外卖',
        }
        self._loading_daily = True
        try:
            if not record.empty:
                record = record.iloc[-1]
                self._loaded_daily_record = record.to_dict()
                legacy_total = record.get('总金额', '')
                saved_revenue = record.get('收益', '')
                if abs(money_amount(saved_revenue)) < Decimal('1e-9') and abs(money_amount(legacy_total)) > Decimal('1e-9'):
                    saved_revenue = legacy_total
                self.entry_revenue.setText(self._money_text(saved_revenue))
                self.entry_fees.setText(self._money_text(record.get('手续费', '')))
                self.entry_available_balance.setText(self._money_text(record.get('可用余额', '')))
                self.entry_shareholder_loan.setText(self._money_text(record.get('向股东借款', '')))
                for widget, column in payment_map.items():
                    widget.setText(self._money_text(record.get(column, '')))
                self.entry_new_customers.setText(format_customer_count(record.get('新客人数量', '')))
                self.entry_total_customers.setText(format_customer_count(record.get('总客人数', '')))
                self.entry_food_detail.setText(str(record.get('食材明细', '')).strip())
                self.entry_spice_detail.setText(str(record.get('佐料明细', '')).strip())
                self.entry_other_detail.setText(str(record.get('其他明细', '')).strip() or (
                    f"旧版其他 {money_amount(record.get('其他', 0))}" if money_amount(record.get('其他', 0)) > 0 else ""))
                self.entry_daily_note.setText(str(record.get('当日备注', '')).strip())
            else:
                self._loaded_daily_record = {}
                for widget in [
                    self.entry_revenue, self.entry_fees, self.entry_available_balance, self.entry_shareholder_loan,
                    *payment_map.keys(), self.entry_new_customers, self.entry_total_customers,
                    self.entry_food_detail, self.entry_spice_detail, self.entry_other_detail, self.entry_daily_note,
                ]:
                    widget.clear()
        finally:
            self._loading_daily = False
        self.sync_revenue_breakdown()
        self._snapshot_daily = self.get_daily_ui_state()
        self._refresh_entry_window_cache(force=True)
        self._refresh_entry_countdown()

    def sync_wechat_bill(self, force=False):
        day_str = self.entry_date.date().toString("yyyy-MM-dd")
        if force and self.entry_date.date() >= QDate.currentDate():
            QMessageBox.warning(self, "无法更新", "微信交易账单只能更新已经结束的历史日期；当天账单需次日上午10点后获取。")
            return
        if self.daily_content_dirty():
            answer = QMessageBox.question(
                self, "未保存修改",
                "当前流水有未保存修改。更新微信账单会重新加载云端数据，是否放弃这些修改并继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if force:
            answer = QMessageBox.warning(
                self, "确认强制更新",
                f"强制更新会重新读取 {day_str} 的微信官方账单，并清除该日已有的微信手动覆盖金额。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        worker = EMBEDDED_SYNC_INSTANCE
        if worker is None:
            QMessageBox.warning(self, "无法更新", "当前未连接网站服务，无法调用微信支付接口。")
            return
        self.btn_sync_wechat.setEnabled(False)
        self.btn_force_sync_wechat.setEnabled(False)
        month_str = self.entry_date.date().toString("yyyy-MM")
        self.lbl_status.setText("⏳ 正在强制读取微信官方账单……" if force else f"⏳ 正在更新 {month_str} 尚未填写的收入……")
        result_holder = {'done': False, 'result': None, 'error': None}

        def task():
            try:
                result_holder['result'] = (
                    worker.sync_wechat_bill(day_str, force=True)
                    if force else worker.sync_missing_wechat_month(month_str)
                )
            except Exception as exc:
                result_holder['error'] = exc
            finally:
                result_holder['done'] = True

        threading.Thread(target=task, name='desktop-wechat-sync', daemon=True).start()

        def poll():
            if not result_holder['done']:
                QTimer.singleShot(120, poll)
                return
            self.btn_sync_wechat.setEnabled(True)
            self.btn_force_sync_wechat.setEnabled(True)
            if result_holder['error'] is not None:
                message = str(result_holder['error'])
                self.lbl_status.setText(" 微信账单更新失败")
                QMessageBox.warning(self, "微信账单更新失败", message)
                return
            result = result_holder['result'] or {}
            if not force:
                self._refresh_after_wechat_sync()
                self.lbl_status.setText(
                    f" {month_str} 未填写收入更新完成：处理 {result.get('changed_days', 0)} 天；"
                    f"已保护 {result.get('skipped', 0)} 个已有收入店铺。"
                )
                return
            stores = result.get('stores') or {}
            skipped_stores = {str(item).split('(', 1)[0] for item in (result.get('skipped_stores') or [])}
            self._loading_daily = True
            try:
                if isinstance(stores.get('A'), dict):
                    amount_a = money_amount(stores['A'].get('amount', 0))
                    # API 返回 0 时服务端会保护原有手工值；不要在桌面端
                    # 先把自动值/手工覆盖清掉，避免刷新前出现短暂的错误显示。
                    if amount_a > 0 and 'A店' not in skipped_stores:
                        self.entry_a_wechat_auto.setText(f"{amount_a:.2f}")
                    if amount_a > 0 and 'A店' not in skipped_stores and (force or result.get('source') == 'wechat_bill_auto'):
                        self.entry_a_wechat_override.clear()
                if isinstance(stores.get('B'), dict):
                    amount_b = money_amount(stores['B'].get('amount', 0))
                    if amount_b > 0 and 'B店' not in skipped_stores:
                        self.entry_b_wechat_auto.setText(f"{amount_b:.2f}")
                    if amount_b > 0 and 'B店' not in skipped_stores and (force or result.get('source') == 'wechat_bill_auto'):
                        self.entry_b_wechat_override.clear()
            finally:
                self._loading_daily = False
            self.sync_revenue_breakdown()
            self._snapshot_daily = self.get_daily_ui_state()
            worker.wake()
            parts = []
            if isinstance(stores.get('A'), dict):
                parts.append(f"{store_display_name('A')}微信 {money_amount(stores['A'].get('amount', 0)):.2f} 元")
            if isinstance(stores.get('B'), dict):
                parts.append(f"{store_display_name('B')}微信 {money_amount(stores['B'].get('amount', 0)):.2f} 元")
            prefix = " 微信账单已强制更新" if force else " 微信账单已更新"
            self.lbl_status.setText(prefix + ("：" + "；".join(parts) if parts else ""))
            QTimer.singleShot(1200, self._refresh_after_wechat_sync)
            QTimer.singleShot(3500, self._refresh_after_wechat_sync)

        poll()

    def _refresh_after_wechat_sync(self):
        try:
            self.auto_load_daily_record()
            self.refresh_table()
            window = self.window()
            if hasattr(window, 'dashboard'):
                window.dashboard.refresh_all()
            if hasattr(window, 'more_stats'):
                window.more_stats.refresh()
        except Exception:
            pass

    def sync_all_dates(self, source):
        if self._is_syncing_ledger_dates: return
        if source == 'fixed' and self.fixed_actual_content_dirty():
            ans = QMessageBox.warning(
                self,
                " 未保存提示",
                "实际／预计水电煤气费尚未保存。\n\n确定放弃修改并切换月份吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans == QMessageBox.No:
                old_month = self._snapshot_fixed.get('month', '')
                if re.fullmatch(r'\d{4}-\d{2}', old_month):
                    old_year, old_month_number = old_month.split('-')
                    self.fixed_year_combo.blockSignals(True)
                    self.fixed_month_combo.blockSignals(True)
                    self.fixed_year_combo.setCurrentText(old_year)
                    self.fixed_month_combo.setCurrentText(old_month_number)
                    self.fixed_year_combo.blockSignals(False)
                    self.fixed_month_combo.blockSignals(False)
                return
        self._is_syncing_ledger_dates = True
        try:
            if source == 'entry':
                y, m = self.entry_date.date().year(), self.entry_date.date().month()
            elif source == 'fixed':
                y, m = int(self.fixed_year_combo.currentText()), int(self.fixed_month_combo.currentText())
            elif source == 'hist':
                y, m = int(self.hist_year_combo.currentText()), int(self.hist_month_combo.currentText())

            if not self._activate_user_excel_for_date(QDate(y, m, 1)):
                return

            if source != 'fixed':
                self.fixed_year_combo.setCurrentText(str(y))
                self.fixed_month_combo.setCurrentText(f"{m:02d}")
            if source != 'entry' and (self.entry_date.date().year() != y or self.entry_date.date().month() != m):
                target_date = QDate(y, m, 1)
                should_switch_entry = True
                if self.daily_content_dirty():
                    ans = QMessageBox.warning(
                        self, " 未保存提示",
                        "检测到【当日流水】有尚未保存的修改。\n\n"
                        f"是否放弃修改，并把录入日期切换到 {target_date.toString('yyyy-MM-dd')}？\n"
                        "选择 No 会只切换当前月份筛选，不影响正在编辑的当日流水。",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                    )
                    should_switch_entry = ans == QMessageBox.Yes
                if should_switch_entry:
                    self.entry_date.blockSignals(True)
                    self.entry_date.setDate(target_date)
                    self.entry_date.blockSignals(False)
                    self.auto_load_daily_record()
            if source != 'hist':
                self.hist_year_combo.setCurrentText(str(y))
                self.hist_month_combo.setCurrentText(f"{m:02d}")

            if source in ('hist', 'fixed', 'entry'):
                self.refresh_table()
                self.load_fixed_cost_for_month()
        finally:
            self._is_syncing_ledger_dates = False

    def open_item_manager(self, entry_widget, category):
        dlg = ItemSelectDialog(entry_widget.text(), category, self)
        if dlg.exec() == QDialog.Accepted: entry_widget.setText(dlg.selected_items_str)

    def _parse_float(self, text, field_name, derived=False):
        if not str(text).strip(): return 0
        try:
            return money_amount(text) if derived else money_input(text)
        except ValueError as exc:
            QMessageBox.warning(self, "金额错误", f"【{field_name}】{exc}")
            return None

    def _parse_optional_money(self, text, field_name):
        text = str(text).strip()
        if not text:
            return ''
        return self._parse_float(text, field_name)

    def _parse_customer_count(self, text, field_name):
        text = str(text).strip()
        if not text:
            return 0
        if not re.fullmatch(r'\d+', text):
            QMessageBox.warning(self, "输入类型错误", f"【{field_name}】只能填写整数，不能输入小数。")
            return None
        return int(text)

    def _parse_mixed_input(self, raw_str, field_name):
        raw_str = raw_str.strip()
        if not raw_str: return "", 0
        try:
            structured = exact_json_loads(raw_str)
        except (ValueError, TypeError):
            structured = None
        if isinstance(structured, list):
            total_cost = 0
            for item in _inventory_detail_items(structured):
                if not item['name']:
                    QMessageBox.warning(self, '名称错误', f'【{field_name}】有未填写名称的项目。')
                    return None, None
                amount = money_amount(item['total']) if money_value_was_entered(item['total']) else money_amount(item['quantity'] * unit_price_value(item['unit_price']))
                if not (0 <= amount < float('inf')):
                    QMessageBox.warning(self, '金额错误', f'【{field_name}】金额必须是有限的非负数。')
                    return None, None
                total_cost += amount
            # Preserve unedited web JSON byte-for-byte so changing only a
            # customer count cannot restart or hit an unrelated expense clock.
            return raw_str, total_cost
        parsed_names, total_cost = [], 0
        # 支持带单位的格式: "牛肉 5斤 50" (名称 数量+单位 总价)
        unit_pattern = get_unit_pattern()
        unit_regex = re.compile(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + unit_pattern + r'?\s+(\d+(?:\.\d+)?)$')
        for item in re.split(r'[,，]', raw_str):
            item = item.strip()
            if not item: continue
            item, note = split_item_note(item)

            # 1) 先尝试匹配带单位的格式
            unit_match = unit_regex.match(item)
            if unit_match:
                name = unit_match.group(1).strip()
                quantity = unit_match.group(2)
                unit = unit_match.group(3) or ''
                cost = money_amount(unit_match.group(4))
                if not name or name.isdigit():
                    QMessageBox.warning(self, "名称错误", f"【{field_name}】中的项 '{item}' 名称无效！")
                    return None, None
                # 显示格式: "牛肉 5斤 50"
                display = join_item_note(f"{name} {unit_join(quantity, unit)} {cost:g}", note)
                parsed_names.append(display)
                total_cost += cost
                continue

            # 2) 名称后面的金额可以带空格，也可以直接紧贴名称，例如
            #    “采购办公用品100”。保存时统一为“名称 金额”，让历史表、
            #    现金余额表和云端同步都使用同一个明确的金额字段。
            named_amount = parse_named_amount(item)
            if not named_amount:
                QMessageBox.warning(self, "格式错误",
                                    f"【{field_name}】中的项 '{item}' 格式不对！\n请用 '名称金额' 或 '名称 金额' 格式（如 '采购办公用品100'、'牛肉 400'），\n或带单位格式（如 '牛肉 5斤 50'）。")
                return None, None
            name, cost = named_amount
            if not name or name.isdigit():
                QMessageBox.warning(self, "名称错误", f"【{field_name}】中的项 '{item}' 菜名无效！")
                return None, None
            if re.search(r'\d\s+[^\d]', name):
                QMessageBox.warning(self, "格式错误",
                                    f"【{field_name}】中的 '{item}' 异常！\n系统检测到多个项目粘连，请用【逗号】隔开。")
                return None, None
            parsed_names.append(join_item_note(f"{name} {cost:g}", note))
            total_cost += cost
        return ", ".join(parsed_names), total_cost

    def get_form_data(self):
        # 渠道输入的 textChanged 信号已经实时维护派生总额。这里不能再无条件
        # 按隐藏的旧版/API 字段重算，否则用户只填写“总金额”时，保存会被历史
        # 渠道值覆盖；这与网页端“总金额可单独填写”的行为不一致。
        payment_widgets = [
            ('A店现金', self.entry_a_cash), ('B店现金', self.entry_b_cash),
            ('A店微信增加', self.entry_a_wechat_add), ('A店微信自动', self.entry_a_wechat_auto), ('A店微信覆盖', self.entry_a_wechat_override),
            ('A店支付宝增加', self.entry_a_alipay_add), ('A店支付宝覆盖', self.entry_a_alipay_override),
            ('B店微信增加', self.entry_b_wechat_add), ('B店微信自动', self.entry_b_wechat_auto), ('B店微信覆盖', self.entry_b_wechat_override),
            ('B店支付宝增加', self.entry_b_alipay_add), ('B店支付宝覆盖', self.entry_b_alipay_override),
            ('学生外卖', self.entry_student_takeout), ('A店外卖', self.entry_a_takeout), ('B店外卖', self.entry_b_takeout),
        ]
        payments = {}
        for field, widget in payment_widgets:
            value = self._parse_optional_money(widget.text(), field)
            if value is None:
                return None
            payments[field] = value
        revenue = self._parse_float(self.entry_revenue.text(), "总金额", derived_money_field("总金额", payments))
        fees = self._parse_optional_money(self.entry_fees.text(), "手续费／抽成")
        total_cash = self._parse_float(self.entry_total_cash.text(), "总现金", derived_money_field("总现金", payments))
        total_online = self._parse_float(self.entry_total_online.text(), "总线上", derived_money_field("总线上", payments))
        a_revenue = self._parse_float(self.entry_a_revenue.text(), "A店收入", derived_money_field("A店收入", payments))
        b_revenue = self._parse_float(self.entry_b_revenue.text(), "B店收入", derived_money_field("B店收入", payments))
        if None in (revenue, fees, total_cash, total_online, a_revenue, b_revenue):
            return None
        new_customers = self._parse_customer_count(self.entry_new_customers.text(), "新客人数量")
        if new_customers is None: return None
        total_customers = self._parse_customer_count(self.entry_total_customers.text(), "总客人数")
        if total_customers is None: return None
        if new_customers < 0 or total_customers < 0:
            QMessageBox.warning(self, "输入错误", "【新客人数量】和【总客人数】不能为负数。")
            return None
        if self.entry_new_customers.text().strip() and self.entry_total_customers.text().strip() and new_customers > total_customers:
            QMessageBox.warning(self, "输入错误", "【新客人数量】不能大于【总客人数】。")
            return None
        if not self.entry_new_customers.text().strip():
            new_customers = ''
        if not self.entry_total_customers.text().strip():
            total_customers = ''
        food_detail, food_cost = self._parse_mixed_input(self.entry_food_detail.text(), "食材明细")
        if food_detail is None: return None
        spice_detail, spice_cost = self._parse_mixed_input(self.entry_spice_detail.text(), "佐料明细")
        if spice_detail is None: return None
        other_detail, other_cost = self._parse_mixed_input(self.entry_other_detail.text(), "其它明细")
        if other_detail is None: return None

        return {
            '日期': self.entry_date.date().toString("yyyy-MM-dd"),
            '收益': revenue, '总现金': total_cash, '总线上': total_online,
            '手续费': fees,
            **payments, 'A店收入': a_revenue, 'B店收入': b_revenue,
            '新客人数量': new_customers, '总客人数': total_customers,
            '食材成本': food_cost, '食材明细': food_detail, '佐料成本': spice_cost, '佐料明细': spice_detail,
            '水电': 0, '其他': other_cost, '其他明细': other_detail,
            '当日备注': self.entry_daily_note.text().strip()
        }

    def save_record(self, mode="add"):
        current_ui = self.get_daily_ui_state()
        changed = {key for key, value in current_ui.items() if value != self._snapshot_daily.get(key)}
        customer_only = mode == 'overwrite' and bool(self._loaded_daily_record) and bool(changed) and changed <= {'new_customers', 'total_customers'}
        if customer_only:
            new_text = self.entry_new_customers.text().strip()
            total_text = self.entry_total_customers.text().strip()
            new_count = self._parse_customer_count(new_text, '新客人数量')
            total_count = self._parse_customer_count(total_text, '总客人数')
            if new_count is None or total_count is None:
                return
            if new_text and total_text and new_count > total_count:
                QMessageBox.warning(self, '输入错误', '【新客人数量】不能大于【总客人数】。')
                return
            # Saving counts must not rewrite an old expense, reformat a web
            # JSON detail, or change a historical revenue aggregate.
            data = dict(self._loaded_daily_record)
            data.update({'日期': self.entry_date.date().toString('yyyy-MM-dd'),
                         '新客人数量': new_count if new_text else '',
                         '总客人数': total_count if total_text else ''})
        else:
            data = self.get_form_data()
        if data is None:
            return
        if not self._activate_user_excel_for_date(QDate.fromString(data['日期'], 'yyyy-MM-dd'), for_save=True):
            return
        df = load_daily()
        existing_idx = df[df['日期'] == data['日期']].index
        old_record = (
            df.loc[existing_idx[0]].to_dict() if len(existing_idx) > 0 else {}
        )
        raw_revenue_fields = [
            'A店现金', 'B店现金',
            'A店微信增加', 'A店微信自动', 'A店微信覆盖', 'A店支付宝增加', 'A店支付宝覆盖',
            'B店微信增加', 'B店微信自动', 'B店微信覆盖', 'B店支付宝增加', 'B店支付宝覆盖',
            '学生外卖', 'A店外卖', 'B店外卖',
        ]
        additive_payment_fields = {
            'A店现金', 'B店现金', 'A店微信增加', 'A店支付宝增加',
            'B店微信增加', 'B店支付宝增加', '学生外卖', 'A店外卖', 'B店外卖',
        }
        override_payment_fields = {
            'A店微信覆盖', 'A店支付宝覆盖', 'B店微信覆盖', 'B店支付宝覆盖',
        }

        if len(existing_idx) > 0:
            idx = existing_idx[0]
            if mode == "add":
                if QMessageBox.question(
                    self, "增加确认", f"要在 {data['日期']} 已有记录上累加填写金额吗？"
                ) != QMessageBox.Yes:
                    return
                old_record = df.loc[idx].to_dict()
                old_has_breakdown = any(money_value_was_entered(old_record.get(field, '')) for field in raw_revenue_fields)
                new_has_breakdown = any(money_value_was_entered(data.get(field, '')) for field in raw_revenue_fields)
                if money_amount(old_record.get('收益', 0)) and not old_has_breakdown and new_has_breakdown:
                    QMessageBox.warning(
                        self,
                        "旧版收入无法自动拆店",
                        "这一天只有旧版总收入，没有 A/B 店及支付渠道明细。为了避免错误分配，不能使用“增加”合并新支付明细；请先用“覆盖”完整保存这一天。",
                    )
                    return

                for field in additive_payment_fields:
                    df.loc[idx, field] = safe_float(old_record.get(field, 0)) + safe_float(data.get(field, 0))
                for field in override_payment_fields:
                    if money_value_was_entered(data.get(field, '')):
                        df.loc[idx, field] = data[field]
                updated = recalculate_revenue_fields(df.loc[idx].to_dict())
                for field in ['收益', '总现金', '总线上', 'A店收入', 'B店收入']:
                    df.loc[idx, field] = updated[field]

                for col in ['新客人数量', '总客人数']:
                    if col not in df.columns:
                        df[col] = 0
                    if money_value_was_entered(data[col]):
                        df.loc[idx, col] = safe_float(df.loc[idx, col]) + safe_float(data[col])
                for prefix in ['食材', '佐料', '其他']:
                    df.loc[idx, f'{prefix}明细'] = ", ".join(
                        filter(None, [str(df.loc[idx, f'{prefix}明细']).strip(), data[f'{prefix}明细']])
                    )
                    cost_col = '其他' if prefix == '其他' else f'{prefix}成本'
                    df.loc[idx, cost_col] = safe_float(df.loc[idx, cost_col]) + data[cost_col]

                old_note = str(df.loc[idx, '当日备注']).strip()
                new_note = data['当日备注']
                if old_note and new_note:
                    df.loc[idx, '当日备注'] = f"{old_note}；{new_note}"
                elif new_note:
                    df.loc[idx, '当日备注'] = new_note

            elif mode == "overwrite":
                if QMessageBox.question(
                    self, "覆盖确认", f"确定完全覆盖清空 {data['日期']} 的记录吗？",
                    QMessageBox.Yes | QMessageBox.No,
                ) != QMessageBox.Yes:
                    return
                for key, value in data.items():
                    df.loc[idx, key] = value
        else:
            if QMessageBox.question(
                self, "新建确认", f"{data['日期']} 尚无记录，按新记录保存？"
            ) != QMessageBox.Yes:
                return
            df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)

        # Validate the fully merged row before it reaches the internal source
        # of truth. Food/spice/other and all nine income slots have independent
        # clocks. A scheduled editor grant bypasses entry-only timing rules.
        new_record = (
            df.loc[existing_idx[0]].to_dict()
            if len(existing_idx) > 0
            else data
        )
        timing_fields_changed = _entry_timing_relevant_change(old_record, new_record)
        timing_windows = None
        effective_role = _desktop_effective_role(data['日期']) or self._role
        if timing_fields_changed and effective_role == 'entry':
            timing_windows = _load_entry_windows()
            _timing_state, timing_error = _entry_validate_and_update_windows(
                timing_windows,
                data['日期'],
                old_record,
                new_record,
                mode='overwrite',
                enforce=True,
            )
            if timing_error and effective_role == 'entry':
                QMessageBox.warning(self, '录入时间窗限制', timing_error)
                return

        save_daily(df)
        if timing_windows is not None:
            try:
                _entry_save_windows(timing_windows)
                self._entry_windows_cache = timing_windows
                self._entry_windows_cache_loaded_at = time.monotonic()
            except Exception as exc:
                # The daily record is already committed.  Keep the user-facing
                # save successful but make a failed timing sync explicit.
                self.lbl_status.setText(f' 已保存；时间窗同步失败：{exc}')
        self.refresh_table()
        self.auto_load_daily_record()
        if not self.lbl_status.text().startswith(' 已保存；'):
            _purchases, pending = _inventory_purchase_entries()
            incomplete = [item for item in pending if item['date'] == data['日期']]
            self.lbl_status.setText((' 已保存；买食材明细已自动入库。' if any(item['date'] == data['日期'] for item in _purchases) else ' 已保存') if not incomplete else f' 已保存；{len(incomplete)} 项食材缺少数量或单位，补齐后自动入库。')
        self._refresh_entry_countdown()

    def reset_form(self):
        """撤销未保存的所有修改，回到上次加载/保存时的状态"""
        daily_dirty, _ = self.has_unsaved_changes()
        if not daily_dirty:
            QMessageBox.information(self, "提示", "没有需要撤销的修改。")
            return
        if QMessageBox.question(self, "确认撤销", 
                "确定要撤销所有未保存的修改吗？\n所有更改将恢复到上次保存/加载时的状态。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.auto_load_daily_record()
            self.lbl_status.setText("↩ 已撤销")

    def open_fixed_expense_editor(self):
        month_str = f"{self.fixed_year_combo.currentText()}-{self.fixed_month_combo.currentText()}"
        try:
            year, month = [int(part) for part in month_str.split('-')]
        except ValueError:
            QMessageBox.warning(self, "月份错误", f"无效的月份：{month_str}")
            return
        if not self._activate_user_excel_for_date(QDate(year, month, 1)):
            return
        dialog = FixedCostEditDialog(
            month_str, self,
            changed_callback=lambda: (
                self.load_fixed_cost_for_month(),
                self.refresh_table()
            )
        )
        dialog.exec()

    def load_fixed_cost_for_month(self):
        m_str = f"{self.fixed_year_combo.currentText()}-{self.fixed_month_combo.currentText()}"
        fixed_df = normalize_sheet_frame('monthly_fixed', load_monthly_fixed())
        row = fixed_df[fixed_df['月份'] == m_str]
        if not row.empty:
            record = row.iloc[0]
            self.fixed_rent.setText(str(record.get('房租总额', '')).strip())
            self.fixed_note.setText(str(record.get('月度备注', '')).strip())
            values = [
                (self.fixed_actual_water, record.get('实际使用水费', '')),
                (self.fixed_expected_water, record.get('预计水费', '')),
                (self.fixed_actual_electric, record.get('实际使用电费', '')),
                (self.fixed_expected_electric, record.get('预计电费', '')),
                (self.fixed_expected_gas, record.get('预计煤气费', '')),
            ]
            for widget, value in values:
                widget.setText(f"{safe_float(value):g}" if money_value_was_entered(value) else "")
        else:
            self.fixed_rent.clear()
            self.fixed_note.clear()
            for widget in (
                self.fixed_actual_water, self.fixed_expected_water,
                self.fixed_actual_electric, self.fixed_expected_electric,
                self.fixed_expected_gas,
            ):
                widget.clear()

        try:
            year, month = (int(part) for part in m_str.split('-'))
        except ValueError:
            year, month = QDate.currentDate().year(), QDate.currentDate().month()
        fixed = get_monthly_fixed_breakdown(year, month, fixed_df)
        water_source = (
            "实际使用" if fixed['实际使用水费'] is not None else
            "预计" if fixed['预计水费'] is not None else "支出"
        )
        electric_source = (
            "实际使用" if fixed['实际使用电费'] is not None else
            "预计" if fixed['预计电费'] is not None else "支出"
        )
        gas_source = "预计" if fixed['预计煤气费'] is not None else "支出"
        self.lbl_fixed_summary.setText(
            f"本月实际支出合计 {fixed['固定支出合计']:.2f} 元  |  "
            f"成本计算：水费 {fixed['计入成本水费']:.2f}（{water_source}）  |  "
            f"电费 {fixed['计入成本电费']:.2f}（{electric_source}）  |  "
            f"煤气费 {fixed['计入成本煤气费']:.2f}（{gas_source}）  |  "
            f"本月固定成本口径合计 {fixed['固定成本合计']:.2f} 元"
        )
        self._snapshot_fixed = self.get_fixed_ui_state()

    @staticmethod
    def _optional_actual_money(text, field_name):
        text = str(text).strip()
        if not text:
            return ''
        try:
            value = money_input(text)
        except ValueError:
            QMessageBox.warning(None, "输入类型错误", f"【{field_name}】必须是纯数字，或留空。")
            return None
        if value < 0 or value != value or value == float('inf'):
            QMessageBox.warning(None, "输入错误", f"【{field_name}】不能是负数或无效数字。")
            return None
        return value

    def save_actual_utility_costs(self):
        fields = [
            ('实际使用水费', self.fixed_actual_water),
            ('预计水费', self.fixed_expected_water),
            ('实际使用电费', self.fixed_actual_electric),
            ('预计电费', self.fixed_expected_electric),
            ('预计煤气费', self.fixed_expected_gas),
        ]
        parsed = {}
        for field_name, widget in fields:
            value = self._optional_actual_money(widget.text(), field_name)
            if value is None:
                return
            parsed[field_name] = value

        month_str = f"{self.fixed_year_combo.currentText()}-{self.fixed_month_combo.currentText()}"
        try:
            year, month = (int(part) for part in month_str.split('-'))
        except ValueError:
            QMessageBox.warning(self, "月份错误", f"无效的月份：{month_str}")
            return
        if not self._activate_user_excel_for_date(QDate(year, month, 1), for_save=True):
            return

        df = normalize_sheet_frame('monthly_fixed', load_monthly_fixed())
        existing = df[df['月份'] == month_str]
        if existing.empty:
            totals = fixed_expense_totals(month_str)
            mapped = {'水费', '电费', '煤气费', '人工', '房租及物业费', '其它'}
            custom_other = sum(value for category, value in totals.items() if category not in mapped)
            record = {
                '月份': month_str,
                '人工总额': totals.get('人工', 0),
                '房租总额': totals.get('房租及物业费', 0),
                '水费支出': totals.get('水费', 0),
                '电费支出': totals.get('电费', 0),
                '水电费': totals.get('水费', 0) + totals.get('电费', 0),
                **parsed,
                '煤气费': totals.get('煤气费', 0),
                '其它固定成本': totals.get('其它', 0) + custom_other,
                '月度备注': rent_property_note_from_expenses(month_str),
            }
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        else:
            idx = existing.index[0]
            for field_name, value in parsed.items():
                df.loc[idx, field_name] = value

        save_monthly_fixed(df)
        self.load_fixed_cost_for_month()
        self.refresh_table()
        window = self.window()
        if hasattr(window, 'dashboard'):
            window.dashboard.refresh_all()
        if hasattr(window, 'more_stats'):
            window.more_stats.refresh()
        QMessageBox.information(
            self,
            "保存成功",
            "实际／预计水电煤气费已保存。\n"
            "水费、电费：实际使用优先，其次预计，最后按实际支出；煤气费：预计优先，否则按实际支出。",
        )

    def refresh_table(self):
        df_daily, df_fixed = load_daily(), load_monthly_fixed()
        m_str = f"{self.hist_year_combo.currentText()}-{self.hist_month_combo.currentText()}"
        month_df = df_daily[df_daily['日期'].str.startswith(m_str)].copy()
        row_fixed = df_fixed[df_fixed['月份'] == m_str]

        if month_df.empty and row_fixed.empty:
            self.table.setRowCount(0)
            return

        month_df['日期_obj'] = pd.to_datetime(month_df['日期'])
        month_df = month_df.sort_values('日期_obj')

        self.table.clearSpans()
        self.table.setRowCount(len(month_df) + 1)

        try:
            summary_year, summary_month = (int(part) for part in m_str.split('-'))
        except ValueError:
            summary_year, summary_month = QDate.currentDate().year(), QDate.currentDate().month()
        fixed = get_monthly_fixed_breakdown(summary_year, summary_month, df_fixed)
        month_note = str(row_fixed.iloc[0].get('月度备注', '')).strip() if not row_fixed.empty else ""
        def utility_value_text(actual, expected, spent, *, gas=False):
            if not gas and actual is not None:
                return f"实际 {actual:g}"
            if expected is not None:
                return f"预计 {expected:g}"
            return f"支出 {spent:g}"

        water_cost_text = utility_value_text(
            fixed['实际使用水费'], fixed['预计水费'], fixed['水费支出']
        )
        electric_cost_text = utility_value_text(
            fixed['实际使用电费'], fixed['预计电费'], fixed['电费支出']
        )
        gas_cost_text = utility_value_text(
            None, fixed['预计煤气费'], fixed['煤气费'], gas=True
        )

        summary_text = (
            f" 【{m_str} 本月固定成本汇总】 人工: {fixed['人工']:g}  |  "
            f"房租及物业: {fixed['房租及物业']:g}  |  "
            f"水费: {water_cost_text}（支出 {fixed['水费支出']:g}）  |  "
            f"电费: {electric_cost_text}（支出 {fixed['电费支出']:g}）  |  "
            f"煤气费: {gas_cost_text}（支出 {fixed['煤气费']:g}）  |  其它: {fixed['其它固定成本']:g}"
        )
        if month_note:
            summary_text += f"\n 【月度备注】 {month_note}"

        summary_item = QTableWidgetItem(summary_text)
        summary_item.setBackground(QColor("#E3F2FD"))
        font = summary_item.font();
        font.setBold(True);
        summary_item.setFont(font)
        self.table.setItem(0, 0, summary_item)
        self.table.setSpan(0, 0, 1, self.table.columnCount())
        self.table.setRowHeight(0, 58)

        for i, (_, row) in enumerate(month_df.iterrows()):
            real_row = i + 1
            m_metrics = calc_day_metrics(row['日期'], df_daily, df_fixed)
            self.table.setItem(real_row, 0, QTableWidgetItem(str(row['日期'])))
            self.table.setItem(real_row, 1, QTableWidgetItem(f"{money_amount(row.get('收益', 0)):.2f}"))
            self.table.setItem(real_row, 2, QTableWidgetItem(f"{money_amount(row.get('A店收入', 0)):.2f}"))
            self.table.setItem(real_row, 3, QTableWidgetItem(f"{money_amount(row.get('B店收入', 0)):.2f}"))
            self.table.setItem(real_row, 4, QTableWidgetItem(f"{safe_float(row.get('新客人数量', 0)):g}"))
            self.table.setItem(real_row, 5, QTableWidgetItem(f"{safe_float(row.get('总客人数', 0)):g}"))
            self.table.setItem(real_row, 6, QTableWidgetItem(f"{money_amount(row.get('食材成本', 0)):.2f} 元"))
            self.table.setItem(real_row, 7, QTableWidgetItem(str(row.get('佐料明细', ''))))
            fixed_for_day = m_metrics['固定分摊'] if m_metrics else 0
            self.table.setItem(real_row, 8, QTableWidgetItem(f"{fixed_for_day:.2f}"))
            other_disp = str(row.get('其他明细', '')).strip() or (
                f"旧版其他 {money_amount(row.get('其他', 0))}" if money_amount(row.get('其他', 0)) > 0 else "")
            self.table.setItem(real_row, 9, QTableWidgetItem(other_disp))
            self.table.setItem(real_row, 10, QTableWidgetItem(str(row.get('当日备注', ''))))
            revenue = m_metrics['收益'] if m_metrics else 0
            gross = m_metrics['毛利'] if m_metrics else 0
            net = m_metrics['净利润'] if m_metrics else 0
            gross_rate = decimal_divide(gross, revenue) * 100 if revenue else 0
            net_rate = decimal_divide(net, revenue) * 100 if revenue else 0
            self.table.setItem(real_row, 11, QTableWidgetItem(f"{gross:.2f} ({gross_rate:.1f}%)"))
            self.table.setItem(real_row, 12, QTableWidgetItem(f"{net:.2f} ({net_rate:.1f}%)"))

    def open_month_history_dialog(self):
        """用更大字体显示当前月份历史，表格自身承担横向和纵向滚动。"""
        self.refresh_table()
        month_str = f"{self.hist_year_combo.currentText()}-{self.hist_month_combo.currentText()}"

        dialog = QDialog(self)
        dialog.setWindowTitle(f" {month_str} 历史记录（大字版）")
        dialog.resize(1320, 760)
        layout = QVBoxLayout(dialog)

        title = QLabel(f" {month_str} 历史记录")
        title_font = title.font()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        large_table = QTableWidget()
        large_table.setColumnCount(self.table.columnCount())
        large_table.setHorizontalHeaderLabels([
            self.table.horizontalHeaderItem(col).text()
            for col in range(self.table.columnCount())
        ])
        large_table.setRowCount(self.table.rowCount())
        large_table.setWordWrap(True)
        large_table.setEditTriggers(QTableWidget.NoEditTriggers)
        large_table.setSelectionBehavior(QTableWidget.SelectRows)
        large_table.setAlternatingRowColors(True)
        large_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        large_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        large_table.cellDoubleClicked.connect(lambda row, col: self.edit_large_history_row(large_table, dialog, row, col))

        table_font = large_table.font()
        table_font.setPointSize(max(table_font.pointSize() + 6, 17))
        large_table.setFont(table_font)
        header_font = large_table.horizontalHeader().font()
        header_font.setPointSize(max(header_font.pointSize() + 4, 15))
        header_font.setBold(True)
        large_table.horizontalHeader().setFont(header_font)
        large_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        large_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    large_table.setItem(row, col, item.clone())
        if self.table.rowCount() > 0:
            large_table.setSpan(0, 0, 1, self.table.columnCount())

        widths = [135, 170, 150, 150, 150, 150, 165, 300, 220, 300, 300, 220, 220]
        for col, width in enumerate(widths):
            large_table.setColumnWidth(col, width)

        layout.addWidget(large_table)
        close_button = QPushButton("关闭")
        close_button.setMinimumHeight(42)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def edit_selected_row(self, row, col):
        if row == 0: return
        date_item = self.table.item(row, 0)
        if not date_item: return

        target_date = QDate.fromString(date_item.text(), "yyyy-MM-dd")
        self.set_entry_date_safely(target_date)

    def edit_large_history_row(self, source_table, dialog, row, col):
        if row == 0:
            return
        date_item = source_table.item(row, 0)
        if not date_item:
            return
        target_date = QDate.fromString(date_item.text(), "yyyy-MM-dd")
        if not target_date.isValid():
            return
        if self.set_entry_date_safely(target_date):
            dialog.accept()

    def delete_record(self):
        if self._role not in {'admin', 'editor'}:
            return QMessageBox.warning(self, "权限不足", "只有管理员或修改权限账号可以删除日记录。")
        selected = self.table.currentRow()
        if selected < 0: return QMessageBox.information(self, "提示", "请先点击选中要删除的记录。")
        if selected == 0: return QMessageBox.information(self, "提示", "此行为当月固定成本统计汇总，不可在此处删除。")

        day_str = self.table.item(selected, 0).text()
        if QMessageBox.warning(self, "确认删除", f"确定永久删除 {day_str} 记录吗？",
                               QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            df = load_daily()
            save_daily(df[df['日期'] != day_str])
            self.refresh_table()


# ===================== 当日做出的菜品页面 =====================
class DishTab(QWidget):
    FIXED_ITEM_NAMES = ('米饭', '汤', '小菜', '青菜')

    def __init__(self):
        super().__init__()
        self._loading = False
        self._snapshot = {}
        self.current_day_str = ""
        self.init_ui()
        self.refresh_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 前一天")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.btn_next = QPushButton("后一天 ▶")
        self.btn_today = QPushButton("今天")
        self.btn_refresh = QPushButton(" 刷新")
        self.btn_undo = QPushButton("↩ 撤销未保存的所有修改")
        self.btn_save = QPushButton(" 保存修改")
        self.btn_save.setStyleSheet(
            "background-color: #315f88; color: white; font-weight: bold; "
            "padding: 6px 16px; font-size: 14px;"
        )

        top_layout.addWidget(QLabel(" 选择日期:"))
        top_layout.addWidget(self.btn_prev)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.btn_next)
        top_layout.addWidget(self.btn_today)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_undo)
        top_layout.addWidget(self.btn_save)
        main_layout.addLayout(top_layout)

        # 本页内容较长，单独使用滚动区域；不会影响其它页面。
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setMinimumHeight(1080)
        page_layout = QVBoxLayout(page)
        page_layout.setSpacing(12)

        # 第一部分：普通菜品。
        dish_group = QGroupBox("第一部分： 当日做出的菜品")
        dish_layout = QVBoxLayout(dish_group)
        self.table = QTableWidget()
        self._configure_input_table(self.table, fixed_names=False)
        self.table.setMinimumHeight(330)
        dish_layout.addWidget(self.table)

        dish_bottom = QHBoxLayout()
        self.btn_add_row = QPushButton(" 新增菜品")
        self.btn_delete_row = QPushButton(" 删除选中菜品")
        self.edit_day_note = QLineEdit()
        self.edit_day_note.setPlaceholderText("当日菜品总备注（选填）")
        self.lbl_total_cost = QLabel("当日全部食材成本合计：0.00 元")
        self.lbl_total_cost.setStyleSheet("font-weight: bold; font-size:16px; color: #111;")
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #888;")
        dish_bottom.addWidget(self.btn_add_row)
        dish_bottom.addWidget(self.btn_delete_row)
        dish_bottom.addWidget(QLabel("总备注:"))
        dish_bottom.addWidget(self.edit_day_note, 1)
        dish_bottom.addStretch()
        dish_bottom.addWidget(self.lbl_total_cost)
        dish_bottom.addWidget(self.lbl_status)
        dish_layout.addLayout(dish_bottom)
        page_layout.addWidget(dish_group)

        # 第二部分：固定项目。四行名称固定，输入方式与普通菜品一致。
        fixed_group = QGroupBox("第二部分： 固定项目（米饭 / 汤 / 小菜 / 青菜）")
        fixed_layout = QVBoxLayout(fixed_group)
        self.fixed_table = QTableWidget()
        self._configure_input_table(self.fixed_table, fixed_names=True)
        self.fixed_table.setMinimumHeight(255)
        fixed_layout.addWidget(self.fixed_table)
        page_layout.addWidget(fixed_group)

        # 第三部分：按食材和单位汇总当天的实际用量。
        summary_group = QGroupBox("第三部分： 每个食材总共用了多少")
        summary_layout = QVBoxLayout(summary_group)
        self.ingredient_summary_table = QTableWidget()
        self.ingredient_summary_table.setColumnCount(7)
        self.ingredient_summary_table.setHorizontalHeaderLabels(
            ["食材名称", "总使用量", "单位", "原录入金额(元)", "使用于", "先进先出入库价", "出库成本(元)"]
        )
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.ingredient_summary_table.setColumnWidth(1, 120)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.ingredient_summary_table.setColumnWidth(2, 90)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.ingredient_summary_table.setColumnWidth(3, 125)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.ingredient_summary_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.ingredient_summary_table.setColumnWidth(6, 190)
        self.ingredient_summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ingredient_summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ingredient_summary_table.setAlternatingRowColors(True)
        self.ingredient_summary_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ingredient_summary_table.setMinimumHeight(240)
        summary_layout.addWidget(self.ingredient_summary_table)
        self.lbl_summary_hint = QLabel("保存前可预览先进先出的入库批次和出库成本；不同单位分开。缺入库数量或数量未填时成本未知；原录入金额保留供核对。")
        self.lbl_summary_hint.setWordWrap(True)
        self.lbl_summary_hint.setStyleSheet("color: #666;")
        summary_layout.addWidget(self.lbl_summary_hint)
        page_layout.addWidget(summary_group)
        page_layout.addStretch()

        self.page_scroll.setWidget(page)
        main_layout.addWidget(self.page_scroll, 1)
        self.setMinimumHeight(760)

        self.btn_prev.clicked.connect(lambda: self.set_date_safely(self.date_edit.date().addDays(-1)))
        self.btn_next.clicked.connect(lambda: self.set_date_safely(self.date_edit.date().addDays(1)))
        self.btn_today.clicked.connect(lambda: self.set_date_safely(QDate.currentDate()))
        self.btn_refresh.clicked.connect(self.refresh_data_safely)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_undo.clicked.connect(self.undo_changes)
        self.btn_add_row.clicked.connect(self.add_row)
        self.btn_delete_row.clicked.connect(self.delete_selected_row)
        self.date_edit.dateChanged.connect(self.on_date_changed)
        self.table.cellChanged.connect(lambda _row, _col: self.on_table_changed())
        self.fixed_table.cellChanged.connect(lambda _row, _col: self.on_table_changed())
        self.edit_day_note.textChanged.connect(lambda _text: self.on_table_changed())

    def _configure_input_table(self, table, fixed_names=False):
        table.setColumnCount(6)
        first_title = "固定项目" if fixed_names else "菜品名称"
        table.setHorizontalHeaderLabels(
            [first_title, "菜品份数", "使用食材明细", "食材成本(元)", "备注", "操作"]
        )
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.setColumnWidth(1, 95)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        table.setColumnWidth(3, 120)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        table.setColumnWidth(5, 145)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.SelectedClicked
        )
        table_font = table.font()
        table_font.setPointSize(table_font.pointSize() + 2)
        table.setFont(table_font)

    def _collect_table_rows(self, table, section):
        rows = []
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            detail_item = table.item(row, 2)
            cost_item = table.item(row, 3)
            note_item = table.item(row, 4)
            servings_widget = table.cellWidget(row, 1)
            name = name_item.text().strip() if name_item else ''
            detail = detail_item.text().strip() if detail_item else ''
            note = note_item.text().strip() if note_item else ''
            servings_text = servings_widget.text().strip() if isinstance(servings_widget, QLineEdit) else ''
            try:
                servings = int(servings_text) if servings_text else 0
            except ValueError:
                servings = 0
            cost = cost_item.data(Qt.UserRole) if cost_item else 0
            cost = money_amount(cost if cost not in (None, '') else 0)

            # 固定项目的名称永远存在，但空行不写入数据文件。
            has_content = bool(detail or note or cost or servings)
            if section == '菜品':
                has_content = bool(name or detail or note or cost or servings)
            if not has_content:
                continue
            rows.append({
                '菜品名称': name,
                '份数': servings,
                '食材明细': detail,
                '成本': money_amount(cost),
                '备注': note,
                '分区': section,
            })
        return rows

    def _state(self):
        rows = self._collect_table_rows(self.table, '菜品')
        rows.extend(self._collect_table_rows(self.fixed_table, '固定项目'))
        return {
            'date': self.date_edit.date().toString("yyyy-MM-dd"),
            'rows': rows,
            'note': self.edit_day_note.text().strip(),
        }

    def has_unsaved_changes(self):
        if self._loading or not self._snapshot:
            return False
        current = self._state()
        return (
            current.get('rows', []) != self._snapshot.get('rows', [])
            or current.get('note', '') != self._snapshot.get('note', '')
        )

    def confirm_discard_changes(self):
        if not self.has_unsaved_changes():
            return True
        ans = QMessageBox.warning(
            self, " 未保存提示",
            "检测到【当日做出的菜品】有尚未保存的修改。\n\n"
            "如果切换日期，这些修改将会丢失。\n您确定要放弃修改并切换吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return ans == QMessageBox.Yes

    def set_date_safely(self, target_date):
        if not target_date.isValid():
            return False
        if not self.confirm_discard_changes():
            return False
        if not ensure_widget_user_excel_year(self, target_date):
            return False
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(target_date)
        self.date_edit.blockSignals(False)
        self.refresh_data()
        return True

    def on_date_changed(self):
        if not self.confirm_discard_changes():
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate.fromString(self.current_day_str, "yyyy-MM-dd"))
            self.date_edit.blockSignals(False)
            return
        if not ensure_widget_user_excel_year(self, self.date_edit.date()):
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate.fromString(self.current_day_str, "yyyy-MM-dd"))
            self.date_edit.blockSignals(False)
            return
        self.refresh_data()

    def on_table_changed(self):
        if self._loading:
            return
        self.update_total_cost()
        self.update_ingredient_summary()
        if self.has_unsaved_changes():
            self.lbl_status.setText(" 已修改 (未保存)")
        else:
            self.lbl_status.setText("")

    def refresh_data_safely(self):
        if self.confirm_discard_changes():
            self.refresh_data()

    def refresh_data(self):
        self.current_day_str = self.date_edit.date().toString("yyyy-MM-dd")
        df = load_dishes()
        record = df[df['日期'] == self.current_day_str]

        self._loading = True
        if not record.empty:
            item = record.iloc[-1]
            all_rows = dish_rows_from_record(item)
            regular_rows = [row for row in all_rows if row.get('分区', '菜品') != '固定项目']
            fixed_rows = [row for row in all_rows if row.get('分区') == '固定项目']
            self._set_table_rows(regular_rows)
            self._set_fixed_rows(fixed_rows)
            self.edit_day_note.setText(str(item.get('备注', '')).strip())
        else:
            self._set_table_rows([])
            self._set_fixed_rows([])
            self.edit_day_note.clear()
        self._loading = False

        self.update_total_cost()
        self.update_ingredient_summary()
        self._snapshot = self._state()
        self.lbl_status.setText("")

    def _readonly_item(self, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _make_servings_editor(self, value=0):
        editor = QLineEdit()
        editor.setAlignment(Qt.AlignCenter)
        editor.setPlaceholderText("份数")
        editor.setValidator(QIntValidator(0, 999999, editor))
        numeric = safe_float(value if value not in (None, '') else 0)
        if numeric:
            editor.setText(str(int(numeric)))
        editor.textChanged.connect(lambda _text: self.on_table_changed())
        return editor

    def _set_table_rows(self, rows):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row_data in rows:
            self._insert_row(self.table, row_data, fixed_name=None)
        self.table.blockSignals(False)

    def _set_fixed_rows(self, rows):
        by_name = {
            str(row.get('菜品名称', '')).strip(): row
            for row in rows
            if str(row.get('菜品名称', '')).strip()
        }
        self.fixed_table.blockSignals(True)
        self.fixed_table.setRowCount(0)
        for name in self.FIXED_ITEM_NAMES:
            self._insert_row(self.fixed_table, by_name.get(name, {}), fixed_name=name)
        self.fixed_table.blockSignals(False)

    def _insert_row(self, table, row_data=None, fixed_name=None):
        row_data = row_data or {}
        row = table.rowCount()
        table.insertRow(row)
        name = fixed_name if fixed_name is not None else str(row_data.get('菜品名称', '')).strip()
        name_item = QTableWidgetItem(name)
        if fixed_name is not None:
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, 0, name_item)
        table.setCellWidget(row, 1, self._make_servings_editor(row_data.get('份数', 0)))
        table.setItem(row, 2, self._readonly_item(str(row_data.get('食材明细', '')).strip()))
        raw_cost = row_data.get('成本', 0)
        cost = money_amount(raw_cost if raw_cost not in (None, '') else 0)
        cost_item = self._readonly_item(f"{cost:.2f}" if cost else "")
        cost_item.setData(Qt.UserRole, cost)
        table.setItem(row, 3, cost_item)
        table.setItem(row, 4, QTableWidgetItem(str(row_data.get('备注', '')).strip()))
        btn = QPushButton(" 选择/修改食材")
        btn.setMinimumHeight(30)
        btn.clicked.connect(
            lambda _checked=False, target_table=table, target_row=row:
            self.open_ingredient_selector_for(target_table, target_row)
        )
        table.setCellWidget(row, 5, btn)

    def add_row(self):
        self._loading = True
        self._insert_row(self.table)
        self._loading = False
        self.table.selectRow(self.table.rowCount() - 1)
        self.on_table_changed()

    def delete_selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先点击选中要删除的菜品。")
            return
        self.table.removeRow(row)
        self.on_table_changed()

    def open_ingredient_selector_for(self, table, row):
        if row < 0 or row >= table.rowCount():
            return
        name_item = table.item(row, 0)
        detail_item = table.item(row, 2)
        dish_name = name_item.text().strip() if name_item else ""
        dialog = ItemSelectDialog(detail_item.text().strip() if detail_item else "", "食材", self)
        dialog.setWindowTitle(f" 选择「{dish_name or '这道菜'}」使用的食材")
        if dialog.exec() != QDialog.Accepted:
            return
        detail = dialog.selected_items_str
        cost = detail_total_cost(detail)
        table.blockSignals(True)
        table.setItem(row, 2, self._readonly_item(detail))
        cost_item = self._readonly_item(f"{cost:.2f}" if cost else "")
        cost_item.setData(Qt.UserRole, cost)
        table.setItem(row, 3, cost_item)
        table.blockSignals(False)
        self.on_table_changed()

    @staticmethod
    def _ingredient_parts(detail_text):
        return [{'name': item['name'], 'quantity': item['quantity'], 'unit': item['unit'],
                 'cost': money_amount(item['total']) if money_value_was_entered(item['total']) else money_amount(item['quantity'] * unit_price_value(item['unit_price'])),
                 'quantity_known': item['quantity'] > 0} for item in _inventory_detail_items(detail_text)]

    def update_ingredient_summary(self):
        preview_day = self.date_edit.date().toString('yyyy-MM-dd')
        draft_record = {'日期': preview_day, '菜品数据': exact_json_dumps(self._state().get('rows', []), ensure_ascii=False)}
        saved_usage = [row for row in _inventory_consumption_rows() if row['date'] != preview_day]
        draft_usage = _inventory_consumption_rows(pd.DataFrame([draft_record]))
        preview = _inventory_fifo_snapshot(usage=saved_usage + draft_usage)
        fifo_groups = {}
        for item in preview['movements']:
            if item['date'] != preview_day or item['kind'] != 'dish':
                continue
            group = fifo_groups.setdefault((item['name'], item['unit']), {'layers': [], 'known_cost': 0, 'unknown_quantity': 0, 'unit': item['unit']})
            group['layers'].extend(item['layers'])
            group['known_cost'] += item['known_cost']
            group['unknown_quantity'] += item['unknown_quantity']
        summary = {}
        for row in self._state().get('rows', []):
            source = str(row.get('菜品名称', '')).strip() or '未命名菜品'
            for item in self._ingredient_parts(row.get('食材明细', '')):
                name = item['name']
                unit = item['unit']
                if not name:
                    continue
                key = (name, unit)
                current = summary.setdefault(key, {
                    'quantity': 0,
                    'cost': 0,
                    'known_count': 0,
                    'unknown_count': 0,
                    'sources': [],
                })
                current['quantity'] += item['quantity']
                current['cost'] += item['cost']
                if item['quantity_known']:
                    current['known_count'] += 1
                else:
                    current['unknown_count'] += 1
                if source not in current['sources']:
                    current['sources'].append(source)

        self.ingredient_summary_table.setRowCount(0)
        for name, unit in sorted(summary, key=lambda value: (value[0], value[1])):
            data = summary[(name, unit)]
            row = self.ingredient_summary_table.rowCount()
            self.ingredient_summary_table.insertRow(row)
            if data['known_count']:
                quantity_text = f"{data['quantity']:g}"
                if data['unknown_count']:
                    quantity_text += " + 未填数量"
            else:
                quantity_text = "未填写"
            values = [
                name,
                quantity_text,
                unit or "—",
                f"{data['cost']:.2f}",
                "、".join(data['sources']),
                _inventory_fifo_description(fifo_groups.get((name, unit), {})) or '数量未填，无法匹配入库批次',
                (_inventory_fifo_cost_text(fifo_groups[(name, unit)]) + ('；另有未填数量' if data['unknown_count'] else '')) if (name, unit) in fifo_groups else '成本未知',
            ]
            for column, value in enumerate(values):
                self.ingredient_summary_table.setItem(row, column, self._readonly_item(str(value)))

    def update_total_cost(self):
        total = sum(row.get('成本', 0) for row in self._state().get('rows', []))
        self.lbl_total_cost.setText(f"当日全部食材成本合计：{total:.2f} 元")

    def save_data(self):
        day_str = self.date_edit.date().toString("yyyy-MM-dd")
        state = self._state()
        rows = state.get('rows', [])
        note = state.get('note', '')
        total_cost = sum(row.get('成本', 0) for row in rows)
        df = load_dishes()
        df = df[df['日期'] != day_str].copy()

        if rows or note:
            df = pd.concat([df, pd.DataFrame([{
                '日期': day_str,
                '菜品明细': "；".join(
                    row.get('菜品名称', '') for row in rows if row.get('菜品名称', '')
                ),
                '菜品数据': exact_json_dumps(rows, ensure_ascii=False),
                '总成本': total_cost,
                '备注': note,
            }])], ignore_index=True)
            message = f"{day_str} 的菜品记录已保存。"
        else:
            message = f"{day_str} 的菜品记录已清空。"

        save_dishes(df)
        self.refresh_data()
        self.lbl_status.setText(" 已保存")
        QMessageBox.information(self, "保存成功", message)

    def undo_changes(self):
        if not self.has_unsaved_changes():
            self.lbl_status.setText("ℹ 没有需要撤销的修改")
            return
        if QMessageBox.question(
                self, "确认撤销",
                "确定要撤销所有未保存的修改吗？\n所有更改将恢复到上次保存/加载时的状态。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.refresh_data()
            self.lbl_status.setText("↩ 已撤销")

# ===================== 食材/佐料明细页面 =====================
class PurchaseDetailTab(QWidget):
    """按天显示/编辑食材或佐料明细，两个页面共用完全相同的逻辑与样式。"""
    def __init__(self, category):
        super().__init__()
        self.category = category
        self.detail_column = f"{category}明细"
        self.cost_column = f"{category}成本"
        self._snapshot = []  # 保存初始状态用于检测修改
        self.current_day_str = ""
        self.btn_del_unit = QPushButton(" 增加/修改/删除 单位")
        self.btn_del_unit.setStyleSheet("padding: 6px 16px; font-size: 14px;")
        self.btn_del_unit.clicked.connect(self.modify_delete_unit)
        self.btn_move_category = QPushButton(
            "移动至佐料" if category == "食材" else "移动至食材"
        )
        self.btn_move_category.setToolTip("勾选下方元素后，把它们移动到另一类明细")
        self.btn_move_category.setStyleSheet("padding: 6px 16px; font-size: 14px;")
        self.btn_move_category.clicked.connect(self.move_selected_to_other_category)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # 日期选择 + 操作按钮
        top_layout = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 前一天")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.btn_next = QPushButton("后一天 ▶")
        self.btn_today = QPushButton("今天")
        self.btn_refresh = QPushButton(" 刷新")
        self.btn_save = QPushButton(" 保存修改")
        self.btn_save.setStyleSheet("background-color: #315f88; color: white; font-weight: bold; padding: 6px 16px; font-size: 14px;")
        self.btn_undo = QPushButton("↩ 撤销未保存的所有修改")
        self.btn_undo.setStyleSheet("padding: 6px 16px; font-size: 14px;")

        top_layout.addWidget(QLabel(" 选择日期:"))
        top_layout.addWidget(self.btn_prev)
        top_layout.addWidget(self.date_edit)
        top_layout.addWidget(self.btn_next)
        top_layout.addWidget(self.btn_today)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_del_unit)
        top_layout.addWidget(self.btn_undo)
        top_layout.addWidget(self.btn_save)
        main_layout.addLayout(top_layout)

        # 明细表格 - 可编辑
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", f"{self.category}名称", "数量", "单位", "单价(元)", "总价(元)", "备注"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 42)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        # 增大字体
        font = self.table.font()
        font.setPointSize(font.pointSize() + 4)
        self.table.setFont(font)
        main_layout.addWidget(self.table)

        # 底部按钮和汇总
        bottom_layout = QHBoxLayout()
        self.btn_add_row = QPushButton(" 新增空行")
        self.btn_delete_row = QPushButton(" 删除选中行")
        self.lbl_total_items = QLabel(f"{self.category}种类: 0")
        self.lbl_total_cost = QLabel("总金额: 0.00 元")
        self.lbl_total_cost.setStyleSheet("font-weight: bold; font-size:16px; color: #111;")
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #888;")

        bottom_layout.addWidget(self.btn_add_row)
        bottom_layout.addWidget(self.btn_delete_row)
        bottom_layout.addWidget(self.btn_move_category)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.lbl_total_items)
        bottom_layout.addWidget(self.lbl_total_cost)
        bottom_layout.addWidget(self.lbl_status)
        main_layout.addLayout(bottom_layout)

        # 把整个页面包进滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content_widget = QWidget()
        content_widget.setLayout(main_layout)
        scroll.setWidget(content_widget)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        # 事件绑定
        self.btn_prev.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(-1)))
        self.btn_next.clicked.connect(lambda: self.date_edit.setDate(self.date_edit.date().addDays(1)))
        self.date_edit.dateChanged.connect(self.on_date_changed)
        self.btn_today.clicked.connect(lambda: self.date_edit.setDate(QDate.currentDate()))
        self.btn_refresh.clicked.connect(self.refresh_data)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_undo.clicked.connect(self.undo_changes)
        self.btn_add_row.clicked.connect(self.add_row)
        self.btn_delete_row.clicked.connect(self.delete_row)
        # 监听表格修改，自动更新总价/汇总
        self.table.cellChanged.connect(self.on_cell_changed)

        self.refresh_data()

    def _get_table_state(self):
        """获取当前表格的快照 (用于脏数据检测)"""
        state = []
        for row in range(self.table.rowCount()):
            row_data = []
            all_empty = True
            for col in range(7):
                item = self.table.item(row, col)
                if item:
                    # Checkboxes are a transient selection aid, not workbook data.
                    # Do not make merely selecting rows look like an unsaved edit.
                    val = '' if col == 0 else item.text()
                else:
                    w = self.table.cellWidget(row, col)
                    if w and isinstance(w, QComboBox):
                        val = w.currentText()
                    elif w and isinstance(w, QLineEdit):
                        val = w.text()
                    else:
                        val = ''
                row_data.append(val)
                if val.strip():
                    all_empty = False
            # 跳过全空行，避免误判未保存
            if not all_empty:
                state.append(row_data)
            else:
                state.append([''] * 7)  # 统一为空行格式
        return state

    def _tables_equal(self, a, b):
        """比较两个表格快照是否相同"""
        if len(a) != len(b):
            return False
        for row_a, row_b in zip(a, b):
            if len(row_a) != len(row_b):
                return False
            for va, vb in zip(row_a, row_b):
                if va.strip() != vb.strip():
                    return False
        return True

    def has_unsaved_changes(self):
        """检测是否有未保存的修改"""
        if not hasattr(self, '_snapshot') or not self._snapshot:
            return False
        current = self._get_table_state()
        # 如果当前所有行都是全空行，视为无修改
        if all(all(v.strip() == '' for v in row) for row in current):
            return False
        return not self._tables_equal(current, self._snapshot)

    def on_date_changed(self):
        """日期改变时，检测未保存修改"""
        if hasattr(self, '_snapshot') and self._snapshot:
            if self.has_unsaved_changes():
                ans = QMessageBox.warning(self, "未保存",
                    "当前页面的修改尚未保存！切换日期将丢失更改。\n\n是否继续？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ans == QMessageBox.No:
                    # 阻止日期切换 - 设回原日期
                    self.date_edit.blockSignals(True)
                    self.date_edit.setDate(QDate.fromString(self.current_day_str, "yyyy-MM-dd"))
                    self.date_edit.blockSignals(False)
                    return
        if not ensure_widget_user_excel_year(self, self.date_edit.date()):
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate.fromString(self.current_day_str, "yyyy-MM-dd"))
            self.date_edit.blockSignals(False)
            return
        self.refresh_data()

    def refresh_data(self):
        self.current_day_str = self.date_edit.date().toString("yyyy-MM-dd")
        self.table.blockSignals(True)  # 防止触发 cellChanged
        self.table.setRowCount(0)

        df = load_daily()
        record = df[df['日期'] == self.current_day_str]
        self.lbl_status.setText("")

        detail_str = ""
        if not record.empty:
            record = record.iloc[0]
            detail_str = str(record.get(self.detail_column, '')).strip()
            if detail_str == 'nan':
                detail_str = ""

        items = self._parse_detail(detail_str)

        if not items:
            # 至少显示一个空行方便输入
            self.table.setRowCount(0)
            self.lbl_total_items.setText(f"{self.category}种类: 0")
            self.lbl_total_cost.setText("总金额: 0.00 元")
        else:
            total_cost = 0
            self.table.setRowCount(len(items))
            for i, (name, qty, unit, unit_price, total_price, note, raw) in enumerate(items):
                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                check_item.setCheckState(Qt.Unchecked)
                self.table.setItem(i, 0, check_item)
                self.table.setItem(i, 1, QTableWidgetItem(name))
                self.table.setItem(i, 2, QTableWidgetItem(str(qty) if qty != '' else ''))

                # 单位用下拉框
                unit_combo = QComboBox()
                unit_combo.addItems([''] + UNITS_LIST)
                if unit:
                    unit_combo.setCurrentText(unit)
                self.table.setCellWidget(i, 3, unit_combo)

                self.table.setItem(i, 4, QTableWidgetItem(f"{unit_price:.6f}" if unit_price != '' else ''))
                self.table.setItem(i, 5, QTableWidgetItem(f"{total_price:.2f}" if total_price != '' else ''))
                self.table.setItem(i, 6, QTableWidgetItem(note))
                total_cost += total_price if total_price != '' else 0

            self.lbl_total_items.setText(f"{self.category}种类: {len(items)}")
            self.lbl_total_cost.setText(f"总金额: {total_cost:.2f} 元")

        self.table.blockSignals(False)
        self._snapshot = self._get_table_state()

    def _parse_detail(self, detail_str):
        """解析明细字符串，返回 [(名称, 数量, 单位, 单价, 总价, 备注, 原文), ...]"""
        results = []
        if not detail_str or detail_str == 'nan':
            return results

        unit_pattern = get_unit_pattern()
        unit_re = re.compile(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*' + unit_pattern + r'?\s+(\d+(?:\.\d+)?)$')
        old_re = re.compile(r'^(.*?)\s*(\d+(?:\.\d+)?)$')

        for item in re.split(r'[,，]', str(detail_str)):
            item = item.strip()
            if not item:
                continue
            clean_item, note = split_item_note(item)

            m = unit_re.match(clean_item)
            if m:
                name = m.group(1).strip()
                qty = decimal_number(m.group(2))
                unit = m.group(3) or ''
                total_price = money_amount(m.group(4))
                unit_price = total_price / qty if qty > 0 else 0
                results.append((name, qty, unit, unit_price_value(unit_price), total_price, note, item))
                continue

            m = old_re.match(clean_item)
            if m:
                name = m.group(1).strip()
                total_price = money_amount(m.group(2))
                results.append((name, '', '', '', total_price, note, item))
                continue

        return results

    def on_cell_changed(self, row, col):
        """单元格内容改变时自动更新汇总"""
        if col == 0:
            return
        self.table.blockSignals(True)

        # Existing detail strings may have only a total price.  If the user
        # later supplies quantity/unit, preserve that total and derive the
        # unit price.  Only a real, non-empty unit-price edit may recalculate
        # the total.  This prevents ``总价`` becoming 0.00 on focus change.
        if col in (2, 4, 5):
            qty_item = self.table.item(row, 2)
            price_item = self.table.item(row, 4)
            total_item = self.table.item(row, 5)
            try:
                qty_text = qty_item.text().strip() if qty_item else ''
                price_text = price_item.text().strip() if price_item else ''
                total_text = total_item.text().strip() if total_item else ''
                qty = decimal_number(qty_text) if qty_text else 0
                price = unit_price_value(price_text) if price_text else 0
                total = money_amount(total_text) if total_text else 0
                if col == 2 and qty > 0 and not price_text and total_text:
                    self.table.setItem(
                        row, 4,
                        QTableWidgetItem(f"{total / qty:.6f}".rstrip('0').rstrip('.')),
                    )
                elif col in (2, 4) and qty > 0 and price_text:
                    self.table.setItem(row, 5, QTableWidgetItem(f"{qty * price:.2f}"))
                elif col == 5 and qty > 0 and total_text and not price_text:
                    self.table.setItem(
                        row, 4,
                        QTableWidgetItem(f"{total / qty:.6f}".rstrip('0').rstrip('.')),
                    )
            except (ValueError, AttributeError):
                pass

        # 修改总价不自动改单价，等保存时再询问

        self.table.blockSignals(False)
        self._update_summary()
        self.lbl_status.setText(" 已修改 (未保存)")

    def _update_summary(self):
        """更新汇总信息"""
        total_cost = 0
        count = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 5)  # 总价列
            if item and item.text().strip():
                try:
                    total_cost += money_amount(item.text())
                    count += 1
                except ValueError:
                    pass
        self.lbl_total_items.setText(f"{self.category}种类: {count}")
        self.lbl_total_cost.setText(f"总金额: {total_cost:.2f} 元")

    def add_row(self):
        """添加空行"""
        self.table.blockSignals(True)
        row = self.table.rowCount()
        self.table.insertRow(row)
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check_item.setCheckState(Qt.Unchecked)
        self.table.setItem(row, 0, check_item)
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self.table.setItem(row, 2, QTableWidgetItem(""))
        unit_combo = QComboBox()
        unit_combo.addItems([''] + UNITS_LIST)
        self.table.setCellWidget(row, 3, unit_combo)
        self.table.setItem(row, 4, QTableWidgetItem(""))
        self.table.setItem(row, 5, QTableWidgetItem(""))
        self.table.setItem(row, 6, QTableWidgetItem(""))
        self.table.blockSignals(False)

    def delete_row(self):
        """删除选中的行"""
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.information(self, "提示", "请先点击选中要删除的行。")
            return
        self.table.removeRow(selected)
        self._update_summary()
        self.lbl_status.setText(" 已修改 (未保存)")

    def save_data(self):
        """保存所有修改到 Excel（含金额校验：单价x数量 vs 总价）"""
        self.table.blockSignals(True)
        food_items = []
        total_cost = 0
        needs_review = []  # 记录有冲突的行

        # 先遍历收集所有行数据
        rows_data = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            qty_item = self.table.item(row, 2)
            unit_widget = self.table.cellWidget(row, 3)
            price_item = self.table.item(row, 4)
            total_item = self.table.item(row, 5)
            note_item = self.table.item(row, 6)

            name = name_item.text().strip() if name_item else ''
            if not name:
                continue  # 跳过空行

            qty_str = qty_item.text().strip() if qty_item and qty_item.text().strip() else ''
            unit = unit_widget.currentText().strip() if unit_widget else ''
            price_str = price_item.text().strip() if price_item and price_item.text().strip() else ''
            total_str = total_item.text().strip() if total_item and total_item.text().strip() else ''
            note = note_item.text().strip() if note_item else ''

            rows_data.append((row, name, qty_str, unit, price_str, total_str, note))

        # 检测冲突并让用户选择
        for row, name, qty_str, unit, price_str, total_str, note in rows_data:
            try:
                qty = decimal_number(qty_str) if qty_str else 0
                unit_price = unit_price_input(price_str) if price_str else 0
                total_price = money_input(total_str) if total_str else 0
            except ValueError as exc:
                self.table.blockSignals(False)
                QMessageBox.warning(self, '金额错误', f'【{name}】{exc}')
                return

            # 只有同时有数量和单价和总价时才检测冲突
            if qty > 0 and unit_price > 0 and total_price > 0:
                calculated_total = money_amount(qty * unit_price)
                if abs(calculated_total - total_price) > Decimal('0.005'):  # 存在显著差异
                    needs_review.append((row, name, qty_str, unit, price_str, total_str, qty, unit_price, total_price, calculated_total))

        # 处理冲突
        if needs_review:
            conflict_msgs = []
            for r, name, qs, u, ps, ts, qty, up, tp, calc_t in needs_review:
                conflict_msgs.append(f"「{name}」: {qs}{u} x {up:.6f} = {calc_t:.2f} ≠ 输入总价 {tp:.2f}")

            msg = f"以下{self.category}的「单价 x 数量」与输入的总价不符：\n" + "\n".join(conflict_msgs) + "\n\n请选择以哪个为准："

            btn_qty_price = QMessageBox.question(self, "金额不符", msg + "\n按「Yes」= 以「单价 x 数量」为准，自动修正总价\n按「No」 = 以「总价」为准，自动修正单价",
                                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

            for r, name, qs, u, ps, ts, qty, up, tp, calc_t in needs_review:
                if btn_qty_price == QMessageBox.Yes:
                    # 以单价x数量为准，修正总价
                    new_total = calc_t
                    self.table.setItem(r, 5, QTableWidgetItem(f"{new_total:.2f}"))
                    # 同时修正存储用的变量
                else:
                    # 以总价为准，修正单价
                    new_up = unit_price_value(tp / qty) if qty > 0 else up
                    self.table.setItem(r, 4, QTableWidgetItem(f"{new_up:.6f}"))

            # 选择之后再次确认
            if btn_qty_price == QMessageBox.Yes:
                confirm_msg = "已将以下行的总价修正为「单价 x 数量」的计算结果：\n" + "\n".join(
                    [f"「{name}」: {qs}{u} x {up:.6f} = {calc_t:.2f}" for _, name, qs, u, _, _, _, up, _, calc_t in needs_review]
                )
            else:
                confirm_msg = "已将以下行的单价修正为「总价 ÷ 数量」的计算结果：\n" + "\n".join(
                    [f"「{name}」: 原单价 {up:.6f} → 新单价 {unit_price_value(tp/qty):.6f}（{tp:.2f} ÷ {qty}）" for _, name, _, _, _, _, qty, up, tp, _ in needs_review]
                )

            ans = QMessageBox.question(self, "确认修改", confirm_msg + "\n\n确定按此方式保存吗？",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans == QMessageBox.No:
                self.table.blockSignals(False)
                return

        self.table.blockSignals(False)

        # 重新读取表格数据（可能已被修正）
        food_items = []
        total_cost = 0
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            qty_item = self.table.item(row, 2)
            unit_widget = self.table.cellWidget(row, 3)
            price_item = self.table.item(row, 4)
            total_item = self.table.item(row, 5)
            note_item = self.table.item(row, 6)

            name = name_item.text().strip() if name_item else ''
            if not name:
                continue

            qty_str = qty_item.text().strip() if qty_item and qty_item.text().strip() else ''
            unit = unit_widget.currentText().strip() if unit_widget else ''
            total_str = total_item.text().strip() if total_item and total_item.text().strip() else ''
            note = note_item.text().strip() if note_item else ''

            if qty_str and unit and total_str:
                food_items.append(join_item_note(f"{name} {unit_join(qty_str, unit)} {total_str}", note))
            elif total_str:
                food_items.append(join_item_note(f"{name} {total_str}", note))
            else:
                food_items.append(join_item_note(name, note))

            if total_str:
                try:
                    total_cost += money_amount(total_str)
                except ValueError:
                    pass

        detail_str = ", ".join(food_items) if food_items else ""

        # 保存到 Excel
        df = load_daily()
        day_str = self.current_day_str
        existing_idx = df[df['日期'] == day_str].index

        if len(existing_idx) > 0:
            df.loc[existing_idx[0], self.detail_column] = detail_str
            df.loc[existing_idx[0], self.cost_column] = total_cost
        else:
            new_row = {
                '日期': day_str, '收益': 0, '新客人数量': '', '总客人数': '', '食材成本': 0, '食材明细': '',
                '佐料成本': 0, '佐料明细': '', '水电': 0, '其他': 0, '其他明细': '', '当日备注': ''
            }
            new_row[self.detail_column] = detail_str
            new_row[self.cost_column] = total_cost
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        save_daily(df)
        self._snapshot = self._get_table_state()
        self.lbl_status.setText(" 已保存")
        QMessageBox.information(self, "保存成功", f"{day_str} 的{self.category}数据已保存！")

    def undo_changes(self):
        """撤销所有未保存的修改，回到上次保存/加载的状态"""
        if not self.has_unsaved_changes():
            self.lbl_status.setText("ℹ 没有需要撤销的修改")
            return
        if QMessageBox.question(self, "确认撤销",
                "确定要撤销所有未保存的修改吗？\n所有更改将恢复到上次保存/加载时的状态。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.refresh_data()
            self.lbl_status.setText("↩ 已撤销")

    def modify_delete_unit(self):
        """修改/删除单位（可拖拽排序、双击编辑、勾选删除）"""
        used_units = set()
        for row in range(self.table.rowCount()):
            unit_widget = self.table.cellWidget(row, 3)
            if unit_widget and isinstance(unit_widget, QComboBox) and unit_widget.currentText().strip():
                used_units.add(unit_widget.currentText().strip())
        open_unit_manager_dialog(self, UNITS_LIST, used_units, self._refresh_ingredient_unit_combos)

    def _refresh_ingredient_unit_combos(self, rename_map=None):
        rename_map = rename_map or {}
        for row in range(self.table.rowCount()):
            unit_widget = self.table.cellWidget(row, 3)
            if unit_widget and isinstance(unit_widget, QComboBox):
                current = unit_widget.currentText()
                current = rename_map.get(current, current)
                unit_widget.blockSignals(True)
                unit_widget.clear()
                unit_widget.addItems([''] + UNITS_LIST)
                if current in UNITS_LIST:
                    unit_widget.setCurrentText(current)
                unit_widget.blockSignals(False)

    def _table_item_string(self, row):
        """Serialize one visible row using the same format as the workbook."""
        name_item = self.table.item(row, 1)
        if not name_item or not name_item.text().strip():
            return '', 0
        name = name_item.text().strip()
        qty_item = self.table.item(row, 2)
        unit_widget = self.table.cellWidget(row, 3)
        total_item = self.table.item(row, 5)
        note_item = self.table.item(row, 6)
        qty = qty_item.text().strip() if qty_item else ''
        unit = unit_widget.currentText().strip() if unit_widget else ''
        total = total_item.text().strip() if total_item else ''
        note = note_item.text().strip() if note_item else ''
        try:
            total_value = money_amount(total) if total else 0
        except ValueError:
            total_value = 0
        if qty and unit and total:
            text = f"{name} {unit_join(qty, unit)} {total}"
        elif total:
            text = f"{name} {total}"
        else:
            text = name
        return join_item_note(text, note), total_value

    def _detail_tuple_to_string(self, item):
        name, qty, unit, _unit_price, total_price, note, _raw = item
        if qty != '' and unit and total_price != '':
            text = f"{name} {unit_join(qty, unit)} {total_price}"
        elif total_price != '':
            text = f"{name} {total_price}"
        else:
            text = str(name).strip()
        return join_item_note(text, note)

    def move_selected_to_other_category(self):
        """Move checked rows between the food and spice columns for this date."""
        selected_rows = [
            row for row in range(self.table.rowCount())
            if self.table.item(row, 0)
            and self.table.item(row, 0).checkState() == Qt.Checked
            and self.table.item(row, 1)
            and self.table.item(row, 1).text().strip()
        ]
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先勾选要移动的元素。")
            return

        other_category = "佐料" if self.category == "食材" else "食材"
        other_detail_column = f"{other_category}明细"
        other_cost_column = f"{other_category}成本"
        current_items, moved_items = [], []
        current_cost, moved_cost = 0, 0
        selected_set = set(selected_rows)
        for row in range(self.table.rowCount()):
            item_text, item_cost = self._table_item_string(row)
            if not item_text:
                continue
            if row in selected_set:
                moved_items.append(item_text)
                moved_cost += item_cost
            else:
                current_items.append(item_text)
                current_cost += item_cost

        df = load_daily()
        existing_idx = df[df['日期'] == self.current_day_str].index
        if len(existing_idx) > 0:
            idx = existing_idx[0]
            destination_text = str(df.loc[idx, other_detail_column] or '').strip()
            destination_items = [
                self._detail_tuple_to_string(item)
                for item in self._parse_detail(destination_text)
            ]
            destination_items.extend(moved_items)
            destination_cost = sum(
                (money_amount(item[4]) if item[4] != '' else 0)
                for item in self._parse_detail(destination_text)
            ) + moved_cost
            df.loc[idx, self.detail_column] = ", ".join(current_items)
            df.loc[idx, self.cost_column] = current_cost
            df.loc[idx, other_detail_column] = ", ".join(destination_items)
            df.loc[idx, other_cost_column] = destination_cost
        else:
            # This is unusual because the page normally loads an existing day, but
            # keeping the operation safe also supports a newly entered date.
            new_row = {
                '日期': self.current_day_str, '收益': 0, '新客人数量': '', '总客人数': '',
                '食材成本': 0, '食材明细': '', '佐料成本': 0, '佐料明细': '',
                '水电': 0, '其他': 0, '其他明细': '', '当日备注': ''
            }
            new_row[self.detail_column] = ", ".join(current_items)
            new_row[self.cost_column] = current_cost
            new_row[other_detail_column] = ", ".join(moved_items)
            new_row[other_cost_column] = moved_cost
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        save_daily(df)
        self.refresh_data()
        QMessageBox.information(
            self,
            "移动完成",
            f"已将 {len(moved_items)} 个元素从{self.category}明细移动至{other_category}明细。",
        )


def _update_remote_replacement_status(request_id, status, message=''):
    config = _read_path_config()
    if str(config.get(REMOTE_REPLACEMENT_REQUEST_ID_KEY) or '') != str(request_id):
        return False
    config[REMOTE_REPLACEMENT_STATUS_KEY] = str(status)
    config['REMOTE_WORKBOOK_REPLACEMENT_MESSAGE'] = str(message)[:4000]
    config['REMOTE_WORKBOOK_REPLACEMENT_UPDATED_AT'] = datetime.now().astimezone().isoformat(timespec='seconds')
    _write_path_config(config)
    return True


def stop_sync_assistant_worker():
    lock_path = os.path.join(os.path.expanduser('~'), '.restaurant_finance_sync', 'assistant.lock')
    try:
        with open(lock_path, 'r', encoding='utf-8') as handle:
            pid = int(handle.read().strip())
        os.kill(pid, getattr(__import__('signal'), 'SIGTERM'))
        return True
    except (OSError, ValueError, ProcessLookupError):
        return False


_SYNC_ASSISTANT_LAST_LAUNCH_AT = 0
_SYNC_ASSISTANT_LAST_LAUNCH_PATH = ""


def _sync_assistant_peer_is_running(timeout=0.35):
    """通过本机握手确认同步助手界面进程确实已经运行。"""
    try:
        with socket.create_connection(("127.0.0.1", ASSISTANT_PORT), timeout=float(timeout)) as connection:
            connection.settimeout(float(timeout))
            request = exact_json_dumps(
                {"role": "cost_manager", "event": "ping", "pid": os.getpid()},
                ensure_ascii=False,
            ).encode("utf-8") + b"\n"
            connection.sendall(request)
            chunks = bytearray()
            while len(chunks) < 4096:
                part = connection.recv(1024)
                if not part:
                    break
                chunks.extend(part)
                if b"\n" in part:
                    break
            raw = bytes(chunks).split(b"\n", 1)[0]
            response = exact_json_loads(raw.decode("utf-8")) if raw else {}
            return str(response.get("role") or "") == "sync_assistant"
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return False


def _current_main_app_bundle():
    """返回当前主程序所在的 .app 根目录；开发环境下返回空字符串。"""
    for raw_path in (getattr(sys, 'executable', ''), globals().get('__file__', '')):
        path = os.path.abspath(os.path.expanduser(str(raw_path or '')))
        while path and path != os.path.dirname(path):
            if path.lower().endswith('.app') and os.path.isdir(path):
                return path
            path = os.path.dirname(path)
    return ''


def _looks_like_sync_assistant_app(path):
    """确认候选目录确实是可启动的云同步助手 macOS 应用包。"""
    try:
        path = os.path.abspath(os.path.expanduser(str(path or '')))
        if not os.path.isdir(path) or not path.lower().endswith('.app'):
            return False
        info_path = os.path.join(path, 'Contents', 'Info.plist')
        if not os.path.isfile(info_path):
            return False
        with open(info_path, 'rb') as handle:
            info = plistlib.load(handle)
        executable_name = str(info.get('CFBundleExecutable') or '').strip()
        if not executable_name:
            return False
        executable_path = os.path.join(path, 'Contents', 'MacOS', executable_name)
        if not os.path.isfile(executable_path):
            return False
        display_name = ' '.join(
            str(info.get(key) or '')
            for key in ('CFBundleDisplayName', 'CFBundleName')
        )
        display_name += ' ' + os.path.basename(path)
        return '同步助手' in display_name and ('云' in display_name or '餐饮' in display_name)
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return False


def _looks_like_standalone_sync_assistant(path):
    """只把真正的单文件云同步助手作为开发环境候选。"""
    try:
        if not os.path.isfile(path) or not str(path).lower().endswith('.py'):
            return False
        with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
            head = handle.read(120000)
        return (
            '餐饮成本管家云同步助手（单文件版）' in head
            and 'MODULE_SOURCES' in head
            and 'def main(' in head
        )
    except OSError:
        return False


def _is_valid_sync_assistant_bundle(path):
    path = str(path or '').strip()
    if path.lower().endswith('.app'):
        return _looks_like_sync_assistant_app(path)
    return _looks_like_standalone_sync_assistant(path)


def _discover_sync_assistant_bundle(config):
    """优先查找与主程序并排放置的同步助手 .app，开发时才回退到 .py。"""
    source_dir = os.path.dirname(os.path.abspath(__file__))
    main_app = _current_main_app_bundle()
    main_app_parent = os.path.dirname(main_app) if main_app else ''

    explicit_paths = []
    for key in (
        'SYNC_ASSISTANT_APP_PATH',
        'SYNC_ASSISTANT_BUNDLE_PATH',
        'SYNC_ASSISTANT_SCRIPT_PATH',
    ):
        value = str(config.get(key, '') or '').strip()
        if value:
            explicit_paths.append(os.path.abspath(os.path.expanduser(value)))

    # 打包后，主程序.app 与云同步助手.app 放在同一文件夹即可自动识别。
    canonical_paths = []
    if main_app_parent:
        canonical_paths.append(os.path.join(main_app_parent, '云同步助手.app'))
    canonical_paths.extend([
        os.path.join(source_dir, '云同步助手.app'),
        os.path.join(source_dir, '云同步助手.py'),
    ])

    for path in explicit_paths + canonical_paths:
        if _is_valid_sync_assistant_bundle(path):
            return path

    search_dirs = []
    for folder in (main_app_parent, source_dir):
        if folder:
            search_dirs.append(folder)
    assistant_dir = str(config.get('SYNC_ASSISTANT_DIR', '') or '').strip()
    if assistant_dir:
        search_dirs.append(os.path.abspath(os.path.expanduser(assistant_dir)))
    for path in explicit_paths:
        search_dirs.append(os.path.dirname(path))

    app_candidates = []
    script_candidates = []
    seen = set()
    for folder in search_dirs:
        folder = os.path.abspath(os.path.expanduser(str(folder or '')))
        if not folder or folder in seen or not os.path.isdir(folder):
            continue
        seen.add(folder)
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            lower_name = name.lower()
            if name.startswith('云同步助手') and lower_name.endswith('.app'):
                if _looks_like_sync_assistant_app(path):
                    try:
                        modified = os.path.getmtime(path)
                    except OSError:
                        modified = 0
                    app_candidates.append((modified, path))
            elif name.startswith('云同步助手') and lower_name.endswith('.py'):
                if _looks_like_standalone_sync_assistant(path):
                    try:
                        modified = os.path.getmtime(path)
                    except OSError:
                        modified = 0
                    script_candidates.append((modified, path))

    # .app 永远优先于 .py，避免打包后错误调用虚拟环境解释器。
    candidates = app_candidates or script_candidates
    if not candidates:
        return ''
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]


def _remember_sync_assistant_bundle(path):
    """保存自动发现的同步助手位置，兼容 .app 和开发环境下的 .py。"""
    if not path:
        return
    try:
        config = _read_path_config()
        resolved = os.path.abspath(os.path.expanduser(path))
        if str(config.get('SYNC_ASSISTANT_BUNDLE_PATH') or '') == resolved:
            return
        config['SYNC_ASSISTANT_BUNDLE_PATH'] = resolved
        if resolved.lower().endswith('.app'):
            config['SYNC_ASSISTANT_APP_PATH'] = resolved
        _write_path_config(config)
    except OSError:
        pass


def _launch_sync_assistant_app(app_path):
    """使用 macOS LaunchServices 在后台打开同步助手应用包。"""
    open_command = '/usr/bin/open'
    if sys.platform != 'darwin' or not os.path.isfile(open_command):
        return False
    try:
        subprocess.Popen(
            [open_command, '-g', app_path],
            cwd=os.path.dirname(app_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def launch_sync_assistant_silently():
    """v28 不再启动任何独立同步助手；桌面版直接使用内置网站 API 同步。"""
    return True


def trigger_sync_assistant_now():
    """唤醒内置同步；仅在旧版环境下回退到外部助手。"""
    if EMBEDDED_SYNC_INSTANCE is not None:
        EMBEDDED_SYNC_INSTANCE.wake()
        return True
    lock_path = os.path.join(
        os.path.expanduser('~'), '.restaurant_finance_sync', 'assistant.lock'
    )
    try:
        with open(lock_path, 'r', encoding='utf-8') as handle:
            pid = int(handle.read().strip())
        sigusr1 = getattr(__import__('signal'), 'SIGUSR1', None)
        if sigusr1 is not None:
            os.kill(pid, sigusr1)
            return True
    except (OSError, ValueError, ProcessLookupError):
        pass
    return launch_sync_assistant_silently()


def _unique_switch_archive_path(path, stamp):
    """Return a non-existing archive name next to a user workbook."""
    path = normalize_excel_path(path)
    folder, filename = os.path.split(path)
    stem, extension = os.path.splitext(filename)
    extension = extension or '.xlsx'
    base = os.path.join(folder, f'{stem}_切换内部Excel前_{stamp}{extension}')
    candidate = base
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(
            folder, f'{stem}_切换内部Excel前_{stamp}_{counter}{extension}'
        )
        counter += 1
    return candidate


def _switch_user_excel_target(old_active_path, selected_internal_path, year):
    """Choose a user-mirror target that can never overwrite the new internal store.

    Normally the new user Excel reuses the old visible workbook's original name after
    that old workbook has been archived. If the old visible path is itself the newly
    selected internal workbook, create a clearly separate user workbook next to it.
    """
    selected_internal_path = normalize_excel_path(selected_internal_path)
    if old_active_path:
        candidate = normalize_excel_path(old_active_path)
        if os.path.normcase(candidate) != os.path.normcase(selected_internal_path):
            return candidate

    folder, filename = os.path.split(selected_internal_path)
    stem, _extension = os.path.splitext(filename)
    stem = re.sub(r'^\(勿删\)\s*', '', stem).strip()
    stem = re.sub(
        r'[_\-\s]*(成本管理软件)?内部(数据|Excel)?$',
        '',
        stem,
        flags=re.IGNORECASE,
    ).strip('_- ') or '餐饮管家数据'
    candidate = os.path.join(folder, f'{stem}_用户数据_{int(year)}.xlsx')
    if os.path.normcase(candidate) == os.path.normcase(selected_internal_path):
        candidate = os.path.join(folder, f'餐饮管家用户数据_{int(year)}.xlsx')
    return normalize_excel_path(candidate)


def _registered_user_excel_paths():
    """Return all current annual mirror paths, active workbook first."""
    config = _read_path_config()
    candidates = []
    if FILE_PATH:
        candidates.append(FILE_PATH)
    year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
    if isinstance(year_map, dict):
        candidates.extend(year_map.values())
    result = []
    seen = set()
    internal = normalize_excel_path(INTERNAL_FILE_PATH) if INTERNAL_FILE_PATH else ''
    for value in candidates:
        try:
            path = normalize_excel_path(value)
        except ExcelAccessError:
            continue
        key = os.path.normcase(path)
        if key in seen or (internal and key == os.path.normcase(internal)):
            continue
        seen.add(key)
        result.append(path)
    return result


# ===================== 店铺与支付 =====================
class StorePaymentsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._paths = {slot: {key: '' for key in ('cert', 'key', 'pub', 'p12', 'readme')} for slot in ('A', 'B')}
        self._loaded_dataset_id = ''
        self._busy = False
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        title = QLabel('店铺设置')
        f = title.font(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        outer.addWidget(title)
        hint = QLabel('店名只改变显示名称；历史数据内部仍使用稳定的 A店/B店 字段。微信支付接口暂时停用。')
        hint.setWordWrap(True); hint.setStyleSheet('color:#5F6B7A;')
        outer.addWidget(hint)

        names = QGroupBox('店铺名称')
        form = QFormLayout(names)
        self.a_name = QLineEdit('A店'); self.b_name = QLineEdit('B店')
        self.auto_sync = QCheckBox('微信支付 API 暂停使用')
        self.auto_sync.setChecked(False)
        self.auto_sync.setVisible(False)
        self.save_names = QPushButton('保存店名')
        self.refresh_button = QPushButton('刷新网站配置')
        actions = QHBoxLayout(); actions.addWidget(self.save_names); actions.addWidget(self.refresh_button); actions.addStretch()
        form.addRow('店铺 A 显示名称', self.a_name); form.addRow('店铺 B 显示名称', self.b_name); form.addRow('', self.auto_sync); form.addRow('', actions)
        outer.addWidget(names)

        row = QHBoxLayout()
        self.store_boxes = {}
        for slot in ('A', 'B'):
            box = self._make_store_box(slot)
            self.store_boxes[slot] = box
            row.addWidget(box, 1)
        outer.addLayout(row)
        for box in self.store_boxes.values():
            box.setVisible(False)
        self.status = QLabel('正在等待网站连接……'); self.status.setWordWrap(True); self.status.setStyleSheet('color:#5F6B7A;')
        outer.addWidget(self.status); outer.addStretch()
        self.save_names.clicked.connect(self.save_store_names)
        self.refresh_button.clicked.connect(lambda: self.refresh_from_cloud(force=True))

    def _make_store_box(self, slot):
        box = QGroupBox(f'{slot}店 · 微信支付 API')
        layout = QVBoxLayout(box)
        form = QFormLayout()
        mchid = QLineEdit(); mchid.setPlaceholderText('基本账户信息 → 微信支付商户号')
        pubid = QLineEdit(); pubid.setPlaceholderText('PUB_KEY_ID_...')
        form.addRow('微信支付商户号', mchid); form.addRow('微信支付公钥 ID', pubid)
        layout.addLayout(form)
        entries = {}
        specs = [
            ('cert', 'apiclient_cert.pem', 'PEM (*.pem);;所有文件 (*)'),
            ('key', 'apiclient_key.pem', 'PEM (*.pem);;所有文件 (*)'),
            ('pub', 'pub_key.pem', 'PEM (*.pem);;所有文件 (*)'),
            ('p12', 'apiclient_cert.p12（可选）', 'P12 (*.p12);;所有文件 (*)'),
            ('readme', 'README_CN.txt（可选）', 'Text (*.txt);;所有文件 (*)'),
        ]
        for key, label, filt in specs:
            line = QLineEdit(); line.setReadOnly(True); line.setPlaceholderText('尚未选择')
            choose = QPushButton('选择')
            choose.clicked.connect(lambda _=False, sl=slot, k=key, w=line, flt=filt: self._choose_file(sl, k, w, flt))
            h = QHBoxLayout(); h.addWidget(line, 1); h.addWidget(choose)
            form_row = QFormLayout(); form_row.addRow(label, h); layout.addLayout(form_row)
            entries[key] = line
        buttons = QHBoxLayout()
        save = QPushButton('上传并保存'); test = QPushButton('验证微信 API'); delete = QPushButton('删除配置')
        delete.setStyleSheet('color:#B83232;')
        buttons.addWidget(save); buttons.addWidget(test); buttons.addWidget(delete); layout.addLayout(buttons)
        state = QLabel('未读取'); state.setWordWrap(True); state.setStyleSheet('color:#5F6B7A;'); layout.addWidget(state)
        save.clicked.connect(lambda _=False, sl=slot: self.upload_store(sl))
        test.clicked.connect(lambda _=False, sl=slot: self.test_store(sl))
        delete.clicked.connect(lambda _=False, sl=slot: self.delete_store(sl))
        box._mchid = mchid; box._pubid = pubid; box._entries = entries; box._state = state
        return box

    def _choose_file(self, slot, key, widget, filt):
        path, _ = QFileDialog.getOpenFileName(self, '选择微信支付文件', os.path.expanduser('~'), filt)
        if path:
            self._paths[slot][key] = path
            widget.setText(path)

    def _worker(self):
        if EMBEDDED_SYNC_INSTANCE is None:
            raise CloudSyncError('当前没有连接网站服务。')
        return EMBEDDED_SYNC_INSTANCE

    def _run_async(self, label, fn, success):
        if self._busy:
            return
        self._busy = True; self.status.setText(label)
        holder = {'done': False, 'value': None, 'error': None}
        def task():
            try: holder['value'] = fn()
            except Exception as exc: holder['error'] = exc
            finally: holder['done'] = True
        threading.Thread(target=task, daemon=True).start()
        def poll():
            if not holder['done']:
                QTimer.singleShot(120, poll); return
            self._busy = False
            if holder['error'] is not None:
                self.status.setText(f' {holder["error"]}')
                QMessageBox.warning(self, '操作失败', str(holder['error']))
                return
            success(holder['value'])
        poll()

    def refresh_from_cloud(self, force=False):
        worker = EMBEDDED_SYNC_INSTANCE
        if worker is None or not worker.snapshot().get('connected'):
            if force: self.status.setText('网站尚未连接。')
            return
        dataset_id = str(worker.snapshot().get('dataset_id') or '')
        if not force and dataset_id and dataset_id == self._loaded_dataset_id:
            return
        def ok(data):
            data = data or {}; self._loaded_dataset_id = dataset_id
            a = str(data.get('store_a_name') or 'A店'); b = str(data.get('store_b_name') or 'B店')
            self.a_name.setText(a); self.b_name.setText(b); self.auto_sync.setChecked(bool(data.get('wechat_auto_sync', True)))
            set_store_display_names(a, b)
            wechat = data.get('wechat') or {}
            for slot in ('A', 'B'):
                st = wechat.get(slot) or {}; box = self.store_boxes[slot]
                if st.get('configured'):
                    box._mchid.setText(str(st.get('mchid') or '')); box._pubid.setText(str(st.get('public_key_id') or ''))
                    serial = str(st.get('merchant_serial_no') or '')
                    files = st.get('files') or {}; present = '、'.join(name for name, yes in files.items() if yes)
                    box._state.setText(f' 已配置；商户证书序列号 {serial}' + (f'；已保存 {present}' if present else ''))
                else:
                    box._state.setText('未配置微信支付 API')
            self.status.setText(' 店铺与支付配置已从网站读取。')
            win = self.window()
            if hasattr(win, 'apply_store_names'): win.apply_store_names()
        self._run_async('正在读取网站店铺与支付配置……', lambda: self._worker().get_store_settings(), ok)

    def save_store_names(self):
        a = self.a_name.text().strip(); b = self.b_name.text().strip()
        if not a or not b:
            QMessageBox.warning(self, '店名错误', '两家店的名称都不能为空。'); return
        if a == b:
            QMessageBox.warning(self, '店名错误', '两家店的显示名称不能完全相同。'); return
        def ok(data):
            set_store_display_names(a, b); self._loaded_dataset_id = ''
            self.status.setText(' 店名已保存。')
            win = self.window()
            if hasattr(win, 'apply_store_names'): win.apply_store_names()
        self._run_async('正在保存店铺设置……', lambda: self._worker().save_store_settings(a, b, self.auto_sync.isChecked()), ok)

    def upload_store(self, slot):
        box = self.store_boxes[slot]; paths = self._paths[slot]
        if not box._mchid.text().strip() or not box._pubid.text().strip():
            QMessageBox.warning(self, '缺少参数', '请填写微信支付商户号和微信支付公钥 ID。'); return
        for key, label in (('cert','apiclient_cert.pem'),('key','apiclient_key.pem'),('pub','pub_key.pem')):
            if not paths.get(key):
                QMessageBox.warning(self, '缺少文件', f'请先选择 {label}。'); return
        def ok(data):
            st=(data or {}).get('status') or {}; box._state.setText(f" 已配置；商户证书序列号 {st.get('merchant_serial_no','')}")
            self.status.setText(f" {store_display_name(slot)}微信支付配置已安全上传到网站服务器。")
            self._loaded_dataset_id=''
        self._run_async(
            f'正在上传 {store_display_name(slot)} 微信支付文件……',
            lambda: self._worker().upload_store_wechat(slot, box._mchid.text().strip(), box._pubid.text().strip(), dict(paths)), ok,
        )

    def test_store(self, slot):
        day = (QDate.currentDate().addDays(-1)).toString('yyyy-MM-dd')
        def ok(data):
            self.store_boxes[slot]._state.setText(f" API 验证成功：{data.get('bill_date',day)}，读取 {data.get('rows',0)} 条账单明细。")
            self.status.setText(f' {store_display_name(slot)} 微信 API 可用。')
        self._run_async(f'正在验证 {store_display_name(slot)} 微信 API……', lambda: self._worker().test_store_wechat(slot, day), ok)

    def delete_store(self, slot):
        if QMessageBox.warning(self, '删除微信配置', f'确定删除 {store_display_name(slot)} 的微信支付配置吗？服务器上的证书和私钥会被删除。', QMessageBox.Yes|QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        def ok(_data):
            self.store_boxes[slot]._state.setText('未配置微信支付 API'); self.status.setText(f' {store_display_name(slot)} 微信配置已删除。'); self._loaded_dataset_id=''
        self._run_async('正在删除微信支付配置……', lambda: self._worker().delete_store_wechat(slot), ok)

    def set_admin_enabled(self, enabled):
        for box in self.store_boxes.values():
            for button in box.findChildren(QPushButton): button.setEnabled(bool(enabled))
        self.save_names.setEnabled(bool(enabled))
        self.refresh_button.setEnabled(True)


# ===================== 批量删除 / 整账覆盖 =====================
class DataManagementTab(QWidget):
    def __init__(self):
        super().__init__(); self._busy=False; self._build_ui()

    def _build_ui(self):
        layout=QVBoxLayout(self)
        title=QLabel('数据管理'); f=title.font(); f.setPointSize(15); f.setBold(True); title.setFont(f); layout.addWidget(title)
        danger=QLabel('批量删除和整账覆盖属于高风险操作。整套内部 Excel 覆盖另一个账本时，网站服务器会先自动备份目标账本，并要求两次确认。')
        danger.setWordWrap(True); danger.setStyleSheet('color:#8A3B12;'); layout.addWidget(danger)

        delete_box=QGroupBox('批量删除全部数据'); d=QGridLayout(delete_box)
        self.start=QDateEdit(QDate.currentDate()); self.start.setCalendarPopup(True)
        self.end=QDateEdit(QDate.currentDate()); self.end.setCalendarPopup(True)
        self.delete_range=QPushButton('删除日期区间全部数据'); self.delete_range.setStyleSheet('background:#B83232;color:white;font-weight:bold;')
        self.month_year=QComboBox(); self.month_year.addItems([str(y) for y in range(2020,2050)]); self.month_year.setCurrentText(str(QDate.currentDate().year()))
        self.month_num=QComboBox(); self.month_num.addItems([f'{m:02d}' for m in range(1,13)]); self.month_num.setCurrentText(f'{QDate.currentDate().month():02d}')
        self.delete_month=QPushButton('删除整月全部数据'); self.delete_month.setStyleSheet('background:#8B1E1E;color:white;font-weight:bold;')
        d.addWidget(QLabel('开始日期'),0,0); d.addWidget(self.start,0,1); d.addWidget(QLabel('结束日期'),0,2); d.addWidget(self.end,0,3); d.addWidget(self.delete_range,0,4)
        d.addWidget(QLabel('整月'),1,0); d.addWidget(self.month_year,1,1); d.addWidget(self.month_num,1,2); d.addWidget(self.delete_month,1,4)
        layout.addWidget(delete_box)

        overwrite=QGroupBox('用整套内部 Excel 覆盖另一个账本'); o=QGridLayout(overwrite)
        self.target_upload=QComboBox(); self.choose_internal=QPushButton('选择内部 Excel'); self.internal_path=QLineEdit(); self.internal_path.setReadOnly(True)
        self.upload_other=QPushButton('双重确认后整体覆盖'); self.upload_other.setStyleSheet('background:#B83232;color:white;font-weight:bold;')
        o.addWidget(QLabel('目标账本'),0,0); o.addWidget(self.target_upload,0,1,1,2); o.addWidget(self.choose_internal,1,0); o.addWidget(self.internal_path,1,1); o.addWidget(self.upload_other,1,2)
        layout.addWidget(overwrite)

        copy_box=QGroupBox('把当前账本整套复制覆盖到另一个账本'); c=QHBoxLayout(copy_box)
        self.target_copy=QComboBox(); self.copy_other=QPushButton('双重确认后复制覆盖'); self.copy_other.setStyleSheet('background:#B83232;color:white;font-weight:bold;')
        c.addWidget(QLabel('目标账本')); c.addWidget(self.target_copy,1); c.addWidget(self.copy_other); layout.addWidget(copy_box)
        self.refresh_targets=QPushButton('刷新目标账本列表'); self.status=QLabel(''); self.status.setWordWrap(True); layout.addWidget(self.refresh_targets); layout.addWidget(self.status); layout.addStretch()
        self.choose_internal.clicked.connect(self.pick_internal); self.delete_range.clicked.connect(self.delete_range_now); self.delete_month.clicked.connect(self.delete_month_now)
        self.upload_other.clicked.connect(self.upload_internal_other); self.copy_other.clicked.connect(self.copy_current_other); self.refresh_targets.clicked.connect(self.refresh_dataset_targets)

    def _worker(self):
        if EMBEDDED_SYNC_INSTANCE is None: raise CloudSyncError('当前没有连接网站服务。')
        return EMBEDDED_SYNC_INSTANCE

    def _run_async(self,label,fn,success):
        if self._busy:return
        self._busy=True; self.status.setText(label); holder={'done':False,'v':None,'e':None}
        def task():
            try: holder['v']=fn()
            except Exception as exc: holder['e']=exc
            finally: holder['done']=True
        threading.Thread(target=task,daemon=True).start()
        def poll():
            if not holder['done']: QTimer.singleShot(120,poll); return
            self._busy=False
            if holder['e'] is not None:
                self.status.setText(f' {holder["e"]}'); QMessageBox.warning(self,'操作失败',str(holder['e'])); return
            success(holder['v'])
        poll()

    def refresh_dataset_targets(self):
        worker=EMBEDDED_SYNC_INSTANCE
        if worker is None:return
        snap=worker.snapshot(); current=str(snap.get('dataset_id') or ''); datasets=list(snap.get('datasets') or [])
        for combo in (self.target_upload,self.target_copy):
            selected=str(combo.currentData() or ''); combo.clear()
            for item in datasets:
                did=str(item.get('id') or '')
                if did and did!=current: combo.addItem(str(item.get('name') or did),did)
            idx=combo.findData(selected)
            if idx>=0: combo.setCurrentIndex(idx)
        self.status.setText(f'可选择 {self.target_upload.count()} 个其它账本作为目标。')

    def pick_internal(self):
        path,_=QFileDialog.getOpenFileName(self,'选择整套内部 Excel',os.path.expanduser('~'),'Excel Files (*.xlsx)')
        if path:self.internal_path.setText(path)

    def _two_confirm(self, first, second):
        if QMessageBox.warning(self,'第一次确认',first,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return False
        return QMessageBox.warning(self,'第二次确认',second,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes

    def delete_range_now(self):
        start=self.start.date().toString('yyyy-MM-dd'); end=self.end.date().toString('yyyy-MM-dd')
        if end<start: QMessageBox.warning(self,'日期错误','结束日期不能早于开始日期。'); return
        if not self._two_confirm(f'确定删除 {start} 至 {end} 的全部日数据吗？', '再次确认：菜品、采购/成本明细以及该日期范围内的库存时间记录都会一起删除。') : return
        def ok(r): self.status.setText(f" 已删除 {r.get('deleted_days',0)} 天数据，并清理 {r.get('inventory_rows_removed',0)} 条库存时间记录。"); self._worker().wake()
        self._run_async('正在批量删除……',lambda:self._worker().bulk_delete_range(start,end),ok)

    def delete_month_now(self):
        month=f'{self.month_year.currentText()}-{self.month_num.currentText()}'
        if not self._two_confirm(f'确定删除 {month} 整月全部数据吗？', '再次确认：该月日数据、菜品、明细、固定成本和该月库存时间记录都会删除。'): return
        def ok(r): self.status.setText(f" {month} 已删除：{r.get('deleted_days',0)} 天、{r.get('deleted_months',0)} 条月记录。"); self._worker().wake()
        self._run_async('正在删除整月数据……',lambda:self._worker().delete_whole_month(month),ok)

    def _target(self,combo):
        did=str(combo.currentData() or ''); name=combo.currentText().strip(); return did,name

    def upload_internal_other(self):
        target_id,target_name=self._target(self.target_upload); path=self.internal_path.text().strip()
        if not target_id: QMessageBox.warning(self,'没有目标','请选择另一个目标账本。'); return
        if not path or not os.path.isfile(path): QMessageBox.warning(self,'没有文件','请选择存在的整套内部 Excel。'); return
        if not self._two_confirm(f'要用“{os.path.basename(path)}”整体覆盖目标账本“{target_name}”吗？', f'最后确认：目标账本“{target_name}”现有经营数据会被整体替换。服务器会先自动备份目标账本。'): return
        def ok(r): self.status.setText(f" 整体覆盖完成；目标账本备份：{r.get('backup_path','已创建')}")
        self._run_async('正在备份目标账本并上传内部 Excel……',lambda:self._worker().upload_internal_to_dataset(path,target_id),ok)

    def copy_current_other(self):
        target_id,target_name=self._target(self.target_copy); snap=self._worker().snapshot(); source_id=str(snap.get('dataset_id') or '')
        source=next((x for x in list(snap.get('datasets') or []) if str(x.get('id') or '')==source_id),{})
        source_name=str(source.get('name') or source_id)
        if not target_id: QMessageBox.warning(self,'没有目标','请选择另一个目标账本。'); return
        if not self._two_confirm(f'把当前账本“{source_name}”整套复制到“{target_name}”吗？', f'最后确认：目标账本“{target_name}”会被整体覆盖，服务器会先自动备份它。'): return
        def ok(r): self.status.setText(f" 整账复制完成；目标备份：{r.get('backup_path','已创建')}")
        self._run_async('正在备份目标账本并整账复制……',lambda:self._worker().copy_entire_ledger(target_id,source_name,target_name),ok)

    def set_admin_enabled(self, enabled):
        for w in (self.delete_range,self.delete_month,self.choose_internal,self.upload_other,self.copy_other): w.setEnabled(bool(enabled))
        self.refresh_targets.setEnabled(True)


# ===================== 修改记录（只读） =====================
class AuditLogTab(QWidget):
    """展示所有有修改权限账号（包括管理员）的修改记录。"""

    HEADERS = ['时间', '操作人', '操作', '数据集', '位置', '变更摘要']

    def __init__(self):
        super().__init__()
        self._role = ''
        self._row_keys = []
        self._cloud_rows = []
        # Cloud audit reads authenticate and make an HTTP request. They must
        # never run on the Qt event loop, otherwise opening this tab can freeze
        # the entire desktop app while a server is slow or reconnecting.
        self._cloud_loading = False
        self._cloud_refresh_queued = False
        layout = QVBoxLayout(self)
        title = QLabel('修改记录')
        font = title.font()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        hint = QLabel(
            '仅管理员或修改权限账号可见；记录保留 366 天。'
            '记录只缓存在内部 Excel，不写入用户 Excel。'
        )
        hint.setWordWrap(True)
        hint.setStyleSheet('color:#5F6B7A;')
        layout.addWidget(hint)
        filters = QHBoxLayout()
        filters.addWidget(QLabel('查看范围:'))
        self.filter_mode = QComboBox(); self.filter_mode.addItems(['全部', '按月', '按日'])
        self.filter_date = QDateEdit(QDate.currentDate()); self.filter_date.setCalendarPopup(True)
        self.filter_button = QPushButton('应用日期筛选')
        filters.addWidget(self.filter_mode); filters.addWidget(self.filter_date); filters.addWidget(self.filter_button)
        filters.addStretch(1); layout.addLayout(filters)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        # Audit history can contain thousands of long summaries.  Word-wrapped
        # cells combined with ResizeToContents make Qt recalculate every row's
        # height when the selection highlight changes; on macOS that can freeze
        # the whole window even before the delete button is pressed.  Fixed row
        # heights make selecting one record constant-time, while tooltips retain
        # the complete text for truncated cells.
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setAlternatingRowColors(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        horizontal_header = self.table.horizontalHeader()
        horizontal_header.setMinimumSectionSize(72)
        horizontal_header.setSectionResizeMode(QHeaderView.Interactive)
        horizontal_header.setSectionResizeMode(len(self.HEADERS) - 1, QHeaderView.Stretch)
        for column, width in enumerate((155, 105, 90, 135, 190)):
            self.table.setColumnWidth(column, width)
        vertical_header = self.table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.Fixed)
        vertical_header.setMinimumSectionSize(28)
        vertical_header.setDefaultSectionSize(32)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.status = QLabel('')
        self.status.setStyleSheet('color:#5F6B7A;')
        refresh = QPushButton('刷新记录')
        refresh.clicked.connect(self.refresh)
        self.filter_button.clicked.connect(self.refresh)
        self.delete_button = QPushButton('删除选中记录')
        self.delete_button.setToolTip('仅管理员可删除修改记录')
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setVisible(False)
        self.delete_button.setEnabled(False)
        footer.addWidget(self.status)
        footer.addStretch()
        footer.addWidget(self.delete_button)
        footer.addWidget(refresh)
        layout.addLayout(footer)

    def set_role(self, role):
        self._role = str(role or '')
        is_admin = self._role == 'admin'
        self.delete_button.setVisible(is_admin)
        self.delete_button.setEnabled(is_admin and self.table.currentRow() >= 0)

    def delete_selected(self):
        if self._role != 'admin':
            QMessageBox.warning(self, '权限不足', '只有管理员可以删除修改记录。')
            return
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self._row_keys):
            QMessageBox.information(self, '提示', '请先选中要删除的修改记录。')
            return
        key = str(self._row_keys[row_index] or '').strip()
        if not key:
            return
        if EMBEDDED_SYNC_INSTANCE:
            if QMessageBox.warning(
                self, '确认删除修改记录', '确定永久删除这条云端修改记录吗？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            # Deleting an audit row performs authentication and an HTTP
            # request. Keep both the request and its completion polling off
            # the Qt event loop; otherwise one slow server response freezes
            # the entire app after the user confirms deletion.
            worker = EMBEDDED_SYNC_INSTANCE
            # The user has already confirmed.  Remove the row immediately
            # while the irreversible server request runs in the background;
            # keep an exact copy for recovery if the server rejects it.
            rows_before_delete = [dict(item) for item in self._cloud_rows]
            if row_index < len(self._cloud_rows):
                self._cloud_rows.pop(row_index)
            self._row_keys.pop(row_index)
            self.table.removeRow(row_index)
            self.delete_button.setEnabled(False)
            self.status.setText('已从列表移除，正在后台确认删除…')
            result = {'done': False, 'error': None}

            def task():
                try:
                    worker.delete_audit_log(key)
                    dataset_id = str(worker.snapshot().get('dataset_id') or FIXED_CLOUD_DATASET_ID)
                    _delete_internal_audit_cache_row(dataset_id, key)
                except Exception as exc:
                    result['error'] = exc
                finally:
                    result['done'] = True

            threading.Thread(target=task, name='cloud-audit-delete', daemon=True).start()

            def finish():
                if not result['done']:
                    QTimer.singleShot(100, finish)
                    return
                if result['error'] is not None:
                    self._show_cloud_rows(rows_before_delete)
                    self.status.setText(f'云端删除失败，已恢复列表：{result["error"]}')
                    return
                self.status.setText(' 修改记录已删除，内部 Excel 缓存已更新。')

            QTimer.singleShot(0, finish)
            return
        if QMessageBox.warning(
            self,
            '确认删除修改记录',
            '删除后该条修改记录会从本地及云端同步数据中移除，且无法恢复。确定继续吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        global LAST_INTERNAL_MTIME_NS
        try:
            require_network_edit()
            path = normalize_excel_path(INTERNAL_FILE_PATH)
            if not path:
                raise ExcelAccessError('尚未选择内部 Excel，无法删除修改记录。')
            with internal_sync_lock(path):
                frames = _read_internal_frames(path)
                frame = frames.get('__global_records', pd.DataFrame())
                dataset_id = FIXED_CLOUD_DATASET_ID
                if not frame.empty and {'dataset_id', '记录类型'}.issubset(frame.columns):
                    matches = frame[
                        (frame['dataset_id'].astype(str) == str(dataset_id))
                        & (frame['记录类型'].astype(str) == key)
                    ]
                else:
                    matches = pd.DataFrame()
                if matches.empty:
                    raise ExcelAccessError('该修改记录已被其它设备删除，请刷新后重试。')
                frames['__global_records'] = _replace_internal_record(
                    frame, dataset_id, '记录类型', key
                )
                _prune_internal_audit_records(frames, dataset_id)
                meta = frames.get('__meta', pd.DataFrame(columns=INTERNAL_META_COLUMNS))
                meta = meta[meta['dataset_id'].astype(str) != dataset_id].copy()
                frames['__meta'] = pd.concat([
                    meta,
                    pd.DataFrame([{
                        'dataset_id': dataset_id,
                        'schema_version': 2,
                        'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    }]),
                ], ignore_index=True)
                _write_internal_frames(path, frames)
            APP_BASELINE_RECORD_HASHES.pop(('global', key), None)
            signature = _file_signature(path)
            LAST_INTERNAL_MTIME_NS = signature[1] if signature else None
            _set_internal_sync_pending(True)
            trigger_embedded_sync_now()
            self.status.setText(' 已删除，正在同步云端。')
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, '删除失败', str(exc))

    def _cloud_date_filter(self):
        mode = self.filter_mode.currentText()
        selected = self.filter_date.date()
        if mode == '按日':
            value = selected.toString('yyyy-MM-dd')
            return value, value
        if mode == '按月':
            return (
                QDate(selected.year(), selected.month(), 1).toString('yyyy-MM-dd'),
                QDate(selected.year(), selected.month(), selected.daysInMonth()).toString('yyyy-MM-dd'),
            )
        return '', ''

    def _show_cloud_rows(self, cloud_rows):
        self._cloud_rows = [dict(item) for item in cloud_rows]
        self._row_keys = [str(item.get('id') or '') for item in cloud_rows]
        previous_signal_state = self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(cloud_rows))
            for row_index, audit in enumerate(cloud_rows):
                stamp = str(audit.get('created_at') or audit.get('occurred_at') or '')
                try:
                    stamp = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except (TypeError, ValueError):
                    pass
                values = [
                    stamp or '—', str(audit.get('actor_label') or audit.get('actor_username') or '—'),
                    str(audit.get('action') or '修改'), str(audit.get('dataset_id') or '—'),
                    f"{audit.get('record_type') or ''}/{audit.get('record_key') or ''}".strip('/'),
                    str(audit.get('change_summary') or '历史记录未保存可比较字段'),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setToolTip(value)
                    self.table.setItem(row_index, column, item)
        finally:
            self.table.blockSignals(previous_signal_state)
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()
        self.delete_button.setEnabled(self._role == 'admin' and bool(self._row_keys))
        self.status.setText(f'当前筛选共 {len(cloud_rows)} 条云端修改记录。')

    def _refresh_cloud_async(self):
        if self._cloud_loading:
            self._cloud_refresh_queued = True
            return
        worker = EMBEDDED_SYNC_INSTANCE
        if worker is None:
            return
        start_date, end_date = self._cloud_date_filter()
        dataset_id = str(worker.snapshot().get('dataset_id') or FIXED_CLOUD_DATASET_ID)
        self._cloud_loading = True
        self.status.setText('正在从内部 Excel 读取修改记录缓存…')
        result = {
            'cache_ready': False, 'cache_shown': False, 'cached_rows': [],
            'done': False, 'rows': [], 'error': None,
        }

        def task():
            try:
                # Show the internal cache first.  The server is only used to
                # refresh it in the background, never to block this tab.
                result['cached_rows'] = _load_internal_audit_cache(dataset_id)
                result['cache_ready'] = True
                result['rows'] = worker.get_audit_logs()
                _replace_internal_audit_cache(dataset_id, result['rows'])
            except Exception as exc:
                result['error'] = exc
            finally:
                result['cache_ready'] = True
                result['done'] = True

        threading.Thread(target=task, name='cloud-audit-refresh', daemon=True).start()

        def finish():
            if result['cache_ready'] and not result['cache_shown']:
                result['cache_shown'] = True
                cached = _audit_cache_rows_for_dates(
                    result['cached_rows'], start_date, end_date
                )
                self._show_cloud_rows(cached)
                if not result['done']:
                    self.status.setText(
                        f'已从内部 Excel 显示 {len(cached)} 条缓存；正在后台检查服务器更新…'
                    )
            if not result['done']:
                QTimer.singleShot(100, finish)
                return
            self._cloud_loading = False
            if result['error'] is not None:
                cached_count = len(_audit_cache_rows_for_dates(
                    result['cached_rows'], start_date, end_date
                ))
                self.status.setText(
                    f'已显示内部 Excel 缓存 {cached_count} 条；服务器更新暂时失败：{result["error"]}'
                )
            else:
                self._show_cloud_rows(_audit_cache_rows_for_dates(
                    result['rows'], start_date, end_date
                ))
                self.status.setText(
                    f'修改记录已更新到内部 Excel，当前显示 {self.table.rowCount()} 条。'
                )
            if self._cloud_refresh_queued:
                self._cloud_refresh_queued = False
                self._refresh_cloud_async()

        QTimer.singleShot(0, finish)

    def refresh(self):
        if EMBEDDED_SYNC_INSTANCE and self._role in {'admin', 'editor'}:
            # This path never opens a user Excel.  It paints the hidden
            # internal cache first, then refreshes the cache in the background.
            self._refresh_cloud_async()
            return
        try:
            # Retention is enforced on reads as well as writes.  Otherwise a
            # read-only account could keep displaying and retaining expired
            # audit rows indefinitely.
            _prune_internal_audit_storage()
            with internal_sync_lock(normalize_excel_path(INTERNAL_FILE_PATH)):
                frames = _read_internal_frames(INTERNAL_FILE_PATH)
        except Exception as exc:
            self.table.setRowCount(0)
            self.status.setText(f'读取失败：{exc}')
            return
        snapshot = EMBEDDED_SYNC_INSTANCE.snapshot() if EMBEDDED_SYNC_INSTANCE else {}
        dataset_id = str(snapshot.get('dataset_id') or FIXED_CLOUD_DATASET_ID)
        rows = []
        frame = frames.get('__global_records', pd.DataFrame())
        for record in frame.to_dict(orient='records'):
            if str(record.get('dataset_id') or '').strip() != dataset_id:
                continue
            key = str(record.get('记录类型') or '').strip()
            if not key.startswith(INTERNAL_AUDIT_PREFIX):
                continue
            try:
                payload = exact_json_loads(str(record.get('payload_json') or '{}'))
                audit = payload.get('audit_log') or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            changed_at = str(audit.get('changed_at') or '')
            location = f"{audit.get('record_type') or ''}/{audit.get('record_key') or ''}".strip('/')
            summary = str(audit.get('source_screen') or '本地餐饮成本管家')
            rows.append((key, changed_at, str(audit.get('operator') or '—'), str(audit.get('operation') or '修改'), dataset_id, location, summary))
        rows.sort(key=lambda row: row[1], reverse=True)
        self._row_keys = [row[0] for row in rows]
        previous_signal_state = self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(rows))
            for row_index, row_values in enumerate(rows):
                values = row_values[1:]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setToolTip(value)
                    self.table.setItem(row_index, column, item)
        finally:
            self.table.blockSignals(previous_signal_state)
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()
        self.delete_button.setEnabled(self._role == 'admin' and bool(self._row_keys))
        self.status.setText(f'最近 366 天共 {len(rows)} 条记录。')


# ===================== 可用余额 / 股东借款 =====================
CASH_POSITION_RECORD_KEY = 'cash_position'
CASH_POSITION_ALIASES = ('cash_balance', 'base_balance')


def _load_global_record_payload(record_key, aliases=()):
    """Read a global record, accepting the names used by older desktop/web builds."""
    path = str(INTERNAL_FILE_PATH or '').strip()
    if not path or not os.path.exists(path):
        return {}
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
    for key in (record_key, *aliases):
        payload = _internal_payload_for_identity(
            frames, FIXED_CLOUD_DATASET_ID, ('global', key)
        )
        if isinstance(payload, dict):
            return payload
    return {}


def _save_global_record_payload(record_key, payload, source_screen='本地桌面版'):
    """Persist a global record and wake the embedded cloud synchronizer."""
    require_network_edit()
    path = normalize_excel_path(INTERNAL_FILE_PATH)
    if not path:
        raise ExcelAccessError('尚未选择内部 Excel，无法保存全局记录。')
    identity = ('global', str(record_key))
    with internal_sync_lock(path):
        frames = _read_internal_frames(path)
        before = _internal_payload_for_identity(frames, FIXED_CLOUD_DATASET_ID, identity)
        clean = dict(payload or {})
        clean['updated_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
        validate_money_changes(clean, before)
        clean = prepare_money_save(clean, before)
        payload_json, digest = _payload_and_hash(clean)
        frames['__global_records'] = _replace_internal_record(
            frames['__global_records'], FIXED_CLOUD_DATASET_ID,
            '记录类型', str(record_key), payload_json, digest,
        )
        if _desktop_cloud_role() != 'admin':
            _append_internal_audit_records(
                frames, FIXED_CLOUD_DATASET_ID, [identity], {identity: before}, source_screen
            )
        _prune_internal_audit_records(frames, FIXED_CLOUD_DATASET_ID)
        meta = frames.get('__meta', pd.DataFrame(columns=INTERNAL_META_COLUMNS))
        meta = meta[meta['dataset_id'].astype(str) != FIXED_CLOUD_DATASET_ID].copy()
        frames['__meta'] = pd.concat([meta, pd.DataFrame([{
            'dataset_id': FIXED_CLOUD_DATASET_ID,
            'schema_version': 2,
            'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }])], ignore_index=True)
        _write_internal_frames(path, frames)
    _set_internal_sync_pending(True)
    trigger_embedded_sync_now()
    return clean


def save_cash_position_record(payload):
    """Persist the cash-position baseline as a cloud-synchronised global record."""
    clean = dict(payload or {})
    clean['base_balance'] = money_amount(clean.get('base_balance', 0))
    clean['shareholder_loan'] = money_amount(clean.get('shareholder_loan', 0))
    clean['as_of_date'] = str(clean.get('as_of_date') or datetime.now().strftime('%Y-%m-%d'))[:10]
    return _save_global_record_payload(CASH_POSITION_RECORD_KEY, clean, '可用余额')


def _cash_position_flows(as_of_date):
    """Return income and expense flows after the configured cash baseline date."""
    try:
        start = datetime.strptime(str(as_of_date), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        start = datetime.now().date()
    income = expenses = 0
    today = datetime.now().date()
    try:
        daily = load_daily()
        for _, row in daily.iterrows():
            try:
                day = datetime.strptime(str(row.get('日期') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError):
                continue
            # Future-dated rows are often pre-created for planning.  They must
            # not change the amount of cash currently in hand.
            if day <= start or day > today:
                continue
            row_data = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            has_breakdown = any(
                money_value_was_entered(row_data.get(field, ''))
                for field in (
                    'A店现金', 'B店现金', 'A店微信增加', 'A店微信自动', 'A店微信覆盖',
                    'A店支付宝增加', 'A店支付宝覆盖', 'B店微信增加', 'B店微信自动',
                    'B店微信覆盖', 'B店支付宝增加', 'B店支付宝覆盖',
                    '学生外卖', 'A店外卖', 'B店外卖',
                )
            )
            revenue_raw = recalculate_revenue_fields(row_data).get('收益', 0) if has_breakdown else row.get('收益', '')
            revenue = money_amount(revenue_raw)
            if abs(revenue) <= Decimal('1e-9') and money_value_was_entered(row.get('总金额', '')):
                revenue = money_amount(row.get('总金额', 0))
            income += revenue
            expenses += sum(money_amount(row.get(column, 0)) for column in (
                '食材成本', '佐料成本', '水电', '其他', '手续费'
            ))
    except Exception:
        pass
    try:
        fixed = load_fixed_expenses()
        for _, row in fixed.iterrows():
            try:
                day = datetime.strptime(str(row.get('日期') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError):
                continue
            if start < day <= today and fixed_expense_includes_cash(row.get(FIXED_EXPENSE_CASH_COLUMN, '')):
                expenses += money_amount(row.get('金额', 0))
    except Exception:
        pass
    try:
        for row in load_inventory_entries():
            try:
                day = datetime.strptime(str(row.get('date') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError):
                continue
            if start < day <= today:
                expenses += money_amount(row.get('total', 0))
    except Exception:
        pass
    return income, expenses


def _cash_position_ledger(payload, month_filter=''):
    """Build the dated cash ledger, including event-sourced balance corrections.

    Legacy transactions have no ``mode`` and remain ordinary deltas.  A
    ``mode=force`` transaction is different: it records a point-in-time target
    balance, leaves income/expense as N/A, and never erases earlier history.
    On the same date all ordinary movements are applied before corrections;
    multiple corrections then follow ``created_at`` and ``id`` order.
    """
    payload = dict(payload or {})
    opening = money_amount(payload.get('base_balance', payload.get('opening_balance', 0)))
    opening_date = str(payload.get('as_of_date') or payload.get('opening_date') or datetime.now().strftime('%Y-%m-%d'))[:10]
    today = datetime.now().date()
    try:
        start = datetime.strptime(opening_date, '%Y-%m-%d').date()
    except ValueError:
        start = today
    entries = []
    loan_records = []

    def append_delta(day, kind, description, amount, **metadata):
        value = money_amount(amount)
        if abs(value) <= Decimal('1e-9'):
            return
        item = {
            'date': day.isoformat() if hasattr(day, 'isoformat') else str(day)[:10],
            'type': str(kind or '其它现金调整'),
            'description': str(description or kind or '其它现金调整'),
            'amount': value,
            'mode': 'delta',
        }
        item.update(metadata)
        entries.append(item)

    def correction_time_key(value):
        """Compare ISO timestamps chronologically, including ``Z``/offset forms."""
        try:
            stamp = datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
            return stamp.timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0

    try:
        for _, row in load_daily().iterrows():
            try: day = datetime.strptime(str(row.get('日期') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError): continue
            if day <= start or day > today: continue
            row_data = row.to_dict()
            revenue = money_amount(recalculate_revenue_fields(row_data).get('收益', row.get('收益', 0)))
            if abs(revenue) <= Decimal('1e-9') and money_value_was_entered(row.get('总金额', '')):
                revenue = money_amount(row.get('总金额', 0))
            append_delta(day, '营业收入', '当日收入', revenue)
            for column, label in [('食材成本','食材'),('佐料成本','佐料'),('水电','水电'),('其他','其它'),('手续费','手续费／抽成')]:
                amount = money_amount(row.get(column, 0))
                append_delta(day, '经营支出', label, -amount)
    except Exception:
        pass
    try:
        for _, row in load_fixed_expenses().iterrows():
            try: day = datetime.strptime(str(row.get('日期') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError): continue
            if start < day <= today and fixed_expense_includes_cash(row.get(FIXED_EXPENSE_CASH_COLUMN, '')):
                amount = money_amount(row.get('金额', 0))
                append_delta(day, '固定成本', str(row.get('明细') or row.get('类别') or '固定成本'), -amount)
    except Exception:
        pass
    try:
        for row in load_inventory_entries():
            try: day = datetime.strptime(str(row.get('date') or ''), '%Y-%m-%d').date()
            except (TypeError, ValueError): continue
            if start < day <= today:
                amount = money_amount(row.get('total', 0))
                append_delta(day, '入库支出', str(row.get('name') or '入库'), -amount)
    except Exception:
        pass
    legacy_loan = money_amount(payload.get('shareholder_loan', 0))
    if legacy_loan:
        append_delta(start, '向股东借款', '旧版股东借款', legacy_loan)
        loan_records.append((opening_date, legacy_loan))
    for item in payload.get('transactions', []) if isinstance(payload.get('transactions'), list) else []:
        if not isinstance(item, dict): continue
        try: day = datetime.strptime(str(item.get('date') or ''), '%Y-%m-%d').date()
        except (TypeError, ValueError): continue
        kind = str(item.get('type') or '其它现金调整')
        mode = 'force' if str(item.get('mode') or '').strip().lower() == 'force' or kind == '余额强制修改' else 'delta'
        amount = money_amount(item.get('amount', 0))
        if kind == '向股东借款' and mode == 'delta' and day <= today:
            loan_records.append((day.isoformat(), abs(amount)))
        if day < start or day > today:
            continue
        locked_value = item.get('system_locked', False)
        system_locked = locked_value is True or str(locked_value).strip().lower() in {'1', 'true', 'yes', 'on'}
        metadata = {
            'id': str(item.get('id') or ''),
            'created_at': str(item.get('created_at') or ''),
            'system_locked': system_locked,
        }
        if mode == 'force':
            entries.append({
                **metadata,
                'date': day.isoformat(),
                'type': '余额强制修改',
                'description': '余额强制修改',
                'amount': amount,
                'mode': 'force',
            })
        else:
            amount = abs(amount)
            if kind in {'现金支出', '其它现金支出'}:
                amount = -amount
            append_delta(day, kind, str(item.get('description') or kind), amount, **metadata)

    entries.sort(key=lambda item: (
        item['date'],
        1 if item.get('mode') == 'force' else 0,
        correction_time_key(item.get('created_at')) if item.get('mode') == 'force' else 0,
        str(item.get('id') or '') if item.get('mode') == 'force' else '',
        str(item.get('type') or ''),
        str(item.get('description') or ''),
    ))
    balance = opening
    for item in entries:
        if item.get('mode') == 'force':
            balance = money_amount(item.get('amount', 0))
        else:
            balance += money_amount(item.get('amount', 0))
        item['balance'] = balance

    selected_month = str(month_filter or today.strftime('%Y-%m'))[:7]
    try:
        selected_month_start = datetime.strptime(selected_month, '%Y-%m').date().replace(day=1)
    except (TypeError, ValueError):
        selected_month = today.strftime('%Y-%m')
        selected_month_start = today.replace(day=1)
    previous_month_balance = opening
    for item in entries:
        if item['date'] < selected_month_start.isoformat():
            previous_month_balance = money_amount(item.get('balance', previous_month_balance))

    visible = [item for item in entries if not month_filter or item['date'].startswith(month_filter)]
    selected_year = selected_month[:4]
    loan_total = sum(amount for _date, amount in loan_records)
    loan_month = sum(amount for date_text, amount in loan_records if date_text.startswith(selected_month))
    loan_year = sum(amount for date_text, amount in loan_records if date_text.startswith(selected_year))
    income = sum(
        money_amount(item['amount']) for item in entries
        if item.get('mode') != 'force' and money_amount(item['amount']) > 0
    )
    expenses = -sum(
        money_amount(item['amount']) for item in entries
        if item.get('mode') != 'force' and money_amount(item['amount']) < 0
    )
    return {
        'opening': opening,
        'opening_date': opening_date,
        'entries': visible,
        'current': balance,
        'previous_month_balance': previous_month_balance,
        'loan_total': loan_total,
        'loan_month': loan_month,
        'loan_year': loan_year,
        'income': income,
        'expenses': expenses,
    }


# Entry-role timing windows are kept as a small global record so every desktop
# installation sees the same deadlines after cloud synchronization.
ENTRY_WINDOWS_RECORD_KEY = 'entry_windows'
ENTRY_DETAIL_KEYS = ('食材', '佐料', '其它')
ENTRY_DETAIL_FIELD_MAP = {'食材': '食材明细', '佐料': '佐料明细', '其它': '其他明细'}
# These are the nine visible revenue inputs.  The aggregate revenue widgets are
# derived values and deliberately have no tenth clock.
ENTRY_INCOME_SLOTS = {
    'A店微信': {
        'primary': 'A店微信覆盖',
        'components': ('A店微信自动', 'A店微信增加'),
        'legacy': 'A',
    },
    'A店支付宝': {
        'primary': 'A店支付宝覆盖',
        'components': ('A店支付宝增加',),
        'legacy': 'A',
    },
    'A店现金': {'primary': 'A店现金', 'components': (), 'legacy': 'A'},
    'B店微信': {
        'primary': 'B店微信覆盖',
        'components': ('B店微信自动', 'B店微信增加'),
        'legacy': 'B',
    },
    'B店支付宝': {
        'primary': 'B店支付宝覆盖',
        'components': ('B店支付宝增加',),
        'legacy': 'B',
    },
    'B店现金': {'primary': 'B店现金', 'components': (), 'legacy': 'B'},
    '学生外卖': {'primary': '学生外卖', 'components': (), 'legacy': '_total'},
    'A店外卖': {'primary': 'A店外卖', 'components': (), 'legacy': 'A'},
    'B店外卖': {'primary': 'B店外卖', 'components': (), 'legacy': 'B'},
}
ENTRY_EDIT_WINDOW = timedelta(minutes=30)
ENTRY_ADD_WINDOW = timedelta(hours=12)


def _load_entry_windows():
    payload = _load_global_record_payload(ENTRY_WINDOWS_RECORD_KEY)
    windows = payload.get('days', {}) if isinstance(payload, dict) else {}
    windows = windows if isinstance(windows, dict) else {}
    if EMBEDDED_SYNC_INSTANCE is not None:
        snapshot = EMBEDDED_SYNC_INSTANCE.snapshot()
        if str(snapshot.get('customer_windows_dataset') or '') == str(snapshot.get('dataset_id') or ''):
            for day, customers in (snapshot.get('customer_entry_windows') or {}).items():
                if isinstance(customers, dict):
                    state = windows.setdefault(day, {})
                    current = state.setdefault('customers', {})
                    for key, value in customers.items():
                        # A pending local first save may precede the next cloud poll.
                        if value.get('saved_at') or not current.get(key, {}).get('saved_at'):
                            current[key] = dict(value)
    return windows


def _entry_customer_value(record, key):
    value = (record or {}).get('新客人数量' if key == 'new' else '总客人数', '')
    return money_value_was_entered(value), safe_float(value)


def _parse_entry_stamp(value):
    try:
        stamp = datetime.fromisoformat(str(value))
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        return stamp.astimezone()
    except (TypeError, ValueError, OverflowError):
        return None


def _entry_item_key(text):
    """Return a stable name key for a detail token, ignoring quantity/price."""
    token, _note = split_item_note(str(text or '').strip())
    token = re.sub(r'\s+\d+(?:\.\d+)?\s*(?:' + get_unit_pattern() + r')?\s+\d+(?:\.\d+)?$', '', token)
    token = re.sub(r'\s*\d+(?:\.\d+)?$', '', token)
    return re.sub(r'\s+', ' ', token).strip().casefold()


def _entry_record_fallback(record, fallback):
    """Use a legacy row timestamp when seeding missing timing metadata."""
    record = record if isinstance(record, dict) else {}
    for key in ('updated_at', '修改时间', '更新时间', 'created_at', '创建时间'):
        stamp = _parse_entry_stamp(record.get(key))
        if stamp is not None:
            return stamp
    return fallback


def _entry_item_signature(text):
    """Return the amount/unit suffix used to recognize a name-only rename."""
    clean, note = split_item_note(str(text or '').strip())
    match = re.search(
        r'(\d+(?:\.\d+)?\s*(?:' + get_unit_pattern() + r')?\s+\d+(?:\.\d+)?$)',
        clean,
    )
    if not match:
        match = re.search(r'(\d+(?:\.\d+)?$)', clean)
    suffix = match.group(1) if match else ''
    return re.sub(r'\s+', '', suffix).casefold() + '|' + re.sub(r'\s+', '', note).casefold()


def _entry_detail_token_list(text):
    return [
        raw.strip()
        for raw in re.split(r'[,，;；\n]+', str(text or ''))
        if raw.strip()
    ]


def _entry_detail_tokens(text):
    result = {}
    for index, raw in enumerate(re.split(r'[,，;；\n]+', str(text or ''))):
        token = raw.strip()
        if not token:
            continue
        key = _entry_item_key(token)
        if key:
            # Duplicate names must still receive independent edit clocks.
            if key in result:
                key = f'{key}#{index}'
            result[key] = token
    return result


def _entry_income_deadline(day_str):
    try:
        day = datetime.strptime(str(day_str), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None
    # Every still-empty revenue slot can first be saved until 11:00 on the
    # following calendar day.  A save at 10:59 then keeps its own correction
    # window open for the full thirty minutes, even past 11:00.
    next_day = day + timedelta(days=1)
    return datetime(next_day.year, next_day.month, next_day.day, 11, 0, tzinfo=datetime.now().astimezone().tzinfo)


def _entry_window_for_day(windows, day_str):
    value = windows.get(str(day_str))
    if not isinstance(value, dict):
        value = {}
        windows[str(day_str)] = value
    value.setdefault('details', {})
    value.setdefault('income', {})
    return value


def _entry_time_text(seconds):
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours}小时{minutes:02d}分{secs:02d}秒' if hours else f'{minutes}分{secs:02d}秒'


def _entry_income_slot_value(record, slot):
    """Return ``(was_filled, effective_value)`` for one visible revenue slot.

    Blank and an explicitly stored zero are intentionally different.  For the
    two online channels a manual override wins; otherwise their legacy
    automatic/addition components form the value displayed in the aggregate.
    """
    record = record if isinstance(record, dict) else {}
    spec = ENTRY_INCOME_SLOTS[slot]
    primary = spec['primary']
    if money_value_was_entered(record.get(primary, '')):
        return True, safe_float(record.get(primary, 0))
    components = tuple(spec.get('components') or ())
    entered = any(money_value_was_entered(record.get(field, '')) for field in components)
    return entered, sum(safe_float(record.get(field, 0)) for field in components)


def _entry_income_timing_state(income_state, slot, promote=False, allow_legacy=True):
    """Read a new nine-slot clock, cloning an old A/B/_total clock if needed."""
    if not isinstance(income_state, dict):
        return {}
    current = income_state.get(slot)
    if isinstance(current, dict):
        return current
    legacy_key = ENTRY_INCOME_SLOTS[slot].get('legacy') if allow_legacy else None
    legacy = income_state.get(legacy_key) if legacy_key else None
    if not isinstance(legacy, dict):
        return {}
    migrated = dict(legacy)
    if promote:
        income_state[slot] = migrated
    return migrated


def _entry_normalized_token(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip().casefold()


def _entry_detail_state_container(details_state, category):
    """Normalize both legacy name-keyed item maps and the current item list."""
    raw = details_state.get(category) if isinstance(details_state, dict) else None
    if isinstance(raw, dict) and isinstance(raw.get('items'), list):
        container = raw
    else:
        items = []
        if isinstance(raw, dict):
            for old_key, old_value in raw.items():
                if old_key in {'items', 'legacy_cost'} or not isinstance(old_value, dict):
                    continue
                text = str(old_value.get('text') or '').strip()
                if not text:
                    continue
                items.append({
                    'id': str(old_value.get('id') or uuid.uuid4()),
                    'text': text,
                    'saved_at': old_value.get('saved_at'),
                    'edit_deadline': old_value.get('edit_deadline'),
                    'active': old_value.get('active', True),
                })
        container = {'items': items}
        if isinstance(raw, dict) and isinstance(raw.get('legacy_cost'), dict):
            container['legacy_cost'] = dict(raw['legacy_cost'])
        details_state[category] = container
    clean_items = []
    for item in container.get('items', []):
        if not isinstance(item, dict) or not str(item.get('text') or '').strip():
            continue
        item['id'] = str(item.get('id') or uuid.uuid4())
        item['text'] = str(item.get('text') or '').strip()
        item['active'] = item.get('active', True) not in {False, 0, '0', 'false', 'False'}
        clean_items.append(item)
    container['items'] = clean_items
    return container


def _entry_seed_item_clock(item, fallback):
    saved_at = _parse_entry_stamp(item.get('saved_at')) or fallback
    deadline = _parse_entry_stamp(item.get('edit_deadline')) or saved_at + ENTRY_EDIT_WINDOW
    item['saved_at'] = saved_at.isoformat(timespec='seconds')
    item['edit_deadline'] = deadline.isoformat(timespec='seconds')
    return saved_at, deadline


def _entry_align_old_detail_items(container, old_tokens, fallback):
    """Align persisted item IDs/clocks to the tokens currently in the day row."""
    items = list(container.get('items') or [])
    active_indexes = [index for index, item in enumerate(items) if item.get('active', True)]
    used = set()
    aligned = []
    for token in old_tokens:
        exact = next((
            index for index in active_indexes
            if index not in used
            and _entry_normalized_token(items[index].get('text')) == _entry_normalized_token(token)
        ), None)
        matched = exact
        if matched is None:
            token_key = _entry_item_key(token)
            matched = next((
                index for index in active_indexes
                if index not in used and _entry_item_key(items[index].get('text')) == token_key
            ), None)
        if matched is None:
            item = {
                'id': str(uuid.uuid4()),
                'text': token,
                'saved_at': fallback.isoformat(timespec='seconds'),
                'edit_deadline': (fallback + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
                'active': True,
            }
            items.append(item)
            matched = len(items) - 1
        item = items[matched]
        used.add(matched)
        item['active'] = True
        # The workbook row is the content baseline; metadata supplies identity
        # and time, not a competing copy of the user's saved text.
        item['text'] = token
        _entry_seed_item_clock(item, fallback)
        aligned.append(item)
    for index in active_indexes:
        if index not in used:
            items[index]['active'] = False
    container['items'] = items
    return aligned


def _entry_match_detail_sequences(old_tokens, new_tokens):
    """Match unchanged/name-stable tokens first, then positional renames."""
    matches = {}
    used_new = set()
    for old_index, old_text in enumerate(old_tokens):
        target = next((
            new_index for new_index, new_text in enumerate(new_tokens)
            if new_index not in used_new
            and _entry_normalized_token(new_text) == _entry_normalized_token(old_text)
        ), None)
        if target is not None:
            matches[old_index] = target
            used_new.add(target)
    for old_index, old_text in enumerate(old_tokens):
        if old_index in matches:
            continue
        old_key = _entry_item_key(old_text)
        target = next((
            new_index for new_index, new_text in enumerate(new_tokens)
            if new_index not in used_new and _entry_item_key(new_text) == old_key
        ), None)
        if target is not None:
            matches[old_index] = target
            used_new.add(target)
    remaining_old = [index for index in range(len(old_tokens)) if index not in matches]
    remaining_new = [index for index in range(len(new_tokens)) if index not in used_new]
    # With a text-line editor there is no item ID in the visible text. Pairing
    # remaining tokens in order makes a within-window rename a modification,
    # while exact matches above prevent insertions/deletions from shifting all
    # subsequent clocks.
    for old_index, new_index in zip(remaining_old, remaining_new):
        matches[old_index] = new_index
        used_new.add(new_index)
    deleted = [index for index in range(len(old_tokens)) if index not in matches]
    added = [index for index in range(len(new_tokens)) if index not in used_new]
    return matches, deleted, added


def _entry_category_detail_start(state, category, fallback, old_record):
    """Return one category's independent 12-hour addition-window start."""
    starts = state.get('detail_started_at_by_category', {}) or {}
    stamp = _parse_entry_stamp(starts.get(category)) if isinstance(starts, dict) else None
    if stamp is not None:
        return stamp
    deadlines = state.get('detail_add_deadlines', {}) or {}
    deadline = _parse_entry_stamp(deadlines.get(category)) if isinstance(deadlines, dict) else None
    if deadline is not None:
        return deadline - ENTRY_ADD_WINDOW
    field = ENTRY_DETAIL_FIELD_MAP[category]
    cost_field = '其他' if category == '其它' else f'{category}成本'
    if _entry_detail_token_list(old_record.get(field, '')) or abs(safe_float(old_record.get(cost_field, 0))) > Decimal('1e-9'):
        # Migrate an old shared clock only for categories that already had data.
        return _parse_entry_stamp(state.get('details_started_at')) or fallback
    return None


def _entry_validate_and_update_windows(
    windows, day_str, old_record, new_data, mode='overwrite', now=None, enforce=True
):
    """Validate entry-role edits and update timing metadata.

    Food, seasoning and other each start their own 12-hour window on their
    first successful save. Every saved item has its own thirty-minute
    correction/deletion clock. The nine visible revenue inputs likewise have
    independent first-entry and correction clocks.
    """
    now = (now or datetime.now().astimezone()).astimezone()
    state = _entry_window_for_day(windows, day_str)
    details_state = state.setdefault('details', {})
    income_state = state.setdefault('income', {})
    old_record = old_record or {}
    new_data = new_data or {}
    customers = state.setdefault('customers', {})
    for key, label in (('new', '新客'), ('total', '总客数')):
        old_value = _entry_customer_value(old_record, key)
        new_value = _entry_customer_value(new_data, key)
        if old_value == new_value:
            continue
        clock = customers.setdefault(key, {})
        saved_at = _parse_entry_stamp(clock.get('saved_at'))
        deadline = _parse_entry_stamp(clock.get('edit_deadline'))
        if deadline is not None and enforce and now >= deadline:
            return state, f'{label}人数只能在首次保存后30分钟内修改或清空。'
        # For legacy rows without a cached server clock, defer the final lock
        # decision to the API instead of inventing a stale timestamp locally.
        if saved_at is None and new_value[0] and not old_value[0]:
            saved_at = now
            deadline = now + ENTRY_EDIT_WINDOW
        if saved_at is not None:
            clock.update(saved_at=saved_at.isoformat(timespec='seconds'), edit_deadline=(deadline or saved_at + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'))
    # Rows created before item-level metadata existed are migrated
    # conservatively: use their real timestamp when present, otherwise regard
    # their edit/add windows as already elapsed rather than granting a new one.
    item_fallback = _entry_record_fallback(old_record, now - ENTRY_ADD_WINDOW)
    income_fallback = _entry_record_fallback(old_record, now - ENTRY_EDIT_WINDOW)
    starts = state.setdefault('detail_started_at_by_category', {})
    deadlines = state.setdefault('detail_add_deadlines', {})

    for category in ENTRY_DETAIL_KEYS:
        category_start = _entry_category_detail_start(state, category, item_fallback, old_record)
        category_deadline = category_start + ENTRY_ADD_WINDOW if category_start is not None else None
        field = ENTRY_DETAIL_FIELD_MAP[category]
        cost_field = '其他' if category == '其它' else f'{category}成本'
        old_text = str(old_record.get(field) or '').strip()
        new_text = str(new_data.get(field) or '').strip()
        if mode == 'add' and old_text and new_text:
            new_text = f'{old_text}, {new_text}'
        old_tokens = _entry_detail_token_list(old_text)
        new_tokens = _entry_detail_token_list(new_text)
        old_cost = safe_float(old_record.get(cost_field, 0))
        new_cost = safe_float(new_data.get(cost_field, 0))
        container = _entry_detail_state_container(details_state, category)
        aligned = _entry_align_old_detail_items(container, old_tokens, item_fallback)
        matches, deleted, added = _entry_match_detail_sequences(old_tokens, new_tokens)

        for old_index, new_index in matches.items():
            item = aligned[old_index]
            _saved_at, edit_deadline = _entry_seed_item_clock(item, item_fallback)
            changed = _entry_normalized_token(old_tokens[old_index]) != _entry_normalized_token(new_tokens[new_index])
            if enforce and changed and now >= edit_deadline:
                return None, f'{category}项目“{old_tokens[old_index]}”已超过保存后30分钟，不能修改。'
            item['text'] = new_tokens[new_index]
            item['active'] = True

        for old_index in deleted:
            item = aligned[old_index]
            _saved_at, edit_deadline = _entry_seed_item_clock(item, item_fallback)
            if enforce and now >= edit_deadline:
                return None, f'{category}项目“{old_tokens[old_index]}”已超过保存后30分钟，不能删除。'
            item['active'] = False
            item['deleted_at'] = now.isoformat(timespec='seconds')

        for new_index in added:
            text = new_tokens[new_index]
            # A just-deleted item can be restored during its original edit
            # window without resetting the timer. Once that window is over, a
            # same-name purchase is a genuinely new item and uses the 12-hour
            # addition rule.
            reusable = None
            for item in container.get('items', []):
                if item.get('active', True):
                    continue
                _saved_at, edit_deadline = _entry_seed_item_clock(item, item_fallback)
                same_item = (
                    _entry_normalized_token(item.get('text')) == _entry_normalized_token(text)
                    or _entry_item_key(item.get('text')) == _entry_item_key(text)
                )
                if same_item and now < edit_deadline:
                    reusable = item
                    break
            if reusable is not None:
                reusable['text'] = text
                reusable['active'] = True
                reusable.pop('deleted_at', None)
                continue
            if enforce and category_deadline is not None and now >= category_deadline:
                return None, f'{category}新增已截止（该分类首个明细保存后12小时），请由有修改权限的账号录入。'
            if category_start is None:
                category_start = now
                category_deadline = now + ENTRY_ADD_WINDOW
            container['items'].append({
                'id': str(uuid.uuid4()),
                'text': text,
                'saved_at': now.isoformat(timespec='seconds'),
                'edit_deadline': (now + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
                'active': True,
            })

        # Very old files could contain only a numeric category total. Preserve
        # that single legacy amount under the same item-level correction rule.
        old_cost_present = abs(old_cost) > Decimal('1e-9') and not old_tokens
        new_cost_present = abs(new_cost) > Decimal('1e-9') and not new_tokens
        legacy_cost = container.get('legacy_cost')
        if old_cost_present and not isinstance(legacy_cost, dict):
            legacy_cost = {
                'saved_at': item_fallback.isoformat(timespec='seconds'),
                'edit_deadline': (item_fallback + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
                'value': old_cost,
                'active': True,
            }
            container['legacy_cost'] = legacy_cost
        if isinstance(legacy_cost, dict) and old_cost_present:
            _saved_at, edit_deadline = _entry_seed_item_clock(legacy_cost, item_fallback)
            legacy_changed = (not new_cost_present) or abs(old_cost - new_cost) > Decimal('1e-9')
            if enforce and legacy_changed and now >= edit_deadline:
                return None, f'{category}旧版金额已超过保存后30分钟，不能修改或删除。'
            legacy_cost['value'] = new_cost
            legacy_cost['active'] = new_cost_present
        elif new_cost_present:
            if enforce and category_deadline is not None and now >= category_deadline:
                return None, f'{category}新增已截止（该分类首个明细保存后12小时）。'
            if category_start is None:
                category_start = now
                category_deadline = now + ENTRY_ADD_WINDOW
            container['legacy_cost'] = {
                'saved_at': now.isoformat(timespec='seconds'),
                'edit_deadline': (now + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
                'value': new_cost,
                'active': True,
            }
        if category_start is not None:
            starts[category] = category_start.isoformat(timespec='seconds')
            deadlines[category] = category_deadline.isoformat(timespec='seconds')

    category_stamps = [_parse_entry_stamp(value) for value in starts.values()]
    category_stamps = [value for value in category_stamps if value is not None]
    if category_stamps:
        earliest = min(category_stamps)
        state['details_started_at'] = earliest.isoformat(timespec='seconds')
        state['details_add_deadline'] = (earliest + ENTRY_ADD_WINDOW).isoformat(timespec='seconds')

    # The nine revenue slots are independent.  Existing legacy A/B clocks are
    # cloned only for slots that already contain a value; from then on every
    # slot persists and advances separately.
    cutoff = _entry_income_deadline(day_str)
    for slot in ENTRY_INCOME_SLOTS:
        old_entered, old_value = _entry_income_slot_value(old_record, slot)
        new_entered, new_value = _entry_income_slot_value(new_data, slot)
        changed = old_entered != new_entered or abs(old_value - new_value) > Decimal('1e-9')
        slot_state = _entry_income_timing_state(
            income_state, slot, promote=old_entered, allow_legacy=old_entered
        )
        if not isinstance(slot_state, dict) or not slot_state:
            slot_state = income_state.setdefault(slot, {})
        saved_at = _parse_entry_stamp(slot_state.get('saved_at'))
        deadline = _parse_entry_stamp(slot_state.get('edit_deadline'))
        if saved_at is None and old_entered:
            saved_at = income_fallback
            deadline = saved_at + ENTRY_EDIT_WINDOW
            slot_state.update({
                'saved_at': saved_at.isoformat(timespec='seconds'),
                'edit_deadline': deadline.isoformat(timespec='seconds'),
            })
        if not changed:
            continue
        if saved_at is None and new_entered:
            if enforce and cutoff and now >= cutoff:
                return None, f'{_store_text(slot)}已超过第二天11:00首次录入截止时间，请由有修改权限的账号录入。'
            saved_at = now
            deadline = saved_at + ENTRY_EDIT_WINDOW
        elif saved_at is not None and enforce and deadline and now >= deadline:
            return None, f'{_store_text(slot)}已超过首次保存后30分钟，录入权限账号不能修改或清空。'
        if saved_at is None:
            # Blank -> blank has no clock. This branch is reachable only for
            # unusual legacy data and deliberately does not start one.
            continue
        slot_state.update({
            'saved_at': saved_at.isoformat(timespec='seconds'),
            'edit_deadline': (deadline or saved_at + ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),
        })
    return state, ''


def _entry_save_windows(windows):
    payload = {'days': windows, 'schema_version': 3}
    return _save_global_record_payload(ENTRY_WINDOWS_RECORD_KEY, payload, '录入时间窗')


def _entry_timing_relevant_change(old_record, new_record):
    """Return whether a detail or income value needs a timing check."""
    old_record = old_record or {}
    new_record = new_record or {}
    detail_changed = any(
        str(old_record.get(field) or '').strip() != str(new_record.get(field) or '').strip()
        for field in ENTRY_DETAIL_FIELD_MAP.values()
    )
    income_changed = False
    for slot in ENTRY_INCOME_SLOTS:
        old_entered, old_value = _entry_income_slot_value(old_record, slot)
        new_entered, new_value = _entry_income_slot_value(new_record, slot)
        if old_entered != new_entered or abs(old_value - new_value) > Decimal('1e-9'):
            income_changed = True
            break
    numeric_detail_changed = any(
        abs(safe_float(old_record.get(field, 0)) - safe_float(new_record.get(field, 0))) > Decimal('1e-9')
        for field in ('食材成本', '佐料成本', '其他')
    )
    customer_changed = any(_entry_customer_value(old_record, key) != _entry_customer_value(new_record, key) for key in ('new', 'total'))
    return detail_changed or income_changed or numeric_detail_changed or customer_changed


def _prepare_entry_timing(day_str, old_record, new_record, role):
    """Load and validate timing state; return ``(windows, error)``."""
    if str(role or '') != 'entry':
        return None, ''
    if not _entry_timing_relevant_change(old_record, new_record):
        return None, ''
    windows = _load_entry_windows()
    _state, error = _entry_validate_and_update_windows(
        windows,
        day_str,
        old_record,
        new_record,
        mode='overwrite',
        enforce=True,
    )
    return windows, error


class CashPositionTab(QWidget):
    """Dated cash ledger, visible only to admin/editor accounts."""

    def __init__(self):
        super().__init__()
        self._role = ''
        self._loading = False
        self._payload = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(10)
        title = QLabel('现金余额表'); title.setStyleSheet('font-size:16px;font-weight:600;'); outer.addWidget(title)
        summary = QFrame(); summary.setStyleSheet('QFrame { background:white; border:1px solid #d7dde5; border-radius:3px; } QLabel { border:0; }')
        summary_grid = QGridLayout(summary); summary_grid.setContentsMargins(12,10,12,10)
        self.current_label=QLabel('0.00 元'); self.previous_month_label=QLabel('0.00 元'); self.month_loan_label=QLabel('0.00 元'); self.year_loan_label=QLabel('0.00 元'); self.total_label=QLabel('0.00 元')
        for column,(caption,value) in enumerate([('现金余额',self.current_label),('上月结余',self.previous_month_label),('本月股东借款',self.month_loan_label),('本年股东借款',self.year_loan_label),('累计股东借款',self.total_label)]):
            label=QLabel(caption); label.setStyleSheet('color:#657486;'); value.setStyleSheet('font-size:16px;font-weight:600;')
            value.setAlignment(Qt.AlignRight|Qt.AlignVCenter); summary_grid.addWidget(label,0,column); summary_grid.addWidget(value,1,column); summary_grid.setColumnStretch(column,1)
        outer.addWidget(summary)
        toolbar=QHBoxLayout(); toolbar.addWidget(QLabel('明细月份'))
        self.filter_month=QDateEdit(QDate.currentDate()); self.filter_month.setCalendarPopup(True); self.filter_month.setDisplayFormat('yyyy-MM'); self.filter_month.setFixedWidth(128)
        self.add_item_button=QPushButton('新增项目'); self.delete_item_button=QPushButton('删除选中手工项目'); self.refresh_button=QPushButton('刷新现金流')
        self.correction_toggle=QPushButton('余额校正'); self.correction_toggle.setCheckable(True)
        for widget in (self.filter_month,self.add_item_button,self.delete_item_button,self.refresh_button):toolbar.addWidget(widget)
        toolbar.addStretch(); toolbar.addWidget(self.correction_toggle); outer.addLayout(toolbar)
        self.correction_form=QGroupBox('余额校正'); form=QGridLayout(self.correction_form)
        self.base_balance=QLineEdit(); self.base_balance.setPlaceholderText('校正后余额'); self.base_balance.setFixedWidth(180); self.base_balance.setAlignment(Qt.AlignRight)
        self.as_of_date=QDateEdit(QDate.currentDate()); self.as_of_date.setCalendarPopup(True); self.as_of_date.setFixedWidth(140)
        self.shareholder_loan=QLineEdit(); self.shareholder_loan.hide()
        self.save_button=QPushButton('保存余额修正'); self.save_button.setStyleSheet('background:#315f88;color:white;')
        form.addWidget(QLabel('校正后余额'),0,0); form.addWidget(self.base_balance,0,1); form.addWidget(QLabel('生效日期'),0,2); form.addWidget(self.as_of_date,0,3); form.addWidget(self.save_button,0,4); form.setColumnStretch(5,1)
        hint=QLabel('校正会追加一条余额记录，保留历史明细；之后的收入和支出继续自动计算。'); hint.setWordWrap(True); hint.setStyleSheet('color:#657486;'); form.addWidget(hint,1,0,1,6)
        self.correction_form.hide(); outer.addWidget(self.correction_form)
        self.correction_toggle.toggled.connect(self.correction_form.setVisible)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(['日期','类型','说明','收入','支出','余额']); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setAlternatingRowColors(True)
        header=self.table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.Interactive)
        for column,width in enumerate((130,160,360,150,150,160)):self.table.setColumnWidth(column,width)
        header.setSectionResizeMode(2,QHeaderView.Stretch); self.table.verticalHeader().setDefaultSectionSize(34); outer.addWidget(self.table,1)
        self.status=QLabel(''); self.status.setStyleSheet('color:#657486;'); outer.addWidget(self.status)
        self.save_button.clicked.connect(self.save); self.refresh_button.clicked.connect(self.refresh); self.filter_month.dateChanged.connect(lambda _date:self._render_summary()); self.add_item_button.clicked.connect(self.add_item); self.delete_item_button.clicked.connect(self.delete_item)

    def set_role(self, role):
        self._role = str(role or '')
        enabled = self._role in {'admin', 'editor'}
        self.save_button.setEnabled(enabled)
        self.base_balance.setReadOnly(not enabled)
        self.as_of_date.setEnabled(enabled)
        self.add_item_button.setEnabled(enabled); self.delete_item_button.setEnabled(enabled)

    def refresh(self):
        self._loading = True
        payload = _load_global_record_payload(CASH_POSITION_RECORD_KEY, CASH_POSITION_ALIASES)
        if not payload:
            # Migrate the most recent legacy daily field when available.
            try:
                daily = load_daily().sort_values('日期')
                for _, row in daily.iloc[::-1].iterrows():
                    if money_value_was_entered(row.get('可用余额', '')):
                        payload = {
                            'base_balance': money_amount(row.get('可用余额', 0)),
                            'as_of_date': str(row.get('日期') or datetime.now().strftime('%Y-%m-%d')),
                            'shareholder_loan': money_amount(row.get('向股东借款', 0)),
                        }
                        break
            except Exception:
                payload = {}
        date_text = str(payload.get('as_of_date') or payload.get('opening_date', '') or '')
        if payload.get('shareholder_loan') and not payload.get('transactions'):
            payload['transactions'] = [{
                'id': str(uuid.uuid4()),
                'date': date_text[:10],
                'type': '向股东借款',
                'amount': money_amount(payload.get('shareholder_loan')),
                'description': '旧版股东借款',
                'mode': 'delta',
                'system_locked': False,
            }]
            payload['shareholder_loan'] = 0
        self._payload = dict(payload or {})
        self._loading = False
        self._render_summary()
        # The input is a proposed target balance, not the historical opening
        # balance.  Showing the current result makes a correction easy without
        # allowing unsaved text to alter the ledger preview.
        self.base_balance.setText(f"{safe_float(getattr(self, '_last_current_balance', 0)):g}")

    def _render_summary(self):
        month = self.filter_month.date().toString('yyyy-MM')
        ledger = _cash_position_ledger(self._payload, month)
        current = ledger['current']
        self._last_current_balance = current
        self.current_label.setText(f'{current:,.2f} 元')
        self.current_label.setStyleSheet('font-size:16px;color:#B42318;font-weight:600;' if current < 0 else 'font-size:16px;color:#315f88;font-weight:600;')
        self.previous_month_label.setText(f"{ledger['previous_month_balance']:,.2f} 元")
        self.month_loan_label.setText(f"{ledger['loan_month']:,.2f} 元")
        self.year_loan_label.setText(f"{ledger['loan_year']:,.2f} 元")
        self.total_label.setText(f"{ledger['loan_total']:,.2f} 元")
        rows = list(reversed(ledger['entries'])); self.table.setRowCount(len(rows))
        for index, item in enumerate(rows):
            amount = money_amount(item.get('amount', 0))
            is_force = item.get('mode') == 'force'
            values = [
                item.get('date',''), item.get('type',''), item.get('description',''),
                '—' if is_force else (f'{amount:,.2f}' if amount > 0 else '—'),
                '—' if is_force else (f'{-amount:,.2f}' if amount < 0 else '—'),
                f"{money_amount(item.get('balance')):,.2f}",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column >= 3:cell.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                cell.setData(Qt.UserRole, str(item.get('id') or ''))
                cell.setData(Qt.UserRole + 1, bool(item.get('system_locked', False)))
                cell.setData(Qt.UserRole + 2, str(item.get('mode') or 'delta'))
                if is_force and item.get('system_locked', False):
                    cell.setToolTip('这条余额修正由上方“保存余额修正”产生，不能删除。')
                self.table.setItem(index, column, cell)

    def save(self):
        try:
            target_balance = money_input(self.base_balance.text())
        except ValueError as exc:
            QMessageBox.warning(self, '金额错误', str(exc))
            return
        if target_balance < 0:
            QMessageBox.warning(self, '金额错误', '强制修正余额不能为负数。')
            return
        try:
            correction_date = self.as_of_date.date().toString('yyyy-MM-dd')
            payload = dict(self._payload)
            if 'base_balance' not in payload:
                payload['base_balance'] = money_amount(payload.get('opening_balance', payload.get('可用余额', 0)))
            if not payload.get('as_of_date'):
                payload['as_of_date'] = str(payload.get('opening_date') or correction_date)[:10]
            transactions = list(payload.get('transactions') or [])
            transactions.append({
                'id': str(uuid.uuid4()),
                'date': correction_date,
                'type': '余额强制修改',
                'amount': target_balance,
                'description': '余额强制修改',
                'mode': 'force',
                'system_locked': True,
                'created_at': _inventory_operation_stamp([{'recorded_at': item.get('created_at')} for item in transactions]),
            })
            payload['transactions'] = transactions
            payload['shareholder_loan'] = 0
            save_cash_position_record(payload)
            self.status.setText('余额强制修改已记入明细，正在同步云端。')
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, '无法保存余额修正', str(exc))

    def add_item(self):
        dialog = QDialog(self); dialog.setWindowTitle('现金余额表 · 加一项')
        form = QFormLayout(dialog); date_edit = QDateEdit(QDate.currentDate()); date_edit.setCalendarPopup(True)
        kind = QComboBox(); kind.addItems(['向股东借款', '其它现金收入', '其它现金支出', '余额强制修改'])
        amount = QLineEdit(); description = QLineEdit(); description.setPlaceholderText('例如：张三借款')
        def update_kind_fields(text):
            is_force = text == '余额强制修改'
            amount.setPlaceholderText('修正后的余额' if is_force else '')
            description.setEnabled(not is_force)
            if is_force:
                description.setText('余额强制修改')
            elif description.text() == '余额强制修改':
                description.clear()
        kind.currentTextChanged.connect(update_kind_fields)
        save_button = QPushButton('保存这一项'); cancel_button = QPushButton('取消'); buttons = QHBoxLayout(); buttons.addStretch(); buttons.addWidget(cancel_button); buttons.addWidget(save_button)
        form.addRow('日期:', date_edit); form.addRow('类型:', kind); form.addRow('金额:', amount); form.addRow('说明:', description); form.addRow(buttons)
        cancel_button.clicked.connect(dialog.reject); save_button.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.Accepted: return
        try: value = money_input(amount.text())
        except ValueError:
            QMessageBox.warning(self, '金额错误', '请输入正确金额。'); return
        is_force = kind.currentText() == '余额强制修改'
        if value < 0 or (not is_force and value <= 0):
            QMessageBox.warning(self, '金额错误', '余额修正可以为 0，其它金额必须大于 0。'); return
        payload = dict(self._payload); transactions = list(payload.get('transactions') or [])
        transaction = {
            'id': str(uuid.uuid4()),
            'date': date_edit.date().toString('yyyy-MM-dd'),
            'type': kind.currentText(),
            'amount': value,
            'description': '余额强制修改' if is_force else (description.text().strip() or kind.currentText()),
            'mode': 'force' if is_force else 'delta',
            'system_locked': False,
            'created_at': _inventory_operation_stamp([{'recorded_at': item.get('created_at')} for item in transactions]),
        }
        transactions.append(transaction)
        if 'base_balance' not in payload:
            payload['base_balance'] = money_amount(payload.get('opening_balance', payload.get('可用余额', 0)))
        if not payload.get('as_of_date'):
            payload['as_of_date'] = transaction['date']
        payload.update({'shareholder_loan': 0, 'transactions': transactions})
        try:
            save_cash_position_record(payload); self.status.setText(f'已增加：{kind.currentText()} {value:,.2f} 元'); self.refresh()
        except Exception as exc: QMessageBox.warning(self, '保存失败', str(exc))

    def delete_item(self):
        row = self.table.currentRow()
        item_id = str(self.table.item(row, 0).data(Qt.UserRole) or '') if row >= 0 and self.table.item(row, 0) else ''
        if not item_id:
            QMessageBox.information(self, '提示', '自动生成的收入和支出不能删除；请选择手工增加的现金项目。'); return
        transaction = next(
            (item for item in self._payload.get('transactions', []) if str(item.get('id') or '') == item_id),
            None,
        )
        if not transaction:
            QMessageBox.information(self, '提示', '这条明细不是可删除的手工项目。'); return
        locked_value = transaction.get('system_locked', False)
        if locked_value is True or str(locked_value).strip().lower() in {'1', 'true', 'yes', 'on'}:
            QMessageBox.information(self, '不能删除', '通过上方“保存余额修正”产生的记录不能删除。'); return
        if QMessageBox.question(self, '确认删除', '确定删除这条手工现金项目吗？') != QMessageBox.Yes: return
        payload = dict(self._payload); payload['transactions'] = [item for item in payload.get('transactions', []) if str(item.get('id') or '') != item_id]; payload['shareholder_loan'] = 0
        try: save_cash_position_record(payload); self.refresh()
        except Exception as exc: QMessageBox.warning(self, '删除失败', str(exc))


# ===================== 管理员临时权限 =====================
class TemporaryPermissionTab(QWidget):
    def __init__(self):
        super().__init__(); self._grants = []
        layout = QVBoxLayout(self); title = QLabel('临时开放录入／修改权限'); title.setStyleSheet('font-size:16px;font-weight:700;'); layout.addWidget(title)
        hint = QLabel(
            '这是管理员的临时授权：不会改变账号原本的永久角色。只在所选账本、业务日期范围，以及实际生效时段内开放录入或修改；到期自动恢复原权限。'
        ); hint.setWordWrap(True); hint.setStyleSheet('color:#5F6B7A;'); layout.addWidget(hint)
        form = QGridLayout(); self.user_combo = QComboBox(); self.dataset_combo = QComboBox(); self.role_combo = QComboBox(); self.role_combo.addItem('录入权限','entry'); self.role_combo.addItem('修改权限','editor')
        today = QDate.currentDate(); self.business_start = QDateEdit(today); self.business_end = QDateEdit(today)
        self.starts_at = QDateTimeEdit(QDateTime.currentDateTime()); self.ends_at = QDateTimeEdit(QDateTime.currentDateTime().addSecs(7200))
        for widget in (self.business_start,self.business_end): widget.setCalendarPopup(True)
        for widget in (self.starts_at,self.ends_at): widget.setCalendarPopup(True); widget.setDisplayFormat('yyyy-MM-dd HH:mm')
        fields=[('账号',self.user_combo),('账本',self.dataset_combo),('权限',self.role_combo),('业务开始日期',self.business_start),('业务结束日期',self.business_end),('生效时间',self.starts_at),('结束时间',self.ends_at)]
        for index,(label,widget) in enumerate(fields): form.addWidget(QLabel(label+':'),index//4*2,index%4); form.addWidget(widget,index//4*2+1,index%4)
        layout.addLayout(form); actions=QHBoxLayout(); self.create_button=QPushButton('开放权限'); self.refresh_button=QPushButton('刷新'); self.delete_button=QPushButton('删除选中权限'); self.status=QLabel(''); actions.addWidget(self.create_button); actions.addWidget(self.delete_button); actions.addWidget(self.refresh_button); actions.addStretch(); actions.addWidget(self.status); layout.addLayout(actions)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(['账号','账本','权限','业务日期','生效时段','编号']); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); layout.addWidget(self.table,1)
        self.create_button.clicked.connect(self.create_permission); self.delete_button.clicked.connect(self.delete_permission); self.refresh_button.clicked.connect(self.refresh)

    def refresh(self):
        if not EMBEDDED_SYNC_INSTANCE: return
        try: data=EMBEDDED_SYNC_INSTANCE.list_temporary_permissions()
        except Exception as exc: self.status.setText(f'读取失败：{exc}'); return
        users=data.get('users') or []; datasets=data.get('datasets') or []; self._grants=data.get('grants') or []
        selected_user=self.user_combo.currentData(); selected_dataset=self.dataset_combo.currentData(); self.user_combo.clear(); self.dataset_combo.clear()
        for user in users:
            if user.get('role')!='admin' and not user.get('is_test'): self.user_combo.addItem(f"{user.get('display_name') or user.get('username')} ({user.get('username')})",user.get('id'))
        for dataset in datasets:
            if not dataset.get('is_test'): self.dataset_combo.addItem(str(dataset.get('name') or dataset.get('id')),dataset.get('id'))
        if selected_user: self.user_combo.setCurrentIndex(max(0,self.user_combo.findData(selected_user)))
        if selected_dataset: self.dataset_combo.setCurrentIndex(max(0,self.dataset_combo.findData(selected_dataset)))
        user_names={str(u.get('id')):str(u.get('display_name') or u.get('username')) for u in users}; dataset_names={str(d.get('id')):str(d.get('name') or d.get('id')) for d in datasets}; self.table.setRowCount(len(self._grants))
        for row,grant in enumerate(self._grants):
            values=[user_names.get(str(grant.get('user_id')),grant.get('user_id','')),dataset_names.get(str(grant.get('dataset_id')),grant.get('dataset_id','')),'修改权限' if grant.get('permission_role')=='editor' else '录入权限',f"{grant.get('business_start_date')} 至 {grant.get('business_end_date')}",f"{grant.get('starts_at')} 至 {grant.get('ends_at')}",grant.get('id','')]
            for column,value in enumerate(values): self.table.setItem(row,column,QTableWidgetItem(str(value)))
        self.status.setText(f'共 {len(self._grants)} 条临时权限。')

    def create_permission(self):
        if not self.user_combo.currentData() or not self.dataset_combo.currentData(): QMessageBox.warning(self,'资料不完整','请选择账号和账本。'); return
        payload={'user_id':str(self.user_combo.currentData()),'dataset_id':str(self.dataset_combo.currentData()),'permission_role':str(self.role_combo.currentData()),'business_start_date':self.business_start.date().toString('yyyy-MM-dd'),'business_end_date':self.business_end.date().toString('yyyy-MM-dd'),'starts_at':self.starts_at.dateTime().toUTC().toString(Qt.ISODate),'ends_at':self.ends_at.dateTime().toUTC().toString(Qt.ISODate)}
        try: EMBEDDED_SYNC_INSTANCE.create_temporary_permission(payload); self.refresh()
        except Exception as exc: QMessageBox.warning(self,'开放失败',str(exc))

    def delete_permission(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self._grants): QMessageBox.information(self,'提示','请先选择一条临时权限。'); return
        if QMessageBox.question(self,'确认删除','确定删除这条临时权限吗？')!=QMessageBox.Yes:return
        try: EMBEDDED_SYNC_INSTANCE.delete_temporary_permission(self._grants[row].get('id')); self.refresh()
        except Exception as exc: QMessageBox.warning(self,'删除失败',str(exc))


# ===================== 主窗口 =====================
class MainWindow(QMainWindow):
    def __init__(self):
        global PERMISSION_RECOVERY_CALLBACK, EMBEDDED_SYNC_INSTANCE, DESKTOP_OFFLINE_ONLY_SESSION
        super().__init__()
        self._update_window_title()
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())
        else:
            self.resize(1400, 950)

        self.tabs = FinanceWorkspace()
        self.dashboard = DashboardTab(
            self.read_other_excel,
            self.create_new_user_excel,
            self.ensure_user_excel_year,
            self.move_internal_excel,
            self.switch_internal_excel,
            self.merge_other_year_data,
        )
        self.ledger = LedgerTab()
        self.dish_detail = DishTab()
        self.ingredient_detail = PurchaseDetailTab("食材")
        self.spice_detail = PurchaseDetailTab("佐料")
        self.inventory = InventoryTab()
        self.more_stats = MoreStatsTab()
        self.store_payments = StorePaymentsTab()
        self.data_management = DataManagementTab()
        self.audit_log = AuditLogTab()
        self.cash_position = CashPositionTab()
        self.temporary_permissions = TemporaryPermissionTab()
        self.tabs.addTab(self.dashboard, " 经营仪表盘")
        self.tabs.addTab(self.ledger, " 记账本")
        self.tabs.addTab(self.store_payments, " 店铺设置")
        self.tabs.addTab(self.dish_detail, " 当日做出的菜品")
        self.tabs.addTab(self.ingredient_detail, " 食材明细")
        self.tabs.addTab(self.spice_detail, " 佐料明细")
        self.tabs.addTab(self.inventory, " 库存")
        self.tabs.addTab(self.more_stats, " 更多统计")
        self.tabs.addTab(self.data_management, " 数据管理")
        self.tabs.addTab(self.audit_log, " 修改记录")
        self.tabs.addTab(self.temporary_permissions, " 临时权限")
        # Keep the cash-position module at the top of the navigation while
        # retaining the historical tab order for the remaining modules below.
        self.tabs.insertTab(1, self.cash_position, " 现金余额表")
        # Resolve role visibility only after authentication.  Hiding the tab at
        # construction time prevents a viewer/entry account from seeing the
        # cash-position module during the first event-loop tick.
        self.cash_position_tab_index = self.tabs.indexOf(self.cash_position)
        self.tabs.setTabVisible(self.cash_position_tab_index, False)
        self.data_management_tab_index = self.tabs.indexOf(self.data_management)
        # Management is an administrator-only module.  Keep it hidden until
        # the login role has been resolved; this avoids exposing it briefly on
        # startup to entry/editor/viewer accounts.
        self.tabs.setTabVisible(self.data_management_tab_index, False)
        self.audit_tab_index = self.tabs.indexOf(self.audit_log)
        self.tabs.setTabVisible(self.audit_tab_index, False)
        self.grants_tab_index = self.tabs.indexOf(self.temporary_permissions)
        self.tabs.setTabVisible(self.grants_tab_index, False)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(8, 8, 8, 8)
        central_layout.setSpacing(7)
        central_layout.addWidget(self._build_connection_status_bar())
        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(12)
        workspace_layout.addWidget(self.tabs.build_navigation())
        workspace_layout.addWidget(self.tabs, 1)
        central_layout.addLayout(workspace_layout, 1)
        self.setCentralWidget(central)

        self._is_handling_tab_switch = False
        self.last_tab_index = self.tabs.currentIndex()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        # The global error handler uses the native Load/Create chooser after an
        # access preflight fails. Selecting a file there also gives a packaged macOS
        # app the best chance to recover its user-selected-file permission.
        PERMISSION_RECOVERY_CALLBACK = self.recover_user_excel
        self._align_ui_dates_to_active_year()
        self._refresh_for_current_excel()
        self.cash_position.refresh()
        self._last_internal_signature = _file_signature(INTERNAL_FILE_PATH)
        self._last_user_signature = _file_signature(FILE_PATH)
        self._sync_waiting_notice = False
        self._remote_replacement_prompt_active = False
        self._remote_replacement_error_shown = ""
        self._network_read_only = None
        self._network_widget_states = {}
        self._updating_dataset_combo = False
        self._offline_reminder_shown = False
        self._connection_disconnected_since = None
        self._last_user_activity_monotonic = time.monotonic()
        self._idle_logout_in_progress = False
        self._force_relogin_on_close = False
        self._cloud_file_refresh_busy = False
        self._embedded_sync = EmbeddedCloudSyncWorker()
        EMBEDDED_SYNC_INSTANCE = self._embedded_sync
        if DESKTOP_STARTUP_CONNECTION_STATE:
            # ``dict`` avoids sharing the mutable datasets list with the global
            # startup hand-off state; the worker will refresh it on its first
            # normal cycle.
            self._embedded_sync._set_state(**dict(DESKTOP_STARTUP_CONNECTION_STATE))
        if not DESKTOP_OFFLINE_ONLY_SESSION:
            self._embedded_sync.start()
        self._connection_ui_timer = QTimer(self)
        self._connection_ui_timer.setInterval(500)
        self._connection_ui_timer.timeout.connect(self._refresh_connection_status)
        self._connection_ui_timer.start()
        self._refresh_connection_status()
        # Count real user activity, including a tab/button click or a keyboard
        # action.  Background syncs deliberately do not touch this timer.
        QApplication.instance().installEventFilter(self)
        self._idle_logout_timer = QTimer(self)
        self._idle_logout_timer.setInterval(30_000)
        self._idle_logout_timer.timeout.connect(self._check_idle_logout)
        self._idle_logout_timer.start()
        # The first cloud login can legitimately take a few seconds.  Poll the
        # reminder state (with a generous delay) instead of firing one fixed
        # single-shot dialog that can race the first successful sync.
        self._offline_reminder_timer = QTimer(self)
        self._offline_reminder_timer.setInterval(5000)
        self._offline_reminder_timer.timeout.connect(self._show_offline_reminder_if_needed)
        self._offline_reminder_timer.start()
        QTimer.singleShot(1800, lambda: self.store_payments.refresh_from_cloud())
        QTimer.singleShot(1900, self.data_management.refresh_dataset_targets)
        poll_seconds = 2
        self._cloud_refresh_timer = QTimer(self)
        self._cloud_refresh_timer.setInterval(poll_seconds * 1000)
        self._cloud_refresh_timer.timeout.connect(self.check_cloud_sync_updates)
        self._cloud_refresh_timer.start()
        self.statusBar().showMessage('网站数据每 2 秒检查一次；断网时自动只读。', 5000)

    def eventFilter(self, watched, event):
        """Refresh the local 2-hour activity deadline without counting sync work."""
        if not self._idle_logout_in_progress:
            try:
                if event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress):
                    self._last_user_activity_monotonic = time.monotonic()
            except RuntimeError:
                pass
        return super().eventFilter(watched, event)

    def _check_idle_logout(self):
        if self._idle_logout_in_progress:
            return
        if time.monotonic() - self._last_user_activity_monotonic < DESKTOP_RELOGIN_SECONDS:
            return
        self._idle_logout_in_progress = True
        if hasattr(self, '_idle_logout_timer'):
            self._idle_logout_timer.stop()
        if hasattr(self, '_embedded_sync'):
            self._embedded_sync.stop()
        self.tabs.setEnabled(False)
        self.statusBar().showMessage('已连续 2 小时没有操作，请重新登录。')
        dialog = CloudSettingsDialog(self, require_login=True)
        if dialog.exec() != QDialog.Accepted:
            # Do not let a later app launch reuse the password from the old
            # session just because the user closed the sign-in dialog.
            self._force_relogin_on_close = True
            self.close()
            return
        global EMBEDDED_SYNC_INSTANCE, DESKTOP_OFFLINE_ONLY_SESSION
        DESKTOP_OFFLINE_ONLY_SESSION = bool(dialog.offline_requested)
        self._embedded_sync = EmbeddedCloudSyncWorker(interval_seconds=2.0)
        EMBEDDED_SYNC_INSTANCE = self._embedded_sync
        if not DESKTOP_OFFLINE_ONLY_SESSION:
            self._embedded_sync.start()
        self.tabs.setEnabled(True)
        self._network_read_only = None
        self._last_user_activity_monotonic = time.monotonic()
        self._idle_logout_in_progress = False
        self._offline_reminder_shown = False
        self._refresh_connection_status()
        if hasattr(self, '_idle_logout_timer'):
            self._idle_logout_timer.start()

    def _build_connection_status_bar(self):
        bar = QFrame()
        bar.setStyleSheet("QFrame { background:#ffffff; border:1px solid #d7dde5; border-radius:3px; } QLabel { border:none; }")
        rows = QVBoxLayout(bar)
        rows.setContentsMargins(10, 7, 10, 7)
        layout = QHBoxLayout(); layout.setSpacing(10)
        status = QHBoxLayout(); status.setSpacing(16)
        rows.addLayout(layout); rows.addLayout(status)
        title = QLabel("餐饮财务工作台")
        title.setStyleSheet("font-weight:700; color:#334155;")
        self.sync_assistant_status_label = QLabel(" 有互联网连接，正在连接服务器…")
        self.server_status_label = QLabel("尚未同步")
        self.network_metrics_label = QLabel("网络：等待首次测速")
        for label in (self.sync_assistant_status_label, self.server_status_label, self.network_metrics_label):
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(0)
            label.setStyleSheet(
                "color:#5F6B7A; background:#E8EDF3; border-radius:3px; "
                "padding:5px 11px; font-weight:700;"
            )
        self.sync_assistant_status_label.setToolTip("有互联网时会先显示正在连接服务器；内置同步每 2 秒自动重试")
        self.server_status_label.setToolTip("显示最近同步时间或连接错误")
        self.network_metrics_label.setToolTip("按最近一次从服务器读取账本数据的耗时与数据量计算；用于观察连接质量。")
        self.network_warning_label = QLabel('需要网络连接；当前仅可查看')
        self.network_warning_label.setStyleSheet('color:#B83232; font-weight:700; border:none;')
        self.cloud_dataset_combo = QComboBox()
        self.cloud_dataset_combo.setMinimumWidth(180)
        self.cloud_dataset_combo.setToolTip('当前云端账本')
        self.cloud_settings_button = QPushButton('网站连接设置')
        self.cloud_settings_button.clicked.connect(self.open_cloud_settings)
        self.account_label = QLabel(''); self.account_label.setStyleSheet('color:#657486; border:none;')
        self.version_label = QLabel(f'版本 {APP_VERSION}')
        self.version_label.setToolTip('当前桌面端版本号')
        self.version_label.setStyleSheet('color:#5F6B7A; font-weight:700; border:none; padding:4px 2px;')
        self.cloud_workbook_button = QPushButton('管理员 Excel')
        self.cloud_workbook_button.setToolTip('上传、合并或替换云端 Excel（仅管理员）')
        self.cloud_workbook_button.clicked.connect(self.open_cloud_workbooks)
        self.cloud_dataset_combo.currentIndexChanged.connect(self._dataset_selection_changed)
        layout.addWidget(title)
        layout.addWidget(self.sync_assistant_status_label)
        layout.addWidget(self.network_warning_label)
        layout.addStretch()
        self.cloud_dataset_label = QLabel('当前账本')
        layout.addWidget(self.cloud_dataset_label)
        layout.addWidget(self.cloud_dataset_combo)
        status.addWidget(self.server_status_label)
        status.addStretch()
        status.addWidget(self.network_metrics_label)
        layout.addWidget(self.account_label)
        layout.addWidget(self.cloud_workbook_button)
        layout.addWidget(self.cloud_settings_button)
        layout.addWidget(self.version_label)
        return bar

    @staticmethod
    def _set_connection_pill(label, text, state):
        if state is True:
            foreground, background = "#37634c", "#f2f6f3"
        elif state is False:
            foreground, background = "#9c3f39", "#faf3f2"
        else:
            foreground, background = "#667486", "#f1f4f7"
        label.setText(text)
        label.setStyleSheet(
            f"color:{foreground}; background:{background}; border-radius:3px; "
            "padding:5px 11px; font-weight:700;"
        )

    def _refresh_connection_status(self):
        snapshot = self._embedded_sync.snapshot()
        connected = bool(snapshot.get('connected'))
        if connected:
            self._connection_disconnected_since = None
        elif self._connection_disconnected_since is None:
            self._connection_disconnected_since = time.monotonic()
        role = str(snapshot.get('role') or '')
        current_widget = self.tabs.currentWidget()
        if current_widget is self.ledger:
            business_day = self.ledger.entry_date.date().toString('yyyy-MM-dd')
        else:
            date_widget = getattr(current_widget, 'date_edit', None)
            business_day = (date_widget.date().toString('yyyy-MM-dd')
                            if isinstance(date_widget, QDateEdit) else '')
        effective_role = _desktop_effective_role(business_day, snapshot) or role
        writable = connected and effective_role in {'admin', 'editor', 'entry'}
        failures = int(snapshot.get('consecutive_failures') or 0)
        connecting = bool(snapshot.get('configured')) and not connected and bool(snapshot.get('internet_connected')) and failures < OFFLINE_MIN_FAILURES
        syncing = bool(snapshot.get('syncing'))
        if connected:
            pill_text, pill_ok = (' 云端已连接 · 正在同步' if syncing else ' 云端已连接'), True
        elif connecting:
            pill_text, pill_ok = ' 有互联网连接，正在连接服务器', None
        else:
            pill_text, pill_ok = ' 云端未连接', False
        self._set_connection_pill(self.sync_assistant_status_label, pill_text, pill_ok)
        error = str(snapshot.get('error') or '')
        last_sync = str(snapshot.get('last_sync_at') or '')
        if connecting:
            status_text = '有互联网连接，正在连接服务器…'
        elif connected and error:
            status_text = error
        elif connected:
            status_text = ('正在后台同步…' if syncing else (f'最近同步 {last_sync}' if last_sync else '正在同步…'))
        else:
            status_text = error or '等待网络连接'
        self.server_status_label.setText(status_text[:80])
        self.server_status_label.setToolTip(status_text)
        latency = snapshot.get('latency_ms')
        speed = snapshot.get('download_kbps')
        if connected and latency is not None and speed is not None:
            metrics_text = f'网络：延迟 {int(latency):,} ms · 接收 {float(speed):,.1f} KB/s'
        elif connecting:
            metrics_text = '网络：正在测试延迟与速度…'
        else:
            metrics_text = '网络：等待服务器连接'
        self.network_metrics_label.setText(metrics_text)
        self.network_metrics_label.setToolTip(
            metrics_text + '（按最近一次账本读取计算，不是运营商带宽测速。）'
        )
        self.network_warning_label.setText(
            '正在连接服务器；当前仅可查看' if connecting
            else '账号为只读权限' if connected and effective_role not in {'admin', 'editor', 'entry'}
            else '需要网络连接；当前仅可查看'
        )
        self.network_warning_label.setVisible(not writable)
        datasets = list(snapshot.get('datasets') or [])
        ids = [str(item.get('id') or '') for item in datasets]
        current_ids = [str(self.cloud_dataset_combo.itemData(index) or '')
                       for index in range(self.cloud_dataset_combo.count())]
        if ids != current_ids:
            self._updating_dataset_combo = True
            self.cloud_dataset_combo.clear()
            for item in datasets:
                dataset_id = str(item.get('id') or '')
                self.cloud_dataset_combo.addItem(str(item.get('name') or dataset_id), dataset_id)
            self._updating_dataset_combo = False
        selected = str(snapshot.get('dataset_id') or '')
        index = self.cloud_dataset_combo.findData(selected)
        if index >= 0 and index != self.cloud_dataset_combo.currentIndex():
            self._updating_dataset_combo = True
            self.cloud_dataset_combo.setCurrentIndex(index)
            self._updating_dataset_combo = False
        self.cloud_dataset_combo.setVisible(True)
        self.cloud_dataset_label.setVisible(True)
        self.cloud_dataset_combo.setEnabled(connected and len(datasets)>1)
        role_label={'admin':'管理员','editor':'修改权限','entry':'录入权限','viewer':'只读权限'}.get(role,role or '未登录')
        self.account_label.setText(' · '.join(filter(None,(str(snapshot.get('username') or ''),role_label))))
        self._set_role_permissions(role)
        self.ledger.set_role(effective_role)
        self._set_network_read_only(not writable)
        self.inventory.correction_button.setEnabled(connected and role in {'admin','editor'})
        self.cloud_workbook_button.setVisible(connected and role == 'admin')
        if connected:
            self.store_payments.refresh_from_cloud()

    def _set_role_permissions(self, role):
        is_admin = str(role or '') == 'admin'
        for name in (
            'btn_create_user_excel', 'btn_move_internal',
            'btn_switch_internal',
        ):
            button = getattr(self.dashboard, name, None)
            if button is not None:
                button.setVisible(is_admin)
        # The legacy local merge used conflict-by-conflict replacement rules.
        # Keep one unambiguous additive merge entry in the cloud Excel dialog.
        self.dashboard.btn_merge_other_year.setVisible(False)
        self.store_payments.set_admin_enabled(is_admin)
        self.data_management.set_admin_enabled(is_admin)
        self.ledger.set_role(role)
        self.audit_log.set_role(role)
        can_use_cash = str(role or '') in {'admin', 'editor'}
        self.cash_position.set_role(role)
        cash_tab_index = self.tabs.indexOf(self.cash_position)
        self.tabs.setTabVisible(cash_tab_index, can_use_cash)
        if not can_use_cash and self.tabs.currentIndex() == cash_tab_index:
            self.tabs.setCurrentIndex(0)
        self.tabs.setTabVisible(self.data_management_tab_index, is_admin)
        self.tabs.setTabVisible(self.grants_tab_index, is_admin)
        if not is_admin and self.tabs.currentIndex() == self.data_management_tab_index:
            self.tabs.setCurrentIndex(0)
        can_view_audit = str(role or '') in {'admin', 'editor'}
        self.tabs.setTabVisible(self.audit_tab_index, can_view_audit)
        if is_admin and self.tabs.currentIndex() == self.grants_tab_index:
            self.temporary_permissions.refresh()

    def apply_store_names(self):
        apply_store_names_to_widget(self)
        # 图表和统计中的动态图例由刷新函数按当前店名重新生成。
        try:
            self.ledger.refresh_table()
            self.dashboard.refresh_all()
            self.more_stats.refresh()
        except Exception:
            pass

    def _show_offline_reminder_if_needed(self):
        snapshot = self._embedded_sync.snapshot()
        if self._offline_reminder_shown or snapshot.get('connected'):
            return
        # Only notify after a persistent, configured connection failure.  A
        # worker that is still performing its first login has no actionable
        # error yet and should not trigger a misleading warning.
        disconnected_since = self._connection_disconnected_since
        if (
            not snapshot.get('configured')
            or not snapshot.get('error')
            or disconnected_since is None
            or time.monotonic() - disconnected_since < OFFLINE_WARNING_DELAY_SECONDS
        ):
            return
        failures = int(snapshot.get('consecutive_failures') or 0)
        if failures < OFFLINE_MIN_FAILURES:
            return
        last_success = snapshot.get('last_success_monotonic')
        if last_success is not None:
            try:
                if time.monotonic() - float(last_success) < STARTUP_CONNECTION_GRACE_SECONDS:
                    return
            except (TypeError, ValueError):
                pass
        elif time.monotonic() - disconnected_since < STARTUP_CONNECTION_GRACE_SECONDS:
            # No successful cycle has completed yet. Give the initial login,
            # dataset fetch and record bootstrap the same grace period even if
            # several short requests have already failed.
            return
        self._offline_reminder_shown = True
        if hasattr(self, '_offline_reminder_timer'):
            self._offline_reminder_timer.stop()
        QMessageBox.warning(
            self, '需要网络连接',
            '当前没有连接到云端 API，软件已自动进入只读模式。\n\n'
            '请检查网络，或点击“网站连接设置”填写 API、用户名和密码。'
            '网络恢复后会自动重新连接并恢复可编辑状态。',
        )

    def open_cloud_settings(self):
        global DESKTOP_OFFLINE_ONLY_SESSION
        dialog = CloudSettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            if DESKTOP_OFFLINE_ONLY_SESSION:
                DESKTOP_OFFLINE_ONLY_SESSION = False
                self._embedded_sync.start()
            self._set_network_read_only(True)
            self._embedded_sync.wake()
            self.statusBar().showMessage('云同步设置已保存，正在登录并读取账本……')

    def open_cloud_workbooks(self):
        snapshot = self._embedded_sync.snapshot()
        if not snapshot.get('connected'):
            QMessageBox.warning(self, '需要网络连接', '当前没有网络连接，恢复连接后才能上传或合并 Excel。')
            return
        if str(snapshot.get('role') or '') != 'admin':
            QMessageBox.warning(self, '权限不足', '只有管理员账号可以上传或合并 Excel。')
            return
        CloudWorkbookDialog(self._embedded_sync, self).exec()

    def _dataset_selection_changed(self, _index):
        if self._updating_dataset_combo:
            return
        dataset_id = str(self.cloud_dataset_combo.currentData() or '')
        config = load_embedded_sync_config()
        old_id = str(config.get('dataset_id') or '')
        if not dataset_id or dataset_id == old_id:
            return
        if self._unsaved_sections():
            QMessageBox.warning(self, '请先保存', '切换账本前请先保存或撤销当前输入。')
            self._refresh_connection_status()
            return
        answer = QMessageBox.question(
            self, '切换云端账本',
            '切换后会先进入只读，并用所选云端账本刷新本地缓存。是否继续？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self._refresh_connection_status()
            return
        config['dataset_id'] = dataset_id
        save_embedded_sync_config(config)
        self.store_payments._loaded_dataset_id = ''
        self._set_network_read_only(True)
        self._embedded_sync.wake()
        QTimer.singleShot(700, lambda: self.store_payments.refresh_from_cloud(force=True))
        QTimer.singleShot(800, self.data_management.refresh_dataset_targets)

    @staticmethod
    def _inside_table(widget):
        parent = widget.parent()
        while parent is not None:
            if isinstance(parent, QTableWidget):
                return True
            parent = parent.parent()
        return False

    def _set_network_read_only(self, read_only):
        global NETWORK_ACCESS_DECIDED, NETWORK_EDIT_ALLOWED
        read_only = bool(read_only)
        NETWORK_ACCESS_DECIDED = True
        NETWORK_EDIT_ALLOWED = not read_only
        if self._network_read_only == read_only:
            # Role changes can re-enable a control while the connection state
            # remains unchanged. Re-apply the read-only mask in that case.
            if read_only:
                for widget, (kind, _value) in list(self._network_widget_states.items()):
                    try:
                        if kind == 'line':
                            widget.setReadOnly(True)
                        elif kind == 'text':
                            widget.setReadOnly(True)
                        elif kind == 'table':
                            widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
                        else:
                            widget.setEnabled(False)
                    except RuntimeError:
                        pass
            return
        mutation_words = re.compile(r'保存|提交|作废|品名更正|安全库存|新增|增加|删除|移动至|管理单位|修改|覆盖|创建新的|切换|合并|上传|导入|选择|重命名|采用')
        if read_only:
            states = {}
            for widget in self.tabs.findChildren(QLineEdit):
                if isinstance(widget.parent(), (QDateEdit, QComboBox)) or widget.property('financeSearch'):
                    continue
                states[widget] = ('line', widget.isReadOnly())
                widget.setReadOnly(True)
            for widget in self.tabs.findChildren(QTextEdit):
                states[widget] = ('text', widget.isReadOnly())
                widget.setReadOnly(True)
            for widget in self.tabs.findChildren(QTableWidget):
                states[widget] = ('table', widget.editTriggers())
                widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for widget in self.tabs.findChildren(QComboBox):
                if self._inside_table(widget):
                    states[widget] = ('enabled', widget.isEnabled())
                    widget.setEnabled(False)
            for widget in self.tabs.findChildren(QPushButton):
                if mutation_words.search(widget.text()):
                    states[widget] = ('enabled', widget.isEnabled())
                    widget.setEnabled(False)
            self._network_widget_states = states
        else:
            for widget, (kind, value) in list(self._network_widget_states.items()):
                try:
                    if kind in {'line', 'text'}:
                        widget.setReadOnly(value)
                    elif kind == 'table':
                        widget.setEditTriggers(value)
                    else:
                        widget.setEnabled(value)
                except RuntimeError:
                    pass
            self._network_widget_states = {}
        self._network_read_only = read_only

    def _update_window_title(self):
        year_text = f"{ACTIVE_USER_EXCEL_YEAR} 年" if ACTIVE_USER_EXCEL_YEAR else "未指定年度"
        self.setWindowTitle(f"餐饮成本管家 {APP_VERSION}  |  年度 Excel 镜像（{year_text}）: {FILE_PATH}")

    def _align_ui_dates_to_active_year(self):
        """Keep every date picker inside the currently active annual user workbook."""
        if not ACTIVE_USER_EXCEL_YEAR:
            return
        year = int(ACTIVE_USER_EXCEL_YEAR)

        def date_in_year(old_date):
            month = old_date.month()
            day = min(old_date.day(), calendar.monthrange(year, month)[1])
            return QDate(year, month, day)

        for widget in (
            self.dashboard.date_edit,
            self.ledger.entry_date,
            self.dish_detail.date_edit,
            self.ingredient_detail.date_edit,
            self.spice_detail.date_edit,
            self.inventory.date_edit,
        ):
            widget.blockSignals(True)
            widget.setDate(date_in_year(widget.date()))
            widget.blockSignals(False)
        for combo in (
            self.dashboard.year_combo,
            self.ledger.fixed_year_combo,
            self.ledger.hist_year_combo,
        ):
            combo.blockSignals(True)
            combo.setCurrentText(str(year))
            combo.blockSignals(False)

    def _unsaved_sections(self):
        """Return all editors that would lose in-memory data during a data-source switch."""
        unsaved_parts = []
        daily_dirty, fixed_dirty = self.ledger.has_unsaved_changes()
        if daily_dirty:
            unsaved_parts.append("【当日流水】")
        if fixed_dirty:
            unsaved_parts.append("【月度固定成本】")
        if self.dish_detail.has_unsaved_changes():
            unsaved_parts.append("【当日做出的菜品】")
        if self.ingredient_detail.has_unsaved_changes():
            unsaved_parts.append("【食材明细】")
        if self.spice_detail.has_unsaved_changes():
            unsaved_parts.append("【佐料明细】")
        if self.inventory.has_unsaved_changes():
            unsaved_parts.append("【库存单据】")
        return unsaved_parts

    def _refresh_for_current_excel(self):
        """Reload every tab after FILE_PATH has been switched successfully."""
        self.dashboard.refresh_all()
        self.ledger.auto_load_daily_record()
        self.ledger.load_fixed_cost_for_month()
        self.ledger.refresh_table()
        self.dish_detail.refresh_data()
        self.ingredient_detail.refresh_data()
        self.spice_detail.refresh_data()
        self.inventory.refresh_data()
        self.cash_position.refresh()
        self.more_stats.refresh()

    def _handle_remote_workbook_replacement(self):
        global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID
        config = _read_path_config()
        request_id = str(config.get(REMOTE_REPLACEMENT_REQUEST_ID_KEY) or '').strip()
        status = str(config.get(REMOTE_REPLACEMENT_STATUS_KEY) or '').strip()
        if not request_id:
            return False

        if status == 'pending':
            # 普通设备版会在这里停住并等待管理员决定；管理员版才显示确认弹窗。
            # 保留本机 Excel，绝不因另一台设备的请求而静默覆盖。
            if str(self._embedded_sync.snapshot().get('role') or '') != 'admin':
                self.statusBar().showMessage(
                    '已保留本机内部 Excel，正在等待管理员决定是否采用云端新账套。'
                )
                return True
            if self._remote_replacement_prompt_active or QApplication.activeModalWidget() is not None:
                return True
            unsaved = self._unsaved_sections()
            if unsaved:
                self.statusBar().showMessage(
                    '另一设备上传了新的内部 Excel；请先保存或撤销当前输入，再进行确认。'
                )
                return True
            info = config.get('REMOTE_WORKBOOK_REPLACEMENT_PAYLOAD', {})
            info = info if isinstance(info, dict) else {}
            source = str(info.get('source_hostname') or '另一设备')
            workbook_name = str(info.get('workbook_name') or '新的内部 Excel')
            self._remote_replacement_prompt_active = True
            try:
                answer = QMessageBox.question(
                    self,
                    '检测到云端更换了内部 Excel',
                    f'{source} 上传了另一份内部 Excel：\n{workbook_name}\n\n'
                    '是否改用这份云端新内部 Excel？\n\n'
                    '选择 Yes 后，程序会先把当前内部 Excel 改名备份，再下载云端新文件，'
                    '并让桌面版与网站数据同时改用新文件。',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    confirm = QMessageBox.warning(
                        self,
                        '再次确认',
                        '确认备份当前内部 Excel，并切换到另一设备上传的云端新内部 Excel？',
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if confirm == QMessageBox.Yes:
                        _update_remote_replacement_status(request_id, 'accepted', '主程序已确认采用云端新内部 Excel。')
                        trigger_sync_assistant_now()
                        self.statusBar().showMessage('正在备份旧内部 Excel并下载云端新内部 Excel……')
                    return True
                _update_remote_replacement_status(
                    request_id, 'declined',
                    '主程序拒绝采用云端新内部 Excel；为防止误覆盖，自动同步已停止。',
                )
                stop_sync_assistant_worker()
                QMessageBox.information(
                    self, '已保留当前内部 Excel',
                    '没有下载云端新内部 Excel。为避免两套整库继续互相覆盖，自动同步已停止。',
                )
                return True
            finally:
                self._remote_replacement_prompt_active = False

        if status in {'accepted', 'processing'}:
            self.statusBar().showMessage('正在备份旧内部 Excel并下载云端新内部 Excel……')
            return True

        if status == 'completed':
            new_path = str(config.get('REMOTE_WORKBOOK_REPLACEMENT_NEW_PATH') or config.get('INTERNAL_FILE_PATH') or '').strip()
            if not new_path:
                return True
            new_path = normalize_excel_path(new_path)
            if os.path.normcase(new_path) != os.path.normcase(normalize_excel_path(INTERNAL_FILE_PATH)):
                if self._unsaved_sections():
                    return True
                _activate_existing_internal_and_rebuild_users(new_path, FILE_PATH)
            else:
                # 路径相同但文件内容已整体替换，重新读取全部年度镜像和基线。
                _activate_existing_internal_and_rebuild_users(new_path, FILE_PATH)
            self._refresh_for_current_excel()
            self._last_internal_signature = _file_signature(INTERNAL_FILE_PATH)
            self._last_user_signature = _file_signature(FILE_PATH)
            config = _read_path_config()
            config[REMOTE_REPLACEMENT_STATUS_KEY] = 'applied'
            config['REMOTE_WORKBOOK_REPLACEMENT_APPLIED_AT'] = datetime.now().astimezone().isoformat(timespec='seconds')
            _write_path_config(config)
            backup = str(config.get('REMOTE_WORKBOOK_REPLACEMENT_BACKUP_PATH') or '')
            QMessageBox.information(
                self, '已切换到云端新内部 Excel',
                f'桌面版与网站数据已改用：\n{INTERNAL_FILE_PATH}'
                + (f'\n\n旧内部 Excel 备份：\n{backup}' if backup else ''),
            )
            return True

        if status == 'error':
            if self._remote_replacement_error_shown != request_id:
                self._remote_replacement_error_shown = request_id
                QMessageBox.warning(
                    self, '下载云端新内部 Excel 失败',
                    str(config.get('REMOTE_WORKBOOK_REPLACEMENT_MESSAGE') or '未知错误'),
                )
            return True
        return status == 'declined'

    def _refresh_visible_tab_after_cloud_update(self):
        """Hydrate only the page being viewed; never rebuild every chart on a tab click."""
        current = self.tabs.currentWidget()
        if current is self.dashboard:
            self.dashboard.refresh_all()
        elif current is self.ledger:
            self.ledger.auto_load_daily_record()
            self.ledger.load_fixed_cost_for_month()
            self.ledger.refresh_table()
        elif current is self.dish_detail:
            self.dish_detail.refresh_data()
        elif current is self.ingredient_detail:
            self.ingredient_detail.refresh_data()
        elif current is self.spice_detail:
            self.spice_detail.refresh_data()
        elif current is self.inventory:
            self.inventory.refresh_data()
        elif current is self.more_stats:
            self.more_stats.refresh()
        elif current is self.cash_position:
            self.cash_position.refresh()
        elif current is self.audit_log:
            self.audit_log.refresh()

    def _refresh_cloud_files_in_background(self):
        """Mirror cloud data without doing pandas/Excel I/O on the GUI thread."""
        if self._cloud_file_refresh_busy:
            return
        self._cloud_file_refresh_busy = True
        result = {'done': False, 'error': None}

        def task():
            try:
                sync_internal_to_user_excels(update_baseline=True)
            except Exception as exc:
                result['error'] = exc
            finally:
                result['done'] = True

        threading.Thread(target=task, name='cloud-mirror-refresh', daemon=True).start()

        def finish():
            if not result['done']:
                QTimer.singleShot(100, finish)
                return
            self._cloud_file_refresh_busy = False
            if result['error'] is not None:
                self.statusBar().showMessage(f'自动刷新暂缓：{result["error"]}')
                return
            self._last_internal_signature = _file_signature(INTERNAL_FILE_PATH)
            self._last_user_signature = _file_signature(FILE_PATH)
            self._sync_waiting_notice = False
            if self._unsaved_sections():
                self.statusBar().showMessage('云端数据已写入本地缓存；当前有未保存输入，暂不覆盖画面。')
                return
            self._refresh_visible_tab_after_cloud_update()
            self.statusBar().showMessage('已同步网站最新保存的数据。', 4000)

        QTimer.singleShot(0, finish)

    def check_cloud_sync_updates(self):
        """Every 2 seconds, follow server changes without blocking the UI."""
        if self._handle_remote_workbook_replacement():
            return
        connection = self._embedded_sync.snapshot()
        if not bool(connection.get('connected')):
            return
        if QApplication.activeModalWidget() is not None:
            return
        current_internal = _file_signature(INTERNAL_FILE_PATH)
        current_user = _file_signature(FILE_PATH)
        other_mirror_changed = any(
            _file_signature(path) != signature
            for path, signature in list(USER_MIRROR_SIGNATURES.items())
        )
        if (
            current_internal == self._last_internal_signature
            and current_user == self._last_user_signature
            and not other_mirror_changed
            and not _read_path_config().get('USER_MIRROR_SYNC_PENDING', False)
        ):
            return

        unsaved_parts = self._unsaved_sections()
        if unsaved_parts:
            self._sync_waiting_notice = True
            self.statusBar().showMessage(
                '云端或内部数据已有更新；当前有未保存输入，暂不刷新，也不会静默覆盖。'
            )
            return
        self._refresh_cloud_files_in_background()

    def ensure_user_excel_year(self, year, parent=None, allow_current_ledger_date_change=False,
                               ignore_current_ledger_unsaved=False):
        """Switch annual user files before a cross-year screen starts reading/writing."""
        year = int(year)
        if ACTIVE_USER_EXCEL_YEAR == year and FILE_PATH:
            try:
                validate_data_excel(FILE_PATH, require_write=True)
                return True
            except (ExcelAccessError, ExcelFormatError):
                # The current workbook may have been moved or lost its macOS TCC
                # grant while the app was open.  Use the same Load/Create flow as
                # startup instead of silently creating a replacement.
                unsaved_parts = self._unsaved_sections()
                if unsaved_parts:
                    QMessageBox.warning(
                        parent or self,
                        "请先处理未保存内容",
                        f"恢复用户 Excel 前，请先保存或撤销：{'、'.join(unsaved_parts)}。",
                    )
                    return False
                self.recover_user_excel()
                return bool(FILE_PATH and ACTIVE_USER_EXCEL_YEAR == year)
        unsaved_parts = self._unsaved_sections()
        # When the ledger date itself has just changed, its old values are about to be
        # reloaded; do not mistake that date-only transition for edited content.
        if ignore_current_ledger_unsaved or (
                allow_current_ledger_date_change and not self.ledger.daily_content_dirty()):
            unsaved_parts = [part for part in unsaved_parts if part != "【当日流水】"]
        if unsaved_parts:
            QMessageBox.warning(
                parent or self,
                "请先处理未保存内容",
                f"切换到 {year} 年用户 Excel 前，请先保存或撤销：{'、'.join(unsaved_parts)}。",
            )
            return False
        try:
            ensure_user_excel_for_year(year)
            self._update_window_title()
            self._align_ui_dates_to_active_year()
            return True
        except (ExcelAccessError, ExcelFormatError) as exc:
            if "找不到" in str(exc) or "访问权限" in str(exc) or "访问" in str(exc):
                self.recover_user_excel()
                return bool(FILE_PATH and ACTIVE_USER_EXCEL_YEAR == year)
            QMessageBox.warning(parent or self, "无法切换年度用户 Excel", str(exc))
            return False

    def reselect_user_excel_for_permission(self):
        """Open the native chooser to let macOS restore TCC file access for this app."""
        current_dir = os.path.dirname(FILE_PATH) if FILE_PATH else ''
        start_dir = current_dir if os.path.isdir(current_dir) else os.path.expanduser('~')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "重新选择用户 Excel 以获取访问权限",
            start_dir,
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        try:
            configure_active_user_excel(file_path)
            self._update_window_title()
            self._align_ui_dates_to_active_year()
            self._refresh_for_current_excel()
            QMessageBox.information(self, "访问权限已检查", "已重新选择年度 Excel，并按内部数据自动刷新。")
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, "仍无法访问 Excel", str(exc))

    def recover_user_excel(self):
        """Offer the same Load/Create recovery flow used during startup."""
        dialog = StartupDialog(self)
        if dialog.exec() != QDialog.Accepted or not dialog.selected_path:
            return
        try:
            configure_active_user_excel(dialog.selected_path)
            self._update_window_title()
            self._align_ui_dates_to_active_year()
            self._refresh_for_current_excel()
            QMessageBox.information(self, "年度 Excel 已启用", "已读取/创建年度 Excel，并按内部数据自动刷新。")
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, "无法启用用户 Excel", str(exc))

    def switch_internal_excel(self):
        """Choose a new authoritative source using the same simple startup flow."""
        unsaved_parts = self._unsaved_sections()
        if unsaved_parts:
            QMessageBox.warning(
                self,
                "请先处理未保存内容",
                f"重新选择数据来源前，请先保存或撤销：{'、'.join(unsaved_parts)}。",
            )
            return

        answer = QMessageBox.warning(
            self,
            "重新选择数据来源",
            "接下来请选择“使用用户 Excel”或“使用内部 Excel”。\n\n"
            "所选文件会成为新的本地事实来源；网站内置同步会直接使用新的内部 Excel 数据。\n"
            "取消选择不会修改任何文件。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        previous_user_path = FILE_PATH
        if not choose_startup_source_once(previous_user_path, self):
            return

        self._update_window_title()
        self._align_ui_dates_to_active_year()
        self._refresh_for_current_excel()
        self._last_internal_signature = _file_signature(INTERNAL_FILE_PATH)
        self._last_user_signature = _file_signature(FILE_PATH)
        launch_sync_assistant_silently()
        QMessageBox.information(
            self,
            "数据来源已切换",
            f"当前用户 Excel：\n{FILE_PATH}\n\n"
            f"当前内部 Excel：\n{INTERNAL_FILE_PATH}",
        )


    def move_internal_excel(self):
        """Move the internal workbook, optionally together with the active user workbook."""
        global FILE_PATH, INTERNAL_FILE_PATH
        source = normalize_excel_path(INTERNAL_FILE_PATH or get_internal_excel_path_from_config())
        try:
            validate_internal_excel(source, require_write=True)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, "无法移动内部 Excel", str(exc))
            return

        choice = QMessageBox(self)
        choice.setIcon(QMessageBox.Question)
        choice.setWindowTitle("选择要移动的内容")
        choice.setText("请选择要移动的文件：")
        choice.setInformativeText("选择后，下一步会让您选择目标文件夹。")
        move_internal_only = choice.addButton("只移动内部 Excel", QMessageBox.ActionRole)
        move_both = choice.addButton("内部 Excel 和用户 Excel 一起移动", QMessageBox.ActionRole)
        choice.addButton("取消", QMessageBox.RejectRole)
        choice.exec()
        if choice.clickedButton() not in (move_internal_only, move_both):
            return

        include_user_excel = choice.clickedButton() is move_both
        user_source = None
        if include_user_excel:
            try:
                user_source = validate_data_excel(FILE_PATH, require_write=True)
            except (ExcelAccessError, ExcelFormatError) as exc:
                QMessageBox.critical(self, "无法移动用户 Excel", str(exc))
                return

        target_dir = QFileDialog.getExistingDirectory(
            self, "选择要移动到的文件夹", os.path.dirname(source)
        )
        if not target_dir:
            return

        items = [("internal", "内部 Excel", source)]
        if include_user_excel:
            items.append(("user", "用户 Excel", user_source))
        targets = [
            (role, label, item_source,
             normalize_excel_path(os.path.join(target_dir, os.path.basename(item_source))))
            for role, label, item_source in items
        ]
        to_move = [item for item in targets if item[2] != item[3]]
        if not to_move:
            QMessageBox.information(self, "无需移动", "所选 Excel 已经在这个文件夹中。")
            return

        target_sources = {}
        for role, label, item_source, target in to_move:
            previous_source = target_sources.get(target)
            if previous_source and previous_source != item_source:
                QMessageBox.warning(
                    self,
                    "文件名冲突",
                    f"内部 Excel 和用户 Excel 的文件名相同，无法同时放入这个文件夹。\n\n"
                    f"请先选择另一个文件夹。",
                )
                return
            target_sources[target] = item_source

        existing_targets = [target for _, _, _, target in to_move if os.path.exists(target)]
        if existing_targets:
            QMessageBox.warning(
                self,
                "不会覆盖已有文件",
                "目标文件已经存在：\n"
                + "\n".join(existing_targets)
                + "\n\n请先选择另一个文件夹。",
            )
            return

        copied = []
        removed = []
        try:
            with internal_sync_lock(source):
                validate_internal_excel(source, require_write=True)
                for role, label, item_source, target in to_move:
                    ensure_excel_writable(target)
                    shutil.copy2(item_source, target)
                    if role == "internal":
                        validate_internal_excel(target, require_write=True)
                    else:
                        validate_data_excel(target, require_write=True)
                    copied.append((role, label, item_source, target))

                for item in to_move:
                    os.remove(item[2])
                    removed.append(item)

                for role, label, item_source, target in removed:
                    if role == "internal":
                        INTERNAL_FILE_PATH = target
                    else:
                        FILE_PATH = target
                save_path_config(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, INTERNAL_FILE_PATH)
            if any(role == "internal" for role, _label, _source, _target in removed):
                launch_sync_assistant_silently()
            moved_labels = "、".join(label for _, label, _, _ in removed)
            QMessageBox.information(
                self,
                "移动完成",
                f"已移动：{moved_labels}\n\n目标文件夹：\n{target_dir}",
            )
        except (OSError, ExcelAccessError, ExcelFormatError) as exc:
            # Remove copies whose original file was not removed. If a source was
            # already removed before the failure, keep its valid copy and adopt it.
            for role, label, item_source, target in copied:
                if item_source not in {item[2] for item in removed}:
                    try:
                        if os.path.exists(target) and os.path.exists(item_source):
                            os.remove(target)
                    except OSError:
                        pass
            for role, label, item_source, target in removed:
                if role == "internal":
                    INTERNAL_FILE_PATH = target
                else:
                    FILE_PATH = target
            if removed:
                save_path_config(FILE_PATH, ACTIVE_USER_EXCEL_YEAR, INTERNAL_FILE_PATH)
            QMessageBox.critical(self, "移动 Excel 失败", str(exc))

    def _choose_merge_conflict_policy(self, imported_year, current_year, mixed_dates):
        """Show the requested three-way choice for dates mixed across years."""
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle("发现混入其它年份的数据")
        message.setText(
            f"导入的{imported_year % 100:02d}年用户 Excel 中，发现了属于"
            f"{current_year % 100:02d}年的日期。"
        )
        message.setInformativeText("请点击“Show Details”查看具体日期，然后选择如何处理这些日期。")
        message.setDetailedText(
            "混入的日期：\n" + "\n".join(f"• {day}" for day in mixed_dates)
        )
        use_imported = message.addButton(
            f"使用{imported_year % 100:02d}年Excel数据", QMessageBox.ActionRole
        )
        use_current = message.addButton(
            f"使用{current_year % 100:02d}年Excel数据", QMessageBox.ActionRole
        )
        merge_data = message.addButton(
            "合并数据 (包括但不限于，购买的食材，收入 都会叠加)", QMessageBox.ActionRole
        )
        message.exec()
        clicked = message.clickedButton()
        if clicked is use_imported:
            return "imported"
        if clicked is use_current:
            return "current"
        if clicked is merge_data:
            return "merge"
        return None


    @staticmethod
    def _merge_payload_summary(record_type, payload):
        """Return a compact human-readable summary for the conflict picker."""
        payload = payload if isinstance(payload, dict) else {}
        if record_type == 'day':
            daily = payload.get('daily') if isinstance(payload.get('daily'), list) else []
            fixed = payload.get('fixed_expenses') if isinstance(payload.get('fixed_expenses'), list) else []
            dishes = payload.get('dishes') if isinstance(payload.get('dishes'), list) else []

            def total(records, key):
                value = 0
                for record in records:
                    try:
                        raw = str(record.get(key, '')).replace(',', '').strip()
                        if raw:
                            value += decimal_number(raw)
                    except (TypeError, ValueError):
                        continue
                return value

            parts = []
            if daily:
                revenue = total(daily, '收益')
                parts.append(f'日账 {len(daily)} 行，收入 {revenue:.2f}')
            if fixed:
                amount = total(fixed, '金额')
                parts.append(f'固定支出 {len(fixed)} 行，金额 {amount:.2f}')
            if dishes:
                cost = total(dishes, '总成本')
                parts.append(f'菜品 {len(dishes)} 行，成本 {cost:.2f}')
            return '；'.join(parts) or '有数据'

        rows = payload.get('monthly_fixed') if isinstance(payload.get('monthly_fixed'), list) else []
        return f'月度固定成本 {len(rows)} 行' if rows else '有数据'

    def _choose_merge_record_versions(
        self,
        duplicate_days,
        duplicate_months,
        current_payloads,
        imported_payloads,
    ):
        """Let the user choose the winning version for every overlapping key."""
        records = [
            ('day', key, current_payloads[('day', key)], imported_payloads[('day', key)])
            for key in duplicate_days
        ] + [
            ('month', key, current_payloads[('month', key)], imported_payloads[('month', key)])
            for key in duplicate_months
        ]
        if not records:
            return {}

        dialog = QDialog(self)
        dialog.setWindowTitle('选择重复数据使用哪个版本')
        dialog.resize(1080, min(760, 250 + len(records) * 42))
        layout = QVBoxLayout(dialog)

        title = QLabel(
            '以下日期或月份在当前内部 Excel 和所选用户 Excel 中都存在数据。\n'
            '请逐条勾选要保留的版本；默认保留当前内部数据。'
        )
        title.setWordWrap(True)
        title.setStyleSheet('font-size: 14px; font-weight: bold; padding: 6px;')
        layout.addWidget(title)

        table = QTableWidget(len(records), 6, dialog)
        table.setHorizontalHeaderLabels([
            '类型', '日期 / 月份', '当前内部版本摘要', '导入文件版本摘要',
            '保留当前', '使用导入',
        ])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)

        choice_boxes = {}

        def centered_checkbox(label=''):
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(2, 0, 2, 0)
            wrapper_layout.setAlignment(Qt.AlignCenter)
            box = QCheckBox(label)
            wrapper_layout.addWidget(box)
            return wrapper, box

        def bind_exclusive(first, second):
            guard = {'busy': False}

            def first_changed(checked):
                if guard['busy']:
                    return
                guard['busy'] = True
                try:
                    if checked:
                        second.setChecked(False)
                    elif not second.isChecked():
                        first.setChecked(True)
                finally:
                    guard['busy'] = False

            def second_changed(checked):
                if guard['busy']:
                    return
                guard['busy'] = True
                try:
                    if checked:
                        first.setChecked(False)
                    elif not first.isChecked():
                        second.setChecked(True)
                finally:
                    guard['busy'] = False

            first.toggled.connect(first_changed)
            second.toggled.connect(second_changed)

        for row, (record_type, key, current_payload, imported_payload) in enumerate(records):
            kind_text = '日期' if record_type == 'day' else '月份'
            table.setItem(row, 0, QTableWidgetItem(kind_text))
            table.setItem(row, 1, QTableWidgetItem(key))
            table.setItem(
                row, 2,
                QTableWidgetItem(self._merge_payload_summary(record_type, current_payload)),
            )
            table.setItem(
                row, 3,
                QTableWidgetItem(self._merge_payload_summary(record_type, imported_payload)),
            )
            current_widget, current_box = centered_checkbox()
            imported_widget, imported_box = centered_checkbox()
            bind_exclusive(current_box, imported_box)
            current_box.setChecked(True)
            table.setCellWidget(row, 4, current_widget)
            table.setCellWidget(row, 5, imported_widget)
            choice_boxes[(record_type, key)] = (current_box, imported_box)

        layout.addWidget(table, 1)

        bulk_layout = QHBoxLayout()
        keep_all = QPushButton('全部保留当前版本')
        import_all = QPushButton('全部使用导入版本')
        bulk_layout.addWidget(keep_all)
        bulk_layout.addWidget(import_all)
        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        cancel_button = QPushButton('取消')
        confirm_button = QPushButton('确认并继续合并')
        confirm_button.setDefault(True)
        action_layout.addWidget(cancel_button)
        action_layout.addWidget(confirm_button)
        layout.addLayout(action_layout)

        def select_all(use_imported):
            for current_box, imported_box in choice_boxes.values():
                if use_imported:
                    imported_box.setChecked(True)
                else:
                    current_box.setChecked(True)

        keep_all.clicked.connect(lambda: select_all(False))
        import_all.clicked.connect(lambda: select_all(True))
        cancel_button.clicked.connect(dialog.reject)
        confirm_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.Accepted:
            return None
        return {
            identity: ('imported' if imported_box.isChecked() else 'current')
            for identity, (current_box, imported_box) in choice_boxes.items()
        }

    def merge_other_year_data(self):
        """Merge any user workbook and resolve every overlapping key explicitly."""
        unsaved_parts = self._unsaved_sections()
        if unsaved_parts:
            QMessageBox.warning(
                self,
                '请先处理未保存内容',
                f"合并用户 Excel 前，请先保存或撤销：{'、'.join(unsaved_parts)}。",
            )
            return
        if not INTERNAL_FILE_PATH:
            QMessageBox.warning(self, '没有内部 Excel', '当前还没有可用的内部 Excel，请先完成初始化。')
            return
        try:
            validate_internal_excel(INTERNAL_FILE_PATH, require_write=True)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, '无法使用内部 Excel', str(exc))
            return

        start_dir = os.path.dirname(FILE_PATH) if FILE_PATH else os.path.expanduser('~')
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择要合并的用户 Excel', start_dir, 'Excel Files (*.xlsx)'
        )
        if not file_path:
            return

        try:
            file_path = validate_data_excel(file_path, require_write=False)
            selected_key = os.path.normcase(normalize_excel_path(file_path))
            if INTERNAL_FILE_PATH and selected_key == os.path.normcase(normalize_excel_path(INTERNAL_FILE_PATH)):
                QMessageBox.warning(self, '文件选择错误', '不能把内部 Excel 当作用户 Excel 合并。')
                return
            registered = {
                os.path.normcase(path) for path in _registered_user_excel_paths()
            }
            if selected_key in registered:
                QMessageBox.information(
                    self,
                    '无需合并',
                    '所选文件已经是当前账套登记的用户 Excel，不需要再次合并。',
                )
                return
            imported_frames = _read_user_workbook_frames(file_path)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, '无法读取要合并的 Excel', str(exc))
            return

        imported_dates = set()
        for sheet_name, date_column in DATE_SHEET_COLUMNS.items():
            imported_dates.update(
                _valid_date_keys(imported_frames[sheet_name], date_column)
            )
        imported_months = _valid_month_keys(imported_frames['monthly_fixed'])
        imported_global_has_data = any(
            not imported_frames[name].empty
            for name in ('ingredients', 'fixed_categories')
        )
        if not imported_dates and not imported_months and not imported_global_has_data:
            QMessageBox.information(self, '没有可合并数据', '所选用户 Excel 中没有找到可合并的数据。')
            return

        destination_dataset = str(ACTIVE_DATASET_ID or FIXED_CLOUD_DATASET_ID)
        archived_files = []
        internal_backup = None

        try:
            with internal_sync_lock(INTERNAL_FILE_PATH):
                before_internal = _read_internal_frames(INTERNAL_FILE_PATH)

            existing_dates = {
                str(value).strip()
                for value in before_internal['__day_records'].loc[
                    before_internal['__day_records']['dataset_id'].astype(str) == destination_dataset,
                    '日期',
                ]
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value).strip())
            }
            existing_months = {
                str(value).strip()
                for value in before_internal['__month_records'].loc[
                    before_internal['__month_records']['dataset_id'].astype(str) == destination_dataset,
                    '月份',
                ]
                if re.fullmatch(r'\d{4}-\d{2}', str(value).strip())
            }

            duplicate_days = sorted(existing_dates & imported_dates)
            duplicate_months = sorted(existing_months & imported_months)
            current_payloads = {}
            imported_payloads = {}
            for day in duplicate_days:
                current_payloads[('day', day)] = _internal_payload_for_identity(
                    before_internal, destination_dataset, ('day', day)
                ) or {}
                imported_payloads[('day', day)] = _user_day_payload(imported_frames, day)
            for month in duplicate_months:
                current_payloads[('month', month)] = _internal_payload_for_identity(
                    before_internal, destination_dataset, ('month', month)
                ) or {}
                imported_payloads[('month', month)] = _user_month_payload(imported_frames, month)

            choices = self._choose_merge_record_versions(
                duplicate_days,
                duplicate_months,
                current_payloads,
                imported_payloads,
            )
            if choices is None:
                return

            days_to_import = set(imported_dates - set(duplicate_days))
            months_to_import = set(imported_months - set(duplicate_months))
            for day in duplicate_days:
                if choices.get(('day', day)) == 'imported':
                    days_to_import.add(day)
            for month in duplicate_months:
                if choices.get(('month', month)) == 'imported':
                    months_to_import.add(month)

            # Ignore choices that produce byte-for-byte equivalent logical payloads.
            actual_days_to_import = {
                day for day in days_to_import
                if day not in existing_dates
                or (_internal_payload_for_identity(
                    before_internal, destination_dataset, ('day', day)
                ) or {}) != _user_day_payload(imported_frames, day)
            }
            actual_months_to_import = {
                month for month in months_to_import
                if month not in existing_months
                or (_internal_payload_for_identity(
                    before_internal, destination_dataset, ('month', month)
                ) or {}) != _user_month_payload(imported_frames, month)
            }

            global_payloads = {}
            changed_global_types = []
            for record_type in ('ingredients', 'fixed_categories'):
                current_payload = _internal_payload_for_identity(
                    before_internal, destination_dataset, ('global', record_type)
                ) or {}
                current_records = current_payload.get(record_type, [])
                if not isinstance(current_records, list):
                    current_records = []
                combined_records = (
                    [dict(item) for item in current_records if isinstance(item, dict)]
                    + _canonical_records(imported_frames[record_type])
                )
                unique = []
                seen = set()
                for record in combined_records:
                    marker = exact_json_dumps(
                        record, ensure_ascii=False, sort_keys=True, separators=(',', ':')
                    )
                    if marker not in seen:
                        seen.add(marker)
                        unique.append(record)
                payload = {record_type: unique}
                global_payloads[record_type] = payload
                if payload != {record_type: current_records}:
                    changed_global_types.append(record_type)

            if not actual_days_to_import and not actual_months_to_import and not changed_global_types:
                QMessageBox.information(
                    self,
                    '没有需要合并的变化',
                    '你选择保留了所有当前版本，并且所选文件没有新增数据。',
                )
                return

            if not duplicate_days and not duplicate_months:
                years_text = sorted(
                    {int(day[:4]) for day in actual_days_to_import}
                    | {int(month[:4]) for month in actual_months_to_import}
                )
                answer = QMessageBox.question(
                    self,
                    '确认合并用户 Excel',
                    '所选文件没有与当前内部 Excel 重复的日期或月份。\n\n'
                    f'将新增 {len(actual_days_to_import)} 天、{len(actual_months_to_import)} 个月的数据'
                    + (f'，涉及年份：{"、".join(map(str, years_text))}' if years_text else '')
                    + '。\n\n是否继续？',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return

            # When an overlapping version will actually be replaced, archive the
            # complete pre-merge annual mirror before touching the internal store.
            years_to_archive = {
                int(day[:4]) for day in actual_days_to_import
                if day in set(duplicate_days)
            } | {
                int(month[:4]) for month in actual_months_to_import
                if month in set(duplicate_months)
            }
            config = _read_path_config()
            year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
            year_map = dict(year_map) if isinstance(year_map, dict) else {}
            for year in sorted(years_to_archive):
                target = (
                    FILE_PATH if int(year) == int(ACTIVE_USER_EXCEL_YEAR or -1) and FILE_PATH
                    else year_map.get(str(year)) or _derived_annual_path(FILE_PATH, year)
                )
                target = normalize_excel_path(target)
                old_frames = _restored_user_frames_for_year(
                    before_internal, destination_dataset, year
                )
                _write_user_mirror_atomically(
                    target,
                    old_frames,
                    destination_dataset,
                    year,
                    allow_family_override=True,
                )
                archive = _unique_archived_excel_path(target, f'{year}年合并前旧数据')
                os.replace(target, archive)
                archived_files.append((target, archive))

            backup_fd, internal_backup = tempfile.mkstemp(
                prefix='.restaurant_finance_merge_backup_',
                suffix='.xlsx',
                dir=os.path.dirname(normalize_excel_path(INTERNAL_FILE_PATH)),
            )
            os.close(backup_fd)
            shutil.copy2(INTERNAL_FILE_PATH, internal_backup)

            with internal_sync_lock(INTERNAL_FILE_PATH):
                internal_frames = _read_internal_frames(INTERNAL_FILE_PATH)
                changed_days = 0
                changed_months = 0
                changed_globals = 0

                for day in sorted(actual_days_to_import):
                    payload_json, digest = _payload_and_hash(
                        _user_day_payload(imported_frames, day)
                    )
                    internal_frames['__day_records'] = _replace_internal_record(
                        internal_frames['__day_records'], destination_dataset,
                        '日期', day, payload_json, digest,
                    )
                    changed_days += 1

                for month in sorted(actual_months_to_import):
                    payload_json, digest = _payload_and_hash(
                        _user_month_payload(imported_frames, month)
                    )
                    internal_frames['__month_records'] = _replace_internal_record(
                        internal_frames['__month_records'], destination_dataset,
                        '月份', month, payload_json, digest,
                    )
                    changed_months += 1

                for record_type in changed_global_types:
                    payload_json, digest = _payload_and_hash(global_payloads[record_type])
                    internal_frames['__global_records'] = _replace_internal_record(
                        internal_frames['__global_records'], destination_dataset,
                        '记录类型', record_type, payload_json, digest,
                    )
                    changed_globals += 1

                meta = internal_frames['__meta']
                meta = meta.loc[meta['dataset_id'].astype(str) != destination_dataset].copy()
                meta = pd.concat([meta, pd.DataFrame([{
                    'dataset_id': destination_dataset,
                    'schema_version': '2',
                    'last_synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }])], ignore_index=True)
                internal_frames['__meta'] = meta
                _write_internal_frames(INTERNAL_FILE_PATH, internal_frames)

                changed_years = sorted(
                    {int(day[:4]) for day in actual_days_to_import}
                    | {int(month[:4]) for month in actual_months_to_import}
                )
                config = _read_path_config()
                year_map = config.get('YEARLY_USER_EXCEL_PATHS', {})
                year_map = dict(year_map) if isinstance(year_map, dict) else {}
                for year in changed_years:
                    if int(year) == int(ACTIVE_USER_EXCEL_YEAR or -1) and FILE_PATH:
                        target = FILE_PATH
                    else:
                        target = year_map.get(str(year)) or _derived_annual_path(FILE_PATH, year)
                    year_map[str(year)] = normalize_excel_path(target)
                config['YEARLY_USER_EXCEL_PATHS'] = year_map
                _write_path_config(config)

                refresh_years = None if changed_globals else changed_years
                _sync_internal_to_user_excels_unlocked(
                    years=refresh_years,
                    update_baseline=True,
                    internal_frames=internal_frames,
                )

            archive_note = ''
            if archived_files:
                archive_note = '\n\n合并前旧版本已归档：\n' + '\n'.join(
                    archive for _target, archive in archived_files
                )
            QMessageBox.information(
                self,
                '合并完成',
                f'已合并：更新 {changed_days} 天、{changed_months} 个月、'
                f'{changed_globals} 项公共字典数据。'
                + archive_note,
            )
        except (OSError, ExcelAccessError, ExcelFormatError, ValueError) as exc:
            if internal_backup and os.path.exists(internal_backup):
                try:
                    os.replace(internal_backup, INTERNAL_FILE_PATH)
                    internal_backup = None
                except OSError:
                    pass
            for target, archive in reversed(archived_files):
                try:
                    if os.path.exists(target):
                        os.remove(target)
                    if os.path.exists(archive):
                        os.replace(archive, target)
                except OSError:
                    pass
            QMessageBox.critical(self, '合并用户 Excel 失败', str(exc))
        finally:
            if internal_backup and os.path.exists(internal_backup):
                try:
                    os.remove(internal_backup)
                except OSError:
                    pass


    def create_new_user_excel(self):
        """Archive the current pair and establish a completely empty new store."""
        global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

        unsaved_parts = self._unsaved_sections()
        if unsaved_parts:
            QMessageBox.warning(
                self,
                '请先处理未保存内容',
                f"建立新账套前，请先保存或撤销：{'、'.join(unsaved_parts)}。",
            )
            return
        if not FILE_PATH or not INTERNAL_FILE_PATH:
            QMessageBox.warning(self, '文件尚未准备好', '当前用户 Excel 或内部 Excel 不存在，无法执行整体清空。')
            return

        user_path = normalize_excel_path(FILE_PATH)
        internal_path = normalize_excel_path(INTERNAL_FILE_PATH)
        if not os.path.exists(user_path) or not os.path.exists(internal_path):
            QMessageBox.warning(
                self,
                '文件缺失',
                '当前用户 Excel 或内部 Excel 已经丢失。请先重新启动软件，让程序自动恢复后再建立新账套。',
            )
            return

        year = int(self.dashboard.date_edit.date().year() if hasattr(self, 'dashboard') else datetime.now().year)
        archived_user = _unique_archived_excel_path(user_path, '旧用户数据')
        archived_internal = _unique_archived_excel_path(internal_path, '旧内部数据')

        first = QMessageBox.warning(
            self,
            '建立全新的空白账套',
            '这个操作会把当前全部本地数据清空，并建立新的内部 Excel 和用户 Excel。\n\n'
            '旧文件不会删除或覆盖，而是先改名归档。新文件会继续使用原来的文件名和原来的路径。\n\n'
            f'旧用户 Excel 将归档为：\n{archived_user}\n\n'
            f'旧内部 Excel 将归档为：\n{archived_internal}\n\n是否继续？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if first != QMessageBox.Yes:
            return

        second = QMessageBox.critical(
            self,
            '最终确认：清空全部数据',
            '确认后，新内部 Excel 和新用户 Excel 都将是空白账套；同步助手随后会弹窗询问是否用空白账套覆盖云端。\n\n'
            '旧数据只保留在刚才显示的归档文件中。\n\n确定执行吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if second != QMessageBox.Yes:
            return

        user_dir = os.path.dirname(user_path)
        internal_dir = os.path.dirname(internal_path)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs(internal_dir, exist_ok=True)
        temp_user = None
        temp_internal = None
        moved_user = False
        moved_internal = False
        old_config = _read_path_config()
        old_state = (FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID)
        try:
            fd, temp_user = tempfile.mkstemp(
                prefix='.restaurant_new_user_', suffix='.xlsx', dir=user_dir
            )
            os.close(fd)
            os.remove(temp_user)
            init_excel_structure(temp_user)
            write_user_workbook_metadata(
                temp_user, FIXED_CLOUD_DATASET_ID, year
            )

            fd, temp_internal = tempfile.mkstemp(
                prefix='.restaurant_new_internal_', suffix='.xlsx', dir=internal_dir
            )
            os.close(fd)
            os.remove(temp_internal)
            _write_internal_frames(temp_internal, _default_internal_frames())
            sync_user_excel_to_internal(
                temp_user, year, FIXED_CLOUD_DATASET_ID, temp_internal
            )

            validate_data_excel(temp_user, require_write=True)
            validate_internal_excel(temp_internal, require_write=True)

            with internal_sync_lock(internal_path):
                ensure_excel_writable(user_path)
                validate_internal_excel(internal_path, require_write=True)
                os.replace(user_path, archived_user)
                moved_user = True
                os.replace(internal_path, archived_internal)
                moved_internal = True
                os.replace(temp_user, user_path)
                temp_user = None
                os.replace(temp_internal, internal_path)
                temp_internal = None

            FILE_PATH = user_path
            INTERNAL_FILE_PATH = internal_path
            ACTIVE_USER_EXCEL_YEAR = int(year)
            ACTIVE_DATASET_ID = FIXED_CLOUD_DATASET_ID
            frames = _read_internal_frames(INTERNAL_FILE_PATH)
            _set_app_baseline_from_internal(
                frames, FIXED_CLOUD_DATASET_ID, ACTIVE_USER_EXCEL_YEAR
            )
            _write_source_choice_config(
                FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, 'new_empty_store'
            )
            _write_cloud_override_request(
                INTERNAL_FILE_PATH,
                'new_empty_store',
                '用户明确建立全新空白账套。',
            )
            trigger_sync_assistant_now()

            self._update_window_title()
            self._align_ui_dates_to_active_year()
            self._refresh_for_current_excel()
            self._last_internal_signature = _file_signature(INTERNAL_FILE_PATH)
            self._last_user_signature = _file_signature(FILE_PATH)
            QMessageBox.information(
                self,
                '新账套已建立',
                '新的内部 Excel 和用户 Excel 已在原路径建立，当前数据为空。\n\n'
                f'旧用户 Excel：\n{archived_user}\n\n'
                f'旧内部 Excel：\n{archived_internal}',
            )
        except Exception as exc:
            FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID = old_state
            try:
                _write_path_config(old_config)
            except OSError:
                pass
            try:
                if moved_internal:
                    if os.path.exists(internal_path):
                        os.remove(internal_path)
                    if os.path.exists(archived_internal):
                        os.replace(archived_internal, internal_path)
                if moved_user:
                    if os.path.exists(user_path):
                        os.remove(user_path)
                    if os.path.exists(archived_user):
                        os.replace(archived_user, user_path)
            except OSError:
                pass
            QMessageBox.critical(
                self,
                '建立新账套失败',
                '操作没有完整完成，程序已尽量恢复原文件。\n\n'
                f'系统返回：{exc}',
            )
        finally:
            for temporary in (temp_user, temp_internal):
                if temporary and os.path.exists(temporary):
                    try:
                        os.remove(temporary)
                    except OSError:
                        pass

    def read_other_excel(self):
        """Safely switch the current data source after the requested 2 + 1 confirmations."""
        global FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID

        unsaved_parts = self._unsaved_sections()
        if unsaved_parts:
            QMessageBox.warning(
                self,
                "请先处理未保存内容",
                "切换 Excel 不会自动保存当前编辑内容。\n\n"
                f"请先保存或撤销：{'、'.join(unsaved_parts)}。"
            )
            return

        first = QMessageBox.warning(
            self,
            "第一次确认：读取另一个 Excel",
            "即将选择另一个 Excel 数据文件。\n\n"
            "切换后，这个年度 Excel 会按内部数据重建；它不会反向覆盖内部数据。\n\n"
            "是否继续选择？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if first != QMessageBox.Yes:
            return

        second = QMessageBox.critical(
            self,
            "第二次确认：切换数据源",
            "请再次确认：接下来选择的 Excel 会成为本软件当前使用的数据文件。\n"
            "请确认不是选错门店或备份文件。\n\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if second != QMessageBox.Yes:
            return

        current_dir = os.path.dirname(FILE_PATH) if FILE_PATH else ''
        start_dir = current_dir if os.path.isdir(current_dir) else os.path.expanduser('~')
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择另一个本软件的数据 Excel",
            start_dir,
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        try:
            file_path = validate_data_excel(file_path, require_write=True)
        except (ExcelAccessError, ExcelFormatError) as exc:
            QMessageBox.critical(self, "无法使用所选 Excel", str(exc))
            return

        third = QMessageBox.question(
            self,
            "最后确认：切换当前 Excel",
            f"已选择：\n{file_path}\n\n"
            "确认后，软件会以内置数据为准，重建该年度 Excel 的标准工作表，"
            "然后刷新全部页面。请确认该文件可作为年度镜像。\n\n"
            "确定切换吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if third != QMessageBox.Yes:
            return

        old_path, old_internal_path, old_year, old_dataset_id = (
            FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID
        )
        selected_meta = read_user_workbook_metadata(file_path)
        selected_family_id = selected_meta.get('family_id') or ACTIVE_DATASET_ID or None
        try:
            # A legacy annual workbook has no identity sheet. Treat it as part of
            # the current family when the user explicitly switches to it, so its
            # year is not stranded in a separate internal dataset.
            configure_active_user_excel(file_path, family_id=selected_family_id)
            self._update_window_title()
            self._align_ui_dates_to_active_year()
            self._refresh_for_current_excel()
        except Exception as exc:
            FILE_PATH, INTERNAL_FILE_PATH, ACTIVE_USER_EXCEL_YEAR, ACTIVE_DATASET_ID = (
                old_path, old_internal_path, old_year, old_dataset_id
            )
            try:
                self._refresh_for_current_excel()
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "切换 Excel 失败",
                (
                    "所选文件没有被设为当前数据源，软件仍在使用原文件。\n\n"
                    + f"系统返回：{exc}"
                ),
            )
            return

        QMessageBox.information(
            self,
            "切换成功",
            "已切换到所选年度 Excel，并已按内部数据自动重建。",
        )

    def _date_for_tab_index(self, index):
        if index == 0:
            return self.dashboard.date_edit.date()
        if index == 2:
            return self.ledger.entry_date.date()
        if index == 4:
            return self.dish_detail.date_edit.date()
        if index == 5:
            return self.ingredient_detail.date_edit.date()
        if index == 6:
            return self.spice_detail.date_edit.date()
        if index == 7:
            return self.inventory.date_edit.date()
        return None

    def on_tab_changed(self, index):
        if self._is_handling_tab_switch:
            return
        previous_index = self.last_tab_index

        # 检测从"记账本"切换到其他页
        if self.last_tab_index == 2:
            daily_dirty, fixed_dirty = self.ledger.has_unsaved_changes()
            if daily_dirty or fixed_dirty:
                msg = "检测到"
                if daily_dirty and fixed_dirty:
                    msg += "【当日流水】和【月度固定成本】"
                elif daily_dirty:
                    msg += "【当日流水】"
                else:
                    msg += "【月度固定成本】"
                msg += "中有输入的内容尚未保存！\n\n如果直接切换，这些未保存的修改将会丢失。\n您确定要放弃修改并切换吗？"

                ans = QMessageBox.warning(
                    self, " 未保存提示", msg,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if ans == QMessageBox.No:
                    self._is_handling_tab_switch = True
                    self.tabs.setCurrentIndex(2)
                    self._is_handling_tab_switch = False
                    return
                else:
                    if daily_dirty:
                        self.ledger.auto_load_daily_record()
                    if fixed_dirty:
                        self.ledger.load_fixed_cost_for_month()

        # 检测从“当日做出的菜品”切换到其他页
        if self.last_tab_index == 4 and self.dish_detail.has_unsaved_changes():
            ans = QMessageBox.warning(
                self, " 未保存提示",
                "检测到【当日做出的菜品】页面有尚未保存的修改！\n\n"
                "如果直接切换，这些修改将会丢失。\n您确定要放弃修改并切换吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans == QMessageBox.No:
                self._is_handling_tab_switch = True
                self.tabs.setCurrentIndex(self.last_tab_index)
                self._is_handling_tab_switch = False
                return
            self.dish_detail.refresh_data()

        # 检测从“食材明细/佐料明细”切换到其他页
        detail_tabs = {
            5: (self.ingredient_detail, "食材明细"),
            6: (self.spice_detail, "佐料明细"),
        }
        if self.last_tab_index in detail_tabs:
            detail_tab, detail_name = detail_tabs[self.last_tab_index]
            if detail_tab.has_unsaved_changes():
                ans = QMessageBox.warning(
                    self, " 未保存提示",
                    f"检测到【{detail_name}】页面有尚未保存的修改！\n\n"
                    "如果直接切换，这些修改将会丢失。\n您确定要放弃修改并切换吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if ans == QMessageBox.No:
                    self._is_handling_tab_switch = True
                    self.tabs.setCurrentIndex(self.last_tab_index)
                    self._is_handling_tab_switch = False
                    return
                else:
                    detail_tab.refresh_data()

        if self.last_tab_index == 7 and self.inventory.has_unsaved_changes():
            answer = QMessageBox.warning(
                self, ' 未保存提示',
                '检测到【库存单据】页面有尚未保存的修改！\n\n'
                '如果直接切换，这些修改将会丢失。确定放弃修改吗？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer == QMessageBox.No:
                self._is_handling_tab_switch = True
                self.tabs.setCurrentIndex(7)
                self._is_handling_tab_switch = False
                return
            self.inventory.refresh_data()

        source_date = self._date_for_tab_index(previous_index)
        self.last_tab_index = index
        if index == 0:
            if source_date and source_date.isValid():
                # setDate() does not emit dateChanged when the date is already the
                # same. Always refresh explicitly so data saved in the ledger,
                # dish, food, spice, or fixed-cost pages is visible immediately.
                if self.dashboard.date_edit.date() != source_date:
                    self.dashboard.date_edit.setDate(source_date)
            self.dashboard.refresh_all()
        elif index == 2:
            # 切换到记账本时，优先沿用刚才所在页面的日期。
            if source_date and source_date.isValid() and source_date != self.ledger.entry_date.date():
                self.ledger.set_entry_date_safely(source_date)
            else:
                self.ledger.auto_load_daily_record()
        elif index == 4:
            # 每次打开菜品页，都同步刚才所在页面的日期并从文件重新加载最新数据。
            target_date = source_date if source_date and source_date.isValid() else self.ledger.entry_date.date()
            self.dish_detail.date_edit.blockSignals(True)
            self.dish_detail.date_edit.setDate(target_date)
            self.dish_detail.date_edit.blockSignals(False)
            self.dish_detail.refresh_data()
        elif index in detail_tabs:
            # 每次打开明细页，都同步刚才所在页面的日期并从文件重新加载最新数据。
            detail_tab, _ = detail_tabs[index]
            target_date = source_date if source_date and source_date.isValid() else self.ledger.entry_date.date()
            detail_tab.date_edit.blockSignals(True)
            detail_tab.date_edit.setDate(target_date)
            detail_tab.date_edit.blockSignals(False)
            detail_tab.refresh_data()
        elif index == 7:
            target_date = source_date if source_date and source_date.isValid() else self.ledger.entry_date.date()
            self.inventory.date_edit.setDate(target_date)
            self.inventory.refresh_data()
        elif index == 8:
            # 切换到更多统计时，自动刷新图表
            self.more_stats.refresh()
        elif index == 3:
            self.store_payments.refresh_from_cloud(force=True)
        elif index == 9:
            self.data_management.refresh_dataset_targets()
        elif index == 1:
            self.cash_position.refresh()
        if self.tabs.widget(index) is self.audit_log:
            self.audit_log.refresh()
        elif self.tabs.widget(index) is self.temporary_permissions:
            self.temporary_permissions.refresh()

    def closeEvent(self, event):
        global DESKTOP_OFFLINE_ONLY_SESSION
        unsaved_parts = []

        daily_dirty, fixed_dirty = self.ledger.has_unsaved_changes()
        if daily_dirty:
            unsaved_parts.append("【当日流水】")
        if fixed_dirty:
            unsaved_parts.append("【月度固定成本】")
        if self.dish_detail.has_unsaved_changes():
            unsaved_parts.append("【当日做出的菜品】")
        if self.ingredient_detail.has_unsaved_changes():
            unsaved_parts.append("【食材明细】")
        if self.spice_detail.has_unsaved_changes():
            unsaved_parts.append("【佐料明细】")
        if self.inventory.has_unsaved_changes():
            unsaved_parts.append("【库存单据】")

        if unsaved_parts:
            msg = "检测到" + "、".join(unsaved_parts) + "中有尚未保存的内容！\n\n如果直接退出，这些未保存的修改将会丢失。\n您确定要退出软件吗？"
            ans = QMessageBox.warning(
                self, " 未保存提示", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans == QMessageBox.No:
                event.ignore()
                return
        if hasattr(self, '_offline_reminder_timer'):
            self._offline_reminder_timer.stop()
        if hasattr(self, '_idle_logout_timer'):
            self._idle_logout_timer.stop()
        try:
            QApplication.instance().removeEventFilter(self)
        except RuntimeError:
            pass
        if hasattr(self, '_embedded_sync'):
            self._embedded_sync.stop()
        if not DESKTOP_OFFLINE_ONLY_SESSION:
            config = load_embedded_sync_config()
            closed_at = datetime.now().astimezone()
            if self._force_relogin_on_close:
                closed_at -= timedelta(seconds=DESKTOP_RELOGIN_SECONDS + 1)
            config['last_closed_at'] = closed_at.isoformat(timespec='seconds')
            save_embedded_sync_config(config)
        event.accept()



if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("RestaurantFinance")
    app.setApplicationName("餐饮成本管家")
    apply_py_charm_run_style(app)

    if desktop_cloud_login_required():
        login_dialog = CloudSettingsDialog(require_login=True)
        if login_dialog.exec() != QDialog.Accepted:
            sys.exit(0)
        DESKTOP_OFFLINE_ONLY_SESSION = login_dialog.offline_requested

    startup_ready = False
    saved_path = load_saved_path()
    configured_internal = get_internal_excel_path_from_config()
    sync_config = load_embedded_sync_config()
    selected_dataset_id = str(sync_config.get('dataset_id') or '')
    cached_dataset_id = str(_read_path_config().get('CLOUD_CACHE_DATASET_ID') or '')

    # A matching app-owned cache can open immediately. A first run, missing cache,
    # or a different selected ledger is bootstrapped directly from the server.
    if selected_dataset_id and cached_dataset_id == selected_dataset_id:
        try:
            startup_ready, _notice_title, _notice_message = prepare_startup_files_without_unnecessary_choice(
                saved_path, configured_internal
            )
        except (ExcelAccessError, ExcelFormatError, OSError):
            startup_ready = False

    if not startup_ready and not DESKTOP_OFFLINE_ONLY_SESSION:
        try:
            # A successful login can be followed by a short DNS/TLS or record
            # fetch hiccup.  Retry only the cloud bootstrap before deciding that
            # the account is genuinely offline.
            last_cloud_error = None
            for attempt in range(3):
                try:
                    startup_ready = initialize_cloud_cache_from_server()
                    last_cloud_error = None
                    break
                except CloudSyncError as exc:
                    last_cloud_error = exc
                    if attempt < 2:
                        time.sleep(0.8 * (attempt + 1))
                    else:
                        raise
            if last_cloud_error is not None and not startup_ready:
                raise last_cloud_error
        except (CloudSyncError, ExcelAccessError, ExcelFormatError, OSError) as exc:
            # When the network is temporarily unavailable, an existing cache may
            # still be viewed, but it must remain read-only until reconnection.
            try:
                startup_ready, _notice_title, _notice_message = prepare_startup_files_without_unnecessary_choice(
                    saved_path, configured_internal
                )
            except (ExcelAccessError, ExcelFormatError, OSError):
                startup_ready = False
            if startup_ready:
                # Do not show an immediate warning here.  The cache is a valid
                # fallback and the worker will report a persistent outage only
                # after its delayed, multi-cycle connection check.
                print(f'云端启动同步暂时失败，已打开缓存并等待重连：{exc}')
            else:
                QMessageBox.critical(
                    None, '无法打开账本',
                    f'暂时无法连接云端，并且本机还没有可读取的账本缓存。\n\n{exc}\n\n请连接网络后重新打开软件。',
                )
                sys.exit(0)

    if not startup_ready and DESKTOP_OFFLINE_ONLY_SESSION:
        try:
            startup_ready, _notice_title, _notice_message = prepare_startup_files_without_unnecessary_choice(
                saved_path, configured_internal
            )
        except (ExcelAccessError, ExcelFormatError, OSError):
            startup_ready = False
        if not startup_ready:
            QMessageBox.critical(
                None, '没有离线缓存',
                '本机还没有成功同步过这份账本，无法离线打开。\n\n请连接网络后重新登录，软件会自动建立缓存。',
            )
            sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
