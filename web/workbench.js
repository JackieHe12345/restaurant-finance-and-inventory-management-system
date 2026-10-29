"use strict";
/* Oct30LingChen: navigation shell shared by every financial surface. */
(() => {
  const toggle=$('sidebarToggle'),backdrop=$('sidebarBackdrop'),sidebar=$('appSidebar');
  function syncSidebar(){if(sidebar)sidebar.inert=window.innerWidth<=1100&&!document.body.classList.contains('sidebar-open');}
  function closeMenu(){document.body.classList.remove('sidebar-open');toggle?.setAttribute('aria-expanded','false');if(backdrop)backdrop.hidden=true;syncSidebar();}
  function updateContext(){
    const active=document.querySelector(`.nav-tabs [data-page="${state.activePage||'overview'}"]`);
    if($('workspaceBreadcrumb'))$('workspaceBreadcrumb').textContent=active?.textContent.trim()||'';
    document.querySelectorAll('.nav-tabs [data-page]').forEach(button=>{if(button===active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
    if($('accountLabel'))$('accountLabel').title=({admin:'管理员',editor:'修改权限',entry:'录入权限',viewer:'只读权限'})[currentRole()]||'';
  }
  toggle?.addEventListener('click',()=>{const open=!document.body.classList.contains('sidebar-open');document.body.classList.toggle('sidebar-open',open);toggle.setAttribute('aria-expanded',String(open));backdrop.hidden=!open;syncSidebar();if(open)sidebar.querySelector('[aria-current="page"]')?.focus();});
  backdrop?.addEventListener('click',closeMenu);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('sidebar-open')){closeMenu();toggle?.focus();}});
  window.addEventListener('resize',()=>{if(window.innerWidth>1100)closeMenu();syncSidebar();});
  $('logoutButton')?.addEventListener('click',closeMenu);
  const priorShow=showPage;showPage=function(...args){const result=priorShow.apply(this,args);updateContext();closeMenu();if(state.activePage===args[0])window.scrollTo({top:0,left:0,behavior:"instant"});return result;};
  const priorLanguage=applyLanguage;applyLanguage=function(...args){const result=priorLanguage.apply(this,args);updateContext();return result;};
  const priorEnter=enterApp;enterApp=async function(...args){const result=await priorEnter.apply(this,args);updateContext();return result;};
  function labelDocumentCells(){
    document.querySelectorAll('.iw-form-table').forEach(table=>{
      const labels=[...table.querySelectorAll('thead th')].map(th=>th.textContent.trim());
      table.querySelectorAll('tbody tr').forEach(row=>[...row.children].forEach((cell,index)=>{const text=labels[index]||'操作';if(cell.dataset.label!==text)cell.dataset.label=text;}));
    });
  }
  new MutationObserver(labelDocumentCells).observe(document.body,{childList:true,subtree:true});
  document.addEventListener('keydown',event=>{
    if(event.key!=='Tab'||!document.body.classList.contains('sidebar-open'))return;
    const nodes=[...sidebar.querySelectorAll('button:not([hidden]):not(.hidden),a[href]')].filter(el=>el.getClientRects().length);
    if(!nodes.length)return;
    if(event.shiftKey&&document.activeElement===nodes[0]){event.preventDefault();nodes[nodes.length-1].focus();}
    else if(!event.shiftKey&&document.activeElement===nodes[nodes.length-1]){event.preventDefault();nodes[0].focus();}
  });
  updateContext();syncSidebar();labelDocumentCells();
})();
