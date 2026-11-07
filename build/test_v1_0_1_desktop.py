"""v1.0.1 desktop acceptance: deterministic production-method scheduling, no service/user data.
Run: python build/test_v1_0_1_desktop.py
Old-version control: DESKTOP_SOURCE=/path/to/old/restaurant_cost_manager.py python build/test_v1_0_1_desktop.py
Dependencies are the desktop's pandas/openpyxl only; no GUI application/network is started.
"""
import ast, calendar, copy, hashlib, json, os, re, tempfile, types, unittest, inspect
from pathlib import Path
from contextlib import nullcontext
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
import pandas as pd
getcontext().prec=256
SOURCE=Path(os.environ.get('DESKTOP_SOURCE', str(Path(__file__).resolve().parents[1] / 'desktop/restaurant_cost_manager.py')))
TREE=ast.parse(SOURCE.read_text()); RESULTS={}
class Now(datetime):
    @classmethod
    def now(cls, tz=None): return cls(2026, 11, 5, 12, tzinfo=tz)
def env():
    return dict(datetime=Now,timedelta=timedelta,Decimal=Decimal,InvalidOperation=InvalidOperation,
                ROUND_HALF_UP=ROUND_HALF_UP,MONEY_CENT=Decimal('.01'),pd=pd,calendar=calendar,re=re,
                os=os,hashlib=hashlib,json=json,tempfile=tempfile,ExcelAccessError=RuntimeError,
                ExcelFormatError=ValueError,CloudSyncError=RuntimeError,_embedded_align_source_order=lambda records:None)
def functions(scope,names):
    nodes=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes}==set(names), set(names)-{n.name for n in nodes}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),scope)
def optional(scope,names):
    available={n.name for n in TREE.body if isinstance(n,ast.FunctionDef)}
    functions(scope,set(names)&available)
def methods(scope,clsname,names):
    cls=copy.deepcopy(next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name==clsname));cls.bases=[]
    cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert {n.name for n in cls.body}==set(names)
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(SOURCE),'exec'),scope);return scope[clsname]
def money(scope):
    names={'MAX_ABS_AMOUNT','MAX_UNIT_PRICE','MONEY_CENT','PRICE_UNIT','MONEY_FIELDS','PRICE_FIELDS','DETAIL_JSON_FIELDS','QUANTITY_FIELDS','MONEY_CONTAINERS','MONEY_ENVELOPES','UNITS_LIST'}
    nodes=[n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in names for x in n.targets)]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),scope)
    functions(scope,{'decimal_number','money_amount','money_input','unit_price_value','money_text','price_text',
                     '_plain_decimal_numbers','money_payload','money_excel_frame','exact_json_loads','exact_json_dumps',
                     'safe_float','decimal_divide','money_value_was_entered','recalculate_revenue_fields',
                     'fixed_expense_includes_cash','get_unit_pattern','unit_join','split_item_note','join_item_note'})
def record(day,value):
    return {'record_type':'day','record_key':day,'payload':{'daily':[{'日期':day,'收益':value}]},'checksum':'h'+str(value),'version':1}
def encode(payload):
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str);return raw,hashlib.sha256(raw.encode()).hexdigest()
def frames_for(payload,key='cash_position'):
    raw,digest=encode(payload)
    return {'说明':pd.DataFrame([{'说明':'v1.0.1 synthetic test'}]),
        '__day_records':pd.DataFrame(columns=['dataset_id','日期','payload_json','sha256']),
        '__month_records':pd.DataFrame(columns=['dataset_id','月份','payload_json','sha256']),
        '__global_records':pd.DataFrame([{'dataset_id':'book','记录类型':key,'payload_json':raw,'sha256':digest}]),
        '__audit_records':pd.DataFrame(columns=['payload_json']),
        '__meta':pd.DataFrame([{'dataset_id':'book','schema_version':2,'last_synced_at':''}])}

