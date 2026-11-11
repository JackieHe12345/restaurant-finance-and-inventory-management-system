"use strict";

/* Sep05V1: cache-safe inventory consumption. */
(() => {
  function stockCategoryMaps(){
    const exact=new Map(),byName=new Map();
    for(const entry of inventoryEntries()){
      const name=String(entry.name||"").trim(),unit=String(entry.unit||"").trim(),category=entry.category==="佐料"?"佐料":"食材";
      if(!name)continue;
      const exactKey=`${name}\u0000${unit}`,names=exact.get(exactKey)||new Set(),named=byName.get(name)||new Set();
      names.add(category);named.add(category);exact.set(exactKey,names);byName.set(name,named);
    }
    return {exact,byName};
  }

  /* Every saved dish recipe is an outbound stock movement.  Use its exact
     name/unit to resolve ingredient versus seasoning; an ambiguous old recipe
     remains an ingredient rather than deducting two unrelated stock rows. */
  inventoryConsumption=function(){
    const used=new Map(),categories=stockCategoryMaps();
    for(const day of state.days){
      const date=String(day.日期||"");const rows=dishData(date).rows||[];
      for(const dish of rows)for(const item of parseDetailItems(dish.食材明细)){
        const name=String(item.name||"").trim(),quantity=num(item.quantity),unit=String(item.unit||"").trim();
        if(!name||!quantity)continue;
        const matches=categories.exact.get(`${name}\u0000${unit}`)||categories.byName.get(name);
        const category=matches?.size===1&&matches.has("佐料")?"佐料":"食材";
        const key=inventoryKey({category,name,unit}),row=used.get(key)||{quantity:0,lastDate:"",byDate:[]};
        row.quantity+=quantity;row.lastDate=date>row.lastDate?date:row.lastDate;row.byDate.push({date,quantity});used.set(key,row);
      }
    }
    return used;
  };

  inventoryBalances=function(){
    const used=inventoryConsumption(),adjustments=inventoryAdjustmentRows(),overrides=inventoryOverrideRows(),latestOverrides=new Map(),entries=inventoryEntries(),balances=new Map();
    for(const item of overrides){const key=inventoryKey(item),previous=latestOverrides.get(key);if(!previous||item.date>=previous.date)latestOverrides.set(key,item);}
    const blank=item=>({category:item.category,name:item.name,unit:item.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null});
    for(const entry of entries){const key=inventoryKey(entry),row=balances.get(key)||blank(entry);row.received+=entry.quantity;row.receivedValue+=entry.total||entry.quantity*entry.unitPrice;row.lastDate=entry.date>row.lastDate?entry.date:row.lastDate;balances.set(key,row);}
    for(const [key,value] of used){const row=balances.get(key);if(row)row.used=value.quantity;}
    for(const item of adjustments){const key=inventoryKey(item),row=balances.get(key)||blank(item);if(item.quantity>0){row.manualUsed+=item.quantity;if(item.kind==="loss")row.loss+=item.quantity;else row.normalUsed+=item.quantity;}balances.set(key,row);}
    for(const [key,item] of latestOverrides){const row=balances.get(key)||blank(item);row.override=item;balances.set(key,row);}
    return [...balances.values()].map(row=>{
      const cutoff=row.override?.date||"",key=inventoryKey(row);
      const futureReceived=cutoff?entries.filter(item=>inventoryKey(item)===key&&item.date>cutoff).reduce((sum,item)=>sum+item.quantity,0):0;
      const futureUsed=cutoff?(used.get(key)?.byDate||[]).filter(item=>item.date>cutoff).reduce((sum,item)=>sum+item.quantity,0):0;
      const futureManual=cutoff?adjustments.filter(item=>inventoryKey(item)===key&&item.date>cutoff).reduce((sum,item)=>sum+Math.max(0,item.quantity),0):0;
      const remaining=row.override?row.override.quantity+futureReceived-futureUsed-futureManual:row.received-row.used-row.manualUsed;
      return {...row,remaining,overridden:Boolean(row.override)};
    }).sort((a,b)=>a.category.localeCompare(b.category,"zh-CN")||a.name.localeCompare(b.name,"zh-CN")||a.unit.localeCompare(b.unit,"zh-CN"));
  };

  if(state.token){
    renderDashboard();
    if($("inventoryBalanceGrid"))renderInventoryBalance();
  }
})();
