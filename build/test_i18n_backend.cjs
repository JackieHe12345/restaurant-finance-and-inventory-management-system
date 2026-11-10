'use strict';
/* Node + Python stdlib only. Never imports the API or connects to a server. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
const ctx={state:{language:'en'},alert:x=>x,confirm:x=>x,prompt:x=>x};ctx.window=ctx;
vm.createContext(ctx);
for(const file of ['i18n-en.js','i18n-backend-en.js'])vm.runInContext(fs.readFileSync(path.join(root,'web',file),'utf8'),ctx,{filename:file});
const python=String.raw`
import ast,json,re,sys
from pathlib import Path
rows=[]
def template(node):
 if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
 if isinstance(node,ast.JoinedStr):
  number=iter(range(30))
  return ''.join(part.value if isinstance(part,ast.Constant) else '{'+str(next(number))+'}' for part in node.values)
 if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return (template(node.left) or '{0}')+(template(node.right) or '{1}')
 return ''
for file in sorted(Path(sys.argv[1]).glob('*.py')):
 tree=ast.parse(file.read_text())
 for node in ast.walk(tree):
  candidates=[]
  if isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call):candidates+=node.exc.args[:1]+[kw.value for kw in node.exc.keywords if kw.arg=='detail']
  if isinstance(node,ast.Call):
   name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
   if name in ('fail','issue') or (name=='append' and any(term in ast.unparse(node.func) for term in ('warning','blocker'))):candidates+=node.args[:1]
  if isinstance(node,ast.Dict):candidates+=[v for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and k.value in ('message','reason','description')]
  for candidate in candidates:
   text=template(candidate)
   if re.search('[\u4e00-\u9fff]',text):rows.append({'source':file.name+':'+str(candidate.lineno),'template':text})
print(json.dumps(rows,ensure_ascii=False))
`;
const audit=JSON.parse(cp.execFileSync(process.env.PYTHON||'python3',['-c',python,path.join(root,'backend/app')],{encoding:'utf8'}));
const defs=ctx.BACKEND_EN_MESSAGE_DEFINITIONS;
const catalog=new Map(defs.map(item=>[item.zh,item]));
const missing=audit.filter(item=>!catalog.has(item.template));
assert.deepStrictEqual(missing,[],'New backend system messages need explicit English translations.');
let templateChecks=0;
for(const item of defs){
 const input=item.zh.replace(/\{(\d+)\}/g,(_,id)=>'CAPTURE_'+id);
 const expected=item.en.replace(/\{(\d+)\}/g,(_,id)=>'CAPTURE_'+id);
 assert.strictEqual(ctx.translateBackendMessage(input),expected,item.source+' '+item.zh);
 const globalResult=ctx.systemMessage(input);
 assert(!/[\u4e00-\u9fff]/.test(globalResult),item.source+' global catalog leaked fixed Chinese: '+globalResult);
 for(const capture of expected.match(/CAPTURE_\d+/g)||[])assert(globalResult.includes(capture),item.source+' global catalog changed a capture');
 assert(!/[\u4e00-\u9fff]/.test(expected),item.source+' has untranslated fixed English text');
 templateChecks++;
}
const examples=[
 ['库存单据：数量必须是大于零的有限数字。','Inventory document: Quantity must be a finite number that is greater than zero.'],
 ['库存单据：入库单价必须是非负的有限数字。','Inventory document: Receipt unit price must be a finite number that is non-negative.'],
 ['库存单据：安全库存必须填写有效数字。','Inventory document: Safety stock must be a valid number.'],
 ['库存单据：首次保存时间须为 UTC ISO 时间。','Inventory document: First-saved timestamp must be a UTC ISO timestamp.'],
 ['新客人数量必须是大于或等于 0 的整数。','New customers must be an integer greater than or equal to 0.'],
 ['Value error, 数量和单价必须是数字','Validation error: Quantity and unit price must be numeric'],
 ["Input should be '食材' or '佐料'",'Choose Ingredient or Seasoning.'],
 ['__day_records 第 8 行 金额无效：金额不能是布尔值。','__day_records row 8: invalid amount: An amount cannot be a boolean.'],
 ['库存单据：招牌 雞肉；增加 食材 金额库存不足，此操作会新增短缺 2.5 斤；请刷新并核对入库、菜品用量和盘点记录。','Inventory document: Insufficient inventory for 招牌 雞肉；增加 食材 金额. This operation would add a shortage of 2.5 斤. Refresh and check receipts, dish usage and stocktakes.'],
 ['“收入”同时出现在不同分类，无法确定菜品用量归属。','“收入” appears in multiple categories; its dish consumption category cannot be determined.'],
 ['单位“斤；修改”不属于本次受影响库存。','Unit “斤；修改” is not part of the inventory affected by this correction.'],
 ['微信支付配置不完整：微信支付商户号、商户私钥路径','The WeChat Pay configuration is incomplete: WeChat Pay merchant id, Merchant private-key path'],
 ['记录 day/2026-11-10 的 食材明细 不是数组。','Record day/2026-11-10: Ingredient details must be an array.'],
];
for(const [input,expected] of examples){assert.strictEqual(ctx.translateBackendMessage(input),expected,input);assert.strictEqual(ctx.systemMessage(input),expected,input+' via global translation');}
const emitted=JSON.parse(cp.execFileSync(process.env.PYTHON||'python3',['-c',String.raw`
import ast,json,sys
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone
from typing import Any
from pathlib import Path
class ValidationError(Exception):pass
def fail(message):raise ValidationError('库存单据：'+message)
tree=ast.parse(Path(sys.argv[1]).read_text())
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('number','stamp')]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<inventory validators>','exec'),globals())
messages=[]
for value,label,positive in [(False,'数量',True),('NaN','数量',True),('-1','入库单价',False),('0','数量',True),('bad','安全库存',False)]:
 try:number(value,label,positive=positive)
 except ValidationError as exc:messages.append(str(exc))
try:stamp('2026-11-10T08:00:00+08:00','记账时间')
except ValidationError as exc:messages.append(str(exc))
print(json.dumps(messages,ensure_ascii=False))
`,path.join(root,'backend/app/inventory_validation.py')],{encoding:'utf8'}));
assert.strictEqual(emitted.length,6);
for(const value of emitted){const translated=ctx.systemMessage(value);assert(translated.startsWith('Inventory document: '));assert(!/[\u4e00-\u9fff]/.test(translated),translated);}
assert.strictEqual(ctx.systemMessage('保存失败：库存单据：数量必须填写有效数字。'),'Save failed: Inventory document: Quantity must be a valid number.');
assert.strictEqual(ctx.translateBackendMessage('这是用户自己输入的说明'), '这是用户自己输入的说明');
assert.strictEqual(ctx.translateBackendMessage('猫店 / 收入 / 金额'), '猫店 / 收入 / 金额');
const before={daily:[{id:'r1',日期:'2026-11-10',当日备注:'增加 食材 老店；修改 收入 → 空白',收益:'10.00'}]};
const after={daily:[{id:'r1',日期:'2026-11-10',当日备注:'删除 佐料 新店；增加 食材 鸡肉',收益:'12.50'}]};
const auditItem={before_payload:before,after_payload:after,reason:'名称写错；修改 收入 不是系统文字',action:'name_correction'};
const serialized=JSON.stringify(auditItem);
const rendered=ctx.translateAuditSummary('ignored ambiguous legacy summary',auditItem);
assert(rendered.includes('Daily notes'),rendered);
assert(rendered.includes('Revenue'),rendered);
assert(rendered.includes('"增加 食材 老店；修改 收入 → 空白"'),rendered);
assert(rendered.includes('"删除 佐料 新店；增加 食材 鸡肉"'),rendered);
assert(rendered.includes('名称写错；修改 收入 不是系统文字'),rendered);
assert(rendered.includes('"10.00" → "12.50"'),rendered);
assert.strictEqual(JSON.stringify(auditItem),serialized,'Translation must not mutate record payloads.');
const itemName={before_payload:{dishes:[{菜品名称:'收入',份数:'1'}]},after_payload:{dishes:[{菜品名称:'收入',份数:'2'}]}};
assert(ctx.translateAuditSummary('',itemName).includes('Dish name:收入'),'User name equal to a system label must be preserved.');
ctx.state.language='zh';
for(const [input] of examples)assert.strictEqual(ctx.translateBackendMessage(input),input);
assert.strictEqual(ctx.translateAuditSummary('原始中文审计',auditItem),'原始中文审计');
console.log(JSON.stringify({status:'passed',backend_source_occurrences:audit.length,unique_backend_templates:catalog.size,source_modules:new Set(audit.map(row=>row.source.split(':')[0])).size,template_checks:templateChecks,behavioral_examples:examples.length,actual_backend_validation_cases:emitted.length,checks:['nested numeric/UTC validation','Pydantic wrapper and enum','Excel location and nested errors','Chinese user item/unit preservation','structured audit data preservation','Chinese mode unchanged','source template coverage']},null,2));
