/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

const API = "/api/v1";
const SESSION_TTL = Exact.mul(Exact.mul(Exact.mul(2, 60), 60), 1000);
const state = { token: "", user: null, datasets: [], dataset: null, records: [], days: [], dayRowsByDate: new Map(), dayRecordMap: new Map(), months: new Map(), recordMap: new Map(), entryWindows: [], cashPosition: null, language: Exact.or(()=>(localStorage.getItem("restaurant_language")), ()=>("zh")), activePage: "overview", autoRefresh: null, refreshBusy: false, pendingDatasetId: "", editorDirty: false, editorDrafts: Object.create(null), editorBaselines: Object.create(null) };
const $ = (id) => document.getElementById(id);
const colors = ["#365f96", "#7994b8", "#586d84", "#a5b5ca", "#84909d", "#bcc7d5", "#526b8b", "#ced5df"];

const metricText = {
  revenue:["收入 (Revenue)","Revenue"], fixed:["固定成本","Fixed Cost"], fixedTotal:["总固定成本","Total Fixed Cost"], variable:["(总成本 - 固定成本)","(Total Cost - Fixed Cost)"], total:["总成本","Total Cost"], totalExpense:["总支出","Total Expenditure"], dish:["“当日做出的菜品”所用成本","Dish Ingredient Cost"], gross:["毛利润 (毛利率)","Gross Profit (Margin)"], net:["净利润 (净利率)","Net Profit (Margin)"], customers:["总客人数","Total Customers"], ticket:["平均客单价","Average Spend per Customer"], food:["食材成本","Ingredient Cost"], spice:["佐料成本","Seasoning Cost"], labour:["人工分摊","Labour Allocation"], rent:["房租分摊","Rent Allocation"], water:["水费分摊","Water Allocation"], electric:["电费分摊","Electricity Allocation"], gas:["煤气分摊","Gas Allocation"], other:["其它","Other"], avgRevenue:["日均收入","Average Daily Revenue"], avgVariable:["日均 (总成本 - 固定成本)","Average Daily Variable Cost"], avgGross:["日均毛利润 (毛利率)","Average Daily Gross Profit (Margin)"], avgNet:["日均净利润 (净利率)","Average Daily Net Profit (Margin)"], monthGross:["月均毛利润 (毛利率)","Average Monthly Gross Profit (Margin)"], monthNet:["月均净利润 (净利率)","Average Monthly Net Profit (Margin)"]
};
function trPair(pair){ return pair[(Exact.truth(Exact.seq(state.language, "en")) ? 1 : 0)]; }
function mt(key){ return trPair(Exact.or(()=>(metricText[key]), ()=>([key,key]))); }
function setSession(token, user) { const payload={token,user,expiresAt:Exact.add(Date.now(), SESSION_TTL)}; localStorage.setItem("restaurant_session",JSON.stringify(payload)); state.token=token; state.user=Exact.or(()=>(user), ()=>(null)); }
function restoreSession() { try { const value=JSON.parse(Exact.or(()=>(localStorage.getItem("restaurant_session")), ()=>("null"))); if(Exact.truth(Exact.and(()=>(value?.token), ()=>(Exact.gt(Exact.toNumber(value.expiresAt), Date.now()))))){state.token=value.token;state.user=Exact.or(()=>(value.user), ()=>(null));return true;} } catch(_){} localStorage.removeItem("restaurant_session"); return false; }
function touchSession(){
  /* Only actual user input calls this function.  Background polling must not
     turn an inactive browser into a permanently logged-in session. */
  if(Exact.truth(Exact.not(state.token)))return;
  try{
    const value=JSON.parse(Exact.or(()=>(localStorage.getItem("restaurant_session")), ()=>("{}")));
    value.expiresAt=Exact.add(Date.now(), SESSION_TTL);value.lastActivityAt=Date.now();
    value.token=state.token;value.user=state.user;
    localStorage.setItem("restaurant_session",JSON.stringify(value));
  }catch(_){}
}
function isTestAccount(){ return Exact.seq(String(Exact.or(()=>(state.user?.username), ()=>(""))).trim().toLowerCase(), "test"); }

function money(value) { const text=Exact.decimal(Exact.or(()=>(value), ()=>(0))).toLocaleString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN"), {minimumFractionDigits:2, maximumFractionDigits:2}); return (Exact.truth(Exact.seq(state.language, "en")) ? `CNY ${text}` : `${text} 元`); }
function percent(value, base) { return (Exact.truth(base) ? `${(Exact.mul(Exact.div(value, base), 100)).toFixed(1)}%` : "0.0%"); }
function num(value) { return Exact.decimal(value); }
function entered(value) { return Exact.and(()=>(Exact.and(()=>(Exact.and(()=>(Exact.sneq(value, null)), ()=>(Exact.sneq(value, undefined)))), ()=>(Exact.sneq(String(value).trim(), "")))), ()=>(Exact.not(["nan","none"].includes(String(value).toLowerCase())))); }
function escapeHtml(text) { return String(text ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c])); }
function isoDate(date) { return `${date.getFullYear()}-${String(Exact.add(date.getMonth(), 1)).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`; }
function parseDate(text) { const [y,m,d] = text.split("-").map(Number); return new Date(y,Exact.sub(m, 1),d); }
function daysInMonth(year, month) { return new Date(year, month, 0).getDate(); }

async function api(path, options = {}) {
  if (Exact.truth(Exact.seq(location.protocol, "file:"))) return mockApi(path,options);
  const headers = {Accept:"application/json", ...(Exact.or(()=>(options.headers), ()=>({})))};
  if (Exact.truth(Exact.and(()=>(Exact.and(()=>(options.body), ()=>(Exact.not(options.body instanceof FormData)))), ()=>(Exact.not(headers["Content-Type"]))))) headers["Content-Type"] = "application/json";
  if (Exact.truth(state.token)) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${API}${path}`, {...options, headers});
  let payload = null;
  try { payload = await response.json(); } catch (_) {}
  if (Exact.truth(Exact.not(response.ok))) {
    if (Exact.truth(Exact.and(()=>(Exact.seq(response.status, 401)), ()=>(Exact.not(["/auth/login","/auth/test-login"].includes(path)))))) logout(true);
    const detail = payload?.detail;
    const detailMessage = (Exact.truth(Exact.seq(typeof detail, "string")) ? detail : Exact.or(()=>(detail?.message), ()=>("")));
    const error = new Error(Exact.or(()=>(detailMessage), ()=>(`请求失败（${response.status}）`)));error.status=response.status;error.detail=detail;throw error;
  }
  return payload;
}

let previewUser = {username:"admin",display_name:"演示管理员",role:"admin",default_dataset_id:"preview"};
let previewDatasets = [
  {id:"preview",name:"餐饮成本管家（界面预览）",is_active:true,is_test:false},
  {id:"test-demo-v1",name:"Test 独立演示账本",is_active:true,is_test:true},
];
const previewRecordStores=new Map();
function previewRecords(datasetId){
  if(Exact.truth(previewRecordStores.has(datasetId)))return previewRecordStores.get(datasetId);
  const revenues=[3200,11020,3342,1241,2322,2223,1221,2422],foods=[331,331,331,331,331,331,331,331];
  const records=revenues.map((revenue,index)=>{const day=Exact.add(12, index),key=`2026-07-${String(day).padStart(2,"0")}`,dish=(Exact.truth(Exact.seq(index, Exact.sub(revenues.length, 1))) ? {dishes:[{日期:key,菜品数据:JSON.stringify([{菜品名称:"胡萝卜汤",菜品份数:12,食材明细:JSON.stringify([{name:"胡萝卜",quantity:3,unit:"公斤",price:8,total:24,note:""}]),成本:24,备注:""}])}]} : {});return{record_type:"day",record_key:key,version:1,payload:{daily:[{日期:key,收益:revenue,食材成本:foods[index],佐料成本:0,水电:0,其他:0,总客人数:Exact.add(30, index),新客人数量:5}],...dish}};});
  records.push({record_type:"month",record_key:"2026-07",version:1,payload:{monthly_fixed:[{月份:"2026-07",人工总额:3100,房租总额:6200,水费支出:310,电费支出:0,实际使用水费:3000,实际使用电费:300,煤气费:310,其它固定成本:0}]}});
  records.push({record_type:"global",record_key:"ingredients",version:1,payload:{ingredients:[{词条名称:"胡萝卜",分类:"食材"},{词条名称:"土豆",分类:"食材"},{词条名称:"盐",分类:"佐料"}]}});
  records.push({record_type:"global",record_key:"inventory",version:1,payload:{entries:[{id:"preview-stock-1",date:"2026-07-12",category:"食材",name:"胡萝卜",quantity:10,unit:"公斤",unit_price:8,total:80,note:"首批入库"},{id:"preview-stock-2",date:"2026-07-15",category:"食材",name:"土豆",quantity:18,unit:"公斤",unit_price:6,total:108,note:""},{id:"preview-stock-3",date:"2026-07-15",category:"佐料",name:"盐",quantity:4,unit:"袋",unit_price:3,total:12,note:""}]}});
  previewRecordStores.set(datasetId,records);return records;
}
function mockApi(path,options={}) {
  if (Exact.truth(Exact.seq(path, "/auth/login"))) { previewUser={username:"admin",display_name:"演示管理员",role:"admin",default_dataset_id:"preview"}; return Promise.resolve({access_token:"preview",user:previewUser}); }
  if (Exact.truth(Exact.seq(path, "/auth/test-login"))) { previewUser={username:"Test",display_name:"Test 演示",role:"viewer",default_dataset_id:"test-demo-v1"}; return Promise.resolve({access_token:"preview",user:previewUser}); }
  if (Exact.truth(Exact.seq(path, "/auth/me"))) return Promise.resolve(Exact.or(()=>(state.user), ()=>(previewUser)));
  if (Exact.truth(Exact.and(()=>(Exact.seq(path, "/datasets")), ()=>(Exact.seq(options.method, "POST"))))) {
    const body=JSON.parse(Exact.or(()=>(options.body), ()=>("{}"))),created={id:String(Exact.or(()=>(body.id), ()=>(""))),name:String(Exact.or(()=>(Exact.or(()=>(body.name), ()=>(body.id))), ()=>(""))),is_active:true,is_test:false};
    if(Exact.truth(Exact.or(()=>(Exact.not(created.id)), ()=>(previewDatasets.some(item=>Exact.seq(item.id, created.id))))))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "That ledger ID is already in use." : "该账本 ID 已存在。")));
    previewDatasets.push(created);return Promise.resolve(created);
  }
  if (Exact.truth(Exact.seq(path, "/datasets"))) return Promise.resolve((Exact.truth(Exact.seq(previewUser.role, "admin")) ? previewDatasets : previewDatasets.filter(item=>Exact.seq(item.id, previewUser.default_dataset_id))));
  const datasetMatch=path.match(/^\/datasets\/([^/?]+)(?:\?([^#]*))?$/);
  if(Exact.truth(Exact.and(()=>(datasetMatch), ()=>(Exact.seq(options.method, "PATCH"))))){
    const id=decodeURIComponent(datasetMatch[1]),index=previewDatasets.findIndex(item=>Exact.seq(item.id, id)),body=JSON.parse(Exact.or(()=>(options.body), ()=>("{}")));
    if(Exact.truth(Exact.lt(index, 0)))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Ledger not found." : "账本不存在。")));
    previewDatasets[index]={...previewDatasets[index],name:String(Exact.or(()=>(body.name), ()=>(previewDatasets[index].name)))};return Promise.resolve(previewDatasets[index]);
  }
  if(Exact.truth(Exact.and(()=>(datasetMatch), ()=>(Exact.seq(options.method, "DELETE"))))){
    const id=decodeURIComponent(datasetMatch[1]),index=previewDatasets.findIndex(item=>Exact.seq(item.id, id)),dataset=previewDatasets[index],query=new URLSearchParams(Exact.or(()=>(datasetMatch[2]), ()=>("")));
    if(Exact.truth(Exact.lt(index, 0)))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Ledger not found." : "账本不存在。")));
    if(Exact.truth(dataset.is_test))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "The Test demonstration ledger cannot be deleted." : "Test 独立演示账本不可删除。")));
    if(Exact.truth(Exact.sneq(query.get("confirm_name"), dataset.name)))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "The confirmation name does not match." : "确认名称不一致。")));
    previewDatasets.splice(index,1);if(Exact.truth(Exact.seq(previewUser.default_dataset_id, id)))previewUser={...previewUser,default_dataset_id:Exact.or(()=>(previewDatasets[0]?.id), ()=>(null))};return Promise.resolve(null);
  }
  if (Exact.truth(Exact.seq(path, "/users"))) return Promise.resolve([]);
  const wechatSyncMatch=path.match(/^\/datasets\/([^/]+)\/wechat\/sync\?bill_date=(\d{4}-\d{2}-\d{2})$/);
  if(Exact.truth(Exact.and(()=>(wechatSyncMatch), ()=>(Exact.seq(options.method, "POST"))))){
    const datasetId=decodeURIComponent(wechatSyncMatch[1]),day=wechatSyncMatch[2],records=previewRecords(datasetId),index=records.findIndex(item=>Exact.and(()=>(Exact.seq(item.record_type, "day")), ()=>(Exact.seq(item.record_key, day)))),record=(Exact.truth(Exact.gte(index, 0)) ? records[index] : {record_type:"day",record_key:day,version:0,payload:{daily:[{日期:day}]}});
    const payload=clone(Exact.or(()=>(record.payload), ()=>({}))),row=clone(Exact.or(()=>((Exact.or(()=>(payload.daily), ()=>([]))).slice(Exact.neg(1))[0]), ()=>({日期:day})));row.A店微信覆盖=888.88;row.总现金=Exact.add(Exact.decimal(Exact.currency(row.A店现金)), Exact.decimal(Exact.currency(row.B店现金)));row.A店收入=Exact.add(Exact.add(Exact.decimal(Exact.currency(row.A店现金)), 888.88), (Exact.truth(entered(row.A店支付宝覆盖)) ? Exact.decimal(Exact.currency(row.A店支付宝覆盖)) : Exact.decimal(Exact.currency(row.A店支付宝增加))));row.B店收入=Exact.add(Exact.add(Exact.decimal(Exact.currency(row.B店现金)), (Exact.truth(entered(row.B店微信覆盖)) ? Exact.decimal(Exact.currency(row.B店微信覆盖)) : Exact.decimal(Exact.currency(row.B店微信增加)))), (Exact.truth(entered(row.B店支付宝覆盖)) ? Exact.decimal(Exact.currency(row.B店支付宝覆盖)) : Exact.decimal(Exact.currency(row.B店支付宝增加))));row.总线上=Exact.sub(Exact.add(row.A店收入, row.B店收入), row.总现金);row.收益=Exact.add(row.A店收入, row.B店收入);payload.daily=[row];const saved={...record,payload,version:Exact.add(Exact.toNumber(Exact.or(()=>(record.version), ()=>(0))), 1),is_deleted:false};if(Exact.truth(Exact.gte(index, 0)))records[index]=saved;else records.push(saved);return Promise.resolve({changed:true,bill_date:day,revenue:row.收益,stores:{A:{amount:888.88,payment_amount:888.88,refund_amount:0,payment_count:12,refund_count:0}}});
  }
  const recordWriteMatch=path.match(/^\/datasets\/([^/]+)\/records\/([^/]+)\/(.+)$/);
  if(Exact.truth(Exact.and(()=>(recordWriteMatch), ()=>(Exact.seq(options.method, "PUT"))))){
    const datasetId=decodeURIComponent(recordWriteMatch[1]),type=decodeURIComponent(recordWriteMatch[2]),key=decodeURIComponent(recordWriteMatch[3]),body=JSON.parse(Exact.or(()=>(options.body), ()=>("{}"))),records=previewRecords(datasetId),index=records.findIndex(item=>Exact.and(()=>(Exact.seq(item.record_type, type)), ()=>(Exact.seq(item.record_key, key)))),saved={record_type:type,record_key:key,payload:Exact.or(()=>(body.payload), ()=>({})),checksum:Exact.or(()=>(body.checksum), ()=>("")),version:(Exact.truth(Exact.gte(index, 0)) ? Exact.add(Exact.toNumber(Exact.or(()=>(records[index].version), ()=>(0))), 1) : 1),is_deleted:false};
    if(Exact.truth(Exact.gte(index, 0)))records[index]=saved;else records.push(saved);return Promise.resolve(saved);
  }
  const recordsMatch=path.match(/^\/datasets\/([^/]+)\/records(?:\?|$)/);
  if (Exact.truth(recordsMatch)) {
    const datasetId=decodeURIComponent(recordsMatch[1]);
    if(Exact.truth(Exact.not(previewDatasets.some(item=>Exact.seq(item.id, datasetId)))))return Promise.reject(new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Ledger not found." : "账本不存在。")));
    return Promise.resolve(previewRecords(datasetId));
  }
  return Promise.reject(new Error("预览接口不存在"));
}

function filenameFromDisposition(response, fallback) {
  const raw = Exact.or(()=>(response.headers.get("Content-Disposition")), ()=>(""));
  const utf = raw.match(/filename\*=UTF-8''([^;]+)/i);
  const plain = raw.match(/filename="?([^";]+)"?/i);
  try { return decodeURIComponent((Exact.or(()=>(Exact.or(()=>(utf?.[1]), ()=>(plain?.[1]))), ()=>(fallback))).trim()); } catch (_) { return fallback; }
}

async function downloadApiFile(path, fallbackName) {
  if (Exact.truth(Exact.seq(location.protocol, "file:"))) throw new Error("文件下载需要连接云端 API。");
  const headers = {Accept:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"};
  if (Exact.truth(state.token)) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(`${API}${path}`, {headers});
  if (Exact.truth(Exact.not(response.ok))) {
    let detail = ""; try { detail = (await response.json())?.detail || ""; } catch (_) {}
    if (Exact.truth(Exact.seq(response.status, 401))) logout(true);
    throw new Error((Exact.truth(Exact.and(()=>(Exact.seq(typeof detail, "string")), ()=>(detail))) ? detail : `下载失败（${response.status}）`));
  }
  const blob = await response.blob(), link = document.createElement("a"), url = URL.createObjectURL(blob);
  link.href = url; link.download = filenameFromDisposition(response, fallbackName); document.body.appendChild(link); link.click(); link.remove();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
}

async function login(event) {
  event.preventDefault();
  const button = Exact.or(()=>(event.submitter), ()=>($("loginForm").querySelector('button[type="submit"]')));
  button.disabled = true; $("loginError").textContent = "";
  try {
    const result = await api("/auth/login", {method:"POST", body:JSON.stringify({username:$("username").value.trim(), password:$("password").value})});
    state.token = result.access_token; state.user = Exact.or(()=>(result.user), ()=>({username:$("username").value.trim()}));
    localStorage.setItem("restaurant_last_username",$("username").value.trim());
    setSession(state.token,state.user);
    await enterApp();
  } catch (error) { $("loginError").textContent = error.message; }
  finally { button.disabled = false; }
}

async function loginAsTest() {
  const button = $("testLoginButton"); button.disabled = true; $("loginError").textContent = "";
  try {
    const result = await api("/auth/test-login", {method:"POST"});
    state.token = result.access_token; state.user = Exact.or(()=>(result.user), ()=>({username:"Test",role:"viewer"}));
    setSession(state.token,state.user); await enterApp();
  } catch (error) { $("loginError").textContent = error.message; }
  finally { button.disabled = false; }
}

function logout(expired=false) {
  if(Exact.truth(Exact.and(()=>(Exact.not(expired)), ()=>(state.editorDirty)))){allowEditorNavigation(()=>logout(false));return;}
  if(Exact.truth(Exact.seq(typeof stopEntryTimingTicker, "function")))stopEntryTimingTicker();
  state.token=""; state.user=null; state.datasets=[]; state.dataset=null; state.records=[]; state.days=[]; state.dayRowsByDate=new Map(); state.dayRecordMap=new Map(); state.months=new Map();state.recordMap=new Map();state.entryWindows=[];state.cashPosition=null;state.pendingDatasetId="";
  clearEditorDrafts();
  localStorage.removeItem("restaurant_session");
  if(Exact.truth(state.autoRefresh)){clearInterval(state.autoRefresh);state.autoRefresh=null;}
  showPage("overview");
  $("userNavButton").classList.add("hidden");
  $("datasetSelectWrap").classList.add("hidden");
  $("appView").classList.add("hidden");$("bootView").classList.add("hidden");$("loginView").classList.remove("hidden");document.body.classList.remove("booting");
  if(Exact.truth(expired)) $("loginError").textContent=(Exact.truth(Exact.seq(state.language, "en")) ? "Your two-hour session has expired. Please sign in again." : "登录已超过两小时，请重新登录。");
}

async function enterApp() {
  if (Exact.truth(state.token)) state.user = await api("/auth/me");
  setSession(state.token,state.user);touchSession();
  $("bootView").classList.add("hidden");$("loginView").classList.add("hidden"); $("appView").classList.remove("hidden");document.body.classList.remove("booting");
  $("accountLabel").textContent = Exact.or(()=>(Exact.or(()=>(state.user?.display_name), ()=>(state.user?.username))), ()=>("已登录"));
  const role = Exact.or(()=>(state.user?.role), ()=>((Exact.truth(Exact.seq(state.user?.username, "admin")) ? "admin" : "viewer")));
  const canEdit = ["admin","editor","entry"].includes(role);
  if(Exact.truth(Exact.seq(typeof startEntryTimingTicker, "function")))startEntryTimingTicker();
  document.body.classList.toggle("read-only", Exact.not(canEdit));
  $("ledgerPermission").textContent = (Exact.truth(canEdit) ? (Exact.truth(Exact.seq(state.language, "en")) ? "Editable" : "可修改") : (Exact.truth(Exact.seq(state.language, "en")) ? "Read only" : "只读账号"));
  $("inventoryPermission").textContent = (Exact.truth(canEdit) ? (Exact.truth(Exact.seq(state.language, "en")) ? "Editable" : "可修改") : (Exact.truth(Exact.seq(state.language, "en")) ? "Read only" : "只读账号"));
  $("userNavButton").classList.toggle("hidden", Exact.or(()=>(Exact.sneq(role, "admin")), ()=>(isTestAccount())));
  $("changeLogNavButton")?.classList.toggle("hidden", Exact.or(()=>(Exact.not(["admin","editor"].includes(role))), ()=>(isTestAccount())));
  // Data Management is an administrator-only surface. Hide both its tab and
  // page root so a non-admin cannot reveal it through a stale route or DOM.
  document.querySelectorAll('[data-page="data"]').forEach(node=>node.classList.toggle("hidden",Exact.or(()=>(Exact.sneq(role, "admin")), ()=>(isTestAccount()))));
  $("pageData")?.classList.toggle("hidden",Exact.or(()=>(Exact.or(()=>(Exact.sneq(role, "admin")), ()=>(isTestAccount()))), ()=>(Exact.sneq(state.activePage, "data"))));
  document.querySelectorAll(".admin-only").forEach(node=>node.classList.toggle("hidden",Exact.sneq(role, "admin")));
  $("uploadUserWorkbookLabel").classList.toggle("hidden",Exact.sneq(role, "admin"));
  $("mergeUserWorkbookLabel").classList.toggle("hidden",Exact.sneq(role, "admin"));
  $("userWorkbookYear").value=String(new Date().getFullYear());
  await loadCloudData();
  if(Exact.truth(state.autoRefresh))clearInterval(state.autoRefresh);
  state.autoRefresh=setInterval(()=>loadCloudData({silent:true}),5000);
}

async function fetchAllRecords(datasetId) {
  const all = []; let offset = 0;
  while (Exact.truth(true)) {
    const page = await api(`/datasets/${encodeURIComponent(datasetId)}/records?include_deleted=false&offset=${offset}&limit=5000`);
    const batch = (Exact.truth(Array.isArray(page)) ? page : Exact.or(()=>(page?.items), ()=>([])));
    all.push(...batch);
    if (Exact.truth(Exact.lt(batch.length, 5000))) break;
    (offset = Exact.add(offset, batch.length));
  }
  return all;
}

function unpackPayload(record) {
  let payload = record?.payload ?? record?.data ?? {};
  if (Exact.truth(Exact.seq(typeof payload, "string"))) { try { payload = JSON.parse(payload); } catch (_) { payload = {}; } }
  return (Exact.truth(Exact.and(()=>(payload), ()=>(Exact.seq(typeof payload, "object")))) ? payload : {});
}

function normalizeDateKey(value) {
  if (Exact.truth(Exact.and(()=>(value instanceof Date), ()=>(Exact.not(Number.isNaN(value.getTime())))))) return isoDate(value);
  const text = String(value ?? "").trim();
  if (Exact.truth(Exact.not(text))) return "";
  /* The desktop builds have used ISO, slash-separated and Chinese date
     strings over time.  Parse only the leading calendar date so a timestamp
     cannot move the day because of a browser timezone conversion. */
  const match = text.match(/^(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*(?:日)?(?:$|[T\s])/);
  if (Exact.truth(Exact.not(match))) return text;
  const year = Exact.toNumber(match[1]), month = Exact.toNumber(match[2]), day = Exact.toNumber(match[3]);
  if (Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.not(Exact.integer(year))), ()=>(Exact.lt(month, 1)))), ()=>(Exact.gt(month, 12)))), ()=>(Exact.lt(day, 1)))), ()=>(Exact.gt(day, daysInMonth(year, month)))))) return text;
  return `${String(year).padStart(4,"0")}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
}
function normalizeMonthKey(value) {
  const text = String(value ?? "").trim();
  const match = text.match(/^(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:月)?(?:$|[T\s])/);
  if (Exact.truth(Exact.not(match))) return text;
  const year = Exact.toNumber(match[1]), month = Exact.toNumber(match[2]);
  return (Exact.truth(Exact.and(()=>(Exact.gte(month, 1)), ()=>(Exact.lte(month, 12)))) ? `${String(year).padStart(4,"0")}-${String(month).padStart(2,"0")}` : text);
}
function isCanonicalDate(value) { return /^\d{4}-\d{2}-\d{2}$/.test(String(Exact.or(()=>(value), ()=>("")))); }
function legacyRevenueValue(row) {
  if (Exact.truth(Exact.or(()=>(Exact.not(row)), ()=>(Exact.sneq(typeof row, "object"))))) return undefined;
  /* A real payment/store split is newer and more specific than a stale
     total-only field left by an older desktop build.  Check it first so a
     row such as 总金额=2539 + A店微信增加=100 resolves to 100. */
  const breakdown = paymentBreakdownRevenue(row);
  if (Exact.truth(hasMeaningfulDayBreakdown(row))) return breakdown;
  let sawDirect = false;
  const direct = [row.收益, row.总金额, row.收入, row.总收入].find(value => Exact.and(()=>(entered(value)), ()=>(Exact.sneq(Exact.decimal(Exact.currency(value)), 0))));
  if (Exact.truth(Exact.sneq(direct, undefined))) return direct;
  [row.收益, row.总金额, row.收入, row.总收入].forEach(value => { if (Exact.truth(entered(value))) sawDirect = true; });
  /* Some intermediate desktop builds wrote only the two derived store
     columns.  They are still a valid total when no legacy total exists. */
  if (Exact.truth(Exact.and(()=>(Exact.sneq(breakdown, undefined)), ()=>(Exact.sneq(breakdown, 0))))) return breakdown;
  return (Exact.truth(Exact.or(()=>(sawDirect), ()=>(Exact.sneq(breakdown, undefined)))) ? 0 : undefined);
}
function dayRowsFromPayload(payload, recordKey="") {
  if (Exact.truth(Array.isArray(payload?.daily))) return payload.daily;
  /* A very old local workbook could be uploaded as one bare row instead of
     {daily:[row]}.  Detect it conservatively so fixed/global payloads are not
     mistaken for income rows. */
  const fields = ["日期","收益","总金额","收入","总收入","A店收入","B店收入","学生外卖","A店外卖","B店外卖","总客人数","食材成本","佐料成本"];
  if (Exact.truth(Exact.and(()=>(Exact.and(()=>(payload), ()=>(Exact.seq(typeof payload, "object")))), ()=>(fields.some(name => Object.prototype.hasOwnProperty.call(payload,name)))))) {
    return [{...payload, 日期:Exact.or(()=>(payload.日期), ()=>(recordKey))}];
  }
  return [];
}
const legacyRevenueFields = new Set(["收益","总金额","收入","总收入","A店收入","B店收入"]);
const paymentBreakdownFields = [
  "A店现金","B店现金","总现金","总线上",
  "A店微信增加","A店微信自动","A店微信覆盖","A店支付宝增加","A店支付宝覆盖",
  "B店微信增加","B店微信自动","B店微信覆盖","B店支付宝增加","B店支付宝覆盖",
  "A店收入","B店收入","学生外卖","A店外卖","B店外卖",
];
function paymentBreakdownRevenue(row) {
  if (Exact.truth(Exact.or(()=>(Exact.not(row)), ()=>(Exact.sneq(typeof row, "object"))))) return undefined;
  const hasAny = paymentBreakdownFields.some(field => entered(row[field]));
  if (Exact.truth(Exact.not(hasAny))) return undefined;
  const rawPaymentFields = paymentBreakdownFields.filter(field => Exact.not(["总现金","总线上","A店收入","B店收入"].includes(field)));
  const hasNonzeroRawPayment = rawPaymentFields.some(field => Exact.and(()=>(entered(row[field])), ()=>(Exact.sneq(Exact.decimal(Exact.currency(row[field])), 0))));
  const effectiveWechat = prefix => {
    const manual = row[`${prefix}微信覆盖`], automatic = row[`${prefix}微信自动`], added = row[`${prefix}微信增加`];
    if (Exact.truth(entered(manual))) return Exact.decimal(Exact.currency(manual));
    if (Exact.truth(entered(automatic))) return Exact.add(Exact.decimal(Exact.currency(automatic)), Exact.decimal(Exact.currency(added)));
    return Exact.decimal(Exact.currency(added));
  };
  const effectiveAlipay = prefix => (Exact.truth(entered(row[`${prefix}支付宝覆盖`])) ? Exact.decimal(Exact.currency(row[`${prefix}支付宝覆盖`])) : Exact.decimal(Exact.currency(row[`${prefix}支付宝增加`])));
  /* Raw payment inputs are newer and more precise than derived A/B columns.
     A non-zero raw field must therefore win even when an override reduces the
     effective total to exactly zero. */
  if (Exact.truth(hasNonzeroRawPayment)) {
    return Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add((Exact.truth(entered(row.A店现金)) ? Exact.decimal(Exact.currency(row.A店现金)) : 0), (Exact.truth(entered(row.B店现金)) ? Exact.decimal(Exact.currency(row.B店现金)) : 0)), effectiveWechat("A店")), effectiveAlipay("A店")), effectiveWechat("B店")), effectiveAlipay("B店")), Exact.decimal(Exact.currency(row.A店外卖))), Exact.decimal(Exact.currency(row.B店外卖))), Exact.decimal(Exact.currency(row.学生外卖)));
  }
  const storeA = (Exact.truth(entered(row.A店收入)) ? Exact.decimal(Exact.currency(row.A店收入)) : 0);
  const storeB = (Exact.truth(entered(row.B店收入)) ? Exact.decimal(Exact.currency(row.B店收入)) : 0);
  if (Exact.truth(Exact.or(()=>(Exact.sneq(storeA, 0)), ()=>(Exact.sneq(storeB, 0))))) return Exact.add(Exact.add(storeA, storeB), Exact.decimal(Exact.currency(row.学生外卖)));
  const totalCash = (Exact.truth(entered(row.总现金)) ? Exact.decimal(Exact.currency(row.总现金)) : 0);
  const totalOnline = (Exact.truth(entered(row.总线上)) ? Exact.decimal(Exact.currency(row.总线上)) : 0);
  if (Exact.truth(Exact.or(()=>(Exact.sneq(totalCash, 0)), ()=>(Exact.sneq(totalOnline, 0))))) return Exact.add(totalCash, totalOnline);
  return Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(Exact.add((Exact.truth(entered(row.A店现金)) ? Exact.decimal(Exact.currency(row.A店现金)) : 0), (Exact.truth(entered(row.B店现金)) ? Exact.decimal(Exact.currency(row.B店现金)) : 0)), effectiveWechat("A店")), effectiveAlipay("A店")), effectiveWechat("B店")), effectiveAlipay("B店")), Exact.decimal(Exact.currency(row.A店外卖))), Exact.decimal(Exact.currency(row.B店外卖))), Exact.decimal(Exact.currency(row.学生外卖)));
}
function hasMeaningfulDayBreakdown(row) {
  return Exact.and(()=>(Exact.not(Exact.not(row))), ()=>(paymentBreakdownFields.some(field => Exact.and(()=>(entered(row[field])), ()=>(Exact.sneq(num(row[field]), 0))))));
}
/* Resolve one store's income from the same payment precedence used by the
   cloud API. A/B columns are derived in newer records, while older rows may
   contain only cash/WeChat/Alipay fields or a total-only 收益 value. */
