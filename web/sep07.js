/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

/* Sep11V1: mobile/tablet presentation mode and immediate audit-row deletion. */
(() => {
  const MOBILE_OR_TABLET = "(max-width: 1180px)";
  const permissionCanEdit = canEdit;
  const isCompactViewport = () => (Exact.truth(window.matchMedia) ? window.matchMedia(MOBILE_OR_TABLET).matches : Exact.lte(window.innerWidth, 1180));

  state.viewOnlyMode = isCompactViewport();
  document.body.classList.remove("large-text");
  try { localStorage.removeItem("restaurant_large_text"); } catch (_) {}

  const hasWritePermission = () => Boolean(permissionCanEdit());
  const isPresentationReadOnly = () => Exact.or(()=>(Boolean(state.viewOnlyMode)), ()=>(Exact.not(hasWritePermission())));
  canEdit = function(){ return Exact.and(()=>(hasWritePermission()), ()=>(Exact.not(state.viewOnlyMode))); };

  /* Read-only is a presentation mode, not a crippled dashboard.  Date and
     analytics filters are navigation controls: they must remain usable so a
     phone/tablet user can still look at a different day without entering any
     business data. */
  const presentationFilterSelector = [
    ".filter-bar", ".analytics-controls", ".stats-command-bar",
    ".stats-subfilter", ".metric-picker", ".audit-filters",
    ".chart-heading-actions"
  ].join(",");
  const dateNavigationSelectIds = new Set(["selectedMonth", "selectedYear", "statsYear", "auditFilterMode"]);
  function keepAsNavigationControl(control){
    if(Exact.truth(control.closest("#pageOverview"))) return true;
    if(Exact.truth(control.closest(presentationFilterSelector))) return true;
    if(Exact.truth(Exact.and(()=>(control instanceof HTMLInputElement), ()=>(["date", "month"].includes(control.type))))) return true;
    return Exact.and(()=>(control instanceof HTMLSelectElement), ()=>(dateNavigationSelectIds.has(control.id)));
  }

  function clearReadOnlyProjection(control){
    control.classList.remove("readonly-source");
    const output=control.__sep07ReadOnlyOutput;
    if(Exact.truth(output?.isConnected)) output.remove();
    control.__sep07ReadOnlyOutput=null;
  }

  function readOnlyDisplayValue(control){
    if(Exact.truth(Exact.and(()=>(control instanceof HTMLInputElement), ()=>(["checkbox","radio"].includes(control.type))))) return (Exact.truth(control.checked) ? "" : "—");
    if(Exact.truth(control instanceof HTMLSelectElement)){
      const labels=[...control.options].filter(option=>option.selected).map(option=>option.textContent.trim()).filter(Exact.truth);
      return Exact.or(()=>(labels.join("、")), ()=>("—"));
    }
    if(Exact.truth(Exact.and(()=>(control instanceof HTMLInputElement), ()=>(Exact.seq(control.type, "file"))))) return Exact.or(()=>(control.files?.[0]?.name), ()=>("—"));
    if(Exact.truth(Exact.and(()=>(control instanceof HTMLInputElement), ()=>(Exact.seq(control.type, "password"))))) return (Exact.truth(control.value) ? "••••••" : "—");
    const value=String(control.value ?? "").trim();
    return Exact.or(()=>(value), ()=>("—"));
  }

  function markPresentationControls(){
    document.querySelectorAll(".app-page input:not([type=hidden]), .app-page select, .app-page textarea").forEach(control=>{
      if(Exact.truth(keepAsNavigationControl(control))){
        clearReadOnlyProjection(control);
        return;
      }
      control.classList.add("readonly-source");
      let output=control.__sep07ReadOnlyOutput;
      if(Exact.truth(Exact.or(()=>(Exact.not(output)), ()=>(Exact.not(output.isConnected))))){
        output=document.createElement("span");
        output.className="readonly-value";
        output.setAttribute("aria-live","off");
        control.insertAdjacentElement("afterend",output);
        control.__sep07ReadOnlyOutput=output;
      }
      const value=readOnlyDisplayValue(control);
      if(Exact.truth(Exact.sneq(output.textContent, value)))output.textContent=value;
    });

    document.querySelectorAll(".app-page button, .app-page label.upload-button").forEach(control=>{
      if(Exact.truth(control.classList.contains("edit-action"))) return;
      const signature=[control.id,control.className,...Object.entries(Exact.or(()=>(control.dataset), ()=>({}))).flat()].join(" ");
      if(Exact.truth(/save|delete|remove|add|create|upload|merge|copy|overwrite|rename|disable|move|pick|manage|sync|undo|clear|grant|cash-delete|inventory-(?:modify|overwrite|submit)/i.test(signature))) control.classList.add("view-only-edit-action");
    });
  }

  function updateModeButton(){
    const button=$("viewModeButton");if(Exact.truth(Exact.not(button)))return;
    const english=Exact.seq(state.language, "en"), writable=hasWritePermission(), readOnly=isPresentationReadOnly();
    button.disabled=Exact.not(writable);
    button.setAttribute("aria-pressed",String(readOnly));
    button.title=(Exact.truth(Exact.not(writable)) ? (Exact.truth(english) ? "This account does not have permission to edit." : "当前账号没有修改权限。") : (Exact.truth(readOnly) ? (Exact.truth(english) ? "Switch to editable mode" : "切换至可修改模式") : (Exact.truth(english) ? "Switch to read-only mode" : "切换至只读模式")));
    const label=(Exact.truth(Exact.not(writable)) ? (Exact.truth(english) ? "Read-only mode" : "只读模式") : (Exact.truth(readOnly) ? (Exact.truth(english) ? "Editable mode" : "可修改模式") : (Exact.truth(english) ? "Read-only mode" : "只读模式")));
    if(Exact.truth(Exact.sneq(button.textContent, label)))button.textContent=label;
  }

  function closeEditingOverlays(){
    if(Exact.truth(Exact.and(()=>($("proModalHost")?.childNodes.length), ()=>(Exact.seq(typeof closeProModal, "function"))))) closeProModal();
    document.querySelectorAll(".cash-item-modal, .inventory-adjust-modal, .selector-dialog").forEach(node=>{
      node.closest(".pro-modal-backdrop, .selector-backdrop")?.remove();
    });
  }

  function applyPresentationMode(){
    const readOnly=isPresentationReadOnly();
    document.body.classList.toggle("view-read-only",readOnly);
    document.body.classList.toggle("read-only",readOnly);
    if(Exact.truth(readOnly)) closeEditingOverlays();
    markPresentationControls();
    updateModeButton();
    const label=$("ledgerPermission"),english=Exact.seq(state.language, "en"),role=currentRole();
    const text=(Exact.truth(readOnly) ? (Exact.truth(english) ? "Read only" : "只读模式") : (Exact.truth(Exact.seq(role, "entry")) ? (Exact.truth(english) ? "Entry access" : "可录入") : (Exact.truth(english) ? "Editable" : "可修改")));
    if(Exact.truth(Exact.and(()=>(label), ()=>(Exact.sneq(label.textContent, text)))))label.textContent=text;
  }

  let presentationQueued=false;
  function queuePresentationMode(){
    if(Exact.truth(presentationQueued))return;
    presentationQueued=true;
    queueMicrotask(()=>{presentationQueued=false;applyPresentationMode();});
  }

  const appView=$("appView");
  if(Exact.truth(appView)){
    new MutationObserver(queuePresentationMode).observe(appView,{childList:true,subtree:true});
    appView.addEventListener("input",queuePresentationMode,true);
    appView.addEventListener("change",queuePresentationMode,true);
  }

  $("viewModeButton")?.addEventListener("click",()=>{
    if(Exact.truth(Exact.not(hasWritePermission())))return;
    state.viewOnlyMode=Exact.not(state.viewOnlyMode);
    if(Exact.truth(Exact.seq(typeof renderCustomerTiming, "function")))renderCustomerTiming();
    applyPresentationMode();
  });

  const baseEnterApp=enterApp;
  enterApp=async function(...args){
    // A new phone/tablet visit always starts in a safe, view-only state.
    state.viewOnlyMode=isCompactViewport();
    const result=await baseEnterApp.apply(this,args);
    applyPresentationMode();
    return result;
  };
  const baseShowPage=showPage;
  showPage=function(...args){const result=baseShowPage.apply(this,args);queuePresentationMode();return result;};
  const baseLoadCloudData=loadCloudData;
  loadCloudData=async function(...args){const result=await baseLoadCloudData.apply(this,args);queuePresentationMode();return result;};
  const baseApplyLanguage=applyLanguage;
  applyLanguage=function(...args){const result=baseApplyLanguage.apply(this,args);queuePresentationMode();return result;};

  const pendingAuditDeletes=new Set();
  deleteAuditLog=async function(auditId){
    if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.sneq(currentRole(), "admin")), ()=>(Exact.not(auditId)))), ()=>(pendingAuditDeletes.has(String(auditId))))))return;
    if(Exact.truth(Exact.not(confirm((Exact.truth(Exact.seq(state.language, "en")) ? "Delete this change record permanently?" : "确定永久删除这条修改记录吗？")))))return;

    const target=$("changeLogRows");
    const row=[...(Exact.or(()=>(target?.querySelectorAll("tr")), ()=>([])))].find(item=>Exact.seq(item.querySelector("[data-delete-audit]")?.dataset.deleteAudit, String(auditId)));
    const button=row?.querySelector("[data-delete-audit]");
    const marker=(Exact.truth(row) ? document.createComment("pending audit deletion") : null);
    pendingAuditDeletes.add(String(auditId));
    if(Exact.truth(row)){row.classList.add("audit-deleting");row.setAttribute("aria-busy","true");}
    if(Exact.truth(button)){button.disabled=true;button.textContent=(Exact.truth(Exact.seq(state.language, "en")) ? "Deleting…" : "删除中…");}
    if(Exact.truth(Exact.and(()=>(row), ()=>(marker))))row.replaceWith(marker);

    try {
      await api(`/audit/${encodeURIComponent(auditId)}`,{method:"DELETE"});
    } catch(error) {
      if(Exact.truth(marker?.isConnected))marker.replaceWith(row);
      if(Exact.truth(row)){row.classList.remove("audit-deleting");row.removeAttribute("aria-busy");}
      if(Exact.truth(button)){button.disabled=false;button.textContent=(Exact.truth(Exact.seq(state.language, "en")) ? "Delete" : "删除");}
      try { await loadChangeLogs(); } catch (_) {}
      throw error;
    } finally {
      pendingAuditDeletes.delete(String(auditId));
    }
  };

  applyPresentationMode();
})();
