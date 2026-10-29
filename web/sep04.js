/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

/* Sep04V1 final behaviour: independent permissions, cash ledger and audit filters. */
(() => {
  const permanentRole = () => Exact.or(()=>(state.user?.role), ()=>((Exact.truth(Exact.seq(state.user?.username, "admin")) ? "admin" : "viewer")));
  const roleRank = {viewer:0,entry:1,editor:2,admin:3};
  const activeBusinessDate = () => {
    const ids = {ledger:"ledgerDate",food:"foodDate",spice:"spiceDate",dishes:"dishDate"};
    return normalizeDateKey(Exact.or(()=>(Exact.or(()=>($(ids[state.activePage])?.value), ()=>($("selectedDate")?.value))), ()=>(isoDate(new Date()))));
  };
  function scheduledRoleForDate(day=activeBusinessDate()) {
    let best = permanentRole();
    const now = Date.now(), dataset = Exact.or(()=>(state.dataset?.id), ()=>(""));
    for (const grant of Exact.or(()=>(state.user?.temporary_permissions), ()=>([]))) {
      const starts = Date.parse(Exact.or(()=>(grant.starts_at), ()=>(""))), ends = Date.parse(Exact.or(()=>(grant.ends_at), ()=>("")));
      if (Exact.truth(Exact.or(()=>(Exact.sneq(grant.dataset_id, dataset)), ()=>(Exact.not(Exact.and(()=>(Exact.lte(starts, now)), ()=>(Exact.lt(now, ends)))))))) continue;
      if (Exact.truth(Exact.or(()=>(Exact.lt(day, grant.business_start_date)), ()=>(Exact.gt(day, grant.business_end_date))))) continue;
      if (Exact.truth(Exact.gt(Exact.or(()=>(roleRank[grant.permission_role]), ()=>(0)), Exact.or(()=>(roleRank[best]), ()=>(0))))) best = grant.permission_role;
    }
    return best;
  }
  const baseCurrentRole = currentRole;
  currentRole = function(){
    return (Exact.truth(["ledger","food","spice","dishes"].includes(state.activePage)) ? scheduledRoleForDate() : baseCurrentRole());
  };
  const baseCanEdit = canEdit;
  canEdit = function(){ return Exact.or(()=>(baseCanEdit()), ()=>(["entry","editor"].includes(scheduledRoleForDate()))); };

  function applyScheduledUi(){
    const writable = canEdit();
    document.body.classList.toggle("read-only", Exact.not(writable));
    if (Exact.truth(Exact.and(()=>($("ledgerPermission")), ()=>(Exact.seq(state.activePage, "ledger"))))) {
      const effective = scheduledRoleForDate();
      $("ledgerPermission").textContent = (Exact.truth(["admin","editor"].includes(effective)) ? "可修改" : (Exact.truth(Exact.seq(effective, "entry")) ? "可录入" : "只读账号"));
    }
  }

  const baseShowPage = showPage;
  showPage = function(page){
    if (Exact.truth(Exact.and(()=>(Exact.seq(page, "cash")), ()=>(Exact.not(["admin","editor"].includes(permanentRole())))))) page = "overview";
    if (Exact.truth(Exact.and(()=>(Exact.seq(page, "grants")), ()=>(Exact.sneq(permanentRole(), "admin"))))) page = "overview";
    const result = baseShowPage(page);
    applyScheduledUi();
    if (Exact.truth(Exact.seq(page, "cash"))) loadCashLedgerV4().catch(showError);
    if (Exact.truth(Exact.seq(page, "grants"))) loadTemporaryPermissionsV4().catch(showError);
    if (Exact.truth(Exact.and(()=>(Exact.and(()=>(Exact.seq(page, "ledger")), ()=>(Exact.seq(scheduledRoleForDate(), "entry")))), ()=>(state.dataset?.id)))) {
      api(`/datasets/${encodeURIComponent(state.dataset.id)}/entry-windows`).then(rows => {
        state.entryWindows = (Exact.truth(Array.isArray(rows)) ? rows : Exact.or(()=>(rows?.items), ()=>([])));
        renderEntryTiming();
      }).catch(()=>{});
    }
    return result;
  };

  const baseEnterApp = enterApp;
  enterApp = async function(){
    await baseEnterApp();
    $("cashPositionCard")?.remove();
    $("cashNavButton")?.classList.toggle("hidden", Exact.or(()=>(Exact.not(["admin","editor"].includes(permanentRole()))), ()=>(isTestAccount())));
    $("grantNavButton")?.classList.toggle("hidden", Exact.or(()=>(Exact.sneq(permanentRole(), "admin")), ()=>(isTestAccount())));
    applyScheduledUi();
  };

  const baseLoadCloudDataV4 = loadCloudData;
  loadCloudData = async function(options={}){
    const result = await baseLoadCloudDataV4(options);
    $("cashNavButton")?.classList.toggle("hidden", Exact.or(()=>(Exact.not(["admin","editor"].includes(permanentRole()))), ()=>(isTestAccount())));
    $("grantNavButton")?.classList.toggle("hidden", Exact.or(()=>(Exact.sneq(permanentRole(), "admin")), ()=>(isTestAccount())));
    applyScheduledUi();
    return result;
  };

  function cashPayloadV4(){
    const record = Exact.or(()=>(currentRecord("global","cash_position")), ()=>(currentRecord("global","cash_balance")));
    const payload = clone((Exact.truth(record) ? unpackPayload(record) : {}));
    if (Exact.truth(Exact.and(()=>(Exact.not(entered(payload.opening_balance))), ()=>(entered(payload.base_balance))))) payload.opening_balance = payload.base_balance;
    if (Exact.truth(Exact.and(()=>(Exact.not(payload.opening_date)), ()=>(payload.as_of_date)))) payload.opening_date = payload.as_of_date;
    if (Exact.truth(Exact.not(Array.isArray(payload.transactions)))) payload.transactions = [];
    return payload;
  }
  function isCashForceEntryV4(item){
    return Exact.or(()=>(Exact.seq(String(Exact.or(()=>(item?.mode), ()=>(""))).toLowerCase(), "force")), ()=>(Exact.seq(String(Exact.or(()=>(Exact.or(()=>(item?.type), ()=>(item?.类型))), ()=>(""))), "余额强制修改")));
  }
  function isCashEntryLockedV4(item){
    const value = item?.system_locked;
    return Exact.or(()=>(Exact.or(()=>(Exact.seq(value, true)), ()=>(Exact.seq(value, 1)))), ()=>(["true","1","yes"].includes(String(Exact.or(()=>(value), ()=>(""))).toLowerCase())));
  }
  function cashSignedAmountV4(item){
    if (Exact.truth(isCashForceEntryV4(item))) return 0;
    const amount = Exact.decimal(Exact.currency(item?.amount ?? item?.金额)), type = String(Exact.or(()=>(Exact.or(()=>(item?.type), ()=>(item?.类型))), ()=>("")));
    if (Exact.truth(Exact.lt(amount, 0))) return amount;
    return (Exact.truth(["现金支出","其它现金支出","经营支出","固定成本","入库支出"].includes(type)) ? Exact.neg(Exact.math.abs(amount)) : Exact.math.abs(amount));
  }
  function cashEntryTimeV4(item){
    const parsed = Date.parse(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(item?.created_at), ()=>(item?.occurred_at))), ()=>(item?.updated_at))), ()=>("")));
    if (Exact.truth(Exact.finite(parsed))) return parsed;
    /* Old force rows have no timestamp. They still belong after that day's
       automatically generated income and expense rows. */
    return (Exact.truth(isCashForceEntryV4(item)) ? Number.MAX_SAFE_INTEGER : 0);
  }
  function chronologicalCashEntriesV4(entries){
    return ((Exact.truth(Array.isArray(entries)) ? entries : [])).map((item,index)=>({...item,_cashIndex:index})).sort(Exact.sortComparator((a,b)=>{
      const dateOrder=String(Exact.or(()=>(Exact.or(()=>(a.date), ()=>(a.日期))), ()=>(""))).localeCompare(String(Exact.or(()=>(Exact.or(()=>(b.date), ()=>(b.日期))), ()=>(""))));
      if(Exact.truth(dateOrder))return dateOrder;
      /* A correction means “this day's final balance”: every automatic or
         manual delta for the same business date is applied first. */
      const forceOrder=Exact.sub(Exact.toNumber(isCashForceEntryV4(a)), Exact.toNumber(isCashForceEntryV4(b)));
      if(Exact.truth(forceOrder))return forceOrder;
      if(Exact.truth(isCashForceEntryV4(a))){
        const timeOrder=Exact.sub(cashEntryTimeV4(a), cashEntryTimeV4(b));
        if(Exact.truth(timeOrder))return timeOrder;
        return String(Exact.or(()=>(a.id), ()=>(a._cashIndex))).localeCompare(String(Exact.or(()=>(b.id), ()=>(b._cashIndex))));
      }
      return Exact.sub(a._cashIndex, b._cashIndex);
    }));
  }
  function cashRowsWithBalanceV4(payload,response){
    const hasServerEntries=Array.isArray(response?.entries);
    /* The bundled API deliberately returns cash rows newest first for the
       table.  Reverse that authoritative sequence before deriving carry-over
       values; re-sorting equal-date deltas here would invert the server's
       running-balance order and could make a historical “上月结余” incorrect. */
    const source=(Exact.truth(hasServerEntries) ? [...response.entries].reverse() : payload.transactions);
    const opening=Exact.decimal(Exact.currency(response?.opening_balance ?? payload.opening_balance ?? payload.base_balance)), rows=(Exact.truth(hasServerEntries) ? source : chronologicalCashEntriesV4(source));
    let running=opening;
    return rows.map(item=>{
      const serverBalance=item.running_balance ?? item.balance_after;
      if(Exact.truth(entered(serverBalance)))running=Exact.decimal(Exact.currency(serverBalance));
      else if(Exact.truth(isCashForceEntryV4(item)))running=Exact.decimal(Exact.currency(item.target_balance ?? item.amount ?? item.金额));
      else (running = Exact.add(running, cashSignedAmountV4(item)));
      return {...item,date:normalizeDateKey(Exact.or(()=>(Exact.or(()=>(item.date), ()=>(item.日期))), ()=>(""))),running_balance:running,_serverRunningBalance:entered(serverBalance)};
    });
  }
  function cashLoanHistoryV4(payload){
    const today=isoDate(new Date()), loans=[];
    for(const item of (Exact.truth(Array.isArray(payload?.transactions)) ? payload.transactions : [])){
      const date=normalizeDateKey(Exact.or(()=>(Exact.or(()=>(item?.date), ()=>(item?.日期))), ()=>(""))), type=String(Exact.or(()=>(Exact.or(()=>(item?.type), ()=>(item?.类型))), ()=>("")));
      if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.sneq(type, "向股东借款")), ()=>(isCashForceEntryV4(item)))), ()=>(Exact.not(isCanonicalDate(date))))), ()=>(Exact.gt(date, today)))))continue;
      const amount=Exact.math.abs(Exact.decimal(Exact.currency(item?.amount ?? item?.金额)));
      if(Exact.truth(amount))loans.push({date,amount});
    }
    /* Very early builds stored one aggregate shareholder_loan value.  The API
       assigns it to opening_date (or today if no date exists), so historical
       browser filters must do the same instead of depending on API entries,
       which intentionally omit cash movements before opening_date. */
    const legacyAmount=Exact.decimal(Exact.currency(payload?.shareholder_loan));
    if(Exact.truth(Exact.gt(legacyAmount, 0))){
      let date=normalizeDateKey(Exact.or(()=>(Exact.or(()=>(payload?.opening_date), ()=>(payload?.as_of_date))), ()=>("")));
      if(Exact.truth(Exact.not(isCanonicalDate(date))))date=today;
      if(Exact.truth(Exact.lte(date, today)))loans.push({date,amount:legacyAmount});
    }
    return loans;
  }
  function responseMoneyV4(response,names,fallback){
    for(const name of names)if(Exact.truth(entered(response?.[name])))return Exact.decimal(Exact.currency(response[name]));
    return fallback;
  }
  let cashServerV4 = null;
  async function loadCashLedgerV4(){
    if (Exact.truth(Exact.or(()=>(Exact.not(["admin","editor"].includes(permanentRole()))), ()=>(Exact.not(state.dataset?.id))))) return;
    cashServerV4 = await api(`/datasets/${encodeURIComponent(state.dataset.id)}/cash-position`);
    renderCashLedgerV4();
  }
  function renderCashLedgerV4(){
    if (Exact.truth(Exact.not($("cashLedgerRows")))) return;
    const payload = cashPayloadV4(), response = Exact.or(()=>(cashServerV4), ()=>({})), opening = Exact.decimal(Exact.currency(response.opening_balance ?? payload.opening_balance ?? payload.base_balance));
    const correctionInput=$("cashOpeningBalanceV4"), correctionDate=$("cashOpeningDateV4");
    if(Exact.truth(Exact.sneq(document.activeElement, correctionInput)))correctionInput.value="";
    if(Exact.truth(Exact.and(()=>(Exact.sneq(document.activeElement, correctionDate)), ()=>(Exact.not(correctionDate.value)))))correctionDate.value=isoDate(new Date());
    const month = Exact.or(()=>($("cashMonthFilter").value), ()=>(isoDate(new Date()).slice(0,7))); $("cashMonthFilter").value = month;
    const withBalance=cashRowsWithBalanceV4(payload,response), balance=(Exact.truth(withBalance.length) ? Exact.decimal(Exact.currency(withBalance[Exact.sub(withBalance.length, 1)].running_balance)) : opening);
    const filtered = withBalance.filter(item=>Exact.or(()=>(Exact.not(month)), ()=>(String(item.date).startsWith(month)))).reverse();
    $("cashLedgerRows").innerHTML = (Exact.truth(filtered.length) ? filtered.map(item=>{
      const force=isCashForceEntryV4(item), signed=cashSignedAmountV4(item), locked=isCashEntryLockedV4(item);
      const action=(Exact.truth(item.id) ? (Exact.truth(locked) ? '<span class="cash-locked-entry">不可删除</span>' : `<button class="danger-link" data-cash-delete="${escapeHtml(item.id)}">删除</button>`) : "—");
      return `<tr${(Exact.truth(force) ? ' class="cash-force-entry"' : "")}><td>${escapeHtml(Exact.or(()=>(item.date), ()=>("")))}</td><td>${escapeHtml(Exact.or(()=>(item.type), ()=>("")))}</td><td>${escapeHtml(Exact.or(()=>(Exact.or(()=>(item.description), ()=>(item.type))), ()=>("")))}</td><td>${(Exact.truth(Exact.and(()=>(Exact.not(force)), ()=>(Exact.gt(signed, 0)))) ? money(signed) : "—")}</td><td>${(Exact.truth(Exact.and(()=>(Exact.not(force)), ()=>(Exact.lt(signed, 0)))) ? money(Exact.neg(signed)) : "—")}</td><td>${money(item.running_balance)}</td><td>${action}</td></tr>`;
    }).join("") : '<tr><td colspan="7">所选月份没有现金明细。</td></tr>');
    $("cashLedgerRows").querySelectorAll("[data-cash-delete]").forEach(button=>button.addEventListener("click",()=>safely(()=>deleteCashItemV4(button.dataset.cashDelete))));
    const forceRows=withBalance.filter(isCashForceEntryV4), serverUnderstandsForce=Exact.or(()=>(Exact.not(forceRows.length)), ()=>(forceRows.every(item=>item._serverRunningBalance)));
    const current=(Exact.truth(serverUnderstandsForce) ? responseMoneyV4(response,["current_balance"],balance) : balance), currentMonth=isoDate(new Date()).slice(0,7), selectedYear=month.slice(0,4), loanHistory=cashLoanHistoryV4(payload);
    const monthLoanFallback=loanHistory.filter(item=>item.date.startsWith(month)).reduce((sum,item)=>Exact.add(sum, item.amount),0);
    const yearLoanFallback=loanHistory.filter(item=>item.date.startsWith(`${selectedYear}-`)).reduce((sum,item)=>Exact.add(sum, item.amount),0);
    const totalLoanFallback=loanHistory.reduce((sum,item)=>Exact.add(sum, item.amount),0);
    const beforeMonth=withBalance.filter(item=>Exact.lt(String(item.date), `${month}-01`)), previousFallback=(Exact.truth(beforeMonth.length) ? Exact.decimal(Exact.currency(beforeMonth[Exact.sub(beforeMonth.length, 1)].running_balance)) : opening);
    const responseMonth=String(Exact.or(()=>(response.summary_month), ()=>(currentMonth))), responseYear=responseMonth.slice(0,4);
    const previous=(Exact.truth(Exact.seq(month, responseMonth)) ? responseMoneyV4(response,["previous_month_balance"],previousFallback) : previousFallback);
    const loanMonth=(Exact.truth(Exact.seq(month, responseMonth)) ? responseMoneyV4(response,["shareholder_loan_this_month","shareholder_loan_month"],monthLoanFallback) : monthLoanFallback);
    const loanYear=(Exact.truth(Exact.seq(selectedYear, responseYear)) ? responseMoneyV4(response,["shareholder_loan_this_year","shareholder_loan_year"],yearLoanFallback) : yearLoanFallback);
    const loanTotal=responseMoneyV4(response,["shareholder_loan_total","shareholder_loan_cumulative"],totalLoanFallback);
    $("cashCurrentBalance").textContent = money(current); $("cashBalanceSummary").textContent = money(current);
    $("cashPreviousMonthBalance").textContent=money(previous);$("cashLoanMonth").textContent=money(loanMonth);$("cashLoanYear").textContent=money(loanYear);$("cashLoanTotal").textContent=money(loanTotal);
  }
  async function saveCashPayloadV4(payload, message){
    await saveRecord("global","cash_position",payload,"cashResultV4");
    cashServerV4 = null; await loadCashLedgerV4(); $("cashResultV4").textContent = message;
  }
  async function saveCashBaselineV4(){
    const input=$("cashOpeningBalanceV4"), raw=input.value.trim(), date=$("cashOpeningDateV4").value;
    if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.not(entered(raw))), ()=>(Exact.lt(Exact.decimal(Exact.currency(raw)), 0)))), ()=>(Exact.not(date)))))throw new Error("修正后的余额不能为负数，并且必须选择修正日期。");
    const target=Exact.decimal(Exact.currency(raw)), payload=cashPayloadV4();
    payload.transactions.push({id:uuid(),date,type:"余额强制修改",amount:target,description:"余额强制修改",mode:"force",system_locked:true,created_at:new Date().toISOString()});
    await saveCashPayloadV4(payload,"余额已强制修正，原有明细均已保留。");input.value="";
  }
  function openCashItemV4(){
    const overlay=document.createElement("div"); overlay.className="pro-modal-backdrop";
    overlay.innerHTML=`<section class="pro-modal cash-item-modal"><header><h2>现金余额表 · 加一项</h2><button type="button" data-close>关闭</button></header><div class="modal-body form-grid"><label>日期<input data-cash-date type="date" value="${isoDate(new Date())}"></label><label>类型<select data-cash-type><option>向股东借款</option><option>其它现金收入</option><option>其它现金支出</option><option>余额强制修改</option></select></label><label>金额／修正后余额<input data-cash-amount type="number" min="0" step="0.01"></label><label>说明<input data-cash-description placeholder="例如：张三借款"></label></div><footer><button class="primary" type="button" data-save>保存这一项</button></footer></section>`;
    document.body.appendChild(overlay); const close=()=>overlay.remove(); overlay.querySelector("[data-close]").onclick=close;
    overlay.querySelector("[data-save]").onclick=()=>safely(async()=>{const payload=cashPayloadV4(),amountInput=overlay.querySelector("[data-cash-amount]"),raw=amountInput.value.trim(),amount=Exact.decimal(Exact.currency(raw)),date=overlay.querySelector("[data-cash-date]").value,type=overlay.querySelector("[data-cash-type]").value,force=Exact.seq(type, "余额强制修改");if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.not(entered(raw))), ()=>(Exact.lt(amount, 0)))), ()=>(Exact.and(()=>(Exact.not(force)), ()=>(Exact.seq(amount, 0)))))), ()=>(Exact.not(date)))))throw new Error((Exact.truth(force) ? "请选择日期并填写不小于 0 的修正后余额。" : "请选择日期并填写大于 0 的金额。"));payload.transactions.push({id:uuid(),date,type,amount,description:Exact.or(()=>(overlay.querySelector("[data-cash-description]").value.trim()), ()=>(type)),mode:(Exact.truth(force) ? "force" : "delta"),system_locked:false,created_at:new Date().toISOString()});await saveCashPayloadV4(payload,`已增加：${type} ${money(amount)}`);close();});
  }
  async function deleteCashItemV4(id){
    const payload=cashPayloadV4(),target=payload.transactions.find(item=>Exact.seq(String(item.id), String(id)));
    if(Exact.truth(Exact.not(target)))return;
    if(Exact.truth(isCashEntryLockedV4(target)))throw new Error("通过“把余额强行修正成：”保存的记录不能删除。");
    if(Exact.truth(Exact.not(confirm("确定删除这条手工现金项目吗？"))))return;
    payload.transactions=payload.transactions.filter(item=>Exact.sneq(String(item.id), String(id)));await saveCashPayloadV4(payload,"现金项目已删除。");
  }

  loadChangeLogs = async function(){
    const target=$("changeLogRows");if(Exact.truth(Exact.or(()=>(Exact.not(target)), ()=>(Exact.not(["admin","editor"].includes(permanentRole()))))))return;
    const params=new URLSearchParams({dataset_id:Exact.or(()=>(state.dataset?.id), ()=>("")),hours:"8784",limit:"5000"}),mode=Exact.or(()=>($("auditFilterMode")?.value), ()=>("all"));
    if(Exact.truth(Exact.and(()=>(Exact.seq(mode, "day")), ()=>($("auditFilterDay").value)))){params.set("start_date",$("auditFilterDay").value);params.set("end_date",$("auditFilterDay").value);}
    if(Exact.truth(Exact.and(()=>(Exact.seq(mode, "month")), ()=>($("auditFilterMonth").value)))){const [y,m]=$("auditFilterMonth").value.split("-").map(Number);params.set("start_date",`${y}-${String(m).padStart(2,"0")}-01`);params.set("end_date",`${y}-${String(m).padStart(2,"0")}-${String(daysInMonth(y,m)).padStart(2,"0")}`);}
    const rows=await api(`/audit?${params}`),items=(Exact.truth(Array.isArray(rows)) ? rows : Exact.or(()=>(rows?.items), ()=>([])));
    target.innerHTML=(Exact.truth(items.length) ? items.map(item=>`<tr><td>${escapeHtml(new Date(Exact.or(()=>(item.created_at), ()=>(item.occurred_at))).toLocaleString("zh-CN"))}</td><td>${escapeHtml(Exact.or(()=>(Exact.or(()=>(item.actor_label), ()=>(item.actor_username))), ()=>("—")))}</td><td>${escapeHtml(auditActionLabel(item.action))}</td><td>${escapeHtml(Exact.or(()=>(Exact.or(()=>(state.dataset?.name), ()=>(item.dataset_id))), ()=>("—")))}</td><td>${escapeHtml(`${Exact.or(()=>(item.record_type), ()=>(""))} ${Exact.or(()=>(item.record_key), ()=>(""))}`.trim())}</td><td class="audit-change-summary">${(Exact.truth(Exact.seq(item.source, "inventory_name_correction")) ? `<small>${escapeHtml(auditSourceLabel(item.source))}</small>` : "")}${escapeHtml(Exact.or(()=>(item.change_summary), ()=>("账本内容已更新")))}</td><td>${(Exact.truth(Exact.seq(permanentRole(), "admin")) ? `<button class="danger-link" data-delete-audit="${escapeHtml(Exact.or(()=>(item.id), ()=>("")))}">删除</button>` : "—")}</td></tr>`).join("") : '<tr><td colspan="7">所选日期范围没有修改记录。</td></tr>');
    target.querySelectorAll("[data-delete-audit]").forEach(button=>button.onclick=()=>safely(()=>deleteAuditLog(button.dataset.deleteAudit)));
  };

  let grantUsersV4=[];
  async function loadTemporaryPermissionsV4(){
    if(Exact.truth(Exact.sneq(permanentRole(), "admin")))return;
    const [users,grants]=await Promise.all([api("/users"),api("/temporary-permissions")]);grantUsersV4=users;
    $("grantUser").innerHTML=users.filter(u=>Exact.and(()=>(Exact.sneq(u.role, "admin")), ()=>(Exact.not(u.is_test)))).map(u=>`<option value="${escapeHtml(u.id)}">${escapeHtml(Exact.or(()=>(u.display_name), ()=>(u.username)))} (${escapeHtml(u.username)})</option>`).join("");
    $("grantDataset").innerHTML=state.datasets.filter(d=>Exact.not(d.is_test)).map(d=>`<option value="${escapeHtml(d.id)}">${escapeHtml(Exact.or(()=>(d.name), ()=>(d.id)))}</option>`).join("");
    const userNames=Object.fromEntries(users.map(u=>[u.id,Exact.or(()=>(u.display_name), ()=>(u.username))])),datasetNames=Object.fromEntries(state.datasets.map(d=>[d.id,Exact.or(()=>(d.name), ()=>(d.id))]));
    $("grantRows").innerHTML=(Exact.truth(grants.length) ? grants.map(g=>`<tr><td>${escapeHtml(Exact.or(()=>(userNames[g.user_id]), ()=>(g.user_id)))}</td><td>${escapeHtml(Exact.or(()=>(datasetNames[g.dataset_id]), ()=>(g.dataset_id)))}</td><td>${(Exact.truth(Exact.seq(g.permission_role, "editor")) ? "修改权限" : "录入权限")}</td><td>${escapeHtml(g.business_start_date)} 至 ${escapeHtml(g.business_end_date)}</td><td>${escapeHtml(new Date(g.starts_at).toLocaleString("zh-CN"))} 至 ${escapeHtml(new Date(g.ends_at).toLocaleString("zh-CN"))}</td><td><button class="danger-link" data-delete-grant="${escapeHtml(g.id)}">删除</button></td></tr>`).join("") : '<tr><td colspan="6">暂无临时权限。</td></tr>');
    $("grantRows").querySelectorAll("[data-delete-grant]").forEach(button=>button.onclick=()=>safely(async()=>{await api(`/temporary-permissions/${encodeURIComponent(button.dataset.deleteGrant)}`,{method:"DELETE"});await loadTemporaryPermissionsV4();}));
  }
  async function createTemporaryPermissionV4(){
    const body={user_id:$("grantUser").value,dataset_id:$("grantDataset").value,permission_role:$("grantRole").value,business_start_date:$("grantBusinessStart").value,business_end_date:$("grantBusinessEnd").value,starts_at:new Date($("grantStartsAt").value).toISOString(),ends_at:new Date($("grantEndsAt").value).toISOString()};
    if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(Exact.not(body.user_id)), ()=>(Exact.not(body.dataset_id)))), ()=>(Exact.not(body.business_start_date)))), ()=>(Exact.not(body.business_end_date)))))throw new Error("请完整选择账号、账本和日期。");
    await api("/temporary-permissions",{method:"POST",body:JSON.stringify(body)});$("grantResult").textContent="临时权限已开放。";await loadTemporaryPermissionsV4();
  }

  function localDatetime(date){const offset=Exact.mul(date.getTimezoneOffset(), 60000);return new Date(Exact.sub(date, offset)).toISOString().slice(0,16);}
  const now=new Date(),later=new Date(Exact.add(now.getTime(), Exact.mul(2, 3600000))),today=isoDate(now);
  for(const id of ["grantBusinessStart","grantBusinessEnd"])if(Exact.truth($(id)))$(id).value=today;
  if(Exact.truth($("grantStartsAt")))$("grantStartsAt").value=localDatetime(now);if(Exact.truth($("grantEndsAt")))$("grantEndsAt").value=localDatetime(later);
  $("cashMonthFilter")?.addEventListener("change",renderCashLedgerV4);$("saveCashBaselineV4")?.addEventListener("click",()=>safely(saveCashBaselineV4));$("addCashItemV4")?.addEventListener("click",openCashItemV4);
  $("auditFilterMode")?.addEventListener("change",()=>{const mode=$("auditFilterMode").value;$("auditFilterMonth").classList.toggle("hidden",Exact.sneq(mode, "month"));$("auditFilterDay").classList.toggle("hidden",Exact.sneq(mode, "day"));});
  $("auditFilterButton")?.addEventListener("click",()=>safely(loadChangeLogs));$("createGrantButton")?.addEventListener("click",()=>safely(createTemporaryPermissionV4));
  $("ledgerDate")?.addEventListener("change",applyScheduledUi);$("foodDate")?.addEventListener("change",applyScheduledUi);$("spiceDate")?.addEventListener("change",applyScheduledUi);$("dishDate")?.addEventListener("change",applyScheduledUi);
  $("cashPositionCard")?.remove();
  if(Exact.truth(state.token)){$("cashNavButton")?.classList.toggle("hidden",Exact.not(["admin","editor"].includes(permanentRole())));$("grantNavButton")?.classList.toggle("hidden",Exact.sneq(permanentRole(), "admin"));applyScheduledUi();}
})();
