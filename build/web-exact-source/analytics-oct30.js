/* Oct30LingChen — task-oriented analytics. All amounts remain Exact decimals. */
(function(root){
  'use strict';
  const E=root.Exact, ZERO=()=>E.decimal(0);
  const COSTS=[
    ['food','食材采购','Ingredients','#2e63c4'],['spice','佐料采购','Seasonings','#5b85d5'],
    ['labour','人工','Labour','#1b8a79'],['rent','房租／物业','Rent / property','#7274c4'],
    ['water','水费','Water','#3d9cc3'],['electric','电费','Electricity','#e1a43c'],
    ['gas','煤气费','Gas','#be8050'],['fees','手续费／抽成','Fees','#a575b5'],
    ['dailyUtilities','日结水电','Daily utilities','#71a8a1'],['other','其他日常支出','Other daily expenses','#8899ad'],
    ['fixedOther','其他固定支出','Other fixed expenses','#ba879c']
  ];
  const fixedFields={labour:['人工总额'],rent:['房租总额'],water:['水费支出','水电费'],electric:['电费支出'],gas:['煤气费'],fixedOther:['其它固定成本']};
  const dailyFields={food:'food',spice:'spice',fees:'fees',dailyUtilities:'waterDaily',other:'other'};
  const ctx={month:'',view:'overview',basis:'monthly',category:'all',metric:'net',search:'',page:1,dataset:'',lastRows:[],lastHeaders:[],installed:false};
  const txt=(zh,en)=>typeof state!=='undefined'&&state.language==='en'?en:zh;
  const esc=v=>escapeHtml(String(v??''));
  const amount=v=>E.decimal(v??0);
  const sum=values=>E.sum(values);
  const add=(a,b)=>E.calculate.add(a,b),sub=(a,b)=>E.calculate.sub(a,b),div=(a,b)=>E.calculate.div(a,b);
  const label=key=>{const c=COSTS.find(c=>c[0]===key);return c?txt(c[1],c[2]):txt('全部费用','All expenses');};
  const formatMoney=v=>v===null?'—':amount(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
  const formatCount=v=>v===null?'—':amount(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
  const monthValid=m=>/^\d{4}-(0[1-9]|1[0-2])$/.test(m||'');
  function monthShift(m,n){const [y,v]=m.split('-').map(Number),d=new Date(y,v-1+n,1);return`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;}
  function costCategory(v){const s=String(v||'').trim();if(/人工|工资|薪资|劳务/.test(s))return'labour';if(/房租|物业|租金/.test(s))return'rent';if(/煤气|燃气/.test(s))return'gas';if(/电费/.test(s))return'electric';if(/水费|水电/.test(s))return'water';return'fixedOther';}
  function expenseRecords(month){const rows=[];for(const record of state.records||[]){if(record.is_deleted||String(record.record_type||record.type)!=='day')continue;const payload=unpackPayload(record);for(const item of payload.fixed_expenses||[]){const date=normalizeDateKey(item.日期||record.record_key||'');if(!date.startsWith(month+'-'))continue;rows.push({date,category:costCategory(item.类别),description:String(item.明细||item.说明||item.类别||''),amount:amount(item.金额??item.amount??0),source:txt('逐笔固定支出','Itemized fixed expense'),rawCategory:String(item.类别||'')});}}return rows.sort((a,b)=>a.date.localeCompare(b.date));}
  function monthlyModel(month){
    const metrics=(state.days||[]).map(dayMetrics).filter(v=>v&&v.date.startsWith(month+'-')).sort((a,b)=>a.date.localeCompare(b.date));
    const fixed=state.months.get(month)||state.months.get(month.replace('-','/'))||{};
    const fixedKnown=state.months.has(month)||state.months.has(month.replace('-','/'));
    const costs=Object.fromEntries(COSTS.map(c=>[c[0],ZERO()])),sources=[];
    for(const m of metrics)for(const [key,field] of Object.entries(dailyFields)){
      const value=amount(m[field]);costs[key]=add(costs[key],value);
      if(E.cmp(value,0)!==0)sources.push({date:m.date,category:key,description:txt('当日记账汇总','Daily ledger total'),amount:value,source:txt('日流水','Daily ledger')});
    }
    for(const [key,fields] of Object.entries(fixedFields)){
      // Legacy combined 水电费 is used only when neither split field exists.
      let field=fields[0];if(key==='water'&&!entered(fixed.水费支出)&&!entered(fixed.电费支出))field='水电费';
      const value=amount(fixed[field]);costs[key]=value;
      if(entered(fixed[field]))sources.push({date:month,category:key,description:txt('月度固定成本保存值；不重复叠加逐笔支出','Saved monthly amount; itemized entries are not added again'),amount:value,source:txt('月度固定成本','Monthly fixed costs')});
    }
    const expenses=expenseRecords(month),itemized=Object.fromEntries(COSTS.map(c=>[c[0],ZERO()]));
    expenses.forEach(row=>itemized[row.category]=add(itemized[row.category],row.amount));
    const revenue=sum(metrics.map(m=>m.revenue)),total=sum(metrics.map(m=>m.total)),net=sum(metrics.map(m=>m.net)),gross=sum(metrics.map(m=>m.gross));
    const customers=sum(metrics.map(m=>m.customers)),fresh=sum(metrics.map(m=>m.newCustomers));
    return {month,metrics,fixed,fixedKnown,costs,sources,expenses,itemized,revenue,total,net,gross,customers,fresh,
      expenseTotal:sum(Object.values(costs)),fixedTotal:sum(Object.keys(fixedFields).map(k=>costs[k])),itemizedTotal:sum(expenses.map(r=>r.amount)),
      ticket:E.cmp(customers,0)>0?div(revenue,customers):null,
      margin:E.cmp(revenue,0)!==0?E.calculate.mul(div(net,revenue),100):null,
      newRatio:E.cmp(customers,0)>0?E.calculate.mul(div(fresh,customers),100):null,
      known:fixedKnown||metrics.length>0||expenses.length>0};
  }
  function costKnown(model,key,basis){if(basis==='itemized')return model.expenses.length>0;if(key==='all')return model.fixedKnown||model.metrics.length>0;if(Object.hasOwn(fixedFields,key))return model.fixedKnown;return model.metrics.length>0;}
  function costValue(model,key,basis){if(!costKnown(model,key,basis))return null;const values=basis==='itemized'?model.itemized:model.costs;return key==='all'?sum(Object.values(values)):values[key]||ZERO();}
  function metricValue(model,key){if(!model.metrics.length)return null;return model[key]??null;}
  function getModel(m){return monthlyModel(m);}
  function chart(host,options){if(root.Oct30Charts?.render)root.Oct30Charts.render(host,options);else host.innerHTML=`<div class="oa-empty">${txt('图表正在加载，完整数值可在下方明细查看。','Chart loading. Full values are available in the table below.')}</div>`;}
  function setText(id,value){const node=$(id);if(node)node.textContent=value;}
  function install(){
    const page=$('pageStats');if(!page||ctx.installed)return;ctx.installed=true;
    const oldNodes=[...page.children];const advanced=document.createElement('details');advanced.id='oaAdvanced';advanced.className='oa-advanced';advanced.innerHTML='<summary id="oaAdvancedSummary"></summary><div class="oa-advanced-body"></div>';
    const body=advanced.lastElementChild;oldNodes.forEach(n=>body.append(n));page.append(advanced);
    body.querySelector('.section-heading')?.classList.add('oa-legacy-heading');
    page.insertAdjacentHTML('afterbegin',`<section class="oa-heading"><div><p class="oa-eyebrow">ANALYTICS</p><h1 id="oaTitle"></h1><p id="oaSubtitle"></p></div><button id="oaExport" class="soft" type="button"></button></section>
      <section class="oa-filter analytics-controls"><div class="oa-period"><button id="oaPrevious" type="button" aria-label="上个月">‹</button><label><span id="oaMonthLabel"></span><input id="oaMonth" type="month"></label><button id="oaNext" type="button" aria-label="下个月">›</button><button id="oaThisMonth" class="soft" type="button"></button></div><div id="oaCoverage" class="oa-coverage"></div></section>
      <nav class="oa-tabs" aria-label="统计主题"><button type="button" data-oa-view="overview"></button><button type="button" data-oa-view="costs"></button><button type="button" data-oa-view="customers"></button><button type="button" id="oaIngredients"></button><button type="button" id="oaAdvancedLink"></button></nav>
      <div id="oaCostControls" class="oa-cost-controls analytics-controls"><label><span id="oaBasisLabel"></span><select id="oaBasis"><option value="monthly"></option><option value="itemized"></option></select></label><label><span id="oaCategoryLabel"></span><select id="oaCategory"></select></label><p id="oaBasisHelp"></p></div>
      <section id="oaKpis" class="oa-kpis" aria-live="polite"></section>
      <section class="oa-chart-grid"><article class="oa-panel oa-primary"><header><div><small id="oaTrendEyebrow"></small><h2 id="oaTrendTitle"></h2></div><label id="oaMetricWrap" class="analytics-controls"><span class="oa-sr-only">选择趋势指标</span><select id="oaMetric"></select></label></header><div id="oaTrend" class="oa-chart"></div><p class="oa-note" id="oaTrendNote"></p></article><article class="oa-panel oa-secondary"><header><div><small id="oaCompareEyebrow"></small><h2 id="oaCompareTitle"></h2></div></header><div id="oaCompare" class="oa-chart"></div><p class="oa-note" id="oaCompareNote"></p></article></section>
      <section id="oaCostBreakdown" class="oa-panel"><header><div><small id="oaCostEyebrow"></small><h2 id="oaCostTitle"></h2></div><button type="button" id="oaAllCosts" class="soft"></button></header><div id="oaCostRows" class="oa-cost-rows"></div></section>
      <section class="oa-panel oa-detail-panel"><header><div><small id="oaDetailEyebrow"></small><h2 id="oaDetailTitle"></h2></div><label class="analytics-controls oa-search"><span class="oa-sr-only">搜索明细</span><input id="oaSearch" type="search"></label></header><p id="oaTableHelp" class="oa-note"></p><div class="oa-table-scroll"><table class="oa-table"><thead id="oaHead"></thead><tbody id="oaRows"></tbody></table></div><footer class="oa-table-footer"><span id="oaTableCount"></span><div><button type="button" id="oaPagePrevious">‹</button><span id="oaPageLabel"></span><button type="button" id="oaPageNext">›</button></div></footer></section>
      <details class="oa-method"><summary id="oaMethodTitle"></summary><p id="oaMethodText"></p></details>`);
    $('oaPrevious').onclick=()=>changeMonth(monthShift(ctx.month,-1));$('oaNext').onclick=()=>changeMonth(monthShift(ctx.month,1));
    $('oaMonth').onchange=()=>{if(monthValid($('oaMonth').value))changeMonth($('oaMonth').value);else $('oaMonth').value=ctx.month;};
    $('oaThisMonth').onclick=()=>changeMonth(isoDate(new Date()).slice(0,7));
    page.querySelectorAll('[data-oa-view]').forEach(b=>b.onclick=()=>{ctx.view=b.dataset.oaView;ctx.category='all';ctx.page=1;ctx.search='';ctx.metric=ctx.view==='customers'?'customers':'net';render();});
    $('oaBasis').onchange=()=>{ctx.basis=$('oaBasis').value;ctx.page=1;render();};
    $('oaCategory').onchange=()=>{ctx.category=$('oaCategory').value;ctx.page=1;render();};
    $('oaMetric').onchange=()=>{ctx.metric=$('oaMetric').value;render();};
    $('oaAllCosts').onclick=()=>{ctx.view='costs';ctx.category='all';ctx.page=1;render();};
    $('oaSearch').oninput=()=>{ctx.search=$('oaSearch').value;ctx.page=1;renderTable();};
    $('oaPagePrevious').onclick=()=>{ctx.page=Math.max(1,ctx.page-1);renderTable();};$('oaPageNext').onclick=()=>{ctx.page++;renderTable();};
    $('oaExport').onclick=exportCsv;
    const openAdvanced=ingredients=>{syncLegacyMonth();advanced.open=true;renderStats();if(ingredients){const details=body.querySelector('.stats-disclosure');if(details)details.open=true;}advanced.scrollIntoView({block:'start',behavior:'smooth'});};
    $('oaIngredients').onclick=()=>openAdvanced(true);$('oaAdvancedLink').onclick=()=>openAdvanced(false);
    advanced.addEventListener('toggle',()=>{if(advanced.open&&root.Oct30Charts?.refresh)root.Oct30Charts.refresh();});
  }
  function syncLegacyMonth(){if(!$('statsYear')?.options.length)return;const year=ctx.month.slice(0,4);if(![...$('statsYear').options].some(o=>o.value===year))$('statsYear').add(new Option(year,year));$('statsYear').value=year;document.querySelectorAll('#statsMonthChecks input').forEach(i=>i.checked=Number(i.value)===Number(ctx.month.slice(5)));}
  function changeMonth(month){ctx.month=month;ctx.page=1;ctx.search='';syncLegacyMonth();renderStats();}
  function defaultMonth(){return monthValid(($('selectedDate')?.value||'').slice(0,7))?$('selectedDate').value.slice(0,7):isoDate(new Date()).slice(0,7);}
  function kpi(title,value,previous,kind='money',note=''){
    const display=value===null?'—':kind==='money'?formatMoney(value):kind==='rate'?formatCount(value)+'%':formatCount(value);
    const comparable=value!==null&&previous!==null,difference=comparable?sub(value,previous):null;
    const delta=comparable?`${E.cmp(difference,0)>0?'+':''}${kind==='money'?formatMoney(difference):formatCount(difference)}${kind==='rate'?txt(' 个百分点',' pp'):''}`:txt('暂无可比数据','No comparison data');
    return`<article class="oa-kpi"><span>${esc(title)}</span><strong class="${value!==null&&E.cmp(value,0)<0?'oa-negative':''}">${esc(display)}${kind==='money'?'<em>元</em>':''}</strong><small>${esc(note||txt('较上月已记账数据','vs recorded data last month'))}<b>${esc(delta)}</b></small></article>`;
  }
  function render(){
    install();if(!ctx.installed)return;
    const dataset=String(state.dataset?.id||'');if(ctx.dataset!==dataset){ctx.dataset=dataset;ctx.month=defaultMonth();ctx.search='';ctx.page=1;}
    if(!monthValid(ctx.month))ctx.month=defaultMonth();
    const model=getModel(ctx.month),previous=getModel(monthShift(ctx.month,-1));ctx.model=model;
    setText('oaTitle',txt('经营分析','Business analytics'));setText('oaSubtitle',txt('从经营结果到每笔费用，按月查看、对比与追溯。','Review monthly performance, compare costs and trace their sources.'));
    setText('oaExport',txt('导出当前明细 CSV','Export detail CSV'));setText('oaMonthLabel',txt('分析月份','Month'));setText('oaThisMonth',txt('本月','This month'));$('oaMonth').value=ctx.month;
    setText('oaCoverage',`${ctx.month} · ${txt('已记账','Recorded')} ${model.metrics.length} ${txt('天','days')} / ${daysInMonth(Number(ctx.month.slice(0,4)),Number(ctx.month.slice(5)))} ${txt('天','days')}`);
    const labels={overview:txt('经营概览','Overview'),costs:txt('费用分析','Expenses'),customers:txt('客流分析','Customers')};document.querySelectorAll('[data-oa-view]').forEach(b=>{b.textContent=labels[b.dataset.oaView];b.classList.toggle('active',b.dataset.oaView===ctx.view);b.setAttribute('aria-pressed',String(b.dataset.oaView===ctx.view));});
    setText('oaIngredients',txt('食材采购与消耗','Purchasing & usage'));setText('oaAdvancedLink',txt('自由分析','Custom analysis'));setText('oaAdvancedSummary',txt('自由分析 · 多月份、星期筛选、食材采购与消耗、库存明细','Custom analysis · months, weekdays, purchasing, usage and inventory'));
    $('oaCostControls').hidden=ctx.view!=='costs';setText('oaBasisLabel',txt('统计口径','Basis'));setText('oaCategoryLabel',txt('费用类别','Category'));
    $('oaBasis').options[0].textContent=txt('月度支出汇总','Monthly expense totals');$('oaBasis').options[1].textContent=txt('逐笔固定支出','Itemized fixed expenses');$('oaBasis').value=ctx.basis;
    $('oaCategory').innerHTML=`<option value="all">${txt('全部费用','All expenses')}</option>`+COSTS.map(c=>`<option value="${c[0]}">${esc(label(c[0]))}</option>`).join('');$('oaCategory').value=ctx.category;
    setText('oaBasisHelp',ctx.basis==='monthly'?txt('日常支出取自日流水；人工、房租等取月度固定成本保存值。逐笔记录不再重复加总。','Daily costs come from the ledger; labour and rent use saved monthly totals. Itemized entries are not added again.'):txt('仅统计逐笔固定支出记录的日期与金额。未录入流水不代表没有发生支出。','Only dated fixed-expense entries are included. Missing entries do not mean no spending occurred.'));
    const present=(m,key)=>metricValue(m,key);
    if(ctx.view==='costs'){
      const v=costValue(model,ctx.category,ctx.basis),p=costValue(previous,ctx.category,ctx.basis);
      $('oaKpis').innerHTML=kpi(label(ctx.category),v,p,'money',txt('较上月同口径','vs same basis last month'))+kpi(txt('月度固定支出汇总','Monthly fixed expense total'),model.fixedKnown?model.fixedTotal:null,previous.fixedKnown?previous.fixedTotal:null)+kpi(txt('食材与佐料采购','Ingredient purchases'),model.metrics.length?add(model.costs.food,model.costs.spice):null,previous.metrics.length?add(previous.costs.food,previous.costs.spice):null)+kpi(txt('逐笔固定支出已记录','Itemized fixed expenses'),model.expenses.length?model.itemizedTotal:null,previous.expenses.length?previous.itemizedTotal:null,'money',txt('独立口径，不与汇总相加','Separate basis; not added to totals'));
    }else if(ctx.view==='customers'){
      $('oaKpis').innerHTML=kpi(txt('总客人数','Customers'),present(model,'customers'),present(previous,'customers'),'count')+kpi(txt('新客人数','New customers'),present(model,'fresh'),present(previous,'fresh'),'count')+kpi(txt('新客占比','New customer share'),model.newRatio,previous.newRatio,'rate')+kpi(txt('平均客单价','Average spend'),model.ticket,previous.ticket);
    }else{
      $('oaKpis').innerHTML=kpi(txt('营业收入','Revenue'),present(model,'revenue'),present(previous,'revenue'))+kpi(txt('已记账日净利润','Net profit • recorded days'),present(model,'net'),present(previous,'net'))+kpi(txt('已记账日成本','Cost • recorded days'),present(model,'total'),present(previous,'total'))+kpi(txt('净利率','Net margin'),model.margin,previous.margin,'rate');
    }
    const year=ctx.month.slice(0,4),months=Array.from({length:12},(_,i)=>`${year}-${String(i+1).padStart(2,'0')}`),yearModels=months.map(getModel);
    $('oaMetricWrap').hidden=ctx.view==='costs';
    const metricOptions=ctx.view==='customers'?[['customers',txt('总客人数','Customers')],['fresh',txt('新客人数','New customers')],['ticket',txt('平均客单价','Average spend')]]:[['net',txt('净利润','Net profit')],['revenue',txt('营业收入','Revenue')],['gross',txt('毛利润','Gross profit')],['total',txt('总成本','Total cost')]];
    if(!metricOptions.some(v=>v[0]===ctx.metric))ctx.metric=metricOptions[0][0];$('oaMetric').innerHTML=metricOptions.map(([v,n])=>`<option value="${v}">${n}</option>`).join('');$('oaMetric').value=ctx.metric;
    const metricLabel=metricOptions.find(v=>v[0]===ctx.metric)[1],isCount=ctx.view==='customers'&&ctx.metric!=='ticket';
    setText('oaTrendEyebrow',ctx.view==='costs'&&ctx.basis==='monthly'?txt('年度比较','ANNUAL COMPARISON'):txt('本月趋势','MONTHLY TREND'));
    setText('oaCompareEyebrow',txt('月度比较','MONTHLY COMPARISON'));
    setText('oaTrendNote',txt('悬停、点按或使用键盘查看精确值；未录入日期保留空缺。','Hover, tap or use the keyboard for exact values. Missing dates remain gaps.'));
    setText('oaCompareNote',txt('各月按相同口径计算；空缺表示没有对应记录。','Every month uses the same basis. Gaps indicate no corresponding records.'));
    if(ctx.view==='costs'){
      const values=yearModels.map(m=>costValue(m,ctx.category,ctx.basis));
      if(ctx.basis==='monthly'){
        setText('oaTrendTitle',`${year} · ${label(ctx.category)}`);chart($('oaTrend'),{labels:months,series:[{name:label(ctx.category),values,color:'#315dc5'}],kind:'bar',format:formatMoney});
        setText('oaTrendNote',txt('月度汇总按整月保存值展示，不虚构每天的人工、房租支出。','Monthly totals use whole-month saved amounts, without fabricating daily labour or rent payments.'));
        setText('oaCompareTitle',txt('本月固定支出 · 两种口径','Monthly fixed expenses · two bases'));
        const fixedKeys=Object.keys(fixedFields).filter(k=>ctx.category==='all'||ctx.category===k);
        chart($('oaCompare'),{labels:fixedKeys.map(label),series:[{name:txt('月度汇总','Monthly total'),values:fixedKeys.map(k=>model.fixedKnown?model.costs[k]:null),color:'#315dc5'},{name:txt('逐笔已记录','Itemized entries'),values:fixedKeys.map(k=>model.expenses.length?model.itemized[k]:null),color:'#62a99b'}],kind:'bar',format:formatMoney});
        setText('oaCompareNote',txt('两列是核对关系，不相加；差异通常表示尚未逐笔补齐或月度汇总未更新。','These columns are for reconciliation, not addition. Differences may reflect incomplete itemization or outdated monthly totals.'));
      }else{
        const selected=model.expenses.filter(r=>ctx.category==='all'||r.category===ctx.category),dates=[...new Set(selected.map(r=>r.date))];
        setText('oaTrendTitle',txt('逐笔支出日期分布','Dated expense entries'));chart($('oaTrend'),{labels:dates,series:[{name:label(ctx.category),values:dates.map(d=>sum(selected.filter(r=>r.date===d).map(r=>r.amount))),color:'#1b8a79'}],kind:'bar',format:formatMoney});
        setText('oaCompareTitle',`${year} · ${label(ctx.category)}`);chart($('oaCompare'),{labels:months,series:[{name:label(ctx.category),values,color:'#315dc5'}],kind:'bar',format:formatMoney});
      }
    }else{
      const days=daysInMonth(Number(year),Number(ctx.month.slice(5))),lookup=new Map(model.metrics.map(m=>[m.date,m]));
      const dates=Array.from({length:days},(_,i)=>`${ctx.month}-${String(i+1).padStart(2,'0')}`);
      const dailyValue=m=>ctx.metric==='fresh'?m.newCustomers:ctx.metric==='ticket'?(E.cmp(m.customers,0)>0?div(m.revenue,m.customers):null):m[ctx.metric];
      setText('oaTrendTitle',metricLabel);chart($('oaTrend'),{labels:dates,series:[{name:metricLabel,values:dates.map(d=>lookup.has(d)?dailyValue(lookup.get(d)):null),color:ctx.view==='customers'?'#1b8a79':'#315dc5'}],kind:'line',format:isCount?formatCount:formatMoney});
      setText('oaCompareTitle',`${year} · ${metricLabel}`);chart($('oaCompare'),{labels:months,series:[{name:metricLabel,values:yearModels.map(m=>metricValue(m,ctx.metric)),color:'#7c96ca'}],kind:'bar',format:isCount?formatCount:formatMoney});
    }
    $('oaCostBreakdown').hidden=ctx.view==='customers';setText('oaCostEyebrow',txt('费用结构','EXPENSE BREAKDOWN'));setText('oaCostTitle',txt('点选类别，查看金额与来源','Select a category to inspect its sources'));setText('oaAllCosts',txt('查看全部费用','View all expenses'));
    const basis=ctx.view==='costs'?ctx.basis:'monthly',values=basis==='itemized'?model.itemized:model.costs,total=sum(Object.values(values)),max=E.math.max(1,...Object.values(values));
    $('oaCostRows').innerHTML=COSTS.map(c=>({key:c[0],color:c[3],value:values[c[0]]})).sort((a,b)=>E.cmp(b.value,a.value)).map(c=>{const share=E.cmp(total,0)>0?E.calculate.mul(div(c.value,total),100):ZERO(),width=E.toNumber(E.calculate.mul(div(E.abs(c.value),max),100));return`<button type="button" class="oa-cost-row ${ctx.category===c.key&&ctx.view==='costs'?'selected':''}" data-oa-cost="${c.key}" aria-pressed="${ctx.category===c.key&&ctx.view==='costs'}"><span>${esc(label(c.key))}</span><i class="oa-cost-track"><i style="width:${Math.max(0,Math.min(100,width))}%;background:${c.color}"></i></i><strong>${costKnown(model,c.key,basis)?formatMoney(c.value):'—'}</strong><small>${costKnown(model,c.key,basis)?formatCount(share)+'%':'—'}</small><b aria-hidden="true">›</b></button>`;}).join('');
    $('oaCostRows').querySelectorAll('[data-oa-cost]').forEach(b=>b.onclick=()=>{ctx.view='costs';ctx.category=b.dataset.oaCost;ctx.page=1;ctx.search='';render();$('oaDetailTitle').scrollIntoView({block:'center',behavior:'smooth'});});
    setText('oaDetailEyebrow',txt('可追溯明细','SOURCE DETAILS'));setText('oaDetailTitle',ctx.view==='costs'?`${label(ctx.category)} · ${ctx.basis==='monthly'?txt('汇总来源','Summary sources'):txt('支出流水','Expense entries')}`:ctx.view==='customers'?txt('每日客流明细','Daily customer details'):txt('每日经营明细','Daily performance'));
    $('oaSearch').placeholder=txt('搜索日期、类别、说明','Search date, category or description');$('oaSearch').value=ctx.search;
    setText('oaTableHelp',ctx.view==='costs'?txt('月度汇总与逐笔支出分别查看。金额来自当前账本，导出包含搜索后的全部明细。','Monthly totals and itemized expenses are separate. Export includes all filtered rows from the current ledger.'):txt('成本与净利润沿用原账本的日核算口径；仅汇总已录入的日期。','Cost and profit follow the existing daily ledger calculation and include recorded dates only.'));
    buildTable(model);renderTable();
    setText('oaMethodTitle',txt('查看统计口径与数据说明','Calculation and data notes'));
    setText('oaMethodText',txt('经营概览：收入、成本、利润按日流水汇总；日成本包含按当月天数分摊的固定支出。费用分析：月度支出汇总使用日流水采购、手续费、其他支出，加上月度人工、房租、水电煤气等保存值，固定费用不按已记账天数折算。逐笔固定支出只展示 fixed_expenses 明细，与月度汇总分开核对，绝不重复加总。水电“实际使用／预计”用于原有成本构成，月度支出视图使用支出金额。空缺日期、没有分母的比例显示为空，不能据此认定没有业务。采购金额与FIFO出库成本是不同口径，出库批次及成本请在库存管理查看。','Overview aggregates recorded daily revenue, costs and profit, including the existing daily fixed-cost allocation. Monthly expenses combine daily purchases and expenses with full saved monthly fixed amounts. Itemized fixed expenses are reconciled separately and never added twice. The expense view uses paid amounts rather than expected utility usage. Missing dates and ratios without a denominator remain blank. Purchases and FIFO issue costs are distinct; inspect issue batches in Inventory.'));
  }
  function buildTable(model){
    if(ctx.view==='costs'){
      ctx.lastHeaders=[txt('日期／月份','Date / month'),txt('类别','Category'),txt('说明','Description'),txt('金额（元）','Amount (CNY)'),txt('来源','Source')];
      const rows=(ctx.basis==='itemized'?model.expenses:model.sources).filter(r=>ctx.category==='all'||r.category===ctx.category);
      ctx.lastRows=rows.map(r=>[r.date,label(r.category),r.description,r.amount,r.source]);
    }else if(ctx.view==='customers'){
      ctx.lastHeaders=[txt('日期','Date'),txt('总客数','Customers'),txt('新客','New'),txt('老客','Returning'),txt('新客占比','New share'),txt('客单价（元）','Average spend (CNY)')];
      ctx.lastRows=model.metrics.map(m=>[m.date,amount(m.customers),amount(m.newCustomers),amount(m.oldCustomers),E.cmp(m.customers,0)>0?formatCount(E.calculate.mul(div(m.newCustomers,m.customers),100))+'%':'—',E.cmp(m.customers,0)>0?div(m.revenue,m.customers):null]);
    }else{
      ctx.lastHeaders=[txt('日期','Date'),txt('营业收入（元）','Revenue (CNY)'),txt('总成本（元）','Cost (CNY)'),txt('净利润（元）','Net profit (CNY)'),txt('净利率','Net margin'),txt('总客数','Customers')];
      ctx.lastRows=model.metrics.map(m=>[m.date,m.revenue,m.total,m.net,E.cmp(m.revenue,0)!==0?formatCount(E.calculate.mul(div(m.net,m.revenue),100))+'%':'—',amount(m.customers)]);
    }
  }
  function matchingRows(){const q=ctx.search.trim().toLowerCase();return q?ctx.lastRows.filter(row=>row.some(v=>String(v??'').toLowerCase().includes(q))):ctx.lastRows;}
  function renderTable(){if(!$('oaRows'))return;const rows=matchingRows(),size=20,pages=Math.max(1,Math.ceil(rows.length/size));ctx.page=Math.min(pages,Math.max(1,ctx.page));
    $('oaHead').innerHTML='<tr>'+ctx.lastHeaders.map(h=>`<th scope="col">${esc(h)}</th>`).join('')+'</tr>';
    $('oaRows').innerHTML=rows.slice((ctx.page-1)*size,ctx.page*size).map(row=>'<tr>'+row.map((v,i)=>`<td class="${E.is(v)?'oa-number':''}" ${i===2&&ctx.view==='costs'?'title="'+esc(v)+'"':''}>${E.is(v)?formatMoney(v):esc(v===null?'—':v)}</td>`).join('')+'</tr>').join('')||`<tr><td colspan="${ctx.lastHeaders.length}" class="oa-empty">${esc(ctx.search?txt('没有匹配的明细，请调整搜索内容。','No matching rows. Adjust the search.'):ctx.view==='costs'&&ctx.basis==='itemized'?txt('尚未录入这类逐笔支出。可切换“月度支出汇总”查看月度保存值。','No itemized entries for this category. Switch to monthly totals to inspect saved amounts.'):txt('所选月份暂无对应记录。','No corresponding records for this month.'))}</td></tr>`;
    setText('oaTableCount',`${rows.length} ${txt('条明细','rows')}${ctx.search?txt('（已筛选）',' (filtered)'):''}`);setText('oaPageLabel',`${ctx.page} / ${pages}`);$('oaPagePrevious').disabled=ctx.page<=1;$('oaPageNext').disabled=ctx.page>=pages;
  }
  function csvCell(value){if(E.is(value))return value.toFixed(2);let text=String(value??'');if(/^\s*[=+\-@]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';}
  function exportCsv(){const rows=matchingRows(),csv='\ufeff'+[ctx.lastHeaders,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n'),blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${ctx.month}-${ctx.view}-${ctx.basis}-${ctx.category}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  root.Oct30Analytics={open(options={}){install();ctx.dataset=String(state.dataset?.id||'');if(monthValid(options.month))ctx.month=options.month;ctx.view=['overview','costs','customers'].includes(options.view)?options.view:'overview';ctx.category=options.category&&COSTS.some(c=>c[0]===options.category)?options.category:'all';ctx.page=1;ctx.search='';showPage('stats');syncLegacyMonth();render();},render,model:monthlyModel,costValue,expenseRecords,category:costCategory};
  if(typeof renderStats==='function'){const previous=renderStats;renderStats=function(){previous();render();};}
  install();
})(typeof window!=='undefined'?window:globalThis);
