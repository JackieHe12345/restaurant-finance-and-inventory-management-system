'use strict';
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const source = path.resolve(process.env.RELEASE_SOURCE_ROOT || path.join(__dirname, '..'));
if (!process.env.QA_OUTPUT_DIR) throw new Error('Set QA_OUTPUT_DIR for evidence and screenshots');
const output = path.resolve(process.env.QA_OUTPUT_DIR);
fs.mkdirSync(output, {recursive:true});

function day(date, costs) {
  return {record_type:'day',record_key:date,version:1,payload:{daily:[{日期:date,收益:'5840.50',...costs}]}};
}
function month(key, allocations) {
  return {record_type:'month',record_key:key,version:1,payload:{monthly_fixed:[{月份:key,...allocations}]}};
}
const records = [
  month('2026-10',{人工总额:'7750',房租总额:'4960'}),
  day('2026-10-23',{食材成本:'684.30',佐料成本:'58.50',其他:'42.70',手续费:'26.50'}),
  month('2026-11',{人工总额:'6000',房租总额:'3600',预计水费:'900',预计电费:'750',预计煤气费:'540',其它固定成本:'690'}),
  day('2026-11-07',{其他:'41.26'}),
  day('2026-11-08',{食材成本:'612.37',佐料成本:'102.15',水电:'64.20',其他:'41.26',手续费:'28.36'}),
  day('2026-11-11',{食材成本:'999999999999.99'}),
  day('2026-09-11',{食材成本:'0'}),
];
const scenarios = [
  ['2026-10-23','1,222.00',6],
  ['2026-11-08','1,264.34',11],
  ['2026-11-07','457.26',7],
  ['2026-11-11','1,000,000,000,415.99',7],
  ['2026-09-11','',0],
  ['2026-09-15','',0],
];
const colors = ['#2563EB','#EA580C','#0891B2','#C02681','#9333EA','#15803D','#CA8A04','#0F766E','#4338CA','#DC2626','#77850C'];
const names = {
  zh:['食材成本','佐料成本','日结水电','其它','手续费／抽成','人工分摊','房租分摊','水费分摊','电费分摊','煤气分摊','其它固定'],
  en:['Ingredient Cost','Seasoning Cost','Daily Utilities','Other','Fees / commissions','Labour Allocation','Rent Allocation','Water Allocation','Electricity Allocation','Gas Allocation','Other Fixed Cost'],
};
const rgb = hex => 'rgb(' + hex.match(/[a-f\d]{2}/ig).map(pair => parseInt(pair,16)).join(', ') + ')';

