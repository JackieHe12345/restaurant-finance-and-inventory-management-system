if(typeof module!=='undefined' && module.exports && !globalThis.Exact) require('./money.js');
/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */
/* Oct30LingChen: exact decimal FIFO; cumulative cent allocation conserves every receipt's booked total. */
(function(root){
  'use strict';
  const EPS=Exact.decimal('0.000000001'),number=value=>Exact.decimal(value);
  const key=row=>`${Exact.or(()=>(row.category), ()=>('食材'))}\u0000${Exact.or(()=>(row.name), ()=>(''))}\u0000${Exact.or(()=>(row.unit), ()=>(''))}`;
  const present=value=>Exact.and(()=>(Exact.and(()=>(Exact.sneq(value, null)), ()=>(Exact.sneq(value, undefined)))), ()=>(Exact.sneq(String(value).trim(), '')));
  const isVoided=row=>Exact.or(()=>(Exact.or(()=>(Exact.seq(row?.voided, true)), ()=>(Exact.seq(row?.voided, 1)))), ()=>(['true','1'].includes(String(Exact.or(()=>(row?.voided), ()=>(''))).toLowerCase())));
  function unitPrice(row){
    if(Exact.truth(Exact.or(()=>(row.priceUnknown), ()=>(Exact.seq(row.price_known, false)))))return null;
    if(Exact.truth(Exact.and(()=>(present(row.total)), ()=>(Exact.or(()=>(Exact.not(Exact.valid(row.total))), ()=>(Exact.lt(number(row.total), 0)))))))return null;
    const value=row.unit_price??row.unitPrice??row.price;
    if(Exact.truth(present(value))){if(Exact.truth(Exact.not(Exact.valid(value))))return null;const price=number(value);return (Exact.truth(Exact.gte(price, 0)) ? Exact.quantize(price,6) : null);}
    if(Exact.truth(Exact.and(()=>(present(row.total)), ()=>(Exact.gt(number(row.quantity), 0))))){const total=number(row.total);return (Exact.truth(Exact.gte(total, 0)) ? Exact.quantize(Exact.div(total, number(row.quantity)),6) : null);}
    return null;
  }
  function batchAmount(batch,consumed){
    if(Exact.truth(Exact.seq(batch.unit_price, null)))return null;
    if(Exact.truth(Exact.gte(consumed, batch.original_quantity)))return batch.original_value;
    return Exact.quantize(Exact.div(Exact.mul(batch.original_value, consumed), batch.original_quantity),2);
  }
  function take(layers,quantity){
    let needed=Exact.math.max(number(0),number(quantity)),cost=number(0),unknownQuantity=number(0);const allocations=[];
    while(Exact.truth(Exact.and(()=>(Exact.gt(needed, EPS)), ()=>(layers.length)))){
      const batch=layers[0],used=Exact.math.min(needed,batch.quantity),price=batch.unit_price;
      const nextConsumed=Exact.add(batch.consumed_quantity, used),nextValue=batchAmount(batch,nextConsumed),usedCost=(Exact.truth(Exact.seq(price, null)) ? null : Exact.sub(nextValue, batch.consumed_value));
      allocations.push({...batch,quantity:used,cost:usedCost});
      if(Exact.truth(Exact.seq(price, null)))(unknownQuantity = Exact.add(unknownQuantity, used));else (cost = Exact.add(cost, usedCost));
      (needed = Exact.sub(needed, used));(batch.quantity = Exact.sub(batch.quantity, used));batch.consumed_quantity=nextConsumed;batch.consumed_value=nextValue;
      if(Exact.truth(Exact.lt(batch.quantity, EPS)))layers.shift();
    }
    if(Exact.truth(Exact.gt(needed, EPS))){(unknownQuantity = Exact.add(unknownQuantity, needed));allocations.push({id:'',date:'',source:'missing',quantity:needed,unit_price:null,cost:null});}
    return {allocations,cost,unknownQuantity,missingQuantity:needed};
  }
  function quote(balance,quantity,skip=0){const layers=(Exact.or(()=>(balance?.layers), ()=>([]))).map(row=>({...row}));if(Exact.truth(Exact.gt(number(skip), 0)))take(layers,skip);return take(layers,quantity);}
  // Display-only weighted average. Cost always comes from the original FIFO allocations.
  function averageUnitCost(result,quantity=null){
    if(Exact.truth(Exact.or(()=>(Exact.not(result)), ()=>(Exact.gt(number(Exact.or(()=>(result.unknownQuantity), ()=>(0))), EPS)))))return null;
    const used=(Exact.truth(Exact.seq(quantity, null)) ? (Exact.truth(present(result.quantity)) ? number(result.quantity) : (Exact.or(()=>(result.allocations), ()=>([]))).reduce((sum,row)=>Exact.add(sum, number(row.quantity)),number(0))) : number(quantity));
    return (Exact.truth(Exact.gt(used, EPS)) ? Exact.div(number(result.cost), used) : null);
  }
  function replay({receipts=[],outbounds=[],adjustments=[],overrides=[],asOf='9999-12-31'}={}){
    const events=[],balances=new Map(),movements=[];
    const add=(rows,event,legacyPriority)=>rows.forEach((row,index)=>{if(Exact.truth(Exact.not(isVoided(row))))events.push({...row,event,priority:(Exact.truth(Exact.finite(Date.parse(row.recorded_at))) ? 4 : legacyPriority),order:index});});
    add(receipts,'receipt',0);add(outbounds,'outbound',1);add(adjustments,'adjustment',2);add(overrides,'override',3);
    events.sort(Exact.sortComparator((a,b)=>Exact.or(()=>(Exact.or(()=>(Exact.or(()=>(String(a.date).localeCompare(String(b.date))), ()=>(Exact.sub(a.priority, b.priority)))), ()=>((Exact.truth(Exact.seq(a.priority, 4)) ? Exact.sub(Date.parse(a.recorded_at), Date.parse(b.recorded_at)) : 0)))), ()=>(Exact.sub(a.order, b.order)))));
    for(const event of events){
      if(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.not(event.name)), ()=>(Exact.not(event.date)))), ()=>(Exact.gt(event.date, asOf)))))continue;
      const quantity=number(event.quantity);if(Exact.truth(Exact.and(()=>(Exact.sneq(event.event, 'override')), ()=>(Exact.lte(quantity, 0)))))continue;
      const itemKey=key(event),row=Exact.or(()=>(balances.get(itemKey)), ()=>({category:Exact.or(()=>(event.category), ()=>('食材')),name:event.name,unit:Exact.or(()=>(event.unit), ()=>('')),received:number(0),receivedValue:number(0),used:number(0),manualUsed:number(0),normalUsed:number(0),loss:number(0),lastDate:'',remaining:number(0),layers:[],debt:number(0),overridden:false}));
      balances.set(itemKey,row);let movement;
      const layer=(qty,price,source,total=null,consumed=number(0))=>{
        const originalValue=(Exact.truth(Exact.seq(price, null)) ? null : Exact.quantize((Exact.truth(Exact.seq(total, null)) ? Exact.mul(qty, price) : total),2)),batch={id:Exact.or(()=>(event.id), ()=>(`${event.event}:${event.order}`)),date:event.date,recorded_at:Exact.or(()=>(event.recorded_at), ()=>('')),document_id:Exact.or(()=>(event.document_id), ()=>('')),document_no:Exact.or(()=>(event.document_no), ()=>('')),source:Exact.or(()=>(Exact.or(()=>(source), ()=>(event.source))), ()=>('manual')),note:Exact.or(()=>(event.note), ()=>('')),quantity:Exact.sub(qty, consumed),unit_price:price,original_quantity:qty,original_value:originalValue,consumed_quantity:consumed,consumed_value:number(0)};
        batch.consumed_value=batchAmount(batch,consumed);return batch;
      };
      if(Exact.truth(Exact.seq(event.event, 'receipt'))){
        const price=unitPrice(event),total=(Exact.truth(Exact.seq(price, null)) ? null : Exact.quantize((Exact.truth(present(event.total)) ? number(event.total) : Exact.mul(quantity, price)),2));
        (row.received = Exact.add(row.received, quantity));(row.receivedValue = Exact.add(row.receivedValue, (Exact.truth(Exact.seq(total, null)) ? number(0) : total)));row.lastDate=event.date;
        const debtPayment=Exact.math.min(row.debt,quantity);(row.debt = Exact.sub(row.debt, debtPayment));
        if(Exact.truth(Exact.gt(Exact.sub(quantity, debtPayment), EPS)))row.layers.push(layer(quantity,price,null,total,debtPayment));
        movement={...event,kind:'receipt',direction:'in',change:quantity,cost:(Exact.truth(Exact.seq(total, null)) ? number(0) : total),unknownQuantity:(Exact.truth(Exact.seq(price, null)) ? quantity : number(0)),missingQuantity:number(0),allocations:[{...layer(quantity,price,null,total),cost:total}]};
      }else if(Exact.truth(Exact.seq(event.event, 'override'))){
        const before=Exact.sub(row.layers.reduce((sum,batch)=>Exact.add(sum, batch.quantity),number(0)), row.debt),target=Exact.math.max(number(0),quantity),difference=Exact.sub(target, before);
        let cost={allocations:[],cost:number(0),unknownQuantity:number(0),missingQuantity:number(0)};
        if(Exact.truth(Exact.lt(difference, 0)))cost=take(row.layers,Exact.neg(difference));
        if(Exact.truth(Exact.gt(difference, 0))){
          const value=event.unit_price??event.unitPrice,price=(Exact.truth(Exact.or(()=>(Exact.or(()=>(Exact.seq(event.price_known, false)), ()=>(Exact.not(present(value))))), ()=>(Exact.lt(number(value), 0)))) ? null : Exact.quantize(number(value),6)),total=(Exact.truth(Exact.seq(price, null)) ? null : Exact.quantize(Exact.mul(difference, price),2));
          const repayment=Exact.math.min(row.debt,difference);(row.debt = Exact.sub(row.debt, repayment));
          if(Exact.truth(Exact.gt(Exact.sub(difference, repayment), EPS)))row.layers.push(layer(difference,price,'stocktake',total,repayment));
          cost={allocations:[{...layer(difference,price,'stocktake',total),cost:total}],cost:(Exact.truth(Exact.seq(total, null)) ? number(0) : total),unknownQuantity:(Exact.truth(Exact.seq(price, null)) ? difference : number(0)),missingQuantity:number(0)};
        }
        row.overridden=true;row.override=event;
        movement={...event,...cost,kind:'stocktake',direction:(Exact.truth(Exact.lt(difference, 0)) ? 'out' : 'in'),quantity:Exact.math.abs(difference),change:difference,book_quantity:before,counted_quantity:target};
      }else{
        const result=take(row.layers,quantity);(row.debt = Exact.add(row.debt, result.missingQuantity));
        if(Exact.truth(Exact.seq(event.event, 'outbound')))(row.used = Exact.add(row.used, quantity));else{(row.manualUsed = Exact.add(row.manualUsed, quantity));if(Exact.truth(Exact.seq(event.kind, 'loss')))(row.loss = Exact.add(row.loss, quantity));else (row.normalUsed = Exact.add(row.normalUsed, quantity));}
        movement={...event,...result,direction:'out',change:Exact.neg(quantity)};
      }
      row.remaining=Exact.sub(row.layers.reduce((sum,batch)=>Exact.add(sum, batch.quantity),number(0)), row.debt);row.lastMovementDate=event.date;
      if(Exact.truth(movement))movements.push({...movement,balance_after:row.remaining});
    }
    for(const row of balances.values()){
      row.remainingValue=row.layers.reduce((sum,batch)=>Exact.add(sum, (Exact.truth(Exact.seq(batch.unit_price, null)) ? number(0) : Exact.sub(batch.original_value, batch.consumed_value))),number(0));
      row.unpricedQuantity=Exact.add(row.layers.filter(batch=>Exact.seq(batch.unit_price, null)).reduce((sum,batch)=>Exact.add(sum, batch.quantity),number(0)), row.debt);
    }
    return {balances:[...balances.values()],movements};
  }
  const api={key,unitPrice,quote,replay,isVoided,averageUnitCost};if(Exact.truth(Exact.and(()=>(Exact.sneq(typeof module, 'undefined')), ()=>(module.exports))))module.exports=api;root.InventoryFIFO=api;
})((Exact.truth(Exact.sneq(typeof globalThis, 'undefined')) ? globalThis : this));
