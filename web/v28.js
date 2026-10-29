/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

/* Sep01V1: two-store naming, shared-cost reporting and data-management tools.
   WeChat API controls remain in the compatibility layer but are not exposed. */
state.storeSettings = Exact.or(()=>(state.storeSettings), ()=>({store_a_name:"A店",store_b_name:"B店",wechat_auto_sync:true,wechat:{}}));
let v26StoreSettingsFetchedAt = 0;
let v26StoreSettingsDataset = "";
const v26OriginalTexts = new WeakMap();

function storeName(slot){
  return (Exact.truth(Exact.seq(slot, "B")) ? Exact.or(()=>(state.storeSettings?.store_b_name), ()=>("B店")) : Exact.or(()=>(state.storeSettings?.store_a_name), ()=>("A店")));
}
function storeReplace(text){
  return String(text ?? "").replaceAll("A店",storeName("A")).replaceAll("B店",storeName("B"));
}
function applyStoreNames(root=document.getElementById("appView")){
  if(Exact.truth(Exact.not(root)))return;
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  const nodes=[];while(Exact.truth(walker.nextNode()))nodes.push(walker.currentNode);
  for(const node of nodes){
    const parent=node.parentElement;if(Exact.truth(Exact.or(()=>(Exact.not(parent)), ()=>(["SCRIPT","STYLE"].includes(parent.tagName)))))continue;
    if(Exact.truth(Exact.not(v26OriginalTexts.has(node))))v26OriginalTexts.set(node,Exact.or(()=>(node.nodeValue), ()=>("")));
    node.nodeValue=storeReplace(v26OriginalTexts.get(node));
  }
  document.querySelectorAll("[data-store-placeholder]").forEach(node=>{node.placeholder=storeReplace(Exact.or(()=>(node.dataset.storePlaceholder), ()=>("")));});
}
function yesterdayIso(){const d=new Date();d.setDate(Exact.sub(d.getDate(), 1));return isoDate(d);}

function installV26Navigation(){
  // v28: navigation and pages are static in index.html so they cannot disappear if a late UI injection fails.
  if(Exact.truth(Exact.not($("pageStores")))) throw new Error("v28 页面缺少 pageStores");
  if(Exact.truth(Exact.not($("pageData")))) throw new Error("v28 页面缺少 pageData");
}

function v26WechatCard(slot){
  return `<article class="editor-card payment-config-card admin-only" data-wechat-card="${slot}"><header><div><h2><span data-store-card-name="${slot}">${slot}店</span> · 微信支付 API</h2><p>上传商户 API 证书、私钥和微信支付公钥。p12 与 README 可一并保存，但 APIv3 拉账单核心使用 PEM 文件。</p></div><span id="wechatStatus${slot}" class="permission-pill">未配置</span></header>
    <div class="form-grid payment-config-fields"><label>微信支付商户号<input id="wechatMch${slot}" inputmode="numeric" autocomplete="off"></label><label>微信支付公钥 ID<input id="wechatPubId${slot}" placeholder="PUB_KEY_ID_..."></label>
      <label>apiclient_cert.pem<input id="wechatCert${slot}" type="file" accept=".pem"></label><label>apiclient_key.pem<input id="wechatKey${slot}" type="file" accept=".pem"></label><label>pub_key.pem<input id="wechatPub${slot}" type="file" accept=".pem"></label><label>apiclient_cert.p12（可选）<input id="wechatP12${slot}" type="file" accept=".p12"></label><label>README_CN.txt（可选）<input id="wechatReadme${slot}" type="file" accept=".txt"></label>
    </div><div class="payment-actions"><button data-wechat-save="${slot}" class="primary edit-action" type="button">上传并保存</button><button data-wechat-test="${slot}" class="soft" type="button">验证微信 API</button><button data-wechat-delete="${slot}" class="danger-button edit-action" type="button">删除这家店微信配置</button></div><p id="wechatResult${slot}" class="operation-result"></p></article>`;
}
function installV26WorkbookTools(){
  // v28: dangerous data operations live on the dedicated static Data Management page.
  if(Exact.truth(Exact.not($("pageData")))) throw new Error("v28 页面缺少数据管理模块");
}