function storeRevenueValue(row, slot) {
  if (Exact.truth(Exact.or(()=>(Exact.not(row)), ()=>(Exact.not(slot))))) return 0;
  const prefix = `${slot}店`;
  const directKey = `${prefix}收入`, cashKey = `${prefix}现金`;
  const wechatAdd = `${prefix}微信增加`, wechatAuto = `${prefix}微信自动`, wechatOverride = `${prefix}微信覆盖`;
  const alipayAdd = `${prefix}支付宝增加`, alipayOverride = `${prefix}支付宝覆盖`;
  const takeoutKey = `${prefix}外卖`;
  const rawKeys = [cashKey, wechatAdd, wechatAuto, wechatOverride, alipayAdd, alipayOverride, takeoutKey];
  const hasRaw = rawKeys.some(key => Exact.and(()=>(entered(row[key])), ()=>(Exact.sneq(Exact.decimal(Exact.currency(row[key])), 0))));
  if (Exact.truth(Exact.and(()=>(Exact.not(hasRaw)), ()=>(entered(row[directKey]))))) return Exact.decimal(Exact.currency(row[directKey]));
  const wechat = (Exact.truth(entered(row[wechatOverride])) ? Exact.decimal(Exact.currency(row[wechatOverride])) : Exact.add(Exact.decimal(Exact.currency(row[wechatAuto])), Exact.decimal(Exact.currency(row[wechatAdd]))));
  const alipay = (Exact.truth(entered(row[alipayOverride])) ? Exact.decimal(Exact.currency(row[alipayOverride])) : Exact.decimal(Exact.currency(row[alipayAdd])));
  return Exact.add(Exact.add(Exact.add(Exact.decimal(Exact.currency(row[cashKey])), wechat), alipay), Exact.decimal(Exact.currency(row[takeoutKey])));
}
function mergeNormalizedDayRow(previous, current) {
  if (Exact.truth(Exact.not(previous))) return current;
  const previousRevenue = legacyRevenueValue(previous);
  const currentRevenue = legacyRevenueValue(current);
  /* A newer cloud import can leave a complete zero-valued placeholder next
     to a total-only row written by the old desktop app.  That placeholder is
     not an intentional reset: it has no payment split to support it.  Keep
     the old non-zero total until a real split/API value arrives. */
  const preserveLegacyTotal = Exact.and(()=>(Exact.and(()=>(Exact.and(()=>(Exact.sneq(previousRevenue, undefined)), ()=>(Exact.sneq(num(previousRevenue), 0)))), ()=>(Exact.or(()=>(Exact.seq(currentRevenue, undefined)), ()=>(Exact.seq(num(currentRevenue), 0)))))), ()=>(Exact.not(hasMeaningfulDayBreakdown(current))));
  const merged = {...previous};
  for (const [key, value] of Object.entries(current)) {
    if (Exact.truth(Exact.not(entered(value)))) continue;
    if (Exact.truth(Exact.and(()=>(preserveLegacyTotal), ()=>(legacyRevenueFields.has(key))))) continue;
    const old = merged[key];
    /* Rows from a later cloud sequence are authoritative, including an
       explicit zero.  Empty cells remain non-destructive so a partial legacy
       row cannot erase details already present in another record. */
    if (Exact.truth(Exact.or(()=>(Exact.not(entered(old))), ()=>(entered(value))))) merged[key] = value;
  }
  if (Exact.truth(preserveLegacyTotal)) {
    /* Keep a canonical non-zero 收益 too; downstream editors should not have
       to rediscover it from 总金额 on every refresh. */
    merged.收益 = previousRevenue;
  } else if (Exact.truth(Exact.and(()=>(hasMeaningfulDayBreakdown(current)), ()=>(Exact.sneq(currentRevenue, undefined))))) {
    /* A real channel edit is authoritative, even when its effective total is
       exactly 0.  Normalize both total columns so an older legacy value cannot
       be resurrected by a later fallback read. */
    merged.收益 = currentRevenue;
    merged.总金额 = currentRevenue;
    ["收入","总收入"].forEach(field => { if (Exact.truth(Exact.or(()=>(entered(merged[field])), ()=>(entered(current[field]))))) merged[field] = currentRevenue; });
  } else if (Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.sneq(currentRevenue, undefined)), ()=>(Exact.sneq(num(currentRevenue), 0)))), ()=>(Exact.or(()=>(Exact.not(entered(current.收益))), ()=>(Exact.seq(Exact.decimal(Exact.currency(current.收益)), 0))))))) {
    /* Some intermediate builds wrote a total field but left 收益 at 0. */
    merged.收益 = currentRevenue;
  }
  return merged;
}
function normalizeRecords(records) {
  const dayMap = new Map(), daySources = new Map(), dayRanks = new Map(); const months = new Map();
  state.recordMap = new Map();
  state.dayRecordMap = new Map();
  const list = (Exact.truth(Array.isArray(records)) ? records : []);
  const rankCompare = (left,right) => {
    for (let index=0; Exact.truth(Exact.lt(index, left.length)); (index = Exact.add(index, 1))) {
      if (Exact.truth(Exact.sneq(left[index], right[index]))) return Exact.sub(left[index], right[index]);
    }
    return 0;
  };
  list.forEach((record, recordIndex) => {
    const type = String(Exact.or(()=>(Exact.or(()=>(record.record_type), ()=>(record.type))), ()=>("")));
    const key = String(Exact.or(()=>(Exact.or(()=>(record.record_key), ()=>(record.key))), ()=>(""))).trim();
    if (Exact.truth(Exact.or(()=>(Exact.not(type)), ()=>(Exact.not(key))))) return;
    const payload = unpackPayload(record);
    const normalizedRecord = {...record, record_type:type, record_key:key, payload};
    state.recordMap.set(`${type}/${key}`, normalizedRecord);
    if (Exact.truth(Exact.seq(type, "day"))) {
      const rows = dayRowsFromPayload(payload,key);
      rows.forEach((source,rowIndex) => {
        if (Exact.truth(Exact.or(()=>(Exact.not(source)), ()=>(Exact.sneq(typeof source, "object"))))) return;
        const date = normalizeDateKey(Exact.or(()=>(source.日期), ()=>(key)));
        if (Exact.truth(Exact.not(isCanonicalDate(date)))) return;
        const normalized = {...source, 日期: date};
        const rank = [Exact.or(()=>(Exact.toNumber(record.sequence ?? record.seq ?? 0)), ()=>(0)), Exact.or(()=>(Exact.toNumber(record.version ?? record.current_version ?? 0)), ()=>(0)), recordIndex, rowIndex];
        const previousRank = dayRanks.get(date);
        if (Exact.truth(Exact.or(()=>(Exact.not(previousRank)), ()=>(Exact.gte(rankCompare(rank,previousRank), 0))))) {
          dayMap.set(date, mergeNormalizedDayRow(dayMap.get(date), normalized));
          dayRanks.set(date,rank);
          daySources.set(date,{record:normalizedRecord,rowDate:date,rowIndex,rank});
        }
      });
    } else if (Exact.truth(Exact.seq(type, "month"))) {
      const rows = (Exact.truth(Array.isArray(payload.monthly_fixed)) ? payload.monthly_fixed : []);
      const month = normalizeMonthKey(Exact.or(()=>(key), ()=>(rows[Exact.sub(rows.length, 1)]?.月份)));
      if (Exact.truth(Exact.and(()=>(rows.length), ()=>(month)))) {
        const source = rows[Exact.sub(rows.length, 1)];
        months.set(month, {...source, 月份:normalizeMonthKey(Exact.or(()=>(source.月份), ()=>(month)))});
      }
    }
  });
  /* Date aliases point back to the original record so edits can be written
     in place.  Keep the raw identity too; this matters for records imported
     by old desktop versions whose key was not a date. */
  for (const [date, source] of daySources) {
    state.dayRecordMap.set(date, {
      ...source.record,
      _dayDate: date,
      _dayRowIndex: source.rowIndex,
      _sourceRecordKey: source.record.record_key,
      _sourceRecord: source.record,
    });
    const alias = `day/${date}`;
    if (Exact.truth(Exact.not(state.recordMap.has(alias)))) state.recordMap.set(alias,state.dayRecordMap.get(date));
  }
  const days = [...dayMap.values()].sort(Exact.sortComparator((a,b) => String(a.日期).localeCompare(String(b.日期))));
  state.days = days; state.dayRowsByDate = dayMap; state.months = months;
}

