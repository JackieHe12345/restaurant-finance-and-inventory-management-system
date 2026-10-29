"use strict";
/* Responsive reporting charts. Decimal values remain exact in text; only
 * coordinates are converted to Number. Missing observations stay missing. */
(() => {
  const palette=['#2563a6','#0f8a7c','#d08b28','#8b65bd','#de5960','#527487'];
  const en=()=>state.language==='en',esc=value=>escapeHtml(String(value??''));
  const number=value=>value===null||value===undefined||value===''?null:Exact.toNumber(value);
  function axis(value){const a=Math.abs(value),scale=a>=100000000?100000000:a>=10000?10000:1;return (value/scale).toLocaleString('zh-CN',{maximumFractionDigits:scale===1?(a<10?2:0):1})+(scale===100000000?'亿':scale===10000?'万':'');}
  function domain(values){let min=Math.min(0,...values),max=Math.max(0,...values);if(min===max)max=min+1;const raw=(max-min)/4,power=10**Math.floor(Math.log10(raw)),fraction=raw/power,step=(fraction<=1?1:fraction<=2?2:fraction<=5?5:10)*power;return {min:Math.floor(min/step)*step,max:Math.ceil(max/step)*step,step};}
  function markup(options,width){
    const labels=options.labels||[],series=options.series||[],height=options.height||280,pad={l:width<400?46:58,r:18,t:18,b:34};
    const numeric=series.flatMap(s=>s.values.map(number)).filter(v=>v!==null&&Number.isFinite(v));
    if(!labels.length||!numeric.length)return `<div class="o30-empty">${en()?'No records in this period':'这段时间还没有记录'}<small>${en()?'Choose another period or enter records.':'可切换月份，或录入后再查看。'}</small></div>`;
    const d=domain(numeric),pw=width-pad.l-pad.r,ph=height-pad.t-pad.b,bar=options.kind==='bar',slot=pw/Math.max(1,labels.length),x=i=>bar?pad.l+slot*(i+.5):pad.l+(labels.length===1?pw/2:i*pw/(labels.length-1)),y=v=>pad.t+(d.max-v)/(d.max-d.min)*ph;
    const grid=[];for(let v=d.min,i=0;i<=10&&v<=d.max+d.step*.01;v+=d.step,i++){const py=y(v);grid.push(`<line x1="${pad.l}" x2="${width-pad.r}" y1="${py}" y2="${py}" class="${Math.abs(v)<d.step*.001?'o30-zero':'o30-grid'}"/><text x="${pad.l-9}" y="${py+4}" text-anchor="end" class="o30-axis">${esc(axis(v))}</text>`);}
    const labelsEvery=Math.max(1,Math.ceil(labels.length/Math.max(2,Math.floor(pw/60))));
    const ticks=labels.map((label,i)=>i%labelsEvery===0||i===labels.length-1?`<text x="${x(i)}" y="${height-9}" text-anchor="${i===labels.length-1?'end':i===0?'start':'middle'}" class="o30-axis">${esc(label)}</text>`:'').join('');
    const plots=series.map((s,si)=>{const color=s.color||palette[si%palette.length],coords=s.values.map((v,i)=>({i,raw:v,v:number(v)}));let path='',connected=false;
      if(bar){const bw=Math.max(1,Math.min(30,slot*.66/Math.max(1,series.length)));return coords.map(p=>p.v===null?'':`<rect x="${x(p.i)+(si-series.length/2)*bw}" y="${Math.min(y(p.v),y(0))}" width="${Math.max(1,bw-2)}" height="${Math.max(0,Math.abs(y(p.v)-y(0)))}" rx="2" fill="${color}" opacity=".9"/>`).join('');}
      coords.forEach(p=>{if(p.v===null){connected=false;return;}path+=`${connected?'L':'M'}${x(p.i)},${y(p.v)} `;connected=true;});
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`+coords.map(p=>p.v===null?'':`<circle cx="${x(p.i)}" cy="${y(p.v)}" r="${labels.length>60?1.5:3}" fill="${color}" stroke="white" stroke-width="1.4"/>`).join('');
    }).join('');
    const hits=labels.map((label,i)=>{const left=bar?pad.l+i*slot:Math.max(pad.l,x(i)-(pw/Math.max(1,labels.length-1))/2),right=bar?left+slot:Math.min(width-pad.r,x(i)+(pw/Math.max(1,labels.length-1))/2),fmt=options.format||((v)=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:2}));const detail=[label,...series.map((s,si)=>`${s.name}: ${s.values[i]===null||s.values[i]===undefined?(en()?'No record':'未记录'):fmt(s.values[i],s,si,i)}`)].join('\n');return `<g data-o30-index="${i}" data-chart-point data-tooltip="${esc(detail)}" tabindex="${i===0?'0':'-1'}" role="button" aria-label="${esc(detail)}"><rect x="${left}" y="${pad.t}" width="${Math.max(1,right-left)}" height="${ph}" fill="transparent"/><line class="o30-focus-line" x1="${x(i)}" x2="${x(i)}" y1="${pad.t}" y2="${height-pad.b}"/></g>`;}).join('');
    return `<div class="o30-legend">${series.map((s,i)=>`<span><i style="background:${s.color||palette[i%palette.length]}"></i>${esc(s.name)}</span>`).join('')}</div><svg class="o30-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="group" aria-label="${esc(options.title||(en()?'Interactive chart':'交互数据图表'))}">${grid.join('')}${plots}${ticks}${hits}</svg><div class="o30-readout" aria-live="polite">${en()?'Tap a date, or use arrow keys to inspect values':'点按日期查看数值，也可用方向键逐项查看'}</div>`;
  }
  function bind(host){
    const nodes=[...host.querySelectorAll('[data-o30-index]')],readout=host.querySelector('.o30-readout');
    function inspect(node){if(!node)return;nodes.forEach(n=>{n.classList.toggle('o30-selected',n===node);n.tabIndex=n===node?0:-1;});if(readout)readout.textContent=node.dataset.tooltip.replace(/\n/g,'  ·  ');}
    host.onpointermove=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.onclick=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.onfocusin=e=>inspect(e.target.closest?.('[data-o30-index]'));
    host.onkeydown=e=>{const n=e.target.closest?.('[data-o30-index]');if(!n)return;let index=nodes.indexOf(n);if(e.key==='ArrowRight')index++;else if(e.key==='ArrowLeft')index--;else if(e.key==='Home')index=0;else if(e.key==='End')index=nodes.length-1;else return;e.preventDefault();nodes[Math.max(0,Math.min(nodes.length-1,index))]?.focus();};
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
  const ingredientBase=renderIngredientStats;renderIngredientStats=function(type){ingredientBase(type);const purchase=type==='purchase',rows=purchase?statsPurchaseRows():statsConsumptionRows(),metric=$(purchase?'purchaseMetric':'consumptionMetric').value;let points=aggregateByDate(rows,item=>purchase?(metric==='unit'||metric==='monthlyAverageUnit'?(item.quantity?item.total/item.quantity:0):metric==='monthlyTotal'?item.total:item.quantity):item.quantity);if(!purchase&&metric==='cumulative'){let running=Exact.decimal(0);points=points.map(p=>({...p,value:(running=Exact.add(running,p.value))}));}render($('statsChart'),{labels:points.map(p=>p.date.slice(5)),series:[{name:$(purchase?'purchaseMetric':'consumptionMetric').selectedOptions[0].textContent,values:points.map(p=>p.value)}],format:v=>Exact.decimal(v).toLocaleString('zh-CN',{maximumFractionDigits:3})});};
})();
