'use strict';
// Offline browser acceptance: real shipped UI, synthetic records, no HTTP access.
// PLAYWRIGHT_MODULE may be an absolute installed module path.
// CHROME_EXECUTABLE may select an installed Chrome/Chromium binary.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const source=path.resolve(process.env.RELEASE_SOURCE_ROOT||path.join(__dirname,'..'));
if(!process.env.QA_OUTPUT_DIR)throw new Error('Set QA_OUTPUT_DIR to a writable evidence directory');
const out=path.resolve(process.env.QA_OUTPUT_DIR);fs.mkdirSync(out,{recursive:true});
const report={revision:null,data:'synthetic only',network:'blocked',layouts:[],charts:[],errors:[]};
async function stable(page){await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));}
async function selectMonth(page,month){await page.evaluate(month=>{showPage('overview');$('selectedDate').value=`2026-${month}-09`;$('selectedMonth').value=String(Number(month));$('selectedYear').value='2026';renderDashboard();},month);await stable(page);}
async function chartGeometry(page,tag){
  await stable(page);
  const result=await page.locator('#pageStats svg.o30-svg:visible').evaluateAll(svgs=>svgs.map(svg=>{
    const box=svg.getBoundingClientRect();
    const ticks=[...svg.querySelectorAll('.o30-x-axis')].map(e=>{const b=e.getBoundingClientRect();return {text:e.textContent,left:b.left,right:b.right,top:b.top,bottom:b.bottom};});
    const overlaps=[];
    for(let i=0;i<ticks.length;i++)for(let j=i+1;j<ticks.length;j++){
      const a=ticks[i],b=ticks[j];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.7&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.7)overlaps.push([a.text,b.text]);
    }
    return {host:svg.parentElement.id,ticks,overlaps,outside:ticks.filter(t=>t.left<box.left-1||t.right>box.right+1||t.bottom>box.bottom+1),points:svg.querySelectorAll('[data-o30-index]').length};
  }));
  assert(result.length>=2,tag+' no chart');
  for(const item of result){assert(item.ticks.length>0,tag+' no x ticks');assert.deepEqual(item.overlaps,[],tag+' overlap '+JSON.stringify(item));assert.deepEqual(item.outside,[],tag+' clipped labels');}
  report.charts.push({tag,charts:result});
}
async function seedLedger(keepPolling=false){
   const rows=[];
   for(const [month,count,revenue,food]of [['09',30,1500,900],['10',31,2000,700],['11',10,2600,800]]){
    for(let i=1;i<=count;i++){
     const day=`2026-${month}-${String(i).padStart(2,'0')}`;
     rows.push({record_type:'day',record_key:day,version:1,payload:{daily:[{'日期':day,'收益':String(revenue),'食材成本':String(food),'食材明细':JSON.stringify([{name:'Synthetic staple',quantity:1,unit:'公斤',price:String(food),total:String(food)}]),'佐料成本':'50','总客人数':'45'}],fixed_expenses:i%3===1?[{'日期':day,'类别':i===1?'人工':i===4?'房租':i===7?'水费':i===10?'电费':i===13?'煤气费':'其它固定成本','明细':'Synthetic acceptance expense','金额':String(100+i*10)}]:[]}});
    }
    rows.push({record_type:'month',record_key:`2026-${month}`,version:1,payload:{monthly_fixed:[{'月份':`2026-${month}`,'人工总额':'6000','房租总额':'8000','水费支出':'400','电费支出':'600','煤气费':'300'}]}});
   }
   rows.push({record_type:'global',record_key:'cash_position',version:1,payload:{opening_balance:'1000.00',opening_date:'2026-09-01',transactions:[{id:'historical-lock',date:'2026-10-01',type:'余额强制修改',amount:'5000',mode:'force',system_locked:true,created_at:'2026-10-01T12:00:00Z'}]}});
   const originalApi=api;api=async function(url,options){if(url==='/devices/register')return {id:'synthetic-browser-device',device_id:'synthetic-browser-device'};if(url.endsWith('/cash-position'))return {opening_balance:'1000.00',summary_month:'2026-11'};return originalApi(url,options);};
   previewRecordStores.set('preview',rows);setSession('preview',previewUser);await enterApp();if(!keepPolling){clearInterval(state.autoRefresh);state.autoRefresh=null;}
}
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1600,height:1100},timezoneId:'Asia/Shanghai',locale:'zh-CN'});
  await context.route(/^https?:\/\//,r=>r.abort());
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
  await page.clock.setFixedTime(new Date('2026-11-10T12:00:00+08:00'));
  await page.goto(pathToFileURL(path.join(source,'web/index.html')).href);
  report.revision=await page.locator('html').getAttribute('data-build-revision');
  assert(report.revision,'The loaded application must expose its build revision');
  await page.evaluate(seedLedger);
  await selectMonth(page,'11');
  let cards=await page.locator('.o30-kpis article').allTextContents();
  const keys=await page.locator('.o30-kpis article').evaluateAll(es=>es.map(e=>e.dataset.overviewMetric));
  assert.deepEqual(keys,['avgRevenue','avgGross','forecast','avgNet','net']);
  assert(cards[1].includes('日均毛利润 (毛利率)'));assert(cards[3].includes('日均净利润 (净利率)'));assert(cards[4].includes('净利润 (净利率)'));
  assert(cards[3].includes('244.44'));assert(cards[3].includes('(8.5%)'));assert(cards[4].includes('2,200.00'));assert(cards[4].includes('(8.5%)'));
  assert(cards.every(t=>t.includes('比上个月')));
  report.currentCards=cards;
  await page.locator('#o30DashboardDetails').evaluate(e=>e.open=true);
  const monthly=await page.locator('#monthCard').textContent();
  assert(monthly.includes('(根据 本月预计成本 和 本月预计收入 计算)'));
  assert(monthly.includes('34,366.67'));assert(cards[2].includes('34,366.67'));assert(monthly.includes('平本 需要 日均收入 增加'));
  const netRows=await page.locator('#monthCard .metric-row').evaluateAll(es=>es.filter(e=>['净利润 (净利率)','日均净利润 (净利率)'].includes(e.querySelector('span')?.textContent)).map(e=>e.textContent));
  assert.equal(netRows.length,2);assert(netRows.every(row=>row.includes('(8.5%)')),JSON.stringify(netRows));report.monthlyNetRows=netRows;
  await page.locator('#monthCard').screenshot({path:path.join(out,'monthly-report-current.png')});
  for(const lang of ['zh','en']){
   await page.evaluate(lang=>{state.language=lang;applyLanguage();renderDashboard();},lang);
   for(const scope of ['overview','report']){
    const selector=`.forecast-info-button[aria-describedby="forecast-help-${scope}"]`;
    const trigger=page.locator(selector),popup=page.getByRole('tooltip');
    await trigger.hover();await popup.waitFor({state:'visible'});
    const formulas=await popup.innerText();
    assert(formulas.includes(lang==='zh'?'预计其他成本':'Other costs = total costs'));
    assert(formulas.includes(lang==='zh'?'含佐料':'including seasonings'));
    assert(formulas.includes(lang==='zh'?'零时':'midnight'));
    assert(formulas.includes(lang==='zh'?'今日':'today')||formulas.includes('今天已保存'));
    for(const entry of lang==='zh'?['预计月底盈亏 = 本月预计收入 − 本月预计成本。\n\n本月预计收入','。\n\n预计固定成本','固定成本)\n\n上月日均','两月持平','944.4444 元/天','8,500.00 元 ÷ 9','采用 2026-11']:['Cost inputs for this forecast','Tie','944.4444/day','CNY 8,500.00 ÷ 9','Selected 2026-11'])assert(formulas.includes(entry),entry+' missing in '+formulas);
    await popup.hover();assert.equal(await trigger.getAttribute('aria-expanded'),'true');
    await page.keyboard.press('Escape');await popup.waitFor({state:'hidden'});
    await trigger.focus();await popup.waitFor({state:'visible'});
    await page.evaluate(()=>renderDashboard());assert.equal(await trigger.evaluate(b=>document.activeElement===b),true);
    assert.equal(await popup.innerText(),formulas);
    await page.keyboard.press('Escape');await popup.waitFor({state:'hidden'});
    await page.keyboard.press('Tab');
   }
   for(const width of [2048,1600,1280,1024,768,430,375,320]){
    await page.setViewportSize({width,height:1100});await stable(page);
    const result=await page.locator('#o30Overview').evaluate(e=>{
     const cards=[...e.querySelectorAll('.o30-kpis article')];
     const overflow=cards.filter(c=>c.scrollWidth>c.clientWidth+1).map(c=>c.dataset.overviewMetric);
     const clipped=[];
     for(const c of cards){const b=c.getBoundingClientRect();for(const text of c.querySelectorAll('strong,article>span,small')){const r=document.createRange();r.selectNodeContents(text);for(const rect of r.getClientRects())if(rect.width&&rect.height&&(rect.left<b.left-1||rect.right>b.right+1))clipped.push(text.textContent);}}
     const formula=e.querySelector('.o30-kpi-formula'),range=document.createRange();range.selectNodeContents(formula.parentElement.firstChild);const title=range.getBoundingClientRect();
     return {overflow,clipped,formulaNewLine:formula.getBoundingClientRect().top>=title.bottom-1,tops:cards.map(c=>Math.round(c.getBoundingClientRect().top)),documentOverflow:document.documentElement.scrollWidth>innerWidth+1};
    });
    assert.deepEqual(result.overflow,[],JSON.stringify({lang,width,result}));assert.deepEqual(result.clipped,[],JSON.stringify({lang,width,result}));assert(result.formulaNewLine,'formula must be on next line');assert.equal(result.documentOverflow,false);
    if(width>=1600)assert.equal(new Set(result.tops).size,1,'wide desktop five cards on one row');
    report.layouts.push({lang,width,...result});
    if((width===1600||width===375)&&lang==='zh')await page.locator('#o30Overview').screenshot({path:path.join(out,`homepage-${width}.png`)});
   }
  }
  await page.setViewportSize({width:780,height:360});await stable(page);
  const keyButton=page.locator('.forecast-info-button[aria-describedby="forecast-help-overview"]');
  await keyButton.scrollIntoViewIfNeeded();await keyButton.focus();
  const keyPanel=page.getByRole('tooltip');await keyPanel.waitFor({state:'visible'});
  await page.keyboard.press('End');
  assert(await keyPanel.evaluate(e=>e.scrollTop>0&&e.scrollHeight-e.clientHeight-e.scrollTop<=1),'keyboard must reach the final line in a short viewport');
  await page.keyboard.press('Home');assert.equal(await keyPanel.evaluate(e=>e.scrollTop),0);
  await page.keyboard.press('Escape');await keyPanel.waitFor({state:'hidden'});
  report.keyboard={focus:true,refreshPreservesFocus:true,escape:true,scrollToEnd:true};
  await page.evaluate(()=>{state.language='zh';applyLanguage();});
  await page.setViewportSize({width:1600,height:1100});await selectMonth(page,'10');
  const closed=await page.locator('[data-overview-metric="forecast"] strong').textContent();assert(closed.includes('23,450.00'),closed);
  report.closedMonthActual=closed;
  const closedHelp=await page.locator('#forecast-help-overview').textContent();
  assert(closedHelp.includes('实际收入 62,000.00 元 − 实际总成本 38,550.00 元 = 23,450.00 元'));
  assert(closedHelp.includes('两月成本对照（仅供参考）'));assert(!closedHelp.includes('采用 '));
  await page.locator('#o30Overview').screenshot({path:path.join(out,'homepage-closed-october.png')});
  // Use the normal ingredient editor and its save callback. Mutate only the
  // synthetic remote store for the second update and let the live poll apply it.
  const liveContext=await browser.newContext({viewport:{width:1600,height:1000},timezoneId:'Asia/Shanghai'});
  await liveContext.route(/^https?:\/\//,r=>r.abort());
  const live=await liveContext.newPage();live.on('pageerror',e=>report.errors.push(e.message));
  await live.clock.setFixedTime(new Date('2026-11-10T12:00:00+08:00'));
  await live.goto(pathToFileURL(path.join(source,'web/index.html')).href);await live.evaluate(seedLedger,true);
  await live.locator('#selectedDate').fill('2026-10-20');
  await live.locator('#selectedMonth').selectOption('11');
  const liveProfit=live.locator('[data-overview-metric="forecast"] strong');
  const reportProfit=live.locator('#monthCard .forecast-row').nth(1).locator('strong');
  const startProfit=await liveProfit.textContent();assert(startProfit.includes('34,366.67'),startProfit);
  await live.locator('button[data-page="food"]').click();
  await live.locator('#foodDate').fill('2026-11-10');
  await live.locator('#addFoodRowButton').click();
  const purchase=live.locator('#foodRows tr').last();
  await purchase.locator('[data-detail="name"]').fill('Synthetic greens');
  await purchase.locator('[data-detail="quantity"]').fill('3');
  await purchase.locator('[data-detail="unit"]').selectOption({label:'公斤'});
  await purchase.locator('[data-detail="price"]').fill('30.00');
  await live.locator('#saveFoodButton').click();
  await live.waitForFunction(()=>document.querySelector('#foodResult').textContent.includes('已保存到云端'));
  const afterSave=await liveProfit.textContent();assert(afterSave.includes('34,066.67'),afterSave);
  assert.equal(await reportProfit.textContent(),afterSave);
  const saved=await live.evaluate(()=>previewRecords('preview').find(r=>r.record_key==='2026-11-10').payload.daily[0]);
  assert.equal(saved.食材成本,'890.00');assert(saved.食材明细.includes('Synthetic greens'));
  await live.locator('button[data-page="overview"]').click();
  await live.locator('.forecast-info-button[aria-describedby="forecast-help-overview"]').focus();
  const livePanel=live.getByRole('tooltip');await livePanel.waitFor({state:'visible'});
  assert((await livePanel.innerText()).includes('8,590.00 元 ÷ 9'));
  await live.evaluate(()=>{
    const records=structuredClone(previewRecords('preview')),today=records.find(r=>r.record_key==='2026-11-10');
    today.version+=1;today.payload.daily[0].其他='60.00';today.payload.daily[0].收益='52600.00';
    previewRecordStores.set('preview',records);
  });
  await live.waitForFunction(()=>document.querySelector('[data-overview-metric="forecast"] strong').textContent.includes('33,866.67'),null,{timeout:15000});
  const afterSync=await liveProfit.textContent();assert.equal(await reportProfit.textContent(),afterSync);
  assert((await livePanel.innerText()).includes('60.00 元 ÷ 9'));
  const revenueAfterSync=await live.locator('#monthCard .forecast-row').first().locator('strong').textContent();
  assert(revenueAfterSync.includes('78,000.00'),revenueAfterSync);
  report.liveCosts={startProfit,todayPurchase:{cost:'90.00',savedTotal:saved.食材成本,afterSave},remoteChange:{other:'60.00',todayRevenueIncrease:'50000.00',revenueAfterSync,afterSync},updatedBothLocations:true,selectedReportMonthPreserved:true,activePopupUpdatedByPoll:true};
  await live.locator('button[data-page="stats"]').click();await live.locator('#oaAdvanced>summary').click();
  const advancedButton=live.locator('#statsForecastBanner .forecast-info-button');
  await advancedButton.scrollIntoViewIfNeeded();await advancedButton.focus();await livePanel.waitFor({state:'visible'});
  assert((await livePanel.innerText()).includes('60.00 元 ÷ 9'));
  await live.evaluate(()=>{
    const remote=structuredClone(previewRecords('preview')),r=remote.find(r=>r.record_key==='2026-11-10');
    r.version++;r.payload.daily[0].其他='120.00';previewRecordStores.set('preview',remote);
  });
  await live.waitForFunction(()=>document.querySelector('#forecast-help-popup').textContent.includes('120.00 元 ÷ 9'),null,{timeout:15000});
  assert(await advancedButton.evaluate(b=>b===document.activeElement&&b.getAttribute('aria-expanded')==='true'));
  assert(await livePanel.isVisible());report.liveCosts.advancedAnalyticsPopupAndFocusUpdatedByPoll=true;
  await liveContext.close();
  // Pause a fresh browser clock before page load so the application's actual
  // midnight timeout is installed. Its five-second polling fallback is not due.
  const timedContext=await browser.newContext({timezoneId:'Asia/Shanghai'});
  await timedContext.route(/^https?:\/\//,r=>r.abort());
  const timed=await timedContext.newPage();timed.on('pageerror',e=>report.errors.push(e.message));
  await timed.clock.install({time:new Date('2026-10-31T23:59:55+08:00')});
  await timed.clock.pauseAt(new Date('2026-10-31T23:59:59.500+08:00'));
  await timed.goto(pathToFileURL(path.join(source,'web/index.html')).href);await timed.evaluate(seedLedger);
  await timed.evaluate(()=>{showPage('overview');$('selectedDate').value='2026-10-31';$('selectedMonth').value='10';$('selectedYear').value='2026';renderDashboard();});
  const headline=timed.locator('[data-overview-metric="forecast"] strong');
  await timed.clock.runFor(499);
  const before=await headline.textContent();assert(before.includes('17,250.00'),before);
  await timed.clock.runFor(1);
  const after=await headline.textContent();assert(after.includes('23,450.00'),after);
  assert((await timed.locator('#monthCard .forecast-row').nth(1).textContent()).includes('23,450.00'));
  report.rollover={before,after,timezone:'Asia/Shanghai',atLocalMidnight:true,automaticWithoutDataChange:true,passed:true};
  await timed.clock.setSystemTime(new Date('2026-11-29T12:00:00+08:00'));
  await timed.evaluate(()=>{
    normalizeRecords([
      {record_type:'month',record_key:'2026-10',payload:{monthly_fixed:[{月份:'2026-10',人工总额:'0.00'}]}},
      {record_type:'day',record_key:'2026-11-01',payload:{daily:[{日期:'2026-11-01',收益:'2800.01',食材成本:'270.00',佐料成本:'10.02',其他:'280.06'}]}}
    ]);
    $('selectedDate').value='2026-11-29';$('selectedMonth').value='11';renderDashboard();
  });
  const headlineRounded=await headline.textContent(),reportRounded=await timed.locator('#monthCard .forecast-row').nth(1).locator('strong').textContent();
  assert(headlineRounded.includes('2,399.93'),headlineRounded);assert.equal(headlineRounded,reportRounded);
  report.rounding={date:'2026-11-29',expectedExact:'2399.925',headlineRounded,reportRounded,passed:true};
  await timedContext.close();
  report.touch=[];
  for(const [width,height] of [[390,844],[820,1040]]){
   const touchContext=await browser.newContext({viewport:{width,height},hasTouch:true,timezoneId:'Asia/Shanghai'});
   await touchContext.route(/^https?:\/\//,r=>r.abort());
   const touch=await touchContext.newPage();touch.on('pageerror',e=>report.errors.push(e.message));
   await touch.clock.setFixedTime(new Date('2026-11-10T12:00:00+08:00'));
   await touch.goto(pathToFileURL(path.join(source,'web/index.html')).href);await touch.evaluate(seedLedger);await selectMonth(touch,'11');
   await touch.locator('#o30DashboardDetails').evaluate(e=>e.open=true);
   for(const lang of ['zh','en']){
    await touch.evaluate(lang=>{state.language=lang;applyLanguage();renderDashboard();},lang);
    for(const scope of ['overview','report']){
     const button=touch.locator(`.forecast-info-button[aria-describedby="forecast-help-${scope}"]`),panel=touch.getByRole('tooltip');
     await button.tap();await panel.waitFor({state:'visible'});
     assert((await panel.innerText()).includes(lang==='zh'?'日历天数':'calendar days'));
     assert.equal(await panel.evaluate(e=>e.scrollTop),0,'opening another explanation starts with its formula');
     const box=await panel.boundingBox(),target=await button.boundingBox();
     assert(target.width>=44&&target.height>=44,`small tap target at ${width}`);
     assert(box.x>=0&&box.y>=0&&box.x+box.width<=width+1&&box.y+box.height<=height+1,`clipped ${scope} at ${width}`);
     const endReachable=await panel.evaluate(e=>{e.scrollTop=e.scrollHeight;return e.scrollHeight-e.clientHeight-e.scrollTop<=1;});assert(endReachable);
     if(lang==='zh'&&scope==='overview')await touch.screenshot({path:path.join(out,`forecast-help-${width}.png`)});
     await button.tap();await panel.waitFor({state:'hidden'});
     report.touch.push({width,height,scope,lang,box,target,endReachable});
    }
   }
   await touchContext.close();
  }
  for(const lang of ['zh','en']){
   await page.evaluate(lang=>{state.language=lang;applyLanguage();Oct30Analytics.open({month:'2026-10',view:'overview'});},lang);
   for(const width of [1600,1024,768,430,375,320]){
    await page.setViewportSize({width,height:1200});
    await page.evaluate(()=>Oct30Analytics.open({month:'2026-10',view:'overview'}));
    await chartGeometry(page,`${lang}-${width}-overview`);
    await page.evaluate(()=>Oct30Analytics.open({month:'2026-10',view:'costs'}));
    await page.locator('#oaBasis').selectOption('monthly');await chartGeometry(page,`${lang}-${width}-monthly-costs`);
    if((width===1600||width===375)&&lang==='zh')await page.locator('.oa-chart-grid').screenshot({path:path.join(out,`cost-monthly-${width}.png`)});
    await page.locator('#oaBasis').selectOption('itemized');await chartGeometry(page,`${lang}-${width}-itemized-costs`);
    const target=page.locator('#oaTrend [data-o30-index]').first();await target.focus();await page.keyboard.press('End');
    const tooltip=await page.locator('#oaTrend [data-o30-index]').last().getAttribute('data-tooltip');
    const readout=await page.locator('#oaTrend .o30-readout').textContent();assert(readout.includes(tooltip.split('\n')[0]),JSON.stringify({lang,width,readout,tooltip,active:await page.evaluate(()=>document.activeElement?.outerHTML)}));
    if((width===1600||width===375)&&lang==='zh')await page.locator('.oa-chart-grid').screenshot({path:path.join(out,`cost-itemized-${width}.png`)});
   }
  }
  await page.evaluate(()=>{state.language='zh';applyLanguage();state.editorDirty=false;showPage('cash');});
  assert.equal(await page.locator('#cashOpeningBalanceV4,#saveCashBaselineV4').count(),0);
  await page.locator('#addCashItemV4').click();await page.locator('[data-cash-type]').selectOption({label:'余额强制修改'});await page.locator('[data-cash-amount]').fill('6000');await page.locator('[data-save]').click();
  await page.locator('.cash-item-modal').waitFor({state:'detached'});
  const cash=await page.evaluate(()=>unpackPayload(currentRecord('global','cash_position')));
  assert(cash.transactions.some(r=>r.system_locked===true));assert(cash.transactions.some(r=>r.mode==='force'&&String(r.amount)==='6000.00'&&r.system_locked===false));
  report.cash={correctionRemoved:true,manualForceRetained:true,historicalLockPreserved:true};
  assert.deepEqual(report.errors,[]);report.passed=true;
 }finally{fs.writeFileSync(path.join(out,'browser-verification.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
 console.log(JSON.stringify({passed:report.passed,layouts:report.layouts.length,chartCases:report.charts.length,rollover:report.rollover,errors:report.errors}));
})().catch(e=>{console.error(e);process.exitCode=1;});