def background_baseline_overwrite():
    import re
    day='2026-10-02';identity=('day',day)
    payments=['A店现金','B店现金','A店微信增加','A店微信自动','A店微信覆盖','A店支付宝增加','A店支付宝覆盖','B店微信增加','B店微信自动','B店微信覆盖','B店支付宝增加','B店支付宝覆盖','学生外卖','A店外卖','B店外卖']
    old={'日期':day,'收益':'1000.00','食材成本':'10.00','食材明细':'米 1斤 10.00','当日备注':'原备注',
         '总现金':'','总线上':'','A店收入':'','B店收入':'','手续费':'','新客人数量':'','总客人数':'',
         '佐料成本':'0.00','佐料明细':'','水电':'0.00','其他':'0.00','其他明细':'',**{key:'' for key in payments}}
    cloud={**old,'食材成本':'20.00','食材明细':'米 1斤 20.00'};draft={**old,'当日备注':'本机新备注'}
    def encode(payload):
        raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str);return raw,hashlib.sha256(raw.encode()).hexdigest()
    initial_payload={'daily':[old]};cloud_payload={'daily':[cloud]};raw,digest=encode(cloud_payload)
    store={'__day_records':pd.DataFrame([{'dataset_id':'book','日期':day,'payload_json':raw,'sha256':digest}],dtype=object),
           '__month_records':pd.DataFrame(columns=['dataset_id','月份','payload_json','sha256']),
           '__global_records':pd.DataFrame(columns=['dataset_id','记录类型','payload_json','sha256']),
           '__meta':pd.DataFrame([{'dataset_id':'book','schema_version':'2','last_synced_at':''}],dtype=object)}
    events=[];callbacks=[]
    def restore(frames,*a):return {'daily':pd.DataFrame(json.loads(frames['__day_records'].iloc[0]['payload_json'])['daily'],dtype=object)}
    def payload_for(frames,dataset,key):return json.loads(frames['__day_records'].iloc[0]['payload_json']) if key==identity else None
    def save_file(path,frames):store.clear();store.update(copy.deepcopy(frames));events.append('committed_stale_form')
    scope=dict(datetime=datetime,pd=pd,re=re,json=json,hashlib=hashlib,Decimal=Decimal,
      INTERNAL_FILE_PATH='memory',FILE_PATH='mirror',ACTIVE_USER_EXCEL_YEAR=2026,ACTIVE_DATASET_ID='book',
      APP_BASELINE_RECORD_HASHES={identity:encode(initial_payload)[1]},APP_BASELINE_SHEET_FRAMES={'daily':pd.DataFrame([old],dtype=object)},
      DATE_SHEET_COLUMNS={'daily':'日期'},ExcelAccessError=RuntimeError,ExcelFormatError=ValueError,
      normalize_sheet_frame=lambda sheet,frame:frame.copy(),sort_rows_by_date=lambda frame,col:frame.copy(),
      internal_sync_lock=lambda p:nullcontext(),_read_internal_frames=lambda p:copy.deepcopy(store),
      _restored_user_frames_for_year=restore,_internal_payload_for_identity=payload_for,
      _file_signature=lambda p:(1,2),_read_path_config=lambda:{},_valid_date_keys=lambda df,col='日期':set(df[col]),
      _canonical_records=lambda df:df.to_dict('records'),_user_day_payload=lambda frames,d:{'daily':frames['daily'][frames['daily']['日期']==d].to_dict('records')},
      validate_money_changes=lambda *a:None,prepare_money_save=lambda p,b:p,_payload_and_hash=encode,
      _desktop_cloud_role=lambda:'admin',_prune_internal_audit_records=lambda *a:[],
      _write_internal_frames=save_file,_sync_internal_to_user_excels_unlocked=lambda *a,**k:{2026:'mirror'},_set_user_mirror_pending=lambda *a:None)
    functions(scope,{'_internal_record_hashes','_set_app_baseline_from_internal','_changed_keys_for_sheet','_sheet_rows_for_key','_replace_frame_keys',
                     '_day_payload_is_empty','_replace_internal_record','_commit_user_sheet_to_internal'})
    control_error=None
    try:scope['_commit_user_sheet_to_internal']('daily',pd.DataFrame([draft],dtype=object),'日期')
    except RuntimeError as exc:control_error=str(exc)
    assert control_error and '其它设备修改' in control_error
    cls=methods(scope,'MainWindow',{'_refresh_cloud_files_in_background'})
    obj=cls();obj._cloud_file_refresh_busy=False;obj.dirty=False;obj.refreshed=False
    obj._unsaved_sections=lambda:['当日流水'] if obj.dirty else []
    obj.statusBar=lambda:types.SimpleNamespace(showMessage=lambda *a:events.append(str(a[0])))
    obj._refresh_visible_tab_after_cloud_update=lambda:setattr(obj,'refreshed',True)
    def sync(*a,**k):
        # The refresh was launched while the form was clean; the GUI receives an edit while I/O is running.
        obj.dirty=True;events.append('user_edits_old_form')
        if k.get('update_baseline'):
            scope['_set_app_baseline_from_internal'](copy.deepcopy(store),'book',2026)
            events.append('new_cloud_version_registered_as_form_baseline')
    scope['sync_internal_to_user_excels']=sync
    scope['_sync_internal_to_user_excels_unlocked']=sync
    scope['QApplication']=types.SimpleNamespace(activeModalWidget=lambda:None)
    scope['threading']=types.SimpleNamespace(Thread=lambda target,**k:types.SimpleNamespace(start=target))
    scope['QTimer']=types.SimpleNamespace(singleShot=lambda delay,fn:callbacks.append(fn))
    obj._refresh_cloud_files_in_background()
    while callbacks:callbacks.pop(0)()
    assert obj.dirty and not obj.refreshed and scope['APP_BASELINE_RECORD_HASHES'][identity]==encode(initial_payload)[1]
    # Execute actual form parsing, actual overwrite handler, and actual internal commit.
    scope.update(InvalidOperation=InvalidOperation,ROUND_HALF_UP=ROUND_HALF_UP)
    names={'MAX_ABS_AMOUNT','MAX_UNIT_PRICE','MONEY_CENT','PRICE_UNIT','MONEY_FIELDS','PRICE_FIELDS','DETAIL_JSON_FIELDS','QUANTITY_FIELDS','MONEY_CONTAINERS','MONEY_ENVELOPES','UNITS_LIST'}
    assignments=[n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in names for x in n.targets)]
    exec(compile(ast.Module(body=assignments,type_ignores=[]),str(SOURCE),'exec'),scope)
    functions(scope,{'decimal_number','money_amount','money_input','unit_price_value','money_text','price_text','_plain_decimal_numbers','money_payload','exact_json_loads','derived_money_field','money_value_was_entered','safe_float','get_unit_pattern','unit_join','split_item_note','join_item_note','parse_named_amount'})
    class Widget:
        def __init__(self,value=''):self.value=value
        def text(self):return self.value
        def setText(self,value):self.value=value
    class Box:
        Yes=1;No=0
        @staticmethod
        def question(*a,**k):return 1
        @staticmethod
        def warning(*a,**k):events.append('conflict_warning:' + str(a[-1]))
    saved_counts=[]
    def save_daily(df):saved_counts.append(scope['_commit_user_sheet_to_internal']('daily',df,'日期')['records'])
    scope.update(QMessageBox=Box,QDate=types.SimpleNamespace(fromString=lambda *a:a[0]),
        load_daily=lambda:restore(store)['daily'],save_daily=save_daily,_desktop_effective_role=lambda *a:'admin',
        _entry_timing_relevant_change=lambda *a:True,_inventory_purchase_entries=lambda:([],[]))
    ledger_cls=methods(scope,'LedgerTab',{'get_form_data','_parse_float','_parse_optional_money','_parse_customer_count','_parse_mixed_input','save_record'})
    editor=ledger_cls();editor._snapshot_daily={'note':'原备注'};editor._loaded_daily_record=copy.deepcopy(old);editor._role='admin'
    editor.get_daily_ui_state=lambda:{'note':'本机新备注'}
    field_map={'entry_revenue':'收益','entry_total_cash':'总现金','entry_total_online':'总线上','entry_a_revenue':'A店收入','entry_b_revenue':'B店收入','entry_fees':'手续费','entry_new_customers':'新客人数量','entry_total_customers':'总客人数','entry_food_detail':'食材明细','entry_spice_detail':'佐料明细','entry_other_detail':'其他明细','entry_daily_note':'当日备注',
      'entry_a_cash':'A店现金','entry_b_cash':'B店现金','entry_a_wechat_add':'A店微信增加','entry_a_wechat_auto':'A店微信自动','entry_a_wechat_override':'A店微信覆盖','entry_a_alipay_add':'A店支付宝增加','entry_a_alipay_override':'A店支付宝覆盖','entry_b_wechat_add':'B店微信增加','entry_b_wechat_auto':'B店微信自动','entry_b_wechat_override':'B店微信覆盖','entry_b_alipay_add':'B店支付宝增加','entry_b_alipay_override':'B店支付宝覆盖','entry_student_takeout':'学生外卖','entry_a_takeout':'A店外卖','entry_b_takeout':'B店外卖'}
    for name,key in field_map.items():setattr(editor,name,Widget(draft[key]))
    editor.entry_date=types.SimpleNamespace(date=lambda:types.SimpleNamespace(toString=lambda fmt:day))
    editor._activate_user_excel_for_date=lambda *a,**k:True;editor.refresh_table=lambda:None;editor.auto_load_daily_record=lambda:None
    editor._refresh_entry_countdown=lambda:None;editor.lbl_status=Widget()
    try:
        editor.save_record(mode='overwrite')
    except RuntimeError as exc:
        events.append('conflict_warning:' + str(exc))
    saved=json.loads(store['__day_records'].iloc[0]['payload_json'])['daily'][0]
    assert saved['食材成本']=='20.00' and saved['当日备注']==cloud['当日备注'] and saved_counts==[]
    assert any('其它设备修改' in event for event in events if event.startswith('conflict_warning:'))
    result={'records':0}
    RESULTS['background_baseline_overwrite']={'before_form':old,'cloud_before_save':cloud,'user_changed_field':'当日备注',
        'after_save':saved,'ui_refreshed':obj.refreshed,'conflict_error':'stale editor rejected','records_saved':result['records'],'events':events,'negative_control_original_editor_baseline_blocks_save':bool(control_error),'executed_original_handlers':['MainWindow._refresh_cloud_files_in_background','LedgerTab.get_form_data','LedgerTab.save_record(mode=overwrite)','_commit_user_sheet_to_internal']}

