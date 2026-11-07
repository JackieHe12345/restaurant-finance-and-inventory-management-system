"""Offline QA harness for the main bytecode extracted from a candidate app.

This is built into a separate QA app with rebuild_macos_app.py. It never ships
inside the production app. Set V101_SOURCE_ROOT, V101_PRODUCTION_APP and
V101_QA_DIR to absolute paths; run each architecture using /usr/bin/arch.
V101_QA_STDLIB may point to Python 3.12's standard library solely to supply
unittest.mock, which the production runtime does not need or bundle.
"""
import os
from pathlib import Path
import sys
import json
import platform
import marshal
import runpy
import types
import traceback
import time
import hashlib

qa = Path(os.environ['V101_QA_DIR']).resolve()
qa.mkdir(parents=True, exist_ok=True)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MPLCONFIGDIR'] = str(qa / 'matplotlib')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
root = Path(os.environ['V101_SOURCE_ROOT']).resolve()
candidate = Path(os.environ['V101_PRODUCTION_APP']).resolve()
result = {'architecture':platform.machine(), 'network':'disabled', 'data':'synthetic isolated workbooks'}


def audit(event, args):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        raise RuntimeError('Network disabled during packaged QA')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path, mode, flags = args
        write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if write:
            resolved = Path(os.fsdecode(path)).resolve()
            if not resolved.is_relative_to(qa) and resolved != Path('/dev/null'):
                raise RuntimeError('QA write outside sandbox: ' + str(resolved))


