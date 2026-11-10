/* v1.0.2: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";
/* v1.0.1 reporting workbench; preserves the original detailed reports. */
(() => {
  const en=()=>Exact.seq(state.language, 'en'),t=(zh,english)=>(Exact.truth(en()) ? english : zh);
  function setup(){const page=$('pageOverview');if(Exact.truth(Exact.or(()=>(Exact.not(page)), ()=>($('o30Overview')))))return;
    const overview=document.createElement('section');overview.id='o30Overview';overview.className='o30-overview';page.querySelector('.summary-grid').before(overview);
    const detail=document.createElement('details');detail.id='o30DashboardDetails';detail.className='o30-details';detail.innerHTML='<summary></summary>';detail.appendChild(page.querySelector('.summary-grid'));page.appendChild(detail);
    const chartGrid=page.querySelector('.dashboard-charts'),trend=$('trendChart').closest('.chart-card');trend.classList.add('o30-main-trend');chartGrid.prepend(trend);
    $('costDonut').closest('.chart-card').classList.add('o30-cost-card');$('expenseChart').closest('.chart-card').classList.add('o30-expense-card');$('weekdayChart').closest('.chart-card').classList.add('o30-weekday-card');
  }
  function monthChangeV102(current,previous){
    if(Exact.truth(Exact.or(()=>(Exact.seq(current, null)), ()=>(Exact.seq(previous, null)))))return t('暂无上月可比数据','No comparable previous-month data');
    const difference=Exact.sub(current,previous),direction=Exact.cmp(difference,0);
    if(Exact.truth(Exact.seq(direction, 0)))return t('与上个月持平 0.0%','Unchanged from last month 0.0%');
    if(Exact.truth(Exact.seq(Exact.cmp(previous,0), 0)))return t('上个月为 0，无法计算百分比','Previous month was 0; percentage unavailable');
    const change=Exact.calculate.div(Exact.calculate.mul(Exact.abs(difference),100),Exact.abs(previous)).toFixed(1);
    return (Exact.truth(en()) ? `${(Exact.truth(Exact.gt(direction, 0)) ? 'More' : 'Less')} than last month by ${change}%` : `比上个月${(Exact.truth(Exact.gt(direction, 0)) ? '多了' : '少了')} ${change}%`);
  }
  function summary(){setup();const c=selectedContext(),forecast=monthForecastV102(c.year,c.month),current=forecast.current,
    previousDate=new Date(c.year,Exact.sub(c.month, 2),1),previousForecast=monthForecastV102(previousDate.getFullYear(),Exact.add(previousDate.getMonth(), 1)),previous=forecast.previous,month=current.key;
    const value=v=>(Exact.truth(Exact.seq(v, null)) ? '—' : money(v)),color=v=>(Exact.truth(Exact.seq(v, null)) ? '' : (Exact.truth(Exact.lt(Exact.cmp(v,0), 0)) ? 'negative' : 'positive')),
      gross=(Exact.truth(Exact.seq(current.avgGross, null)) ? '—' : `${money(current.avgGross)} <span class="o30-kpi-margin">(${percent(current.avgGross,current.avgRevenue)})</span>`),
      netMargin=(Exact.truth(Exact.seq(current.netMargin, null)) ? '—' : `${Exact.decimal(current.netMargin).toFixed(1)}%`),
      netValue=v=>(Exact.truth(Exact.seq(v, null)) ? '—' : `${money(v)} <span class="o30-kpi-margin">(${netMargin})</span>`),
      forecastNote=(Exact.truth(forecast.closed) ? t('已结月：显示实际净利润','Closed month: actual net profit') : t('本月预测：上月总成本与本月日均收入','Current estimate: previous costs and current average daily revenue'));
    $('o30Overview').innerHTML=`<div class="o30-section-line"><div><span class="o30-eyebrow">${t('月度经营概览','MONTHLY OVERVIEW')}</span><h2>${month} <span>${t('经营表现','Performance')}</span></h2></div><button type="button" class="soft" id="o30AnalyzeCosts">${t('分析本月费用','Analyze costs')} <span aria-hidden="true">↗</span></button></div><div class="o30-kpis"><article data-overview-metric="avgRevenue"><span>${t('日均收入','Average daily revenue')}</span><strong>${value(current.avgRevenue)}</strong><small>${monthChangeV102(current.avgRevenue,previous.avgRevenue)}</small></article><article data-overview-metric="avgGross"><span>${t('日均毛利润 (毛利率)','Average daily gross profit (Margin)')}</span><strong class="${color(current.avgGross)}">${gross}</strong><small>${monthChangeV102(current.avgGross,previous.avgGross)}</small></article><article data-overview-metric="forecast" title="${forecastNote}"><span>${t('预计月底盈亏','Estimated month-end profit/loss')}<span class="o30-kpi-formula">${t('(根据 上个月总成本 和 这个月日均收入 计算)','(based on previous month total cost and current average daily revenue)')}</span></span><strong class="${color(forecast.net)}">${value(forecast.net)}</strong><small>${monthChangeV102(forecast.net,previousForecast.net)}</small></article><article data-overview-metric="avgNet"><span>${t('日均净利润 (净利率)','Average daily net profit (Margin)')}</span><strong class="${color(current.avgNet)}">${netValue(current.avgNet)}</strong><small>${monthChangeV102(current.avgNet,previous.avgNet)}</small></article><article data-overview-metric="net"><span>${t('净利润 (净利率)','Net profit (Margin)')}</span><strong class="${color(current.net)}">${netValue(current.net)}</strong><small>${monthChangeV102(current.net,previous.net)}</small></article></div><div class="o30-context"><span><i></i>${t('已录入','Recorded')} ${current.items.length} ${t('个营业日','operating days')} · ${t('所选日期','Selected date')} ${c.dateText}${(Exact.truth(forecast.closed) ? ` · ${forecastNote}` : '')}</span><span>${t('当日收入','Day revenue')} ${(Exact.truth(dayRowForDate(c.dateText)) ? money(c.day.revenue) : t('未记录','No record'))}</span></div>`;
    $('o30AnalyzeCosts').onclick=()=>window.Oct30Analytics?.open({month,view:'costs'});
    $('o30DashboardDetails').querySelector('summary').innerHTML=`<strong>${t('完整经营报表','Full financial reports')}</strong><span>${t('日 / 周 / 月 / 年 · 预测与全部指标','Day / week / month / year · forecasts and all metrics')}</span>`;
    const subtitle=pageSubtitle();if(Exact.truth(subtitle))subtitle.textContent=t('先看本月表现，再查看趋势、成本与具体来源。','Start with monthly performance, then inspect trends and costs.');
  }
  function pageSubtitle(){let p=$('pageOverview').querySelector('.page-title-row p');if(Exact.truth(Exact.not(p))){p=document.createElement('p');$('pageOverview').querySelector('.page-title-row h1').after(p);}return p;}
  fitDashboardMonthChart=function(){if(Exact.truth(Exact.not($('selectedYear')?.value)))return;const y=Exact.toNumber($('selectedYear').value),m=Exact.toNumber($('selectedMonth').value),key=$('trendMetric').value,prefix=`${y}-${String(m).padStart(2,'0')}`,lookup=new Map(state.days.filter(r=>String(r.日期).startsWith(prefix)).map(r=>[String(r.日期),dayMetrics(r)])),labels=[],values=[];
    for(let day=1;Exact.truth(Exact.lte(day, daysInMonth(y,m)));day++){const date=`${prefix}-${String(day).padStart(2,'0')}`,metric=lookup.get(date);labels.push(`${m}/${day}`);values.push((Exact.truth(Exact.not(metric)) ? null : (Exact.truth(Exact.seq(key, 'food')) ? Exact.add(metric.food,metric.spice) : metric[(Exact.truth(Exact.seq(key, 'revenue')) ? 'revenue' : (Exact.truth(Exact.seq(key, 'gross')) ? 'gross' : 'net'))])));}
    const names={net:t('每日净利润','Daily net profit'),gross:t('每日毛利润','Daily gross profit'),food:t('食材与佐料成本','Ingredient and seasoning costs'),revenue:t('每日营业收入','Daily revenue')};$('trendTitle').textContent=names[key];$('trendSummary').textContent=Exact.add(t('已录入累计 ','Recorded total '), money(Exact.sum(values.filter(v=>Exact.sneq(v, null)))));
    Oct30Charts.render($('trendChart'),{labels,series:[{name:names[key],values,color:'#2563a6'}],format:money,height:300});const hint=$('trendChart').parentElement.querySelector('.chart-hint');if(Exact.truth(hint))hint.textContent=t('空白日期表示未录入；每日利润按当日成本口径，月度利润含整月固定成本。','Gaps indicate no record. Daily profit uses daily costs; monthly profit includes full-month fixed costs.');
  };
  renderWeekdays=function(metrics){const names=(Exact.truth(en()) ? ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] : ['周一','周二','周三','周四','周五','周六','周日']),groups=names.map(()=>[]);metrics.forEach(m=>groups[Exact.mod(Exact.add(parseDate(m.date).getDay(), 6), 7)].push(m));Oct30Charts.render($('weekdayChart'),{labels:names,kind:'bar',series:[{name:t('平均净利润','Average net profit'),color:'#0f8a7c',values:groups.map(g=>(Exact.truth(g.length) ? Exact.div(Exact.sum(g.map(m=>m.net)),g.length) : null))}],format:money,height:240});};
  const donutBase=renderCostDonut;renderCostDonut=function(day){donutBase(day);const entries=(Exact.truth(day) ? Object.entries(day.expense).filter(([,v])=>Exact.gt(Exact.cmp(v,0), 0)) : []),total=Exact.sum(entries.map(([,v])=>v));$('costLegend').innerHTML=Exact.or(()=>(entries.map(([name,value],i)=>`<div class="legend-row"><i style="background:${colors[Exact.mod(i, colors.length)]}"></i><span>${escapeHtml(name)}</span><strong>${money(value)}<small>${percent(value,total)}</small></strong></div>`).join('')), ()=>(`<div class="o30-empty">${t('当天没有成本记录','No cost records for this date')}</div>`));};
  const base=renderDashboard;renderDashboard=function(...args){setup();const result=base.apply(this,args);summary();return result;};
  // Earlier handlers retain references to older wrappers. Schedule the final
  // responsive rendering after any of their date/filter handlers complete.
  ['selectedDate','selectedMonth','selectedYear','trendMetric'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(()=>{summary();fitDashboardMonthChart();},0)));
  // Expand keeps native responsive charts; no artificial chart padding/pan frame.
  const expandBase=toggleChartExpanded;toggleChartExpanded=function(button){const card=button.closest('.chart-card');if(Exact.truth(Exact.not(card?.querySelector('.o30-chart,.o30-facets'))))return expandBase(button);const opening=Exact.not(card.classList.contains('chart-expanded'));closeExpandedCharts();if(Exact.truth(opening)){card.classList.add('chart-expanded','o30-expanded');document.body.classList.add('chart-modal-open');button.textContent=t('退出全屏','Exit full screen');button.focus();}};
  const bindBase=bindInteractiveChart;bindInteractiveChart=function(host){if(Exact.truth(host.querySelector('.o30-svg')))return;return bindBase(host);};
  setup();if(Exact.truth(state.token))renderDashboard();
  // An unchanged cloud snapshot skips dashboard rendering. Watch the local
  // calendar independently so an open page closes last month at midnight.
  refreshCalendarBoundaryV102();setInterval(refreshCalendarBoundaryV102,5000);
  document.addEventListener('visibilitychange',()=>{if(Exact.truth(Exact.not(document.hidden)))refreshCalendarBoundaryV102();});
})();
