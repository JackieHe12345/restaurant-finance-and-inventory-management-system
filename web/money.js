/* Oct30LingChen. Exact decimal arithmetic. No binary floating point is used
 * for a Decimal calculation; only chart/DOM adapters may call toNumber().
 * Persisted currency is ROUND_HALF_UP to cents; unit prices have 6 places.
 */
(function(root){
  "use strict";
  const POW=[1n],MAX="999999999999.99",MAX_PRICE="999999999999.999999",DIVISION_PLACES=24;
  const power=n=>{if(!Number.isInteger(n)||n<0||n>120)throw new RangeError("小数位数超出支持范围");while(POW.length<=n)POW.push(POW[POW.length-1]*10n);return POW[n];};
  const rounded=(numerator,denominator)=>{if(denominator===0n)throw new RangeError("金额计算不能除以零");if(denominator<0n){numerator=-numerator;denominator=-denominator;}const sign=numerator<0n?-1n:1n,n=numerator<0n?-numerator:numerator,q=n/denominator,r=n%denominator;return sign*(q+(r*2n>=denominator?1n:0n));};
  class Decimal {
    constructor(coefficient,scale=0){this.coefficient=coefficient;this.scale=scale;Object.freeze(this);}
    toString(){let n=this.coefficient,s=this.scale,negative=n<0n;if(negative)n=-n;let text=n.toString().padStart(s+1,"0");if(s)text=text.slice(0,-s)+"."+text.slice(-s);text=text.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/,"");return (negative&&n!==0n?"-":"")+text;}
    toFixed(places=2){const q=quantize(this,places),negative=q.coefficient<0n,n=negative?-q.coefficient:q.coefficient,text=n.toString().padStart(places+1,"0");return(negative&&n!==0n?"-":"")+(places?text.slice(0,-places)+"."+text.slice(-places):text);}
    toJSON(){return this.toString();}
    toNumber(){return Number(this.toString());}
    valueOf(){throw new TypeError("禁止将精确金额隐式转换为浮点数；请在图表边界显式转换");}
    toLocaleString(locale,options={}){const min=options.minimumFractionDigits??0,max=options.maximumFractionDigits??Math.max(min,3);let text=this.toFixed(max);if(max>min){let [whole,fraction]=text.split(".");while(fraction&&fraction.length>min&&fraction.endsWith("0"))fraction=fraction.slice(0,-1);text=whole+(fraction?"."+fraction:"");}let [whole,fraction]=text.split(".");if(options.useGrouping!==false)whole=whole.replace(/\B(?=(\d{3})+(?!\d))/g,",");return whole+(fraction?"."+fraction:"");}
  }
  const is=value=>value instanceof Decimal;
  function decimal(value){
    if(is(value))return value;
    if(value===null||value===undefined||value===""||typeof value==="boolean")return new Decimal(value===true?1n:0n);
    const input=String(value).trim();if(input==="")return new Decimal(0n);
    const match=/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(input)||/^([+-]?)()(?:\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(input);
    if(!match||input.length>160)throw new TypeError("金额必须是有效十进制数");
    const exponent=Number(match[4]||0),fraction=match[3]||"";if(!Number.isSafeInteger(exponent)||Math.abs(exponent)>60)throw new RangeError("金额超出支持范围");
    let scale=fraction.length-exponent,coefficient=BigInt((match[1]==="-"?"-":"")+(match[2]||"0")+fraction);
    if(scale<0){coefficient*=power(-scale);scale=0;}if(scale>60)throw new RangeError("小数位数超出支持范围");
    return new Decimal(coefficient,scale);
  }
  function aligned(a,b){a=decimal(a);b=decimal(b);const scale=Math.max(a.scale,b.scale);return[a.coefficient*power(scale-a.scale),b.coefficient*power(scale-b.scale),scale];}
  function cmp(a,b){const [x,y]=aligned(a,b);return x<y?-1:x>y?1:0;}
  function quantize(value,places=2){const d=decimal(value);return new Decimal(d.scale>places?rounded(d.coefficient,power(d.scale-places)):d.coefficient*power(places-d.scale),places);}
  const numeric=value=>is(value)||typeof value==="number"||typeof value==="bigint";
  const exactAdd=(a,b)=>{const[x,y,s]=aligned(a,b);return new Decimal(x+y,s);};
  const exactSub=(a,b)=>{const[x,y,s]=aligned(a,b);return new Decimal(x-y,s);};
  const exactMul=(a,b)=>{a=decimal(a);b=decimal(b);return new Decimal(a.coefficient*b.coefficient,a.scale+b.scale);};
  function exactDiv(a,b,places=DIVISION_PLACES){a=decimal(a);b=decimal(b);const shift=places+b.scale-a.scale;return new Decimal(rounded(a.coefficient*(shift>=0?power(shift):1n),b.coefficient*(shift<0?power(-shift):1n)),places);}
  function amount(value){if(typeof value==="boolean")throw new TypeError("金额不能是布尔值");const result=quantize(value,2);if(cmp(abs(result),MAX)>0)throw new RangeError("金额不能超过 999,999,999,999.99 元");return result.toFixed(2);}
  function price(value){if(typeof value==="boolean")throw new TypeError("单价不能是布尔值");const result=quantize(value,6);if(cmp(abs(result),MAX_PRICE)>0)throw new RangeError("单价不能超过 999,999,999,999.999999 元");return result.toFixed(6);}
  function abs(value){if(!is(value))return Math.abs(value);return new Decimal(value.coefficient<0n?-value.coefficient:value.coefficient,value.scale);}
  const truth=value=>is(value)?value.coefficient!==0n:Boolean(value);
  const eq=(a,b,strict)=>{if(!is(a)&&!is(b))return strict?a===b:a==b;if(a===null||b===null||a===undefined||b===undefined)return false;if(strict&&(!numeric(a)||!numeric(b)))return false;try{return cmp(a,b)===0;}catch(_){return false;}};
  const compare=(a,b,op)=>{if(!is(a)&&!is(b))return op==="lt"?a<b:op==="lte"?a<=b:op==="gt"?a>b:a>=b;try{const n=cmp(a,b);return op==="lt"?n<0:op==="lte"?n<=0:op==="gt"?n>0:n>=0;}catch(_){return false;}};
  const math={abs,sqrt:value=>Math.sqrt(is(value)?value.toNumber():value),min:(...values)=>values.length?values.reduce((a,b)=>compare(a,b,"lte")?a:b):Infinity,max:(...values)=>values.length?values.reduce((a,b)=>compare(a,b,"gte")?a:b):-Infinity,round:value=>is(value)?quantize(value,0):Math.round(value),floor:value=>{if(!is(value))return Math.floor(value);const p=power(value.scale),q=value.coefficient/p,r=value.coefficient%p;return new Decimal(q-(r<0n?1n:0n));},ceil:value=>{if(!is(value))return Math.ceil(value);const p=power(value.scale),q=value.coefficient/p,r=value.coefficient%p;return new Decimal(q+(r>0n?1n:0n));},trunc:value=>is(value)?new Decimal(value.coefficient/power(value.scale)):Math.trunc(value)};
  const api={Decimal,is,decimal,valid:value=>{try{decimal(value);return true;}catch(_){return false;}},quantize,amount,price,currency:value=>quantize(value,2),cmp,truth,toNumber:value=>is(value)?value.toNumber():Number(value),sortComparator:compareFn=>(a,b)=>{const result=compareFn(a,b);return is(result)?cmp(result,0):result;},not:value=>!truth(value),type:value=>is(value)?"number":typeof value,abs,
    add:(a,b)=>(is(a)||is(b))?(numeric(a)&&numeric(b)?exactAdd(a,b):String(a)+String(b)):a+b,
    sub:(a,b)=>is(a)||is(b)?exactSub(a,b):a-b,
    mul:(a,b)=>is(a)||is(b)?exactMul(a,b):a*b,
    div:(a,b)=>is(a)||is(b)?exactDiv(a,b):a/b,
    mod:(a,b)=>{if(!is(a)&&!is(b))return a%b;const[x,y,s]=aligned(a,b);return new Decimal(x%y,s);},
    pow:(a,b)=>{if(!is(a)&&!is(b))return a**b;const exp=Number(b);if(!Number.isSafeInteger(exp)||Math.abs(exp)>30)throw new RangeError("不支持的精确数值指数");a=decimal(a);if(exp<0)return exactDiv(1,api.pow(a,-exp));return new Decimal(a.coefficient**BigInt(exp),a.scale*exp);},
    neg:value=>is(value)?new Decimal(-value.coefficient,value.scale):-value,
    pos:value=>is(value)?value:+value,
    eq:(a,b)=>eq(a,b,false),neq:(a,b)=>!eq(a,b,false),seq:(a,b)=>eq(a,b,true),sneq:(a,b)=>!eq(a,b,true),
    lt:(a,b)=>compare(a,b,"lt"),lte:(a,b)=>compare(a,b,"lte"),gt:(a,b)=>compare(a,b,"gt"),gte:(a,b)=>compare(a,b,"gte"),
    or:(left,right)=>{const value=left();return truth(value)?value:right();},and:(left,right)=>{const value=left();return truth(value)?right():value;},
    finite:value=>is(value)||Number.isFinite(value),integer:value=>is(value)?value.coefficient%power(value.scale)===0n:Number.isInteger(value),safeInteger:value=>is(value)?value.coefficient%power(value.scale)===0n&&cmp(abs(value),Number.MAX_SAFE_INTEGER)<=0:Number.isSafeInteger(value),math,
    sum:values=>values.reduce((sum,value)=>exactAdd(sum,decimal(value)),new Decimal(0n)),
    calculate:{add:exactAdd,sub:exactSub,mul:exactMul,div:exactDiv},
    // Business-number boundaries. Labels/metadata are deliberately untouched.
    amountKey:key=>!(/备注|说明|明细|名称|日期|时间|计入|include_|_date$|_time$|_at$|_note$|_name$|_id$/.test(key))&&(/^(amount|total|cost|income|expense|balance|opening_balance|target_balance|force_balance|remainingValue|receivedValue|known_cost|revenue|gross|net|fees|payment_amount|refund_amount|net_amount|unit_cost_total)$/.test(key)||/_balance$|_expenses$|shareholder_loan/.test(key)||/金额|成本|收入|收益|支出|现金|线上|手续费|抽成|余额|结余|借款|总额|总价|煤气费|水电费|房租|人工|水费|电费|水电$|其他$|其它$|外卖$|微信增加$|微信覆盖$|支付宝增加$|支付宝覆盖$/.test(key)),
    priceKey:key=>/^(price|unit_price|unitPrice|nextUnitPrice)$/.test(key)||/单价$/.test(key),
    quantityKey:key=>/^(quantity|qty|previous_quantity|final_quantity|servings|count|version|sequence)$/.test(key)||/数量$|人数$|份数$/.test(key),
    normalizePayload(payload){
      // Traverse only documented financial containers. Unknown extensions keep
      // their original type/value even if they happen to contain amount/price.
      const daily=new Set('收益 总金额 收入 总收入 食材成本 佐料成本 水电 其他 其它 总现金 总线上 A店收入 B店收入 学生外卖 A店外卖 B店外卖 手续费 可用余额 向股东借款'.split(' '));
      for(const store of ['A店','B店'])for(const suffix of ['现金','微信增加','微信自动','微信覆盖','支付宝增加','支付宝覆盖','微信支付金额','微信退款金额'])daily.add(store+suffix);
      const month=new Set('人工总额 房租总额 水费支出 电费支出 水电费 实际使用水费 实际使用电费 煤气费 其它固定成本 预计水费 预计电费 预计煤气费'.split(' '));
      const detail=new Set('total 总价 金额 amount cost 成本 总成本'.split(' ')),prices=new Set('unit_price unitPrice price 单价 单位价'.split(' '));
      const cash=new Set('opening_balance base_balance current_balance shareholder_loan amount 金额 income expense running_balance previous_month_balance target_balance force_balance'.split(' '));
      const schemas={daily,monthly_fixed:month,fixed_expenses:new Set(['金额','amount']),dishes:new Set(['总成本','cost','total_cost']),菜品数据:new Set(['总成本','成本','cost','total_cost','单份成本']),detail,entries:detail,adjustments:detail,overrides:detail,transactions:cash};
      const details=new Set(['食材明细','佐料明细','其他明细','其它明细']);
      function derived(key,row,context){
        if(context!=='daily')return false;
        const entered=field=>Object.prototype.hasOwnProperty.call(row,field)&&row[field]!==null&&String(row[field]).trim()!=='';
        const channels=Object.fromEntries(['A店','B店'].map(store=>[store,['现金','微信增加','微信自动','微信覆盖','支付宝增加','支付宝覆盖','外卖'].map(suffix=>store+suffix)]));
        if(['A店收入','B店收入'].includes(key))return channels[key.slice(0,2)].some(entered);
        if(key==='总现金')return ['A店现金','B店现金'].some(entered);
        if(key==='总线上')return [...channels['A店'].slice(1),...channels['B店'].slice(1),'学生外卖'].some(entered);
        if(['收益','总金额','收入','总收入'].includes(key))return [...channels['A店'],...channels['B店'],'学生外卖'].some(entered);
        if(['食材成本','佐料成本'].includes(key)){let detail=row[key==='食材成本'?'食材明细':'佐料明细'];if(typeof detail==='string'){try{detail=JSON.parse(detail);}catch(_){return detail.trim()!=='';}}return Array.isArray(detail)?detail.length>0:!!detail&&typeof detail==='object'&&Object.keys(detail).length>0;}
        return false;
      }
      const scalar=(value,key,row,context)=>{if(value===null||value===undefined||value==='')return value;if(typeof value==='boolean')throw new TypeError('金额不能是布尔值');return prices.has(key)?price(value):derived(key,row,context)?quantize(value,2).toFixed(2):amount(value);};
      function node(value,context){
        if(Array.isArray(value))return value.map(item=>node(item,context));
        // JSON/plain-text detail strings are intentionally retained verbatim;
        // the server applies schema validation without touching unchanged text.
        if(!value||typeof value!=='object'||is(value))return value;
        const result={...value},known=schemas[context]||new Set();
        for(const [key,item] of Object.entries(value)){
          if(known.has(key)||(['detail','entries','adjustments','overrides'].includes(context)&&prices.has(key)))result[key]=scalar(item,key,value,context);
          else if(details.has(key))result[key]=node(item,'detail');
          else if(key==='菜品数据')result[key]=node(item,'菜品数据');
          else if(api.quantityKey(key)&&is(item))result[key]=item.toNumber();
        }
        return result;
      }
      if(!payload||typeof payload!=='object'||Array.isArray(payload))return payload;
      const result={...payload};
      for(const key of new Set([...daily,...month,...cash]))if(Object.prototype.hasOwnProperty.call(payload,key))result[key]=scalar(payload[key],key,payload,'daily');
      for(const key of details)if(Object.prototype.hasOwnProperty.call(payload,key))result[key]=node(payload[key],'detail');
      for(const key of Object.keys(schemas))if(key!=='detail'&&Object.prototype.hasOwnProperty.call(payload,key))result[key]=node(payload[key],key);
      return result;
    }
  };
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  root.Exact=api;
})(typeof globalThis!=="undefined"?globalThis:this);