function datasetStorageKey(){ return `restaurant_dataset_${Exact.or(()=>(Exact.or(()=>(state.user?.id), ()=>(state.user?.username))), ()=>("account"))}`; }
function selectDatasetFrom(items, requestedId="") {
  const wanted = Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(requestedId), ()=>(state.dataset?.id))), ()=>(localStorage.getItem(datasetStorageKey())))), ()=>(state.user?.default_dataset_id))), ()=>(""));
  return Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(items.find(item=>Exact.seq(item.id, wanted))), ()=>(items.find(item=>Exact.seq(item.id, state.user?.default_dataset_id))))), ()=>(items[0]))), ()=>(null));
}
function isTestDataset(dataset=state.dataset){return Exact.or(()=>(Exact.seq(dataset?.is_test, true)), ()=>(Exact.seq(String(Exact.or(()=>(dataset?.id), ()=>(""))), "test-demo-v1")));}
function renderCurrentDatasetAdmin(){
  const dataset=state.dataset,nameInput=$("currentDatasetName"),idNode=$("currentDatasetId"),deleteButton=$("deleteDatasetButton");
  if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.not(nameInput)), ()=>(Exact.not(idNode)))), ()=>(Exact.not(deleteButton)))))return;
  const id=String(Exact.or(()=>(dataset?.id), ()=>("")));
  if(Exact.truth(Exact.sneq(nameInput.dataset.datasetId, id))){nameInput.dataset.datasetId=id;nameInput.value=Exact.or(()=>(dataset?.name), ()=>(id));setOperationResult("currentDatasetAdminResult","");}
  else if(Exact.truth(Exact.sneq(document.activeElement, nameInput)))nameInput.value=Exact.or(()=>(dataset?.name), ()=>(id));
  idNode.textContent=Exact.or(()=>(id), ()=>("—"));
  nameInput.disabled=Exact.not(dataset);
  $("renameDatasetButton").disabled=Exact.not(dataset);
  deleteButton.disabled=Exact.or(()=>(Exact.not(dataset)), ()=>(isTestDataset(dataset)));
  deleteButton.title=(Exact.truth(isTestDataset(dataset)) ? (Exact.truth(Exact.seq(state.language, "en")) ? "The Test demonstration ledger cannot be deleted." : "Test 独立演示账本不可删除。") : "");
}
function renderDatasetSwitcher() {
  const select=$("datasetSelect"), admin=Exact.seq(currentRole(), "admin"), show=Exact.or(()=>(admin), ()=>(Exact.gt(state.datasets.length, 1)));
  $("datasetSelectWrap").classList.toggle("hidden",Exact.not(show));
  select.innerHTML=state.datasets.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(Exact.or(()=>(item.name), ()=>(item.id)))}</option>`).join("");
  if(Exact.truth(state.dataset))select.value=state.dataset.id;
  $("workbookDatasetName").textContent=Exact.or(()=>(Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id))), ()=>("—"));
  renderCurrentDatasetAdmin();
}

async function loadCloudData({silent=false,datasetId=""}={}) {
  if(Exact.truth(state.refreshBusy)){if(Exact.truth(datasetId))state.pendingDatasetId=datasetId;return;}
  state.refreshBusy=true;
  try {
    // Scheduled permissions can start/end while the page remains open.
    state.user = await api("/auth/me");
    const datasetsResponse = await api("/datasets");
    const datasets = (Exact.truth(Array.isArray(datasetsResponse)) ? datasetsResponse : Exact.or(()=>(datasetsResponse?.items), ()=>([])));
    const active = datasets.filter(item => Exact.sneq(item.is_active, false));
    if (Exact.truth(Exact.not(active.length))) throw new Error("当前账号没有可用的数据集。请先让云同步助手上传数据。");
    const previousDatasetId=Exact.or(()=>(state.dataset?.id), ()=>(""));
    state.datasets=active; state.dataset=selectDatasetFrom(active,datasetId);
    if(Exact.truth(Exact.and(()=>(previousDatasetId), ()=>(Exact.sneq(previousDatasetId, state.dataset?.id))))){clearEditorDrafts();}
    localStorage.setItem(datasetStorageKey(),state.dataset.id); renderDatasetSwitcher();
    const cloudRecords = await fetchAllRecords(state.dataset.id);
    if(Exact.truth(Exact.and(()=>(Exact.and(()=>(silent), ()=>(Exact.seq(previousDatasetId, state.dataset.id)))), ()=>(Exact.seq(canonical(cloudRecords), canonical(state.records)))))){
      $("lastUpdated").textContent=Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? "Updated " : "最近更新："), new Date().toLocaleTimeString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN"),{hour:"2-digit",minute:"2-digit",second:"2-digit"}));
      $("notice").classList.add("hidden");
      return;
    }
    state.records = cloudRecords;
    normalizeRecords(state.records);
    /* Entry users get server-owned deadlines for the visible countdown. The
       endpoint is intentionally skipped for other roles because timing
       metadata is not part of their UI contract. */
    state.entryWindows = [];
    if (Exact.truth(Exact.seq(currentRole(), "entry"))) {
      try {
        const windows = await api(`/datasets/${encodeURIComponent(state.dataset.id)}/entry-windows`);
        state.entryWindows = (Exact.truth(Array.isArray(windows)) ? windows : Exact.or(()=>(windows?.items), ()=>([])));
      } catch (_) {
        state.entryWindows = [];
      }
    }
    state.cashPosition = null;
    if (Exact.truth(Exact.and(()=>(["admin", "editor"].includes(currentRole())), ()=>(Exact.not(isTestAccount()))))) {
      try {
        state.cashPosition = await api(`/datasets/${encodeURIComponent(state.dataset.id)}/cash-position`);
      } catch (_) {
        /* Older deployments have no dedicated route; local record fallback
           keeps the module usable while the server is upgraded. */
      }
    }
    initializeFilters(); renderDashboard();
    if(Exact.truth(Exact.or(()=>(Exact.not(silent)), ()=>(Exact.not(state.editorDirty))))){refreshOpenEditors();state.editorDirty=Exact.gt(Object.keys(state.editorDrafts).length, 0);}
    if(Exact.truth(Exact.seq(state.activePage, "stats")))renderStats();
    if(Exact.truth(Exact.seq(typeof renderEntryTiming, "function")))renderEntryTiming();
    if(Exact.truth(Exact.seq(typeof renderCashPosition, "function")))renderCashPosition();
    $("lastUpdated").textContent=Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? "Updated " : "最近更新："), new Date().toLocaleTimeString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN"),{hour:"2-digit",minute:"2-digit",second:"2-digit"}));
    $("notice").classList.add("hidden");
  } catch (error) {
    $("notice").textContent = error.message; $("notice").classList.remove("hidden");
  } finally {
    state.refreshBusy=false;
    const pending=state.pendingDatasetId;state.pendingDatasetId="";
    if(Exact.truth(Exact.and(()=>(pending), ()=>(Exact.sneq(pending, state.dataset?.id)))))queueMicrotask(()=>loadCloudData({datasetId:pending}));
  }
}

function initializeFilters() {
  const latest = (Exact.truth(state.days.length) ? String(state.days[Exact.sub(state.days.length, 1)].日期) : isoDate(new Date()));
  const current = $("selectedDate").value;
  if (Exact.truth(Exact.not(current))) $("selectedDate").value = latest;
  const years = [...new Set([...state.days.map(row => String(row.日期).slice(0,4)),$("selectedDate").value.slice(0,4)].filter(Exact.truth))].sort().reverse();
  if (Exact.truth(Exact.not(years.length))) years.push(String(new Date().getFullYear()));
  $("selectedYear").innerHTML = years.map(y => `<option value="${y}">${(Exact.truth(Exact.seq(state.language, "en")) ? y : `${y} 年`)}</option>`).join("");
  $("selectedYear").value = $("selectedDate").value.slice(0,4);
  $("selectedMonth").innerHTML = Array.from({length:12},(_,i) => `<option value="${Exact.add(i, 1)}">${String(Exact.add(i, 1)).padStart(2,"0")}${(Exact.truth(Exact.seq(state.language, "en")) ? "" : " 月")}</option>`).join("");
  $("selectedMonth").value = Exact.toNumber($("selectedDate").value.slice(5,7));
}

function fixedBreakdown(year, month) {
  const monthKey = normalizeMonthKey(`${year}-${String(month).padStart(2,"0")}`);
  const row = Exact.or(()=>(Exact.or(()=>(state.months.get(monthKey)), ()=>(state.months.get(`${year}/${String(month).padStart(2,"0")}`)))), ()=>({}));
  const labour = Exact.decimal(Exact.currency(row.人工总额)), rent = Exact.decimal(Exact.currency(row.房租总额)), gas = Exact.decimal(Exact.currency(row.煤气费)), other = Exact.decimal(Exact.currency(row.其它固定成本));
  const splitSpent = Exact.or(()=>(entered(row.水费支出)), ()=>(entered(row.电费支出)));
  const waterSpent = (Exact.truth(splitSpent) ? Exact.decimal(Exact.currency(row.水费支出)) : Exact.decimal(Exact.currency(row.水电费)));
  const electricSpent = (Exact.truth(splitSpent) ? Exact.decimal(Exact.currency(row.电费支出)) : 0);
  const actualWater = (Exact.truth(entered(row.实际使用水费)) ? Exact.decimal(Exact.currency(row.实际使用水费)) : null);
  const actualElectric = (Exact.truth(entered(row.实际使用电费)) ? Exact.decimal(Exact.currency(row.实际使用电费)) : null);
  const expectedWater = (Exact.truth(entered(row.预计水费)) ? Exact.decimal(Exact.currency(row.预计水费)) : waterSpent);
  const expectedElectric = (Exact.truth(entered(row.预计电费)) ? Exact.decimal(Exact.currency(row.预计电费)) : electricSpent);
  const expectedGas = (Exact.truth(entered(row.预计煤气费)) ? Exact.decimal(Exact.currency(row.预计煤气费)) : gas);
  const water = (Exact.truth(Exact.seq(actualWater, null)) ? expectedWater : actualWater);
  const electric = (Exact.truth(Exact.seq(actualElectric, null)) ? expectedElectric : actualElectric);
  return {labour,rent,gas,other,waterSpent,electricSpent,actualWater,actualElectric,expectedWater,expectedElectric,expectedGas,water,electric,effectiveTotal:Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(labour, rent), expectedGas), other), water), electric),spentTotal:Exact.add(Exact.add(Exact.add(Exact.add(Exact.add(labour, rent), gas), other), waterSpent), electricSpent)};
}

function dayMetrics(row) {
  if (Exact.truth(Exact.not(row))) return null;
  const dateKey = normalizeDateKey(row.日期);
  if (Exact.truth(Exact.not(isCanonicalDate(dateKey)))) return null;
  const date = parseDate(dateKey); const fixed = fixedBreakdown(date.getFullYear(), Exact.add(date.getMonth(), 1)); const dim = daysInMonth(date.getFullYear(), Exact.add(date.getMonth(), 1));
  // Legacy desktop builds stored a total-only entry as “总金额”. Keep it
  // visible when the newer “收益” field is absent or zero.
  const revenueValue = legacyRevenueValue(row);
  const revenue = (Exact.truth(Exact.seq(revenueValue, undefined)) ? 0 : Exact.decimal(Exact.currency(revenueValue))), food = Exact.decimal(Exact.currency(row.食材成本)), spice = Exact.decimal(Exact.currency(row.佐料成本)), waterDaily = Exact.decimal(Exact.currency(row.水电)), other = Exact.decimal(Exact.currency(row.其他)), fees = Exact.decimal(Exact.currency(row.手续费));
  const fixedDaily = (Exact.truth(dim) ? Exact.div(fixed.spentTotal, dim) : 0); const variable = Exact.add(Exact.add(Exact.add(Exact.add(food, spice), waterDaily), other), fees); const total = Exact.add(variable, fixedDaily);
  const customers = num(row.总客人数), newCustomers = num(row.新客人数量);
  const storeA=storeRevenueValue(row,"A"),storeB=storeRevenueValue(row,"B");
  return {date:dateKey,revenue,storeA,storeB,food,spice,waterDaily,other,fees,fixedDaily,variable,total,gross:Exact.sub(Exact.sub(Exact.sub(revenue, food), spice), fees),net:Exact.sub(revenue, total),customers,newCustomers,oldCustomers:Exact.math.max(Exact.sub(customers, newCustomers),0),expense:{[mt("food")]:food,[mt("spice")]:spice,[(Exact.truth(Exact.seq(state.language, "en")) ? "Daily Utilities" : "日结水电")]:waterDaily,[mt("other")]:other,["手续费／抽成"]:fees,[mt("labour")]:Exact.div(fixed.labour, dim),[mt("rent")]:Exact.div(fixed.rent, dim),[mt("water")]:Exact.div(fixed.water, dim),[mt("electric")]:Exact.div(fixed.electric, dim),[mt("gas")]:Exact.div(fixed.expectedGas, dim),[(Exact.truth(Exact.seq(state.language, "en")) ? "Other Fixed Cost" : "其它固定")]:Exact.div(fixed.other, dim)}};
}

function dishCostForDate(key) {
  const record=currentRecord("day",key); if(Exact.truth(Exact.not(record)))return {has:false,cost:0};
  const payload=unpackPayload(record), dishes=(Exact.truth(Array.isArray(payload.dishes)) ? payload.dishes : []);
  const target=normalizeDateKey(key), item=dishes.find(row=>Exact.seq(normalizeDateKey(Exact.or(()=>(row?.日期), ()=>(""))), target)); if(Exact.truth(Exact.not(item)))return {has:false,cost:0};
  if(Exact.truth(entered(item.总成本)))return {has:true,cost:Exact.decimal(Exact.currency(item.总成本))};
  try { const rows=(Exact.truth(Array.isArray(item.菜品数据)) ? item.菜品数据 : JSON.parse(Exact.or(()=>(item.菜品数据), ()=>("[]")))); return {has:Exact.and(()=>(Array.isArray(rows)), ()=>(Exact.gt(rows.length, 0))),cost:(Exact.or(()=>(rows), ()=>([]))).reduce((sum,row)=>Exact.add(sum, Exact.decimal(Exact.currency(row.成本))),0)}; } catch(_){ return {has:false,cost:0}; }
}

function aggregate(metrics, elapsedDays=metrics.length, averageMetrics=metrics) {
  if (Exact.truth(Exact.not(metrics.length))) return null;
  const sum = key => metrics.reduce((total,item) => Exact.add(total, item[key]),0);
  const averageSum = key => averageMetrics.reduce((total,item) => Exact.add(total, item[key]),0);
  const denominator=Exact.math.max(1,Exact.or(()=>(Exact.toNumber(elapsedDays)), ()=>(metrics.length)));
  return {days:metrics.length,elapsedDays:denominator,revenue:sum("revenue"),gross:sum("gross"),net:sum("net"),fixed:sum("fixedDaily"),variable:sum("variable"),total:sum("total"),avgRevenue:Exact.div(averageSum("revenue"), denominator),avgGross:Exact.div(averageSum("gross"), denominator),avgNet:Exact.div(averageSum("net"), denominator),avgVariable:Exact.div(averageSum("variable"), denominator)};
}

function elapsedCalendarDays(start,end,asOf=new Date()) {
  const first=new Date(start.getFullYear(),start.getMonth(),start.getDate());
  const last=new Date(end.getFullYear(),end.getMonth(),end.getDate());
  const yesterday=new Date(asOf.getFullYear(),asOf.getMonth(),Exact.sub(asOf.getDate(), 1));
  const capped=(Exact.truth(Exact.lt(last, yesterday)) ? last : yesterday);
  return (Exact.truth(Exact.lt(capped, first)) ? 0 : Exact.add(Exact.math.floor(Exact.div(Exact.sub(capped, first), 86400000)), 1));
}
function periodElapsedDays(year,month) {
  return Exact.math.max(0,elapsedCalendarDays(new Date(year,Exact.sub(month, 1),1),new Date(year,month,0)));
}
function periodElapsedDaysBetween(start,end) { return Exact.math.max(0,elapsedCalendarDays(start,end)); }
function yearElapsedDays(year) { return Exact.math.max(0,elapsedCalendarDays(new Date(year,0,1),new Date(year,11,31))); }

function dayRowForDate(key) {
  const normalized = normalizeDateKey(key);
  return Exact.or(()=>(Exact.or(()=>(state.dayRowsByDate?.get(normalized)), ()=>(state.days.find(row => Exact.seq(normalizeDateKey(row.日期), normalized))))), ()=>(null));
}
function hasMeaningfulDayData(row){
  if(Exact.truth(Exact.not(row)))return false;
  const numericKeys=["收益","总金额","收入","总收入","A店收入","B店收入","学生外卖","A店外卖","B店外卖","A店现金","B店现金","总现金","总线上","食材成本","佐料成本","水电","其他","总客人数","新客人数量"];
  if(Exact.truth(numericKeys.some(key=>Exact.and(()=>(entered(row[key])), ()=>(Exact.gt(Exact.math.abs(num(row[key])), 1e-9))))))return true;
  return ["食材明细","佐料明细","其他明细","当日备注"].some(key=>entered(row[key]));
}
function dataDayMetrics(){return state.days.map(row=>(Exact.truth(hasMeaningfulDayData(row)) ? dayMetrics(row) : null)).filter(Exact.truth);}
function metricSd(metrics,key){const values=(Exact.or(()=>(metrics), ()=>([]))).map(item=>num(item?.[key])).filter(Exact.finite);if(Exact.truth(Exact.lt(values.length, 1)))return 0;const mean=Exact.div(values.reduce((a,b)=>Exact.add(a, b),0), values.length);return Exact.math.sqrt(Exact.div(values.reduce((a,b)=>Exact.add(a, Exact.pow(Exact.sub(b, mean), 2)),0), values.length));}
function metricMoneySd(value,metrics,key){return `${money(value)} (SD: ${money(metricSd(metrics,key))})`;}
function metricCountSd(value,metrics,key){return `${Exact.decimal(Exact.or(()=>(value), ()=>(0))).toLocaleString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN"))} (SD: ${metricSd(metrics,key).toFixed(2)})`;}
function metricProfitSd(value,revenue,metrics,key){return `${money(value)} (${percent(value,revenue)}) (SD: ${money(metricSd(metrics,key))})`;}
function selectedContext() {
  const rawDateText = Exact.or(()=>($("selectedDate").value), ()=>(isoDate(new Date())));
  const normalizedDateText = normalizeDateKey(rawDateText);
  const dateText = (Exact.truth(isCanonicalDate(normalizedDateText)) ? normalizedDateText : isoDate(new Date()));
  if (Exact.truth(Exact.sneq($("selectedDate").value, dateText))) $("selectedDate").value = dateText;
  const target = parseDate(dateText); const year = Exact.toNumber(Exact.or(()=>($("selectedYear").value), ()=>(target.getFullYear()))); const month = Exact.toNumber(Exact.or(()=>($("selectedMonth").value), ()=>(Exact.add(target.getMonth(), 1))));
  /* Render an empty selected day as a real zero-valued day. This keeps the
     daily card useful and still applies that month's shared fixed-cost share. */
  const dayRow = dayRowForDate(dateText); const day = dayMetrics(Exact.or(()=>(dayRow), ()=>({日期:dateText,收益:0,总金额:0,食材成本:0,佐料成本:0,水电:0,其他:0})));
  const weekday = Exact.mod(Exact.add(target.getDay(), 6), 7); const weekStart = new Date(target); weekStart.setDate(Exact.sub(target.getDate(), weekday)); const weekEnd = new Date(weekStart); weekEnd.setDate(Exact.add(weekStart.getDate(), 6));
  const todayKey=isoDate(new Date());
  const averageCutoff=isoDate(new Date(new Date().getFullYear(),new Date().getMonth(),Exact.sub(new Date().getDate(), 1)));
  const allMetrics = dataDayMetrics().filter(m=>Exact.lte(m.date, todayKey));
  const averageMetrics = allMetrics.filter(m=>Exact.lte(m.date, averageCutoff));
  const weekMetrics = allMetrics.filter(m => {const d=parseDate(m.date); return Exact.and(()=>(Exact.gte(d, weekStart)), ()=>(Exact.lte(d, weekEnd)));});
  const monthMetrics = allMetrics.filter(m => m.date.startsWith(`${year}-${String(month).padStart(2,"0")}`));
  const yearMetrics = allMetrics.filter(m => m.date.startsWith(`${year}-`));
  const weekAverageMetrics = averageMetrics.filter(m => {const d=parseDate(m.date); return Exact.and(()=>(Exact.gte(d, weekStart)), ()=>(Exact.lte(d, weekEnd)));});
  const monthAverageMetrics = averageMetrics.filter(m => m.date.startsWith(`${year}-${String(month).padStart(2,"0")}`));
  const yearAverageMetrics = averageMetrics.filter(m => m.date.startsWith(`${year}-`));
  const monthElapsed=periodElapsedDays(year,month), weekElapsed=periodElapsedDaysBetween(weekStart,weekEnd), yearElapsed=yearElapsedDays(year);
  return {dateText,target,year,month,day,week:aggregate(weekMetrics,weekElapsed,weekAverageMetrics),monthSummary:aggregate(monthMetrics,monthElapsed,monthAverageMetrics),yearSummary:aggregate(yearMetrics,yearElapsed,yearAverageMetrics),monthMetrics,monthAverageMetrics,yearMetrics,weekMetrics,monthElapsedDays:monthElapsed,weekElapsedDays:weekElapsed,yearElapsedDays:yearElapsed,weekStart,weekEnd};
}

function row(label, value, cls="") { return `<div class="metric-row ${cls}"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`; }
function forecastRow(title, formula, value, cls="", formulaFirst=false) {
  const titleMarkup=`<span class="forecast-title">${escapeHtml(title)}</span>`, formulaMarkup=`<small class="forecast-formula">${escapeHtml(formula)}</small>`;
  return `<div class="metric-row forecast-row ${cls}"><span class="forecast-label">${(Exact.truth(formulaFirst) ? `${formulaMarkup}${titleMarkup}` : `${titleMarkup}${formulaMarkup}`)}</span><strong>${value}</strong></div>`;
}
function spacer() { return '<div class="metric-row spacer" aria-hidden="true"></div>'; }
function profit(value, revenue) { return `${money(value)} (${percent(value,revenue)})`; }
function renderCard(id, rows) { $(id).querySelector(".metric-list").innerHTML = rows.join(""); }

function renderDashboard() {
  const c = selectedContext();
  $("dayTitle").textContent = c.dateText; $("weekTitle").textContent = `${isoDate(c.weekStart).slice(5)} ${(Exact.truth(Exact.seq(state.language, "en")) ? "to" : "至")} ${isoDate(c.weekEnd).slice(5)}`; $("monthTitle").textContent = (Exact.truth(Exact.seq(state.language, "en")) ? `${c.year}-${String(c.month).padStart(2,"0")}` : `${c.year} 年 ${c.month} 月`); $("yearTitle").textContent = (Exact.truth(Exact.seq(state.language, "en")) ? String(c.year) : `${c.year} 年`);
  const d=c.day, monthDays=daysInMonth(c.year,c.month), elapsed=Exact.math.max(1,Exact.or(()=>(Exact.or(()=>(c.monthElapsedDays), ()=>(c.monthSummary?.elapsedDays))), ()=>(1))), dailyRevenue=(Exact.truth(c.monthSummary) ? c.monthSummary.avgRevenue : 0), expectedMonthRevenue=Exact.mul(dailyRevenue, monthDays);
  const previousDate=new Date(c.year,Exact.sub(c.month, 2),1), previousMonthKey=`${previousDate.getFullYear()}-${String(Exact.add(previousDate.getMonth(), 1)).padStart(2,"0")}`, previousMonthMetrics=dataDayMetrics().filter(m=>m.date.startsWith(previousMonthKey));
  const monthPaid=(Exact.truth(c.monthSummary) ? fixedBreakdown(c.year,c.month).spentTotal : 0), monthTotal=(Exact.truth(c.monthSummary) ? Exact.add(c.monthSummary.variable, monthPaid) : 0), monthNet=(Exact.truth(c.monthSummary) ? Exact.sub(c.monthSummary.revenue, monthTotal) : 0);
  const previousMonthTotalCost=(Exact.truth(previousMonthMetrics.length) ? Exact.add(previousMonthMetrics.reduce((sum,item)=>Exact.add(sum, item.variable),0), fixedBreakdown(previousDate.getFullYear(),Exact.add(previousDate.getMonth(), 1)).spentTotal) : monthTotal), expectedMonthNet=Exact.sub(expectedMonthRevenue, previousMonthTotalCost);
  const dish=(Exact.truth(d) ? dishCostForDate(d.date) : {has:false,cost:0}), displayedGross=(Exact.truth(dish.has) ? Exact.sub(d.revenue, dish.cost) : Exact.or(()=>(d?.gross), ()=>(0)));
  /* Standard deviation is intentionally limited to the three daily revenue
     values. All cost and profit rows stay as ordinary money/profit values. */
  renderCard("dayCard", (Exact.truth(d) ? [row(mt("revenue"),metricMoneySd(d.revenue,c.monthAverageMetrics,"revenue"),"hero"),spacer(),row(mt("fixed"),money(d.fixedDaily)),row(mt("variable"),money(d.variable)),row(mt("total"),money(d.total)),row((Exact.truth(Exact.seq(state.language, "en")) ? "Average total cost" : "日均总成本"),money(d.total)),row(mt("dish"),money((Exact.truth(dish.has) ? dish.cost : 0))),spacer(),row(mt("net"),profit(d.net,d.revenue),(Exact.truth(Exact.gte(d.net, 0)) ? "positive" : "negative")),spacer(),row(mt("gross"),profit(displayedGross,d.revenue),(Exact.truth(Exact.gte(displayedGross, 0)) ? "positive" : "negative")),row(mt("customers"),compactNumber(d.customers)),row(mt("ticket"),money((Exact.truth(d.customers) ? Exact.div(d.revenue, d.customers) : 0)))] : [row((Exact.truth(Exact.seq(state.language, "en")) ? "No data for this date" : "当天没有经营数据"),"—")]));
  const summaryRows=(s,metrics,override={})=>{if(Exact.truth(Exact.not(s)))return[row((Exact.truth(Exact.seq(state.language, "en")) ? "No operating data" : "没有经营数据"),"—")];const fixedTotal=override.fixedTotal??s.fixed,total=override.total??(Exact.add(s.variable, fixedTotal)),net=override.net??(Exact.sub(s.revenue, total)),avgTotal=override.avgTotal??(Exact.div(total, Exact.math.max(1,Exact.or(()=>(s.elapsedDays), ()=>(s.days)))));return[row(mt("revenue"),money(s.revenue),"hero"),spacer(),row(mt("fixedTotal"),money(fixedTotal)),row(mt("variable"),money(s.variable)),row(mt("total"),money(total)),row((Exact.truth(Exact.seq(state.language, "en")) ? "Average total cost" : "日均总成本"),money(avgTotal)),spacer(),row(mt("gross"),profit(s.gross,s.revenue),(Exact.truth(Exact.gte(s.gross, 0)) ? "positive" : "negative")),row(mt("net"),profit(net,s.revenue),(Exact.truth(Exact.gte(net, 0)) ? "positive" : "negative")),spacer(),row(mt("avgRevenue"),money(s.avgRevenue)),row(mt("avgVariable"),money(s.avgVariable)),row(mt("avgGross"),profit(s.avgGross,s.avgRevenue)),row(mt("avgNet"),profit(Exact.div(net, Exact.math.max(1,Exact.or(()=>(s.elapsedDays), ()=>(s.days)))),s.avgRevenue))];};
  renderCard("weekCard",summaryRows(c.week,c.weekMetrics));
  if(Exact.truth(c.monthSummary)){
    const grossMargin=(Exact.truth(Exact.gt(c.monthSummary.revenue, 0)) ? Exact.div(c.monthSummary.gross, c.monthSummary.revenue) : 0);
    const breakEvenDailyIncrease=(Exact.truth(Exact.and(()=>(Exact.lt(expectedMonthNet, 0)), ()=>(Exact.gt(grossMargin, 0)))) ? Exact.div(Exact.div(Exact.math.abs(expectedMonthNet), grossMargin), monthDays) : 0);
    const forecastRows=[
      spacer(),
      forecastRow((Exact.truth(Exact.seq(state.language, "en")) ? "Monthly revenue forecast" : "本月收入预测"),(Exact.truth(Exact.seq(state.language, "en")) ? "(current average daily revenue × total days)" : "(本月截至目前的日均收入 x 本月总天数)"),money(expectedMonthRevenue),"hero",true),
      forecastRow((Exact.truth(Exact.seq(state.language, "en")) ? "Estimated month-end profit/loss" : "预计月底盈亏"),(Exact.truth(Exact.seq(state.language, "en")) ? "(based on previous month total cost and monthly revenue forecast)" : "(根据上月总成本和本月收入预测)"),money(expectedMonthNet),`hero ${(Exact.truth(Exact.gte(expectedMonthNet, 0)) ? "positive" : "negative")}`),
      forecastRow((Exact.truth(Exact.seq(state.language, "en")) ? "Daily Revenue increase needed to break even" : "平本需要 日均收入（“收入”指“Revenue”）增加"),(Exact.truth(Exact.seq(state.language, "en")) ? "((estimated month-end profit/loss ÷ monthly gross margin) ÷ days in month)" : "( (预计月底盈亏/本月毛利率) / 本月天数 )"),money(breakEvenDailyIncrease),"hero")
    ];
    renderCard("monthCard",summaryRows(c.monthSummary,c.monthMetrics,{fixedTotal:monthPaid,total:monthTotal,net:monthNet,avgTotal:Exact.div(monthTotal, Exact.math.max(1,Exact.or(()=>(c.monthElapsedDays), ()=>(c.monthSummary.elapsedDays))))}).concat(forecastRows));
  }else renderCard("monthCard",summaryRows(c.monthSummary,c.monthMetrics));
  const y=c.yearSummary;let yearRows=summaryRows(y,c.yearMetrics);if(Exact.truth(y)){const paid=Array.from({length:12},(_,i)=>fixedBreakdown(c.year,Exact.add(i, 1)).spentTotal).reduce((a,b)=>Exact.add(a, b),0),yearTotal=Exact.add(y.variable, paid),yearNet=Exact.sub(y.revenue, yearTotal);yearRows=summaryRows(y,c.yearMetrics,{fixedTotal:paid,total:yearTotal,net:yearNet,avgTotal:Exact.div(yearTotal, Exact.math.max(1,Exact.or(()=>(c.yearElapsedDays), ()=>(y.elapsedDays))))});yearRows.splice(5,0,row(mt("totalExpense"),money(yearTotal)));const monthCount=Exact.math.max(1,new Set(c.yearMetrics.map(m=>m.date.slice(0,7))).size);yearRows.push(row(mt("monthGross"),profit(Exact.div(y.gross, monthCount),Exact.div(y.revenue, monthCount))));yearRows.push(row(mt("monthNet"),profit(Exact.div(yearNet, monthCount),Exact.div(y.revenue, monthCount))));}
  renderCard("yearCard",yearRows);renderCostDonut(d);renderTrend(c.monthMetrics);renderWeekdays(c.monthMetrics);renderExpenses(c);if(Exact.truth(Exact.seq(typeof renderCashPosition, "function")))renderCashPosition();
}

function renderCostDonut(day) {
  const entries = (Exact.truth(day) ? Object.entries(day.expense).filter(([,v])=>Exact.gt(v, 0)) : []); const total=entries.reduce((s,[,v])=>Exact.add(s, v),0); let cursor=0;
  const segments=entries.map(([name,value],i)=>{const start=Exact.mul(Exact.div(cursor, total), 100);(cursor = Exact.add(cursor, value));return `${colors[Exact.mod(i, colors.length)]} ${start}% ${Exact.mul(Exact.div(cursor, total), 100)}%`;});
  $("costDonut").style.background=(Exact.truth(segments.length) ? `conic-gradient(${segments.join(",")})` : "#e8eef4"); $("costDonut").querySelector("span").innerHTML=(Exact.truth(total) ? `${(Exact.truth(Exact.seq(state.language, "en")) ? "Total Cost" : "总成本")}<br><b>${money(total)}</b>` : (Exact.truth(Exact.seq(state.language, "en")) ? "No data" : "暂无数据")); $("costTotal").textContent=(Exact.truth(day) ? `${day.date} ${(Exact.truth(Exact.seq(state.language, "en")) ? "cost share" : "开销占比")}` : "—");
  $("costLegend").innerHTML=Exact.or(()=>(entries.map(([name,value],i)=>`<div class="legend-row"><i style="background:${colors[Exact.mod(i, colors.length)]}"></i><span>${escapeHtml(name)}</span><strong>${percent(value,total)}</strong></div>`).join("")), ()=>(`<div class="empty-chart">${(Exact.truth(Exact.seq(state.language, "en")) ? "No cost data for this date" : "当天没有成本数据")}</div>`));
}

function compactNumber(value){return Exact.decimal(Exact.or(()=>(value), ()=>(0))).toLocaleString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN"), {maximumFractionDigits:0});}
function pointValue(metric,value,revenue){return (Exact.truth(["net","gross"].includes(metric)) ? `${compactNumber(value)} (${percent(value,revenue).replace(".0%","%")})` : compactNumber(value));}
function bindInteractiveChart(container){
  let down=false,startX=0,startScroll=0;
  container.onpointerdown=e=>{down=true;startX=e.clientX;startScroll=container.scrollLeft;container.classList.add("dragging");container.setPointerCapture?.(e.pointerId);};
  container.onpointermove=e=>{if(Exact.truth(down))container.scrollLeft=Exact.sub(startScroll, Exact.sub(e.clientX, startX));const point=e.target.closest?.("[data-chart-point]");if(Exact.truth(point))showChartTooltip(point,e);};
  container.onpointerup=container.onpointercancel=()=>{down=false;container.classList.remove("dragging");};
  container.onpointerleave=()=>{$("chartTooltip").classList.add("hidden");if(Exact.truth(down)){down=false;container.classList.remove("dragging");}};
  container.querySelectorAll("[data-chart-point]").forEach(point=>{point.addEventListener("pointerenter",e=>showChartTooltip(point,e));point.addEventListener("click",e=>showChartTooltip(point,e));});
}
function showChartTooltip(point,event){const tip=$("chartTooltip");tip.innerHTML=escapeHtml(Exact.or(()=>(point.dataset.tooltip), ()=>(""))).replace(/\n/g,"<br>");tip.classList.remove("hidden");const rect=tip.getBoundingClientRect();tip.style.left=`${Exact.math.min(Exact.sub(Exact.sub(innerWidth, rect.width), 10),Exact.add(event.clientX, 14))}px`;tip.style.top=`${Exact.math.max(8,Exact.sub(Exact.sub(event.clientY, rect.height), 12))}px`;}
function lineChartMarkup(items,metric,key,{includeEmpty=false}={}){
  const values=items.map(item=>num(item[key]));const width=Exact.math.max(760,Exact.add(Exact.mul(items.length, 138), 80)),height=315,pad={l:58,r:32,t:78,b:42};let min=Exact.math.min(0,...values),max=Exact.math.max(0,...values);if(Exact.truth(Exact.seq(max, min)))max=Exact.add(min, 1);const range=Exact.sub(max, min);(max = Exact.add(max, Exact.mul(range, .2)));(min = Exact.sub(min, Exact.mul(range, .1)));
  const x=i=>Exact.add(pad.l, (Exact.truth(Exact.seq(items.length, 1)) ? Exact.div(Exact.sub(Exact.sub(width, pad.l), pad.r), 2) : Exact.mul(Exact.div(i, Exact.sub(items.length, 1)), Exact.sub(Exact.sub(width, pad.l), pad.r))));const y=v=>Exact.add(pad.t, Exact.mul(Exact.div(Exact.sub(max, v), Exact.sub(max, min)), Exact.sub(Exact.sub(height, pad.t), pad.b)));const points=items.map((m,i)=>`${x(i)},${y(values[i])}`).join(" ");const area=`${x(0)},${y(0)} ${points} ${x(Exact.sub(items.length, 1))},${y(0)}`;
  const grid=Array.from({length:5},(_,i)=>{const yy=Exact.add(pad.t, Exact.div(Exact.mul(i, Exact.sub(Exact.sub(height, pad.t), pad.b)), 4));return `<line class="grid-line" x1="${pad.l}" y1="${yy}" x2="${Exact.sub(width, pad.r)}" y2="${yy}"/>`;}).join("");
  const marks=items.map((m,i)=>{const value=values[i],label=pointValue(metric,value,m.revenue),yy=y(value),labelY=Exact.math.max(16,Exact.sub(yy, Exact.add(16, Exact.mul(Exact.mod(i, 3), 20))));const tooltip=`${m.date}\n${label}`;return `<line class="point-leader" x1="${x(i)}" y1="${Exact.sub(yy, 4)}" x2="${x(i)}" y2="${Exact.add(labelY, 4)}"/><text class="point-value" x="${x(i)}" y="${labelY}" text-anchor="middle">${label}</text><circle data-chart-point data-tooltip="${escapeHtml(tooltip)}" class="trend-point" cx="${x(i)}" cy="${yy}" r="5"/><text class="chart-label" x="${x(i)}" y="${Exact.sub(height, 10)}" text-anchor="middle">${m.date.slice(5)}</text>`;}).join("");
  return `<svg viewBox="0 0 ${width} ${height}" style="width:${width}px" preserveAspectRatio="none"><defs><linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#19aeca" stop-opacity=".22"/><stop offset="1" stop-color="#19aeca" stop-opacity="0"/></linearGradient></defs>${grid}<line class="axis-line" x1="${pad.l}" y1="${y(0)}" x2="${Exact.sub(width, pad.r)}" y2="${y(0)}"/><polygon class="trend-area" points="${area}"/><polyline class="trend-line" points="${points}"/>${marks}</svg>`;
}
function renderTrend(metrics) {
  if (Exact.truth(Exact.not(metrics.length))){$("trendChart").innerHTML=`<div class="empty-chart">${(Exact.truth(Exact.seq(state.language, "en")) ? "No data this month" : "本月没有经营数据")}</div>`;$("trendSummary").textContent="—";return;}
  const metric=$("trendMetric").value;const meta={net:[(Exact.truth(Exact.seq(state.language, "en")) ? "Net Profit" : "净利润"),"net"],gross:[(Exact.truth(Exact.seq(state.language, "en")) ? "Gross Profit" : "毛利润"),"gross"],food:[(Exact.truth(Exact.seq(state.language, "en")) ? "Ingredient + Seasoning Cost" : "食材成本（包括佐料）"),"foodTotal"],revenue:[(Exact.truth(Exact.seq(state.language, "en")) ? "Revenue" : "收入（Revenue）"),"revenue"]}[metric];$("trendTitle").textContent=Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? "Daily " : "每日"), meta[0]);
  const source=new Map(metrics.map(m=>[Exact.toNumber(m.date.slice(Exact.neg(2))),m]));const first=parseDate(metrics[0].date);const count=daysInMonth(first.getFullYear(),Exact.add(first.getMonth(), 1));const full=Array.from({length:count},(_,i)=>Exact.or(()=>(source.get(Exact.add(i, 1))), ()=>({date:`${metrics[0].date.slice(0,8)}${String(Exact.add(i, 1)).padStart(2,"0")}`,net:0,gross:0,food:0,spice:0,revenue:0})));full.forEach(m=>m.foodTotal=Exact.add(num(m.food), num(m.spice)));
  $("trendChart").innerHTML=lineChartMarkup(full,metric,meta[1]);bindInteractiveChart($("trendChart"));
  const total=full.reduce((sum,item)=>Exact.add(sum, num(item[meta[1]])),0);$("trendSummary").textContent=Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? "Total " : "累计 "), money(total));
}

