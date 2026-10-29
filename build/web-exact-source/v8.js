"use strict";

/* v8 compatibility layer: shared dates, compact chart labels, complete picker tools and English UI. */
const V8_UNIT_EN={"斤":"500 g","公斤":"Kg","千克":"Kg","克":"g","两":"50 g","袋":"Pack","盒":"Box","个":"Pc","只":"Pc","条":"Pc","件":"Pc","颗":"Pc","根":"Pc","瓶":"Bottle","箱":"Carton","份":"Serving","把":"Bunch","扎":"Bunch","碗":"Bowl","盘":"Plate","升":"L","打":"Dozen"};
const V8_TEXT_EN=new Map(Object.entries({
  "选择日期":"Date","选择月份":"Month","选择日":"Date","选择年":"Year","前一天":"Previous day","后一天":"Next day","今天":"Today","关闭":"Close","搜索":"Search","清空搜索":"Clear search",
  "录入／编辑当日流水":"Enter / edit daily record","收入（Revenue）":"Revenue","总客人数":"Total customers","新客人数量":"New customers","当日备注":"Daily notes","食材明细及金额":"Ingredient details and amount","佐料明细及金额":"Seasoning details and amount","其它明细及金额":"Other details and amount","选择食材":"Select ingredients","选择佐料":"Select seasonings","覆盖当日记录（完整替换原有数据）":"Save daily record (replace existing data)","撤销未保存的所有修改":"Discard unsaved changes",
  "固定成本录入":"Fixed cost entry","查看／增加／修改 固定成本":"View / add / edit fixed costs","本月房租及物业合计":"Monthly rent and property total","房租／物业备注汇总":"Rent / property notes","实际使用水费":"Actual water used","实际使用电费":"Actual electricity used","保存实际使用水费、电费":"Save actual water and electricity","历史记录（双击回填编辑）":"History (double-click to edit)","至少显示 25 行":"At least 25 rows",
  "日期":"Date","收入":"Revenue","新客":"New customers","总客数":"Total customers","食材总价格":"Ingredient total","佐料明细":"Seasoning details","当日总固定成本":"Daily fixed cost","其它明细":"Other details","毛利润（毛利率）":"Gross Profit (Margin)","净利润（净利率）":"Net Profit (Margin)",
  "当日做出的菜品":"Dishes prepared today","第一部分： 当日做出的菜品":"Part 1:  Dishes prepared today","第二部分： 固定项目（米饭／汤／小菜／青菜）":"Part 2:  Fixed items (rice / soup / side dishes / vegetables)","第三部分： 每个食材总共用了多少":"Part 3:  Total use of each ingredient","保存修改":"Save changes","新增菜品":"Add dish","删除选中菜品":"Delete selected dishes","总备注：":"General notes:","菜品名称":"Dish name","菜品份数":"Servings","使用食材明细":"Ingredient details","食材成本（元）":"Ingredient cost (CNY)","备注":"Notes","操作":"Actions","固定项目":"Fixed item","选择／修改食材":"Select / edit ingredients","食材名称":"Ingredient","总使用量":"Total quantity","单位":"Unit","总成本（元）":"Total cost (CNY)","使用于":"Used in","尚未选择食材":"No ingredients selected",
  "食材明细":"Ingredient details","佐料明细":"Seasoning details","增加／修改／删除 单位":"Add / edit / delete units","新增空行":"Add row","删除选中行":"Delete selected rows","移动至佐料":"Move to seasonings","移动至食材":"Move to ingredients","数量":"Quantity","单价（元）":"Unit price (CNY)","总价（元）":"Total (CNY)",
  "更多统计":"Advanced analytics","统计方式：":"Method:","明细":"Detail","平均":"Average","年份：":"Year:","上一年":"Previous year","今年":"This year","下一年":"Next year","导出 CSV":"Export CSV","导出当前筛选 CSV":"Export current filters to CSV","月份：":"Months:","星期：":"Weekdays:","经营指标":"Business metrics","全选":"Select all","全不选":"Clear all","食材采购":"Ingredient purchasing","食材指标：":"Ingredient metric:","单价随时间变化":"Unit price over time","每月采购总价":"Monthly purchase total","每月采购量":"Monthly quantity","每月平均单价":"Monthly average unit price","选择食材（不选则看经营指标）":"Choose ingredients (none = business metrics)","清空食材":"Clear ingredients","食材消耗（来自“当日做出的菜品”）":"Ingredient usage (from dishes)","消耗指标：":"Usage metric:","每日消耗量变化":"Daily quantity","每月消耗总量":"Monthly total quantity","每月日均消耗量":"Monthly daily average","累计消耗量":"Cumulative quantity","选择消耗食材（未选择）":"Choose usage ingredients (none selected)","清空消耗食材":"Clear usage ingredients","显示内容：":"Show:","趋势图":"Trend","月度／食材对比图":"Monthly / ingredient comparison","星期图":"Weekday chart","数据表":"Data table","只看表格":"Table only","所选日期明细趋势":"Selected-date trend","月度对比":"Monthly comparison","星期分布":"Weekday distribution","悬停或点按查看数值；可左右拖动":"Hover or tap for values; drag horizontally","悬停或点按查看数值":"Hover or tap for values","放大":"Expand","退出全屏":"Exit full screen",
  "类型":"Type","日期／月份":"Date / month","日期/月份":"Date / month","星期":"Weekday","采购明细":"Purchase detail","消耗明细":"Usage detail","当前筛选条件没有所选食材记录":"No ingredient records match the current filters","没有符合筛选条件的数据":"No data matches the current filters",
  "上个月":"Previous month","本月":"This month","下个月":"Next month","工作日":"Weekdays","周末":"Weekend","周一":"Monday","周二":"Tuesday","周三":"Wednesday","周四":"Thursday","周五":"Friday","周六":"Saturday","周日":"Sunday","一":"Mon","二":"Tue","三":"Wed","四":"Thu","五":"Fri","六":"Sat","日":"Sun",
  "增加一笔":"Add entry","删除选中支出":"Delete selected expenses","支出日期":"Payment date","类别":"Category","对象／说明":"Item / description","金额（元）":"Amount (CNY)","显示类别：":"Categories:","人工":"Labour","房租及物业费":"Rent and property","水费":"Water","电费":"Electricity","煤气费":"Gas","其它":"Other",
  "确认带回":"Confirm selection","新增到字库":"Add to dictionary","管理单位":"Manage units","删除勾选词条":"Delete selected words","重命名勾选词条":"Rename selected word","搜索食材或佐料":"Search ingredients or seasonings","食材名称":"Ingredient","佐料名称":"Seasoning",
  "未选择":"None selected","可修改":"Editable","只读账号":"Read only","食材种类":"Ingredient types","佐料种类":"Seasoning types","总金额":"Total amount","当前显示合计":"Displayed total","本月实际支出合计":"Monthly payments","成本计算：水费":"Cost basis: water","电费":"Electricity","固定成本口径合计":"Fixed-cost basis total","逐笔记录":"Entries",
  "食材成本":"Ingredient Cost","食材成本（包括佐料）":"Ingredient Cost (including seasonings)","食材成本（包含佐料）":"Ingredient Cost (including seasonings)","佐料成本":"Seasoning Cost","总成本":"Total Cost","日均总成本":"Average total cost","每日收入":"Daily Revenue","每日毛利润":"Daily Gross Profit","每日净利润":"Daily Net Profit","每日食材成本":"Daily Ingredient Cost","每日佐料成本":"Daily Seasoning Cost","每日总成本":"Daily Total Cost","当前选择":"Current selection","月度／食材对比":"Monthly / ingredient comparison"
}));
const v8OriginalText=new WeakMap();
const v8OriginalPlaceholder=new WeakMap();

