/* v1.0.2: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";
/* Responsive reporting charts. Decimal values remain exact in text; only
 * coordinates are converted to Number. Missing observations stay missing. */
(() => {
  const palette=['#2563a6','#0f8a7c','#d08b28','#8b65bd','#de5960','#527487'];
  const en=()=>Exact.seq(state.language, 'en'),esc=value=>escapeHtml(String(value??''));
  const number=value=>(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.seq(value, null)), ()=>(Exact.seq(value, undefined)))), ()=>(Exact.seq(value, '')))) ? null : Exact.toNumber(value));
  function axis(value){const a=Exact.math.abs(value),scale=(Exact.truth(en()) ? (Exact.truth(Exact.gte(a, 1000000000)) ? 1000000000 : (Exact.truth(Exact.gte(a, 1000000)) ? 1000000 : (Exact.truth(Exact.gte(a, 1000)) ? 1000 : 1))) : (Exact.truth(Exact.gte(a, 100000000)) ? 100000000 : (Exact.truth(Exact.gte(a, 10000)) ? 10000 : 1))),suffix=(Exact.truth(en()) ? (Exact.truth(Exact.seq(scale, 1000000000)) ? 'B' : (Exact.truth(Exact.seq(scale, 1000000)) ? 'M' : (Exact.truth(Exact.seq(scale, 1000)) ? 'K' : ''))) : (Exact.truth(Exact.seq(scale, 100000000)) ? '亿' : (Exact.truth(Exact.seq(scale, 10000)) ? '万' : '')));return Exact.add((Exact.div(value, scale)).toLocaleString((Exact.truth(en()) ? 'en-US' : 'zh-CN'),{maximumFractionDigits:(Exact.truth(Exact.seq(scale, 1)) ? (Exact.truth(Exact.lt(a, 10)) ? 2 : 0) : 1)}), suffix);}
  function domain(values){let min=Exact.math.min(0,...values),max=Exact.math.max(0,...values);if(Exact.truth(Exact.seq(min, max)))max=Exact.add(min, 1);const raw=Exact.div(Exact.sub(max, min), 4),power=Exact.pow(10, Exact.math.floor(Math.log10(raw))),fraction=Exact.div(raw, power),step=Exact.mul((Exact.truth(Exact.lte(fraction, 1)) ? 1 : (Exact.truth(Exact.lte(fraction, 2)) ? 2 : (Exact.truth(Exact.lte(fraction, 5)) ? 5 : 10))), power);return {min:Exact.mul(Exact.math.floor(Exact.div(min, step)), step),max:Exact.mul(Exact.math.ceil(Exact.div(max, step)), step),step};}
  let measurementContext;
  function labelWidth(text){
    if(Exact.truth(Exact.seq(measurementContext, undefined))){try{measurementContext=(Exact.truth(Exact.seq(typeof document, 'undefined')) ? null : document.createElement('canvas').getContext('2d'));}catch(_){measurementContext=null;}}
    if(Exact.truth(measurementContext)){measurementContext.font='11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';return Exact.add(measurementContext.measureText(String(text)).width, 2);}
    // Conservative fallback also keeps server-side/static previews readable.
    return Exact.add(Array.from(String(text)).reduce((total,char)=>Exact.add(total, (Exact.truth(/[^\x00-\x7f]/.test(char)) ? 12 : (Exact.truth(/[MW@#]/.test(char)) ? 10 : 7))),0), 2);
  }
  function compactLabels(labels){
    const text=labels.map(String),dates=text.every(s=>/^\d{4}-\d{2}-\d{2}$/.test(s)),months=text.every(s=>/^\d{4}-\d{2}$/.test(s)),sameYear=Exact.seq(new Set(text.map(s=>s.slice(0,4))).size, 1);
    if(Exact.truth(Exact.and(()=>(dates), ()=>(sameYear))))return {temporal:true,labels:text.map(s=>`${Exact.toNumber(s.slice(5,7))}/${Exact.toNumber(s.slice(8,10))}`)};
    if(Exact.truth(Exact.and(()=>(months), ()=>(sameYear)))){const names=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return {temporal:true,labels:text.map(s=>(Exact.truth(en()) ? names[Exact.sub(Exact.toNumber(s.slice(5,7)), 1)] : `${Exact.toNumber(s.slice(5,7))}月`))};}
    return {temporal:Exact.or(()=>(Exact.or(()=>(dates), ()=>(months))), ()=>(text.every(s=>/^\d{1,2}[-/]\d{1,2}$/.test(s)))),labels:text};
  }
  function wrapLabel(label,maxWidth){
    const lines=[];let line='';
    for(const word of String(label).split(/(\s+)/).filter(Exact.truth)){
      if(Exact.truth(Exact.lte(labelWidth(Exact.add(line, word)), maxWidth))){(line = Exact.add(line, word));continue;}
      if(Exact.truth(line.trim())){lines.push(line.trim());line='';}
      if(Exact.truth(Exact.not(word.trim())))continue;
      for(const char of Array.from(word)){if(Exact.truth(Exact.and(()=>(line), ()=>(Exact.gt(labelWidth(Exact.add(line, char)), maxWidth))))){lines.push(line);line='';}(line = Exact.add(line, char));}
    }
    if(Exact.truth(line.trim()))lines.push(line.trim());return (Exact.truth(lines.length) ? lines : ['']);
  }
  function xAxisLayout(labels,width,pad,bar){
    const pw=Exact.sub(Exact.sub(width, pad.l), pad.r),slot=Exact.div(pw, Exact.math.max(1,(Exact.truth(bar) ? labels.length : Exact.sub(labels.length, 1)))),short=compactLabels(labels),wrap=Exact.not(short.temporal),
      x=i=>(Exact.truth(bar) ? Exact.add(pad.l, Exact.mul(slot, Exact.add(i, .5))) : Exact.add(pad.l, (Exact.truth(Exact.seq(labels.length, 1)) ? Exact.div(pw, 2) : Exact.mul(i, slot)))),
      candidates=short.labels.map((label,i)=>{const lines=(Exact.truth(wrap) ? wrapLabel(label,(Exact.truth(Exact.lte(labels.length, 12)) ? Exact.math.max(22,Exact.sub(slot, 12)) : Exact.math.min(110,pw))) : [label]),w=Exact.math.min(pw,Exact.math.max(...lines.map(labelWidth))),center=Exact.math.max(Exact.add(pad.l, Exact.div(w, 2)),Exact.math.min(Exact.sub(Exact.sub(width, pad.r), Exact.div(w, 2)),x(i)));return {i,lines,x:center,left:Exact.sub(center, Exact.div(w, 2)),right:Exact.add(center, Exact.div(w, 2))};}),
      selected=[],last=candidates[Exact.sub(candidates.length, 1)],gap=9;
    // Reserve the final label before choosing intermediate ticks. Simply
    // appending the last tick after a fixed interval caused 10/11/12 overlap.
    for(const item of candidates){if(Exact.truth(Exact.and(()=>(selected.length), ()=>(Exact.lt(item.left, Exact.add(selected[Exact.sub(selected.length, 1)].right, gap))))))continue;if(Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.sneq(item, last)), ()=>(Exact.sneq(item.i, 0)))), ()=>(Exact.gt(Exact.add(item.right, gap), last.left)))))continue;selected.push(item);}
    return {ticks:selected,bottom:Exact.math.max(34,Exact.add(Exact.mul(Exact.math.max(...selected.map(t=>t.lines.length)), 14), 17))};
  }
  function markup(options,width){
    const labels=Exact.or(()=>(options.labels), ()=>([])),series=Exact.or(()=>(options.series), ()=>([])),height=Exact.or(()=>(options.height), ()=>(280)),pad={l:(Exact.truth(Exact.lt(width, 400)) ? 46 : 58),r:18,t:18,b:34};
    const numeric=series.flatMap(s=>s.values.map(number)).filter(v=>Exact.and(()=>(Exact.sneq(v, null)), ()=>(Exact.finite(v))));
    if(Exact.truth(Exact.or(()=>(Exact.not(labels.length)), ()=>(Exact.not(numeric.length)))))return `<div class="o30-empty">${esc(Exact.or(()=>(options.emptyText), ()=>((Exact.truth(en()) ? 'No records in this period' : '这段时间还没有记录'))))}<small>${(Exact.truth(en()) ? 'Choose another period or enter records.' : '可切换月份，或录入后再查看。')}</small></div>`;
    const bar=Exact.seq(options.kind, 'bar'),layout=xAxisLayout(labels,width,pad,bar);pad.b=layout.bottom;
    const chartHeight=Exact.math.max(height,Exact.add(Exact.add(pad.t, pad.b), 140)),d=domain(numeric),pw=Exact.sub(Exact.sub(width, pad.l), pad.r),ph=Exact.sub(Exact.sub(chartHeight, pad.t), pad.b),slot=Exact.div(pw, Exact.math.max(1,labels.length)),x=i=>(Exact.truth(bar) ? Exact.add(pad.l, Exact.mul(slot, Exact.add(i, .5))) : Exact.add(pad.l, (Exact.truth(Exact.seq(labels.length, 1)) ? Exact.div(pw, 2) : Exact.div(Exact.mul(i, pw), Exact.sub(labels.length, 1))))),y=v=>Exact.add(pad.t, Exact.mul(Exact.div(Exact.sub(d.max, v), Exact.sub(d.max, d.min)), ph));
    const grid=[];for(let v=d.min,i=0;Exact.truth(Exact.and(()=>(Exact.lte(i, 10)), ()=>(Exact.lte(v, Exact.add(d.max, Exact.mul(d.step, .01))))));(v = Exact.add(v, d.step)),i++){const py=y(v);grid.push(`<line x1="${pad.l}" x2="${Exact.sub(width, pad.r)}" y1="${py}" y2="${py}" class="${(Exact.truth(Exact.lt(Exact.math.abs(v), Exact.mul(d.step, .001))) ? 'o30-zero' : 'o30-grid')}"/><text x="${Exact.sub(pad.l, 9)}" y="${Exact.add(py, 4)}" text-anchor="end" class="o30-axis">${esc(axis(v))}</text>`);}
    const ticks=layout.ticks.map(t=>`<text x="${t.x}" y="${Exact.add(Exact.sub(chartHeight, pad.b), 20)}" text-anchor="middle" class="o30-axis o30-x-axis" data-o30-tick-index="${t.i}">${t.lines.map((line,i)=>`<tspan x="${t.x}" dy="${(Exact.truth(i) ? 14 : 0)}">${esc(line)}</tspan>`).join('')}</text>`).join('');
    const plots=series.map((s,si)=>{const color=Exact.or(()=>(s.color), ()=>(palette[Exact.mod(si, palette.length)])),coords=s.values.map((v,i)=>({i,raw:v,v:number(v)}));let path='',connected=false;
      if(Exact.truth(bar)){const bw=Exact.math.max(1,Exact.math.min(30,Exact.div(Exact.mul(slot, .66), Exact.math.max(1,series.length))));return coords.map(p=>(Exact.truth(Exact.seq(p.v, null)) ? '' : `<rect x="${Exact.add(x(p.i), Exact.mul(Exact.sub(si, Exact.div(series.length, 2)), bw))}" y="${Exact.math.min(y(p.v),y(0))}" width="${Exact.math.max(1,Exact.sub(bw, 2))}" height="${Exact.math.max(0,Exact.math.abs(Exact.sub(y(p.v), y(0))))}" rx="2" fill="${color}" opacity=".9"/>`)).join('');}
      coords.forEach(p=>{if(Exact.truth(Exact.seq(p.v, null))){connected=false;return;}(path = Exact.add(path, `${(Exact.truth(connected) ? 'L' : 'M')}${x(p.i)},${y(p.v)} `));connected=true;});
      return Exact.add(`<path d="${path}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`, coords.map(p=>(Exact.truth(Exact.seq(p.v, null)) ? '' : `<circle cx="${x(p.i)}" cy="${y(p.v)}" r="${(Exact.truth(Exact.gt(labels.length, 60)) ? 1.5 : 3)}" fill="${color}" stroke="white" stroke-width="1.4"/>`)).join(''));
    }).join('');
    const hits=labels.map((label,i)=>{const left=(Exact.truth(bar) ? Exact.add(pad.l, Exact.mul(i, slot)) : Exact.math.max(pad.l,Exact.sub(x(i), Exact.div(Exact.div(pw, Exact.math.max(1,Exact.sub(labels.length, 1))), 2)))),right=(Exact.truth(bar) ? Exact.add(left, slot) : Exact.math.min(Exact.sub(width, pad.r),Exact.add(x(i), Exact.div(Exact.div(pw, Exact.math.max(1,Exact.sub(labels.length, 1))), 2)))),fmt=Exact.or(()=>(options.format), ()=>((v)=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:2})));const detail=[label,...series.map((s,si)=>`${s.name}: ${(Exact.truth(Exact.or(()=>(Exact.seq(s.values[i], null)), ()=>(Exact.seq(s.values[i], undefined)))) ? (Exact.truth(en()) ? 'No record' : '未记录') : fmt(s.values[i],s,si,i))}`)].join('\n');return `<g ${(Exact.truth(Exact.or(()=>(series.some(s=>s.userContent)), ()=>(options.userLabels))) ? 'data-user-content' : '')} data-o30-index="${i}" data-chart-point data-tooltip="${esc(detail)}" tabindex="${(Exact.truth(Exact.seq(i, 0)) ? '0' : '-1')}" role="button" aria-label="${esc(detail)}"><rect x="${left}" y="${pad.t}" width="${Exact.math.max(1,Exact.sub(right, left))}" height="${ph}" fill="transparent"/><line class="o30-focus-line" x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${Exact.sub(chartHeight, pad.b)}"/></g>`;}).join('');
    return `<div class="o30-legend">${series.map((s,i)=>`<span ${(Exact.truth(s.userContent) ? 'data-user-content' : '')}><i style="background:${Exact.or(()=>(s.color), ()=>(palette[Exact.mod(i, palette.length)]))}"></i>${esc(s.name)}</span>`).join('')}</div><svg class="o30-svg" width="${width}" height="${chartHeight}" viewBox="0 0 ${width} ${chartHeight}" role="group" aria-label="${esc(Exact.or(()=>(options.title), ()=>((Exact.truth(en()) ? 'Interactive chart' : '交互数据图表'))))}">${grid.join('')}${plots}${ticks}${hits}</svg><div class="o30-readout" ${(Exact.truth(Exact.or(()=>(series.some(s=>s.userContent)), ()=>(options.userLabels))) ? 'data-user-content' : '')} aria-live="polite">${(Exact.truth(en()) ? 'Tap a date or category, or use arrow keys to inspect values' : '点按日期或类别查看数值，也可用方向键逐项查看')}</div>`;
  }
  function bind(host){
    const nodes=[...host.querySelectorAll('[data-o30-index]')],readout=host.querySelector('.o30-readout');
    function inspect(node){if(Exact.truth(Exact.not(node)))return;nodes.forEach(n=>{n.classList.toggle('o30-selected',Exact.seq(n, node));n.tabIndex=(Exact.truth(Exact.seq(n, node)) ? 0 : Exact.neg(1));});if(Exact.truth(readout))readout.textContent=node.dataset.tooltip.replace(/\n/g,'  ·  ');}
    host.onpointermove=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.onclick=e=>inspect(e.target.closest?.('[data-o30-index]'));
    if(Exact.truth(host._o30FocusHandler))host.removeEventListener('focusin',host._o30FocusHandler);
    host._o30FocusHandler=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.addEventListener('focusin',host._o30FocusHandler);
    host.onkeydown=e=>{const n=e.target.closest?.('[data-o30-index]');if(Exact.truth(Exact.not(n)))return;let index=nodes.indexOf(n);if(Exact.truth(Exact.seq(e.key, 'ArrowRight')))index++;else if(Exact.truth(Exact.seq(e.key, 'ArrowLeft')))index--;else if(Exact.truth(Exact.seq(e.key, 'Home')))index=0;else if(Exact.truth(Exact.seq(e.key, 'End')))index=Exact.sub(nodes.length, 1);else return;e.preventDefault();const target=nodes[Exact.math.max(0,Exact.math.min(Exact.sub(nodes.length, 1),index))];inspect(target);target?.focus();};
  }
  function render(host,options){if(Exact.truth(Exact.not(host)))return;host._o30Options=options;host.classList.add('o30-chart');host.classList.remove('business-grouped-chart','sep05-chart-ready','fit-month-chart');host.style.removeProperty('min-width');host.style.removeProperty('height');host.style.width='100%';
    const draw=()=>{const width=Exact.math.max(220,Exact.math.floor(Exact.or(()=>(Exact.or(()=>(host.getBoundingClientRect().width), ()=>(host.parentElement?.clientWidth))), ()=>(600))));host._o30Width=width;host.innerHTML=markup(host._o30Options,width);bind(host);};draw();
    if(Exact.truth(Exact.and(()=>(Exact.not(host._o30Observer)), ()=>(Exact.sneq(typeof ResizeObserver, 'undefined'))))){host._o30Observer=new ResizeObserver(()=>{const w=Exact.math.floor(host.getBoundingClientRect().width);if(Exact.truth(Exact.and(()=>(Exact.gt(w, 0)), ()=>(Exact.sneq(w, host._o30Width)))))draw();});host._o30Observer.observe(host);}
  }
  window.Oct30Charts={render,markup,palette};
  // All legacy analysis views share the same chart language. Separate units
  // have separate axes rather than combining people, percentages and money.
  const unit=key=>(Exact.truth(['grossRate','netRate','newRatio','oldRatio'].includes(key)) ? 'rate' : (Exact.truth(['customers','newCustomers','oldCustomers'].includes(key)) ? 'count' : 'money'));
  function businessChart(host,groups,keys,average,kind){host.innerHTML='';host._o30Options=null;host._o30Observer?.disconnect();host._o30Observer=null;host.classList.add('o30-facets');host.classList.remove('o30-chart','business-grouped-chart');host.style.height='auto';
    for(const type of [...new Set(keys.map(unit))]){const chosen=keys.filter(k=>Exact.seq(unit(k), type)),facet=document.createElement('div');host.appendChild(facet);render(facet,{labels:groups.map(g=>g.label),kind,series:chosen.map((key,i)=>({name:proBusinessMetricLabel(key),color:palette[Exact.mod(i, palette.length)],values:groups.map(g=>{const explicit=g.values?.find(v=>Exact.seq(v.key, key));return (Exact.truth(explicit) ? explicit.value : (Exact.truth(g.list?.length) ? proBusinessGroupValue(g.list,key,average).value : null));})})),format:v=>(Exact.truth(Exact.seq(type, 'rate')) ? `${Exact.decimal(v).toFixed(1)}%` : (Exact.truth(Exact.seq(type, 'count')) ? Exact.decimal(v).toLocaleString() : money(v)))});}
  }
  proBusinessGroupedBars=function(node,groups,keys,average){businessChart(node,groups,keys,average,'bar');};
  const businessBase=renderBusinessStats;renderBusinessStats=function(){businessBase();businessChart($('statsChart'),proBusinessTrendGroups(filteredStatsItems(),proBusinessModeAverage()),selectedProMetrics(),proBusinessModeAverage(),'line');};
  renderIngredientGroupedCharts=function(rows,purchase,metric,value){
    const hosts=['statsChart','statsMonthlyChart','statsWeekdayChart'].map($);
    hosts.forEach(host=>{host.innerHTML='';host._o30Options=null;host._o30Observer?.disconnect();host._o30Observer=null;host.classList.add('o30-facets');host.classList.remove('o30-chart');host.style.height='auto';});
    const groups=ingredientSeriesGroups(rows),format=v=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:3});
    if(Exact.truth(Exact.not(groups.length))){hosts.forEach(host=>render(host,{labels:[],series:[]}));return;}
    for(const group of groups){
      const first=group[0],emptyText=(Exact.truth(Exact.and(()=>(purchase), ()=>(Exact.not(group.some(row=>entered(row.total)))))) ? (Exact.truth(en()) ? 'Selected records are not priced yet' : '所选记录尚未定价') : ''),unknown=ingredientAggregate(group).unknownQuantity,name=`${first.name}（${(Exact.truth(first.unit) ? (Exact.truth(Exact.seq(typeof v8DisplayUnit, 'function')) ? v8DisplayUnit(first.unit) : first.unit) : (Exact.truth(en()) ? 'No unit' : '无单位'))}）${(Exact.truth(Exact.and(()=>(Exact.and(()=>(purchase), ()=>(unknown))), ()=>(Exact.or(()=>(Exact.seq(metric, 'unit')), ()=>(Exact.seq(metric, 'monthlyAverageUnit')))))) ? (Exact.truth(en()) ? ' · unit price uses priced quantities only' : ' · 单价仅计已定价数量') : '')}`,panels=hosts.map(host=>{const panel=document.createElement('div');host.appendChild(panel);return panel;});
      let points=aggregateByDate(group,value);
      if(Exact.truth(Exact.and(()=>(Exact.not(purchase)), ()=>(Exact.seq(metric, 'cumulative'))))){let running=0;points=points.map(point=>({...point,value:((running = Exact.add(running, point.value)))}));}
      render(panels[0],{labels:points.map(p=>p.date.slice(5)),series:[{name,userContent:true,values:points.map(p=>p.value)}],format,emptyText});
      const monthly=aggregateByMonth(group,item=>(Exact.truth(purchase) ? value(item) : (Exact.truth(Exact.seq(metric, 'monthlyAverage')) ? (Exact.truth(item.days) ? Exact.div(item.quantity, item.days) : 0) : item.quantity)));
      render(panels[1],{labels:monthly.map((p,i)=>(Exact.truth(en()) ? ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i] : p.label)),kind:'bar',series:[{name,userContent:true,values:monthly.map(p=>p.value)}],format,emptyText});
      const labels=(Exact.truth(en()) ? ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] : ['周一','周二','周三','周四','周五','周六','周日']),week=labels.map(()=>[]);group.forEach(row=>week[Exact.mod(Exact.add(parseDate(row.date).getDay(), 6), 7)].push(row));
      const values=week.map(list=>{if(Exact.truth(Exact.not(list.length)))return null;const aggregate=ingredientAggregate(list),{quantity,days}=aggregate;return (Exact.truth(purchase) ? value(aggregate) : Exact.div(quantity, days));});
      render(panels[2],{labels,kind:'bar',series:[{name,userContent:true,values}],format,emptyText});
    }
  };
})();