function renderWeekdays(metrics){const names=(Exact.truth(Exact.seq(state.language, "en")) ? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] : ["周一","周二","周三","周四","周五","周六","周日"]),groups=Array.from({length:7},()=>[]);metrics.forEach(m=>groups[Exact.mod(Exact.add(parseDate(m.date).getDay(), 6), 7)].push(m));const values=groups.map(group=>{const net=(Exact.truth(group.length) ? Exact.div(group.reduce((sum,item)=>Exact.add(sum, item.net),0), group.length) : 0),revenue=(Exact.truth(group.length) ? Exact.div(group.reduce((sum,item)=>Exact.add(sum, item.revenue),0), group.length) : 0);return {net,revenue};}),max=Exact.math.max(1,...values.map(item=>Exact.math.abs(item.net)));$("weekdayChart").innerHTML=values.map((item,i)=>`<div class="vertical-bar" data-chart-point data-tooltip="${names[i]}\n${pointValue("net",item.net,item.revenue)}"><b>${pointValue("net",item.net,item.revenue)}</b><i style="height:${Exact.math.max(2,Exact.mul(Exact.div(Exact.math.abs(item.net), max), 82))}%;background:${(Exact.truth(Exact.lt(item.net, 0)) ? 'linear-gradient(#ed7780,#d14e58)' : '')}"></i><em>${names[i]}</em></div>`).join("");bindInteractiveChart($("weekdayChart"));}