async function loadStoreSettings(force=false){
  if(Exact.truth(Exact.not(state.dataset?.id)))return;
  if(Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.not(force)), ()=>(Exact.seq(v26StoreSettingsDataset, state.dataset.id)))), ()=>(Exact.lt(Exact.sub(Date.now(), v26StoreSettingsFetchedAt), 15000))))){applyStoreNames();return;}
  try{
    const result=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/store-settings`);
    state.storeSettings=Exact.or(()=>(result), ()=>(state.storeSettings));
    v26StoreSettingsDataset=state.dataset.id;v26StoreSettingsFetchedAt=Date.now();
    renderStoreSettings();applyStoreNames();
  }catch(error){console.warn("store settings",error);}
}
function renderStoreSettings(){
  if(Exact.truth($("storeSettingsDataset")))$("storeSettingsDataset").textContent=Exact.or(()=>(Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id))), ()=>("—"));
  if(Exact.truth(Exact.and(()=>($("storeAName")), ()=>(Exact.sneq(document.activeElement, $("storeAName"))))))$("storeAName").value=storeName("A");
  if(Exact.truth(Exact.and(()=>($("storeBName")), ()=>(Exact.sneq(document.activeElement, $("storeBName"))))))$("storeBName").value=storeName("B");
  if(Exact.truth($("wechatAutoSync")))$("wechatAutoSync").checked=Exact.sneq(state.storeSettings?.wechat_auto_sync, false);
  for(const slot of ["A","B"]){
    const cfg=Exact.or(()=>(state.storeSettings?.wechat?.[slot]), ()=>({}));
    const nameNode=document.querySelector(`[data-store-card-name="${slot}"]`);if(Exact.truth(nameNode))nameNode.textContent=storeName(slot);
    const mch=$(Exact.add("wechatMch", slot)),pub=$(Exact.add("wechatPubId", slot)),status=$(Exact.add("wechatStatus", slot));
    if(Exact.truth(Exact.and(()=>(mch), ()=>(Exact.sneq(document.activeElement, mch)))))mch.value=Exact.or(()=>(cfg.mchid), ()=>(""));
    if(Exact.truth(Exact.and(()=>(pub), ()=>(Exact.sneq(document.activeElement, pub)))))pub.value=Exact.or(()=>(cfg.public_key_id), ()=>(""));
    if(Exact.truth(status)){status.textContent=(Exact.truth(cfg.configured) ? "已配置" : "未配置");status.classList.toggle("ok",Exact.not(Exact.not(cfg.configured)));}
    const result=$(Exact.add("wechatResult", slot));if(Exact.truth(Exact.and(()=>(Exact.and(()=>(result), ()=>(cfg.configured))), ()=>(Exact.not(result.textContent))))){const files=Exact.or(()=>(cfg.files), ()=>({}));result.textContent=`证书序列号：${Exact.or(()=>(cfg.merchant_serial_no), ()=>("—"))}；核心文件：${(Exact.truth(Exact.and(()=>(Exact.and(()=>(files["apiclient_cert.pem"]), ()=>(files["apiclient_key.pem"]))), ()=>(files["pub_key.pem"]))) ? "齐全" : "不完整")}`;}
  }
  refreshV26DatasetTargets();
}
function refreshV26DatasetTargets(){
  // 演示账本可作为“整套内部 Excel 覆盖”的目标；后端会保留它原有的账本名称。
  for(const id of ["overwriteTargetDataset","copyTargetDataset"]){const select=$(id);if(Exact.truth(Exact.not(select)))continue;const current=select.value;select.innerHTML=state.datasets.filter(d=>Exact.sneq(d.id, state.dataset?.id)).map(d=>`<option value="${escapeHtml(d.id)}">${escapeHtml(Exact.or(()=>(d.name), ()=>(d.id)))}</option>`).join("");if(Exact.truth([...select.options].some(o=>Exact.seq(o.value, current))))select.value=current;}
}
async function saveStoreNamesV26(){
  const a=$("storeAName").value.trim(),b=$("storeBName").value.trim();if(Exact.truth(Exact.or(()=>(Exact.not(a)), ()=>(Exact.not(b)))))throw new Error("两家店名都不能为空。");
  const result=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/store-settings`,{method:"PUT",body:JSON.stringify({store_a_name:a,store_b_name:b,wechat_auto_sync:false})});
  state.storeSettings={...state.storeSettings,...result};$("storeNameResult").textContent="已保存。";applyStoreNames();renderDashboard();renderHistory();renderStats?.();
}
function formAppendFile(form,key,id){const file=$(id)?.files?.[0];if(Exact.truth(file))form.append(key,file);}
async function saveWechatConfigV26(slot){
  const form=new FormData();form.append("mchid",$(Exact.add("wechatMch", slot)).value.trim());form.append("public_key_id",$(Exact.add("wechatPubId", slot)).value.trim());
  const required=[["apiclient_cert",Exact.add("wechatCert", slot)],["apiclient_key",Exact.add("wechatKey", slot)],["pub_key",Exact.add("wechatPub", slot)]];
  for(const [key,id] of required){const file=$(id).files?.[0];if(Exact.truth(Exact.not(file)))throw new Error(`请上传 ${(Exact.truth(id.includes("Cert")) ? "apiclient_cert.pem" : (Exact.truth(Exact.and(()=>(id.includes("Key")), ()=>(Exact.not(id.includes("Pub"))))) ? "apiclient_key.pem" : "pub_key.pem"))}。`);form.append(key,file);}
  formAppendFile(form,"apiclient_p12",Exact.add("wechatP12", slot));formAppendFile(form,"readme_cn",Exact.add("wechatReadme", slot));
  $(Exact.add("wechatResult", slot)).textContent="正在校验证书并上传……";
  try{await api(`/datasets/${encodeURIComponent(state.dataset.id)}/stores/${slot}/wechat-config`,{method:"POST",body:form});$(Exact.add("wechatResult", slot)).textContent="上传成功，证书与私钥匹配检查已通过。";await loadStoreSettings(true);}catch(error){$(Exact.add("wechatResult", slot)).textContent=`上传失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}
}
async function testWechatV26(slot){
  $(Exact.add("wechatResult", slot)).textContent="正在调用微信支付测试……";
  try{const result=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/stores/${slot}/wechat-config/test?bill_date=${yesterdayIso()}`,{method:"POST"});$(Exact.add("wechatResult", slot)).textContent=`验证成功：${result.bill_date}，读取 ${result.rows} 条账单明细。`;}catch(error){$(Exact.add("wechatResult", slot)).textContent=`验证失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}
}
async function downloadWechatBillV26(slot){const date=Exact.or(()=>($(Exact.add("wechatBillDate", slot))?.value), ()=>(yesterdayIso()));const result=$(Exact.add("wechatResult", slot));result.textContent="正在从微信支付 API 下载账单……";try{const response=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/stores/${slot}/wechat-config/test?bill_date=${encodeURIComponent(date)}`,{method:"POST"});result.textContent=`下载成功：${date}，已连接 ${storeName(slot)} API，读取 ${Exact.or(()=>(response.rows), ()=>(0))} 条明细。`;}catch(error){result.textContent=`下载失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}}
async function deleteWechatV26(slot){
  if(Exact.truth(Exact.not(confirm(`确定删除 ${storeName(slot)} 的微信支付配置吗？服务器上的商户证书和私钥会被删除。`))))return;
  try{await api(`/datasets/${encodeURIComponent(state.dataset.id)}/stores/${slot}/wechat-config`,{method:"DELETE"});$(Exact.add("wechatResult", slot)).textContent="微信配置已删除。";await loadStoreSettings(true);}catch(error){$(Exact.add("wechatResult", slot)).textContent=`删除失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}
}

