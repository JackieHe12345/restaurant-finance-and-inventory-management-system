"use strict";
/* Oct29V1: explicit customer counts, derived purchase receipts and FIFO costs. */
function validateCustomerCounts(){
  for(const [id,label] of [["ledgerNewCustomers","新客人数"],["ledgerCustomers","总客人数"]]){
    const value=$(id)?.value;
    if(entered(value)&&(!Number.isSafeInteger(Number(value))||Number(value)<0))throw new Error(`${label}请输入大于或等于 0 的整数；未录入请留空。`);
  }
  if(entered($("ledgerNewCustomers")?.value)&&entered($("ledgerCustomers")?.value)&&num($("ledgerNewCustomers").value)>num($("ledgerCustomers").value))throw new Error("新客人数不能大于总客人数。");
}
function renderCustomerTiming(){
  const entry=currentRole()==="entry",window=entryTimingWindowForDate(),fields=window?.customer_fields||{},parts=[];
  for(const [name,id,label] of [["new","ledgerNewCustomers","新客人数"],["total","ledgerCustomers","总客人数"]]){
    const input=$(id);if(!input)continue;
    const info=fields[name]||{},saved=Boolean(info.saved_at||info.edit_deadline),editable=!entry||!saved||entryDeadlineOpen(info.edit_deadline);
    input.disabled=!canEdit()||!editable;input.dataset.entryTimingLocked=editable?"":"1";
    input.title=!entry?"":saved?(editable?"本项首次保存后 30 分钟内可修改":"本项保存已超过 30 分钟，需修改权限"):"本项首次成功保存后开始独立的 30 分钟修改时间";
    parts.push(`<span class="entry-timing-row ${editable?"is-open":"is-locked"}"><b>${label}</b><em>${saved?(editable?escapeHtml(entryTimingText(info.edit_deadline)):"已锁"):"首次保存后开始 30 分钟"}</em></span>`);
  }
  const notice=$("entryTimingNotice");notice?.querySelector(".customer-timing-section")?.remove();
  if(entry&&notice){notice.classList.remove("hidden");notice.insertAdjacentHTML("beforeend",`<section class="customer-timing-section"><h3>新客／总客数（分别计时）</h3><div class="entry-timing-grid">${parts.join("")}</div></section>`);}
}
function inventoryReceiptData(inventory=inventoryPayload()){
  const receipts=[],warnings=[];
  for(const [index,item] of (inventory.entries||[]).entries()){
    const receipt={...item,id:String(item.id||`manual:${index}`),date:normalizeDateKey(item.date||item.日期||""),category:(item.category||item.分类)==="佐料"?"佐料":"食材",name:String(item.name||item.名称||"").trim(),quantity:num(item.quantity??item.数量),unit:String(item.unit||item.单位||"").trim(),unit_price:item.unit_price??item.单价??"",total:item.total??item.总价??"",price_known:item.price_known,source:"manual",note:String(item.note||item.备注||"")};
    if(receipt.name&&receipt.quantity>0)receipts.push(receipt);
  }
  for(const day of [...state.days].sort((a,b)=>String(a.日期).localeCompare(String(b.日期)))){
    const date=normalizeDateKey(day.日期),row=dailyRow(dayPayload(date),date);
    parseDetailItems(row.食材明细).forEach((item,index)=>{
      const name=String(item.name||"").trim(),quantity=num(item.quantity),unit=String(item.unit||"").trim();if(!name)return;
      if(!(quantity>0)||!unit){warnings.push({date,name,reason:!(quantity>0)?"缺少有效数量，请补数量和单位":"缺少单位，请补单位"});return;}
      receipts.push({id:`purchase:${date}:${index}`,date,category:"食材",name,quantity,unit,unit_price:item.price,total:item.total,source:"purchase",note:item.note||""});
    });
  }
  return {receipts,warnings};
}
function inventoryStoredDishRows(record,date){
  const payload=unpackPayload(record),rows=Array.isArray(payload.dishes)?payload.dishes:[];
  const raw=[...rows].reverse().find(row=>normalizeDateKey(row.日期||record?.record_key||"")===date);
  if(!raw)return [];
  try{const dishes=Array.isArray(raw.菜品数据)?raw.菜品数据:JSON.parse(raw.菜品数据||"[]");return Array.isArray(dishes)?dishes:[];}catch(_){return [];}
}
function inventoryFIFOData(options={}){
  const inventory=options.inventory||inventoryPayload(),{receipts,warnings}=inventoryReceiptData(inventory),exact=new Map(),named=new Map(),outbounds=[];
  let dictionaryNames=null;
  const dictionaryCategories=name=>{if(!dictionaryNames)dictionaryNames=new Map(["食材","佐料"].map(category=>[category,new Set(ingredientDictionary(category))]));return new Set([...dictionaryNames].filter(([,names])=>names.has(name)).map(([category])=>category));};
  for(const row of receipts){const k=`${row.name}\u0000${row.unit}`;if(!exact.has(k))exact.set(k,new Set());exact.get(k).add(row.category);if(!named.has(row.name))named.set(row.name,new Set());named.get(row.name).add(row.category);}
  // Dish-only records are valid before the first daily ledger save. Include
  // their dates as well as dates with income/purchase rows.
  const dishDates=new Set(state.days.map(row=>normalizeDateKey(row.日期))),savedDishes=new Map();
  for(const record of state.records||[]){
    if(String(record.record_type||record.type)!=="day")continue;
    const payload=unpackPayload(record);
    for(const row of Array.isArray(payload.dishes)?payload.dishes:[]){
      const date=normalizeDateKey(row.日期||record.record_key||"");if(!isCanonicalDate(date))continue;
      dishDates.add(date);let rows=[];try{rows=Array.isArray(row.菜品数据)?row.菜品数据:JSON.parse(row.菜品数据||"[]");}catch(_){}
      savedDishes.set(date,Array.isArray(rows)?rows:[]);
    }
  }
  if(options.dishDate)dishDates.add(options.dishDate);
  for(const date of [...dishDates].sort()){
    const stored=currentRecord("day",date),dishes=(options.dishDate===date?options.dishRows:stored?inventoryStoredDishRows(stored,date):savedDishes.get(date))||[];
    dishes.forEach((dish,dishIndex)=>parseDetailItems(dish.食材明细).forEach((item,itemIndex)=>{
      const name=String(item.name||"").trim(),unit=String(item.unit||"").trim(),quantity=num(item.quantity);if(!name||quantity<=0)return;
      const categories=exact.get(`${name}\u0000${unit}`)||named.get(name)||dictionaryCategories(name),category=categories?.size===1&&categories.has("佐料")?"佐料":"食材";
      outbounds.push({id:`dish:${date}:${dishIndex}:${itemIndex}`,date,category,name,unit,quantity,kind:"dish",label:dish.菜品名称||"菜品消耗"});
    }));
  }
  const result=InventoryFIFO.replay({receipts,outbounds,adjustments:inventoryAdjustmentRows(inventory),overrides:inventoryOverrideRows(inventory),asOf:options.asOf||isoDate(new Date())});
  result.balances.sort((a,b)=>a.category.localeCompare(b.category,"zh-CN")||a.name.localeCompare(b.name,"zh-CN")||a.unit.localeCompare(b.unit,"zh-CN"));
  return {...result,receipts,warnings};
}
function fifoAllocationText(result){
  const parts=(result.allocations||[]).map(batch=>`${batch.date||"缺入库记录"}：${compactDecimal(batch.quantity)} × ${batch.unit_price===null?"单价未知":compactDecimal(batch.unit_price)+" 元"}`);
  return parts.length?parts.join("；"):"—";
}
function fifoAverageText(result){const value=InventoryFIFO.averageUnitCost(result);return value===null?"待定价":money(value);}
function fifoCostText(result){return result.unknownQuantity>1e-9?`${money(result.cost)}（已知部分；${compactDecimal(result.unknownQuantity)} 未定价）`:money(result.cost);}
function renderInventoryFIFO(){
  const page=$("pageInventory");if(!page)return;
  const data=inventoryFIFOData();let card=$("inventoryFifoCard");
  if(!card){page.insertAdjacentHTML("beforeend",'<section id="inventoryFifoCard" class="table-card fifo-card"></section>');card=$("inventoryFifoCard");}
  const purchases=data.receipts.filter(row=>row.source==="purchase"),movements=[...data.movements].reverse();
  card.innerHTML=`<header class="card-title"><div><h2>出入库成本 · 先进先出</h2><small>同名、同单位按入库日期先后出库；不同单位分开统计。买食材保存后自动入库，采购支出只记一次。旧记录无时间时，同日按入库、菜品、使用／损耗、覆盖的顺序计算。</small></div></header>
    ${data.warnings.length?`<p class="fifo-warning">以下采购已记支出，尚未计入数量库存：${data.warnings.map(row=>`${escapeHtml(row.date)} ${escapeHtml(row.name)}（${escapeHtml(row.reason)}）`).join("；")}</p>`:""}
    <details ${purchases.length?"":"open"}><summary>买食材自动入库：${purchases.length} 条（在原食材明细中修改）</summary><div class="table-scroll"><table><thead><tr><th>日期</th><th>食材</th><th>数量</th><th>单位</th><th>入库单价</th><th>总价</th></tr></thead><tbody>${purchases.slice().reverse().map(row=>{const price=InventoryFIFO.unitPrice(row);return `<tr><td>${escapeHtml(row.date)}</td><td>${escapeHtml(row.name)}</td><td>${compactDecimal(row.quantity)}</td><td>${escapeHtml(row.unit)}</td><td>${price===null?"未知":compactDecimal(price)}</td><td>${price===null?"未知":money(price*row.quantity)}</td></tr>`;}).join("")||'<tr><td colspan="6">暂无带数量和单位的食材采购记录。</td></tr>'}</tbody></table></div></details>
    <h3>出库明细及原入库价格</h3><div class="table-scroll"><table><thead><tr><th>出库日期</th><th>食材／佐料</th><th>用途</th><th>出库量</th><th>FIFO 入库批次（数量 × 单价）</th><th>出库成本</th><th>平均单价</th></tr></thead><tbody>${movements.map(row=>`<tr><td>${escapeHtml(row.date)}</td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.label||(row.kind==="loss"?"损耗":"正常使用"))}</td><td>${compactDecimal(row.quantity)} ${escapeHtml(row.unit)}</td><td>${escapeHtml(fifoAllocationText(row))}</td><td>${escapeHtml(fifoCostText(row))}</td><td>${escapeHtml(fifoAverageText(row))} 元／${escapeHtml(row.unit||"单位")}</td></tr>`).join("")||'<tr><td colspan="7">暂无出库记录。</td></tr>'}</tbody></table></div>`;
}
function attachFIFOQuote(key,overwrite=false){
  const host=$("proModalHost"),body=host?.querySelector(".inventory-adjust-modal .modal-body"),input=host?.querySelector("[data-inventory-value]");
  if(!body||!input||overwrite)return;
  body.insertAdjacentHTML("beforeend",'<div class="fifo-preview" aria-live="polite"></div>');const preview=body.querySelector(".fifo-preview");
  const update=()=>{const mode=host.querySelector("[data-inventory-kind]")?.value;if(mode==="overwrite"){preview.textContent="库存覆盖不新增采购金额；增加部分单价记为未知。";return;}const row=inventoryBalances().find(item=>inventoryKey(item)===key),quantity=Math.max(0,(row?.remaining||0)-num(input.value)),cost=InventoryFIFO.quote(row,quantity);preview.textContent=quantity?`本次出库 ${compactDecimal(quantity)} ${row.unit}；${fifoAllocationText(cost)}；成本 ${fifoCostText(cost)}；均价 ${fifoAverageText(cost)} 元／${row.unit}`:"减少剩余量后，这里显示本次出库所用的入库价格。";};
  input.addEventListener("input",update);host.querySelector("[data-inventory-kind]")?.addEventListener("change",update);update();
}
function renderDishFIFO(){
  const page=$("pageDishes"),date=$("dishDate")?.value;if(!page||!date)return;
  let card=$("dishFifoPreview");if(!card){page.insertAdjacentHTML("beforeend",'<section id="dishFifoPreview" class="table-card fifo-card"></section>');card=$("dishFifoPreview");}
  const data=inventoryFIFOData({dishDate:date,dishRows:collectDishRows(),asOf:date}),rows=data.movements.filter(row=>row.date===date&&row.kind==="dish");
  card.innerHTML=`<header class="card-title"><div><h2>本日菜品出库 · 入库价格预览</h2><small>按当前编辑用量计算 FIFO 批次成本；保存菜品后扣减库存。平均单价仅作显示，实际成本按各入库批次分摊合计；采购及现金金额仍按原采购记录计算。</small></div></header><div class="table-scroll"><table><thead><tr><th>菜品</th><th>食材</th><th>数量</th><th>原入库价格</th><th>FIFO 成本</th><th>平均单价</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${escapeHtml(row.label)}</td><td>${escapeHtml(row.name)}</td><td>${compactDecimal(row.quantity)} ${escapeHtml(row.unit)}</td><td>${escapeHtml(fifoAllocationText(row))}</td><td>${escapeHtml(fifoCostText(row))}</td><td>${escapeHtml(fifoAverageText(row))} 元／${escapeHtml(row.unit||"单位")}</td></tr>`).join("")||'<tr><td colspan="6">填写菜品食材用量后显示出库价格。</td></tr>'}</tbody></table></div>`;
}
(() => {
  const baseRefresh=refreshLedger;
  refreshLedger=function(){baseRefresh();renderCustomerTiming();};
  const baseSave=saveLedger;
  saveLedger=async function(){validateCustomerCounts();await baseSave();renderCustomerTiming();};
  const baseTiming=renderEntryTiming;
  renderEntryTiming=function(){baseTiming();renderCustomerTiming();};
  inventoryBalances=function(){return inventoryFIFOData().balances;};
  const baseDishSummary=updateDishSummary;
  updateDishSummary=function(){baseDishSummary();renderDishFIFO();};
  const baseDishRefresh=refreshDishes;
  refreshDishes=function(){baseDishRefresh();renderDishFIFO();};
  const baseSaveDetail=saveDetail;
  saveDetail=async function(kind){await baseSaveDetail(kind);if(kind==="food"){const key=$("foodDate")?.value,warnings=inventoryReceiptData().warnings.filter(row=>row.date===key);if(warnings.length)$("foodResult").textContent+="；部分食材缺少数量或单位，补全后自动计入库存。";}};
  if(state.token)refreshLedger();
})();
