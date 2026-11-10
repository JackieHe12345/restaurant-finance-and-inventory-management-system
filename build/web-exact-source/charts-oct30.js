"use strict";
/* Responsive reporting charts. Decimal values remain exact in text; only
 * coordinates are converted to Number. Missing observations stay missing. */
(() => {
  const palette=['#2563a6','#0f8a7c','#d08b28','#8b65bd','#de5960','#527487'];
  const en=()=>state.language==='en',esc=value=>escapeHtml(String(value??''));
  const number=value=>value===null||value===undefined||value===''?null:Exact.toNumber(value);
  function axis(value){const a=Math.abs(value),scale=en()?(a>=1000000000?1000000000:a>=1000000?1000000:a>=1000?1000:1):(a>=100000000?100000000:a>=10000?10000:1),suffix=en()?(scale===1000000000?'B':scale===1000000?'M':scale===1000?'K':''):(scale===100000000?'亿':scale===10000?'万':'');return (value/scale).toLocaleString(en()?'en-US':'zh-CN',{maximumFractionDigits:scale===1?(a<10?2:0):1})+suffix;}
  function domain(values){let min=Math.min(0,...values),max=Math.max(0,...values);if(min===max)max=min+1;const raw=(max-min)/4,power=10**Math.floor(Math.log10(raw)),fraction=raw/power,step=(fraction<=1?1:fraction<=2?2:fraction<=5?5:10)*power;return {min:Math.floor(min/step)*step,max:Math.ceil(max/step)*step,step};}
  let measurementContext;
  function labelWidth(text){
    if(measurementContext===undefined){try{measurementContext=typeof document==='undefined'?null:document.createElement('canvas').getContext('2d');}catch(_){measurementContext=null;}}
    if(measurementContext){measurementContext.font='11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';return measurementContext.measureText(String(text)).width+2;}
    // Conservative fallback also keeps server-side/static previews readable.
    return Array.from(String(text)).reduce((total,char)=>total+(/[^\x00-\x7f]/.test(char)?12:/[MW@#]/.test(char)?10:7),0)+2;
  }
  function compactLabels(labels){
    const text=labels.map(String),dates=text.every(s=>/^\d{4}-\d{2}-\d{2}$/.test(s)),months=text.every(s=>/^\d{4}-\d{2}$/.test(s)),sameYear=new Set(text.map(s=>s.slice(0,4))).size===1;
    if(dates&&sameYear)return {temporal:true,labels:text.map(s=>`${Number(s.slice(5,7))}/${Number(s.slice(8,10))}`)};
    if(months&&sameYear){const names=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];return {temporal:true,labels:text.map(s=>en()?names[Number(s.slice(5,7))-1]:`${Number(s.slice(5,7))}月`)};}
    return {temporal:dates||months||text.every(s=>/^\d{1,2}[-/]\d{1,2}$/.test(s)),labels:text};
  }
  function wrapLabel(label,maxWidth){
    const lines=[];let line='';
    for(const word of String(label).split(/(\s+)/).filter(Boolean)){
      if(labelWidth(line+word)<=maxWidth){line+=word;continue;}
      if(line.trim()){lines.push(line.trim());line='';}
      if(!word.trim())continue;
      for(const char of Array.from(word)){if(line&&labelWidth(line+char)>maxWidth){lines.push(line);line='';}line+=char;}
    }
    if(line.trim())lines.push(line.trim());return lines.length?lines:[''];
  }
  function xAxisLayout(labels,width,pad,bar){
    const pw=width-pad.l-pad.r,slot=pw/Math.max(1,bar?labels.length:labels.length-1),short=compactLabels(labels),wrap=!short.temporal,
      x=i=>bar?pad.l+slot*(i+.5):pad.l+(labels.length===1?pw/2:i*slot),
      candidates=short.labels.map((label,i)=>{const lines=wrap?wrapLabel(label,labels.length<=12?Math.max(22,slot-12):Math.min(110,pw)):[label],w=Math.min(pw,Math.max(...lines.map(labelWidth))),center=Math.max(pad.l+w/2,Math.min(width-pad.r-w/2,x(i)));return {i,lines,x:center,left:center-w/2,right:center+w/2};}),
      selected=[],last=candidates[candidates.length-1],gap=9;
    // Reserve the final label before choosing intermediate ticks. Simply
    // appending the last tick after a fixed interval caused 10/11/12 overlap.
    for(const item of candidates){if(selected.length&&item.left<selected[selected.length-1].right+gap)continue;if(item!==last&&item.i!==0&&item.right+gap>last.left)continue;selected.push(item);}
    return {ticks:selected,bottom:Math.max(34,Math.max(...selected.map(t=>t.lines.length))*14+17)};
  }
  function markup(options,width){
    const labels=options.labels||[],series=options.series||[],height=options.height||280,pad={l:width<400?46:58,r:18,t:18,b:34};
    const numeric=series.flatMap(s=>s.values.map(number)).filter(v=>v!==null&&Number.isFinite(v));
    if(!labels.length||!numeric.length)return `<div class="o30-empty">${esc(options.emptyText||(en()?'No records in this period':'这段时间还没有记录'))}<small>${en()?'Choose another period or enter records.':'可切换月份，或录入后再查看。'}</small></div>`;
    const bar=options.kind==='bar',layout=xAxisLayout(labels,width,pad,bar);pad.b=layout.bottom;
    const chartHeight=Math.max(height,pad.t+pad.b+140),d=domain(numeric),pw=width-pad.l-pad.r,ph=chartHeight-pad.t-pad.b,slot=pw/Math.max(1,labels.length),x=i=>bar?pad.l+slot*(i+.5):pad.l+(labels.length===1?pw/2:i*pw/(labels.length-1)),y=v=>pad.t+(d.max-v)/(d.max-d.min)*ph;
    const grid=[];for(let v=d.min,i=0;i<=10&&v<=d.max+d.step*.01;v+=d.step,i++){const py=y(v);grid.push(`<line x1="${pad.l}" x2="${width-pad.r}" y1="${py}" y2="${py}" class="${Math.abs(v)<d.step*.001?'o30-zero':'o30-grid'}"/><text x="${pad.l-9}" y="${py+4}" text-anchor="end" class="o30-axis">${esc(axis(v))}</text>`);}
    const ticks=layout.ticks.map(t=>`<text x="${t.x}" y="${chartHeight-pad.b+20}" text-anchor="middle" class="o30-axis o30-x-axis" data-o30-tick-index="${t.i}">${t.lines.map((line,i)=>`<tspan x="${t.x}" dy="${i?14:0}">${esc(line)}</tspan>`).join('')}</text>`).join('');
    const plots=series.map((s,si)=>{const color=s.color||palette[si%palette.length],coords=s.values.map((v,i)=>({i,raw:v,v:number(v)}));let path='',connected=false;
      if(bar){const bw=Math.max(1,Math.min(30,slot*.66/Math.max(1,series.length)));return coords.map(p=>p.v===null?'':`<rect x="${x(p.i)+(si-series.length/2)*bw}" y="${Math.min(y(p.v),y(0))}" width="${Math.max(1,bw-2)}" height="${Math.max(0,Math.abs(y(p.v)-y(0)))}" rx="2" fill="${color}" opacity=".9"/>`).join('');}
      coords.forEach(p=>{if(p.v===null){connected=false;return;}path+=`${connected?'L':'M'}${x(p.i)},${y(p.v)} `;connected=true;});
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`+coords.map(p=>p.v===null?'':`<circle cx="${x(p.i)}" cy="${y(p.v)}" r="${labels.length>60?1.5:3}" fill="${color}" stroke="white" stroke-width="1.4"/>`).join('');
    }).join('');
    const hits=labels.map((label,i)=>{const left=bar?pad.l+i*slot:Math.max(pad.l,x(i)-(pw/Math.max(1,labels.length-1))/2),right=bar?left+slot:Math.min(width-pad.r,x(i)+(pw/Math.max(1,labels.length-1))/2),fmt=options.format||((v)=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:2}));const detail=[label,...series.map((s,si)=>`${s.name}: ${s.values[i]===null||s.values[i]===undefined?(en()?'No record':'未记录'):fmt(s.values[i],s,si,i)}`)].join('\n');return `<g ${series.some(s=>s.userContent)||options.userLabels?'data-user-content':''} data-o30-index="${i}" data-chart-point data-tooltip="${esc(detail)}" tabindex="${i===0?'0':'-1'}" role="button" aria-label="${esc(detail)}"><rect x="${left}" y="${pad.t}" width="${Math.max(1,right-left)}" height="${ph}" fill="transparent"/><line class="o30-focus-line" x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${chartHeight-pad.b}"/></g>`;}).join('');
    return `<div class="o30-legend">${series.map((s,i)=>`<span ${s.userContent?'data-user-content':''}><i style="background:${s.color||palette[i%palette.length]}"></i>${esc(s.name)}</span>`).join('')}</div><svg class="o30-svg" width="${width}" height="${chartHeight}" viewBox="0 0 ${width} ${chartHeight}" role="group" aria-label="${esc(options.title||(en()?'Interactive chart':'交互数据图表'))}">${grid.join('')}${plots}${ticks}${hits}</svg><div class="o30-readout" ${series.some(s=>s.userContent)||options.userLabels?'data-user-content':''} aria-live="polite">${en()?'Tap a date or category, or use arrow keys to inspect values':'点按日期或类别查看数值，也可用方向键逐项查看'}</div>`;
  }
  function bind(host){
    const nodes=[...host.querySelectorAll('[data-o30-index]')],readout=host.querySelector('.o30-readout');
    function inspect(node){if(!node)return;nodes.forEach(n=>{n.classList.toggle('o30-selected',n===node);n.tabIndex=n===node?0:-1;});if(readout)readout.textContent=node.dataset.tooltip.replace(/\n/g,'  ·  ');}
    host.onpointermove=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.onclick=e=>inspect(e.target.closest?.('[data-o30-index]'));
    if(host._o30FocusHandler)host.removeEventListener('focusin',host._o30FocusHandler);
    host._o30FocusHandler=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.addEventListener('focusin',host._o30FocusHandler);
    host.onkeydown=e=>{const n=e.target.closest?.('[data-o30-index]');if(!n)return;let index=nodes.indexOf(n);if(e.key==='ArrowRight')index++;else if(e.key==='ArrowLeft')index--;else if(e.key==='Home')index=0;else if(e.key==='End')index=nodes.length-1;else return;e.preventDefault();const target=nodes[Math.max(0,Math.min(nodes.length-1,index))];inspect(target);target?.focus();};
  }
  function render(host,options){if(!host)return;host._o30Options=options;host.classList.add('o30-chart');host.classList.remove('business-grouped-chart','sep05-chart-ready','fit-month-chart');host.style.removeProperty('min-width');host.style.removeProperty('height');host.style.width='100%';
    const draw=()=>{const width=Math.max(220,Math.floor(host.getBoundingClientRect().width||host.parentElement?.clientWidth||600));host._o30Width=width;host.innerHTML=markup(host._o30Options,width);bind(host);};draw();
    if(!host._o30Observer&&typeof ResizeObserver!=='undefined'){host._o30Observer=new ResizeObserver(()=>{const w=Math.floor(host.getBoundingClientRect().width);if(w>0&&w!==host._o30Width)draw();});host._o30Observer.observe(host);}
  }
  window.Oct30Charts={render,markup,palette};
  // All legacy analysis views share the same chart language. Separate units
  // have separate axes rather than combining people, percentages and money.
  const unit=key=>['grossRate','netRate','newRatio','oldRatio'].includes(key)?'rate':['customers','newCustomers','oldCustomers'].includes(key)?'count':'money';
  function businessChart(host,groups,keys,average,kind){host.innerHTML='';host._o30Options=null;host._o30Observer?.disconnect();host._o30Observer=null;host.classList.add('o30-facets');host.classList.remove('o30-chart','business-grouped-chart');host.style.height='auto';
    for(const type of [...new Set(keys.map(unit))]){const chosen=keys.filter(k=>unit(k)===type),facet=document.createElement('div');host.appendChild(facet);render(facet,{labels:groups.map(g=>g.label),kind,series:chosen.map((key,i)=>({name:proBusinessMetricLabel(key),color:palette[i%palette.length],values:groups.map(g=>{const explicit=g.values?.find(v=>v.key===key);return explicit?explicit.value:g.list?.length?proBusinessGroupValue(g.list,key,average).value:null;})})),format:v=>type==='rate'?`${Exact.decimal(v).toFixed(1)}%`:type==='count'?Exact.decimal(v).toLocaleString():money(v)});}
  }
  proBusinessGroupedBars=function(node,groups,keys,average){businessChart(node,groups,keys,average,'bar');};
  const businessBase=renderBusinessStats;renderBusinessStats=function(){businessBase();businessChart($('statsChart'),proBusinessTrendGroups(filteredStatsItems(),proBusinessModeAverage()),selectedProMetrics(),proBusinessModeAverage(),'line');};
  renderIngredientGroupedCharts=function(rows,purchase,metric,value){
    const hosts=['statsChart','statsMonthlyChart','statsWeekdayChart'].map($);
    hosts.forEach(host=>{host.innerHTML='';host._o30Options=null;host._o30Observer?.disconnect();host._o30Observer=null;host.classList.add('o30-facets');host.classList.remove('o30-chart');host.style.height='auto';});
    const groups=ingredientSeriesGroups(rows),format=v=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:3});
    if(!groups.length){hosts.forEach(host=>render(host,{labels:[],series:[]}));return;}
    for(const group of groups){
      const first=group[0],emptyText=purchase&&!group.some(row=>entered(row.total))?(en()?'Selected records are not priced yet':'所选记录尚未定价'):'',unknown=ingredientAggregate(group).unknownQuantity,name=`${first.name}（${first.unit?(typeof v8DisplayUnit==='function'?v8DisplayUnit(first.unit):first.unit):(en()?'No unit':'无单位')}）${purchase&&unknown&&(metric==='unit'||metric==='monthlyAverageUnit')?(en()?' · unit price uses priced quantities only':' · 单价仅计已定价数量'):''}`,panels=hosts.map(host=>{const panel=document.createElement('div');host.appendChild(panel);return panel;});
      let points=aggregateByDate(group,value);
      if(!purchase&&metric==='cumulative'){let running=0;points=points.map(point=>({...point,value:(running+=point.value)}));}
      render(panels[0],{labels:points.map(p=>p.date.slice(5)),series:[{name,userContent:true,values:points.map(p=>p.value)}],format,emptyText});
      const monthly=aggregateByMonth(group,item=>purchase?value(item):(metric==='monthlyAverage'?(item.days?item.quantity/item.days:0):item.quantity));
      render(panels[1],{labels:monthly.map((p,i)=>en()?['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i]:p.label),kind:'bar',series:[{name,userContent:true,values:monthly.map(p=>p.value)}],format,emptyText});
      const labels=en()?['Mon','Tue','Wed','Thu','Fri','Sat','Sun']:['周一','周二','周三','周四','周五','周六','周日'],week=labels.map(()=>[]);group.forEach(row=>week[(parseDate(row.date).getDay()+6)%7].push(row));
      const values=week.map(list=>{if(!list.length)return null;const aggregate=ingredientAggregate(list),{quantity,days}=aggregate;return purchase?value(aggregate):quantity/days;});
      render(panels[2],{labels,kind:'bar',series:[{name,userContent:true,values}],format,emptyText});
    }
  };
})();
