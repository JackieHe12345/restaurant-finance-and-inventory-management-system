'use strict';
// Shipped-browser acceptance for analytics presentation, exact derived values,
// localization boundaries and detail-table interactions. Synthetic data only.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const source=path.resolve(process.env.RELEASE_SOURCE_ROOT||path.join(__dirname,'..'));
if(!process.env.QA_OUTPUT_DIR)throw new Error('Set QA_OUTPUT_DIR');
const out=path.resolve(process.env.QA_OUTPUT_DIR);fs.mkdirSync(out,{recursive:true});
const report={revision:null,syntheticData:true,networkBlocked:true,layouts:[],checks:[],errors:[]};
const stable=async page=>{await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME_EXECUTABLE?{executablePath:process.env.CHROME_EXECUTABLE}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1600,height:1100},timezoneId:'Asia/Shanghai',locale:'en-US'});
  await context.route(/^https?:\/\//,route=>route.abort());
  const page=await context.newPage();page.on('pageerror',error=>report.errors.push(error.message));
  await page.clock.setFixedTime(new Date('2026-11-10T12:00:00+08:00'));
  await page.goto(pathToFileURL(path.join(source,'web/index.html')).href);
  report.revision=await page.locator('html').getAttribute('data-build-revision');
  assert(report.revision,'The loaded application must expose its build revision');
  await page.evaluate(async()=>{
   const rows=[];
   for(const [month,count]of [['09',30],['10',31]]){
    for(let i=1;i<=count;i++){
     const date=`2026-${month}-${String(i).padStart(2,'0')}`;
     rows.push({record_type:'day',record_key:date,version:1,payload:{daily:[{'日期':date,'收益':String(2000+i),'食材成本':'700.10','佐料成本':'50.20','总客人数':i%5===0?'0':'45','新客人数':'8'}],fixed_expenses:month==='10'&&i<=3?[{'日期':date,'类别':i===2?'房租':'人工','明细':i===1?'删除':i===2?'自定义菜品':'Custom note','金额':i===1?'100.10':i===2?'99.90':'25.00'}]:[]}});
    }
    rows.push({record_type:'month',record_key:`2026-${month}`,version:1,payload:{monthly_fixed:[{'月份':`2026-${month}`,'人工总额':'6000','房租总额':'8000','水费支出':'400','电费支出':'600','煤气费':'300'}]}});
   }
   const originalApi=api;api=async function(url,options){if(url==='/devices/register')return{id:'synthetic-analytics-device',device_id:'synthetic-analytics-device'};if(url.endsWith('/cash-position'))return{opening_balance:'0.00',summary_month:'2026-10'};return originalApi(url,options);};
   previewRecordStores.set('preview',rows);setSession('preview',previewUser);await enterApp();clearInterval(state.autoRefresh);state.autoRefresh=null;
   $('selectedDate').value='2026-10-09';$('selectedMonth').value='10';$('selectedYear').value='2026';state.language='en';applyLanguage();renderDashboard();
  });
  await stable(page);
  const colors=await page.locator('.o30-kpis article').evaluateAll(cards=>cards.map(card=>{const s=getComputedStyle(card);return{background:s.backgroundColor,border:s.borderTopColor};}));
  assert.equal(colors.length,5);assert.equal(new Set(colors.map(v=>JSON.stringify(v))).size,1);report.checks.push('All five homepage cards use the same background and border');
  await page.locator('#o30Overview').screenshot({path:path.join(out,'five-neutral-cards.png')});
  await page.evaluate(()=>Oct30Analytics.open({month:'2026-10',view:'overview'}));await stable(page);
  assert.equal(await page.locator('.oa-insight').count(),3);
  assert((await page.locator('#oaViewBasis').innerText()).includes('Recorded dates'));
  assert((await page.locator('#oaTrendStats').innerText()).includes('31 available days'));
  await page.locator('#oaChartKind').selectOption('bar');assert.equal(await page.evaluate(()=>$('oaTrend')._o30Options.kind),'bar');
  await page.locator('#oaChartKind').selectOption('line');assert.equal(await page.evaluate(()=>$('oaTrend')._o30Options.kind),'line');report.checks.push('Chart style controls preserve observations and selected metric');
  await page.evaluate(()=>Oct30Analytics.open({month:'2026-10',view:'costs'}));await page.locator('#oaBasis').selectOption('itemized');
  assert.equal(await page.locator('#oaRows tr').count(),3);
  assert((await page.locator('#oaTotals').innerText()).includes('225.00'));
  await page.locator('[data-oa-sort="3"]').click();
  const ascending=await page.locator('#oaRows tr td:nth-child(4)').allTextContents();assert.deepEqual(ascending,['25.00','99.90','100.10']);
  await page.locator('[data-oa-sort="3"]').click();
  assert.deepEqual(await page.locator('#oaRows tr td:nth-child(4)').allTextContents(),['100.10','99.90','25.00']);
  await page.locator('#oaSearch').fill('删除');assert.equal(await page.locator('#oaRows tr').count(),1);
  assert.equal(await page.locator('#oaRows [data-user-content]').innerText(),'删除');
  assert((await page.locator('#oaTotals').innerText()).includes('100.10'));
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#oaExport').click()]);const csvPath=path.join(out,'filtered-detail.csv');await download.saveAs(csvPath);
  const csv=fs.readFileSync(csvPath,'utf8');assert(csv.includes('删除'));assert(csv.includes('100.10'));assert(!csv.includes('99.90'));assert(csv.includes('Amount (CNY)'));
  report.checks.push('Exact amount sorting, filtered totals, user-authored Chinese text and filtered CSV export');
  await page.locator('#oaSearch').fill('');
  for(const lang of ['en','zh'])for(const width of [1600,1024,768,430,375,320]){
   await page.setViewportSize({width,height:1100});
   await page.evaluate(lang=>{state.language=lang;applyLanguage();Oct30Analytics.open({month:'2026-10',view:'overview'});},lang);
   for(const view of ['overview','costs','customers']){
    await page.evaluate(view=>Oct30Analytics.open({month:'2026-10',view}),view);await stable(page);
    const geometry=await page.evaluate(()=>{
     const boxes=[...document.querySelectorAll('#pageStats .oa-kpi,#pageStats .oa-insight,#pageStats .oa-chart-controls')].filter(el=>el.getClientRects().length);
     return {pageOverflow:document.documentElement.scrollWidth>innerWidth+1,overflow:boxes.filter(el=>el.scrollWidth>el.clientWidth+1).map(el=>el.className),englishSystemChinese:state.language==='en'?[...document.querySelectorAll('#pageStats .oa-heading,#pageStats .oa-filter,#pageStats .oa-tabs,#pageStats .oa-kpis,#pageStats .oa-insights,#pageStats .oa-chart-grid,#pageStats .oa-cost-controls,#pageStats .oa-detail-panel')].flatMap(root=>{const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];let n;while(n=walker.nextNode()){const parent=n.parentElement;if(!parent?.closest('[data-user-content]')&&parent?.getClientRects().length&&getComputedStyle(parent).visibility!=='hidden'&&/[\u3400-\u9fff]/.test(n.textContent)){const r=document.createRange();r.selectNodeContents(n);if(r.getBoundingClientRect().height)nodes.push(n.textContent.trim());}}return nodes;}):[]};
    });
    assert.equal(geometry.pageOverflow,false,JSON.stringify({lang,width,view,geometry}));assert.deepEqual(geometry.overflow,[],JSON.stringify({lang,width,view,geometry}));assert.deepEqual(geometry.englishSystemChinese,[],JSON.stringify({lang,width,view,geometry}));
    report.layouts.push({lang,width,view,...geometry});
    if((width===1600||width===375)&&lang==='en'&&view==='overview')await page.screenshot({path:path.join(out,`analytics-${lang}-${width}.png`)});
   }
  }
  assert.deepEqual(report.errors,[]);report.passed=true;
 }finally{fs.writeFileSync(path.join(out,'enhanced-analytics-browser.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
 console.log(JSON.stringify({passed:report.passed,layouts:report.layouts.length,checks:report.checks,errors:report.errors}));
})().catch(error=>{console.error(error);process.exitCode=1;});
