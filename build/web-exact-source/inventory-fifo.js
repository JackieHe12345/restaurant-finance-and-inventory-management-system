/* Oct30LingChen: exact decimal FIFO; cumulative cent allocation conserves every receipt's booked total. */
(function(root){
  'use strict';
  const EPS=Exact.decimal('0.000000001'),number=value=>Exact.decimal(value);
  const key=row=>`${row.category||'食材'}\u0000${row.name||''}\u0000${row.unit||''}`;
  const present=value=>value!==null&&value!==undefined&&String(value).trim()!=='';
  const isVoided=row=>row?.voided===true||row?.voided===1||['true','1'].includes(String(row?.voided||'').toLowerCase());
  function unitPrice(row){
    if(row.priceUnknown||row.price_known===false)return null;
    if(present(row.total)&&(!Exact.valid(row.total)||number(row.total)<0))return null;
    const value=row.unit_price??row.unitPrice??row.price;
    if(present(value)){if(!Exact.valid(value))return null;const price=number(value);return price>=0?Exact.quantize(price,6):null;}
    if(present(row.total)&&number(row.quantity)>0){const total=number(row.total);return total>=0?Exact.quantize(total/number(row.quantity),6):null;}
    return null;
  }
  function batchAmount(batch,consumed){
    if(batch.unit_price===null)return null;
    if(consumed>=batch.original_quantity)return batch.original_value;
    return Exact.quantize(batch.original_value*consumed/batch.original_quantity,2);
  }
  function take(layers,quantity){
    let needed=Math.max(number(0),number(quantity)),cost=number(0),unknownQuantity=number(0);const allocations=[];
    while(needed>EPS&&layers.length){
      const batch=layers[0],used=Math.min(needed,batch.quantity),price=batch.unit_price;
      const nextConsumed=batch.consumed_quantity+used,nextValue=batchAmount(batch,nextConsumed),usedCost=price===null?null:nextValue-batch.consumed_value;
      allocations.push({...batch,quantity:used,cost:usedCost});
      if(price===null)unknownQuantity+=used;else cost+=usedCost;
      needed-=used;batch.quantity-=used;batch.consumed_quantity=nextConsumed;batch.consumed_value=nextValue;
      if(batch.quantity<EPS)layers.shift();
    }
    if(needed>EPS){unknownQuantity+=needed;allocations.push({id:'',date:'',source:'missing',quantity:needed,unit_price:null,cost:null});}
    return {allocations,cost,unknownQuantity,missingQuantity:needed};
  }
  function quote(balance,quantity,skip=0){const layers=(balance?.layers||[]).map(row=>({...row}));if(number(skip)>0)take(layers,skip);return take(layers,quantity);}
  // Display-only weighted average. Cost always comes from the original FIFO allocations.
  function averageUnitCost(result,quantity=null){
    if(!result||number(result.unknownQuantity||0)>EPS)return null;
    const used=quantity===null?(present(result.quantity)?number(result.quantity):(result.allocations||[]).reduce((sum,row)=>sum+number(row.quantity),number(0))):number(quantity);
    return used>EPS?number(result.cost)/used:null;
  }
  function replay({receipts=[],outbounds=[],adjustments=[],overrides=[],asOf='9999-12-31'}={}){
    const events=[],balances=new Map(),movements=[];
    const add=(rows,event,legacyPriority)=>rows.forEach((row,index)=>{if(!isVoided(row))events.push({...row,event,priority:Number.isFinite(Date.parse(row.recorded_at))?4:legacyPriority,order:index});});
    add(receipts,'receipt',0);add(outbounds,'outbound',1);add(adjustments,'adjustment',2);add(overrides,'override',3);
    events.sort((a,b)=>String(a.date).localeCompare(String(b.date))||a.priority-b.priority||(a.priority===4?Date.parse(a.recorded_at)-Date.parse(b.recorded_at):0)||a.order-b.order);
    for(const event of events){
      if(!event.name||!event.date||event.date>asOf)continue;
      const quantity=number(event.quantity);if(event.event!=='override'&&quantity<=0)continue;
      const itemKey=key(event),row=balances.get(itemKey)||{category:event.category||'食材',name:event.name,unit:event.unit||'',received:number(0),receivedValue:number(0),used:number(0),manualUsed:number(0),normalUsed:number(0),loss:number(0),lastDate:'',remaining:number(0),layers:[],debt:number(0),overridden:false};
      balances.set(itemKey,row);let movement;
      const layer=(qty,price,source,total=null,consumed=number(0))=>{
        const originalValue=price===null?null:Exact.quantize(total===null?qty*price:total,2),batch={id:event.id||`${event.event}:${event.order}`,date:event.date,recorded_at:event.recorded_at||'',document_id:event.document_id||'',document_no:event.document_no||'',source:source||event.source||'manual',note:event.note||'',quantity:qty-consumed,unit_price:price,original_quantity:qty,original_value:originalValue,consumed_quantity:consumed,consumed_value:number(0)};
        batch.consumed_value=batchAmount(batch,consumed);return batch;
      };
      if(event.event==='receipt'){
        const price=unitPrice(event),total=price===null?null:Exact.quantize(present(event.total)?number(event.total):quantity*price,2);
        row.received+=quantity;row.receivedValue+=total===null?number(0):total;row.lastDate=event.date;
        const debtPayment=Math.min(row.debt,quantity);row.debt-=debtPayment;
        if(quantity-debtPayment>EPS)row.layers.push(layer(quantity,price,null,total,debtPayment));
        movement={...event,kind:'receipt',direction:'in',change:quantity,cost:total===null?number(0):total,unknownQuantity:price===null?quantity:number(0),missingQuantity:number(0),allocations:[{...layer(quantity,price,null,total),cost:total}]};
      }else if(event.event==='override'){
        const before=row.layers.reduce((sum,batch)=>sum+batch.quantity,number(0))-row.debt,target=Math.max(number(0),quantity),difference=target-before;
        let cost={allocations:[],cost:number(0),unknownQuantity:number(0),missingQuantity:number(0)};
        if(difference<0)cost=take(row.layers,-difference);
        if(difference>0){
          const value=event.unit_price??event.unitPrice,price=event.price_known===false||!present(value)||number(value)<0?null:Exact.quantize(number(value),6),total=price===null?null:Exact.quantize(difference*price,2);
          const repayment=Math.min(row.debt,difference);row.debt-=repayment;
          if(difference-repayment>EPS)row.layers.push(layer(difference,price,'stocktake',total,repayment));
          cost={allocations:[{...layer(difference,price,'stocktake',total),cost:total}],cost:total===null?number(0):total,unknownQuantity:price===null?difference:number(0),missingQuantity:number(0)};
        }
        row.overridden=true;row.override=event;
        movement={...event,...cost,kind:'stocktake',direction:difference<0?'out':'in',quantity:Math.abs(difference),change:difference,book_quantity:before,counted_quantity:target};
      }else{
        const result=take(row.layers,quantity);row.debt+=result.missingQuantity;
        if(event.event==='outbound')row.used+=quantity;else{row.manualUsed+=quantity;if(event.kind==='loss')row.loss+=quantity;else row.normalUsed+=quantity;}
        movement={...event,...result,direction:'out',change:-quantity};
      }
      row.remaining=row.layers.reduce((sum,batch)=>sum+batch.quantity,number(0))-row.debt;row.lastMovementDate=event.date;
      if(movement)movements.push({...movement,balance_after:row.remaining});
    }
    for(const row of balances.values()){
      row.remainingValue=row.layers.reduce((sum,batch)=>sum+(batch.unit_price===null?number(0):batch.original_value-batch.consumed_value),number(0));
      row.unpricedQuantity=row.layers.filter(batch=>batch.unit_price===null).reduce((sum,batch)=>sum+batch.quantity,number(0))+row.debt;
    }
    return {balances:[...balances.values()],movements};
  }
  const api={key,unitPrice,quote,replay,isVoided,averageUnitCost};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.InventoryFIFO=api;
})(typeof globalThis!=='undefined'?globalThis:this);
