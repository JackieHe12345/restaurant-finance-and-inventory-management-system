"""Offline Qt widgets + real XLSX compatibility checks; no network/user ledgers.
Use QT_QPA_PLATFORM=offscreen python build/test_v1_0_1_desktop_qt.py.
"""
import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
SOURCE=Path(os.environ.get('DESKTOP_SOURCE',str(Path(__file__).resolve().parents[1]/'desktop/restaurant_cost_manager.py')))
spec=importlib.util.spec_from_file_location('v1_0_1_desktop_test',SOURCE);appmod=importlib.util.module_from_spec(spec)
hook=sys.excepthook
spec.loader.exec_module(appmod)
sys.excepthook=hook
APP=appmod.QApplication.instance() or appmod.QApplication([])
class DesktopQtAcceptance(unittest.TestCase):
    def setUp(self):
        self.items=[{'name':'青菜,有机','quantity':'2','unit':'斤','price':'','total':'','note':'备注: 一,二；三'},
                    {'name':'鸡蛋','quantity':'0','unit':'个','price':'0.000000','total':'0.00','note':''},
                    {'name':'青菜,有机','quantity':'3','unit':'斤','price':'2.000000','total':'6.00','note':'第二批'}]
        self.raw=json.dumps(self.items,ensure_ascii=False)
        self.today=appmod.QDate.currentDate().toString('yyyy-MM-dd')
    def test_selector_widget_preserves_duplicates_unknown_and_zero(self):
        dictionary=appmod.pd.DataFrame([{'分类':'食材','词条名称':'鸡蛋'},{'分类':'食材','词条名称':'米'}])
        with patch.object(appmod,'load_ingredients',return_value=dictionary):
            dialog=appmod.ItemSelectDialog(self.raw,'食材')
            self.assertEqual(dialog.table.rowCount(),4)
            dialog.confirm_selection()
            actual=json.loads(dialog.selected_items_str)
            self.assertEqual(actual,self.items)
            dialog.close();dialog.deleteLater()
    def test_purchase_actual_refresh_save_and_move_preserves_data(self):
        frame=appmod.pd.DataFrame([{'日期':self.today,'食材明细':self.raw,'食材成本':'6.00','佐料明细':'盐 1斤 1.00','佐料成本':'1.00'}],dtype=object)
        saved=[]
        def save(value):saved.append(value.copy());frame.loc[:,:]=value
        with patch.object(appmod,'load_daily',side_effect=lambda:frame.copy()),patch.object(appmod,'save_daily',side_effect=save),patch.object(appmod.QMessageBox,'information',return_value=appmod.QMessageBox.Ok),patch.object(appmod.QMessageBox,'question',return_value=appmod.QMessageBox.Yes):
            tab=appmod.PurchaseDetailTab('食材');tab.refresh_data()
            self.assertEqual(tab.table.rowCount(),3);self.assertEqual(tab.table.item(0,4).text(),'');self.assertEqual(tab.table.item(1,5).text(),'0.00')
            tab.save_data();self.assertEqual(json.loads(saved[-1].iloc[0]['食材明细']),self.items)
            tab.table.item(0,0).setCheckState(appmod.Qt.Checked);tab.move_selected_to_other_category()
            self.assertEqual(json.loads(saved[-1].iloc[0]['食材明细']),self.items[1:])
            moved=json.loads(saved[-1].iloc[0]['佐料明细']);self.assertEqual(moved[-1],self.items[0]);self.assertEqual(moved[0]['name'],'盐')
            tab.close();tab.deleteLater()
    def test_W009_derived_amount_survives_purchase_save_and_move(self):
        source_items=[{'name':'米','quantity':'2','unit':'斤','price':'3.000000','total':'','note':'按数量和单价计价'},
                      {'name':'赠品','quantity':'2','unit':'个','price':'3.000000','total':'0.00','note':'明确零总价'},
                      {'name':'待定价','quantity':'2','unit':'斤','price':'','total':'','note':''}]
        destination_items=[{'name':'盐','quantity':'4','unit':'斤','price':'0.500000','total':'','note':''}]
        frame=appmod.pd.DataFrame([{'日期':self.today,'食材明细':json.dumps(source_items,ensure_ascii=False),'食材成本':'6.00',
                                  '佐料明细':json.dumps(destination_items,ensure_ascii=False),'佐料成本':'2.00'}],dtype=object)
        saved=[]
        def save(value):saved.append(value.copy());frame.loc[:,:]=value
        with patch.object(appmod,'load_daily',side_effect=lambda:frame.copy()),patch.object(appmod,'save_daily',side_effect=save),patch.object(appmod.QMessageBox,'information',return_value=appmod.QMessageBox.Ok),patch.object(appmod.QMessageBox,'question',return_value=appmod.QMessageBox.Yes):
            tab=appmod.PurchaseDetailTab('食材');tab.refresh_data()
            self.assertEqual(tab.table.item(0,5).text(),'')
            tab.save_data()
            self.assertEqual(saved[-1].iloc[0]['食材成本'],appmod.Decimal('6.00'))
            self.assertIn('6.00',tab.lbl_total_cost.text())
            self.assertEqual(json.loads(saved[-1].iloc[0]['食材明细']),source_items)
            tab.table.item(0,0).setCheckState(appmod.Qt.Checked);tab.move_selected_to_other_category()
            self.assertEqual(saved[-1].iloc[0]['食材成本'],appmod.Decimal('0.00'))
            self.assertEqual(saved[-1].iloc[0]['佐料成本'],appmod.Decimal('8.00'))
            self.assertEqual(json.loads(saved[-1].iloc[0]['食材明细']),source_items[1:])
            self.assertEqual(json.loads(saved[-1].iloc[0]['佐料明细']),destination_items+[source_items[0]])
            tab.close();tab.deleteLater()

    def test_D003_cash_alias_migration_checks_loaded_record_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'internal.xlsx';ds=appmod.FIXED_CLOUD_DATASET_ID
            frames=appmod._default_internal_frames();frames['__meta']=appmod.pd.DataFrame([{'dataset_id':ds,'schema_version':2,'last_synced_at':''}])
            old={'base_balance':'100.00','as_of_date':'2026-10-01','transactions':[]}
            raw,digest=appmod._payload_and_hash(old)
            frames['__global_records']=appmod._replace_internal_record(frames['__global_records'],ds,'记录类型','cash_balance',raw,digest)
            appmod._write_internal_frames(str(path),frames)
            with patch.object(appmod,'INTERNAL_FILE_PATH',str(path)),patch.object(appmod,'require_network_edit',return_value=None),patch.object(appmod,'_desktop_cloud_role',return_value='admin'),patch.object(appmod,'_set_internal_sync_pending',return_value=None),patch.object(appmod,'trigger_embedded_sync_now',return_value=None):
                loaded=appmod._load_global_record_payload(appmod.CASH_POSITION_RECORD_KEY,appmod.CASH_POSITION_ALIASES)
                self.assertEqual(loaded,old);expected=appmod._payload_and_hash(loaded)[1]
                remote={**old,'transactions':[{'id':'remote','date':'2026-10-02','kind':'收入','amount':'20.00'}]}
                raw,digest=appmod._payload_and_hash(remote);frames=appmod._read_internal_frames(str(path))
                frames['__global_records']=appmod._replace_internal_record(frames['__global_records'],ds,'记录类型','cash_balance',raw,digest)
                appmod._write_internal_frames(str(path),frames);before=path.read_bytes()
                with self.assertRaises(appmod.ExcelAccessError):appmod.save_cash_position_record(old,expected_hash=expected)
                self.assertEqual(path.read_bytes(),before)
                loaded=appmod._load_global_record_payload(appmod.CASH_POSITION_RECORD_KEY,appmod.CASH_POSITION_ALIASES)
                clean=appmod.save_cash_position_record({**loaded,'base_balance':'120.00'},expected_hash=appmod._payload_and_hash(loaded)[1])
                self.assertEqual(clean['transactions'],remote['transactions'])
                read=appmod._read_internal_frames(str(path))
                self.assertIsNotNone(appmod._internal_payload_for_identity(read,ds,('global','cash_position')))
                self.assertEqual(appmod._load_global_record_payload(appmod.CASH_POSITION_RECORD_KEY,appmod.CASH_POSITION_ALIASES),clean)

    def test_B07_source_order_survives_real_excel_and_new_write_advances_rank(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'internal.xlsx';frames=appmod._default_internal_frames();ds=appmod.FIXED_CLOUD_DATASET_ID
            frames['__meta']=appmod.pd.DataFrame([{'dataset_id':ds,'schema_version':2,'last_synced_at':''}])
            rows=[]
            for key,order,revenue in [('2026-10-02',2,'200.00'),('2026-10-01',1,'100.00')]:
                payload={'daily':[{'日期':'2026-10-02','收益':revenue}]};raw,digest=appmod._payload_and_hash(payload)
                rows.append({'dataset_id':ds,'日期':key,'payload_json':raw,'sha256':digest,'source_order':order})
            frames['__day_records']=appmod.pd.DataFrame(rows)
            raw,digest=appmod._payload_and_hash({'ingredients':[]})
            frames['__global_records']=appmod.pd.DataFrame([{'dataset_id':ds,'记录类型':'ingredients','payload_json':raw,'sha256':digest,'source_order':3}])
            appmod._write_internal_frames(str(path),frames);read=appmod._read_internal_frames(str(path))
            self.assertEqual(list(read['__day_records']['source_order']),[2,1])
            with patch.object(appmod,'INTERNAL_FILE_PATH',str(path)):
                self.assertEqual(appmod._inventory_day_sheet('daily').iloc[0]['收益'],'200.00')
                raw,digest=appmod._payload_and_hash({'daily':[{'日期':'2026-10-02','收益':'300.00'}]})
                read['__day_records']=appmod._replace_internal_record(read['__day_records'],ds,'日期','2026-10-01',raw,digest)
                appmod._write_internal_frames(str(path),read)
                self.assertEqual(appmod._inventory_day_sheet('daily').iloc[0]['收益'],'300.00')
                after=appmod._read_internal_frames(str(path))
                ranks=list(after['__day_records']['source_order'])+list(after['__global_records']['source_order'])
                self.assertEqual(sorted(ranks),[1,2,3]);self.assertGreater(after['__day_records'].iloc[-1]['source_order'],after['__day_records'].iloc[0]['source_order'])
    def test_B07_live_sync_same_payload_metadata_and_mixed_upload_priority(self):
        def make(key, amount, sequence, version=1):
            payload={'daily':[{'日期':'2026-10-02','收益':amount}]}
            return {'record_type':'day','record_key':key,'payload':payload,'checksum':appmod._payload_and_hash(payload)[1],
                    'sequence':sequence,'version':version}
        for scenario in ('same_payload_sequence','changed_payloads','mixed_upload'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'internal.xlsx';frames=appmod._default_internal_frames();ds=appmod.FIXED_CLOUD_DATASET_ID
                frames['__meta']=appmod.pd.DataFrame([{'dataset_id':ds,'schema_version':2,'last_synced_at':''}]);appmod._write_internal_frames(str(path),frames)
                before=[make('2026-10-01','100.00',1),make('2026-10-02','200.00',2)]
                with patch.object(appmod,'INTERNAL_FILE_PATH',str(path)),patch.object(appmod,'save_embedded_sync_config',return_value=None):
                    appmod._embedded_apply_cloud_records(before,replace_all=True)
                    worker=appmod.EmbeddedCloudSyncWorker();config={'embedded_last_dataset_id':'book','embedded_baselines':{'book':worker._build_baseline(appmod._embedded_local_records(),{(row['record_type'],row['record_key']):row for row in before})}}
                    if scenario=='mixed_upload':
                        pending=make('2026-10-01','150.00',1);appmod._embedded_apply_cloud_records([pending])
                        incoming=[before[0],make('2026-10-02','250.00',3,2)]
                        worker._put_local=lambda cfg,ds,local,*args:dict(local,sequence=4,version=2)
                        expected='150.00'
                    elif scenario=='changed_payloads':
                        incoming=[make('2026-10-01','110.00',4,2),make('2026-10-02','210.00',3,2)];expected='110.00'
                    else:
                        incoming=[make('2026-10-01','100.00',4,2),make('2026-10-02','200.00',3,2)];expected='100.00'
                    self.assertEqual(worker._sync_records(config,'book',incoming,'admin'),[])
                    self.assertEqual(appmod._inventory_day_sheet('daily').iloc[0]['收益'],expected)
                    self.assertEqual(config['embedded_baselines']['book']['day\0'+'2026-10-01']['cloud_sequence'],4)
                    # A second unchanged cycle must not alter the winner or write content.
                    if scenario=='mixed_upload':incoming[0]=make('2026-10-01','150.00',4,2)
                    self.assertEqual(worker._sync_records(config,'book',incoming,'admin'),[])
                    self.assertEqual(appmod._inventory_day_sheet('daily').iloc[0]['收益'],expected)

    def test_W009_entry_text_to_JSON_migration_keeps_original_clocks(self):
        now=appmod.datetime.now().astimezone();old_time=now-appmod.timedelta(hours=1)
        old_text='米 1斤 10.00'
        original={'日期':self.today,'食材明细':old_text,'食材成本':'10.00','updated_at':old_time.isoformat(timespec='seconds')}
        migrated=[{'name':'米','quantity':'1','unit':'斤','price':'10.000000','total':'10.00','note':''},
                  {'name':'菜','quantity':'1','unit':'斤','price':'5.000000','total':'5.00','note':''}]
        new={**original,'食材明细':json.dumps(migrated,ensure_ascii=False),'食材成本':'15.00'}
        windows={self.today:{'details':{'食材':{'items':[{'id':'old-id','text':old_text,'saved_at':old_time.isoformat(timespec='seconds'),
                   'edit_deadline':(old_time+appmod.ENTRY_EDIT_WINDOW).isoformat(timespec='seconds'),'active':True}]}},
                   'detail_started_at_by_category':{'食材':old_time.isoformat(timespec='seconds')}}}
        self.assertEqual(appmod._entry_normalized_token(old_text),appmod._entry_normalized_token(json.dumps(migrated[0],ensure_ascii=False)))
        state,error=appmod._entry_validate_and_update_windows(windows,self.today,original,new,now=now,enforce=True)
        self.assertFalse(error);items=state['details']['食材']['items'];self.assertEqual(len(items),2)
        self.assertEqual(items[0]['id'],'old-id');self.assertEqual(items[0]['saved_at'],old_time.isoformat(timespec='seconds'))
        changed=json.loads(new['食材明细']);changed[0]['total']='11.00';changed[0]['price']='11.000000'
        _state,error=appmod._entry_validate_and_update_windows(windows,self.today,new,{**new,'食材明细':json.dumps(changed,ensure_ascii=False),'食材成本':'16.00'},now=now,enforce=True)
        self.assertIsNotNone(error);self.assertIn('30分钟',error)
        unknown={'name':'米','quantity':'1','unit':'斤','price':'','total':'','note':''}
        zero={**unknown,'price':'0.000000','total':'0.00'}
        self.assertNotEqual(appmod._entry_normalized_token(json.dumps(unknown,ensure_ascii=False)),appmod._entry_normalized_token(json.dumps(zero,ensure_ascii=False)))

    def test_W009_unknown_purchase_quantity_and_known_price_statistics(self):
        import types
        tab=types.SimpleNamespace()
        tab._parse_food_part=types.MethodType(appmod.MoreStatsTab._parse_food_part,tab)
        tab._food_group_value=types.MethodType(appmod.MoreStatsTab._food_group_value,tab)
        tab._food_frame=types.MethodType(appmod.MoreStatsTab._food_frame,tab)
        tab.WEEKDAY_NAMES=appmod.MoreStatsTab.WEEKDAY_NAMES;tab.selected_food_items={'米'}
        items=[{'name':'米','quantity':'10','unit':'斤','price':'2.000000','total':'20.00'},
               {'name':'米','quantity':'10','unit':'斤','price':'','total':''}]
        tab._filtered_daily=lambda:appmod.pd.DataFrame([{'日期':'2026-10-01','食材明细':json.dumps(items,ensure_ascii=False)}])
        frame=tab._food_frame();self.assertEqual(len(frame),2)
        self.assertEqual(tab._food_group_value(frame,'每月采购量'),appmod.Decimal('20'))
        self.assertEqual(tab._food_group_value(frame,'单价随时间变化'),appmod.Decimal('2'))
        unknown=frame[frame['总价'].isna()];self.assertTrue(appmod.pd.isna(tab._food_group_value(unknown,'每月平均单价')))
        self.assertEqual(tab._food_group_value(unknown,'每月采购量'),appmod.Decimal('10'))
        tables=[];tab._set_table=tables.append;tab._selected_modes=lambda:(True,True)
        appmod.MoreStatsTab.update_food_table(tab,frame,'单价随时间变化')
        detail=tables[-1].iloc[1];summary=tables[-1].iloc[-1]
        self.assertEqual(detail['数量'],appmod.Decimal('10'));self.assertEqual(detail['总价'],'待定价')
        self.assertEqual(summary['数量'],appmod.Decimal('20'));self.assertEqual(summary['待定价数量'],appmod.Decimal('10'));self.assertEqual(summary['单价'],appmod.Decimal('2'))
        zero=tab._parse_food_part({'name':'米','quantity':'10','unit':'斤','price':'0','total':'0'})
        self.assertEqual(zero['总价'],appmod.Decimal('0'));self.assertEqual(zero['单价'],appmod.Decimal('0'))
        self.assertEqual(tab._parse_food_part('米 10斤 20.00')['总价'],appmod.Decimal('20'))

    def test_W009_ledger_real_widgets_display_edit_and_save_losslessly(self):
        frame=appmod.pd.DataFrame([{'日期':self.today,'收益':'0.00','食材明细':self.raw,'食材成本':'6.00','佐料明细':self.raw,'佐料成本':'6.00','其他':'0.00','当日备注':'原备注'}],dtype=object)
        fixed=appmod.pd.DataFrame(columns=appmod.STANDARD_SHEET_COLUMNS['monthly_fixed']);saved=[]
        dictionary=appmod.pd.DataFrame([{'分类':'食材','词条名称':'鸡蛋'}])
        def save(value):saved.append(value.copy());frame.loc[:,:]=value[frame.columns]
        def choose(dialog):
            self.assertEqual(dialog.table.item(0,1).text(),'青菜,有机')
            self.assertEqual(dialog.table.cellWidget(0,5).text(),'')
            dialog.table.cellWidget(0,2).setText('4');dialog.confirm_selection();return appmod.QDialog.Accepted
        with patch.object(appmod,'load_daily',side_effect=lambda:frame.copy()),patch.object(appmod,'load_monthly_fixed',return_value=fixed),patch.object(appmod,'load_fixed_expenses',return_value=appmod.pd.DataFrame(columns=appmod.FIXED_EXPENSE_COLUMNS)),patch.object(appmod,'_load_entry_windows',return_value={}),patch.object(appmod.LedgerTab,'_activate_user_excel_for_date',return_value=True),patch.object(appmod,'load_ingredients',return_value=dictionary),patch.object(appmod,'save_daily',side_effect=save),patch.object(appmod,'_desktop_effective_role',return_value='admin'),patch.object(appmod,'_inventory_purchase_entries',return_value=([],[])),patch.object(appmod.QMessageBox,'information',return_value=appmod.QMessageBox.Ok),patch.object(appmod.QMessageBox,'question',return_value=appmod.QMessageBox.Yes):
            ledger=appmod.LedgerTab();ledger._role='admin'
            self.assertNotIn('"name"',ledger.entry_food_detail.displayText());self.assertIn('待定价',ledger.entry_food_detail.displayText())
            self.assertTrue(ledger.entry_food_detail.isReadOnly());self.assertEqual(ledger.entry_food_detail.text(),self.raw)
            self.assertNotIn('"name"',ledger.table.item(1,7).text());self.assertIn('青菜,有机',ledger.table.item(1,7).text())
            ledger.entry_daily_note.setText('只改备注');ledger.save_record('overwrite');self.assertEqual(saved[-1].iloc[0]['食材明细'],self.raw)
            with patch.object(appmod.ItemSelectDialog,'exec',choose):ledger.open_item_manager(ledger.entry_food_detail,'食材')
            changed=json.loads(ledger.entry_food_detail.text());self.assertEqual(changed[0]['quantity'],'4');self.assertEqual(changed[0]['total'],'');self.assertEqual(changed[0]['note'],self.items[0]['note'])
            self.assertEqual(len(changed),3);self.assertNotIn('"name"',ledger.entry_food_detail.displayText())
            ledger.save_record('overwrite');self.assertEqual(json.loads(saved[-1].iloc[0]['食材明细']),changed)
            # Offline read-only masking must not leave a later plain-text row locked.
            original=getattr(ledger.entry_food_detail,'_detail_requested_readonly',ledger.entry_food_detail.isReadOnly())
            ledger.entry_food_detail.setReadOnly(True);ledger.entry_food_detail.setReadOnly(original);ledger.entry_food_detail.clear()
            self.assertFalse(ledger.entry_food_detail.isReadOnly());ledger.entry_food_detail.setText('米 1斤 10');self.assertEqual(ledger.entry_food_detail.text(),'米 1斤 10')
            ledger.close();ledger.deleteLater()

    def test_W009_dish_real_widget_summary_keeps_raw_storage(self):
        dish={'菜品名称':'测试菜','份数':1,'食材明细':self.raw,'成本':'6.00','备注':'原备注','分区':'菜品'}
        frame=appmod.pd.DataFrame([{'日期':self.today,'菜品数据':json.dumps([dish],ensure_ascii=False),'菜品明细':'测试菜','总成本':'6.00','备注':''}],dtype=object);saved=[]
        def save(value):saved.append(value.copy())
        with patch.object(appmod,'load_dishes',return_value=frame),patch.object(appmod,'save_dishes',side_effect=save),patch.object(appmod.DishTab,'update_ingredient_summary',return_value=None),patch.object(appmod.QMessageBox,'information',return_value=appmod.QMessageBox.Ok):
            tab=appmod.DishTab();item=tab.table.item(0,2)
            self.assertNotIn('"name"',str(item.data(appmod.Qt.DisplayRole)));self.assertIn('待定价',str(item.data(appmod.Qt.DisplayRole)))
            self.assertEqual(item.text(),self.raw);tab.table.item(0,4).setText('只改备注');tab.save_data()
            value=json.loads(saved[-1].iloc[0]['菜品数据'])[0];self.assertEqual(value['食材明细'],self.raw);self.assertEqual(value['备注'],'只改备注')
            tab.close();tab.deleteLater()

if __name__=='__main__':unittest.main(verbosity=2)
