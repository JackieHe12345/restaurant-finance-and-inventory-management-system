'use strict';
/* Native month values remain canonical YYYY-MM. English presentation is ISO,
   independent of the operating system's month-name formatting. Picker popup
   chrome remains browser-owned; no event, validation or saved value is replaced. */
(() => {
 const controls=new WeakMap();
 function sync(input){
  let item=controls.get(input);
  if(!item){
   const shell=document.createElement('span'),label=document.createElement('span');
   shell.className='iso-month-shell';label.className='iso-month-label';label.setAttribute('aria-hidden','true');
   input.before(shell);shell.append(input,label);item={shell,label};controls.set(input,item);
   input.addEventListener('input',()=>sync(input));input.addEventListener('change',()=>sync(input));
  }
  const english=typeof state!=='undefined'&&state.language==='en';
  item.shell.classList.toggle('iso-month-english',english);item.label.hidden=!english;
  const text=input.value||'YYYY-MM';if(item.label.textContent!==text)item.label.textContent=text;
 }
 globalThis.syncSystemMonthControls=function(){document.querySelectorAll('input[type="month"]').forEach(sync);};
})();
