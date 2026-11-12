"use strict";
/* v1.0.1 reporting workbench; preserves the original detailed reports. */
(() => {
  const en=()=>state.language==='en',t=(zh,english)=>en()?english:zh;
  // Keep one viewport-constrained popup for all forecast labels, including a
  // label replaced by a dashboard refresh while its explanation is open.
  function bindForecastHelp(){
    const panel=document.createElement('div');
    panel.id='forecast-help-popup';panel.className='forecast-help-panel';
    panel.setAttribute('role','tooltip');panel.hidden=true;document.body.appendChild(panel);
    let trigger=null,sourceId='',pinned=false,focused=false,leaveTimer;
    const helpButton=element=>element?.closest?.('.forecast-info-button');
    function close(){
      clearTimeout(leaveTimer);trigger?.setAttribute('aria-expanded','false');
      trigger=null;sourceId='';pinned=false;focused=false;panel.hidden=true;
    }
    function position(){
      if(!trigger)return;
      const rect=trigger.getBoundingClientRect(),gutter=8,width=document.documentElement.clientWidth,height=window.innerHeight;
      if(!rect.height||rect.bottom<=0||rect.top>=height){close();return;}
      const below=height-rect.bottom-2*gutter,above=rect.top-2*gutter;
      panel.style.maxHeight=`${height-2*gutter}px`;
      const useBelow=below>=panel.offsetHeight||below>=above;
      panel.style.maxHeight=`${Math.max(40,useBelow?below:above)}px`;
      const top=useBelow?rect.bottom+gutter:rect.top-gutter-panel.offsetHeight;
      panel.style.top=`${Math.max(gutter,top)}px`;
      panel.style.left=`${Math.max(gutter,Math.min(rect.left,width-gutter-panel.offsetWidth))}px`;
    }
    function show(button){
      clearTimeout(leaveTimer);
      const opening=trigger!==button;
      if(opening){close();trigger=button;sourceId=button.getAttribute('aria-describedby');}
      const source=document.getElementById(sourceId);if(!source){close();return;}
      if(panel.textContent!==source.textContent)panel.textContent=source.textContent;
      trigger.setAttribute('aria-expanded','true');panel.hidden=false;position();
      if(opening)panel.scrollTop=0;
    }
    function sync(){
      if(!trigger)return;
      if(!trigger.isConnected){
        const replacement=document.querySelector(`.forecast-info-button[aria-describedby="${sourceId}"]`);
        if(!replacement){close();return;}
        trigger=replacement;
        if(focused)replacement.focus({preventScroll:true});
      }
      show(trigger);
    }
    document.addEventListener('pointerover',event=>{
      if(event.pointerType==='touch')return;
      if(panel.contains(event.target)){clearTimeout(leaveTimer);return;}
      const button=helpButton(event.target);if(button)show(button);
    });
    document.addEventListener('pointerout',event=>{
      if(event.pointerType==='touch'||!trigger||pinned||focused)return;
      if(!trigger.contains(event.target)&&!panel.contains(event.target))return;
      if(trigger.contains(event.relatedTarget)||panel.contains(event.relatedTarget))return;
      leaveTimer=setTimeout(close,200);
    });
    document.addEventListener('focusin',event=>{
      const button=helpButton(event.target);if(button){show(button);focused=true;}
      else if(!panel.contains(event.target))close();
    });
    document.addEventListener('focusout',event=>{
      if(event.target===trigger&&event.relatedTarget&&!panel.contains(event.relatedTarget))close();
    });
    document.addEventListener('pointerdown',event=>{
      if(!helpButton(event.target)&&!panel.contains(event.target))close();
    });
    document.addEventListener('click',event=>{
      const button=helpButton(event.target);if(!button)return;
      if(trigger===button&&pinned)close();
      else{show(button);pinned=true;}
    });
    document.addEventListener('keydown',event=>{
      if(!trigger)return;
      if(event.key==='Escape'){close();event.preventDefault();return;}
      if(event.target!==trigger||panel.scrollHeight<=panel.clientHeight)return;
      const distance={ArrowDown:32,ArrowUp:-32,PageDown:panel.clientHeight,PageUp:-panel.clientHeight,Home:-panel.scrollHeight,End:panel.scrollHeight};
      if(Object.hasOwn(distance,event.key)){panel.scrollTop+=distance[event.key];event.preventDefault();}
    });
    // Advanced analytics redraws its forecast after the dashboard has rendered.
    const statsBanner=$('statsForecastBanner');
    if(statsBanner)new MutationObserver(()=>{
      if(sourceId==='forecast-help-stats')sync();
    }).observe(statsBanner,{childList:true});
    window.addEventListener('resize',sync);
    document.addEventListener('scroll',event=>{if(!panel.contains(event.target))sync();},true);
    return sync;
  }
  const syncForecastHelp=bindForecastHelp();
  function setup(){const page=$('pageOverview');if(!page||$('o30Overview'))return;
    const overview=document.createElement('section');overview.id='o30Overview';overview.className='o30-overview';page.querySelector('.summary-grid').before(overview);
    const detail=document.createElement('details');detail.id='o30DashboardDetails';detail.className='o30-details';detail.innerHTML='<summary></summary>';detail.appendChild(page.querySelector('.summary-grid'));page.appendChild(detail);
    const chartGrid=page.querySelector('.dashboard-charts'),trend=$('trendChart').closest('.chart-card');trend.classList.add('o30-main-trend');chartGrid.prepend(trend);
    $('costDonut').closest('.chart-card').classList.add('o30-cost-card');$('expenseChart').closest('.chart-card').classList.add('o30-expense-card');$('weekdayChart').closest('.chart-card').classList.add('o30-weekday-card');
  }
  function monthChangeV102(current,previous,currentDivisor=1,previousDivisor=1){
    if(current===null||previous===null)return t('暂无上月可比数据','No comparable previous-month data');
    // Compare fractions at a common denominator so a repeating daily rate
    // cannot move an exact half-tenth percentage across its rounding boundary.
    const prior=Exact.mul(previous,currentDivisor);
    const difference=Exact.sub(Exact.mul(current,previousDivisor),prior),direction=Exact.cmp(difference,0);
    if(direction===0)return t('与上个月持平 0.0%','Unchanged from last month 0.0%');
    if(Exact.cmp(prior,0)===0)return t('上个月为 0，无法计算百分比','Previous month was 0; percentage unavailable');
    const change=Exact.calculate.div(Exact.calculate.mul(Exact.abs(difference),100),Exact.abs(prior),1).toFixed(1);
    return en()?`${direction>0?'More':'Less'} than last month by ${change}%`:`比上个月${direction>0?'多了':'少了'} ${change}%`;
  }
  function summary(){setup();const c=selectedContext(),forecast=monthForecastV102(c.year,c.month),current=forecast.current,
    previousDate=new Date(c.year,c.month-2,1),previousForecast=monthForecastV102(previousDate.getFullYear(),previousDate.getMonth()+1),previous=forecast.previous,month=current.key;
    const value=v=>v===null?'—':money(v),color=v=>v===null?'':Exact.cmp(v,0)<0?'negative':'positive',
      gross=current.avgGross===null?'—':`${money(current.avgGross)} <span class="o30-kpi-margin">(${percent(current.avgGross,current.avgRevenue)})</span>`,
      netMargin=current.netMargin===null?'—':`${Exact.decimal(current.netMargin).toFixed(1)}%`,
      netValue=v=>v===null?'—':`${money(v)} <span class="o30-kpi-margin">(${netMargin})</span>`,
      forecastNote=t('已结月：显示实际净利润','Closed month: actual net profit');
    const dailyNetValue=forecast.dailyNet===null?'—':money(forecast.dailyNet)+t('/天','/day');
    const dailyChange=monthChangeV102(forecast.netNumerator,previousForecast.netNumerator,forecast.dailyNetDenominator,previousForecast.dailyNetDenominator);
    const dailyForecastCard=`<article data-overview-metric="dailyForecast"><span><span class="forecast-title">${t('预计 本月每日盈亏','Estimated daily profit/loss this month')}</span><small class="o30-kpi-formula">${t('(预计月底盈亏 ➗ 本月天数)','(Estimated month-end profit/loss ÷ days in the month)')}</small></span><strong class="${color(forecast.dailyNet)}">${dailyNetValue}</strong><small>${dailyChange}</small></article>`;
    $('o30Overview').innerHTML=`<div class="o30-section-line"><div><span class="o30-eyebrow">${t('月度经营概览','MONTHLY OVERVIEW')}</span><h2>${month} <span>${t('经营表现','Performance')}</span></h2></div><button type="button" class="soft" id="o30AnalyzeCosts">${t('分析本月费用','Analyze costs')} <span aria-hidden="true">↗</span></button></div><div class="o30-kpis"><article data-overview-metric="avgRevenue"><span>${t('日均收入','Average daily revenue')}</span><strong>${value(current.avgRevenue)}</strong><small>${monthChangeV102(current.avgRevenue,previous.avgRevenue)}</small></article><article data-overview-metric="avgGross"><span>${t('日均毛利润 (毛利率)','Average daily gross profit (Margin)')}</span><strong class="${color(current.avgGross)}">${gross}</strong><small>${monthChangeV102(current.avgGross,previous.avgGross)}</small></article><article data-overview-metric="forecast"><span>${forecastLabelV102("overview",forecast)}</span><strong class="${color(forecast.net)}">${value(forecast.net)}</strong><small>${monthChangeV102(forecast.net,previousForecast.net)}</small></article>${dailyForecastCard}<article data-overview-metric="net"><span>${t('净利润 (净利率)','Net profit (Margin)')}</span><strong class="${color(current.net)}">${netValue(current.net)}</strong><small>${monthChangeV102(current.net,previous.net)}</small></article></div><div class="o30-context"><span><i></i>${t('已录入','Recorded')} ${current.items.length} ${t('个营业日','operating days')} · ${t('所选日期','Selected date')} ${c.dateText}${forecast.closed?` · ${forecastNote}`:''}</span><span>${t('当日收入','Day revenue')} ${dayRowForDate(c.dateText)?money(c.day.revenue):t('未记录','No record')}</span></div>`;
    $('o30AnalyzeCosts').onclick=()=>window.Oct30Analytics?.open({month,view:'costs'});
    $('o30DashboardDetails').querySelector('summary').innerHTML=`<strong>${t('完整经营报表','Full financial reports')}</strong><span>${t('日 / 周 / 月 / 年 · 预测与全部指标','Day / week / month / year · forecasts and all metrics')}</span>`;
    syncForecastHelp();
    const subtitle=pageSubtitle();if(subtitle)subtitle.textContent=t('先看本月表现，再查看趋势、成本与具体来源。','Start with monthly performance, then inspect trends and costs.');
  }
  function pageSubtitle(){let p=$('pageOverview').querySelector('.page-title-row p');if(!p){p=document.createElement('p');$('pageOverview').querySelector('.page-title-row h1').after(p);}return p;}
  const base=renderDashboard;renderDashboard=function(...args){setup();const result=base.apply(this,args);summary();return result;};
  // Earlier handlers retain references to older wrappers. Schedule the final
  // responsive rendering after any of their date/filter handlers complete.
  ['selectedDate','selectedMonth','selectedYear'].forEach(id=>$(id)?.addEventListener('change',()=>setTimeout(summary,0)));
  // Expand keeps native responsive charts; no artificial chart padding/pan frame.
  const expandBase=toggleChartExpanded;toggleChartExpanded=function(button){const card=button.closest('.chart-card');if(!card?.querySelector('.o30-chart,.o30-facets'))return expandBase(button);const opening=!card.classList.contains('chart-expanded');closeExpandedCharts();if(opening){card.classList.add('chart-expanded','o30-expanded');document.body.classList.add('chart-modal-open');button.textContent=t('退出全屏','Exit full screen');button.focus();}};
  const bindBase=bindInteractiveChart;bindInteractiveChart=function(host){if(host.querySelector('.o30-svg'))return;return bindBase(host);};
  setup();if(state.token)renderDashboard();
  // An unchanged cloud snapshot skips dashboard rendering. Watch the local
  // calendar independently so an open page closes last month at midnight.
  function scheduleLocalMidnight(){
    const now=new Date();
    const midnight=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
    setTimeout(()=>{refreshCalendarBoundaryV102();scheduleLocalMidnight();},Math.max(1,midnight-now));
  }
  refreshCalendarBoundaryV102();scheduleLocalMidnight();setInterval(refreshCalendarBoundaryV102,5000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshCalendarBoundaryV102();});
})();
