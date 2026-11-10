'use strict';
// Data and accessibility regressions for the shipped shared SVG renderer.
// Browser geometry/resize coverage lives in build/qa_web_browser.cjs.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const Exact=require('./money.js'),state={language:'zh'},window={};
const esc=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const c=vm.createContext({Exact,state,window,escapeHtml:esc,Math,Date,Number,String,Array,Set,
  renderBusinessStats(){},proBusinessGroupedBars(){},renderIngredientGroupedCharts(){}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'charts-oct30.js'),'utf8'),c);
const markup=(labels,width=300,kind='bar',values=labels.map((_,i)=>String(i+1)))=>window.Oct30Charts.markup({labels,kind,series:[{name:'金额',values}],format:v=>Exact.decimal(v).toFixed(2)},width);
let checks=0;const check=(name,fn)=>{fn();checks++;console.log('PASS',name);};
check('month axis abbreviates dates while all original point labels remain accessible',()=>{
  const labels=Array.from({length:12},(_,i)=>`2026-${String(i+1).padStart(2,'0')}`),html=markup(labels);
  assert.match(html,/>1月<\/tspan>/);assert.match(html,/>12月<\/tspan>/);
  assert.equal([...html.matchAll(/data-o30-index=/g)].length,12);
  labels.forEach(label=>assert.ok(html.includes(`data-tooltip="${label}\n`)));
  state.language='en';const english=markup(labels);assert.match(english,/>Jan<\/tspan>/);assert.match(english,/>Dec<\/tspan>/);state.language='zh';
});
check('daily and cross-year dates retain full exact readout labels',()=>{
  const dates=Array.from({length:31},(_,i)=>`2026-10-${String(i+1).padStart(2,'0')}`),html=markup(dates,300,'line');
  assert.match(html,/>10\/1<\/tspan>/);assert.match(html,/>10\/31<\/tspan>/);
  assert.equal([...html.matchAll(/data-o30-index=/g)].length,31);
  const cross=markup(['2025-12','2026-01'],260);assert.match(cross,/>2025-12<\/tspan>/);assert.match(cross,/>2026-01<\/tspan>/);
});
check('all six fixed categories are wrapped instead of being dropped',()=>{
  const labels=['人工','房租及物业','水费','电费','煤气费','其他固定支出'];
  for(const width of [220,280,360,600]){const html=markup(labels,width);assert.equal([...html.matchAll(/data-o30-tick-index=/g)].length,6);labels.forEach(label=>assert.ok(html.includes(`data-tooltip="${label}\n`)));assert.ok(!html.includes('NaN'));}
});
check('missing observations and decimal amounts are preserved',()=>{
  const html=markup(['2026-10-01','2026-10-02','2026-10-03'],360,'line',[Exact.decimal('9007199254740993.12'),null,Exact.decimal('-0.01')]);
  assert.ok(html.includes('9007199254740993.12'));assert.ok(html.includes('2026-10-02\n金额: 未记录'));assert.ok(html.includes('-0.01'));
  assert.equal([...html.matchAll(/data-o30-index=/g)].length,3);
});
check('empty and one-point charts have usable states',()=>{
  assert.ok(markup([],260).includes('这段时间还没有记录'));
  for(const kind of ['bar','line']){const html=markup(['2026-10-01'],260,kind);assert.equal([...html.matchAll(/data-o30-tick-index=/g)].length,1);assert.ok(!/NaN|Infinity/.test(html));}
});
console.log(JSON.stringify({version:'v1.0.2',checks,passed:true}));