class DesktopAcceptance(unittest.TestCase):
    def test_D001_upload_during_GUI_save_remains_pending(self):
        scope=env(); identity=('day','2026-10-02'); current={'local':record(identity[1],2),'cloud':record(identity[1],1)}; puts=[]
        scope.update(FIXED_CLOUD_DATASET_ID='book',_embedded_local_records=lambda:{identity:copy.deepcopy(current['local'])},
            _embedded_apply_cloud_records=lambda *a,**k:None,save_embedded_sync_config=lambda c:None,
            _embedded_payload_hash=lambda p:encode(p)[1])
        cls=methods(scope,'EmbeddedCloudSyncWorker',{'_sync_records','_build_baseline','_cloud_marker'});obj=cls()
        obj._effective_role=lambda *a:'admin';obj.snapshot=lambda:{}
        def put(*args):
            local=args[2];puts.append(local['payload']['daily'][0]['收益']);current['cloud']=dict(copy.deepcopy(local),version=len(puts)+1)
            if len(puts)==1:current['local']=record(identity[1],3)
            return current['cloud']
        obj._put_local=put;obj._fetch_cloud_records=lambda *a:[copy.deepcopy(current['cloud'])];obj._delete_cloud=lambda *a:None
        config={'embedded_baselines':{'book':{'\0'.join(identity):{'local_hash':'h1','cloud_hash':'h1','cloud_version':1}}},'embedded_last_dataset_id':'book'}
        self.assertEqual(obj._sync_records(config,'book',[copy.deepcopy(current['cloud'])],'admin'),[])
        self.assertEqual(obj._sync_records(config,'book',[copy.deepcopy(current['cloud'])],'admin'),[])
        self.assertEqual(puts,[2,3]);self.assertEqual(config['embedded_baselines']['book']['\0'.join(identity)]['local_hash'],'h3')
        RESULTS['D001']={'uploaded_revisions':puts,'latest_local_pending_until_acknowledged':True}

    def test_D001_cloud_apply_checks_snapshot_inside_lock(self):
        scope=env();money(scope);frames=frames_for({});day=record('2026-10-02',3);raw,digest=encode(day['payload'])
        frames['__day_records']=pd.DataFrame([{'dataset_id':'book','日期':day['record_key'],'payload_json':raw,'sha256':digest}]);writes=[]
        scope.update(INTERNAL_FILE_PATH='memory',FIXED_CLOUD_DATASET_ID='book',INTERNAL_META_COLUMNS=['dataset_id','schema_version','last_synced_at'],
            internal_sync_lock=lambda p:nullcontext(),_read_internal_frames=lambda p:copy.deepcopy(frames),
            _internal_payload_for_identity=lambda fs,ds,i:day['payload'] if i[0]=='day' else None,
            _payload_and_hash=encode,_write_internal_frames=lambda *args:writes.append(args))
        functions(scope,{'_embedded_apply_cloud_records','_replace_internal_record','_internal_record_hashes'})
        apply=scope['_embedded_apply_cloud_records'];kwargs={'expected_hashes':{('day',day['record_key']):'h1'}} if 'expected_hashes' in inspect.signature(apply).parameters else {}
        caught=None
        try:apply([record(day['record_key'],2)],**kwargs)
        except RuntimeError as error:caught=error
        self.assertIsNotNone(caught);self.assertEqual(writes,[])

    def test_D002_cross_year_cash_does_not_follow_active_mirror(self):
        scope=env();money(scope);active=[2026]
        daily=[{'日期':'2025-12-31','收益':'100.00'},{'日期':'2026-01-02','收益':'200.00'},{'日期':'2026-12-01','收益':'999.00'}]
        fixed=[{'日期':'2025-12-31','金额':'10.00','计入可用余额':'是'},{'日期':'2026-01-02','金额':'20.00','计入可用余额':'是'}]
        scope.update(load_daily=lambda:pd.DataFrame([row for row in daily if row['日期'].startswith(str(active[0]))]),
            load_fixed_expenses=lambda:pd.DataFrame([row for row in fixed if row['日期'].startswith(str(active[0]))]),
            _inventory_day_sheet=lambda sheet:pd.DataFrame(daily),_embedded_local_records=lambda:{('day',row['日期']):{'payload':{'fixed_expenses':[row]}} for row in fixed},
            load_inventory_entries=lambda:[],FIXED_EXPENSE_CASH_COLUMN='计入可用余额')
        functions(scope,{'_cash_position_ledger'});optional(scope,{'_cash_position_source_frames','_cash_daily_revenue'})
        payload={'base_balance':'5.00','as_of_date':'2025-12-30'}
        first=scope['_cash_position_ledger'](payload,'2026-01');active[0]=2025;second=scope['_cash_position_ledger'](payload,'2026-01')
        self.assertEqual(first['current'],Decimal('275.00'));self.assertEqual(first['current'],second['current'])
        self.assertEqual(first['previous_month_balance'],Decimal('95.00'));self.assertEqual(len(first['entries']),2)
        RESULTS['D002']={'balance_2025_mirror':str(second['current']),'balance_2026_mirror':str(first['current']),'future_ignored':True}

    def test_D003_stale_cash_update_is_rejected_but_matching_save_works(self):
        scope=env();money(scope);old={'transactions':[{'id':'old','amount':'10.00'}]};current={'transactions':old['transactions']+[{'id':'remote','amount':'20.00'}]};frames=frames_for(current)
        def read(fs,ds,identity):
            matches=fs['__global_records'][fs['__global_records']['记录类型']==identity[1]]
            return json.loads(matches.iloc[0]['payload_json']) if not matches.empty else None
        def write(path,value):frames.clear();frames.update(copy.deepcopy(value))
        scope.update(INTERNAL_FILE_PATH='memory',FIXED_CLOUD_DATASET_ID='book',INTERNAL_META_COLUMNS=['dataset_id','schema_version','last_synced_at'],
            require_network_edit=lambda:None,normalize_excel_path=lambda p:p,internal_sync_lock=lambda p:nullcontext(),_read_internal_frames=lambda p:copy.deepcopy(frames),
            _internal_payload_for_identity=read,validate_money_changes=lambda *a:None,prepare_money_save=lambda p,b:p,_payload_and_hash=encode,
            _desktop_cloud_role=lambda:'admin',_prune_internal_audit_records=lambda *a:None,_write_internal_frames=write,_set_internal_sync_pending=lambda *a:None,trigger_embedded_sync_now=lambda:None)
        functions(scope,{'_save_global_record_payload','_replace_internal_record'})
        save=scope['_save_global_record_payload'];kwargs={'expected_hash':encode(old)[1]} if 'expected_hash' in inspect.signature(save).parameters else {}
        caught=None
        try:save('cash_position',{'transactions':old['transactions']+[{'id':'mine','amount':'30.00'}]},**kwargs)
        except RuntimeError as exc:caught=exc
        self.assertIsNotNone(caught);self.assertEqual(read(frames,'book',('global','cash_position')),current)
        clean=save('cash_position',{**current,'note':'normal save'},expected_hash=encode(current)[1]);self.assertEqual(clean['note'],'normal save')
        RESULTS['D003']={'stale_blocked':True,'remote_transaction_retained':True,'matching_hash_save':True}

    def test_D004_empty_days_month_year_keep_fixed_costs(self):
        scope=env();money(scope)
        functions(scope,{'get_monthly_fixed_breakdown','calc_day_metrics','calc_week_summary','calc_month_summary','calc_year_summary','day_has_meaningful_data','elapsed_week_days','elapsed_month_days','elapsed_year_days','_elapsed_reference'})
        fixed=pd.DataFrame([{'月份':'2026-10','人工总额':'3100.00','房租总额':'0.00'},{'月份':'2026-12','人工总额':'3100.00'}]).fillna('');empty=pd.DataFrame(columns=['日期','收益'])
        month=scope['calc_month_summary'](2026,10,empty,fixed);self.assertIsNotNone(month);self.assertEqual(month['本月净利'],Decimal('-3100.00'));self.assertEqual(month['活跃天数'],0)
        year=scope['calc_year_summary'](2026,empty,fixed);self.assertEqual(year['本年固定成本'],Decimal('3100.00'));self.assertEqual(year['月均净利'],Decimal('-3100.00'))
        for rows in [[{'日期':'2026-10-05','收益':'1000'}],[{'日期':f'2026-10-{day:02d}','收益':'1000' if day==5 else '0'} for day in range(5,12)]]:
            week=scope['calc_week_summary']('2026-10-05',pd.DataFrame(rows),fixed);self.assertEqual(week['本周固定成本'],Decimal('700'));self.assertEqual(week['本周净利'],Decimal('300'));self.assertEqual(week['活跃天数'],1)
        self.assertIsNone(scope['calc_month_summary'](2026,12,empty,fixed))
        RESULTS['D004']={'week_fixed':'700.00','fixed_only_month_and_year':'-3100.00','zero_days_not_active':True,'future_month_ignored':True}

    def test_D005_total_only_legacy_and_explicit_channel_zero(self):
        scope=env();money(scope);daily=[{'日期':'2026-10-02','收益':'1000.00'}]
        scope.update(load_daily=lambda:pd.DataFrame(daily),load_fixed_expenses=lambda:pd.DataFrame(),load_inventory_entries=lambda:[],FIXED_EXPENSE_CASH_COLUMN='计入可用余额',_cash_position_source_frames=lambda:(pd.DataFrame(daily),pd.DataFrame()))
        functions(scope,{'_cash_position_ledger'});optional(scope,{'_cash_daily_revenue'})
        value=lambda:scope['_cash_position_ledger']({'base_balance':'0','as_of_date':'2026-10-01'})['current']
        self.assertEqual(value(),Decimal('1000'))
        daily[:]=[{'日期':'2026-10-02','总金额':'123.45'}];self.assertEqual(value(),Decimal('123.45'))
        daily[:]=[{'日期':'2026-10-02','收益':'1000','总金额':'999','A店现金':'0'}];self.assertEqual(value(),Decimal('0'))
        RESULTS['D005']={'total_only':'1000.00','legacy_total':'123.45','explicit_channel_zero':'0.00'}

    def test_D006_oversize_and_corrupt_json_never_replace_existing_file(self):
        scope=env();money(scope);scope.update(_ensure_internal_storage_access=lambda p:None,read_excel_exact=lambda workbook,**kw:pd.read_excel(workbook,**kw,dtype=object,keep_default_na=False))
        functions(scope,{'_write_internal_frames','_validate_internal_frames_integrity'});write=scope['_write_internal_frames']
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'store.xlsx';good=frames_for({'entries':[]},'inventory');write(str(path),good);before=path.read_bytes()
            entries=[{'id':str(i),'name':'测试食材','date':'2026-10-02','note':'普通采购入库'*8,'quantity':'10','total':'100.00'} for i in range(300)]
            oversized=frames_for({'entries':entries},'inventory');self.assertGreater(len(oversized['__global_records'].iloc[0]['payload_json']),32767)
            caught=None
            try:write(str(path),oversized)
            except ValueError as exc:caught=exc
            self.assertIsNotNone(caught);self.assertEqual(path.read_bytes(),before)
            broken=frames_for({});broken['__global_records'].loc[0,'payload_json']='{broken'
            with self.assertRaises(ValueError):write(str(path),broken)
            self.assertEqual(path.read_bytes(),before)
            # Real readback fault: an intact XLSX container is insufficient.
            scope['read_excel_exact']=lambda workbook,**kw:pd.read_excel(workbook,**kw,dtype=object,keep_default_na=False).assign(payload_json='{}') if kw['sheet_name']=='__global_records' else pd.read_excel(workbook,**kw,dtype=object,keep_default_na=False)
            with self.assertRaises(ValueError):write(str(path),good)
            self.assertEqual(path.read_bytes(),before)
        RESULTS['D006']={'oversize_rejected':True,'malformed_json_rejected':True,'readback_mismatch_rejected':True,'old_file_bytes_unchanged':True}

    def test_D007_missing_internal_recovery_never_deletes_other_year(self):
        scope=env();money(scope);cloud={('day','2025-10-01'):record('2025-10-01',100),('day','2026-10-01'):record('2026-10-01',200)};local={};deleted=[]
        baseline={'\0'.join(k):{'local_hash':v['checksum'],'cloud_hash':v['checksum'],'cloud_version':1} for k,v in cloud.items()};config={'embedded_baselines':{'book':copy.deepcopy(baseline)},'embedded_last_dataset_id':'book'}
        def import_user(*a):local.update({k:copy.deepcopy(v) for k,v in cloud.items() if k[1].startswith('2026')})
        def apply(records,replace_all=False,**kw):
            if replace_all:local.clear()
            for row in records:
                key=(row['record_type'],row['record_key'])
                if row.get('is_deleted'):local.pop(key,None)
                else:local[key]=copy.deepcopy(row)
        scope.update(FIXED_CLOUD_DATASET_ID='book',FILE_PATH='old-user',INTERNAL_FILE_PATH='old-internal',ACTIVE_USER_EXCEL_YEAR=2026,ACTIVE_DATASET_ID='book',
            validate_data_excel=lambda p,**k:p,_infer_user_excel_year=lambda *a:2026,normalize_excel_path=lambda p:p,
            write_user_workbook_metadata=lambda *a:None,_write_internal_frames=lambda *a:None,_default_internal_frames=lambda:{},sync_user_excel_to_internal=import_user,
            _read_internal_frames=lambda p:{},_set_app_baseline_from_internal=lambda *a:None,save_path_config=lambda *a:None,_write_cloud_override_request=lambda *a:None,trigger_sync_assistant_now=lambda:None,
            _embedded_local_records=lambda:copy.deepcopy(local),_embedded_apply_cloud_records=apply,save_embedded_sync_config=lambda c:None,load_embedded_sync_config=lambda:config)
        functions(scope,{'_create_internal_automatically_from_user'});scope['_create_internal_automatically_from_user']('/synthetic/2026.xlsx','/synthetic/missing.xlsx')
        cls=methods(scope,'EmbeddedCloudSyncWorker',{'_sync_records','_build_baseline','_cloud_marker'});obj=cls();obj._effective_role=lambda *a:'admin';obj.snapshot=lambda:{}
        obj._put_local=lambda *a:(_ for _ in ()).throw(AssertionError('unexpected upload'))
        def delete(cfg,ds,row):deleted.append((row['record_type'],row['record_key']));return dict(row,is_deleted=True,version=2)
        obj._delete_cloud=delete;obj._fetch_cloud_records=lambda *a:list(copy.deepcopy(cloud).values())
        obj._sync_records(config,'book',list(copy.deepcopy(cloud).values()),'admin')
        self.assertEqual(deleted,[]);self.assertEqual(set(local),set(cloud));self.assertNotIn('embedded_cache_recovery',config)
        RESULTS['D007']={'cloud_deletions':deleted,'restored_years':[2025,2026]}

    def test_D008_real_form_handler_rejects_stale_background_editor(self):
        background_baseline_overwrite()
        RESULTS['D008']=RESULTS.pop('background_baseline_overwrite')

    def test_D008_clean_reload_binds_snapshot_after_widgets_and_modal_defers(self):
        for modal in (False, True):
            scope=env();events=[];callbacks=[];snapshot={'snapshot':'mirrored'}
            scope.update(INTERNAL_FILE_PATH='memory',FILE_PATH='mirror',ACTIVE_DATASET_ID='book',ACTIVE_USER_EXCEL_YEAR=2026,
                internal_sync_lock=lambda p:nullcontext(),_read_internal_frames=lambda p:snapshot,
                _sync_internal_to_user_excels_unlocked=lambda **kw:events.append(('mirror',kw['update_baseline'])),
                sync_internal_to_user_excels=lambda **kw:events.append(('mirror',kw['update_baseline'])),
                _file_signature=lambda p:('captured',p),
                _set_app_baseline_from_internal=lambda frame,*args:events.append(('baseline',frame)),
                QApplication=types.SimpleNamespace(activeModalWidget=lambda:object() if modal else None),
                threading=types.SimpleNamespace(Thread=lambda target,**kw:types.SimpleNamespace(start=target)),
                QTimer=types.SimpleNamespace(singleShot=lambda delay,fn:callbacks.append(fn)))
            cls=methods(scope,'MainWindow',{'_refresh_cloud_files_in_background'});obj=cls();obj._cloud_file_refresh_busy=False
            obj._last_internal_signature='old';obj._unsaved_sections=lambda:[]
            obj.statusBar=lambda:types.SimpleNamespace(showMessage=lambda *a:None)
            obj._refresh_visible_tab_after_cloud_update=lambda:events.append(('widgets','loaded'))
            obj._refresh_cloud_files_in_background()
            while callbacks:callbacks.pop(0)()
            self.assertEqual(events[0],('mirror',False))
            if modal:
                self.assertEqual(len(events),1);self.assertEqual(obj._last_internal_signature,'old')
            else:
                self.assertEqual(events[1:], [('widgets','loaded'),('baseline',snapshot)])
                self.assertEqual(obj._last_internal_signature,('captured','memory'))

    def test_W009_structured_and_legacy_detail_contract(self):
        scope=env();money(scope);functions(scope,{'_inventory_detail_items','detail_total_cost','parse_cost_detail_part','replace_units_in_detail','_entry_item_key','_entry_detail_token_list','_entry_detail_tokens','_entry_item_signature'})
        optional(scope,{'_detail_json_rows','_detail_record','_detail_parts','_serialize_detail_records'})
        cls=methods(scope,'PurchaseDetailTab',{'_parse_detail','_detail_tuple_to_string'});obj=cls()
        raw=json.dumps([{'name':'青菜,有机','quantity':'2','unit':'斤','price':'','total':'','note':'备注: 一,二；三'},{'name':'鸡蛋','quantity':'0','unit':'个','price':'0.000000','total':'0.00','note':''}],ensure_ascii=False)
        parsed=obj._parse_detail(raw);self.assertEqual(len(parsed),2);self.assertEqual(parsed[0][:5],('青菜,有机',Decimal('2'),'斤','',''));self.assertEqual(parsed[1][4],Decimal('0.00'))
        self.assertEqual(scope['detail_total_cost'](raw),0);self.assertEqual(obj._parse_detail('米 2斤 20.00')[0][4],Decimal('20.00'))
        self.assertEqual(scope['detail_total_cost']('米 2斤 20.00'),Decimal('20.00'))
        self.assertEqual(json.loads(scope['replace_units_in_detail'](raw,{'斤':'公斤'}))[0]['unit'],'公斤')
        self.assertEqual(len(scope['_entry_detail_tokens'](raw)),2)
        item=obj._detail_tuple_to_string(parsed[0]);self.assertEqual(item['name'],'青菜,有机');self.assertEqual(item['total'],'');self.assertEqual(item['note'],'备注: 一,二；三')
        RESULTS['W009']={'json_and_text_supported':True,'comma_names_notes_blank_and_zero_preserved':True}

    def test_B03_low_role_cash_removed_locally_without_cloud_delete(self):
        scope=env();money(scope);local={('global','cash_position'):{'record_type':'global','record_key':'cash_position','checksum':'private','payload':{'base_balance':'10'}}};deleted=[]
        def apply(rows,**kwargs):
            for row in rows:local.pop((row['record_type'],row['record_key']),None)
        scope.update(_embedded_local_records=lambda:copy.deepcopy(local),_embedded_apply_cloud_records=apply,save_embedded_sync_config=lambda c:None,_embedded_payload_hash=lambda p:encode(p)[1])
        cls=methods(scope,'EmbeddedCloudSyncWorker',{'_sync_records','_build_baseline','_cloud_marker'});obj=cls();obj._effective_role=lambda *a:'entry';obj.snapshot=lambda:{}
        obj._put_local=lambda *a:deleted.append('put');obj._delete_cloud=lambda *a:deleted.append('delete');obj._fetch_cloud_records=lambda *a:[]
        config={'embedded_baselines':{'book':{'global\0cash_position':{'local_hash':'private','cloud_hash':'private','cloud_version':1}}},'embedded_last_dataset_id':'book'}
        obj._sync_records(config,'book',[],'entry');self.assertEqual(local,{});self.assertEqual(deleted,[]);self.assertNotIn('global\0cash_position',config['embedded_baselines']['book'])
        RESULTS['B03']={'private_cache_removed':True,'no_cloud_mutation':True}

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DesktopAcceptance)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'results':RESULTS}
    print(json.dumps(report,ensure_ascii=False,indent=2,default=str))
    if os.environ.get('DESKTOP_TEST_REPORT'):Path(os.environ['DESKTOP_TEST_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