function effectiveWechatV26(prefix){
  const manual=Exact.or(()=>($(Exact.add(prefix, "WechatOverride"))?.value?.trim()), ()=>("")),auto=Exact.or(()=>($(Exact.add(prefix, "WechatAuto"))?.value?.trim()), ()=>("")),add=Exact.or(()=>($(Exact.add(prefix, "WechatAdd"))?.value?.trim()), ()=>(""));
  if(Exact.truth(Exact.sneq(manual, "")))return Exact.decimal(Exact.currency(manual));if(Exact.truth(Exact.sneq(auto, "")))return Exact.add(Exact.decimal(Exact.currency(auto)), Exact.decimal(Exact.currency(add)));return Exact.decimal(Exact.currency(add));
}
function syncLedgerRevenueBreakdown(capture=true){
  const ids=["ledgerACash","ledgerBCash","ledgerAWechatAdd","ledgerAWechatAuto","ledgerAWechatOverride","ledgerAAlipayAdd","ledgerAAlipayOverride","ledgerBWechatAdd","ledgerBWechatAuto","ledgerBWechatOverride","ledgerBAlipayAdd","ledgerBAlipayOverride","ledgerStudentTakeout","ledgerATakeout","ledgerBTakeout"];
  /* An old desktop record has the split fields serialized as 0/0.00 even
     though its only real value is 总金额. Treat an all-zero split as empty;
     otherwise hydration would erase the legacy total and create a fake draft. */
  const hasMeaningfulPayment=ids.some(id=>{const value=Exact.or(()=>($(id)?.value?.trim()), ()=>(""));return Exact.and(()=>(Exact.sneq(value, "")), ()=>(Exact.sneq(Exact.decimal(Exact.currency(value)), 0)));});
  if(Exact.truth(Exact.and(()=>(Exact.not(hasMeaningfulPayment)), ()=>(Exact.seq(capture, false)))))return false;
  const cashA=Exact.decimal(Exact.currency($("ledgerACash").value)),cashB=Exact.decimal(Exact.currency($("ledgerBCash").value)),aWechat=effectiveWechatV26("ledgerA"),bWechat=effectiveWechatV26("ledgerB"),aAlipay=(Exact.truth(Exact.sneq($("ledgerAAlipayOverride").value.trim(), "")) ? Exact.decimal(Exact.currency($("ledgerAAlipayOverride").value)) : Exact.decimal(Exact.currency($("ledgerAAlipayAdd").value))),bAlipay=(Exact.truth(Exact.sneq($("ledgerBAlipayOverride").value.trim(), "")) ? Exact.decimal(Exact.currency($("ledgerBAlipayOverride").value)) : Exact.decimal(Exact.currency($("ledgerBAlipayAdd").value))),student=Exact.decimal(Exact.currency($("ledgerStudentTakeout").value)),aTakeout=Exact.decimal(Exact.currency($("ledgerATakeout").value)),bTakeout=Exact.decimal(Exact.currency($("ledgerBTakeout").value)),a=Exact.add(Exact.add(Exact.add(cashA, aWechat), aAlipay), aTakeout),b=Exact.add(Exact.add(Exact.add(cashB, bWechat), bAlipay), bTakeout);
  $("ledgerTotalCash").value=(Exact.add(cashA, cashB)).toFixed(2);$("ledgerTotalOnline").value=(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(aWechat, aAlipay), bWechat), bAlipay), student), aTakeout), bTakeout)).toFixed(2);$("ledgerARevenue").value=a.toFixed(2);$("ledgerBRevenue").value=b.toFixed(2);$("ledgerRevenue").value=(Exact.add(Exact.add(a, b), student)).toFixed(2);if(Exact.truth(capture))captureLedgerDraft();
  return true;
}
function installLedgerPaymentV26(){
  const grid=document.querySelector("#pageLedger .ledger-entry-grid");if(Exact.truth(Exact.or(()=>(Exact.not(grid)), ()=>($("ledgerAWechatAuto")))))return;
  for(const slot of ["A","B"]){
    const add=$((Exact.truth(Exact.seq(slot, "A")) ? "ledgerAWechatAdd" : "ledgerBWechatAdd"));if(Exact.truth(Exact.not(add)))continue;
    const label=document.createElement("label");label.textContent=`${slot}店微信 API（自动）`;label.className="hidden";
    const input=document.createElement("input");input.id=`ledger${slot}WechatAuto`;input.type="hidden";input.step="0.01";input.readOnly=true;
    add.parentNode.insertBefore(label,add.nextSibling);add.parentNode.insertBefore(input,label.nextSibling);
  }
  document.querySelectorAll("#pageLedger label").forEach(label=>{if(Exact.truth(label.textContent.includes("微信（覆盖）")))label.textContent=label.textContent.replace("微信（覆盖）","微信（手动覆盖）");if(Exact.truth(label.textContent.includes("支付宝（覆盖）")))label.textContent=label.textContent.replace("支付宝（覆盖）","支付宝（手动覆盖）");});
  const sync=$("syncWechatButton");if(Exact.truth(sync))sync.textContent=" 用微信Api更新未填写收入";
  $("syncWechatDayButton")?.addEventListener("click",()=>safely(()=>syncWechatBillV26(true)));
}
const v26RefreshLedgerBase=refreshLedger;
refreshLedger=function(){v26RefreshLedgerBase();const key=$("ledgerDate")?.value;if(Exact.truth(Exact.not(key)))return;const row=dailyRow(dayPayload(key),key);if(Exact.truth($("ledgerAWechatAuto")))$("ledgerAWechatAuto").value=(Exact.truth(entered(row.A店微信自动)) ? Exact.decimal(row.A店微信自动).toFixed(2) : "");if(Exact.truth($("ledgerBWechatAuto")))$("ledgerBWechatAuto").value=(Exact.truth(entered(row.B店微信自动)) ? Exact.decimal(row.B店微信自动).toFixed(2) : "");/* Hydration must never create a local draft. */syncLedgerRevenueBreakdown(false);applyStoreNames();};
async function syncWechatBillV26(force=false){
  const key=$("ledgerDate").value;if(Exact.truth(Exact.not(key)))throw new Error("请先选择要更新的日期。");if(Exact.truth(Exact.gte(key, isoDate(new Date()))))throw new Error("微信交易账单只能更新已经结束的历史日期；当天账单需次日上午生成后获取。");if(Exact.truth(Exact.not(state.dataset?.id)))throw new Error("当前没有可用账本。");
  if(Exact.truth(Exact.and(()=>(force), ()=>(Exact.not(confirm("强制更新会重新读取微信官方账单，并清除当天两家店的“微信手动覆盖”金额。确定继续吗？"))))))return;
  if(Exact.truth(Exact.and(()=>(state.editorDirty), ()=>(Exact.not(confirm("当前页面有未保存修改。更新微信账单会重新加载这一天，是否继续？"))))))return;
  const button=(Exact.truth(force) ? Exact.or(()=>($("syncWechatDayButton")), ()=>($("syncWechatButton"))) : $("syncWechatButton")),result=$("ledgerResult");if(Exact.truth(Exact.not(button)))throw new Error("找不到微信账单更新按钮。");button.disabled=true;result.textContent=(Exact.truth(force) ? "正在强制重新获取微信账单……" : "正在获取微信账单……");
  try{const response=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/wechat/sync?bill_date=${encodeURIComponent(key)}&force=${(Exact.truth(force) ? "true" : "false")}`,{method:"POST"});forgetEditorDraft("ledger",key);await loadCloudData({silent:true,datasetId:state.dataset.id});refreshLedger();renderHistory();renderDashboard();const stores=Exact.or(()=>(response?.stores), ()=>({})),parts=[];if(Exact.truth(stores.A))parts.push(`${storeName("A")}微信 ${money(stores.A.amount)}`);if(Exact.truth(stores.B))parts.push(`${storeName("B")}微信 ${money(stores.B.amount)}`);result.textContent=`${(Exact.truth(force) ? "强制" : "")}更新完成${(Exact.truth(parts.length) ? Exact.add("：", parts.join("；")) : "")}${(Exact.truth(response?.skipped_stores?.length) ? `；已保护非零数据：${response.skipped_stores.join("、")}` : "")}`;}catch(error){result.textContent=`${(Exact.truth(force) ? "强制" : "")}更新失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}finally{button.disabled=false;}
}
async function syncMissingWechatMonthV26(){const month=(Exact.or(()=>($("ledgerDate")?.value), ()=>(isoDate(new Date())))).slice(0,7),last=isoDate(new Date(Exact.sub(Date.now(), 86400000))),start=parseDate(`${month}-01`),end=parseDate(`${month}-${String(new Date(Exact.toNumber(month.slice(0,4)),Exact.toNumber(month.slice(5,7)),0).getDate()).padStart(2,"0")}`),result=$("ledgerResult"),button=$("syncWechatButton");button.disabled=true;let updated=0,skipped=0,failed=0;result.textContent=`正在更新 ${month} 尚未填写的收入……`;try{for(let day=new Date(start);Exact.truth(Exact.and(()=>(Exact.lte(day, end)), ()=>(Exact.lte(isoDate(day), last))));day.setDate(Exact.add(day.getDate(), 1))){const key=isoDate(day);const response=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/wechat/sync?bill_date=${encodeURIComponent(key)}&force=false`,{method:"POST"});(updated = Exact.add(updated, (Exact.truth(response?.changed) ? 1 : 0)));(skipped = Exact.add(skipped, (Exact.truth(Array.isArray(response?.skipped_stores)) ? response.skipped_stores.length : 0)));}await loadCloudData({silent:true,datasetId:state.dataset.id});refreshLedger();renderHistory();renderDashboard();result.textContent=`${month} 未填写收入更新完成：处理 ${updated} 天；已保护 ${skipped} 个已有收入的店铺。`;}catch(error){failed=1;result.textContent=`当月收入更新失败：${Exact.or(()=>(error.message), ()=>(error))}`;throw error;}finally{button.disabled=false;}}
syncWechatBill=function(){return syncMissingWechatMonthV26();};

function storeTotalsFor(metrics){return{a:metrics.reduce((s,m)=>Exact.add(s, Exact.decimal(Exact.currency(m?.storeA))),0),b:metrics.reduce((s,m)=>Exact.add(s, Exact.decimal(Exact.currency(m?.storeB))),0)};}
function injectStoreRows(cardId,a,b,sdMetrics=null){const list=$(cardId)?.querySelector(".metric-list");if(Exact.truth(Exact.not(list)))return;list.querySelectorAll(".v26-store-row").forEach(n=>n.remove());const first=list.firstElementChild;const valueA=(Exact.truth(sdMetrics) ? metricMoneySd(a,sdMetrics,"storeA") : money(a)),valueB=(Exact.truth(sdMetrics) ? metricMoneySd(b,sdMetrics,"storeB") : money(b));const html=`<div class="metric-row v26-store-row"><span>${escapeHtml(storeName("A"))}收入</span><strong>${valueA}</strong></div><div class="metric-row v26-store-row"><span>${escapeHtml(storeName("B"))}收入</span><strong>${valueB}</strong></div>`;if(Exact.truth(first))first.insertAdjacentHTML("afterend",html);else list.insertAdjacentHTML("beforeend",html);}
const v26DashboardBase=renderDashboard;
renderDashboard=function(){v26DashboardBase();const c=selectedContext(),all=dataDayMetrics().filter(m=>Exact.lte(m.date, isoDate(new Date()))),week=all.filter(m=>{const d=parseDate(m.date);return Exact.and(()=>(Exact.gte(d, c.weekStart)), ()=>(Exact.lte(d, c.weekEnd)));}),month=all.filter(m=>m.date.startsWith(`${c.year}-${String(c.month).padStart(2,"0")}`)),year=all.filter(m=>m.date.startsWith(`${c.year}-`));injectStoreRows("dayCard",Exact.or(()=>(c.day?.storeA), ()=>(0)),Exact.or(()=>(c.day?.storeB), ()=>(0)),Exact.or(()=>(c.monthAverageMetrics), ()=>(c.monthMetrics)));let t=storeTotalsFor(week);injectStoreRows("weekCard",t.a,t.b);t=storeTotalsFor(month);injectStoreRows("monthCard",t.a,t.b);t=storeTotalsFor(year);injectStoreRows("yearCard",t.a,t.b);applyStoreNames();};

renderHistory=function(){
  const month=Exact.or(()=>($("historyMonth").value), ()=>((Exact.or(()=>($("selectedDate").value), ()=>(""))).slice(0,7)));if(Exact.truth(Exact.not(month)))return;const table=$("historyRows")?.closest("table");if(Exact.truth(Exact.not(table)))return;
  table.querySelector("thead tr").innerHTML=`<th>日期</th><th>总收入</th><th>${escapeHtml(storeName("A"))}收入</th><th>${escapeHtml(storeName("B"))}收入</th><th>新客</th><th>总客数</th><th>食材总价格</th><th>佐料明细</th><th>当日总固定成本</th><th>其它明细</th><th>当日备注</th><th>毛利润（毛利率）</th><th>净利润（净利率）</th>`;
  const items=state.days.filter(row=>String(row.日期).startsWith(month));const rows=items.map(row=>{const m=dayMetrics(row);return `<tr><td>${escapeHtml(m.date)}</td><td>${money(m.revenue)}</td><td>${money(m.storeA)}</td><td>${money(m.storeB)}</td><td>${compactNumber(m.newCustomers)}</td><td>${compactNumber(m.customers)}</td><td>${money(m.food)}</td><td>${escapeHtml(Exact.or(()=>(row.佐料明细), ()=>("")))}</td><td>${money(m.fixedDaily)}</td><td>${escapeHtml(Exact.or(()=>(row.其他明细), ()=>("")))}</td><td>${escapeHtml(Exact.or(()=>(row.当日备注), ()=>("")))}</td><td>${pointValue("gross",m.gross,m.revenue)}</td><td>${pointValue("net",m.net,m.revenue)}</td></tr>`;}).join("");
  const fixed=fixedBreakdown(Exact.toNumber(month.slice(0,4)),Exact.toNumber(month.slice(5,7)));const fixedRow=`<tr class="month-summary-row"><td colspan="13"> ${month} 本月共享固定成本汇总 · 人工: ${money(fixed.labour)} · 房租: ${money(fixed.rent)} · 水费: ${money(fixed.water)} · 电费: ${money(fixed.electric)} · 煤气: ${money(fixed.gas)} · 其它: ${money(fixed.other)}</td></tr>`;const blanks=Array.from({length:Exact.math.max(0,Exact.sub(25, items.length))},()=>Exact.add(Exact.add('<tr class="blank-row">', Array.from({length:13},(_,i)=>`<td>${(Exact.truth(Exact.seq(i, 0)) ? '&nbsp;' : '')}</td>`).join("")), '</tr>')).join("");$("historyRows").innerHTML=Exact.add(Exact.add(fixedRow, rows), blanks);applyStoreNames();
};

async function bulkDeleteRangeV26(){
  const start=$("bulkDeleteStart").value,end=$("bulkDeleteEnd").value;if(Exact.truth(Exact.or(()=>(Exact.not(start)), ()=>(Exact.not(end)))))throw new Error("请选择开始和结束日期。");if(Exact.truth(Exact.lt(end, start)))throw new Error("结束日期不能早于开始日期。");
  if(Exact.truth(Exact.not(confirm(`确定删除 ${start} 至 ${end} 的全部日数据吗？菜品、采购明细和当天固定支出都会一起删除。`))))return;const typed=prompt('这是不可逆操作。请输入“删除”再次确认：','');if(Exact.truth(Exact.sneq(typed, "删除")))return;
  const result=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/records/bulk-delete`,{method:"POST",body:JSON.stringify({start_date:start,end_date:end,delete_month_records:false,delete_inventory_in_range:true})});$("bulkDeleteResult").textContent=`已删除 ${result.deleted_days} 天数据；清除 ${result.inventory_rows_removed} 条库存时间记录。`;await loadCloudData({datasetId:state.dataset.id});
}
async function bulkDeleteMonthV26(){
  const month=$("bulkDeleteMonth").value;if(Exact.truth(Exact.not(month)))throw new Error("请选择月份。");if(Exact.truth(Exact.not(confirm(`确定删除 ${month} 整月全部数据吗？这会同时删除该月固定成本。`))))return;const typed=prompt(`第二次确认：请输入月份 ${month}：`,"");if(Exact.truth(Exact.sneq(typed, month)))return;
  const result=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/records/delete-month`,{method:"POST",body:JSON.stringify({month,delete_inventory_in_month:true})});$("bulkDeleteResult").textContent=`${month} 已删除：${result.deleted_days} 天、${result.deleted_months} 条月记录、${result.inventory_rows_removed} 条库存记录。`;await loadCloudData({datasetId:state.dataset.id});
}
async function overwriteAnotherLedgerV26(){
  const targetId=$("overwriteTargetDataset").value,file=$("overwriteInternalFile").files?.[0];if(Exact.truth(Exact.not(targetId)))throw new Error("没有可选择的目标账本。");if(Exact.truth(Exact.not(file)))throw new Error("请选择整套内部 Excel。");const target=state.datasets.find(d=>Exact.seq(d.id, targetId));if(Exact.truth(Exact.not(confirm(`第一次确认：要用“${file.name}”整体覆盖目标账本“${Exact.or(()=>(target?.name), ()=>(targetId))}”吗？`))))return;if(Exact.truth(Exact.not(confirm(`第二次确认：目标账本“${Exact.or(()=>(target?.name), ()=>(targetId))}”现有经营数据将被内部 Excel 整体替换。确定执行？`))))return;
  const form=new FormData();form.append("confirm_target_name",target.name);form.append("confirm_again",target.name);form.append("file",file);$("overwriteLedgerResult").textContent="正在备份目标账本并整体覆盖……";const result=await api(`/datasets/${encodeURIComponent(targetId)}/workbooks/internal-overwrite`,{method:"POST",body:form});$("overwriteLedgerResult").textContent=`覆盖完成：新增 ${Exact.or(()=>(result.created), ()=>(0))}，更新 ${Exact.or(()=>(result.updated), ()=>(0))}，删除 ${Exact.or(()=>(result.deleted), ()=>(0))}；目标备份：${Exact.or(()=>(result.backup_path), ()=>("已创建"))}。`;
}
async function copyWholeLedgerV26(){
  const targetId=$("copyTargetDataset").value;if(Exact.truth(Exact.not(targetId)))throw new Error("没有可选择的目标账本。");const source=state.dataset,target=state.datasets.find(d=>Exact.seq(d.id, targetId));if(Exact.truth(Exact.not(confirm(`第一次确认：把当前账本“${source.name}”整套复制到“${Exact.or(()=>(target?.name), ()=>(targetId))}”？`))))return;if(Exact.truth(Exact.not(confirm(`第二次确认：目标账本“${Exact.or(()=>(target?.name), ()=>(targetId))}”现有数据会被整体覆盖。服务器会先备份目标账本。确定执行？`))))return;
  $("copyLedgerResult").textContent="正在备份目标账本并整体复制……";const result=await api(`/datasets/${encodeURIComponent(source.id)}/copy-to-ledger`,{method:"POST",body:JSON.stringify({target_dataset_id:targetId,confirm_source_name:source.name,confirm_target_name:target.name})});$("copyLedgerResult").textContent=`复制完成；目标备份：${result.backup_path}`;
}

function bindV26Events(){
  $("saveStoreNames")?.addEventListener("click",()=>safely(saveStoreNamesV26));
  for(const slot of ["A","B"]){document.querySelector(`[data-wechat-save="${slot}"]`)?.addEventListener("click",()=>safely(()=>saveWechatConfigV26(slot)));document.querySelector(`[data-wechat-test="${slot}"]`)?.addEventListener("click",()=>safely(()=>testWechatV26(slot)));document.querySelector(`[data-wechat-download="${slot}"]`)?.addEventListener("click",()=>safely(()=>downloadWechatBillV26(slot)));document.querySelector(`[data-wechat-delete="${slot}"]`)?.addEventListener("click",()=>safely(()=>deleteWechatV26(slot)));if(Exact.truth($(Exact.add("wechatBillDate", slot))))$(Exact.add("wechatBillDate", slot)).value=yesterdayIso();}
  $("bulkDeleteRange")?.addEventListener("click",()=>safely(bulkDeleteRangeV26));$("bulkDeleteWholeMonth")?.addEventListener("click",()=>safely(bulkDeleteMonthV26));$("overwriteAnotherLedger")?.addEventListener("click",()=>safely(overwriteAnotherLedgerV26));$("copyWholeLedger")?.addEventListener("click",()=>safely(copyWholeLedgerV26));
}

const v26LoadCloudBase=loadCloudData;
loadCloudData=async function(options={}){await v26LoadCloudBase(options);if(Exact.truth(state.dataset?.id))await loadStoreSettings(false);};
const v26ShowPageBase=showPage;
showPage=function(page){if(Exact.truth(Exact.and(()=>(Exact.or(()=>(Exact.or(()=>(Exact.seq(page, "stores")), ()=>(Exact.seq(page, "data")))), ()=>(Exact.seq(page, "users")))), ()=>(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(isTestAccount()))))))page="overview";const ok=v26ShowPageBase(page);if(Exact.truth(Exact.and(()=>(ok), ()=>(Exact.seq(page, "stores"))))){renderStoreSettings();loadStoreSettings(true);}if(Exact.truth(Exact.and(()=>(ok), ()=>(Exact.or(()=>(Exact.seq(page, "workbooks")), ()=>(Exact.seq(page, "data")))))))refreshV26DatasetTargets();return ok;};
const v26ApplyLanguageBase=applyLanguage;
applyLanguage=function(){v26ApplyLanguageBase();applyStoreNames();};

installV26Navigation();installLedgerPaymentV26();bindV26Events();
const today=isoDate(new Date());if(Exact.truth($("bulkDeleteStart")))$("bulkDeleteStart").value=today;if(Exact.truth($("bulkDeleteEnd")))$("bulkDeleteEnd").value=today;if(Exact.truth($("bulkDeleteMonth")))$("bulkDeleteMonth").value=today.slice(0,7);
const appView=$("appView");if(Exact.truth(appView)){new MutationObserver(()=>applyStoreNames(appView)).observe(appView,{childList:true,subtree:true});}
if(Exact.truth(Exact.and(()=>(state.token), ()=>(state.dataset?.id))))loadStoreSettings(true);else applyStoreNames();
