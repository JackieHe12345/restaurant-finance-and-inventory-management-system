'use strict';
// Exact derived analytics calculations and user-content localization boundaries.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const Exact=require('./money.js'),state={language:'en'},nodes=new Map(),node=id=>nodes.get(id)||nodes.set(id,{innerHTML:''}).get(id);
const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const window={Exact};
const context=vm.createContext({Exact,state,window,escapeHtml,$:id=>id==='pageStats'?null:node(id),daysInMonth:(year,month)=>new Date(year,month,0).getDate()});
const source=fs.readFileSync(path.join(__dirname,'analytics-oct30.js'),'utf8');
assert(source.includes('root.Oct30Analytics='));
vm.runInContext(source.replace('root.Oct30Analytics=','root.__qa={compareCells,kpi,renderTrendStats,renderInsights,ctx};root.Oct30Analytics='),context);
const qa=window.__qa,decimal=Exact.decimal;
let checks=0;const check=(title,fn)=>{fn();checks++;console.log('PASS',title);};
check('sorts monetary values beyond binary float precision',()=>{
 const a=decimal('9007199254740993.12'),b=decimal('9007199254740993.13');
 assert.equal(qa.compareCells(a,b,1),-1);assert.equal(qa.compareCells(a,b,-1),1);
 assert.equal(qa.compareCells(decimal('-0.01'),decimal('0.00'),1),-1);
});
check('sorts percentage magnitudes numerically and keeps missing values last',()=>{
 assert.equal(qa.compareCells('20.5%','3.0%',1),1);assert.equal(qa.compareCells('-2.0%','3.0%',1),-1);
 for(const direction of [1,-1]){assert.equal(qa.compareCells(null,decimal(0),direction),1);assert.equal(qa.compareCells(decimal(0),'—',direction),-1);assert.equal(qa.compareCells(null,'—',direction),0);}
});
check('trend statistics preserve exact decimals, missing values and observed zero',()=>{
 qa.renderTrendStats([decimal('0.1'),null,decimal('0.2'),decimal('0.0')],value=>value.toFixed(2),'available days');
 const html=node('oaTrendStats').innerHTML;assert(html.includes('<strong>0.10</strong>'));assert(html.includes('<strong>0.00</strong>'));assert(html.includes('<strong>0.20</strong>'));assert(html.includes('3 available days'));
 qa.renderTrendStats([null],value=>value.toFixed(2),'available days');assert.equal((node('oaTrendStats').innerHTML.match(/<strong>—<\/strong>/g)||[]).length,3);
});
check('English KPI currency and zero/missing comparisons are explicit',()=>{
 const html=qa.kpi('Revenue',decimal('10.10'),decimal('0'),'money');assert(html.includes('<em>CNY</em>'));assert(html.includes('+10.10'));assert(!/[\u3400-\u9fff]/.test(html));
 assert(qa.kpi('Revenue',null,null).includes('No comparison data'));
 state.language='zh';assert(qa.kpi('收入',decimal(10),decimal(0)).includes('<em>元</em>'));state.language='en';
});
check('expense reconciliation observes separate bases without double counting',()=>{
 qa.ctx.month='2026-10';qa.ctx.view='costs';qa.ctx.basis='monthly';
 const costs=Object.fromEntries(['food','spice','labour','rent','water','electric','gas','fees','dailyUtilities','other','fixedOther'].map(key=>[key,decimal(0)]));costs.labour=decimal('100.10');costs.food=decimal('20.10');
 qa.renderInsights({metrics:[{net:decimal(1)}],costs,itemized:costs,fixedKnown:true,expenses:[{}],fixedTotal:decimal('100.10'),itemizedTotal:decimal('99.90')});
 const html=node('oaInsights').innerHTML;assert(html.includes('+0.20'));assert(html.includes('Labour · 100.10'));assert(html.includes('1 / 31'));assert(html.includes('never added together'));
});
check('all five dashboard backgrounds are neutral',()=>{
 const dashboard=fs.readFileSync(path.join(__dirname,'dashboard-oct30.js'),'utf8'),css=fs.readFileSync(path.join(__dirname,'reporting-oct30.css'),'utf8');
 assert(!dashboard.includes('class="o30-profit"'));assert(!css.includes('.o30-kpis .o30-profit'));
});
const charts=vm.createContext({Exact,state,window,escapeHtml,renderBusinessStats(){},proBusinessGroupedBars(){},renderIngredientGroupedCharts(){}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'charts-oct30.js'),'utf8'),charts);
check('English chart scales use K/M/B and preserve explicit user series names',()=>{
 const markup=window.Oct30Charts.markup({labels:['2026-01','2026-02'],kind:'bar',series:[{name:'删除',userContent:true,values:[decimal(10000),decimal(20000)]}]},400);
 assert(markup.includes('K</text>'));assert(!markup.includes('万'));assert(markup.includes('删除'));assert(markup.includes('<span data-user-content>'));assert(markup.includes('class="o30-readout" data-user-content'));
});
console.log(JSON.stringify({version:'v1.0.2',checks,passed:true}));
