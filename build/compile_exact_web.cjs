/* Rebuild the shipped business scripts from reviewed source expressions.
 * Only Decimal operands use decimal arithmetic; normal JS strings, dates,
 * navigation counters and DOM operations retain their original semantics.
 * This prevents a legacy layer overriding a corrected monetary function.
 * The decimal runtime and stylesheets are maintained directly in web/.
 */
const fs=require('fs'),path=require('path'),acorn=require('./js-transform/node_modules/acorn');
const source=path.join(__dirname,'web-exact-source'),target=path.resolve(__dirname,'../web');
const Exact=require('../web/money.js');
const moneyFunctions=new Set(['legacyRevenueValue','paymentBreakdownRevenue','storeRevenueValue','fixedBreakdown','saveLedger','saveFixed','openFixedExpensesModal','rebuildMonthFixedFromExpenses','cashOpeningValue','cashFlowSummary','cashFlowFromServer','renderCashPosition','saveCashPosition','updateInventoryEntryTotal','updateDishTotal','sumItems','syncLedgerRevenueBreakdown','effectiveWechatV26','storeTotalsFor','cashSignedAmountV4','cashRowsWithBalanceV4','cashLoanHistoryV4','responseMoneyV4','renderCashLedgerV4','saveCashBaselineV4','openCashItemV4']);
const binary={'+':'add','-':'sub','*':'mul','/':'div','%':'mod','**':'pow','==':'eq','!=':'neq','===':'seq','!==':'sneq','<':'lt','<=':'lte','>':'gt','>=':'gte'};
const unary={'-':'neg','+':'pos','!':'not'};
function transform(text){
 const ast=acorn.parse(text,{ecmaVersion:'latest',sourceType:'script'});
 const functions=new WeakMap();function tag(node,name=''){if(!node||typeof node!=='object')return;if(node.type==='FunctionDeclaration')name=node.id.name;functions.set(node,name);for(const [k,v] of Object.entries(node)){if(['start','end'].includes(k))continue;Array.isArray(v)?v.forEach(n=>tag(n,name)):tag(v,name);}}tag(ast);
 const hasSuspension=node=>{if(!node||typeof node!=='object')return false;if(['AwaitExpression','YieldExpression'].includes(node.type))return true;if(/Function/.test(node.type))return false;return Object.entries(node).some(([k,v])=>!['start','end'].includes(k)&&(Array.isArray(v)?v.some(hasSuspension):hasSuspension(v)));};
 function children(node){const result=[];for(const [key,value]of Object.entries(node)){if(key==='start'||key==='end')continue;if(Array.isArray(value)){for(const item of value)if(item&&typeof item.type==='string')result.push(item);}else if(value&&typeof value.type==='string')result.push(value);}return result.sort((a,b)=>a.start-b.start);}
 function render(node){
  const raw=()=>text.slice(node.start,node.end),call=(name,args)=>`Exact.${name}(${args.join(', ')})`;
  if(node.type==='CallExpression'&&node.callee.type==='Identifier'&&node.callee.name==='num'&&node.arguments.length===1){
   const arg=node.arguments[0],source=text.slice(arg.start,arg.end),leaf=arg.type==='ChainExpression'?arg.expression:arg,key=leaf?.type==='MemberExpression'&&!leaf.computed?leaf.property.name:'';
   const isPrice=Exact.priceKey(key)||/get\(["'](?:unitPrice|price)["']\)|Exact\.price\(/.test(source);
   const isMoney=moneyFunctions.has(functions.get(node))||Exact.amountKey(key)||/get\(["'](?:total|成本)["']\)|data-dish=["']cost|^revenueValue$|^full\[4\]$|^custom\[4\]$|^amountOnly\[2\]$/.test(source)||(functions.get(node)==='proDerivedUnitPriceText'&&source==='total');
   if(isPrice||isMoney)return`Exact.decimal(Exact.${isPrice?'price':'currency'}(${render(arg)}))`;
  }
  if(node.type==='BinaryExpression'&&binary[node.operator])return call(binary[node.operator],[render(node.left),render(node.right)]);
  if(node.type==='UnaryExpression'&&unary[node.operator])return call(unary[node.operator],[render(node.argument)]);
  if(node.type==='LogicalExpression'&&node.operator!=='??'&&!hasSuspension(node))return call(node.operator==='||'?'or':'and',[`()=>(${render(node.left)})`,`()=>(${render(node.right)})`]);
  if(node.type==='ConditionalExpression')return`(Exact.truth(${render(node.test)}) ? ${render(node.consequent)} : ${render(node.alternate)})`;
  if(node.type==='AssignmentExpression'&&binary[node.operator.slice(0,-1)]&&node.operator.endsWith('=')){
   const left=render(node.left);return`(${left} = ${call(binary[node.operator.slice(0,-1)],[left,render(node.right)])})`;
  }
  if(node.type==='MemberExpression'&&!node.computed&&node.object.type==='Identifier'&&node.object.name==='Number'){
   const replacement={isFinite:'finite',isInteger:'integer',isSafeInteger:'safeInteger'}[node.property.name];if(replacement)return`Exact.${replacement}`;
  }
  if(node.type==='MemberExpression'&&!node.computed&&node.object.type==='Identifier'&&node.object.name==='Math'&&['abs','min','max','round','floor','ceil','trunc','sqrt'].includes(node.property.name))return`Exact.math.${node.property.name}`;
  if(node.type==='CallExpression'&&node.callee.type==='MemberExpression'&&!node.callee.computed&&['toFixed','toLocaleString'].includes(node.callee.property.name)&&node.callee.object.type==='CallExpression'&&node.callee.object.callee.type==='Identifier'&&node.callee.object.callee.name==='Number')return`Exact.decimal(${node.callee.object.arguments.map(render).join(', ')}).${node.callee.property.name}(${node.arguments.map(render).join(', ')})`;
  if(node.type==='CallExpression'&&node.callee.type==='Identifier'&&node.callee.name==='Number')return`Exact.toNumber(${node.arguments.map(render).join(', ')})`;
  if(node.type==='CallExpression'&&node.callee.type==='MemberExpression'&&!node.callee.computed&&node.callee.property.name==='sort'&&node.arguments.length===1)return`${render(node.callee)}(Exact.sortComparator(${render(node.arguments[0])}))`;
  if(node.type==='CallExpression'&&node.callee.type==='MemberExpression'&&!node.callee.computed&&node.callee.property.name==='filter'&&node.arguments.length===1&&node.arguments[0].type==='Identifier'&&node.arguments[0].name==='Boolean')return`${render(node.callee)}(Exact.truth)`;
  let output='',cursor=node.start;for(const child of children(node)){if(child.start<cursor)continue;output+=text.slice(cursor,child.start);let value=render(child);if(['IfStatement','WhileStatement','DoWhileStatement','ForStatement'].includes(node.type)&&child===node.test)value=`Exact.truth(${value})`;output+=value;cursor=child.end;}return output+text.slice(cursor,node.end);
 }
 return '/* Oct30LingChen: Decimal-safe business expressions; source and rebuild tool accompany this release. */\n'+render(ast);
}
let files=0;for(const name of fs.readdirSync(source).filter(name=>name.endsWith('.js'))){const result=(name==='inventory-fifo.js'?"if(typeof module!=='undefined' && module.exports && !globalThis.Exact) require('./money.js');\n":'')+transform(fs.readFileSync(path.join(source,name),'utf8'));acorn.parse(result,{ecmaVersion:'latest'});fs.writeFileSync(path.join(target,name),result);files++;}
console.log(JSON.stringify({files,source,target}));
