"use strict";
const assert=require('node:assert/strict'),fifo=require('./inventory-fifo.js'),Exact=require('./money.js');
const decimalEqual=(actual,expected,message)=>assert.equal(Exact.decimal(actual).toString(),Exact.decimal(expected).toString(),message);
const item={category:'食材',name:'牛肉',unit:'斤',date:'2026-10-29'};
const receipt=(id,quantity,price,recorded_at)=>({...item,id,quantity,unit_price:price,total:Exact.amount(Exact.calculate.mul(quantity,price)),document_id:id,document_no:'RK-'+id,recorded_at});
// New receipts must not cover an earlier same-day issue; every movement remains traceable.
let data=fifo.replay({receipts:[receipt('late',5,20,'2026-10-29T03:00:00Z')],adjustments:[{...item,id:'issue',kind:'normal',quantity:2,recorded_at:'2026-10-29T02:00:00Z'}]});
assert.deepEqual(data.movements.map(row=>[row.id,row.direction,row.change.toString()]),[['issue','out','-2'],['late','in','5']]);
decimalEqual(data.movements[0].missingQuantity,2);decimalEqual(data.balances[0].remaining,3);decimalEqual(data.balances[0].remainingValue,60);
assert.equal(data.balances[0].layers[0].document_no,'RK-late');
// Stocktake gains use the stated price or stay unknown; they never become normal use/loss.
data=fifo.replay({receipts:[receipt('first',5,10)],overrides:[{...item,id:'count1',quantity:7,unit_price:20,recorded_at:'2026-10-29T02:00:00Z'},{...item,id:'count2',quantity:9,recorded_at:'2026-10-29T03:00:00Z'}]});
decimalEqual(data.balances[0].remainingValue,90);decimalEqual(data.balances[0].unpricedQuantity,2);
decimalEqual(data.balances[0].manualUsed,0);decimalEqual(data.balances[0].used,0);decimalEqual(data.balances[0].loss,0);
assert.deepEqual(data.movements.filter(row=>row.kind==='stocktake').map(row=>[row.book_quantity,row.counted_quantity,row.change,row.cost,row.unknownQuantity].map(value=>Exact.decimal(value).toString())),[["5","7","2","40","0"],["7","9","2","0","2"]]);
// All supported historical void markers are ignored; explicit zero price is known.
for(const voided of [true,1,'true','1']){data=fifo.replay({receipts:[{...receipt('void',2,8),voided},receipt('zero',3,0)],adjustments:[{...item,id:'void-issue',kind:'loss',quantity:9,voided}]});decimalEqual(data.balances[0].remaining,3);decimalEqual(data.balances[0].unpricedQuantity,0);assert.equal(data.movements.length,1);decimalEqual(data.balances[0].loss,0);}
// A count loss consumes oldest layers, so a following issue has the correct later-batch cost.
data=fifo.replay({receipts:[receipt('early',5,10),receipt('later',5,20)],overrides:[{...item,id:'count',quantity:5,recorded_at:'2026-10-29T02:00:00+00:00'}],adjustments:[{...item,id:'after-count',quantity:4,kind:'normal',recorded_at:'2026-10-29T03:00:00Z'}]});
decimalEqual(data.movements.find(row=>row.id==='after-count').cost,80);decimalEqual(data.balances[0].remaining,1);
decimalEqual(data.movements.find(row=>row.id==='count').cost,50);decimalEqual(data.balances[0].manualUsed,4);
console.log('Oct30LingChen document/FIFO movement regression checks passed.');