function costSharePercentages(entries){
  const total=entries.reduce((sum,[,value])=>Exact.add(sum, value),0);if(Exact.truth(Exact.lte(total, 0)))return [];
  const units=entries.map(([name,value],index)=>{const raw=Exact.mul(Exact.div(value, total), 1000),base=Exact.math.floor(raw);return {name,index,base,remainder:Exact.sub(raw, base)};});
  let remaining=Exact.sub(1000, units.reduce((sum,item)=>Exact.add(sum, item.base),0));
  units.slice().sort(Exact.sortComparator((a,b)=>Exact.or(()=>(Exact.sub(b.remainder, a.remainder)), ()=>(Exact.sub(a.index, b.index))))).forEach(item=>{if(Exact.truth(Exact.gt(remaining, 0))){(item.base = Exact.add(item.base, 1));(remaining = Exact.sub(remaining, 1));}});
  return units.sort(Exact.sortComparator((a,b)=>Exact.sub(a.index, b.index))).map(item=>`${(Exact.div(item.base, 10)).toFixed(1)}%`);
}
function renderExpenses(c){
  const fixed=fixedBreakdown(c.year,c.month),m=c.monthMetrics;
  const values={[mt("food")]:m.reduce((s,x)=>Exact.add(s, x.food),0),[mt("spice")]:m.reduce((s,x)=>Exact.add(s, x.spice),0),[mt("labour")]:(Exact.truth(c.monthSummary?.fixed) ? Exact.mul(Exact.div(fixed.labour, daysInMonth(c.year,c.month)), m.length) : 0),[mt("rent")]:Exact.mul(Exact.div(fixed.rent, daysInMonth(c.year,c.month)), m.length),[mt("water")]:Exact.mul(Exact.div(fixed.water, daysInMonth(c.year,c.month)), m.length),[mt("electric")]:Exact.mul(Exact.div(fixed.electric, daysInMonth(c.year,c.month)), m.length),[mt("gas")]:Exact.mul(Exact.div(fixed.expectedGas, daysInMonth(c.year,c.month)), m.length),[mt("other")]:Exact.add(m.reduce((s,x)=>Exact.add(Exact.add(s, x.other), x.waterDaily),0), Exact.mul(Exact.div(fixed.other, daysInMonth(c.year,c.month)), m.length))};
  const entries=Object.entries(values).filter(([,value])=>Exact.gt(value, 0)).sort(Exact.sortComparator((a,b)=>Exact.sub(b[1], a[1])));
  if(Exact.truth(Exact.not(entries.length))){$("expenseChart").innerHTML=`<div class="empty-chart">${(Exact.truth(Exact.seq(state.language, "en")) ? "No cost data this month" : "本月没有成本数据")}</div>`;return;}
  const total=entries.reduce((sum,[,value])=>Exact.add(sum, value),0),max=Exact.math.max(1,...entries.map(([,value])=>value)),shares=costSharePercentages(entries);
  $("expenseChart").innerHTML=`<div class="expense-chart-total"><span>${(Exact.truth(Exact.seq(state.language, "en")) ? "Month-to-date cost total" : "本月累计成本")}</span><strong>${money(total)}</strong><small>${(Exact.truth(Exact.seq(state.language, "en")) ? "Shares total 100.0%" : "占比合计 100.0%")}</small></div>${entries.map(([name,value],index)=>`<div class="horizontal-row"><span>${escapeHtml(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${Exact.mul(Exact.div(value, max), 100)}%"></div></div><strong>${compactNumber(value)} <small>${shares[index]}</small></strong></div>`).join("")}`;
}

function shiftDay(amount){const d=parseDate($("selectedDate").value);d.setDate(Exact.add(d.getDate(), amount));$("selectedDate").value=isoDate(d);syncPeriodToDate();renderDashboard();}
function syncPeriodToDate(){const value=$("selectedDate").value;if(Exact.truth(Exact.not(value)))return;const year=value.slice(0,4);if(Exact.truth([...$("selectedYear").options].some(o=>Exact.seq(o.value, year))))$("selectedYear").value=year;$("selectedMonth").value=Exact.toNumber(value.slice(5,7));}

function clone(value) { return JSON.parse(JSON.stringify(value ?? {})); }
function canonical(value) {
  if (Exact.truth(Exact.is(value))) return JSON.stringify(value.toString());
  if (Exact.truth(Array.isArray(value))) return `[${value.map(canonical).join(",")}]`;
  if (Exact.truth(Exact.and(()=>(value), ()=>(Exact.seq(typeof value, "object"))))) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
async function sha256(text) {
  if (Exact.truth(crypto.subtle)) {
    const bytes = new TextEncoder().encode(text);
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2,"0")).join("");
  }
  /* HTTP 裸 IP 不是 secure context；这里保留等价的纯 JS SHA-256。 */
  const rightRotate=(value,amount)=>(value>>>amount)|(value<<(Exact.sub(32, amount))); let mathPow=Math.pow,maxWord=mathPow(2,32),lengthProperty="length",i,j,result="",words=[],ascii=unescape(encodeURIComponent(text)),asciiBitLength=Exact.mul(ascii[lengthProperty], 8),hash=sha256.h=Exact.or(()=>(sha256.h), ()=>([])),k=sha256.k=Exact.or(()=>(sha256.k), ()=>([])),primeCounter=k[lengthProperty],isComposite={};
  for(let candidate=2;Exact.truth(Exact.lt(primeCounter, 64));candidate++){if(Exact.truth(Exact.not(isComposite[candidate]))){for(i=0;Exact.truth(Exact.lt(i, 313));(i = Exact.add(i, candidate)))isComposite[i]=candidate;hash[primeCounter]=(Exact.mul(mathPow(candidate,.5), maxWord))|0;k[primeCounter++]=(Exact.mul(mathPow(candidate,Exact.div(1, 3)), maxWord))|0;}}
  (ascii = Exact.add(ascii, "\x80"));while(Exact.truth(Exact.sub(Exact.mod(ascii[lengthProperty], 64), 56)))(ascii = Exact.add(ascii, "\x00"));for(i=0;Exact.truth(Exact.lt(i, ascii[lengthProperty]));i++){j=ascii.charCodeAt(i);words[i>>2]|=j<<Exact.mul(Exact.mod(Exact.sub(3, i), 4), 8);}words[words[lengthProperty]]=(Exact.div(asciiBitLength, maxWord))|0;words[words[lengthProperty]]=asciiBitLength;
  for(j=0;Exact.truth(Exact.lt(j, words[lengthProperty]));){const w=words.slice(j,(j = Exact.add(j, 16))),oldHash=hash.slice(0);hash=hash.slice(0,8);for(i=0;Exact.truth(Exact.lt(i, 64));i++){const w15=w[Exact.sub(i, 15)],w2=w[Exact.sub(i, 2)],a=hash[0],e=hash[4],temp1=Exact.add(Exact.add(Exact.add(Exact.add(hash[7], rightRotate(e,6)^rightRotate(e,11)^rightRotate(e,25)), (e&hash[5])^((~e)&hash[6])), k[i]), w[i]=(Exact.truth(Exact.lt(i, 16)) ? w[i] : (Exact.add(Exact.add(Exact.add(w[Exact.sub(i, 16)], rightRotate(w15,7)^rightRotate(w15,18)^(w15>>>3)), w[Exact.sub(i, 7)]), rightRotate(w2,17)^rightRotate(w2,19)^(w2>>>10)))|0)),temp2=Exact.add(rightRotate(a,2)^rightRotate(a,13)^rightRotate(a,22), (a&hash[1])^(a&hash[2])^(hash[1]&hash[2]));hash=[(Exact.add(temp1, temp2))|0,a,hash[1],hash[2],(Exact.add(hash[3], temp1))|0,e,hash[5],hash[6]];}for(i=0;Exact.truth(Exact.lt(i, 8));i++)hash[i]=(Exact.add(hash[i], oldHash[i]))|0;}
  for(i=0;Exact.truth(Exact.lt(i, 8));i++)for(j=3;Exact.truth(Exact.add(j, 1));j--){const b=(hash[i]>>(Exact.mul(j, 8)))&255;(result = Exact.add(result, Exact.add((Exact.truth(Exact.lt(b, 16)) ? "0" : ""), b.toString(16))));}return result;
}
function uuid() { return (Exact.truth(crypto.randomUUID) ? crypto.randomUUID() : "10000000-1000-4000-8000-100000000000".replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Exact.div(c, 4)).toString(16))); }
function blankValue(id, numeric=false) {
  const value = $(id).value;
  if (Exact.truth(Exact.seq(value.trim(), ""))) return "";
  return (Exact.truth(numeric) ? (Exact.truth(/Customers$/.test(id)) ? num(value) : (Exact.truth(["ledgerRevenue","ledgerTotalCash","ledgerTotalOnline","ledgerARevenue","ledgerBRevenue"].includes(id)) ? Exact.currency(value) : Exact.decimal(Exact.amount(value)))) : value);
}
function setValue(id, value) { $(id).value = (Exact.truth(entered(value)) ? String(value) : ""); }
function editorDraftKey(section,key){return `${Exact.or(()=>(state.dataset?.id), ()=>(""))}|${section}|${key}`;}
function editorSnapshotEqual(left,right){return Exact.seq(canonical((Exact.truth(Exact.seq(left, undefined)) ? null : left)), canonical((Exact.truth(Exact.seq(right, undefined)) ? null : right)));}
function rememberEditorBaseline(section,key,value,{force=false}={}){
  if(Exact.truth(Exact.or(()=>(Exact.not(section)), ()=>(Exact.not(key)))))return;
  const identity=editorDraftKey(section,key);
  /* A cloud refresh must never overwrite an active local draft. */
  if(Exact.truth(Exact.and(()=>(Exact.not(force)), ()=>(Object.prototype.hasOwnProperty.call(state.editorDrafts,identity)))))return;
  state.editorBaselines[identity]=clone(value);
  if(Exact.truth(editorSnapshotEqual(state.editorDrafts[identity],state.editorBaselines[identity])))delete state.editorDrafts[identity];
  updateEditorDirty();
}
function updateEditorDirty(){
  state.editorDirty=Object.keys(state.editorDrafts).some(identity=>Exact.not(editorSnapshotEqual(state.editorDrafts[identity],state.editorBaselines[identity])));
  return state.editorDirty;
}
function rememberEditorDraft(section,key,value){
  if(Exact.truth(Exact.or(()=>(Exact.not(section)), ()=>(Exact.not(key)))))return false;
  const identity=editorDraftKey(section,key);
  if(Exact.truth(Exact.not(Object.prototype.hasOwnProperty.call(state.editorBaselines,identity))))state.editorBaselines[identity]=clone(value);
  const snapshot=clone(value),baseline=state.editorBaselines[identity];
  if(Exact.truth(editorSnapshotEqual(snapshot,baseline)))delete state.editorDrafts[identity];
  else state.editorDrafts[identity]=snapshot;
  return updateEditorDirty();
}
function readEditorDraft(section,key){if(Exact.truth(Exact.or(()=>(Exact.not(section)), ()=>(Exact.not(key)))))return null;return Exact.or(()=>(state.editorDrafts[editorDraftKey(section,key)]), ()=>(null));}
function forgetEditorDraft(section,key){if(Exact.truth(Exact.or(()=>(Exact.not(section)), ()=>(Exact.not(key)))))return;const identity=editorDraftKey(section,key);delete state.editorDrafts[identity];delete state.editorBaselines[identity];updateEditorDirty();}
function clearEditorDrafts(){state.editorDrafts=Object.create(null);state.editorBaselines=Object.create(null);state.editorDirty=false;}
const editorFieldLabels={
  ledger:{ledgerRevenue:"收入",ledgerFees:"手续费／抽成",ledgerAvailableBalance:"可用余额",ledgerShareholderLoan:"向股东借款",ledgerNewCustomers:"新客人数",ledgerCustomers:"总客人数",ledgerFoodCost:"食材成本",ledgerSpiceCost:"佐料成本",ledgerUtilities:"水电",ledgerOther:"其它",ledgerFoodDetail:"食材明细",ledgerSpiceDetail:"佐料明细",ledgerOtherDetail:"其它明细",ledgerNote:"当日备注"},
  fixed:{fixedLabour:"人工总额",fixedRent:"房租／物业",fixedWaterSpent:"水费支出",fixedElectricSpent:"电费支出",fixedActualWater:"实际使用水费",fixedExpectedWater:"预计水费",fixedActualElectric:"实际使用电费",fixedExpectedElectric:"预计电费",fixedExpectedGas:"预计煤气费",fixedGas:"煤气费",fixedOther:"其它固定成本",fixedNote:"月度备注"}
};
function editorSectionLabel(section,key){
  const labels={ledger:"记账本",fixed:"固定成本",dishes:"菜品明细",food:"食材明细",spice:"佐料明细",inventory:"入库",users:"用户管理"};
  const prefix=Exact.or(()=>(labels[section]), ()=>(section));
  return (Exact.truth(Exact.and(()=>(key), ()=>(Exact.sneq(key, "current")))) ? `${prefix}（${key}）` : prefix);
}
function editorDirtyEntries(){
  const result=[];
  for(const identity of Object.keys(state.editorDrafts)){
    const draft=state.editorDrafts[identity],baseline=state.editorBaselines[identity];
    if(Exact.truth(editorSnapshotEqual(draft,baseline)))continue;
    const parts=identity.split("|"),section=Exact.or(()=>(parts[Exact.sub(parts.length, 2)]), ()=>("")),key=Exact.or(()=>(parts[Exact.sub(parts.length, 1)]), ()=>(""));
    const fields=editorFieldLabels[section],changed=[];
    if(Exact.truth(Exact.and(()=>(Exact.and(()=>(fields), ()=>(draft?.values))), ()=>(baseline?.values))))for(const [id,label] of Object.entries(fields))if(Exact.truth(Exact.not(editorSnapshotEqual(draft.values[id],baseline.values[id]))))changed.push(label);
    if(Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.seq(section, "users")), ()=>(draft?.values))), ()=>(baseline?.values)))){
      if(Exact.truth(Exact.not(editorSnapshotEqual(draft.values.newUser,baseline.values.newUser))))changed.push("新增用户");
      if(Exact.truth(Exact.not(editorSnapshotEqual(draft.values.rows,baseline.values.rows))))changed.push("用户资料／账本权限");
    }
    if(Exact.truth(Exact.and(()=>(Exact.not(changed.length)), ()=>(["dishes","food","spice","inventory"].includes(section)))))changed.push("明细内容");
    result.push({section,key,label:editorSectionLabel(section,key),details:changed});
  }
  return result;
}
function currentRole() { return Exact.or(()=>(state.user?.role), ()=>((Exact.truth(Exact.seq(state.user?.username, "admin")) ? "admin" : "viewer"))); }
function canEdit() { return ["admin","editor","entry"].includes(currentRole()); }
function currentRecord(type,key) {
  const rawKey = String(key ?? "").trim();
  if (Exact.truth(Exact.seq(type, "day"))) {
    const normalized = normalizeDateKey(rawKey);
    /* Prefer the row selected by the normalized sequence index.  This avoids
       returning an older canonical-key record when an imported aggregate
       record (or a later API update) is the authoritative source. */
    const indexed = state.dayRecordMap?.get(normalized);
    if (Exact.truth(indexed)) return indexed;
  }
  const direct = state.recordMap.get(`${type}/${rawKey}`);
  if (Exact.truth(direct)) return direct;
  if (Exact.truth(Exact.seq(type, "day"))) {
    const normalized = normalizeDateKey(rawKey);
    const alias = Exact.or(()=>(state.dayRecordMap?.get(normalized)), ()=>(state.recordMap.get(`day/${normalized}`)));
    if (Exact.truth(alias)) return alias;
    /* Last-resort scan for records returned by an older API shape that was
       not indexed during normalization. */
    for (const record of Exact.or(()=>(state.records), ()=>([]))) {
      if (Exact.truth(Exact.sneq(String(Exact.or(()=>(Exact.or(()=>(record?.record_type), ()=>(record?.type))), ()=>(""))), "day"))) continue;
      const payload = unpackPayload(record);
      if (Exact.truth(dayRowsFromPayload(payload,record.record_key).some(row => Exact.seq(normalizeDateKey(Exact.or(()=>(row?.日期), ()=>(record.record_key))), normalized)))) {
        return {...record,record_type:"day",record_key:String(Exact.or(()=>(record.record_key), ()=>(""))).trim(),payload,_dayDate:normalized,_sourceRecordKey:String(Exact.or(()=>(record.record_key), ()=>(""))).trim(),_sourceRecord:record};
      }
    }
  } else if (Exact.truth(Exact.seq(type, "month"))) {
    const normalized = normalizeMonthKey(rawKey);
    for (const record of Exact.or(()=>(state.records), ()=>([]))) {
      if (Exact.truth(Exact.sneq(String(Exact.or(()=>(Exact.or(()=>(record?.record_type), ()=>(record?.type))), ()=>(""))), "month"))) continue;
      if (Exact.truth(Exact.seq(normalizeMonthKey(record.record_key), normalized))) return {...record,record_type:"month",record_key:String(Exact.or(()=>(record.record_key), ()=>(""))).trim(),payload:unpackPayload(record)};
    }
  }
  return null;
}
function recordVersion(record) { return Exact.or(()=>(Exact.toNumber(record?.version ?? record?.current_version ?? 0)), ()=>(0)); }

async function ensureWebDevice() {
  const storageKey = `restaurant_web_device_${state.dataset.id}`;
  const saved = localStorage.getItem(storageKey);
  if (Exact.truth(saved)) return saved;
  const result = await api("/devices/register", {method:"POST", body:JSON.stringify({dataset_id:state.dataset.id,name:`网页版 · ${Exact.or(()=>(navigator.platform), ()=>("浏览器"))}`,platform:"web"})});
  const id = Exact.or(()=>(result?.id), ()=>(result?.device_id));
  if (Exact.truth(Exact.not(id))) throw new Error("服务器没有返回网页设备编号。");
  localStorage.setItem(storageKey, id);
  return id;
}

