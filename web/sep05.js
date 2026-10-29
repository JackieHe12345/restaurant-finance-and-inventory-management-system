/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

/* Sep05V1: cache-safe inventory consumption and desktop-quality dashboard line. */
(() => {
  function stockCategoryMaps(){
    const exact=new Map(),byName=new Map();
    for(const entry of inventoryEntries()){
      const name=String(Exact.or(()=>(entry.name), ()=>(""))).trim(),unit=String(Exact.or(()=>(entry.unit), ()=>(""))).trim(),category=(Exact.truth(Exact.seq(entry.category, "佐料")) ? "佐料" : "食材");
      if(Exact.truth(Exact.not(name)))continue;
      const exactKey=`${name}\u0000${unit}`,names=Exact.or(()=>(exact.get(exactKey)), ()=>(new Set())),named=Exact.or(()=>(byName.get(name)), ()=>(new Set()));
      names.add(category);named.add(category);exact.set(exactKey,names);byName.set(name,named);
    }
    return {exact,byName};
  }

  /* Every saved dish recipe is an outbound stock movement.  Use its exact
     name/unit to resolve ingredient versus seasoning; an ambiguous old recipe
     remains an ingredient rather than deducting two unrelated stock rows. */
  inventoryConsumption=function(){
    const used=new Map(),categories=stockCategoryMaps();
    for(const day of state.days){
      const date=String(Exact.or(()=>(day.日期), ()=>("")));const rows=Exact.or(()=>(dishData(date).rows), ()=>([]));
      for(const dish of rows)for(const item of parseDetailItems(dish.食材明细)){
        const name=String(Exact.or(()=>(item.name), ()=>(""))).trim(),quantity=num(item.quantity),unit=String(Exact.or(()=>(item.unit), ()=>(""))).trim();
        if(Exact.truth(Exact.or(()=>(Exact.not(name)), ()=>(Exact.not(quantity)))))continue;
        const matches=Exact.or(()=>(categories.exact.get(`${name}\u0000${unit}`)), ()=>(categories.byName.get(name)));
        const category=(Exact.truth(Exact.and(()=>(Exact.seq(matches?.size, 1)), ()=>(matches.has("佐料")))) ? "佐料" : "食材");
        const key=inventoryKey({category,name,unit}),row=Exact.or(()=>(used.get(key)), ()=>({quantity:0,lastDate:"",byDate:[]}));
        (row.quantity = Exact.add(row.quantity, quantity));row.lastDate=(Exact.truth(Exact.gt(date, row.lastDate)) ? date : row.lastDate);row.byDate.push({date,quantity});used.set(key,row);
      }
    }
    return used;
  };

  inventoryBalances=function(){
    const used=inventoryConsumption(),adjustments=inventoryAdjustmentRows(),overrides=inventoryOverrideRows(),latestOverrides=new Map(),entries=inventoryEntries(),balances=new Map();
    for(const item of overrides){const key=inventoryKey(item),previous=latestOverrides.get(key);if(Exact.truth(Exact.or(()=>(Exact.not(previous)), ()=>(Exact.gte(item.date, previous.date)))))latestOverrides.set(key,item);}
    const blank=item=>({category:item.category,name:item.name,unit:item.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null});
    for(const entry of entries){const key=inventoryKey(entry),row=Exact.or(()=>(balances.get(key)), ()=>(blank(entry)));(row.received = Exact.add(row.received, entry.quantity));(row.receivedValue = Exact.add(row.receivedValue, Exact.or(()=>(entry.total), ()=>(Exact.mul(entry.quantity, entry.unitPrice)))));row.lastDate=(Exact.truth(Exact.gt(entry.date, row.lastDate)) ? entry.date : row.lastDate);balances.set(key,row);}
    for(const [key,value] of used){const row=balances.get(key);if(Exact.truth(row))row.used=value.quantity;}
    for(const item of adjustments){const key=inventoryKey(item),row=Exact.or(()=>(balances.get(key)), ()=>(blank(item)));if(Exact.truth(Exact.gt(item.quantity, 0))){(row.manualUsed = Exact.add(row.manualUsed, item.quantity));if(Exact.truth(Exact.seq(item.kind, "loss")))(row.loss = Exact.add(row.loss, item.quantity));else (row.normalUsed = Exact.add(row.normalUsed, item.quantity));}balances.set(key,row);}
    for(const [key,item] of latestOverrides){const row=Exact.or(()=>(balances.get(key)), ()=>(blank(item)));row.override=item;balances.set(key,row);}
    return [...balances.values()].map(row=>{
      const cutoff=Exact.or(()=>(row.override?.date), ()=>("")),key=inventoryKey(row);
      const futureReceived=(Exact.truth(cutoff) ? entries.filter(item=>Exact.and(()=>(Exact.seq(inventoryKey(item), key)), ()=>(Exact.gt(item.date, cutoff)))).reduce((sum,item)=>Exact.add(sum, item.quantity),0) : 0);
      const futureUsed=(Exact.truth(cutoff) ? (Exact.or(()=>(used.get(key)?.byDate), ()=>([]))).filter(item=>Exact.gt(item.date, cutoff)).reduce((sum,item)=>Exact.add(sum, item.quantity),0) : 0);
      const futureManual=(Exact.truth(cutoff) ? adjustments.filter(item=>Exact.and(()=>(Exact.seq(inventoryKey(item), key)), ()=>(Exact.gt(item.date, cutoff)))).reduce((sum,item)=>Exact.add(sum, Exact.math.max(0,item.quantity)),0) : 0);
      const remaining=(Exact.truth(row.override) ? Exact.sub(Exact.sub(Exact.add(row.override.quantity, futureReceived), futureUsed), futureManual) : Exact.sub(Exact.sub(row.received, row.used), row.manualUsed));
      return {...row,remaining,overridden:Boolean(row.override)};
    }).sort(Exact.sortComparator((a,b)=>Exact.or(()=>(Exact.or(()=>(a.category.localeCompare(b.category,"zh-CN")), ()=>(a.name.localeCompare(b.name,"zh-CN")))), ()=>(a.unit.localeCompare(b.unit,"zh-CN")))));
  };

  function dashboardLineSvg(points,key){
    const width=Exact.math.max(1180,Exact.add(Exact.mul(points.length, 46), 120)),height=390,pad={l:74,r:34,t:38,b:62},values=points.map(point=>point.value);
    const rawMin=Exact.math.min(0,...values),rawMax=Exact.math.max(0,...values),padding=Exact.math.max(1,Exact.mul(Exact.or(()=>(Exact.sub(rawMax, rawMin)), ()=>(1)), 0.12)),min=Exact.sub(rawMin, padding),max=Exact.add(rawMax, padding),range=Exact.or(()=>(Exact.sub(max, min)), ()=>(1));
    const x=index=>Exact.add(pad.l, Exact.div(Exact.mul(index, Exact.sub(Exact.sub(width, pad.l), pad.r)), Exact.math.max(1,Exact.sub(points.length, 1)))),y=value=>Exact.add(pad.t, Exact.mul(Exact.div(Exact.sub(max, value), range), Exact.sub(Exact.sub(height, pad.t), pad.b))),zero=y(0);
    const path=points.map((point,index)=>`${(Exact.truth(index) ? "L" : "M")}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
    const area=`${path} L${x(Exact.sub(points.length, 1)).toFixed(1)},${zero.toFixed(1)} L${x(0).toFixed(1)},${zero.toFixed(1)} Z`;
    const grid=Array.from({length:5},(_,index)=>{const value=Exact.sub(max, Exact.div(Exact.mul(range, index), 4)),py=y(value);return `<g><line class="sep05-grid" x1="${pad.l}" x2="${Exact.sub(width, pad.r)}" y1="${py}" y2="${py}"/><text class="sep05-y-label" x="${Exact.sub(pad.l, 12)}" y="${Exact.add(py, 4)}" text-anchor="end">${compactNumber(value)}</text></g>`;}).join("");
    const dots=points.map((point,index)=>{
      const px=x(index),py=y(point.value),label=pointValue(key,point.value,point.revenue),day=String(Exact.toNumber(point.date.slice(8)));
      const labelY=(Exact.truth(Exact.gte(point.value, 0)) ? Exact.sub(py, 13) : Exact.add(py, 23));
      return `<g class="sep05-point" data-chart-point data-tooltip="${escapeHtml(point.date)}&#10;${escapeHtml(label)}" tabindex="0"><circle class="sep05-point-halo" cx="${px}" cy="${py}" r="9"/><circle class="sep05-point-dot" cx="${px}" cy="${py}" r="4.8"/><text class="sep05-value" x="${px}" y="${labelY}" text-anchor="middle">${escapeHtml(label)}</text><text class="sep05-x-label" x="${px}" y="${Exact.sub(height, 20)}" text-anchor="middle">${day}</text></g>`;
    }).join("");
    return `<svg class="sep05-dashboard-svg" style="width:${width}px" viewBox="0 0 ${width} ${height}" role="img" aria-label="本月每日趋势"><defs><linearGradient id="sep05TrendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0baac6" stop-opacity=".28"/><stop offset="1" stop-color="#0baac6" stop-opacity=".02"/></linearGradient><filter id="sep05Shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#087fa2" flood-opacity=".25"/></filter></defs>${grid}<line class="sep05-zero" x1="${pad.l}" x2="${Exact.sub(width, pad.r)}" y1="${zero}" y2="${zero}"/><path class="sep05-area" d="${area}"/><path class="sep05-line" d="${path}" filter="url(#sep05Shadow)"/>${dots}</svg>`;
  }

  fitDashboardMonthChart=function(){
    if(Exact.truth(Exact.or(()=>(Exact.not($("trendChart"))), ()=>(Exact.not($("selectedYear")?.value)))))return;
    const year=Exact.toNumber($("selectedYear").value),month=Exact.toNumber($("selectedMonth").value),key=$("trendMetric").value,monthPrefix=`${year}-${String(month).padStart(2,"0")}`;
    const lookup=new Map(state.days.filter(row=>String(row.日期).startsWith(monthPrefix)).map(row=>[Exact.toNumber(String(row.日期).slice(8)),dayMetrics(row)])),points=[];
    for(let day=1;Exact.truth(Exact.lte(day, daysInMonth(year,month)));day++){
      const metric=lookup.get(day),value=(Exact.truth(metric) ? (Exact.truth(Exact.seq(key, "revenue")) ? metric.revenue : (Exact.truth(Exact.seq(key, "food")) ? Exact.add(metric.food, metric.spice) : (Exact.truth(Exact.seq(key, "gross")) ? metric.gross : metric.net))) : 0);
      points.push({date:`${monthPrefix}-${String(day).padStart(2,"0")}`,value,revenue:Exact.or(()=>(metric?.revenue), ()=>(0))});
    }
    const chart=$("trendChart");chart.classList.add("fit-month-chart","sep05-chart-ready");chart.innerHTML=dashboardLineSvg(points,key);bindInteractiveChart(chart);
    const hint=chart.parentElement.querySelector(".chart-hint");if(Exact.truth(hint))hint.textContent=`整月 1–${points.length} 日；悬停或点按查看。图表与桌面端使用同样的“每日趋势”口径。`;
  };

  if(Exact.truth(state.token)){
    renderDashboard();
    if(Exact.truth($("inventoryBalanceGrid")))renderInventoryBalance();
  }
})();
