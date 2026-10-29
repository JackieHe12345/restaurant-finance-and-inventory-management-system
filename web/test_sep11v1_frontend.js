"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const Exact = require("./money.js");
const currency = value => Exact.currency(value).toFixed(2);
class TestDate extends Date { constructor(...args) { super(...(args.length ? args : ["2026-10-29T12:00:00Z"])); } }

const root = __dirname;
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const cashJs = fs.readFileSync(path.join(root, "sep04.js"), "utf8");
const appJs = fs.readFileSync(path.join(root, "app.js"), "utf8");
const css = fs.readFileSync(path.join(root, "sep07.css"), "utf8");

function functionSource(source, name) {
  let start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `missing function ${name}`);
  if (source.slice(start - 6, start) === "async ") start -= 6;
  const brace = source.indexOf("{", start);
  let depth = 0;
  for (let index = brace; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`unterminated function ${name}`);
}

const context = vm.createContext({
  Date: TestDate,
  Exact,
  Number,
  Math,
  String,
  num: value => Exact.decimal(value),
  entered: value => value !== null && value !== undefined && String(value).trim() !== "",
  normalizeDateKey: value => String(value || "").replaceAll("/", "-"),
  isCanonicalDate: value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || "")),
  isoDate: date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`,
});
for (const name of ["isCashForceEntryV4", "isCashEntryLockedV4", "cashSignedAmountV4", "cashEntryTimeV4", "chronologicalCashEntriesV4", "cashRowsWithBalanceV4", "cashLoanHistoryV4", "responseMoneyV4", "renderCashLedgerV4", "saveCashBaselineV4", "openCashItemV4", "deleteCashItemV4"]) {
  vm.runInContext(functionSource(cashJs, name), context);
}

const fallbackReplay = vm.runInContext(`cashRowsWithBalanceV4({opening_balance:100,transactions:[
  {id:"expense",date:"2026-09-08",type:"其它现金支出",amount:-10,created_at:"2026-09-08T11:00:00Z"},
  {id:"force",date:"2026-09-08",type:"余额强制修改",amount:40,mode:"force",system_locked:true,created_at:"2026-09-08T10:00:00Z"},
  {id:"income",date:"2026-09-08",type:"营业收入",amount:50}
]},{})`, context);
assert.deepEqual(Array.from(fallbackReplay, row => [row.id, currency(row.running_balance)]), [["expense", "90.00"], ["income", "140.00"], ["force", "40.00"]]);
assert.equal(fallbackReplay[2]._serverRunningBalance, false);

/* /cash-position returns newest first.  The client must reverse that exact
   server sequence rather than re-sort same-day deltas and lose the balance
   order used to calculate historical carry-over. */
const serverReplay = vm.runInContext(`cashRowsWithBalanceV4({opening_balance:100,transactions:[]},{entries:[
  {id:"next-month",date:"2026-09-09",type:"其它现金收入",amount:30,running_balance:70},
  {id:"force",date:"2026-09-08",type:"余额强制修改",amount:40,mode:"force",system_locked:true,created_at:"2026-09-08T10:00:00Z",running_balance:40},
  {id:"income",date:"2026-09-08",type:"营业收入",amount:50,running_balance:140},
  {id:"expense",date:"2026-09-08",type:"其它现金支出",amount:-10,running_balance:90}
]})`, context);
assert.deepEqual(Array.from(serverReplay, row => [row.id, currency(row.running_balance)]), [["expense", "90.00"], ["income", "140.00"], ["force", "40.00"], ["next-month", "70.00"]]);
assert.equal(currency(serverReplay.filter(row => row.date < "2026-09-09").at(-1).running_balance), "40.00", "historical carry-over must use the final row before the selected month");

const authoritative = vm.runInContext(`cashRowsWithBalanceV4({opening_balance:100},{entries:[
  {id:"force",date:"2026-09-08",type:"余额强制修改",amount:40,mode:"force",running_balance:37}
]})`, context);
assert.equal(currency(authoritative[0].running_balance), "37.00", "server running_balance must win");

const loanHistory = vm.runInContext(`cashLoanHistoryV4({
  opening_date:"2026-03-01",shareholder_loan:25,
  transactions:[
    {date:"2026-02-10",type:"向股东借款",amount:40},
    {date:"2026-09-02",type:"向股东借款",amount:60},
    {date:"2025-09-02",type:"向股东借款",amount:30},
    {date:"2026-09-03",type:"向股东借款",amount:999,mode:"force"},
    {date:"2099-01-01",type:"向股东借款",amount:500}
  ]
})`, context);
assert.equal(currency(Exact.sum(Array.from(loanHistory, row=>row.amount))),"155.00","cumulative fallback includes pre-opening and legacy loans, but not future/force rows");
assert.equal(currency(Exact.sum(Array.from(loanHistory).filter(row=>row.date.startsWith("2026-")).map(row=>row.amount))),"125.00","year fallback includes pre-opening loans");
assert.equal(currency(Exact.sum(Array.from(loanHistory).filter(row=>row.date.startsWith("2026-09")).map(row=>row.amount))),"60.00","month fallback uses payload transaction dates");

assert.match(html, /data-build="Oct30LingChen"/);
// Asset count may grow; every current local stylesheet/script must exist and
// use the current version, including the decimal runtime and adaptive layout.
const assets = [...html.matchAll(/(?:src|href)="([^"?]+\.(?:css|js))(?:\?v=([^" ]+))?"/g)];
assert.ok(assets.length > 0);
for (const [, asset, version] of assets) {
  assert.equal(version, "Oct30LingChen", `cache key for ${asset}`);
  assert.ok(fs.existsSync(path.join(root, asset)), `missing asset ${asset}`);
}
assert.ok(html.indexOf("money.js") < html.indexOf("app.js"));
assert.ok(assets.some(match => match[1] === "adaptive.css"));
assert.match(html, /修正后余额<input id="cashOpeningBalanceV4"/);
assert.match(html, /<small>上月结余<\/small><strong id="cashPreviousMonthBalance"/);
assert.ok(html.indexOf("cashLoanMonth") < html.indexOf("cashLoanYear") && html.indexOf("cashLoanYear") < html.indexOf("cashLoanTotal"), "loan summaries must be month/year/cumulative");
assert.doesNotMatch(html, /cashFlowSummary|基准日之后现金流/);

// Cash behavior is exercised below instead of matching pre-transform JS
// expressions such as !force&&signed>0, whose Exact form is intentionally different.
assert.doesNotMatch(cashJs, /payload\.base_balance\s*=\s*payload\.opening_balance/);

for (const line of [
  "(本月截至目前的日均收入 x 本月总天数)",
  "平本需要 日均收入（“收入”指“Revenue”）增加",
  "( (预计月底盈亏/本月毛利率) / 本月天数 )",
]) assert.ok(appJs.includes(line), `missing exact forecast line: ${line}`);
assert.match(css, /\.forecast-row \.forecast-title\{[^}]*white-space:nowrap/);
assert.match(css, /\.forecast-row \.forecast-formula\{[^}]*white-space:nowrap/);
assert.match(css, /\.forecast-row strong\{[^}]*text-align:right/);

async function checkCashEditingAndRendering() {
  const fields = Object.create(null);
  const field = id => fields[id] ||= {value:"", innerHTML:"", textContent:"", querySelectorAll:()=>[]};
  let payload = {opening_balance:"100.00",base_balance:"10.00",transactions:[]},saved;
  const modalFields = Object.create(null);
  const modal = {querySelector: selector => modalFields[selector] ||= {value:""}, remove(){this.removed=true;}};
  Object.assign(context, {
    $: field, cashPayloadV4:()=>payload, cashServerV4:null,
    money:currency, escapeHtml: value=>String(value), uuid:()=>"new-cash-row",
    safely: fn=>fn(), confirm:()=>true,
    saveCashPayloadV4:async value=>{saved=value;},
    document:{activeElement:null, createElement:()=>modal, body:{appendChild(){}}},
  });
  field("cashOpeningBalanceV4").value="40.005";
  field("cashOpeningDateV4").value="2026-10-29";
  await context.saveCashBaselineV4();
  assert.equal(saved.base_balance,"10.00","balance corrections retain the original baseline");
  const locked=saved.transactions[0];
  assert.equal(currency(locked.amount),"40.01","correction input rounds half up");
  assert.equal(locked.type,"余额强制修改");assert.equal(locked.description,"余额强制修改");
  assert.equal(locked.mode,"force");assert.equal(locked.system_locked,true);
  assert.equal(locked.created_at,"2026-10-29T12:00:00.000Z");
  await assert.rejects(context.deleteCashItemV4(locked.id),/不能删除/);

  for (const [type,mode] of [["余额强制修改","force"],["其它现金收入","delta"]]) {
    context.openCashItemV4();
    modal.querySelector("[data-cash-date]").value="2026-10-29";
    modal.querySelector("[data-cash-type]").value=type;
    modal.querySelector("[data-cash-amount]").value="0.105";
    await modal.querySelector("[data-save]").onclick();
    const item=saved.transactions.at(-1);
    assert.equal(currency(item.amount),"0.11");assert.equal(item.mode,mode);
    assert.equal(item.system_locked,false,"items added through the item editor stay deletable");
    assert.equal(modal.removed,true);
  }
  payload={opening_balance:"10.00",transactions:[
    {id:"income",date:"2026-10-29",type:"其它现金收入",amount:"0.10"},
    {id:"expense",date:"2026-10-29",type:"其它现金支出",amount:"0.20"},
    {id:"force",date:"2026-10-29",type:"余额强制修改",amount:"11.11",mode:"force",system_locked:true},
  ]};
  field("cashMonthFilter").value="2026-10";
  context.renderCashLedgerV4();
  const rendered=field("cashLedgerRows").innerHTML;
  assert.match(rendered, /<td>0\.10<\/td><td>—<\/td>/, "income is in the income column");
  assert.match(rendered, /<td>—<\/td><td>0\.20<\/td>/, "expense is in the expense column");
  assert.match(rendered, /class="cash-force-entry"[^]*?<td>—<\/td><td>—<\/td><td>11\.11<\/td>/, "correction is not income or expense");
  assert.match(rendered, /class="cash-locked-entry">不可删除<\/span>/);
  assert.equal(field("cashCurrentBalance").textContent,"11.11");
  context.cashServerV4={entries:[],summary_month:"2026-10",current_balance:"0.30",previous_month_balance:"0.10",shareholder_loan_this_month:"0.01",shareholder_loan_this_year:"0.02",shareholder_loan_total:"0.03"};
  context.renderCashLedgerV4();
  for(const [id,value] of [["cashCurrentBalance","0.30"],["cashPreviousMonthBalance","0.10"],["cashLoanMonth","0.01"],["cashLoanYear","0.02"],["cashLoanTotal","0.03"]])assert.equal(field(id).textContent,value,`server-authoritative ${id}`);
  assert.throws(()=>Exact.decimal("0.1")+Exact.decimal("0.2"),/禁止/);
}
checkCashEditingAndRendering().then(()=>console.log("Oct30LingChen cash/history/cache/forecast regression checks passed.")).catch(error=>{console.error(error);process.exitCode=1;});
