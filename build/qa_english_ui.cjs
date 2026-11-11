'use strict';
// Runs the shipped UI against synthetic data only; all network traffic is blocked.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{pathToFileURL}=require('url');
const source=path.resolve(process.env.RELEASE_SOURCE_ROOT||path.join(__dirname,'..')),out=process.env.QA_OUTPUT_DIR;
if(!out)throw new Error('QA_OUTPUT_DIR is required');fs.mkdirSync(out,{recursive:true});
const report={revision:'20261111-live-forecast-r2',data:'synthetic only',network:'blocked',pages:[],dialogs:[],errors:[]};
async function settle(page){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));}
async function scan(page,tag){await settle(page);const result=await page.evaluate(()=>{
 const texts=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){const n=walker.currentNode,p=n.parentElement;if(!p||!p.getClientRects().length||p.closest('script,style,textarea,[data-user-content],#accountLabel,#datasetSelect,#workbookDatasetName,#storeSettingsDataset'))continue;let fixedText=n.nodeValue;if(typeof v26OriginalTexts!=='undefined'&&v26OriginalTexts.has(n))for(const slot of ['A','B'])fixedText=fixedText.split(storeName(slot)).join('');if(/[\u3400-\u9fff]/.test(fixedText))texts.push({text:n.nodeValue.trim(),id:p.id,tag:p.tagName});}
 for(const p of document.querySelectorAll('[placeholder],[title],[aria-label]'))if(p.getClientRects().length&&!p.closest('[data-user-content]'))for(const a of ['placeholder','title','aria-label']){const text=p.getAttribute(a);if(text&&/[\u3400-\u9fff]/.test(text))texts.push({text,attr:a,id:p.id});}
 return {texts,documentOverflow:document.documentElement.scrollWidth>innerWidth+1};
 });report.pages.push({tag,...result});return result;}
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
try{
 const ctx=await browser.newContext({viewport:{width:1600,height:1100},timezoneId:'Asia/Shanghai',locale:'en-US'});await ctx.route(/^https?:/,r=>r.abort());
 const page=await ctx.newPage();page.on('pageerror',e=>report.errors.push(e.message));page.on('dialog',async d=>{report.dialogs.push(d.message());await d.dismiss();});
 await page.clock.setFixedTime(new Date('2026-11-10T12:00:00+08:00'));
 await page.goto(pathToFileURL(path.join(source,'web/index.html')).href);
 await page.evaluate(async()=>{
  const day='2026-11-09',name='收入',note='删除；食材 → 管理员';
  const items=JSON.stringify([{name,quantity:'2',unit:'公斤',price:'3.25',total:'6.50',note}]);
  const rows=[{record_type:'day',record_key:day,version:1,payload:{daily:[{日期:day,收益:'2000',食材成本:'6.50',食材明细:items,佐料明细:JSON.stringify([{name:'删除',quantity:'1',unit:'袋',total:'2',note}]),佐料成本:'2',其他:'5',其他明细:note,当日备注:note,总客人数:'30'}],dishes:[{日期:day,菜品数据:JSON.stringify([{菜品名称:'管理员',份数:'1',食材明细:items,成本:'6.5',备注:note,分区:'菜品'}])}],fixed_expenses:[{日期:day,类别:'人工',明细:'删除',金额:'100',计入可用余额:true}]}},
  {record_type:'month',record_key:'2026-11',version:1,payload:{monthly_fixed:[{月份:'2026-11',人工总额:'100',房租总额:'300'}]}},
  {record_type:'global',record_key:'ingredients',version:1,payload:{ingredients:[{词条名称:'收入',分类:'食材'},{词条名称:'删除',分类:'佐料'},{词条名称:'管理员',分类:'食材'}]}},
  {record_type:'global',record_key:'inventory',version:1,payload:{entries:[{id:'qa-stock',date:'2026-11-01',category:'食材',name:'收入',quantity:'10',unit:'公斤',unit_price:'3.25',total:'32.50',note}]}},
  {record_type:'global',record_key:'cash_position',version:1,payload:{opening_balance:'100',opening_date:'2026-11-01',transactions:[{id:'qa-cash',date:day,type:'其它现金收入',description:'收入',amount:'10',mode:'delta',system_locked:false}]}}];
  previewDatasets=[{id:'preview',name:'收入',is_active:true,is_test:false},{id:'other',name:'删除',is_active:true,is_test:false}];
  previewUser={id:'qa-admin',username:'管理员',display_name:'管理员',role:'admin',default_dataset_id:'preview',dataset_ids:['preview','other']};previewRecordStores.set('preview',rows);
  const originalApi=api;window.qaWrites=[];
  api=async function(url,options={}){
   if(options.method&&options.method!=='GET')qaWrites.push({url,method:options.method});
   if(url==='/devices/register')return {id:'qa-browser',device_id:'qa-browser'};
   if(url==='/users')return [previewUser,{id:'qa-editor',username:'删除',display_name:'收入',role:'editor',dataset_ids:['preview'],default_dataset_id:'preview',is_active:true}];
   if(url.endsWith('/store-settings'))return {store_a_name:'删除',store_b_name:'保存',wechat_auto_sync:false,wechat:{}};
   if(url.endsWith('/cash-position'))return {opening_balance:'100',summary_month:'2026-11',transactions:unpackPayload(currentRecord('global','cash_position')).transactions};
   if(url.startsWith('/audit'))return [{id:'qa-audit',actor_label:'管理员',action:'update',record_type:'day',record_key:day,created_at:'2026-11-09T10:00:00Z',change_summary:'当日备注：收入 → 删除；食材 → 管理员',before_payload:{daily:[{日期:day,当日备注:'收入'}]},after_payload:{daily:[{日期:day,当日备注:note}]}}];
   if(url.startsWith('/temporary-permissions'))return [];
   return originalApi(url,options);
  };
  setSession('preview',previewUser);await enterApp();clearInterval(state.autoRefresh);state.autoRefresh=null;state.language='en';applyLanguage();v8SyncDate(day);refreshOpenEditors();
  window.qaOriginalRecords=JSON.stringify(state.records);window.qaOriginalWrites=qaWrites.length;
 });
 const pages=['overview','ledger','food','spice','dishes','inventory','stats','workbooks','stores','data','users','cash','changes','grants'];
 for(const width of [1600,375,320]){await page.setViewportSize({width,height:1100});for(const section of pages){await page.evaluate(p=>{state.editorDirty=false;showPage(p);},section);await scan(page,`${section}-${width}`);if(width===1600&&['ledger','workbooks'].includes(section))await page.screenshot({path:path.join(out,`${section}-en.png`)});}}
 await page.evaluate(()=>{state.editorDirty=false;showPage('ledger');openFixedExpensesModal();});await scan(page,'fixed-expenses-modal');
 report.fixedCategory=await page.locator('#fixedExpenseRows select[data-fixed="类别"]').first().evaluate(e=>({value:e.value,text:e.selectedOptions[0].textContent}));assert.equal(report.fixedCategory.value,'人工');assert.equal(report.fixedCategory.text,'Labour');
 await page.evaluate(()=>closeProModal());
 await page.evaluate(()=>{openItemPicker('食材',JSON.stringify([{name:'收入',quantity:'2',unit:'公斤',total:'6.50',note:'删除'}]),()=>{});});await scan(page,'ingredient-picker');
 const names=await page.locator('[data-pick-name]').allTextContents();assert(names.includes('收入'));assert(names.includes('管理员'));report.preservedPickerNames=names;
 await page.evaluate(()=>closeProModal());
 await page.evaluate(()=>{state.editorDirty=false;showPage('cash');});await page.locator('#addCashItemV4').click();await scan(page,'cash-add-modal');
 report.cashTypes=await page.locator('[data-cash-type]').evaluate(e=>[...e.options].map(o=>({value:o.value,text:o.textContent})));assert(report.cashTypes.some(x=>x.value==='余额强制修改'&&x.text==='Force balance adjustment'));
 await page.locator('.cash-item-modal [data-close]').click();
 await page.evaluate(()=>{state.editorDirty=false;showPage('dishes');});
 report.userLedgerOptions=await page.locator('#userRows select[data-datasets] option').allTextContents();assert(report.userLedgerOptions.includes('收入'));assert(!report.userLedgerOptions.includes('Revenue'));
 report.dishNames=await page.locator('#dishRows [data-dish="name"]').evaluateAll(es=>es.map(e=>e.value));assert(report.dishNames.includes('管理员'));assert(report.dishNames.every(x=>!x.includes('<span')));
 await page.evaluate(()=>{state.editorDirty=false;showPage('food');});const values=await page.locator('#foodRows input,#foodRows textarea').evaluateAll(es=>es.map(e=>e.value));assert(values.includes('收入'));assert(values.includes('删除；食材 → 管理员'));
 await page.evaluate(()=>{for(const language of ['zh','en','zh','en']){state.language=language;applyLanguage();} });
 report.monthPresentation=await page.locator('input[type="month"]').first().evaluate(e=>({value:e.value,display:e.parentElement.querySelector('.iso-month-label').textContent,language:document.documentElement.lang}));assert.equal(report.monthPresentation.value,report.monthPresentation.display);assert.equal(report.monthPresentation.language,'en');
 report.languagePreservesData=await page.evaluate(()=>JSON.stringify(state.records)===qaOriginalRecords);assert(report.languagePreservesData);
 report.noLanguageWrites=await page.evaluate(()=>qaWrites.length===qaOriginalWrites);assert(report.noLanguageWrites);
 report.inputPreservation=await page.locator('#foodRows input,#foodRows textarea').evaluateAll(es=>es.map(e=>e.value));assert.deepEqual(report.inputPreservation,values);
 await page.evaluate(()=>alert('请选择日期并填写大于 0 的金额。'));assert(!/[\u3400-\u9fff]/.test(report.dialogs.at(-1)));
 report.protectedData=await page.evaluate(()=>({dataset:state.dataset.name,user:$('accountLabel').textContent,stores:[storeName('A'),storeName('B')]}));assert.equal(report.protectedData.dataset,'收入');assert(report.protectedData.user.includes('管理员'));assert.deepEqual(report.protectedData.stores,['删除','保存']);
 for(const role of ['viewer','entry','admin']){await page.evaluate(role=>{state.user.role=role;state.viewOnlyMode=role!=='admin';state.editorDirty=false;showPage('ledger');applyLanguage();},role);await scan(page,'permission-'+role);}
 await page.setViewportSize({width:1600,height:1100});await page.evaluate(()=>{state.user.role='admin';state.viewOnlyMode=false;state.editorDirty=false;showPage('cash');applyLanguage();});
 await page.locator('#addCashItemV4').click();await page.locator('[data-cash-type]').selectOption('余额强制修改');await page.locator('[data-cash-amount]').fill('123.45');await page.locator('[data-cash-description]').fill('收入');await page.locator('.cash-item-modal [data-save]').click();await page.locator('.cash-item-modal').waitFor({state:'detached'});
 report.englishCashWrite=await page.evaluate(()=>unpackPayload(currentRecord('global','cash_position')).transactions.find(r=>r.description==='收入'&&r.mode==='force'));assert.equal(report.englishCashWrite.type,'余额强制修改');assert.equal(report.englishCashWrite.amount,'123.45');
 await page.evaluate(()=>{state.editorDirty=false;showPage('ledger');openFixedExpensesModal();});await page.locator('#fixedExpenseRows [data-fixed="金额"]').first().fill('101.25');await page.locator('#proModalHost [data-save-fixed]').click();await page.locator('#fixedExpenseRows').waitFor({state:'detached'});
 report.englishFixedWrite=await page.evaluate(()=>dayPayload('2026-11-09').fixed_expenses[0]);assert.equal(report.englishFixedWrite.类别,'人工');assert.equal(report.englishFixedWrite.明细,'删除');assert.equal(report.englishFixedWrite.金额,'101.25');
 assert.deepEqual(report.errors,[]);
 report.untranslated=report.pages.filter(p=>p.texts.length);report.overflows=report.pages.filter(p=>p.documentOverflow);
 if(process.env.QA_DIAGNOSTIC!=='1'){assert.deepEqual(report.untranslated,[]);assert.deepEqual(report.overflows,[]);}
 report.passed=!report.untranslated.length&&!report.overflows.length;
 console.log(JSON.stringify({passed:report.passed,pages:report.pages.length,untranslated:report.untranslated,overflows:report.overflows,errors:report.errors}));
}finally{fs.writeFileSync(path.join(out,'english-ui-verification.json'),JSON.stringify(report,null,2));await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