async function saveRecord(type,key,payload,resultId) {
  payload=Exact.normalizePayload(payload);
  if (Exact.truth(Exact.not(canEdit()))) throw new Error("当前账号为只读权限，不能修改数据。");
  const record = currentRecord(type,key);
  /* Keep legacy slash-formatted day keys addressable. If such a record is
     edited from the ISO date picker, update it in place instead of creating a
     second record for the same calendar day. */
  const writeKey = Exact.or(()=>(record?.record_key), ()=>(key));
  const oldPayload = (Exact.truth(record) ? unpackPayload(record) : {});
  let writePayload = payload;
  /* Preserve sibling dates when an old record packed multiple daily rows
     under one non-date key.  Editor save functions intentionally submit one
     selected row; merge that row back into the original payload before PUT. */
  if (Exact.truth(Exact.and(()=>(Exact.seq(type, "day")), ()=>(record)))) {
    const sourceRows = dayRowsFromPayload(oldPayload,record.record_key);
    const incomingRows = (Exact.truth(Array.isArray(payload?.daily)) ? payload.daily : []);
    if (Exact.truth(Exact.and(()=>(Exact.gt(sourceRows.length, 1)), ()=>(Exact.seq(incomingRows.length, 1))))) {
      const target = normalizeDateKey(key), incoming = clone(incomingRows[0]);
      let replaced = false;
      const mergedRows = sourceRows.map(source => {
        const sourceDate = normalizeDateKey(Exact.or(()=>(source?.日期), ()=>(record.record_key)));
        if (Exact.truth(Exact.and(()=>(Exact.not(replaced)), ()=>(Exact.seq(sourceDate, target))))) { replaced = true; return {...source,...incoming,日期:Exact.or(()=>(Exact.or(()=>(incoming.日期), ()=>(source.日期))), ()=>(target))}; }
        return clone(source);
      });
      if (Exact.truth(Exact.not(replaced))) mergedRows.push({...incoming,日期:Exact.or(()=>(incoming.日期), ()=>(target))});
      writePayload = {...oldPayload,...payload,daily:mergedRows};
    } else if (Exact.truth(Exact.and(()=>(Exact.not(Array.isArray(payload?.daily))), ()=>(sourceRows.length)))) {
      writePayload = {...oldPayload,...payload,daily:sourceRows};
    }
  }
  if (Exact.truth(Exact.seq(canonical(oldPayload), canonical(writePayload)))) {
    if (Exact.truth(resultId)) $(resultId).textContent = (Exact.truth(Exact.seq(state.language, "en")) ? "Nothing changed, so no change log was created." : "内容没有变化，不会写入修改记录。");
    return false;
  }
  const deviceId = await ensureWebDevice();
  const body = {event_id:uuid(),expected_version:recordVersion(record),occurred_at:new Date().toISOString(),source:"cloud",device_id:deviceId,payload:writePayload,checksum:await sha256(canonical(writePayload))};
  const saved=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/records/${encodeURIComponent(type)}/${encodeURIComponent(writeKey)}`, {method:"PUT",body:JSON.stringify(body)});
  const identity=`${type}/${writeKey}`,normalized={...saved,record_type:type,record_key:writeKey,payload:clone(saved?.payload??writePayload)};
  const index=state.records.findIndex(item=>Exact.seq(`${item.record_type}/${item.record_key}`, identity));
  if(Exact.truth(Exact.gte(index, 0)))state.records[index]=normalized;else state.records.push(normalized);
  normalizeRecords(state.records);
  initializeFilters();renderDashboard();
  if (Exact.truth(resultId)) $(resultId).textContent = (Exact.truth(Exact.seq(state.language, "en")) ? "Saved to the cloud. The sync assistant will update the local copy." : "已保存到云端，云同步助手会自动写回本地。");
  return true;
}

function dayPayload(key) {
  const record=currentRecord("day",key); const source=(Exact.truth(record) ? unpackPayload(record) : {}); const payload=clone(source);
  if (Exact.truth(Exact.not(Array.isArray(payload.daily)))) payload.daily=dayRowsFromPayload(source,Exact.or(()=>(record?.record_key), ()=>(key))).map(clone);
  if (Exact.truth(Exact.not(Array.isArray(payload.dishes)))) payload.dishes=[];
  if (Exact.truth(Exact.not(Array.isArray(payload.fixed_expenses)))) payload.fixed_expenses=[];
  return payload;
}
function dailyRow(payload,key) {
  const target = normalizeDateKey(key);
  const rows = (Exact.truth(Array.isArray(payload?.daily)) ? payload.daily : dayRowsFromPayload(payload,key));
  const matched = rows.reduce((latest,row)=>{
    const date=normalizeDateKey(Exact.or(()=>(row?.日期), ()=>(key)));
    return (Exact.truth(Exact.seq(normalizeDateKey(date), target)) ? row : latest);
  },null);
  /* A legacy day can be represented by more than one cloud record (for
     example, an old slash-formatted total plus a later zero-valued row).
     Merge the canonical date row into the source row used for editing so the
     ledger and dashboard never disagree about the selected day's revenue. */
  const canonicalRow = (Exact.truth(Exact.seq(typeof dayRowForDate, "function")) ? dayRowForDate(target) : null);
  const row = clone(Exact.or(()=>(Exact.or(()=>(matched), ()=>(canonicalRow))), ()=>({日期:target,收益:0})));
  if (Exact.truth(Exact.and(()=>(canonicalRow), ()=>(matched)))) {
    for (const [field,value] of Object.entries(canonicalRow)) {
      if (Exact.truth(Exact.not(entered(value)))) continue;
      const current = row[field];
      if (Exact.truth(Exact.or(()=>(Exact.not(entered(current))), ()=>(Exact.and(()=>(Exact.and(()=>(Exact.and(()=>(Exact.valid(current)), ()=>(Exact.valid(value)))), ()=>(Exact.seq(num(current), 0)))), ()=>(Exact.sneq(num(value), 0))))))) row[field]=value;
    }
  }
  if (Exact.truth(Exact.or(()=>(Exact.not(entered(row.日期))), ()=>(Exact.not(isCanonicalDate(normalizeDateKey(row.日期))))))) row.日期=target;
  // Never borrow another date's data when the selected day is empty.
  const legacyRevenue = legacyRevenueValue(row);
  if (Exact.truth(Exact.and(()=>(Exact.or(()=>(Exact.not(entered(row.收益))), ()=>(Exact.seq(Exact.decimal(Exact.currency(row.收益)), 0)))), ()=>(Exact.sneq(legacyRevenue, undefined))))) row.收益 = legacyRevenue;
  return row;
}

function refreshLedger() {
  const key=Exact.or(()=>($("ledgerDate").value), ()=>($("selectedDate").value)); if(Exact.truth(Exact.not(key)))return;
  const payload=dayPayload(key), row=dailyRow(payload,key);
  const fields={ledgerRevenue:"收益",ledgerNewCustomers:"新客人数量",ledgerCustomers:"总客人数",ledgerFoodCost:"食材成本",ledgerSpiceCost:"佐料成本",ledgerUtilities:"水电",ledgerOther:"其他",ledgerFoodDetail:"食材明细",ledgerSpiceDetail:"佐料明细",ledgerOtherDetail:"其他明细",ledgerNote:"当日备注"};
  Object.entries(fields).forEach(([id,name])=>setValue(id,row[name]));
  /* The dashboard uses the normalized day list. Mirror that exact value into
     the ledger when an old record has no usable split/payment fields. */
  if (Exact.truth(Exact.seq(num($("ledgerRevenue")?.value), 0))) {
    const source=dayRowForDate(key);
    const normalized=(Exact.truth(source) ? dayMetrics(source)?.revenue : 0);
    if (Exact.truth(Exact.and(()=>(Exact.finite(normalized)), ()=>(Exact.sneq(normalized, 0))))) $("ledgerRevenue").value=String(normalized);
  }
}
async function saveLedger() {
  const key=$("ledgerDate").value; if(Exact.truth(Exact.not(key)))throw new Error("请选择日期。");
  const payload=dayPayload(key), row=dailyRow(payload,key);
  Object.assign(row,{日期:key,收益:blankValue("ledgerRevenue",true),新客人数量:blankValue("ledgerNewCustomers",true),总客人数:blankValue("ledgerCustomers",true),食材成本:blankValue("ledgerFoodCost",true),食材明细:blankValue("ledgerFoodDetail"),佐料成本:blankValue("ledgerSpiceCost",true),佐料明细:blankValue("ledgerSpiceDetail"),水电:blankValue("ledgerUtilities",true),其他:blankValue("ledgerOther",true),其他明细:blankValue("ledgerOtherDetail"),当日备注:blankValue("ledgerNote")});
  payload.daily=[row]; await saveRecord("day",key,payload,"ledgerResult");
}
function refreshFixed() {
  const key=$("fixedMonth").value; if(Exact.truth(Exact.not(key)))return; const row=Exact.or(()=>(state.months.get(key)), ()=>({}));
  const fields={fixedLabour:"人工总额",fixedRent:"房租总额",fixedWaterSpent:"水费支出",fixedElectricSpent:"电费支出",fixedActualWater:"实际使用水费",fixedActualElectric:"实际使用电费",fixedGas:"煤气费",fixedOther:"其它固定成本",fixedNote:"月度备注"};
  Object.entries(fields).forEach(([id,name])=>setValue(id,row[name]));
}
async function saveFixed() {
  const key=$("fixedMonth").value;if(Exact.truth(Exact.not(key)))throw new Error("请选择月份。");const record=currentRecord("month",key),payload=clone((Exact.truth(record) ? unpackPayload(record) : {}));const previous=clone(Exact.or(()=>((Exact.or(()=>(payload.monthly_fixed), ()=>([]))).slice(Exact.neg(1))[0]), ()=>({})));
  Object.assign(previous,{月份:key,人工总额:blankValue("fixedLabour",true),房租总额:blankValue("fixedRent",true),水费支出:blankValue("fixedWaterSpent",true),电费支出:blankValue("fixedElectricSpent",true),实际使用水费:blankValue("fixedActualWater",true),实际使用电费:blankValue("fixedActualElectric",true),煤气费:blankValue("fixedGas",true),其它固定成本:blankValue("fixedOther",true),月度备注:blankValue("fixedNote")});payload.monthly_fixed=[previous];await saveRecord("month",key,payload,"fixedResult");
}

function renderHistory(){
  const month=Exact.or(()=>($("historyMonth").value), ()=>((Exact.or(()=>($("selectedDate").value), ()=>(""))).slice(0,7)));if(Exact.truth(Exact.not(month)))return;
  const items=state.days.filter(row=>String(row.日期).startsWith(month));
  const rows=items.map(row=>{const m=dayMetrics(row);return `<tr><td>${escapeHtml(m.date)}</td><td>${money(m.revenue)}</td><td>${compactNumber(m.newCustomers)}</td><td>${compactNumber(m.customers)}</td><td>${money(m.food)}</td><td>${escapeHtml(Exact.or(()=>(row.佐料明细), ()=>("")))}</td><td>${money(m.fixedDaily)}</td><td>${escapeHtml(Exact.or(()=>(row.其他明细), ()=>("")))}</td><td>${escapeHtml(Exact.or(()=>(row.当日备注), ()=>("")))}</td><td>${pointValue("gross",m.gross,m.revenue)}</td><td>${pointValue("net",m.net,m.revenue)}</td></tr>`;}).join("");
  const fixed=fixedBreakdown(Exact.toNumber(month.slice(0,4)),Exact.toNumber(month.slice(5,7)));
  const fixedRow=`<tr class="month-summary-row"><td colspan="11"> ${month} ${(Exact.truth(Exact.seq(state.language, "en")) ? "Fixed cost summary" : "本月固定成本汇总")} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Labour" : "人工")}: ${money(fixed.labour)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Rent" : "房租")}: ${money(fixed.rent)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Water" : "水费")}: ${money(fixed.water)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Electricity" : "电费")}: ${money(fixed.electric)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Gas" : "煤气")}: ${money(fixed.gas)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Other" : "其它")}: ${money(fixed.other)}</td></tr>`;
  const blanks=Array.from({length:Exact.math.max(0,Exact.sub(25, items.length))},()=>'<tr class="blank-row"><td>&nbsp;</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>').join("");
  $("historyRows").innerHTML=Exact.add(Exact.add(fixedRow, rows), blanks);
}

function dishData(key) {
  const payload=dayPayload(key); const raw=Exact.or(()=>(Exact.or(()=>(payload.dishes.find(row=>Exact.seq(String(Exact.or(()=>(row.日期), ()=>(""))), key))), ()=>(payload.dishes[Exact.sub(payload.dishes.length, 1)]))), ()=>({})); let rows=[];
  try { rows=(Exact.truth(Array.isArray(raw.菜品数据)) ? raw.菜品数据 : JSON.parse(Exact.or(()=>(raw.菜品数据), ()=>("[]")))); } catch(_){ rows=[]; }
  return {payload,raw:clone(raw),rows:(Exact.truth(Array.isArray(rows)) ? rows : [])};
}
function addDishRow(data={}) {
  const tr=document.createElement("tr"); tr.innerHTML=`<td><input data-field="菜品名称" value="${escapeHtml(Exact.or(()=>(data.菜品名称), ()=>("")))}"></td><td><input data-field="菜品份数" type="number" step="1" min="0" value="${(Exact.truth(entered(data.菜品份数)) ? escapeHtml(data.菜品份数) : "")}"></td><td><textarea data-field="食材明细">${escapeHtml(Exact.or(()=>(data.食材明细), ()=>("")))}</textarea></td><td><input data-field="成本" type="number" step="0.01" value="${(Exact.truth(entered(data.成本)) ? escapeHtml(data.成本) : "")}"></td><td><input data-field="备注" value="${escapeHtml(Exact.or(()=>(data.备注), ()=>("")))}"></td><td><button class="danger-link edit-action" data-remove>${(Exact.truth(Exact.seq(state.language, "en")) ? "Delete" : "删除")}</button></td>`;tr.querySelector("[data-remove]").addEventListener("click",()=>{tr.remove();updateDishTotal();});tr.querySelectorAll("input").forEach(input=>input.addEventListener("input",updateDishTotal));$("dishRows").appendChild(tr);updateDishTotal();
}
function refreshDishes(){const key=$("dishDate").value;if(Exact.truth(Exact.not(key)))return;const {rows}=dishData(key);$("dishRows").innerHTML="";rows.forEach(addDishRow);if(Exact.truth(Exact.not(rows.length)))addDishRow();}
function updateDishTotal(){const total=[...$("dishRows").querySelectorAll('[data-field="成本"]')].reduce((sum,input)=>Exact.add(sum, Exact.decimal(Exact.currency(input.value))),0);$("dishTotal").textContent=Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? "Total ingredient cost: " : "当日全部食材成本合计："), money(total));}
async function saveDishes(){const key=$("dishDate").value;if(Exact.truth(Exact.not(key)))throw new Error("请选择日期。");const {payload,raw}=dishData(key);const rows=[...$("dishRows").querySelectorAll("tr")].map(tr=>{const get=name=>tr.querySelector(`[data-field="${name}"]`).value;return {菜品名称:get("菜品名称"),菜品份数:(Exact.truth(Exact.seq(get("菜品份数").trim(), "")) ? "" : num(get("菜品份数"))),食材明细:get("食材明细"),成本:(Exact.truth(Exact.seq(get("成本").trim(), "")) ? "" : Exact.decimal(Exact.currency(get("成本")))),备注:get("备注")};}).filter(row=>Object.values(row).some(entered));const total=rows.reduce((s,row)=>Exact.add(s, Exact.decimal(Exact.currency(row.成本))),0);Object.assign(raw,{日期:key,菜品明细:rows.map(row=>row.菜品名称).filter(Exact.truth).join("；"),菜品数据:JSON.stringify(rows),总成本:total,备注:Exact.or(()=>(raw.备注), ()=>(""))});payload.dishes=[raw];await saveRecord("day",key,payload,"dishResult");}

function parseDetailRows(raw){
  if(Exact.truth(Exact.not(entered(raw))))return [];
  if(Exact.truth(Array.isArray(raw)))return raw;
  const text=String(raw).trim();
  try{const parsed=JSON.parse(text);if(Exact.truth(Array.isArray(parsed)))return parsed;}catch(_){}
  return text.split(/[；;\n]+/).map(part=>part.trim()).filter(Exact.truth).map(part=>({名称:part,数量:"",单位:"",单价:"",总价:"",备注:""}));
}
function addDetailRow(kind,data={}){const body=$((Exact.truth(Exact.seq(kind, "food")) ? "foodRows" : "spiceRows")),tr=document.createElement("tr"),name=data.名称??data.食材名称??data.佐料名称??data.name??"",quantity=data.数量??data.quantity??"",unit=data.单位??data.unit??"",price=data.单价??data.unit_price??"",total=data.总价??data.total??"",note=data.备注??data.note??"";tr.innerHTML=`<td><input data-detail="name" value="${escapeHtml(name)}"></td><td><input data-detail="quantity" type="number" step="any" value="${escapeHtml(quantity)}"></td><td><input data-detail="unit" value="${escapeHtml(unit)}"></td><td><input data-detail="price" type="number" step="0.01" value="${escapeHtml(price)}"></td><td><input data-detail="total" type="number" step="0.01" value="${escapeHtml(total)}"></td><td><input data-detail="note" value="${escapeHtml(note)}"></td><td><button class="danger-link edit-action" data-remove>${(Exact.truth(Exact.seq(state.language, "en")) ? "Delete" : "删除")}</button></td>`;const fields={};tr.querySelectorAll("[data-detail]").forEach(input=>{fields[input.dataset.detail]=input;input.addEventListener("input",()=>{if(Exact.truth(Exact.and(()=>(Exact.and(()=>(["quantity","price"].includes(input.dataset.detail)), ()=>(Exact.sneq(fields.quantity.value, "")))), ()=>(Exact.sneq(fields.price.value, "")))))fields.total.value=(Exact.mul(num(fields.quantity.value), num(fields.price.value))).toFixed(2);updateDetailTotal(kind);});});tr.querySelector("[data-remove]").addEventListener("click",()=>{tr.remove();updateDetailTotal(kind);});body.appendChild(tr);}
function detailRows(kind){return [...$((Exact.truth(Exact.seq(kind, "food")) ? "foodRows" : "spiceRows")).querySelectorAll("tr")].map(tr=>{const get=name=>tr.querySelector(`[data-detail="${name}"]`).value;return {名称:get("name"),数量:(Exact.truth(Exact.seq(get("quantity").trim(), "")) ? "" : num(get("quantity"))),单位:get("unit"),单价:(Exact.truth(Exact.seq(get("price").trim(), "")) ? "" : Exact.decimal(Exact.price(get("price")))),总价:(Exact.truth(Exact.seq(get("total").trim(), "")) ? "" : Exact.decimal(Exact.currency(get("total")))),备注:get("note")};}).filter(row=>Object.values(row).some(entered));}
function updateDetailTotal(kind){const rows=detailRows(kind),total=rows.reduce((sum,row)=>Exact.add(sum, Exact.decimal(Exact.currency(row.总价))),0);$((Exact.truth(Exact.seq(kind, "food")) ? "foodTotal" : "spiceTotal")).textContent=`${(Exact.truth(Exact.seq(state.language, "en")) ? "Items" : "种类")}: ${rows.length} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Total" : "总金额")}: ${money(total)}`;}
function refreshDetail(kind){const dateId=(Exact.truth(Exact.seq(kind, "food")) ? "foodDate" : "spiceDate"),key=$(dateId).value;if(Exact.truth(Exact.not(key)))return;const row=dailyRow(dayPayload(key),key),raw=row[(Exact.truth(Exact.seq(kind, "food")) ? "食材明细" : "佐料明细")],body=$((Exact.truth(Exact.seq(kind, "food")) ? "foodRows" : "spiceRows"));body.innerHTML="";parseDetailRows(raw).forEach(item=>addDetailRow(kind,item));if(Exact.truth(Exact.not(body.children.length)))addDetailRow(kind);updateDetailTotal(kind);}
async function saveDetail(kind){const dateId=(Exact.truth(Exact.seq(kind, "food")) ? "foodDate" : "spiceDate"),resultId=(Exact.truth(Exact.seq(kind, "food")) ? "foodResult" : "spiceResult"),key=$(dateId).value,payload=dayPayload(key),row=dailyRow(payload,key),rows=detailRows(kind),total=rows.reduce((sum,item)=>Exact.add(sum, Exact.decimal(Exact.currency(item.总价))),0);row.日期=key;row[(Exact.truth(Exact.seq(kind, "food")) ? "食材成本" : "佐料成本")]=total;row[(Exact.truth(Exact.seq(kind, "food")) ? "食材明细" : "佐料明细")]=JSON.stringify(rows);payload.daily=[row];await saveRecord("day",key,payload,resultId);}

