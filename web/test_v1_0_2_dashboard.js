'use strict';
// Exercise shipped Decimal-transformed calculations and their actual KPI renderer.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const Exact=require('./money.js'),acorn=require('../build/js-transform/node_modules/acorn');
const read=name=>fs.readFileSync(path.join(__dirname,name),'utf8'),app=read('app.js'),dashboard=read('dashboard-oct30.js');
function func(source,name){let found;function walk(n){if(!n||typeof n!=='object')return;if(n.type==='FunctionDeclaration'&&n.id.name===name)found=source.slice(n.start,n.end);for(const [k,v] of Object.entries(n))if(!['start','end'].includes(k))Array.isArray(v)?v.forEach(walk):walk(v);}walk(acorn.parse(source,{ecmaVersion:'latest'}));assert.ok(found,name);return found;}
let clock=[2026,10,10,12];
class TestDate extends Date{constructor(...args){super(...(args.length?args:clock));}}
const amount=Exact.decimal,format=x=>Exact.currency(x).toFixed(2);
function metric(date,revenue,variable,gross,food=0,spice=0){
  return {date,revenue:amount(revenue),variable:amount(variable),gross:amount(gross),food:amount(food),spice:amount(spice)};
}
const metrics=[
  metric('2026-09-01',3000,600,2400,100,20),metric('2026-10-01',3100,1000,2100,300,50),
  metric('2026-11-01',900,400,500,370,30),metric('2026-11-09',900,100,800,90,10),
  metric('2026-11-10',9000,2000,7000,1800,200),metric('2026-11-11',99999,99999,0,99999),
];
const state={language:'zh',months:new Map([['2026-09',{}],['2026-10',{}],['2026-11',{}]])};
let activeMetrics=metrics;
const c=vm.createContext({Exact,Date:TestDate,Math,Number,String,Array,Map,state,
  isoDate:d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`,
  dataDayMetrics:()=>activeMetrics,daysInMonth:(y,m)=>new Date(y,m,0).getDate(),
  fixedBreakdown:(y,m)=>{const row=state.months.get(`${y}-${String(m).padStart(2,'0')}`);return {spentTotal:amount(row?row.fixed??1000:0)};},
  syncForecastHelp(){},escapeHtml:s=>s,
  money:format,percent:(x,y)=>Exact.cmp(y,0)===0?'0.0%':Exact.calculate.mul(Exact.div(x,y),100).toFixed(1)+'%',
  en:()=>state.language==='en',t:(zh,en)=>state.language==='en'?en:zh,
});
for(const n of ['elapsedCalendarDays','periodElapsedDays','monthOverviewMetricsV102','forecastCostChoiceV102','monthForecastV102','forecastLabelV102','refreshCalendarBoundaryV102'])vm.runInContext(func(app,n),c);
vm.runInContext(func(dashboard,'monthChangeV102'),c);
let checks=0;
function check(name,fn){fn();checks++;console.log('PASS',name);}
check('calendar-day averages exclude today; current net includes today',()=>{
  const m=c.monthOverviewMetricsV102(2026,11);
  assert.equal(format(m.avgRevenue),'200.00');assert.equal(format(m.avgGross),'144.44');
  assert.equal(format(m.net),'7300.00');assert.equal(m.items.length,3);
  assert.equal(format(m.avgNet),'811.11');assert.equal(m.netMargin.toFixed(1),'67.6');
  assert.equal(format(c.monthOverviewMetricsV102(2026,10).avgRevenue),'100.00');
});
check('projection picks current ingredient rate and prior other rate independently; closed months show actuals',()=>{
  const live=c.monthForecastV102(2026,11);
  assert.equal(format(live.revenue),'6000.00');assert.equal(format(live.cost),'9962.37');assert.equal(format(live.net),'-3962.37');
  assert.equal(format(live.breakEven),'182.88');
  const prior=c.monthForecastV102(2026,10);
  assert.equal(format(live.dailyNet),'-132.08');assert.equal(format(prior.dailyNet),'35.48');
  assert.equal(c.monthChangeV102(live.dailyNet,prior.dailyNet),'比上个月少了 472.2%');
  assert.equal(format(c.monthForecastV102(2026,10).net),'1100.00');
  assert.equal(c.monthForecastV102(2026,10).closed,true);
  assert.equal(c.monthChangeV102(c.monthForecastV102(2026,11).net,c.monthForecastV102(2026,10).net),'比上个月少了 460.2%');
});
check('today’s saved variable spending enters each category immediately; future spending and today’s revenue stay out',()=>{
  activeMetrics=metrics.filter(m=>m.date<'2026-11-10');
  const before=c.monthForecastV102(2026,11);
  assert.equal(format(before.net),'2704.30');assert.equal(format(before.dailyNet),'90.14');
  activeMetrics=[...activeMetrics,metric('2026-11-10',90000,305,89995,2,3),metric('2026-11-11',0,100000,0,50000,50000)];
  const after=c.monthForecastV102(2026,11);
  assert.equal(format(after.revenue),format(before.revenue));
  assert.equal(format(after.current.ingredient),'505.00');assert.equal(format(after.current.other),'300.00');
  assert.equal(after.current.elapsed,9);
  assert.equal(format(after.net),'2316.67');assert.equal(format(after.dailyNet),'77.22');assert.equal(after.choices.other.winner,'current');
  activeMetrics=metrics;
});
check('live comparisons keep exact winners even for daily values displaying the same cents and handle genuine ties',()=>{
  state.months.set('2026-10',{fixed:123});state.months.set('2026-11',{fixed:123});
  activeMetrics=[metric('2026-10-02',100,'31.01',68.99,'31.01'),metric('2026-11-01',200,'9.01',190.99,'9.01')];
  const f=c.monthForecastV102(2026,11);
  assert.equal(f.choices.ingredient.winner,'current');
  assert.equal(f.choices.fixed.winner,'tie');assert.equal(f.choices.other.winner,'tie');
  const zh=c.forecastLabelV102('report',f);
  assert.ok(zh.includes('1.0003 元/天 (31.01 ÷ 31)'));assert.ok(zh.includes('1.0011 元/天 (9.01 ÷ 9)'));
  assert.ok(zh.includes('采用 2026-11 · 1.0011 元/天'));assert.ok(zh.includes('采用 两月持平 · 123.00'));
  const closed=c.forecastLabelV102('report',c.monthForecastV102(2026,10));
  assert.ok(closed.includes('两月成本对照（仅供参考）'));assert.ok(closed.includes('实际总成本 154.01'));assert.ok(!closed.includes('采用 '));
  state.months.delete('2026-11');const noFixed=c.monthForecastV102(2026,11);
  assert.equal(noFixed.choices.fixed.now,null);assert.equal(noFixed.choices.fixed.winner,'previous');
  state.months.set('2026-10',{});state.months.set('2026-11',{});activeMetrics=metrics;
});
check('local first-of-month boundary replaces previous estimate with actual net',()=>{
  clock=[2026,9,31,23,59,59];
  assert.equal(c.monthForecastV102(2026,10).closed,false);
  assert.equal(format(c.monthForecastV102(2026,10).net),'1170.00');
  clock=[2026,10,1,0,0,0];
  assert.equal(c.monthForecastV102(2026,10).closed,true);
  assert.equal(format(c.monthForecastV102(2026,10).net),'1100.00');
  assert.equal(format(c.monthForecastV102(2026,10).revenue),'3100.00');
  assert.equal(format(c.monthOverviewMetricsV102(2026,10).avgNet),'35.48');
  assert.equal(c.monthOverviewMetricsV102(2026,11).avgNet,null);
  const first=c.monthForecastV102(2026,11);assert.equal(first.net,null);assert.equal(first.dailyNet,null);
  assert.equal(first.choices.ingredient.now.days,0);assert.equal(first.choices.ingredient.chosen,null);
  const firstHelp=c.forecastLabelV102('report',first);assert.ok(firstHelp.includes('暂无日均 (400.00 ÷ 0)'));assert.ok(firstHelp.includes('两月成本对照（仅供参考）'));
  clock=[2026,10,10,12];
});
check('an unchanged open ledger rerenders once at the local date boundary',()=>{
  let renders=0;c.renderDashboard=()=>renders++;state.token='test-only';
  clock=[2026,9,31,23,59,59];c.refreshCalendarBoundaryV102();assert.equal(renders,0);
  clock=[2026,10,1,0,0,0];c.refreshCalendarBoundaryV102();assert.equal(renders,1);
  c.refreshCalendarBoundaryV102();assert.equal(renders,1);
  state.token=null;clock=[2026,10,2,0,0,0];c.refreshCalendarBoundaryV102();assert.equal(renders,1);
  clock=[2026,10,10,12];
});
check('closed month does not require preceding month; zero revenue margin is unavailable',()=>{
  state.months.delete('2026-09');
  assert.equal(format(c.monthForecastV102(2026,10).net),'1100.00');
  state.months.set('2026-09',{});
  activeMetrics=[{date:'2026-10-01',revenue:amount('0'),variable:amount('0'),gross:amount('0')}];
  assert.equal(c.monthOverviewMetricsV102(2026,10).netMargin,null);
  assert.equal(format(c.monthOverviewMetricsV102(2026,10).avgNet),'-32.26');
  activeMetrics=metrics;
});
check('negative/zero/missing bases do not invert or fabricate percentages',()=>{
  for(const [now,before,expected] of [['-50','-100','比上个月多了 50.0%'],['-150','-100','比上个月少了 50.0%'],['100','-100','比上个月多了 200.0%'],['0','0','与上个月持平 0.0%']])assert.equal(c.monthChangeV102(amount(now),amount(before)),expected);
  assert.equal(c.monthChangeV102(amount('1'),amount('0')),'上个月为 0，无法计算百分比');
  assert.equal(c.monthChangeV102(null,amount('10')),'暂无上月可比数据');
});
check('fixed-only prior cost is valid; missing prior cost is unavailable',()=>{
  activeMetrics=metrics.filter(m=>!m.date.startsWith('2026-10'));
  assert.equal(format(c.monthForecastV102(2026,11).net),'-3333.33');
  state.months.delete('2026-10');assert.equal(c.monthForecastV102(2026,11).net,null);
  assert.equal(c.monthOverviewMetricsV102(2026,10).net,null);
  assert.equal(c.monthForecastV102(2026,12).net,null);
  for(const month of [10,11,12])assert.equal(c.monthForecastV102(2026,month).dailyNet,null);
  state.months.set('2026-10',{});activeMetrics=metrics;
});
check('larger fixed budget wins in either direction; stored zero and absent monthly fixed do not erase history',()=>{
  state.months.set('2026-10',{fixed:3000});state.months.set('2026-11',{fixed:4200});
  assert.equal(format(c.monthForecastV102(2026,11).cost),'13162.37');
  assert.equal(format(c.monthForecastV102(2026,11).breakEven),'330.57');
  state.months.set('2026-11',{fixed:0});assert.equal(format(c.monthForecastV102(2026,11).cost),'11962.37');
  state.months.delete('2026-11');assert.equal(format(c.monthForecastV102(2026,11).cost),'11962.37');
  state.months.set('2026-10',{fixed:-500});assert.equal(format(c.monthForecastV102(2026,11).cost),'8462.37');
  state.months.set('2026-11',{fixed:0});assert.equal(format(c.monthForecastV102(2026,11).cost),'8962.37');
  state.months.set('2026-10',{fixed:0});
  activeMetrics=[metric('2026-11-01',0,9,0,8,1)];
  assert.equal(format(c.monthForecastV102(2026,11).net),'-30.00');assert.equal(c.monthForecastV102(2026,11).breakEven,null);
  state.months.set('2026-10',{});state.months.set('2026-11',{});activeMetrics=metrics;
});
check('prior ingredient and current other rate can win independently, including leap February',()=>{
  clock=[2024,1,11,12];state.months.set('2024-01',{fixed:0});
  activeMetrics=[metric('2024-01-01',600,310,290,248,62),metric('2024-02-01',1000,50,1000)];
  const f=c.monthForecastV102(2024,2);
  assert.equal(format(f.revenue),'2900.00');assert.equal(format(f.cost),'435.00');assert.equal(format(f.net),'2465.00');assert.equal(format(f.dailyNet),'85.00');
  state.months.delete('2024-01');clock=[2026,10,10,12];activeMetrics=metrics;
});
check('projecting before rounding preserves exact half cents for daily costs and revenue',()=>{
  clock=[2026,10,13,12];state.months.set('2026-10',{fixed:0});state.months.set('2026-11',{fixed:0});
  activeMetrics=[metric('2026-11-01','0.01','0.01',0,'0.01')];
  const f=c.monthForecastV102(2026,11);
  assert.equal(format(f.revenue),'0.03');assert.equal(format(f.cost),'0.03');assert.equal(format(f.net),'0.00');
  state.months.set('2026-10',{});state.months.set('2026-11',{});clock=[2026,10,10,12];activeMetrics=metrics;
});
check('daily forecast divides the unrounded monthly numerator and rounds cash once',()=>{
  state.months.set('2026-10',{fixed:0});
  for(const [day,income,fixed,monthly,daily] of [
    [5,'0.03','0.08','0.15','0.00'],[5,'0.01','0.22','-0.15','0.00'],
    [7,'0.03','0.00','0.15','0.01'],[7,'0.00','0.15','-0.15','-0.01'],
    [5,'0.04','0.30','0.00','0.00']
  ]){
    clock=[2026,10,day,12];state.months.set('2026-11',{fixed});
    activeMetrics=[metric('2026-11-01',income,0,income)];
    const f=c.monthForecastV102(2026,11);
    assert.equal(format(f.net),monthly);assert.equal(format(f.dailyNet),daily);
  }
  clock=[2026,10,10,12];state.months.set('2026-10',{});state.months.set('2026-11',{});activeMetrics=metrics;
});
check('closed February uses all calendar days and the preceding January uses its own 31 days',()=>{
  for(const [year,days] of [[2023,28],[2024,29]]){
    activeMetrics=[metric(`${year}-01-01`,310,0,310),metric(`${year}-02-01`,days*20,0,days*20)];
    for(const month of ['01','02'])state.months.set(`${year}-${month}`,{fixed:0});
    const february=c.monthForecastV102(year,2),january=c.monthForecastV102(year,1);
    assert.equal(format(february.dailyNet),'20.00');
    assert.equal(february.closed,true);assert.equal(format(january.dailyNet),'10.00');
    assert.equal(c.monthChangeV102(february.dailyNet,january.dailyNet),'比上个月多了 100.0%');
    for(const month of ['01','02'])state.months.delete(`${year}-${month}`);
  }
  activeMetrics=metrics;
});
check('daily month change rounds an exact half tenth once even with a repeating previous daily rate',()=>{
  clock=[2026,11,1,12];
  for(const month of ['2026-10','2026-11'])state.months.set(month,{fixed:0});
  activeMetrics=[metric('2026-10-01','2.00',0,'2.00'),metric('2026-11-01','0.03',0,'0.03')];
  const current=c.monthForecastV102(2026,11),previous=c.monthForecastV102(2026,10);
  assert.equal(c.monthChangeV102(current.netNumerator,previous.netNumerator,current.dailyNetDenominator,previous.dailyNetDenominator),'比上个月少了 98.5%');
  for(const month of ['2026-10','2026-11'])state.months.set(month,{});
  clock=[2026,10,10,12];activeMetrics=metrics;
});
check('the three-line forecast footer uses the full calendar month and divides before rounding',()=>{
  state.months.set('2026-10',{fixed:0});state.months.set('2026-11',{fixed:'0.07'});
  clock=[2026,10,5,12];activeMetrics=[metric('2026-11-01','0.21','0.01','0.20','0.01')];
  const f=c.monthForecastV102(2026,11);
  assert.equal(f.cost.toString(),'0.145');
  for(const scope of ['overview','report','stats']){
    const label=c.forecastLabelV102(scope,f);
    assert.ok(label.endsWith('\n\n本月预计日均总成本：0.00/天\n本月预计总成本：0.15\n本月预计收入：1.58</span>'),label);
  }
  // Saturday: Friday closes the sixth calendar day, though only Sunday has a ledger row.
  clock=[2026,10,7,12];state.months.set('2026-11',{fixed:0});
  activeMetrics=[metric('2026-11-01','0.21','0.03','0.18','0.03')];
  const weekend=c.monthForecastV102(2026,11);
  assert.equal(weekend.dailyCost.toString(),'0.005');
  state.language='en';
  assert.ok(c.forecastLabelV102('overview',weekend).endsWith('\n\nProjected average daily total cost: 0.01/day\nProjected monthly total cost: 0.15\nProjected monthly revenue: 1.05</span>'));
  state.language='zh';state.months.set('2026-10',{});state.months.set('2026-11',{});clock=[2026,10,10,12];activeMetrics=metrics;
});
check('the footer keeps independent unknowns and labels closed-month actuals, including a known zero',()=>{
  state.months.delete('2026-10');activeMetrics=[metric('2026-11-01',90,10,80,10)];
  const footer=(year,month)=>c.forecastLabelV102('report',c.monthForecastV102(year,month)).split('\n\n').pop();
  assert.equal(footer(2026,11),'本月预计日均总成本：—\n本月预计总成本：—\n本月预计收入：300.00</span>');
  assert.equal(footer(2026,12),'本月预计日均总成本：—\n本月预计总成本：—\n本月预计收入：—</span>');
  assert.equal(footer(2026,10),'本月实际日均总成本：—\n本月实际总成本：—\n本月实际收入：—</span>');
  state.months.set('2026-10',{fixed:'1.00'});
  assert.equal(footer(2026,10),'本月实际日均总成本：0.03/天\n本月实际总成本：1.00\n本月实际收入：0.00</span>');
  state.months.set('2026-10',{});activeMetrics=metrics;
});
check('28 elapsed days preserve positive and negative half cents after combining recurring rates',()=>{
  clock=[2026,10,29,12];state.months.set('2026-10',{fixed:0});state.months.set('2026-11',{fixed:0});
  for(const [income,ingredient,other,exact,display] of [
    ['2800.01','280.02','280.06','2399.925','2399.93'],
    ['0.02','0.01','0.08','-0.075','-0.08'],
    ['0.16','0.01','0.08','0.075','0.08'],
  ]){
    activeMetrics=[metric('2026-11-01',income,Exact.calculate.add(ingredient,other),Exact.calculate.sub(income,ingredient),ingredient)];
    const f=c.monthForecastV102(2026,11);
    assert.equal(f.net.toString(),exact);assert.equal(format(f.net),display);
  }
  activeMetrics=[metric('2026-11-01','1.00','0.07','0.99','0.01')];
  const f=c.monthForecastV102(2026,11);assert.equal(f.cost.toString(),'0.075');assert.equal(format(f.cost),'0.08');
  activeMetrics=[metric('2026-11-01','0.14','0.29','0.01','0.13')];
  const required=c.monthForecastV102(2026,11).breakEven;assert.equal(required.toString(),'0.075');assert.equal(format(required),'0.08');
  state.months.set('2026-10',{});state.months.set('2026-11',{});clock=[2026,10,10,12];activeMetrics=metrics;
});
check('month day counts survive spring and autumn daylight-saving changes',()=>{
  for(const m of [3,11])assert.equal(c.elapsedCalendarDays(new Date(2026,m-1,1),new Date(2026,m,0),new Date(2026,m,1)),new Date(2026,m,0).getDate());
});
check('today-only and future fixed-only months do not invent daily averages or forecasts',()=>{
  activeMetrics=metrics.filter(m=>m.date==='2026-11-10'||!m.date.startsWith('2026-11'));
  const todayOnly=c.monthOverviewMetricsV102(2026,11);
  assert.equal(todayOnly.avgRevenue,null);assert.equal(todayOnly.avgGross,null);
  assert.equal(format(todayOnly.net),'6000.00');
  assert.equal(c.monthForecastV102(2026,11).revenue,null);assert.equal(c.monthForecastV102(2026,11).net,null);
  state.months.set('2026-12',{});
  assert.equal(c.monthOverviewMetricsV102(2026,12).net,null);
  assert.equal(c.monthOverviewMetricsV102(2026,12).avgRevenue,null);
  state.months.delete('2026-12');activeMetrics=metrics;
});
check('January rolls back across year boundary',()=>{
  activeMetrics=[{date:'2025-12-01',revenue:amount(3100),variable:amount(100),gross:amount(3000)},{date:'2026-01-01',revenue:amount(6200),variable:amount(100),gross:amount(6100)}];
  state.months.set('2025-12',{});state.months.set('2026-01',{});clock=[2026,0,1,0,0,0];
  assert.equal(c.monthForecastV102(2026,1).previous.key,'2025-12');
  assert.equal(format(c.monthForecastV102(2025,12).net),'2000.00');
  assert.equal(c.monthForecastV102(2026,1).net,null);
  clock=[2026,1,1,0,0,0];assert.equal(format(c.monthForecastV102(2026,1).net),'5100.00');
  state.months.delete('2026-01');state.months.delete('2025-12');clock=[2026,10,10,12];activeMetrics=metrics;
});
const fields={};const field=id=>fields[id]||=(id==='o30DashboardDetails'?{querySelector:()=>field('details-summary')}:{innerHTML:'',textContent:''});
Object.assign(c,{setup(){},$:field,selectedContext:()=>({year:2026,month:11,dateText:'2026-11-10',day:{revenue:amount(9000)}}),dayRowForDate:()=>({}),pageSubtitle:()=>field('subtitle'),window:{}});
vm.runInContext(func(dashboard,'summary'),c);
check('five rendered cards preserve requested order, margins, parentheses, and monthly comparisons',()=>{
  c.summary();const html=field('o30Overview').innerHTML;
  assert.deepEqual([...html.matchAll(/data-overview-metric="([^"]+)"/g)].map(m=>m[1]),['avgRevenue','avgGross','forecast','dailyForecast','net']);
  assert.ok(html.includes('日均毛利润 (毛利率)'));
  assert.ok(html.includes('144.44 <span class="o30-kpi-margin">(72.2%)</span>'));
  assert.ok(html.includes('(根据 本月预计成本 和 本月预计收入 计算)'));assert.ok(html.includes('forecast-help-overview'));
  assert.ok(html.includes('预计食材成本 (含佐料)'));assert.ok(html.includes('其他成本 = 总成本 − 食材与佐料成本 − 固定成本'));
  const dailyCard=html.match(/<article data-overview-metric="dailyForecast">(.*?)<\/article>/s)[1];
  assert.ok(dailyCard.includes('>预计 本月每日盈亏</span><small class="o30-kpi-formula">(预计月底盈亏 ➗ 本月天数)</small>'));
  assert.ok(dailyCard.includes('<strong class="negative">-132.08/天</strong><small>比上个月少了 472.2%</small>'));
  assert.ok(html.includes('净利润 (净利率)'));
  assert.ok(html.includes('7300.00 <span class="o30-kpi-margin">(67.6%)</span>'));
  assert.equal([...html.matchAll(/<small>比上个月/g)].length,5);
  assert.ok(html.includes('<strong class="negative">-3962.37</strong>'));
  state.language='en';c.summary();const english=field('o30Overview').innerHTML;
  assert.ok(english.includes('More than last month by 100.0%'));
  assert.ok(english.includes('>Estimated daily profit/loss this month</span><small class="o30-kpi-formula">(Estimated month-end profit/loss ÷ days in the month)</small>'));
  assert.ok(english.includes('<strong class="negative">-132.08/day</strong>'));
  state.language='zh';
  const originalMetrics=activeMetrics;
  activeMetrics=[];c.summary();
  const missing=field('o30Overview').innerHTML.match(/<article data-overview-metric="dailyForecast">(.*?)<\/article>/s)[1];
  assert.ok(missing.includes('<strong class="">—</strong><small>暂无上月可比数据</small>'));
  activeMetrics=originalMetrics;
});
check('full report wording and cash-only-entry removal are shipped',()=>{
  assert.ok(app.includes('(根据 本月预计成本 和 本月预计收入 计算)'));
  assert.ok(app.includes('平本 需要 日均收入 增加'));
  assert.ok(!app.includes('平本需要 日均收入（“收入”指“Revenue”）增加'));
  const html=read('index.html'),cash=read('sep04.js');
  assert.doesNotMatch(html,/cashOpeningBalanceV4|cashOpeningDateV4|saveCashBaselineV4|余额校正/);
  assert.doesNotMatch(cash,/cashOpeningBalanceV4|cashOpeningDateV4|saveCashBaselineV4/);
  assert.ok(cash.includes('<option>余额强制修改</option>'));
});
console.log(JSON.stringify({version:'v1.0.2',checks,passed:true}));
