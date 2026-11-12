'use strict';
// Run against the shipped UI. The local preview API receives only these synthetic ledger rows.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const source = path.resolve(process.env.RELEASE_SOURCE_ROOT || path.join(__dirname, '..'));
if (!process.env.QA_OUTPUT_DIR) throw new Error('Set QA_OUTPUT_DIR for the report and screenshots');
const output = path.resolve(process.env.QA_OUTPUT_DIR);
fs.mkdirSync(output, { recursive: true });

function amount(cents) {
  return (cents / 100).toFixed(2);
}
function syntheticLedger() {
  const rows = [];
  for (const [month, count] of [['09', 1], ['10', 31], ['11', 11]]) {
    const monthly = '2026-' + month;
    for (let i = 1; i <= count; i++) {
      const date = monthly + '-' + String(i).padStart(2, '0');
      const weekday = new Date(date + 'T12:00:00Z').getUTCDay();
      const revenue = [432000, 215000, 237000, 246000, 258000, 350000, 474000][weekday] + ((i * 23) % 7) * 6100 + i * 63;
      const food = 51000 + (i % 6) * 7500, seasoning = 2400 + i * 26;
      const daily = {日期:date, 收益:amount(revenue), 食材成本:amount(food), 佐料成本:amount(seasoning),
        水电:amount(1700 + i * 15), 手续费:amount(2700 + i * 8), 其他:amount(3900 + i * 20), 总客人数:String(60 + i % 33)};
      rows.push({ record_type:'day', record_key:date, version:1, payload:{daily:[daily]} });
    }
    rows.push({record_type:'month', record_key:monthly, version:1, payload:{
      monthly_fixed:[{月份:monthly, 人工总额:month === '11' ? '6000' : '6200', 房租总额:month === '11' ? '3000' : '3100'}]}});
  }
  return rows;
}
function installSyntheticLedger(rows) {
  document.addEventListener('DOMContentLoaded',()=>{
    const original = api;
    api = async function(url, options) {
      if (url === '/devices/register') return {id:'preview-device',device_id:'preview-device'};
      if (url.endsWith('/cash-position')) return {opening_balance:'0',summary_month:'2026-11'};
      return original(url, options);
    };
    previewRecordStores.set('preview',rows);
  },{once:true});
}
async function enterSyntheticLedger() {
  setSession('preview', previewUser);
  await enterApp();
  clearInterval(state.autoRefresh);
  state.autoRefresh = null;
}
async function settled(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
}
async function chooseDate(page, date) {
  await page.locator('#selectedDate').fill(date);
  await page.waitForFunction(month => document.getElementById('selectedMonth').value === month, String(Number(date.slice(5,7))));
  await settled(page);
}
function expectedValues(row) {
  const cents = key => Math.round(Number(row[key]) * 100);
  const food = cents('食材成本') + cents('佐料成本'), revenue = cents('收益');
  const gross = revenue - food - cents('手续费');
  return {revenue, food, gross, net:gross - cents('水电') - cents('其他') - 30000};
}
const locales = {
  zh:{daily:['每日营业收入','每日毛利润','每日净利润','食材与佐料成本'], weekday:['平均营业收入','平均毛利润','平均净利润','平均食材成本（含佐料）']},
  en:{daily:['Daily revenue','Daily gross profit','Daily net profit','Ingredient and seasoning costs'], weekday:['Average revenue','Average gross profit','Average net profit','Average ingredient and seasoning cost']}
};
async function verifyPoint(page, host, index, name, value, lang) {
  const point = page.locator(host + ' [data-o30-index="' + index + '"]');
  const label = await point.getAttribute('data-tooltip');
  const expected = value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  assert(label.includes(name), label);
  assert(label.includes(lang === 'en' ? 'CNY ' + expected : expected + ' 元'), label + ' expected ' + expected);
  assert.equal(await page.locator(host + ' .o30-legend').innerText(), name);
  await point.focus();
  assert((await page.locator(host + ' .o30-readout').innerText()).includes(expected));
}
async function snapshotCharts(page, lang) {
  await page.mouse.move(0,0);
  for (const [selector, file] of [['.o30-main-trend','daily-revenue'],['.o30-weekday-card','weekday-revenue']]) {
    const card=page.locator('#pageOverview ' + selector);
    await card.locator('[data-o30-index="' + (file === 'daily-revenue' ? 23 : 5) + '"]').click();
    await card.screenshot({path:path.join(output,file + '-' + lang + '.png')});
  }
}
async function snapshotKpis(page, lang) {
  const originalViewport = page.viewportSize();
  await page.setViewportSize({width:1800,height:originalViewport.height});
  await chooseDate(page, '2026-11-11');
  await page.mouse.move(0, 0);
  const grid = page.locator('#o30Overview .o30-kpis');
  const cards = grid.locator('article');
  const english = lang === 'en';
  const currency = value => english ? 'CNY ' + value : value + ' 元';
  const expected = [
    currency('3,300.77'), currency('2,550.40') + ' (77.3%)', currency('62,475.33'),
    currency('2,082.51') + (english ? '/day' : '/天'), currency('17,453.04') + ' (49.1%)'
  ];
  assert.deepEqual(await cards.locator('strong').allTextContents(), expected);
  assert.deepEqual(await cards.evaluateAll(nodes => nodes.map(node => node.dataset.overviewMetric)),
    ['avgRevenue', 'avgGross', 'forecast', 'dailyForecast', 'net']);
  const daily = cards.nth(3);
  const label = english ? 'Estimated daily profit/loss this month\n(Estimated month-end profit/loss ÷ days in the month)' :
    '预计 本月每日盈亏\n(预计月底盈亏 ➗ 本月天数)';
  assert.equal(await daily.locator(':scope > span').innerText(), label);
  // November's 62,475.33 / 30 compared with October's 70,999.24 / 31.
  assert.equal(await daily.locator(':scope > small').innerText(),
    english ? 'Less than last month by 9.1%' : '比上个月少了 9.1%');
  const tops = await cards.evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().top));
  assert.equal(new Set(tops).size, 1, 'All five cards must fit in a single row');
  await grid.screenshot({path:path.join(output, 'dashboard-kpis-' + lang + '.png')});
  await page.setViewportSize(originalViewport);
}
async function snapshotForecast(page, lang) {
  const originalViewport=page.viewportSize();
  await page.setViewportSize({width:originalViewport.width,height:1350});
  await chooseDate(page, '2026-11-11');
  const trigger = page.locator('[aria-describedby="forecast-help-overview"]');
  await trigger.scrollIntoViewIfNeeded();
  await trigger.click();
  const panel = page.locator('#forecast-help-popup');
  await panel.waitFor({state:'visible'});
  const text=await panel.innerText();
  const selected=lang==='en'?'Selected':'采用';
  assert.equal(text.split('\n').filter(line=>line.startsWith(selected+' ')).length,3);
  const totals=lang==='en'?
    ['Projected average daily total cost: CNY 1,218.25/day','Projected monthly total cost: CNY 36,547.62','Projected monthly revenue: CNY 99,022.95']:
    ['本月预计日均总成本：1,218.25 元/天','本月预计总成本：36,547.62 元','本月预计收入：99,022.95 元'];
  assert(text.endsWith('\n\n'+totals.join('\n')),text);
  await panel.evaluate(e => e.scrollTop = e.scrollHeight);
  const heading=lang === 'en' ? 'Cost inputs for this forecast' : '本次估算的成本取值';
  const clip=await panel.evaluate((e,heading)=>{
    const node=e.firstChild, start=node.textContent.indexOf(heading);
    if(start<0)throw new Error('Forecast cost heading missing');
    const range=document.createRange();range.setStart(node,start);range.setEnd(node,node.length);
    const box=e.getBoundingClientRect(), content=range.getBoundingClientRect();
    if(content.y<box.y||content.bottom>box.bottom)throw new Error('Selected cost inputs or forecast totals are clipped');
    const y=Math.floor(content.y-5);
    return {x:Math.ceil(box.x+2), y, width:Math.floor(box.width-4), height:Math.ceil(content.bottom-y+6)};
  },heading);
  await page.screenshot({clip,path:path.join(output,'forecast-inputs-' + lang + '.png')});
  await page.keyboard.press('Escape');
  await page.setViewportSize(originalViewport);
}
async function run() {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE});
  const checks = [], errors = [];
  try {
    const context = await browser.newContext({viewport:{width:1280,height:950},deviceScaleFactor:1.5,timezoneId:'Asia/Shanghai',locale:'zh-CN'});
    await context.route(/^https?:\/\//, route => route.abort());
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.stack || e.message));
    await page.clock.setFixedTime(new Date('2026-11-11T12:00:00+08:00'));
    const rows = syntheticLedger();
    await page.addInitScript(installSyntheticLedger, rows);
    await page.goto(pathToFileURL(path.join(source,'web/index.html')).href);
    await page.evaluate(enterSyntheticLedger);
    const revision = await page.locator('html').getAttribute('data-build-revision');
    for (const id of ['trendMetric','weekdayMetric']) assert.equal(await page.locator('#' + id).inputValue(), 'revenue');
    const oct = rows.filter(r => r.record_type === 'day' && r.record_key.startsWith('2026-10')).map(r => r.payload.daily[0]);
    const mondays = oct.filter(row => new Date(row.日期 + 'T12:00:00Z').getUTCDay() === 1);
    for (const lang of ['zh','en']) {
      if (lang === 'en') await page.locator('#languageButton').click();
      await chooseDate(page, '2026-10-28');
      await snapshotCharts(page, lang);
      for (const [i,key] of ['revenue','gross','net','food'].entries()) {
        const { daily,weekday } = locales[lang];
        const weekdayName = weekday[i], title = lang === 'en' ? weekdayName + ' by weekday' : '各星期' + weekdayName;
        await page.locator('#trendMetric').selectOption(key);
        await page.locator('#weekdayMetric').selectOption(key);
        await settled(page);
        assert.equal(await page.locator('#trendTitle').innerText(), daily[i]);
        assert.equal(await page.locator('#weekdayTitle').innerText(), title);
        assert.equal(await page.locator('#weekdayChart svg').getAttribute('aria-label'), title);
        await verifyPoint(page, '#trendChart', 4, daily[i], expectedValues(oct[4])[key]/100, lang);
        const mean = mondays.reduce((sum,row) => sum + expectedValues(row)[key],0)/mondays.length/100;
        await verifyPoint(page, '#weekdayChart', 0, weekdayName, mean, lang);
        checks.push(lang + ' ' + key + ' exact daily and weekday amounts, titles, legends, accessible readouts');
      }
      await page.locator('.o30-weekday-card [data-expand-chart]').click();
      await page.locator('.o30-weekday-card.chart-expanded').waitFor();
      await page.locator('#weekdayMetric').selectOption('net');
      await verifyPoint(page, '#weekdayChart', 0, locales[lang].weekday[2], mondays.reduce((s,r)=>s + expectedValues(r).net,0)/mondays.length/100, lang);
      await page.keyboard.press('Escape');
      await page.locator('.o30-weekday-card.chart-expanded').waitFor({state:'detached'});
      await page.evaluate(()=>loadCloudData());
      assert.equal(await page.locator('#weekdayMetric').inputValue(), 'net');
      assert.equal(await page.locator('#trendMetric').inputValue(), 'food');
      await chooseDate(page, '2026-09-01');
      assert.equal(await page.locator('#weekdayMetric').inputValue(), 'net');
      assert.equal(await page.locator('#trendMetric').inputValue(), 'food');
      assert((await page.locator('#weekdayChart [data-o30-index="0"]').getAttribute('data-tooltip')).includes(lang === 'en' ? 'No record' : '未记录'));
      await page.locator('#trendMetric').selectOption('revenue');
      await page.locator('#weekdayMetric').selectOption('revenue');
      await snapshotKpis(page, lang);
      checks.push(lang + ' five dashboard amounts, daily forecast title, daily unit and 30-day versus 31-day comparison');
      await snapshotForecast(page, lang);
      checks.push(lang + ' interactive zoom, independent selections, date change, missing weekday, and forecast help');
    }
    await page.setViewportSize({width:375,height:800});
    await page.locator('#weekdayMetric').selectOption('food');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.locator('.o30-weekday-card [data-expand-chart]').click();
    await page.locator('.o30-weekday-card.chart-expanded').waitFor();
    await page.keyboard.press('Escape');
    await page.reload();
    await page.locator('#appView:visible #weekdayChart svg').waitFor({timeout:5000});
    assert(await page.evaluate(()=>Boolean(state.token)),'Session must be restored before checking its charts');
    assert.equal(await page.locator('#weekdayMetric').inputValue(), 'revenue');
    assert.equal(await page.locator('#trendMetric').inputValue(), 'revenue');
    checks.push('375px mobile, fresh document revenue defaults');
    assert.deepEqual(errors,[]);
    const report={revision,fixture:'synthetic only',externalNetwork:'blocked',checks,errors};
    fs.writeFileSync(path.join(output,'chart-acceptance.json'),JSON.stringify(report,null,2) + '\n');
    console.log(JSON.stringify(report));
  } finally {
    await browser.close();
  }
}
run().catch(err=>{console.error(err);process.exitCode=1;});