const statsMetrics={
  revenue:{zh:"收入",en:"Revenue",value:m=>m.revenue},gross:{zh:"毛利润（毛利率）",en:"Gross Profit (Margin)",value:m=>m.gross,rate:true},grossRate:{zh:"毛利率（%）",en:"Gross Margin (%)",value:m=>(Exact.truth(m.revenue) ? Exact.mul(Exact.div(m.gross, m.revenue), 100) : 0),percent:true},net:{zh:"净利润（净利率）",en:"Net Profit (Margin)",value:m=>m.net,rate:true},netRate:{zh:"净利率（%）",en:"Net Margin (%)",value:m=>(Exact.truth(m.revenue) ? Exact.mul(Exact.div(m.net, m.revenue), 100) : 0),percent:true},customers:{zh:"总客人数",en:"Total Customers",value:m=>m.customers},newCustomers:{zh:"新客人数量",en:"New Customers",value:m=>m.newCustomers},oldCustomers:{zh:"老客人数",en:"Returning Customers",value:m=>m.oldCustomers},ticket:{zh:"客单价（平均）",en:"Average Spend",value:m=>(Exact.truth(m.customers) ? Exact.div(m.revenue, m.customers) : 0)},food:{zh:"食材成本",en:"Ingredient Cost",value:m=>m.food},spice:{zh:"佐料成本",en:"Seasoning Cost",value:m=>m.spice},foodSpice:{zh:"食材＋佐料成本",en:"Ingredient + Seasoning",value:m=>Exact.add(m.food, m.spice)},utilities:{zh:"水电＋其他",en:"Utilities + Other",value:m=>Exact.add(m.waterDaily, m.other)},fixedDaily:{zh:"固定成本",en:"Fixed Cost",value:m=>m.fixedDaily},variable:{zh:"（总成本－固定成本）",en:"(Total Cost − Fixed Cost)",value:m=>m.variable},total:{zh:"总成本",en:"Total Cost",value:m=>m.total}
};
delete statsMetrics.food;
delete statsMetrics.spice;
function statsMetricName(key){const item=statsMetrics[key];return (Exact.truth(item) ? item[state.language] : key);}
function selectedStatsMetrics(){const selected=[...document.querySelectorAll("#statsMetricChecks input:checked")].map(input=>input.value);return (Exact.truth(selected.length) ? selected : ["net"]);}
function filteredStatsItems(){const year=$("statsYear").value,months=[...document.querySelectorAll('#statsMonthChecks input:checked')].map(input=>Exact.toNumber(input.value)),weekdays=[...document.querySelectorAll('#statsWeekdayChecks input:checked')].map(input=>Exact.toNumber(input.value));return state.days.map(dayMetrics).filter(m=>Exact.and(()=>(Exact.and(()=>(Exact.and(()=>(m), ()=>(m.date.startsWith(`${year}-`)))), ()=>(months.includes(Exact.toNumber(m.date.slice(5,7)))))), ()=>(weekdays.includes(Exact.mod(Exact.add(parseDate(m.date).getDay(), 6), 7)))));}
function statsValueText(key,value,item){const meta=statsMetrics[key];if(Exact.truth(meta?.percent))return `${Exact.decimal(value).toFixed(1)}%`;if(Exact.truth(meta?.rate))return pointValue(key,value,item.revenue);if(Exact.truth(["customers","newCustomers","oldCustomers"].includes(key)))return compactNumber(value);return money(value);}
function renderStats(){
  if(Exact.truth(Exact.not($("statsYear").options.length)))return;const items=filteredStatsItems(),metrics=selectedStatsMetrics(),primary=metrics[0],meta=statsMetrics[primary];
  const trendItems=items.map(item=>({...item,statsPrimary:meta.value(item)}));$("statsTrendTitle").textContent=`${statsMetricName(primary)} · ${(Exact.truth(Exact.seq(state.language, "en")) ? "Detailed Trend" : "所选日期明细趋势")}`;
  $("statsChart").innerHTML=(Exact.truth(trendItems.length) ? lineChartMarkup(trendItems,(Exact.truth(meta.rate) ? primary : "plain"),"statsPrimary") : `<div class="empty-chart">${(Exact.truth(Exact.seq(state.language, "en")) ? "No matching data" : "没有符合筛选条件的数据")}</div>`);if(Exact.truth(trendItems.length))bindInteractiveChart($("statsChart"));
  const year=$("statsYear").value,monthValues=Array.from({length:12},(_,index)=>{const list=items.filter(m=>Exact.seq(Exact.toNumber(m.date.slice(5,7)), Exact.add(index, 1))),value=list.reduce((sum,item)=>Exact.add(sum, meta.value(item)),0);return {month:Exact.add(index, 1),value};}),monthMax=Exact.math.max(1,...monthValues.map(item=>Exact.math.abs(item.value)));
  $("statsMonthlyChart").innerHTML=monthValues.map(item=>{const revenue=items.filter(m=>Exact.seq(Exact.toNumber(m.date.slice(5,7)), item.month)).reduce((s,m)=>Exact.add(s, m.revenue),0),label=statsValueText(primary,item.value,{revenue});return `<div data-chart-point data-tooltip="${year}-${String(item.month).padStart(2,"0")}\n${escapeHtml(label)}"><b>${escapeHtml(label)}</b><i style="height:${Exact.math.max(3,Exact.mul(Exact.div(Exact.math.abs(item.value), monthMax), 240))}px;${(Exact.truth(Exact.lt(item.value, 0)) ? "background:#dc5964" : "")}"></i><span>${item.month}${(Exact.truth(Exact.seq(state.language, "en")) ? "" : "月")}</span></div>`;}).join("");bindInteractiveChart($("statsMonthlyChart"));
  const groups=Array.from({length:7},()=>[]);items.forEach(item=>groups[Exact.mod(Exact.add(parseDate(item.date).getDay(), 6), 7)].push(item));const weekdayValues=groups.map(group=>(Exact.truth(group.length) ? Exact.div(group.reduce((sum,item)=>Exact.add(sum, meta.value(item)),0), group.length) : 0)),weekdayMax=Exact.math.max(1,...weekdayValues.map(Exact.math.abs)),weekNames=(Exact.truth(Exact.seq(state.language, "en")) ? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] : ["周一","周二","周三","周四","周五","周六","周日"]);
  $("statsWeekdayChart").innerHTML=weekdayValues.map((value,index)=>{const label=statsValueText(primary,value,{revenue:Exact.div(groups[index].reduce((s,m)=>Exact.add(s, m.revenue),0), Exact.math.max(1,groups[index].length))});return `<div class="vertical-bar" data-chart-point data-tooltip="${weekNames[index]}\n${escapeHtml(label)}"><b>${escapeHtml(label)}</b><i style="height:${Exact.math.max(2,Exact.mul(Exact.div(Exact.math.abs(value), weekdayMax), 82))}%;${(Exact.truth(Exact.lt(value, 0)) ? "background:linear-gradient(#ed7780,#d14e58)" : "")}"></i><em>${weekNames[index]}</em></div>`;}).join("");bindInteractiveChart($("statsWeekdayChart"));
  const head=`<tr><th>${(Exact.truth(Exact.seq(state.language, "en")) ? "Type" : "类型")}</th><th>${(Exact.truth(Exact.seq(state.language, "en")) ? "Date / Month" : "日期／月份")}</th><th>${(Exact.truth(Exact.seq(state.language, "en")) ? "Weekday" : "星期")}</th>${metrics.map(key=>`<th>${escapeHtml(statsMetricName(key))}</th>`).join("")}</tr>`;$("statsHead").innerHTML=head;
  const detailRows=(Exact.truth($("statsDetail").checked) ? items.map(item=>`<tr><td>${(Exact.truth(Exact.seq(state.language, "en")) ? "Detail" : "明细")}</td><td>${item.date}</td><td>${weekNames[Exact.mod(Exact.add(parseDate(item.date).getDay(), 6), 7)]}</td>${metrics.map(key=>`<td>${statsValueText(key,statsMetrics[key].value(item),item)}</td>`).join("")}</tr>`).join("") : "");
  const averageRows=(Exact.truth($("statsAverage").checked) ? Array.from({length:12},(_,index)=>{const list=items.filter(m=>Exact.seq(Exact.toNumber(m.date.slice(5,7)), Exact.add(index, 1)));if(Exact.truth(Exact.not(list.length)))return"";const elapsed=periodElapsedDays(Exact.toNumber(year),Exact.add(index, 1));const summary=aggregate(list,elapsed);return `<tr><td>${(Exact.truth(Exact.seq(state.language, "en")) ? "Average" : "平均")}</td><td>${year}-${String(Exact.add(index, 1)).padStart(2,"0")}</td><td>—</td>${metrics.map(key=>{const value=Exact.div(list.reduce((sum,item)=>Exact.add(sum, statsMetrics[key].value(item)),0), Exact.math.max(1,summary.elapsedDays));return `<td>${statsValueText(key,value,{revenue:summary.avgRevenue})}</td>`;}).join("")}</tr>`;}).join("") : "");$("statsRows").innerHTML=Exact.add(detailRows, averageRows);
  const views=new Set([...document.querySelectorAll('.stats-view-check:checked')].map(input=>input.value));$("statsTrendCard").classList.toggle("hidden",Exact.not(views.has("trend")));$("statsMonthlyCard").classList.toggle("hidden",Exact.not(views.has("monthly")));$("statsWeekdayCard").classList.toggle("hidden",Exact.not(views.has("weekday")));$("statsTableCard").classList.toggle("hidden",Exact.not(views.has("table")));
}
function initializeStats(){
  const years=[...new Set(state.days.map(row=>String(row.日期).slice(0,4)))].sort().reverse();if(Exact.truth(Exact.not(years.length)))years.push(String(new Date().getFullYear()));$("statsYear").innerHTML=years.map(y=>`<option>${y}</option>`).join("");$("statsYear").value=(Exact.truth(years.includes($("selectedYear").value)) ? $("selectedYear").value : years[0]);
  if(Exact.truth(Exact.not($("statsMonthChecks").querySelector("input")))){const selectedMonth=Exact.toNumber(Exact.or(()=>($("selectedMonth").value), ()=>(Exact.add(new Date().getMonth(), 1))));for(let month=1;Exact.truth(Exact.lte(month, 12));month++)$("statsMonthChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${month}" ${(Exact.truth(Exact.seq(month, selectedMonth)) ? "checked" : "")}> ${month}${(Exact.truth(Exact.seq(state.language, "en")) ? "" : "月")}</label>`);const names=(Exact.truth(Exact.seq(state.language, "en")) ? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] : ["一","二","三","四","五","六","日"]);names.forEach((name,index)=>$("statsWeekdayChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${index}" checked> ${name}</label>`));Object.entries(statsMetrics).forEach(([key,item])=>$("statsMetricChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${key}" ${(Exact.truth(Exact.seq(key, "net")) ? "checked" : "")}> <span data-metric-label="${key}">${escapeHtml(item[state.language])}</span></label>`));document.querySelectorAll("#pageStats input,#pageStats select").forEach(input=>input.addEventListener("change",renderStats));}
  renderStats();
}

function workbookYear(){const year=Exact.toNumber($("userWorkbookYear").value);if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.not(Exact.integer(year))), ()=>(Exact.lt(year, 2000)))), ()=>(Exact.gt(year, 2200)))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Choose a valid year." : "请选择有效年份。"));return year;}
function workbookPath(kind){if(Exact.truth(Exact.not(state.dataset)))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "No ledger is selected." : "尚未选择账本。"));const route=(Exact.truth(Exact.seq(kind, "user_merge")) ? "user-merge" : kind);return `/datasets/${encodeURIComponent(state.dataset.id)}/workbooks/${route}`;}
function setOperationResult(id,text,error=false){const node=$(id);node.textContent=text;node.classList.toggle("error",error);}
async function downloadUserWorkbook(){const year=workbookYear(),name=`${Exact.or(()=>(state.dataset?.name), ()=>("账本"))}_${year}_用户数据.xlsx`;setOperationResult("userWorkbookResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Preparing workbook…" : "正在生成用户 Excel…"));try{await downloadApiFile(`${workbookPath("user")}?year=${year}`,name);setOperationResult("userWorkbookResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Download started." : "用户 Excel 已开始下载。"));}catch(error){setOperationResult("userWorkbookResult",error.message,true);}}
async function downloadInternalWorkbook(){const name=`${Exact.or(()=>(state.dataset?.name), ()=>("账本"))}_内部数据.xlsx`;setOperationResult("internalWorkbookResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Preparing workbook…" : "正在生成内部 Excel…"));try{await downloadApiFile(workbookPath("internal"),name);setOperationResult("internalWorkbookResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Download started." : "内部 Excel 已开始下载。"));}catch(error){setOperationResult("internalWorkbookResult",error.message,true);}}
async function uploadWorkbook(event,kind){
  const file=event.target.files?.[0];if(Exact.truth(Exact.not(file)))return;
  const resultId=(Exact.truth(Exact.seq(kind, "internal")) ? "internalWorkbookResult" : "userWorkbookResult");
  try{
    if(Exact.truth(Exact.gt(file.size, Exact.mul(Exact.mul(25, 1024), 1024))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "The workbook must be smaller than 25 MB." : "Excel 文件不能超过 25 MB。"));
    if(Exact.truth(Exact.and(()=>(Exact.seq(kind, "internal")), ()=>(Exact.sneq(currentRole(), "admin")))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Administrator permission is required." : "只有管理员可以上传内部 Excel。"));
    if(Exact.truth(Exact.and(()=>(Exact.seq(kind, "internal")), ()=>(Exact.not(confirm((Exact.truth(Exact.seq(state.language, "en")) ? `Replace every record in “${Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id))}” with this internal workbook? User assignments will remain unchanged.` : `确定用这个内部 Excel 整体替换“${Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id))}”的全部数据吗？用户与账本的绑定不会改变。`)))))))return;
    if(Exact.truth(Exact.and(()=>(["user","user_merge"].includes(kind)), ()=>(Exact.sneq(currentRole(), "admin")))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Only administrators can upload user Excel workbooks." : "只有管理员可以上传用户 Excel。"));
    const selectedYear=(Exact.truth(["user","user_merge"].includes(kind)) ? workbookYear() : null),ledgerName=Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id));
    if(Exact.truth(Exact.and(()=>(Exact.seq(kind, "user")), ()=>(Exact.not(confirm((Exact.truth(Exact.seq(state.language, "en")) ? `Replace the entire ${selectedYear} user workbook in “${ledgerName}”? Dates and months missing from the uploaded file will be deleted. Other years will remain. The ingredient dictionary and fixed-cost categories will be replaced from this file.` : `确定整体替换“${ledgerName}”的 ${selectedYear} 年用户账本吗？上传文件中缺少的日期和月份会从云端删除，其他年份保留；食材字典与固定成本类别会按本文件替换。`)))))))return;
    if(Exact.truth(Exact.and(()=>(Exact.seq(kind, "user_merge")), ()=>(Exact.not(confirm((Exact.truth(Exact.seq(state.language, "en")) ? `Merge this workbook into ${selectedYear} in “${ledgerName}”? Amounts, quantities and detail rows will be added; existing unit prices stay unchanged. No missing records will be deleted.` : `确定把这份 Excel 合并到“${ledgerName}”的 ${selectedYear} 年吗？金额、数量和明细会累加；原账本单价保持不变；上传文件中没有的记录不会删除。`)))))))return;
    setOperationResult(resultId,(Exact.truth(Exact.seq(state.language, "en")) ? "Uploading and validating…" : "正在上传并校验 Excel…"));
    const activeDatasetId=state.dataset.id,form=new FormData();form.append("file",file);
    const suffix=(Exact.truth(["user","user_merge"].includes(kind)) ? `?year=${selectedYear}` : "");
    const response=await api(`${workbookPath(kind)}${suffix}`,{method:"POST",body:form});
    const count=Exact.toNumber(response?.imported_records??response?.records??0),warnings=(Exact.truth(Array.isArray(response?.warnings)) ? response.warnings.filter(Exact.truth) : []),warningText=(Exact.truth(warnings.length) ? (Exact.truth(Exact.seq(state.language, "en")) ? ` Warnings: ${warnings.join("; ")}` : ` 提示：${warnings.join("；")}`) : "");
    if(Exact.truth(Exact.and(()=>(Exact.seq(kind, "user")), ()=>(Exact.or(()=>(Exact.seq(response?.mode, "replace_year")), ()=>(Exact.sneq(response?.replace_year, undefined))))))){
      const responseYear=Exact.toNumber(response?.replace_year),year=(Exact.truth(Exact.and(()=>(Exact.integer(responseYear)), ()=>(Exact.gte(responseYear, 2000)))) ? responseYear : Exact.or(()=>(Exact.toNumber(response?.year)), ()=>(selectedYear)));
      const counts=[["created",(Exact.truth(Exact.seq(state.language, "en")) ? "created" : "新增")],["updated",(Exact.truth(Exact.seq(state.language, "en")) ? "updated" : "更新")],["deleted",(Exact.truth(Exact.seq(state.language, "en")) ? "deleted" : "删除")],["unchanged",(Exact.truth(Exact.seq(state.language, "en")) ? "unchanged" : "未变化")]].filter(([key])=>Exact.sneq(response?.[key], undefined)).map(([key,label])=>`${label} ${Exact.or(()=>(Exact.toNumber(response[key])), ()=>(0))}`);
      const detail=(Exact.truth(counts.length) ? (Exact.truth(Exact.seq(state.language, "en")) ? ` (${counts.join(", ")})` : `（${counts.join("，")}）`) : "");
      setOperationResult(resultId,Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? `Replaced the entire ${year} workbook; ${count} records imported${detail}.` : `已整体替换 ${year} 年用户账本，共导入 ${count} 条记录${detail}。`), warningText));
    }else if(Exact.truth(Exact.or(()=>(Exact.seq(kind, "user_merge")), ()=>(Exact.seq(response?.mode, "merge"))))){
      const counts=[["created",(Exact.truth(Exact.seq(state.language, "en")) ? "created" : "新增")],["updated",(Exact.truth(Exact.seq(state.language, "en")) ? "updated" : "更新")],["unchanged",(Exact.truth(Exact.seq(state.language, "en")) ? "unchanged" : "未变化")]].filter(([key])=>Exact.sneq(response?.[key], undefined)).map(([key,label])=>`${label} ${Exact.or(()=>(Exact.toNumber(response[key])), ()=>(0))}`);
      const detail=(Exact.truth(counts.length) ? (Exact.truth(Exact.seq(state.language, "en")) ? ` (${counts.join(", ")})` : `（${counts.join("，")}）`) : "");
      setOperationResult(resultId,Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? `Merged ${count} records; amounts and quantities were added, unit prices preserved${detail}.` : `已合并 ${count} 条记录，金额和数量已累加，单价保持原值${detail}。`), warningText));
    }else setOperationResult(resultId,Exact.add((Exact.truth(Exact.seq(state.language, "en")) ? `Imported ${count} records.` : `上传完成，共导入 ${count} 条记录。`), warningText));
    await loadCloudData({datasetId:activeDatasetId});
  }catch(error){setOperationResult(resultId,Exact.or(()=>(error.message), ()=>(String(error))),true);}finally{event.target.value="";}
}
function slugDatasetId(name){const ascii=String(Exact.or(()=>(name), ()=>(""))).trim().toLowerCase().replace(/[^a-z0-9_-]+/g,"-").replace(/^-+|-+$/g,"");return `${Exact.or(()=>(ascii), ()=>("ledger"))}-${Date.now().toString(36)}`;}
async function createDataset(){if(Exact.truth(Exact.sneq(currentRole(), "admin")))throw new Error("只有管理员可以建立账本。");const name=$("newDatasetName").value.trim();if(Exact.truth(Exact.not(name)))throw new Error("请输入账本名称。");const id=Exact.or(()=>($("newDatasetId").value.trim()), ()=>(slugDatasetId(name)));if(Exact.truth(Exact.not(/^[A-Za-z0-9._-]{1,64}$/.test(id))))throw new Error("账本 ID 只能使用英文字母、数字、点、下划线和连字符，最长 64 位。");const created=await api("/datasets",{method:"POST",body:JSON.stringify({id,name,schema_version:2})});$("datasetAdminResult").textContent="独立账本已建立。";$("newDatasetName").value="";$("newDatasetId").value="";await loadCloudData({datasetId:created.id});await loadUsers();}
async function renameCurrentDataset(){
  if(Exact.truth(Exact.sneq(currentRole(), "admin")))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Administrator permission is required." : "只有管理员可以重命名账本。"));
  if(Exact.truth(Exact.not(state.dataset)))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "No ledger is selected." : "尚未选择账本。"));
  const id=state.dataset.id,name=$("currentDatasetName").value.trim();
  if(Exact.truth(Exact.not(name)))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Ledger name cannot be empty." : "账本名称不能为空。"));
  if(Exact.truth(Exact.seq(name, Exact.or(()=>(state.dataset.name), ()=>(state.dataset.id))))){setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? "The ledger name is unchanged." : "账本名称没有变化。"));return;}
  setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Saving the new name…" : "正在保存新名称…"));
  await api(`/datasets/${encodeURIComponent(id)}`,{method:"PATCH",body:JSON.stringify({name})});
  await loadCloudData({datasetId:id});await loadUsers();
  setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Ledger renamed. Its ID and data are unchanged." : "账本已重命名；账本 ID 和数据均未改变。"));
}
async function deleteCurrentDataset(){
  if(Exact.truth(Exact.sneq(currentRole(), "admin")))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Administrator permission is required." : "只有管理员可以删除账本。"));
  const dataset=state.dataset;if(Exact.truth(Exact.not(dataset)))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "No ledger is selected." : "尚未选择账本。"));
  if(Exact.truth(isTestDataset(dataset)))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "The Test demonstration ledger cannot be deleted." : "Test 独立演示账本不可删除。"));
  const name=Exact.or(()=>(dataset.name), ()=>(dataset.id)),promptText=(Exact.truth(Exact.seq(state.language, "en")) ? `This permanently deletes “${name}” and all of its data. Type the complete ledger name to confirm:` : `此操作会永久删除“${name}”及其全部数据。请输入完整账本名称以确认：`);
  const typed=prompt(promptText,"");if(Exact.truth(Exact.seq(typed, null)))return;
  if(Exact.truth(Exact.sneq(typed, name))){setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Name did not match. The ledger was not deleted." : "输入的名称不一致，账本没有删除。"),true);return;}
  setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? "Deleting ledger…" : "正在删除账本…"));
  const deletedId=dataset.id,nextId=Exact.or(()=>(selectDatasetFrom(state.datasets.filter(item=>Exact.sneq(item.id, deletedId)))?.id), ()=>(""));
  await api(`/datasets/${encodeURIComponent(deletedId)}?confirm_name=${encodeURIComponent(name)}`,{method:"DELETE"});
  localStorage.removeItem(datasetStorageKey());state.dataset=null;
  await loadCloudData({datasetId:nextId});await loadUsers();
  setOperationResult("currentDatasetAdminResult",(Exact.truth(Exact.seq(state.language, "en")) ? `“${name}” was permanently deleted.` : `“${name}”已永久删除。`));
}

function applyLanguage(){
  const english=Exact.seq(state.language, "en");document.documentElement.lang=(Exact.truth(english) ? "en" : "zh-CN");document.title=(Exact.truth(english) ? "Restaurant Cost Manager" : "餐饮成本管家云端");
  document.querySelectorAll("[data-zh][data-en]").forEach(node=>{node.textContent=node.dataset[(Exact.truth(english) ? "en" : "zh")];});
  document.querySelectorAll("[data-label-zh][data-label-en]").forEach(label=>{const text=label.dataset[(Exact.truth(english) ? "labelEn" : "labelZh")];const first=[...label.childNodes].find(node=>Exact.seq(node.nodeType, Node.TEXT_NODE));if(Exact.truth(first))first.textContent=text;});
  $("languageButton").textContent=(Exact.truth(english) ? "中文" : "English");$("loginLanguageButton").textContent=(Exact.truth(english) ? "中文" : "English");
  $("addFoodRowButton").textContent=(Exact.truth(english) ? "＋ Add Row" : "＋ 新增空行");$("addSpiceRowButton").textContent=(Exact.truth(english) ? "＋ Add Row" : "＋ 新增空行");
  const trendLabels={net:["净利润 (净利率)","Net Profit (Margin)"],gross:["毛利润 (毛利率)","Gross Profit (Margin)"],food:["食材成本 (包括佐料)","Ingredient + Seasoning Cost"],revenue:["收入 (Revenue)","Revenue"]};
  [...$("trendMetric").options].forEach(option=>option.textContent=trendLabels[option.value][(Exact.truth(english) ? 1 : 0)]);
  const roles={viewer:["只读","Read only"],entry:["录入（收入独立30分钟／明细新增12小时）","Entry (independent 30m income / 12h detail additions)"],editor:["修改权限","Editor"],admin:["管理员","Administrator"]};[...$("newRole").options].forEach(option=>{if(Exact.truth(roles[option.value]))option.textContent=roles[option.value][(Exact.truth(english) ? 1 : 0)];});
  document.querySelectorAll("[data-metric-label]").forEach(node=>node.textContent=statsMetricName(node.dataset.metricLabel));
  document.querySelectorAll("#statsMonthChecks label").forEach(label=>{const input=label.querySelector("input");if(Exact.truth(input))label.lastChild.textContent=(Exact.truth(english) ? ` ${input.value}` : ` ${input.value}月`);});
  const weekNames=(Exact.truth(english) ? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] : ["一","二","三","四","五","六","日"]);document.querySelectorAll("#statsWeekdayChecks label").forEach((label,index)=>{if(Exact.truth(label.lastChild))label.lastChild.textContent=` ${weekNames[index]}`;});
  if(Exact.truth(state.token)){$("ledgerPermission").textContent=(Exact.truth(canEdit()) ? (Exact.truth(english) ? "Editable" : "可修改") : (Exact.truth(english) ? "Read only" : "只读账号"));if(Exact.truth($("inventoryPermission")))$("inventoryPermission").textContent=(Exact.truth(canEdit()) ? (Exact.truth(english) ? "Editable" : "可修改") : (Exact.truth(english) ? "Read only" : "只读账号"));$("changeLogNavButton")?.classList.toggle("hidden",Exact.or(()=>(Exact.not(["admin","editor"].includes(currentRole()))), ()=>(isTestAccount())));renderCurrentDatasetAdmin();initializeFilters();renderDashboard();renderHistory();if(Exact.truth(Exact.seq(typeof renderInventory, "function")))renderInventory();if(Exact.truth(Exact.seq(state.activePage, "stats")))renderStats();if(Exact.truth(Exact.and(()=>(Exact.seq(state.activePage, "users")), ()=>(Exact.seq(currentRole(), "admin")))))loadUsers().catch(showError);if(Exact.truth(Exact.seq(state.activePage, "changes")))loadChangeLogs().catch(showError);}
  localStorage.setItem("restaurant_language",state.language);
}

function toggleLanguage(){state.language=(Exact.truth(Exact.seq(state.language, "en")) ? "zh" : "en");applyLanguage();}

function userDatasetIds(user){if(Exact.truth(Array.isArray(user?.dataset_ids)))return user.dataset_ids.map(String);if(Exact.truth(Array.isArray(user?.datasets)))return user.datasets.map(item=>String(Exact.or(()=>(item?.id), ()=>(item))));return [];}
function selectedOptionValues(select){return [...select.selectedOptions].map(option=>option.value);}
function datasetOptions(selected=[]){const chosen=new Set(selected.map(String));return state.datasets.map(item=>`<option value="${escapeHtml(item.id)}" ${(Exact.truth(chosen.has(String(item.id))) ? "selected" : "")}>${escapeHtml(Exact.or(()=>(item.name), ()=>(item.id)))}</option>`).join("");}
function defaultDatasetOptions(ids,selected=""){const allowed=new Set(ids.map(String)),items=state.datasets.filter(item=>allowed.has(String(item.id)));return Exact.add(`<option value="">—</option>`, items.map(item=>`<option value="${escapeHtml(item.id)}" ${(Exact.truth(Exact.seq(String(item.id), String(selected))) ? "selected" : "")}>${escapeHtml(Exact.or(()=>(item.name), ()=>(item.id)))}</option>`).join(""));}
function syncDefaultDataset(multiple,defaultSelect){const old=defaultSelect.value,ids=selectedOptionValues(multiple);defaultSelect.innerHTML=defaultDatasetOptions(ids,(Exact.truth(ids.includes(old)) ? old : Exact.or(()=>(ids[0]), ()=>(""))));}
function renderNewUserDatasets(){const multiple=$("newUserDatasets"),defaultSelect=$("newUserDefaultDataset");const keep=selectedOptionValues(multiple);multiple.innerHTML=datasetOptions((Exact.truth(keep.length) ? keep : (Exact.truth(state.dataset) ? [state.dataset.id] : [])));syncDefaultDataset(multiple,defaultSelect);}
function usersEditorSnapshot(){
  const newUser={
    username:Exact.or(()=>($("newUsername")?.value), ()=>("")),
    displayName:Exact.or(()=>($("newDisplayName")?.value), ()=>("")),
    password:Exact.or(()=>($("newPassword")?.value), ()=>("")),
    role:Exact.or(()=>($("newRole")?.value), ()=>("")),
    datasets:(Exact.truth($("newUserDatasets")) ? selectedOptionValues($("newUserDatasets")) : []),
    defaultDataset:Exact.or(()=>($("newUserDefaultDataset")?.value), ()=>(""))
  };
  const rows=[...(Exact.or(()=>($("userRows")?.querySelectorAll("tr")), ()=>([])))].map(tr=>({
    id:Exact.or(()=>(tr.dataset.userId), ()=>("")),
    displayName:Exact.or(()=>(tr.querySelector("[data-display]")?.value), ()=>("")),
    role:Exact.or(()=>(tr.querySelector("[data-role]")?.value), ()=>("")),
    datasets:(Exact.truth(tr.querySelector("[data-datasets]")) ? selectedOptionValues(tr.querySelector("[data-datasets]")) : []),
    defaultDataset:Exact.or(()=>(tr.querySelector("[data-default-dataset]")?.value), ()=>("")),
    password:Exact.or(()=>(tr.querySelector("[data-password]")?.value), ()=>("")),
    active:Exact.or(()=>(tr.dataset.active), ()=>(""))
  }));
  return {values:{newUser,rows}};
}
function captureUsersDraft(){return rememberEditorDraft("users","current",usersEditorSnapshot());}
function rememberUsersBaseline(){rememberEditorBaseline("users","current",usersEditorSnapshot());}
async function loadUsers(){
  if(Exact.truth(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(isTestAccount()))))return;
  const en=Exact.seq(state.language, "en"),response=await api("/users"),users=(Exact.truth(Array.isArray(response)) ? response : Exact.or(()=>(response?.items), ()=>([]))),roles={viewer:(Exact.truth(en) ? "Read only" : "只读"),entry:(Exact.truth(en) ? "Entry (independent 30m income / 12h detail additions)" : "录入（收入独立30分钟／明细新增12小时）"),editor:(Exact.truth(en) ? "Editor" : "可修改"),admin:(Exact.truth(en) ? "Administrator" : "管理员")};
  renderNewUserDatasets();
  $("userRows").innerHTML=users.map(user=>{
    const ids=userDatasetIds(user),locked=Exact.or(()=>(Exact.seq(user.is_test, true)), ()=>(Exact.seq(String(Exact.or(()=>(user.username), ()=>(""))).toLowerCase(), "test"))),disabled=(Exact.truth(locked) ? " disabled" : "");
    return `<tr data-user-id="${escapeHtml(user.id)}" data-active="${Exact.sneq(user.is_active, false)}" data-system-user="${locked}"><td><strong>${escapeHtml(user.username)}</strong>${(Exact.truth(locked) ? `<small class="system-user-note">${(Exact.truth(en) ? "Public read-only demo" : "公开只读演示")}</small>` : "")}</td><td><input data-display value="${escapeHtml(Exact.or(()=>(user.display_name), ()=>("")))}"></td><td><select data-role${disabled}>${Object.entries(roles).map(([role,label])=>`<option value="${role}" ${(Exact.truth(Exact.seq(user.role, role)) ? "selected" : "")}>${label}</option>`).join("")}</select></td><td><select data-datasets multiple size="3"${disabled}>${datasetOptions(ids)}</select></td><td><select data-default-dataset${disabled}>${defaultDatasetOptions(ids,Exact.or(()=>(user.default_dataset_id), ()=>("")))}</select></td><td>${(Exact.truth(Exact.seq(user.is_active, false)) ? (Exact.truth(en) ? "Disabled" : "已停用") : (Exact.truth(en) ? "Active" : "正常"))}</td><td><input data-password type="password" placeholder="${(Exact.truth(en) ? "Enter a new password" : "输入新密码")}"></td><td><button class="soft" data-save-user>${(Exact.truth(en) ? "Save" : "保存")}</button> <button class="danger-link" data-disable-user${disabled}>${(Exact.truth(Exact.seq(user.is_active, false)) ? (Exact.truth(en) ? "Restore" : "恢复") : (Exact.truth(en) ? "Disable" : "停用"))}</button></td></tr>`;
  }).join("");
  $("userRows").querySelectorAll("[data-datasets]:not(:disabled)").forEach(select=>select.addEventListener("change",()=>syncDefaultDataset(select,select.closest("tr").querySelector("[data-default-dataset]"))));
  $("userRows").querySelectorAll("[data-save-user]").forEach(button=>button.addEventListener("click",()=>safely(()=>updateUser(button.closest("tr"),false))));
  $("userRows").querySelectorAll("[data-disable-user]:not(:disabled)").forEach(button=>button.addEventListener("click",()=>safely(()=>updateUser(button.closest("tr"),true))));
  $("userRows").querySelectorAll("tr[data-user-id]").forEach(tr=>{if(Exact.truth(Exact.or(()=>(Exact.seq(tr.dataset.systemUser, "true")), ()=>(tr.querySelector("[data-delete-user]")))))return;const button=document.createElement("button");button.className="danger-link";button.type="button";button.textContent=(Exact.truth(en) ? "Delete" : "删除用户");button.dataset.deleteUser="true";tr.lastElementChild?.append(" ",button);button.addEventListener("click",()=>safely(()=>deleteUser(tr)));});
  $("userRows").querySelectorAll("[data-delete-user]:not(:disabled)").forEach(button=>button.addEventListener("click",()=>safely(()=>deleteUser(button.closest("tr")))));
  rememberUsersBaseline();
}
async function createUser(){const ids=selectedOptionValues($("newUserDatasets"));const body={username:$("newUsername").value.trim(),display_name:$("newDisplayName").value.trim(),password:$("newPassword").value,role:$("newRole").value,dataset_ids:ids,default_dataset_id:Exact.or(()=>($("newUserDefaultDataset").value), ()=>(null))};if(Exact.truth(Exact.or(()=>(Exact.not(body.username)), ()=>(Exact.not(body.password)))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Username and initial password are required." : "账号和初始密码不能为空。"));if(Exact.truth(Exact.and(()=>(Exact.sneq(body.role, "admin")), ()=>(Exact.not(ids.length)))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Assign at least one ledger." : "非管理员账号至少要分配一个账本。"));await api("/users",{method:"POST",body:JSON.stringify(body)});forgetEditorDraft("users","current");$("newPassword").value="";$("userResult").textContent=(Exact.truth(Exact.seq(state.language, "en")) ? "User created." : "用户创建成功。");await loadUsers();}
async function updateUser(tr,toggle){const ids=selectedOptionValues(tr.querySelector("[data-datasets]"));const body={display_name:tr.querySelector("[data-display]").value,role:tr.querySelector("[data-role]").value,dataset_ids:ids,default_dataset_id:Exact.or(()=>(tr.querySelector("[data-default-dataset]").value), ()=>(null))};if(Exact.truth(Exact.and(()=>(Exact.sneq(body.role, "admin")), ()=>(Exact.not(ids.length)))))throw new Error((Exact.truth(Exact.seq(state.language, "en")) ? "Assign at least one ledger." : "非管理员账号至少要分配一个账本。"));const password=tr.querySelector("[data-password]").value;if(Exact.truth(password))body.password=password;if(Exact.truth(toggle))body.is_active=Exact.sneq(tr.dataset.active, "true");await api(`/users/${encodeURIComponent(tr.dataset.userId)}`,{method:"PATCH",body:JSON.stringify(body)});forgetEditorDraft("users","current");$("userResult").textContent=(Exact.truth(toggle) ? (Exact.truth(Exact.seq(state.language, "en")) ? "Account status updated." : "账号状态已更新。") : (Exact.truth(Exact.seq(state.language, "en")) ? "User saved." : "用户资料与账本绑定已保存。"));await loadUsers();}
async function deleteUser(tr){const username=Exact.or(()=>(tr.querySelector("strong")?.textContent), ()=>("该用户"));if(Exact.truth(Exact.not(confirm(`确定删除用户“${username}”吗？该操作不可恢复。`))))return;if(Exact.truth(Exact.sneq(prompt(`请输入用户名 ${username} 以确认删除：`,""), username)))return;await api(`/users/${encodeURIComponent(tr.dataset.userId)}`,{method:"DELETE"});$("userResult").textContent=`用户“${username}”已删除。`;await loadUsers();}

function auditActionLabel(action){const labels={name_correction:["品名更正","Name correction"],name_correction_reindex:["关联来源同步版本","Linked source version update"]};return Exact.or(()=>(Exact.or(()=>(labels[action]?.[(Exact.truth(Exact.seq(state.language, "en")) ? 1 : 0)]), ()=>(action))), ()=>("修改"));}
function auditSourceLabel(source){return (Exact.truth(Exact.seq(source, "inventory_name_correction")) ? (Exact.truth(Exact.seq(state.language, "en")) ? "Inventory name correction" : "库存品名更正") : Exact.or(()=>(source), ()=>("cloud")));}
async function loadChangeLogs(){
  const target=$("changeLogRows");if(Exact.truth(Exact.or(()=>(Exact.not(target)), ()=>(Exact.not(["admin","editor"].includes(currentRole()))))))return;
  const rows=await api(`/audit?dataset_id=${encodeURIComponent(Exact.or(()=>(state.dataset?.id), ()=>("")))}&hours=8784&limit=500`);
  const items=(Exact.truth(Array.isArray(rows)) ? rows : Exact.or(()=>(rows?.items), ()=>([])));
  target.innerHTML=(Exact.truth(items.length) ? items.map(item=>{const when=Exact.or(()=>(Exact.or(()=>(item.created_at), ()=>(item.occurred_at))), ()=>("")),action=auditActionLabel(item.action),location=`${Exact.or(()=>(item.record_type), ()=>(""))} ${Exact.or(()=>(item.record_key), ()=>(""))}`.trim(),deleteCell=(Exact.truth(Exact.seq(currentRole(), "admin")) ? `<td><button type="button" class="danger-link" data-delete-audit="${escapeHtml(Exact.or(()=>(item.id), ()=>("")))}">${(Exact.truth(Exact.seq(state.language, "en")) ? "Delete" : "删除")}</button></td>` : "<td class=\"admin-only audit-admin-column hidden\"></td>");return `<tr><td>${escapeHtml((Exact.truth(when) ? new Date(when).toLocaleString((Exact.truth(Exact.seq(state.language, "en")) ? "en-US" : "zh-CN")) : "—"))}</td><td>${escapeHtml(Exact.or(()=>(Exact.or(()=>(item.actor_label), ()=>(item.actor_username))), ()=>("—")))}</td><td>${escapeHtml(action)}</td><td>${escapeHtml(Exact.or(()=>(Exact.or(()=>(state.dataset?.name), ()=>(item.dataset_id))), ()=>("—")))}</td><td>${escapeHtml(Exact.or(()=>(location), ()=>("—")))}</td><td>${escapeHtml(auditSourceLabel(item.source))} · v${escapeHtml(item.to_version??"")}</td>${deleteCell}</tr>`;}).join("") : `<tr><td colspan="7">${(Exact.truth(Exact.seq(state.language, "en")) ? "No changes in the last 366 days." : "近 366 天没有非管理员修改记录。")}</td></tr>`);
  target.querySelectorAll("[data-delete-audit]").forEach(button=>button.addEventListener("click",()=>safely(()=>deleteAuditLog(button.dataset.deleteAudit))));
}
async function deleteAuditLog(auditId){
  if(Exact.truth(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(Exact.not(auditId)))))return;
  if(Exact.truth(Exact.not(confirm((Exact.truth(Exact.seq(state.language, "en")) ? "Delete this change record permanently?" : "确定永久删除这条修改记录吗？")))))return;
  await api(`/audit/${encodeURIComponent(auditId)}`,{method:"DELETE"});
  await loadChangeLogs();
}

function refreshOpenEditors(){const date=Exact.or(()=>($("selectedDate").value), ()=>(isoDate(new Date()))),month=date.slice(0,7);["ledgerDate","dishDate","foodDate","spiceDate"].forEach(id=>{if(Exact.truth(Exact.not($(id).value)))$(id).value=date;});if(Exact.truth(Exact.not($("fixedMonth").value)))$("fixedMonth").value=month;if(Exact.truth(Exact.not($("historyMonth").value)))$("historyMonth").value=month;refreshLedger();refreshFixed();renderHistory();refreshDishes();refreshDetail("food");refreshDetail("spice");if(Exact.truth(Exact.seq(typeof renderInventory, "function")))renderInventory();if(Exact.truth($("statsYear").options.length))renderStats();}
function editorDiscardEntriesHtml(entries,english){
  if(Exact.truth(Exact.not(entries.length)))return `<p>${(Exact.truth(english) ? "There are unsaved changes." : "当前有未保存的修改。")}</p>`;
  return `<p>${(Exact.truth(english) ? "The following areas were changed:" : "以下位置有未保存修改：")}</p><ul class="unsaved-change-list">${entries.map(entry=>`<li><strong>${escapeHtml((Exact.truth(english) ? Exact.or(()=>({ledger:"Ledger",fixed:"Fixed costs",dishes:"Dishes",food:"Ingredients",spice:"Seasonings",inventory:"Inventory"}[entry.section]), ()=>(entry.label)) : entry.label))}</strong>${(Exact.truth(entry.details.length) ? `：${entry.details.map(escapeHtml).join("、")}` : "")}</li>`).join("")}</ul>`;
}
function allowEditorNavigation(onConfirm=null){
  updateEditorDirty();
  if(Exact.truth(Exact.not(state.editorDirty))){if(Exact.truth(onConfirm))onConfirm();return true;}
  if(Exact.truth($("unsavedNavigationBlocker")))return false;
  const english=Exact.seq(state.language, "en"),entries=editorDirtyEntries(),overlay=document.createElement("div");
  overlay.id="unsavedNavigationBlocker";overlay.className="pro-modal-backdrop";overlay.setAttribute("role","alertdialog");overlay.setAttribute("aria-modal","true");
  let confirmed=false;
  const close=()=>{overlay.remove();document.removeEventListener("keydown",onKey);};
  const onKey=event=>{if(Exact.truth(Exact.seq(event.key, "Escape")))close();};
  const renderFirst=()=>{const ledgerEntry=entries.find(entry=>Exact.and(()=>(Exact.and(()=>(Exact.seq(entry.section, "ledger")), ()=>(entry.key))), ()=>(Exact.sneq(entry.key, "current"))));overlay.innerHTML=`<section class="pro-modal unsaved-warning-modal"><header><h2>${(Exact.truth(english) ? " Unsaved changes" : " 有未保存修改")}</h2></header><div class="modal-body">${editorDiscardEntriesHtml(entries,english)}<p>${(Exact.truth(english) ? "Do you want to discard these changes and continue?" : "是否放弃这些修改并继续？")}</p></div><footer><button type="button" class="pro-button" data-unsaved-cancel>${(Exact.truth(Exact.and(()=>(ledgerEntry), ()=>(Exact.seq(state.activePage, "overview")))) ? (Exact.truth(english) ? "No, edit in Ledger" : "否，去记账本修改") : (Exact.truth(english) ? "No, stay" : "否，留下修改"))}</button><button type="button" class="pro-button red" data-unsaved-abandon>${(Exact.truth(english) ? "Yes, discard" : "是，放弃修改")}</button></footer></section>`;overlay.querySelector("[data-unsaved-cancel]").addEventListener("click",()=>{if(Exact.truth(Exact.and(()=>(ledgerEntry), ()=>(Exact.seq(state.activePage, "overview"))))){if(Exact.truth($("ledgerDate")))$("ledgerDate").value=ledgerEntry.key;state.editorNavigationBypass=true;try{close();showPage("ledger");}finally{state.editorNavigationBypass=false;}}else close();});overlay.querySelector("[data-unsaved-abandon]").addEventListener("click",renderSecond);overlay.querySelector("[data-unsaved-cancel]").focus();};
  const renderSecond=()=>{overlay.innerHTML=`<section class="pro-modal unsaved-warning-modal"><header><h2>${(Exact.truth(english) ? "Confirm discard" : "再次确认放弃修改")}</h2></header><div class="modal-body">${editorDiscardEntriesHtml(entries,english)}<p>${(Exact.truth(english) ? "This will permanently discard the unsaved changes. Continue?" : "放弃后这些未保存内容将被清除，确定继续吗？")}</p></div><footer><button type="button" class="pro-button" data-unsaved-back>${(Exact.truth(english) ? "No, go back" : "否，返回修改")}</button><button type="button" class="pro-button red" data-unsaved-confirm>${(Exact.truth(english) ? "Yes, discard and continue" : "是，确认放弃并继续")}</button></footer></section>`;overlay.querySelector("[data-unsaved-back]").addEventListener("click",renderFirst);overlay.querySelector("[data-unsaved-confirm]").addEventListener("click",()=>{if(Exact.truth(confirmed))return;confirmed=true;/* Discard first, then perform the requested navigation.  Refreshing an
    editor here can hydrate the legacy row again and recreate the draft that
    the user just discarded, which was the source of the confirmation loop. */state.editorNavigationBypass=true;try{clearEditorDrafts();close();onConfirm?.();}finally{state.editorNavigationBypass=false;}});overlay.querySelector("[data-unsaved-back]").focus();};
  document.body.appendChild(overlay);document.addEventListener("keydown",onKey);renderFirst();return false;
}
function showPage(page){if(Exact.truth(Exact.and(()=>(Exact.seq(page, "users")), ()=>(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(isTestAccount()))))))page="overview";if(Exact.truth(Exact.and(()=>(Exact.seq(page, "changes")), ()=>(Exact.or(()=>(Exact.not(["admin","editor"].includes(currentRole()))), ()=>(isTestAccount()))))))page="overview";if(Exact.truth(Exact.and(()=>(Exact.seq(page, "data")), ()=>(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(isTestAccount()))))))page="overview";if(Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.sneq(page, state.activePage)), ()=>(state.editorDirty))), ()=>(Exact.not(state.editorNavigationBypass)))))return allowEditorNavigation(()=>showPage(page));state.activePage=page;document.querySelectorAll(".app-page").forEach(node=>node.classList.toggle("hidden",Exact.sneq(node.id, `page${page[0].toUpperCase()}${page.slice(1)}`)));document.querySelectorAll('[data-page="data"]').forEach(node=>node.classList.toggle("hidden",Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(isTestAccount()))));let activeButton=null;document.querySelectorAll("[data-page]").forEach(button=>{const active=Exact.seq(button.dataset.page, page);button.classList.toggle("active",active);if(Exact.truth(active))activeButton=button;});if(Exact.truth(Exact.and(()=>(activeButton), ()=>(window.matchMedia("(max-width: 1180px)").matches)))){const behavior=(Exact.truth(window.matchMedia("(prefers-reduced-motion: reduce)").matches) ? "auto" : "smooth");requestAnimationFrame(()=>activeButton.scrollIntoView({block:"nearest",inline:"center",behavior}));}if(Exact.truth(Exact.and(()=>(Exact.seq(page, "ledger")), ()=>(Exact.seq(typeof refreshLedger, "function")))))refreshLedger();if(Exact.truth(Exact.seq(page, "stats")))initializeStats();if(Exact.truth(Exact.and(()=>(Exact.seq(page, "inventory")), ()=>(Exact.seq(typeof renderInventory, "function")))))renderInventory();if(Exact.truth(Exact.seq(page, "users")))loadUsers().catch(showError);if(Exact.truth(Exact.seq(page, "changes")))loadChangeLogs().catch(showError);if(Exact.truth(Exact.seq(page, "workbooks"))){$("workbookDatasetName").textContent=Exact.or(()=>(Exact.or(()=>(state.dataset?.name), ()=>(state.dataset?.id))), ()=>("—"));document.querySelectorAll(".admin-only").forEach(node=>node.classList.toggle("hidden",Exact.sneq(currentRole(), "admin")));renderCurrentDatasetAdmin();}if(Exact.truth(Exact.seq(typeof renderCashPosition, "function")))renderCashPosition();return true;}
function showError(error){$("notice").textContent=Exact.or(()=>(error.message), ()=>(String(error)));$("notice").classList.remove("hidden");}
async function safely(action){try{await action();}catch(error){showError(error);}}
function shiftStatsYear(amount){const target=String(Exact.add(Exact.toNumber(Exact.or(()=>($("statsYear").value), ()=>(new Date().getFullYear()))), amount));if(Exact.truth(Exact.not([...$("statsYear").options].some(option=>Exact.seq(option.value, target)))))$("statsYear").add(new Option(target,target));$("statsYear").value=target;renderStats();}

document.querySelectorAll("[data-page]").forEach(button=>button.addEventListener("click",()=>{if(Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.seq(state.activePage, "overview")), ()=>(state.editorDirty))), ()=>(editorDirtyEntries().some(entry=>Exact.seq(entry.section, "ledger")))))){state.editorNavigationBypass=true;try{showPage("ledger");}finally{state.editorNavigationBypass=false;}return;}showPage(button.dataset.page);}));
$("loginForm").addEventListener("submit",login);$("testLoginButton").addEventListener("click",loginAsTest);$("logoutButton").addEventListener("click",()=>logout(false));$("loginLanguageButton").addEventListener("click",toggleLanguage);$("languageButton").addEventListener("click",toggleLanguage);$("datasetSelect").addEventListener("change",()=>{const target=$("datasetSelect").value;if(Exact.truth(state.editorDirty)){renderDatasetSwitcher();allowEditorNavigation(()=>loadCloudData({datasetId:target}).catch(showError));return;}loadCloudData({datasetId:target}).catch(showError);});$("previousDay").addEventListener("click",()=>shiftDay(Exact.neg(1)));$("nextDay").addEventListener("click",()=>shiftDay(1));$("todayButton").addEventListener("click",()=>{$("selectedDate").value=isoDate(new Date());syncPeriodToDate();renderDashboard();});$("selectedDate").addEventListener("change",()=>{syncPeriodToDate();renderDashboard();});$("selectedMonth").addEventListener("change",renderDashboard);$("selectedYear").addEventListener("change",renderDashboard);$("trendMetric").addEventListener("change",renderDashboard);
$("historyMonth").addEventListener("change",renderHistory);$("statsPreviousYear").addEventListener("click",()=>shiftStatsYear(Exact.neg(1)));$("statsThisYear").addEventListener("click",()=>{const year=String(new Date().getFullYear()),select=$("statsYear");if(Exact.truth(Exact.not([...select.options].some(option=>Exact.seq(option.value, year)))))select.add(new Option(year,year));select.value=year;renderStats();});$("statsNextYear").addEventListener("click",()=>shiftStatsYear(1));$("createUserButton").addEventListener("click",()=>safely(createUser));$("newUserDatasets").addEventListener("change",()=>syncDefaultDataset($("newUserDatasets"),$("newUserDefaultDataset")));$("downloadUserWorkbook").addEventListener("click",downloadUserWorkbook);$("downloadInternalWorkbook").addEventListener("click",downloadInternalWorkbook);$("uploadUserWorkbook").addEventListener("change",event=>uploadWorkbook(event,"user"));$("mergeUserWorkbook").addEventListener("change",event=>uploadWorkbook(event,"user_merge"));$("uploadInternalWorkbook").addEventListener("change",event=>uploadWorkbook(event,"internal"));$("renameDatasetButton").addEventListener("click",()=>safely(renameCurrentDataset));$("deleteDatasetButton").addEventListener("click",()=>safely(deleteCurrentDataset));$("createDatasetButton").addEventListener("click",()=>safely(createDataset));
document.addEventListener("pointerdown",touchSession,{passive:true});document.addEventListener("keydown",touchSession,{passive:true});
/* Auto-refresh performs API calls every few seconds, but only direct activity
   may renew the two-hour session.  Check independently so an idle open tab
   returns to the login view without needing a reload. */
setInterval(()=>{
  if(Exact.truth(Exact.not(state.token)))return;
  try{
    const session=JSON.parse(Exact.or(()=>(localStorage.getItem("restaurant_session")), ()=>("{}")));
    if(Exact.truth(Exact.or(()=>(Exact.not(Exact.toNumber(session.expiresAt))), ()=>(Exact.lte(Exact.toNumber(session.expiresAt), Date.now())))))logout(true);
  }catch(_){logout(true);}
},10_000);
document.addEventListener("input",event=>{const target=event.target;if(Exact.truth(Exact.and(()=>(target.closest?.("#appView")), ()=>(Exact.not(target.matches('input[type="date"],input[type="month"],select')))))){const tracked=window.captureWebEditorDraft?.(target);if(Exact.truth(tracked))updateEditorDirty();}});
document.addEventListener("change",event=>{const target=event.target;if(Exact.truth(Exact.and(()=>(target.closest?.("#appView")), ()=>(Exact.not(target.matches('input[type="date"],input[type="month"]')))))){const tracked=window.captureWebEditorDraft?.(target);if(Exact.truth(tracked))updateEditorDirty();}});
$("username").value=Exact.or(()=>(localStorage.getItem("restaurant_last_username")), ()=>(""));applyLanguage();
if(Exact.truth(restoreSession())){enterApp().catch(()=>logout(true));}else{$("bootView").classList.add("hidden");$("loginView").classList.remove("hidden");document.body.classList.remove("booting");}
