/* v1.0.2: Decimal-safe business expressions; source and rebuild tool accompany this release. */
"use strict";

/* Sep05V1: cache-safe inventory consumption. */
(() => {
  function stockCategoryMaps(){
    const exact=new Map(),byName=new Map();
    for(const entry of inventoryEntries()){
      const name=String(Exact.or(()=>(entry.name), ()=>(""))).trim(),unit=String(Exact.or(()=>(entry.unit), ()=>(""))).trim(),category=(Exact.truth(Exact.seq(entry.category, "佐料")) ? "佐料" : "食材");
      if(Exact.truth(Exact.not(name)))continue;
      const exactKey=`${name}\u0000${unit}`,names=Exact.or(()=>(exact.get(exactKey)), ()=>(new Set())),named=Exact.or(()=>(byName.get(name)), ()=>(new Set()));
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
      const date=String(Exact.or(()=>(day.日期), ()=>("")));const rows=Exact.or(()=>(dishData(date).rows), ()=>([]));
      for(const dish of rows)for(const item of parseDetailItems(dish.食材明细)){
        const name=String(Exact.or(()=>(item.name), ()=>(""))).trim(),quantity=num(item.quantity),unit=String(Exact.or(()=>(item.unit), ()=>(""))).trim();
        if(Exact.truth(Exact.or(()=>(Exact.not(name)), ()=>(Exact.not(quantity)))))continue;
        const matches=Exact.or(()=>(categories.exact.get(`${name}\u0000${unit}`)), ()=>(categories.byName.get(name)));
        const category=(Exact.truth(Exact.and(()=>(Exact.seq(matches?.size, 1)), ()=>(matches.has("佐料")))) ? "佐料" : "食材");
        const key=inventoryKey({category,name,unit}),row=Exact.or(()=>(used.get(key)), ()=>({quantity:0,lastDate:"",byDate:[]}));
        (row.quantity = Exact.add(row.quantity, quantity));row.lastDate=(Exact.truth(Exact.gt(date, row.lastDate)) ? date : row.lastDate);row.byDate.push({date,quantity});used.set(key,row);
      }
    }
    return used;
  };

  inventoryBalances=function(){
    const used=inventoryConsumption(),adjustments=inventoryAdjustmentRows(),overrides=inventoryOverrideRows(),latestOverrides=new Map(),entries=inventoryEntries(),balances=new Map();
    for(const item of overrides){const key=inventoryKey(item),previous=latestOverrides.get(key);if(Exact.truth(Exact.or(()=>(Exact.not(previous)), ()=>(Exact.gte(item.date, previous.date)))))latestOverrides.set(key,item);}
    const blank=item=>({category:item.category,name:item.name,unit:item.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null});
    for(const entry of entries){const key=inventoryKey(entry),row=Exact.or(()=>(balances.get(key)), ()=>(blank(entry)));(row.received = Exact.add(row.received, entry.quantity));(row.receivedValue = Exact.add(row.receivedValue, Exact.or(()=>(entry.total), ()=>(Exact.mul(entry.quantity, entry.unitPrice)))));row.lastDate=(Exact.truth(Exact.gt(entry.date, row.lastDate)) ? entry.date : row.lastDate);balances.set(key,row);}
    for(const [key,value] of used){const row=balances.get(key);if(Exact.truth(row))row.used=value.quantity;}
    for(const item of adjustments){const key=inventoryKey(item),row=Exact.or(()=>(balances.get(key)), ()=>(blank(item)));if(Exact.truth(Exact.gt(item.quantity, 0))){(row.manualUsed = Exact.add(row.manualUsed, item.quantity));if(Exact.truth(Exact.seq(item.kind, "loss")))(row.loss = Exact.add(row.loss, item.quantity));else (row.normalUsed = Exact.add(row.normalUsed, item.quantity));}balances.set(key,row);}
    for(const [key,item] of latestOverrides){const row=Exact.or(()=>(balances.get(key)), ()=>(blank(item)));row.override=item;balances.set(key,row);}
    return [...balances.values()].map(row=>{
      const cutoff=Exact.or(()=>(row.override?.date), ()=>("")),key=inventoryKey(row);
      const futureReceived=(Exact.truth(cutoff) ? entries.filter(item=>Exact.and(()=>(Exact.seq(inventoryKey(item), key)), ()=>(Exact.gt(item.date, cutoff)))).reduce((sum,item)=>Exact.add(sum, item.quantity),0) : 0);
      const futureUsed=(Exact.truth(cutoff) ? (Exact.or(()=>(used.get(key)?.byDate), ()=>([]))).filter(item=>Exact.gt(item.date, cutoff)).reduce((sum,item)=>Exact.add(sum, item.quantity),0) : 0);
      const futureManual=(Exact.truth(cutoff) ? adjustments.filter(item=>Exact.and(()=>(Exact.seq(inventoryKey(item), key)), ()=>(Exact.gt(item.date, cutoff)))).reduce((sum,item)=>Exact.add(sum, Exact.math.max(0,item.quantity)),0) : 0);
      const remaining=(Exact.truth(row.override) ? Exact.sub(Exact.sub(Exact.add(row.override.quantity, futureReceived), futureUsed), futureManual) : Exact.sub(Exact.sub(row.received, row.used), row.manualUsed));
      return {...row,remaining,overridden:Boolean(row.override)};
    }).sort(Exact.sortComparator((a,b)=>Exact.or(()=>(Exact.or(()=>(a.category.localeCompare(b.category,"zh-CN")), ()=>(a.name.localeCompare(b.name,"zh-CN")))), ()=>(a.unit.localeCompare(b.unit,"zh-CN")))));
  };

  if(Exact.truth(state.token)){
    renderDashboard();
    if(Exact.truth($("inventoryBalanceGrid")))renderInventoryBalance();
  }
})();