function v8DisplayUnit(unit){return state.language==="en"?(V8_UNIT_EN[unit]||unit):unit;}
function v8TranslateValue(text){const raw=String(text??""),trimmed=raw.trim();if(!trimmed)return raw;let translated=V8_TEXT_EN.get(trimmed);if(!translated){
  translated=trimmed
    .replace(/ · 所选日期明细趋势$/," · Selected-date trend")
    .replace(/^(\d{1,2})月$/,(_,month)=>["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][Number(month)-1]||month)
    .replace(/^ (\d{4}-\d{2}) 增加[／/]修改 固定成本$/," $1 Add / edit fixed costs")
    .replace(/^显示范围：(.+)（整月固定成本支出）$/,"Range: $1 (full-month fixed-cost payments)")
    .replace(/^整月 (\d+)–(\d+) 日已生成；.*$/,"All days $1–$2 are shown; hover or tap for details")
    .replace(/^本月实际支出合计\s*/,"Monthly payments ")
    .replace(/^当日全部食材成本合计：/,"Total ingredient cost today: ")
    .replace(/^食材种类：/,"Ingredient types: ").replace(/^佐料种类：/,"Seasoning types: ").replace(/　总金额：/,"  Total: ")
    .replace(/^当前显示合计：/,"Displayed total: ")
    .replace(/^第(\d+)部分：/,"Part $1: ");
  if(translated===trimmed&&V8_UNIT_EN[trimmed])translated=V8_UNIT_EN[trimmed];
}
if(translated===trimmed)return raw;return raw.replace(trimmed,translated);}
function v8TranslateTree(root=document){
  if(state.language!=="en"){document.querySelectorAll("*").forEach(()=>{});return;}
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes){const parent=node.parentElement;if(!parent||parent.matches("script,style")||parent.closest("[data-user-content]"))continue;const next=v8TranslateValue(node.nodeValue);if(next!==node.nodeValue){if(!v8OriginalText.has(node))v8OriginalText.set(node,node.nodeValue);node.nodeValue=next;}}
  root.querySelectorAll?.("input[placeholder],textarea[placeholder]").forEach(node=>{const next=v8TranslateValue(node.placeholder);if(next!==node.placeholder){if(!v8OriginalPlaceholder.has(node))v8OriginalPlaceholder.set(node,node.placeholder);node.placeholder=next;}});
}
function v8RestoreChinese(){
  const walker=document.createTreeWalker(document,NodeFilter.SHOW_TEXT);while(walker.nextNode()){const node=walker.currentNode;if(v8OriginalText.has(node))node.nodeValue=v8OriginalText.get(node);}
  document.querySelectorAll("input[placeholder],textarea[placeholder]").forEach(node=>{if(v8OriginalPlaceholder.has(node))node.placeholder=v8OriginalPlaceholder.get(node);});
}

proUnitOptions=function(value=""){return [...new Set(["",...proUnits(),value])].map(item=>`<option value="${escapeHtml(item)}" ${item===value?"selected":""}>${escapeHtml(v8DisplayUnit(item))}</option>`).join("");};

function v8PickerItems(host,checkedOnly=true){return [...host.querySelectorAll("tbody tr")].filter(tr=>!checkedOnly||tr.querySelector("[data-pick-check]").checked).map(tr=>({name:tr.querySelector("[data-pick-name]").textContent.trim(),quantity:tr.querySelector('[data-pick="quantity"]').value,unit:tr.querySelector('[data-pick="unit"]').value,price:tr.querySelector('[data-pick="price"]').value,total:tr.querySelector('[data-pick="total"]').value,note:tr.querySelector('[data-pick="note"]').value}));}
openItemPicker=function(category,current,callback,title=""){
  proPickerCallback=callback;const selected=new Map(parseDetailItems(current).map(item=>[item.name,item])),names=[...new Set([...ingredientDictionary(category),...selected.keys()])];
  const en=state.language==="en",categoryLabel=en?(category==="食材"?"ingredient":"seasoning"):category;
  const heading=title||(en?` Select ${categoryLabel}s`:` 选择当天的${category}`);
  const rows=names.map(name=>{
    const item=selected.get(name)||{name};
    return `<tr><td><input data-pick-check type="checkbox" ${selected.has(name)?"checked":""}></td><td class="picker-name-cell" data-pick-name data-user-content>${escapeHtml(name)}</td><td><input data-pick="quantity" type="number" step="any" value="${escapeHtml(item.quantity??"")}"></td><td><select data-pick="unit">${proUnitOptions(item.unit)}</select></td><td><input data-pick="price" type="number" step="0.000001" value="${entered(item.price)?num(item.price).toFixed(6):""}"></td><td><input data-pick="total" type="number" step="0.01" value="${entered(item.total)?num(item.total).toFixed(2):""}"></td><td><input data-pick="note" value="${escapeHtml(item.note||"")}"></td></tr>`;
  }).join("");
  $("proModalHost").innerHTML=`<div class="selector-backdrop"><section class="selector-dialog"><header><h2>${escapeHtml(heading)}</h2><button class="pro-button" data-close-modal>${en?"Close":"关闭"}</button></header><div class="modal-body"><div class="picker-search-row"><input data-picker-search placeholder="${en?`Search ${categoryLabel}s`:"搜索食材或佐料"}"><button class="pro-button" data-clear-search>${en?"Clear search":"清空搜索"}</button></div><div class="desktop-table-wrap"><table class="desktop-table selector-table"><thead><tr><th></th><th>${en?(category==="食材"?"Ingredient":"Seasoning"):`${category}名称`}</th><th>${en?"Quantity":"数量"}</th><th>${en?"Unit":"单位"}</th><th>${en?"Unit price (CNY)":"单价（元）"}</th><th>${en?"Total (CNY)":"总价（元）"}</th><th>${en?"Notes":"备注"}</th></tr></thead><tbody>${rows}</tbody></table></div></div><footer><button data-select-all class="pro-button"> ${en?"Select all":"全选"}</button><span class="selector-add-inline"><input data-add-word-input aria-label="${en?`New ${categoryLabel} name`:`新增${category}名称`}" placeholder="${en?`New ${categoryLabel} name`:`新增${category}名称`}"><button data-add-word class="pro-button">＋ ${en?"Add":"新增"}</button></span><button data-rename-word class="pro-button"> ${en?"Rename selected word":"重命名勾选词条"}</button><button data-manage-units-modal class="pro-button"> ${en?"Manage units":"管理单位"}</button><button data-delete-words class="pro-button red"> ${en?"Delete selected words":"删除勾选词条"}</button><button data-confirm-picker class="pro-button green confirm"> ${en?"Confirm":"确认带回"}</button></footer></section></div>`;
  const host=$("proModalHost"),initialSelection=JSON.stringify(v8PickerItems($("proModalHost"),true)),preserveUnchanged=state.activePage==="ledger"&&["ledgerFoodDetail","ledgerSpiceDetail"].some(id=>$(id)?.value===current),reopen=()=>openItemPicker(category,serializeItems(v8PickerItems(host,true)),callback,title);
  host.querySelector("[data-close-modal]").addEventListener("click",closeProModal);host.querySelector("[data-select-all]").addEventListener("click",()=>host.querySelectorAll("[data-pick-check]").forEach(i=>i.checked=true));
  const search=host.querySelector("[data-picker-search]"),filter=()=>{const term=search.value.trim().toLocaleLowerCase();host.querySelectorAll("tbody tr").forEach(tr=>tr.hidden=!!term&&!tr.querySelector("[data-pick-name]").textContent.toLocaleLowerCase().includes(term));};search.addEventListener("input",filter);host.querySelector("[data-clear-search]").addEventListener("click",()=>{search.value="";filter();search.focus();});
  const addWord=async()=>{const input=host.querySelector("[data-add-word-input]"),word=input.value.trim();if(!word){input.focus();return;}await saveDictionary(category,[...ingredientDictionary(category),word]);reopen();};
  host.querySelector("[data-add-word]").addEventListener("click",()=>safely(addWord));host.querySelector("[data-add-word-input]").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();safely(addWord);}});
  host.querySelector("[data-rename-word]").addEventListener("click",async()=>{const rows=[...host.querySelectorAll("tbody tr")].filter(tr=>tr.querySelector("[data-pick-check]").checked);if(rows.length!==1){alert(en?"Select exactly one word to rename.":"请只勾选一个需要重命名的词条。");return;}const oldName=rows[0].querySelector("[data-pick-name]").textContent.trim(),newName=prompt(en?"New name:":"请输入新名称：",oldName)?.trim();if(!newName||newName===oldName)return;rows[0].querySelector("[data-pick-name]").textContent=newName;await saveDictionary(category,ingredientDictionary(category).map(name=>name===oldName?newName:name));reopen();});
  host.querySelector("[data-manage-units-modal]").addEventListener("click",manageUnits);host.querySelector("[data-delete-words]").addEventListener("click",async()=>{const remove=[...host.querySelectorAll("tbody tr")].filter(tr=>tr.querySelector("[data-pick-check]").checked).map(tr=>tr.querySelector("[data-pick-name]").textContent);if(remove.length&&confirm(en?`Delete ${remove.length} selected word(s) from the dictionary?`:`确定从字库删除 ${remove.length} 个词条吗？`)){await saveDictionary(category,ingredientDictionary(category).filter(name=>!remove.includes(name)));reopen();}});
  const syncPickerAmounts=(tr,source)=>proSyncAmountFields(tr.querySelector('[data-pick="quantity"]'),tr.querySelector('[data-pick="price"]'),tr.querySelector('[data-pick="total"]'),source);
  host.querySelectorAll('[data-pick="quantity"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"quantity")));
  host.querySelectorAll('[data-pick="price"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"price")));
  host.querySelectorAll('[data-pick="total"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"total")));
  host.querySelector("[data-confirm-picker]").addEventListener("click",()=>{const items=v8PickerItems(host,true);if(!preserveUnchanged||JSON.stringify(items)!==initialSelection)callback(items);closeProModal();});
};

proLineSvg=function(points,fitAll=false,key="net"){
  if(!points.length)return `<div class="empty-chart">${state.language==="en"?"No data matches the current filters":"没有符合筛选条件的数据"}</div>`;
  const values=points.map(p=>p.value),min=Math.min(0,...values),max=Math.max(1,...values),range=max-min||1,maxIndex=values.indexOf(Math.max(...values)),minIndex=values.indexOf(Math.min(...values));
  const makeSvg=(width,height,detailed)=>{const pad=detailed?{l:100,r:90,t:105,b:180}:{l:65,r:45,t:60,b:50},x=i=>pad.l+i*(width-pad.l-pad.r)/Math.max(1,points.length-1),y=v=>pad.t+(max-v)/range*(height-pad.t-pad.b),dateY=detailed?height-pad.b+62:height-22,path=points.map((p,i)=>`${i?"L":"M"}${x(i)},${y(p.value)}`).join(" ");return `<svg class="clean-trend-svg ${detailed?"detailed-trend-svg":"compact-trend-svg"}" style="width:${width}px" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line class="axis-line" x1="${pad.l}" x2="${width-pad.r}" y1="${y(0)}" y2="${y(0)}"/><path class="trend-line" d="${path}"/>${points.map((p,i)=>{const label=key==="gross"||key==="net"?`${Math.round(p.value).toLocaleString()} (${percent(p.value,p.revenue)})`:compactDecimal(p.value),dateLabel=fitAll?String(Number(p.date.slice(8))):p.date.slice(5),extreme=i===maxIndex||i===minIndex,pointY=y(p.value),lane=i%4;let labelY=pointY-(34+lane*30);if(labelY<35)labelY=Math.min(height-pad.b-24,pointY+42+lane*30);return `<g data-chart-point data-tooltip="${p.date}\n${label}" tabindex="0"><line class="point-label-leader" x1="${x(i)}" y1="${pointY}" x2="${x(i)}" y2="${labelY+(labelY<pointY?7:-18)}"/><circle class="trend-point" cx="${x(i)}" cy="${pointY}" r="5"/><text class="point-value-label ${extreme?"is-extreme":""}" x="${x(i)}" y="${labelY}" text-anchor="middle">${label}</text><text class="chart-label" x="${x(i)}" y="${dateY}" text-anchor="middle">${dateLabel}</text></g>`;}).join("")}</svg>`;};
  return makeSvg(1080,420,false)+makeSvg(Math.max(1700,points.length*220+180),900,true);
};

function v8SyncDate(dateText,source=""){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(dateText))return;const month=dateText.slice(0,7);["selectedDate","ledgerDate","dishDate","foodDate","spiceDate"].forEach(id=>{const node=$(id);if(node&&id!==source)node.value=dateText;});["fixedMonth","historyMonth"].forEach(id=>{const node=$(id);if(node)node.value=month;});if($("selectedYear"))$("selectedYear").value=dateText.slice(0,4);if($("selectedMonth"))$("selectedMonth").value=String(Number(dateText.slice(5,7)));
}
function v8DateFromMonth(month){if(!/^\d{4}-\d{2}$/.test(month))return "";const old=$("selectedDate")?.value||`${month}-01`,day=Math.min(Number(old.slice(8))||1,daysInMonth(Number(month.slice(0,4)),Number(month.slice(5))));return `${month}-${String(day).padStart(2,"0")}`;}
function v8RefreshPage(page){if(page==="ledger"){refreshLedger();refreshFixed();renderHistory();}else if(page==="dishes")refreshDishes();else if(page==="food")refreshDetail("food");else if(page==="spice")refreshDetail("spice");else if(page==="inventory")renderInventory();else if(page==="stats")initializeStats();else if(page==="overview")renderDashboard();}
document.addEventListener("change",event=>{const id=event.target?.id;if(["selectedDate","ledgerDate","dishDate","foodDate","spiceDate"].includes(id)){v8SyncDate(event.target.value,id);setTimeout(()=>v8RefreshPage(state.activePage),0);}else if(["fixedMonth","historyMonth"].includes(id)){const date=v8DateFromMonth(event.target.value);v8SyncDate(date,id);setTimeout(()=>v8RefreshPage(state.activePage),0);}else if(id==="selectedMonth"||id==="selectedYear"){const year=$("selectedYear").value,month=String($("selectedMonth").value).padStart(2,"0");v8SyncDate(v8DateFromMonth(`${year}-${month}`),id);}},true);
document.addEventListener("click",event=>{
  const page=event.target.closest?.("[data-page]")?.dataset.page;
  if(page)setTimeout(()=>{v8SyncDate($("selectedDate").value);v8RefreshPage(state.activePage);},0);
  const id=event.target.closest?.("button")?.id;
  if(["previousDay","nextDay","todayButton"].includes(id))setTimeout(()=>{v8SyncDate($("selectedDate").value);v8RefreshPage(state.activePage);},0);
},true);
document.addEventListener("change",event=>{
  if(event.target.closest?.("#statsMonthChecks")&&event.target.checked){
    const year=Number($("statsYear")?.value)||new Date().getFullYear(),month=Number(event.target.value||event.target.dataset.month);
    if(month)v8SyncDate(v8DateFromMonth(`${year}-${String(month).padStart(2,"0")}`));
  }else if(event.target?.id==="statsYear"){
    const checked=document.querySelector("#statsMonthChecks input:checked");
    if(checked){const month=Number(checked.value||checked.dataset.month);v8SyncDate(v8DateFromMonth(`${event.target.value}-${String(month).padStart(2,"0")}`));}
  }
},true);

const v8BaseRefreshOpenEditors=refreshOpenEditors;
refreshOpenEditors=function(){v8SyncDate($("selectedDate").value||isoDate(new Date()));v8BaseRefreshOpenEditors();};
const v8BaseApplyLanguage=applyLanguage;
applyLanguage=function(){if(state.language!=="en")v8RestoreChinese();v8BaseApplyLanguage();document.querySelectorAll("select[data-pick='unit'],[data-detail='unit']").forEach(select=>[...select.options].forEach(option=>option.textContent=v8DisplayUnit(option.value||option.textContent)));if(state.language==="en")v8TranslateTree(document);};
const v8BaseRenderStats=renderStats;renderStats=function(){v8BaseRenderStats();if(state.language==="en")v8TranslateTree($("pageStats"));};
const v8BaseRenderDashboard=renderDashboard;renderDashboard=function(){v8BaseRenderDashboard();if(state.language==="en")v8TranslateTree($("pageOverview"));};

const v8Observer=new MutationObserver(records=>{if(state.language!=="en")return;for(const record of records)for(const node of record.addedNodes)if(node.nodeType===Node.ELEMENT_NODE)v8TranslateTree(node);});v8Observer.observe(document.body,{childList:true,subtree:true});
v8SyncDate($("selectedDate")?.value||isoDate(new Date()));applyLanguage();