def execute():
    import plistlib, tempfile
    (qa/'tmp').mkdir(exist_ok=True)
    tempfile.tempdir = str(qa/'tmp')
    helper = runpy.run_path(str(root / 'build/rebuild_macos_app.py'), run_name='build_helpers')
    info = plistlib.loads((candidate / 'Contents/Info.plist').read_bytes())
    binary = candidate / 'Contents/MacOS' / info['CFBundleExecutable']
    thin = helper['slices'](binary.read_bytes())[platform.machine()]
    entries = helper['archive'](thin)[1]
    raw = helper['unpack'](helper['main_entry'](entries))
    code = marshal.loads(raw)
    assert helper['same_code'](code, compile((root/'desktop/restaurant_cost_manager.py').read_bytes(), code.co_filename, 'exec'))
    result['main_bytecode_sha256'] = hashlib.sha256(raw).hexdigest()
    # A temporary root is used without changing HOME or any real account config.
    original_expanduser = os.path.expanduser
    os.path.expanduser = lambda path: str(qa/'home') + str(path)[1:] if str(path).startswith('~') else original_expanduser(path)
    (qa/'home').mkdir(exist_ok=True)
    sys.addaudithook(audit)
    m = types.ModuleType('v1_0_1_packaged_desktop')
    m.__file__ = str(root/'desktop/restaurant_cost_manager.py')
    sys.modules[m.__name__] = m
    exec(code, m.__dict__)
    sys.excepthook = sys.__excepthook__
    assert m.APP_VERSION == 'v1.0.1'
    result['versions'] = dict(app=m.APP_VERSION, python=sys.version, pandas=m.pd.__version__,
                              matplotlib=m.matplotlib.__version__)
    from PySide6 import __version__ as qt_version
    import openpyxl
    result['versions'].update(pyside6=qt_version, openpyxl=openpyxl.__version__)
    assert m.money_text(m.decimal_number('0.1') + m.decimal_number('0.2')) == '0.30'
    assert m.money_text('1.005') == '1.01'
    assert m.money_text('999999999999.99') == '999999999999.99'
    for invalid in ('NaN', 'Infinity', True):
        try:
            m.money_input(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid money accepted')
    result['money'] = 'passed'
    ds = 'v1_0_1-offline-qa'
    m.CONFIG_FILE = str(qa/'paths.json')
    m.SYNC_ASSISTANT_CONFIG_PATH = str(qa/'sync.json')
    m.INTERNAL_FILE_PATH = str(qa/'internal.xlsx')
    m.FILE_PATH = str(qa/'year2026.xlsx')
    m.ACTIVE_USER_EXCEL_YEAR = 2026
    m.ACTIVE_DATASET_ID = ds
    m.FIXED_CLOUD_DATASET_ID = ds
    frames = m._default_internal_frames()
    frames['__meta'] = m.pd.DataFrame([dict(dataset_id=ds, schema_version=2, last_synced_at='')])
    row = {'日期':'2026-10-09', '收益':'1000.00', '食材成本':'180.00',
           '食材明细':'猪肉 9斤 180.00', '其他':'0.00'}
    payload = {'daily':[row], 'dishes':[], 'fixed_expenses':[]}
    raw_json, digest = m._payload_and_hash(payload)
    frames['__day_records'] = m.pd.DataFrame([dict(dataset_id=ds, 日期='2026-10-09', payload_json=raw_json, sha256=digest)])
    cash = {'opening_date':'2026-10-01', 'opening_balance':'100.00', 'transactions':[]}
    raw_json, digest = m._payload_and_hash(cash)
    frames['__global_records'] = m.pd.DataFrame([{'dataset_id':ds,'记录类型':'cash_position','payload_json':raw_json,'sha256':digest}])
    m._write_internal_frames(m.INTERNAL_FILE_PATH, frames)
    reread = m._read_internal_frames(m.INTERNAL_FILE_PATH)
    assert m._internal_payload_for_identity(reread, ds, ('day','2026-10-09'))['daily'][0]['收益'] == '1000.00'
    m.recreate_user_mirror_from_internal(m.FILE_PATH, year=2026, dataset_id=ds, internal_path=m.INTERNAL_FILE_PATH)
    m._write_path_config({'DATASET_ID':ds,'ACTIVE_USER_EXCEL_YEAR':2026,'FILE_PATH':m.FILE_PATH,
                          'INTERNAL_FILE_PATH':m.INTERNAL_FILE_PATH,'YEARLY_USER_EXCEL_PATHS':{'2026':m.FILE_PATH}})
    m._set_app_baseline_from_internal(reread, ds, 2026)
    result['excel_roundtrip'] = 'passed'
    receipts = [dict(id='first',date='2026-10-09',category='食材',name='猪肉',unit='斤',quantity='9',total='180',unit_price='20'),
                dict(id='second',date='2026-10-10',category='食材',name='猪肉',unit='斤',quantity='10',total='150',unit_price='15')]
    issues = [dict(id='use9',date='2026-10-09',category='食材',name='猪肉',unit='斤',quantity='8'),
              dict(id='use10',date='2026-10-10',category='食材',name='猪肉',unit='斤',quantity='3')]
    fifo = m._inventory_fifo(receipts, issues, [], [])
    movement = next(x for x in fifo['movements'] if x['id'] == 'use10')
    assert m.money_text(movement['known_cost']) == '50.00'
    assert m.money_text(m._inventory_fifo_average_price(movement)) == '16.67'
    result['fifo_example'] = {'cost':'50.00','average':'16.67'}
    app = m.QApplication.instance() or m.QApplication([])
    app.setApplicationName('v1.0.1 isolated QA')
    m.apply_py_charm_run_style(app)
    snapshot = dict(configured=True, connected=True, role='admin', username='offline-qa', dataset_id=ds,
                    datasets=[{'id':ds,'name':'离线合成验收账本'}], temporary_permissions=[], conflicts=[],
                    consecutive_failures=0, syncing=False, internet_connected=True)
    class Worker:
        def __init__(self, *a, **k): pass
        def start(self): pass
        def stop(self): pass
        def wake(self): pass
        def snapshot(self): return dict(snapshot)
        def _set_state(self, **k): snapshot.update(k)
        def get_store_settings(self): return {'store_a_name':'A店','store_b_name':'B店'}
        def list_datasets(self): return snapshot['datasets']
        def list_temporary_permissions(self): return {'users':[],'datasets':snapshot['datasets'],'grants':[]}
        def list_audit_logs(self, *a, **k): return []
    m.EmbeddedCloudSyncWorker = Worker
    m.DESKTOP_STARTUP_CONNECTION_STATE = snapshot
    m.DESKTOP_OFFLINE_ONLY_SESSION = True
    messages = []
    for name in ('warning','critical','information'):
        setattr(m.QMessageBox, name, lambda *args, **kw: messages.append(str(args[2]) if len(args)>2 else str(args)) or m.QMessageBox.Ok)
    m.QMessageBox.question = lambda *a, **k: m.QMessageBox.No
    m.QMessageBox.exec = lambda self: messages.append(self.text()) or m.QMessageBox.Ok
    qt_errors = []
    sys.excepthook = lambda typ, val, tb: qt_errors.append(''.join(traceback.format_exception(typ,val,tb)))
    window = m.MainWindow()
    for timer in window.findChildren(m.QTimer): timer.stop()
    window.resize(1440, 960)
    window.show()
    app.processEvents()
    names = []
    for index in range(window.tabs.count()):
        window.tabs.setTabVisible(index, True)
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        names.append(window.tabs.tabText(index).strip())
    assert len(names) == 12, names
    assert not qt_errors, qt_errors
    assert not messages, messages
    result['qt_modules'] = names
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    window.grab().save(str(qa/'main-window.png'))
    window.hide()
    result['qt_offscreen'] = '12 modules constructed and switched'
    sys.excepthook = sys.__excepthook__
    os.environ['DESKTOP_SOURCE'] = str(root/'desktop/restaurant_cost_manager.py')
    os.environ['DESKTOP_TEST_REPORT'] = str(qa/'desktop-regressions.json')
    if os.environ.get('V101_QA_STDLIB'):
        import unittest
        unittest.__path__.append(str(Path(os.environ['V101_QA_STDLIB'])/'unittest'))
        result['test_support'] = 'unittest.mock from host Python3.12 standard library; app dependencies unchanged'
    for script in ('test_v1_0_1_desktop.py', 'test_v1_0_1_desktop_qt.py'):
        sys.argv = [str(root/'build'/script)]
        try:
            runpy.run_path(sys.argv[0], run_name='__main__')
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise AssertionError(f'Packaged-runtime regression failed: {script}, {exc.code}')
        result[script] = 'passed in packaged runtime'
    result['status'] = 'passed'


try:
    execute()
except BaseException:
    result.update(status='failed', error=traceback.format_exc())
finally:
    (qa/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
if result.get('status') != 'passed':
    sys.exit(1)