async function ready(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
}
async function inspect(page, lang, expected, count) {
  const geometry = await page.locator('#costDonut').evaluate(ring => {
    const hole = ring.firstElementChild;
    const rect = hole.getBoundingClientRect();
    const face = ring.getBoundingClientRect();
    const card = ring.closest('article').getBoundingClientRect();
    const cx = face.x + face.width/2, cy = face.y + face.height/2;
    const range = document.createRange();
    const text = [...(hole.children.length ? hole.children : [hole])].map(node => {
      range.selectNodeContents(node);
      const box = range.getBoundingClientRect();
      const dx = Math.max(Math.abs(box.x-cx),Math.abs(box.right-cx));
      const dy = Math.max(Math.abs(box.y-cy),Math.abs(box.bottom-cy));
      return {text:node.textContent, centerOffset:Math.abs(box.x+box.width/2-cx),
        circleInset:rect.width/2-Math.hypot(dx,dy), top:box.y-cy, bottom:box.bottom-cy,
        size:parseFloat(getComputedStyle(node).fontSize)};
    });
    const gradient = getComputedStyle(ring).backgroundImage;
    const rows = [...document.querySelectorAll('#costLegend .legend-row')].map(r => ({
      name:r.querySelector('span').textContent, color:getComputedStyle(r.querySelector('i')).backgroundColor,
      amount:r.querySelector('strong').firstChild.textContent, percent:r.querySelector('small').textContent,
    }));
    return {face:face.width, hole:rect.width, centerOffset:Math.max(Math.abs(cx-rect.x-rect.width/2),Math.abs(cy-rect.y-rect.height/2)),
      squareError:Math.abs(face.width-face.height), text, rows, gradient, background:getComputedStyle(ring).backgroundColor,
      aria:ring.getAttribute('aria-label'), layoutOverflowsCard:Math.max(0,face.right-card.right,card.x-face.x),
      groupOffset:Math.abs((Math.min(...text.map(t=>t.top))+Math.max(...text.map(t=>t.bottom)))/2),
      pageOverflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};
  });
  assert(geometry.centerOffset <= 1 && geometry.squareError <= 1 && geometry.layoutOverflowsCard <= 1,JSON.stringify(geometry));
  assert(geometry.pageOverflow <= 1,JSON.stringify(geometry));
  assert(geometry.groupOffset <= 2.5,JSON.stringify(geometry));
  for (const line of geometry.text) assert(line.circleInset >= 2 && line.centerOffset <= 1,JSON.stringify(geometry));
  const {rows} = geometry;
  assert.equal(rows.length,count,JSON.stringify(geometry));
  if (expected) {
    const label = lang === 'en' ? 'Total Cost' : '总成本';
    const unit = lang === 'en' ? 'CNY' : '元';
    assert.deepEqual(geometry.text.map(v=>v.text),[label,expected,unit]);
    assert(geometry.aria.includes(lang==='en'?'CNY '+expected:expected+' 元'),geometry.aria);
    const found = geometry.gradient.match(/rgb\([^)]+\)/g);
    assert.deepEqual(found.filter((color,i)=>color!==found[i-1]),rows.map(r=>r.color));
    assert.equal(new Set(found).size,rows.length);
    for (const row of rows) {
      assert.equal(row.color,rgb(colors[names[lang].indexOf(row.name)]),row.name);
      assert.match(row.percent,/^\d+(\.\d+)?%$/);
    }
  } else {
    const message = lang==='zh'?'暂无数据':'No data';
    assert.deepEqual(geometry.text.map(v=>v.text),[message]);
    assert.equal(geometry.aria,message);
    assert.equal(geometry.gradient,'none');
    assert.equal(geometry.background,'rgb(232, 238, 244)');
  }
  return geometry;
}
async function run() {
  const browser = await chromium.launch({executablePath:process.env.CHROME_EXECUTABLE,headless:true});
  const checks = [], errors = [];
  try {
    const context = await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1.5,timezoneId:'Asia/Shanghai'});
    await context.route(/^https?:\/\//,route=>route.abort());
    const page = await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    await page.clock.setFixedTime(new Date('2026-11-12T12:00:00+08:00'));
    await page.addInitScript(rows => {
      document.addEventListener('DOMContentLoaded',()=>{
        const original=api;
        api=async (url,options)=>{
          if (url==='/devices/register') return {id:'ring-example',device_id:'ring-example'};
          if (url.endsWith('/cash-position')) return {opening_balance:'0',summary_month:'2026-11'};
          return original(url,options);
        };
        previewRecordStores.set('test-demo-v1',rows);
      },{once:true});
    },records);
    await page.goto(pathToFileURL(path.join(source,'web/index.html')).href);
    await page.locator('#testLoginButton').click();
    const card=page.locator('#pageOverview .o30-cost-card');
    await card.waitFor();
    const revision=await page.locator('html').getAttribute('data-build-revision');
    for (const lang of ['zh','en']) {
      if (lang==='en') await page.locator('#languageButton').click();
      for (const width of [320,375,390,1280]) {
        await page.setViewportSize({width,height:844});
        for (const [date,expected,count] of scenarios) {
          await page.locator('#selectedDate').fill(date);
          await ready(page);
          const base=await inspect(page,lang,expected,count);
          checks.push({lang,width,date,expanded:false,...base});
          if (width===390&&date==='2026-10-23') {
            await page.mouse.move(0,0);
            await card.screenshot({path:path.join(output,'cost-ring-'+lang+'.png')});
          }
          if (date==='2026-11-11'||date==='2026-09-11') {
            await card.locator('[data-expand-chart]').focus();
            await page.keyboard.press('Enter');
            await card.locator('.chart-direct-scroll-shell').waitFor();
            await ready(page);
            const zoom=await inspect(page,lang,expected,count);
            assert(zoom.face > base.face,'Expand must magnify the donut');
            checks.push({lang,width,date,expanded:true,...zoom});
            await page.keyboard.press('Escape');
            await card.locator('.chart-direct-scroll-shell').waitFor({state:'detached'});
          }
        }
      }
    }
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'ring-acceptance.json'),JSON.stringify({revision,fixture:'synthetic',errors,checks},null,2)+'\n');
    console.log(JSON.stringify({revision,checks:checks.length,errors}));
  } finally { await browser.close(); }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
