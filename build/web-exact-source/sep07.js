"use strict";

/* Sep11V1: mobile/tablet presentation mode and immediate audit-row deletion. */
(() => {
  const MOBILE_OR_TABLET = "(max-width: 1180px)";
  const permissionCanEdit = canEdit;
  const isCompactViewport = () => window.matchMedia ? window.matchMedia(MOBILE_OR_TABLET).matches : window.innerWidth <= 1180;

  state.viewOnlyMode = isCompactViewport();
  document.body.classList.remove("large-text");
  try { localStorage.removeItem("restaurant_large_text"); } catch (_) {}

  const hasWritePermission = () => Boolean(permissionCanEdit());
  const isPresentationReadOnly = () => Boolean(state.viewOnlyMode) || !hasWritePermission();
  canEdit = function(){ return hasWritePermission() && !state.viewOnlyMode; };

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
    if(control.closest("#pageOverview")) return true;
    if(control.closest(presentationFilterSelector)) return true;
    if(control instanceof HTMLInputElement && ["date", "month"].includes(control.type)) return true;
    return control instanceof HTMLSelectElement && dateNavigationSelectIds.has(control.id);
  }

  function clearReadOnlyProjection(control){
    control.classList.remove("readonly-source");
    const output=control.__sep07ReadOnlyOutput;
    if(output?.isConnected) output.remove();
    control.__sep07ReadOnlyOutput=null;
  }

  function readOnlyDisplayValue(control){
    if(control instanceof HTMLInputElement && ["checkbox","radio"].includes(control.type)) return control.checked ? "" : "—";
    if(control instanceof HTMLSelectElement){
      const labels=[...control.options].filter(option=>option.selected).map(option=>option.textContent.trim()).filter(Boolean);
      return labels.join("、") || "—";
    }
    if(control instanceof HTMLInputElement && control.type === "file") return control.files?.[0]?.name || "—";
    if(control instanceof HTMLInputElement && control.type === "password") return control.value ? "••••••" : "—";
    const value=String(control.value ?? "").trim();
    return value || "—";
  }

  function markPresentationControls(){
    document.querySelectorAll(".app-page input:not([type=hidden]), .app-page select, .app-page textarea").forEach(control=>{
      if(keepAsNavigationControl(control)){
        clearReadOnlyProjection(control);
        return;
      }
      control.classList.add("readonly-source");
      let output=control.__sep07ReadOnlyOutput;
      if(!output || !output.isConnected){
        output=document.createElement("span");
        output.className="readonly-value";
        output.setAttribute("aria-live","off");
        control.insertAdjacentElement("afterend",output);
        control.__sep07ReadOnlyOutput=output;
      }
      const value=readOnlyDisplayValue(control);
      if(output.textContent!==value)output.textContent=value;
    });

    document.querySelectorAll(".app-page button, .app-page label.upload-button").forEach(control=>{
      if(control.classList.contains("edit-action")) return;
      const signature=[control.id,control.className,...Object.entries(control.dataset || {}).flat()].join(" ");
      if(/save|delete|remove|add|create|upload|merge|copy|overwrite|rename|disable|move|pick|manage|sync|undo|clear|grant|cash-delete|inventory-(?:modify|overwrite|submit)/i.test(signature)) control.classList.add("view-only-edit-action");
    });
  }

  function updateModeButton(){
    const button=$("viewModeButton");if(!button)return;
    const english=state.language === "en", writable=hasWritePermission(), readOnly=isPresentationReadOnly();
    button.disabled=!writable;
    button.setAttribute("aria-pressed",String(readOnly));
    button.title=!writable
      ? (english ? "This account does not have permission to edit." : "当前账号没有修改权限。")
      : (readOnly ? (english ? "Switch to editable mode" : "切换至可修改模式") : (english ? "Switch to read-only mode" : "切换至只读模式"));
    const label=!writable
      ? (english ? "Read-only mode" : "只读模式")
      : (readOnly ? (english ? "Editable mode" : "可修改模式") : (english ? "Read-only mode" : "只读模式"));
    if(button.textContent!==label)button.textContent=label;
  }

  function closeEditingOverlays(){
    if($("proModalHost")?.childNodes.length&&typeof closeProModal === "function") closeProModal();
    document.querySelectorAll(".cash-item-modal, .inventory-adjust-modal, .selector-dialog").forEach(node=>{
      node.closest(".pro-modal-backdrop, .selector-backdrop")?.remove();
    });
  }

  function applyPresentationMode(){
    const readOnly=isPresentationReadOnly();
    document.body.classList.toggle("view-read-only",readOnly);
    document.body.classList.toggle("read-only",readOnly);
    if(readOnly) closeEditingOverlays();
    markPresentationControls();
    updateModeButton();
    const label=$("ledgerPermission"),english=state.language==="en",role=currentRole();
    const text=readOnly?(english?"Read only":"只读模式"):(role==="entry"?(english?"Entry access":"可录入"):(english?"Editable":"可修改"));
    if(label&&label.textContent!==text)label.textContent=text;
  }

  let presentationQueued=false;
  function queuePresentationMode(){
    if(presentationQueued)return;
    presentationQueued=true;
    queueMicrotask(()=>{presentationQueued=false;applyPresentationMode();});
  }

  const appView=$("appView");
  if(appView){
    new MutationObserver(queuePresentationMode).observe(appView,{childList:true,subtree:true});
    appView.addEventListener("input",queuePresentationMode,true);
    appView.addEventListener("change",queuePresentationMode,true);
  }

  $("viewModeButton")?.addEventListener("click",()=>{
    if(!hasWritePermission())return;
    state.viewOnlyMode=!state.viewOnlyMode;
    if(typeof renderCustomerTiming==="function")renderCustomerTiming();
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
    if(currentRole()!=="admin"||!auditId||pendingAuditDeletes.has(String(auditId)))return;
    if(!confirm(state.language==="en"?"Delete this change record permanently?":"确定永久删除这条修改记录吗？"))return;

    const target=$("changeLogRows");
    const row=[...(target?.querySelectorAll("tr") || [])].find(item=>item.querySelector("[data-delete-audit]")?.dataset.deleteAudit===String(auditId));
    const button=row?.querySelector("[data-delete-audit]");
    const marker=row ? document.createComment("pending audit deletion") : null;
    pendingAuditDeletes.add(String(auditId));
    if(row){row.classList.add("audit-deleting");row.setAttribute("aria-busy","true");}
    if(button){button.disabled=true;button.textContent=state.language==="en"?"Deleting…":"删除中…";}
    if(row&&marker)row.replaceWith(marker);

    try {
      await api(`/audit/${encodeURIComponent(auditId)}`,{method:"DELETE"});
    } catch(error) {
      if(marker?.isConnected)marker.replaceWith(row);
      if(row){row.classList.remove("audit-deleting");row.removeAttribute("aria-busy");}
      if(button){button.disabled=false;button.textContent=state.language==="en"?"Delete":"删除";}
      try { await loadChangeLogs(); } catch (_) {}
      throw error;
    } finally {
      pendingAuditDeletes.delete(String(auditId));
    }
  };

  applyPresentationMode();
})();
