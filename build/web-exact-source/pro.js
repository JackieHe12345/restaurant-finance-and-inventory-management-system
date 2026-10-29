"use strict";

const PRO_UNITS_DEFAULT=["斤","公斤","个","袋","打","盒","两","克","千克","瓶","箱","只","条","份","件","颗","根","把","扎","碗","盘","升","ml","L","kg","KG","g","mL","毫升","斤两"];
const PRO_FIXED_NAMES=["米饭","汤","小菜","青菜"];
let proPickerCallback=null;
let proSelectedPurchase=[];
let proSelectedConsumption=[];
let proLastStatsExport={headers:[],rows:[]};

function proUnits(){try{return [...new Set([...PRO_UNITS_DEFAULT,...JSON.parse(localStorage.getItem("restaurant_web_units")||"[]")])];}catch(_){return [...PRO_UNITS_DEFAULT];}}
function proDateToolbar(id,label="选择日期"){return `<div class="pro-toolbar"><strong>${label}：</strong><button class="pro-button" data-date-shift="${id}" data-shift="-1">◀ 前一天</button><input id="${id}" type="date"><button class="pro-button" data-date-shift="${id}" data-shift="1">后一天 ▶</button><button class="pro-button" data-date-today="${id}">今天</button><span class="grow"></span></div>`;}
function proUnitOptions(value=""){return [...new Set(["",...proUnits(),value].filter(item=>item!==undefined&&item!==null))].map(item=>`<option ${item===value?"selected":""}>${escapeHtml(item)}</option>`).join("");}
function proShiftDate(id,amount){const node=$(id);if(!node?.value)return;const date=parseDate(node.value);date.setDate(date.getDate()+amount);node.value=isoDate(date);node.dispatchEvent(new Event("change"));}
function proInstallDateButtons(root=document){root.querySelectorAll("[data-date-shift]").forEach(button=>button.addEventListener("click",()=>proShiftDate(button.dataset.dateShift,Number(button.dataset.shift))));root.querySelectorAll("[data-date-today]").forEach(button=>button.addEventListener("click",()=>{const node=$(button.dataset.dateToday);node.value=isoDate(new Date());node.dispatchEvent(new Event("change"));}));}

function installProUI(){
  $("pageLedger").innerHTML=`
    <section class="section-heading ledger-section-heading"><div><h1 data-zh="记账本" data-en="Daily ledger">记账本</h1><p data-zh="录入日收入、客数和采购支出，查看固定成本与历史记录。" data-en="Daily income, customers, purchases and fixed costs.">录入日收入、客数和采购支出，查看固定成本与历史记录。</p></div><span id="ledgerPermission" class="permission-pill"></span></section>
    ${proDateToolbar("ledgerDate")}
    <aside id="entryTimingNotice" class="entry-timing-notice hidden" role="status" aria-live="polite"></aside>
    <section class="desktop-panel ledger-daily-panel"><header class="panel-heading"><h2>当日流水</h2><span>金额单位：元</span></header><div class="desktop-panel-body">
      <div class="ledger-summary-fields"><label>营业收入<input id="ledgerRevenue" type="number" step="0.01" readonly></label><label>现金合计<input id="ledgerTotalCash" type="number" step="0.01" readonly></label><label>线上合计<input id="ledgerTotalOnline" type="number" step="0.01" readonly></label><label>手续费／抽成<input id="ledgerFees" type="number" step="0.01" placeholder="0.00"></label></div><input id="ledgerAvailableBalance" type="hidden"><input id="ledgerShareholderLoan" type="hidden">
      <fieldset class="ledger-block"><legend>收入明细</legend><div class="ledger-income-grid"><section class="store-revenue-column"><h3>A店</h3><label>A店微信<input id="ledgerAWechatOverride" type="number" step="0.01"></label><label>A店支付宝<input id="ledgerAAlipayOverride" type="number" step="0.01"></label><label>A店现金<input id="ledgerACash" type="number" step="0.01"></label><input id="ledgerAWechatAdd" type="hidden"><input id="ledgerAAlipayAdd" type="hidden"><input id="ledgerARevenue" type="hidden"></section><section class="store-revenue-column"><h3>B店</h3><label>B店微信<input id="ledgerBWechatOverride" type="number" step="0.01"></label><label>B店支付宝<input id="ledgerBAlipayOverride" type="number" step="0.01"></label><label>B店现金<input id="ledgerBCash" type="number" step="0.01"></label><input id="ledgerBWechatAdd" type="hidden"><input id="ledgerBAlipayAdd" type="hidden"><input id="ledgerBRevenue" type="hidden"></section><section class="store-revenue-column"><h3>外卖</h3><label>学生外卖<input id="ledgerStudentTakeout" type="number" step="0.01"></label><label>A店外卖<input id="ledgerATakeout" type="number" step="0.01"></label><label>B店外卖<input id="ledgerBTakeout" type="number" step="0.01"></label></section></div><p class="field-help">各渠道收入自动合计；食材与固定成本按当前账本统一核算。</p></fieldset>
      <div class="ledger-customer-fields"><label data-label-zh="新客人数" data-label-en="New customers">新客人数<input id="ledgerNewCustomers" type="number" step="1" min="0"></label><label data-label-zh="总客人数" data-label-en="Total customers">总客人数<input id="ledgerCustomers" type="number" step="1" min="0"></label><label class="grow" data-label-zh="当日备注" data-label-en="Daily note">当日备注<input id="ledgerNote"></label></div>
      <fieldset class="ledger-block ledger-purchase-block"><legend>采购与其他支出</legend><div class="ledger-detail-fields"><label for="ledgerFoodDetail">食材明细及金额</label><div class="full-field"><small id="ledgerFoodSaved" class="entry-saved-detail hidden"></small><input id="ledgerFoodDetail"><button id="ledgerPickFood" class="soft edit-action">选择食材</button></div><label for="ledgerSpiceDetail">佐料明细及金额</label><div class="full-field"><small id="ledgerSpiceSaved" class="entry-saved-detail hidden"></small><input id="ledgerSpiceDetail"><button id="ledgerPickSpice" class="soft edit-action">选择佐料</button></div><label for="ledgerOtherDetail">其他明细及金额</label><div class="full-field"><small id="ledgerOtherSaved" class="entry-saved-detail hidden"></small><input id="ledgerOtherDetail"></div></div><input id="ledgerFoodCost" type="hidden"><input id="ledgerSpiceCost" type="hidden"><input id="ledgerUtilities" type="hidden"><input id="ledgerOther" type="hidden"></fieldset>
      <footer class="ledger-actions"><span id="ledgerResult" role="status"></span><span class="grow"></span><button id="undoLedgerButton" class="soft">撤销未保存修改</button><button id="saveLedgerButton" class="primary edit-action">保存当日记录</button></footer>
    </div></section>
    <section class="desktop-panel ledger-fixed-panel"><header class="panel-heading"><h2 data-zh="月度固定成本" data-en="Monthly fixed costs">月度固定成本</h2><div class="inline-actions"><input id="fixedMonth" type="month"><button id="openFixedExpenses" class="soft edit-action">逐笔固定支出</button></div></header><div class="desktop-panel-body"><div class="fixed-fields"><label>本月房租及物业合计<input id="fixedRent" readonly></label><label>房租／物业备注<input id="fixedNote" readonly></label><label>实际使用水费<input id="fixedActualWater" type="number" step="0.01" placeholder="留空按预计／支出"></label><label>预计水费<input id="fixedExpectedWater" type="number" step="0.01"></label><label>实际使用电费<input id="fixedActualElectric" type="number" step="0.01" placeholder="留空按预计／支出"></label><label>预计电费<input id="fixedExpectedElectric" type="number" step="0.01"></label><label>预计煤气费<input id="fixedExpectedGas" type="number" step="0.01"></label></div><input id="fixedLabour" type="hidden"><input id="fixedWaterSpent" type="hidden"><input id="fixedElectricSpent" type="hidden"><input id="fixedGas" type="hidden"><input id="fixedOther" type="hidden"><div id="fixedSummary" class="fixed-summary"></div><footer class="ledger-actions"><span id="fixedResult"></span><span class="grow"></span><button id="saveFixedButton" class="primary edit-action">保存水电煤气费</button></footer></div></section>
    <section class="table-card history-card"><header class="card-title"><div><h2 data-zh="历史记录" data-en="History">历史记录</h2><small data-zh="双击记录可回填编辑" data-en="Double-click a row to edit">双击记录可回填编辑</small></div><input id="historyMonth" type="month"></header><div class="table-scroll tall-table"><table><thead><tr><th>日期</th><th>收入</th><th>新客</th><th>总客数</th><th>食材总价格</th><th>佐料明细</th><th>当日固定成本</th><th>其他明细</th><th>备注</th><th>毛利润（毛利率）</th><th>净利润（净利率）</th></tr></thead><tbody id="historyRows"></tbody></table></div></section>
`;

  $("pageDishes").innerHTML=`<section class="section-heading"><div><h1 data-zh="当日做出的菜品" data-en="Dishes prepared today">当日做出的菜品</h1><p data-zh="普通菜品、四项固定项目以及食材用量自动汇总。" data-en="Dishes, four fixed items and automatic ingredient totals.">普通菜品、四项固定项目以及食材用量自动汇总。</p></div></section>${proDateToolbar("dishDate")}
    <div class="pro-toolbar"><button id="undoDishesButton" class="pro-button">↩ 撤销未保存修改</button><span class="grow"></span><button id="saveDishesButton" class="pro-button green edit-action"> 保存修改</button><span id="dishResult"></span></div>
    <section class="dish-sections"><article class="desktop-panel"><h2>菜品用量</h2><div class="desktop-panel-body"><div class="desktop-table-wrap"><table class="desktop-table"><thead><tr><th>菜品名称</th><th class="number-col">菜品份数</th><th>使用食材明细</th><th class="number-col">食材成本（元）</th><th>备注</th><th class="action-col">操作</th></tr></thead><tbody id="dishRows"></tbody></table></div><div class="status-line"><div><button id="addDishButton" class="pro-button edit-action">＋ 新增菜品</button> <button id="deleteDishButton" class="pro-button red edit-action"> 删除选中菜品</button> <label>总备注：<input id="dishDayNote"></label></div><span id="dishTotal" class="total"></span></div></div></article>
    <article class="desktop-panel"><h2>固定项目（米饭／汤／小菜／青菜）</h2><div class="desktop-panel-body"><div class="desktop-table-wrap" style="min-height:250px"><table class="desktop-table"><thead><tr><th>固定项目</th><th>菜品份数</th><th>使用食材明细</th><th>食材成本（元）</th><th>备注</th><th>操作</th></tr></thead><tbody id="fixedDishRows"></tbody></table></div></div></article>
    <article class="desktop-panel"><h2>食材消耗汇总</h2><div class="desktop-panel-body"><div class="desktop-table-wrap dish-summary-table"><table class="desktop-table"><thead><tr><th>食材名称</th><th>总使用量</th><th>单位</th><th>总成本（元）</th><th>使用于</th></tr></thead><tbody id="dishIngredientSummary"></tbody></table></div><p class="muted">食材用量会根据上面两部分所选食材自动汇总；不同单位分别统计。</p></div></article></section>`;

  for(const kind of ["Food","Spice"]){const lower=kind.toLowerCase(),zh=kind==="Food"?"食材":"佐料",icon=kind==="Food"?"":"";$("page"+kind).innerHTML=`<section class="section-heading"><div><h1>${icon} ${zh}明细</h1><p>按天编辑数量、单位、单价、总价和备注；支持批量移动和单位管理。</p></div></section>${proDateToolbar(lower+"Date")}<div class="pro-toolbar"><button data-manage-units class="pro-button"> 管理单位</button><button data-undo-detail="${lower}" class="pro-button">↩ 撤销未保存修改</button><span class="grow"></span><button id="save${kind}Button" class="pro-button green edit-action"> 保存修改</button></div><section class="desktop-panel"><div class="desktop-panel-body"><div class="desktop-table-wrap"><table class="desktop-table"><thead><tr><th class="check-col"></th><th>${zh}名称</th><th>数量</th><th>单位</th><th>单价（元）</th><th>总价（元）</th><th>备注</th></tr></thead><tbody id="${lower}Rows"></tbody></table></div><div class="status-line"><div><button id="add${kind}RowButton" class="pro-button edit-action">＋ 新增空行</button> <button data-delete-detail="${lower}" class="pro-button red edit-action"> 删除选中行</button> <button data-move-detail="${lower}" class="pro-button edit-action">移动至${kind==="Food"?"佐料":"食材"}</button></div><div><strong id="${lower}Total"></strong> <span id="${lower}Result"></span></div></div></div></section>`;}

  $("pageStats").innerHTML=`<section class="section-heading"><div><h1 data-zh="更多统计" data-en="Advanced analytics">更多统计</h1><p data-zh="按照主程序的月份、星期、经营指标、食材采购和食材消耗进行筛选。" data-en="Filter by month, weekday, metric, purchasing and consumption.">按照主程序的月份、星期、经营指标、食材采购和食材消耗进行筛选。</p></div></section><section class="analytics-controls">
    <div class="stats-command-bar"><strong>统计方式：</strong><label><input id="statsDetail" name="statsMode" type="radio" checked> 明细</label><label><input id="statsAverage" name="statsMode" type="radio"> 平均</label><span class="separator"></span><strong>年份：</strong><select id="statsYear"></select><button id="statsPreviousYear" class="pro-button">上一年</button><button id="statsThisYear" class="pro-button">今年</button><button id="statsNextYear" class="pro-button">下一年</button><button id="statsExport" class="pro-button orange">导出当前筛选 CSV</button></div>
    <div class="stats-command-bar" id="statsMonthChecks"><strong>月份：</strong></div><div class="stats-command-bar" id="statsWeekdayChecks"><strong>星期：</strong></div>
    <fieldset class="stats-group"><legend>经营指标</legend><div id="statsMetricChecks" class="stats-metric-grid"></div><div class="stats-command-bar"><span class="grow"></span><button data-stats-metrics="all" class="pro-button">全选</button><button data-stats-metrics="none" class="pro-button">全不选</button></div></fieldset>
    <details class="stats-group stats-disclosure"><summary>食材采购分析</summary><div class="stats-subfilter"><strong>食材指标：</strong><select id="purchaseMetric"><option value="unit">单价随时间变化</option><option value="monthlyTotal">每月采购总价</option><option value="monthlyQuantity">每月采购量</option><option value="monthlyAverageUnit">每月平均单价</option></select><button id="purchaseIngredients" class="pro-button">选择食材（不选则看经营指标）</button><button id="clearPurchaseIngredients" class="pro-button">清空食材</button><small>不选食材时显示经营指标；选了食材后自动切换为食材分析。同一食材不同单位会分开统计。</small></div></details>
    <details class="stats-group stats-disclosure"><summary>食材消耗分析</summary><div class="stats-subfilter"><strong>消耗指标：</strong><select id="consumptionMetric"><option value="daily">每日消耗量变化</option><option value="monthlyTotal">每月消耗总量</option><option value="monthlyAverage">每月日均消耗量</option><option value="cumulative">累计消耗量</option></select><button id="consumptionIngredients" class="pro-button">选择消耗食材（未选择）</button><button id="clearConsumptionIngredients" class="pro-button">清空消耗食材</button><small>按菜品中填写的实际总用量统计，不再乘菜品份数；不同单位分开统计。</small></div></details>
    <div class="stats-command-bar"><strong>显示内容：</strong><label><input class="stats-view-check" value="trend" type="checkbox" checked> 趋势图</label><label><input class="stats-view-check" value="monthly" type="checkbox" checked> 月度／食材对比图</label><label><input class="stats-view-check" value="weekday" type="checkbox" checked> 星期图</label><label><input class="stats-view-check" value="table" type="checkbox" checked> 数据表</label><button data-stats-views="all" class="pro-button">全选</button><button data-stats-views="none" class="pro-button">全不选</button><button data-stats-views="table" class="pro-button">只看表格</button></div></section>
    <div id="statsForecastBanner" class="stats-forecast-banner"></div>
    <section class="analytics-grid pro-analytics"><article id="statsTrendCard" class="chart-card analytics-card"><header><h2 id="statsTrendTitle">所选日期明细趋势</h2><button class="chart-expand-button" type="button" data-expand-chart> 放大</button></header><div class="interactive-chart-shell"><div id="statsChart" class="svg-chart interactive-chart analytics-chart"></div><div class="chart-hint">悬停或点按查看数值；可左右拖动</div></div></article><article id="statsMonthlyCard" class="chart-card analytics-card"><header><h2 id="statsMonthlyTitle">月度对比</h2><button class="chart-expand-button" type="button" data-expand-chart> 放大</button></header><div class="chart-scroll-shell"><div id="statsMonthlyChart" class="interactive-bars"></div></div><div class="chart-hint">全年 12 个月；悬停或点按查看明细</div></article><article id="statsWeekdayCard" class="chart-card analytics-card span-all"><header><h2 id="statsWeekdayTitle">星期分布</h2><button class="chart-expand-button" type="button" data-expand-chart> 放大</button></header><div class="chart-scroll-shell"><div id="statsWeekdayChart" class="bar-chart wide-bars"></div></div><div class="chart-hint">悬停或点按查看数值</div></article></section><section id="statsTableCard" class="table-card"><div class="stats-table-wrap"><table><thead id="statsHead"></thead><tbody id="statsRows"></tbody></table></div></section>`;

  $("pageStats").insertAdjacentHTML("beforeend",`<section id="inventoryStatsCard" class="table-card inventory-stats-card"><header class="card-title"><div><h2 data-zh="食材当前剩余量" data-en="Current Ingredient Balance">食材当前剩余量</h2><small data-zh="累计入库减去菜品实际消耗、正常消耗和损耗；不同单位分开统计" data-en="Received minus dish usage, normal usage and loss">累计入库减去菜品实际消耗、正常消耗和损耗；不同单位分开统计</small></div><span id="inventoryStatsUpdated"></span></header><div class="table-scroll"><table><thead><tr><th>分类</th><th>名称</th><th>单位</th><th>累计入库</th><th>菜品消耗</th><th>正常消耗</th><th>损耗</th><th>当前剩余</th><th>库存状态</th><th>最近入库</th></tr></thead><tbody id="inventoryStatsRows"></tbody></table></div></section>`);

  /* Cash is the standalone page installed by sep04.js. Do not briefly mount
     the obsolete dashboard editor with its opening-balance overwrite UI. */
  document.body.insertAdjacentHTML("beforeend",`<div id="proModalHost"></div>`);
  bindProUI();
}

function canManageCashPosition(){return ["admin","editor"].includes(currentRole()) && !isTestAccount();}
/* Desktop builds use the global/cash_position identity and the
   base_balance/as_of_date field names.  Earlier web builds used
   global/cash_balance with opening_balance/opening_date.  Read both forms,
   preferring the desktop identity, so either client can continue a balance
   record created by the other one. */
function cashPositionRecord(){return currentRecord("global","cash_position")||currentRecord("global","cash_balance");}
function cashPositionPayload(){
  const record=state.cashPosition?.record||cashPositionRecord();
  if(!record)return {};
  const payload=clone(unpackPayload(record));
  if(!entered(payload.opening_balance)&&entered(payload.base_balance))payload.opening_balance=payload.base_balance;
  if(!payload.opening_date&&payload.as_of_date)payload.opening_date=payload.as_of_date;
  return payload;
}
function cashOpeningValue(payload){return entered(payload.opening_balance)?num(payload.opening_balance):0;}
function cashOpeningDate(payload){const value=normalizeDateKey(payload.opening_date||"");return isCanonicalDate(value)?value:"0000-01-01";}
function fixedExpenseCountsForCash(row){
  const isEnabled=value=>!(value===false||value===0||["false","0","no","否"].includes(String(value).toLowerCase()));
  if(Object.prototype.hasOwnProperty.call(row||{},"计入可用余额"))return isEnabled(row.计入可用余额);
  if(Object.prototype.hasOwnProperty.call(row||{},"include_cash_balance"))return isEnabled(row.include_cash_balance);
  // Rows created before the checkbox existed remain included by default.
  return true;
}
function cashFlowSummary(payload){
  const start=cashOpeningDate(payload),today=isoDate(new Date()),metrics=dataDayMetrics().filter(item=>item.date>start&&item.date<=today);
  const income=metrics.reduce((sum,item)=>sum+num(item.revenue),0);
  /* Daily ledger costs and receiving purchases are both real cash outflows
     in the desktop client.  Keep the same convention in the web summary. */
  const ledgerExpenses=metrics.reduce((sum,item)=>sum+num(item.food)+num(item.spice)+num(item.waterDaily)+num(item.other)+num(item.fees),0);
  const inventoryExpenses=typeof inventoryEntries==="function"?inventoryEntries().filter(item=>item.date>start&&item.date<=today).reduce((sum,item)=>sum+num(entered(item.total)?item.total:item.quantity*item.unitPrice),0):0;
  const operatingExpenses=ledgerExpenses+inventoryExpenses;
  let fixedExpenses=0;
  const monthsWithDailyFixed=new Set();
  for(const row of state.records||[]){
    if(String(row.record_type||row.type)!=="day")continue;
    const dayPayloadValue=unpackPayload(row),expenses=Array.isArray(dayPayloadValue.fixed_expenses)?dayPayloadValue.fixed_expenses:[];
    for(const expense of expenses){const date=normalizeDateKey(expense?.日期||row.record_key||"");if(isCanonicalDate(date))monthsWithDailyFixed.add(date.slice(0,7));if(date>start&&date<=today&&fixedExpenseCountsForCash(expense))fixedExpenses+=num(expense.金额);}
  }
  /* Older web records only have monthly_fixed totals.  Treat the first day of
     each such month as its payment date, matching the desktop migration, but
     never add a monthly total on top of an already itemized month. */
  if(state.months instanceof Map){
    for(const month of state.months.keys()){
      const monthKey=normalizeMonthKey(month),date=`${monthKey}-01`;
      if(!/^\d{4}-\d{2}$/.test(monthKey)||monthsWithDailyFixed.has(monthKey)||date<=start||date>today)continue;
      const year=Number(monthKey.slice(0,4)),monthNumber=Number(monthKey.slice(5,7));
      fixedExpenses+=num(fixedBreakdown(year,monthNumber).spentTotal);
    }
  }
  const shareholderLoan=num(payload?.shareholder_loan);
  return {income,operatingExpenses,inventoryExpenses,fixedExpenses,totalExpenses:operatingExpenses+fixedExpenses,current:cashOpeningValue(payload)+shareholderLoan+income-operatingExpenses-fixedExpenses,days:metrics.length};
}
function cashFlowFromServer(payload){
  const server=state.cashPosition;
  if(!server||typeof server!=="object")return null;
  return {
    income:num(server.income),
    operatingExpenses:num(server.daily_expenses)+num(server.inventory_expenses),
    inventoryExpenses:num(server.inventory_expenses),
    fixedExpenses:num(server.fixed_expenses),
    totalExpenses:num(server.total_expenses),
    current:num(server.current_balance),
    days:num(server.days),
  };
}
function installCashPositionModule(){
  const overview=$("pageOverview");if(!overview||$("cashPositionCard"))return;
  overview.insertAdjacentHTML("afterbegin",`<section id="cashPositionCard" class="cash-position-module editor-only-position hidden"><header class="cash-position-header"><div><h2 data-zh="可用余额与向股东借款" data-en="Available Balance & Shareholder Loan">可用余额与向股东借款</h2><p data-zh="收入自动增加；食材、佐料、其它、手续费及勾选纳入余额的固定支出自动扣除。" data-en="Income is added automatically; ingredients, seasonings, other costs, fees and selected fixed expenses are deducted.">收入自动增加；食材、佐料、其它、手续费及勾选纳入余额的固定支出自动扣除。</p></div><div class="cash-position-readouts"><div><small data-zh="当前可用余额" data-en="Available balance">当前可用余额</small><strong id="cashComputedBalance">0.00 元</strong></div><div><small data-zh="向股东借款" data-en="Shareholder loan">向股东借款</small><strong id="cashShareholderLoanReadout">0.00 元</strong></div></div></header><div class="cash-position-body"><div class="cash-position-flow"><div><span data-zh="期初手动余额" data-en="Opening balance">期初手动余额</span><strong id="cashOpeningReadout">0.00 元</strong></div><div><span data-zh="累计收入" data-en="Cumulative income">累计收入</span><strong id="cashIncomeReadout">0.00 元</strong></div><div><span data-zh="累计扣除" data-en="Cumulative deductions">累计扣除</span><strong id="cashExpensesReadout">0.00 元</strong></div><div><span data-zh="纳入计算天数" data-en="Days included">纳入计算天数</span><strong id="cashDaysReadout">0</strong></div></div><div class="cash-position-form"><label><span data-zh="手动设置期初余额" data-en="Set opening balance">手动设置期初余额</span><input id="cashOpeningBalance" type="number" step="0.01" placeholder="0.00"></label><label><span data-zh="余额起算日期" data-en="Opening date">余额起算日期</span><input id="cashOpeningDate" type="date"></label><label><span data-zh="向股东借款" data-en="Shareholder loan">向股东借款</span><input id="cashShareholderLoan" type="number" step="0.01" placeholder="0.00"></label><button id="saveCashPosition" class="pro-button green edit-action" type="button" data-zh="保存余额设置" data-en="Save balance settings">保存余额设置</button><span id="cashPositionResult" class="operation-result" role="status"></span></div></div></section>`);
}
function renderCashPosition(){
  const card=$("cashPositionCard");if(!card)return;
  const visible=canManageCashPosition();card.classList.toggle("hidden",!visible);if(!visible)return;
  const payload=cashPositionPayload(),flow=cashFlowFromServer(payload)||cashFlowSummary(payload),loan=entered(payload.shareholder_loan)?num(payload.shareholder_loan):0;
  $("cashComputedBalance").textContent=money(flow.current);$("cashComputedBalance").classList.toggle("negative",flow.current<0);$("cashOpeningReadout").textContent=money(cashOpeningValue(payload));$("cashIncomeReadout").textContent=money(flow.income);$("cashExpensesReadout").textContent=money(flow.totalExpenses);$("cashDaysReadout").textContent=compactNumber(flow.days);$("cashShareholderLoanReadout").textContent=money(loan);
  const opening=$("cashOpeningBalance"),date=$("cashOpeningDate"),loanInput=$("cashShareholderLoan"),draftDirty=card.dataset.dirty==="1";if(!draftDirty){if(opening&&document.activeElement!==opening)opening.value=entered(payload.opening_balance)?num(payload.opening_balance).toFixed(2):"";if(date&&document.activeElement!==date)date.value=isCanonicalDate(normalizeDateKey(payload.opening_date||""))?normalizeDateKey(payload.opening_date):isoDate(new Date());if(loanInput&&document.activeElement!==loanInput)loanInput.value=entered(payload.shareholder_loan)?num(payload.shareholder_loan).toFixed(2):"";}
}
async function saveCashPosition(){
  if(!canManageCashPosition())throw new Error("当前账号没有修改余额的权限。");
  const payload=cashPositionPayload();
  payload.opening_balance=blankValue("cashOpeningBalance",true);
  payload.opening_date=normalizeDateKey($("cashOpeningDate").value)||isoDate(new Date());
  payload.shareholder_loan=blankValue("cashShareholderLoan",true);
  if(num(payload.opening_balance)<0||num(payload.shareholder_loan)<0)throw new Error("目前余额和向股东借款不能为负数。");
  /* Keep aliases in the same payload for the desktop synchronizer. */
  payload.base_balance=payload.opening_balance;
  payload.as_of_date=payload.opening_date;
  payload.updated_at=new Date().toISOString();
  await saveRecord("global","cash_position",payload,"cashPositionResult");state.cashPosition=null;$("cashPositionCard").dataset.dirty="";renderCashPosition();
}

let entryTimingTimer=null;
const ENTRY_INCOME_UI={
  a_wechat:{input:"ledgerAWechatOverride",field:"A店微信覆盖",label:()=>`${storeName("A")}微信`},
  a_alipay:{input:"ledgerAAlipayOverride",field:"A店支付宝覆盖",label:()=>`${storeName("A")}支付宝`},
  a_cash:{input:"ledgerACash",field:"A店现金",label:()=>`${storeName("A")}现金`},
  b_wechat:{input:"ledgerBWechatOverride",field:"B店微信覆盖",label:()=>`${storeName("B")}微信`},
  b_alipay:{input:"ledgerBAlipayOverride",field:"B店支付宝覆盖",label:()=>`${storeName("B")}支付宝`},
  b_cash:{input:"ledgerBCash",field:"B店现金",label:()=>`${storeName("B")}现金`},
  student_takeout:{input:"ledgerStudentTakeout",field:"学生外卖",label:()=>"学生外卖"},
  a_takeout:{input:"ledgerATakeout",field:"A店外卖",label:()=>`${storeName("A")}外卖`},
  b_takeout:{input:"ledgerBTakeout",field:"B店外卖",label:()=>`${storeName("B")}外卖`},
};
const ENTRY_DETAIL_UI={food:{input:"ledgerFoodDetail",saved:"ledgerFoodSaved",field:"食材明细",picker:"ledgerPickFood",label:"食材"},spice:{input:"ledgerSpiceDetail",saved:"ledgerSpiceSaved",field:"佐料明细",picker:"ledgerPickSpice",label:"佐料"},other:{input:"ledgerOtherDetail",saved:"ledgerOtherSaved",field:"其他明细",label:"其它"}};
function entryLocalRevenueDeadline(key){
  const normalized=normalizeDateKey(key),parts=normalized.split("-").map(Number);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(normalized)||parts.length!==3||parts.some(value=>!Number.isFinite(value)))return "";
  return new Date(parts[0],parts[1]-1,parts[2]+1,11,0,0,0).toISOString();
}
function entryTimingWindowForDate(){
  if(currentRole()!=="entry")return null;
  const key=$("ledgerDate")?.value||$("selectedDate")?.value||"";
  if(!key)return null;
  const normalized=normalizeDateKey(key),found=(state.entryWindows||[]).find(item=>item.record_type==="day"&&normalizeDateKey(item.record_key||"")===normalized)||null,entryDeadline=entryLocalRevenueDeadline(normalized),incomeFields={};
  for(const incomeKey of Object.keys(ENTRY_INCOME_UI)){
    const provided=Boolean(found?.income_fields&&Object.prototype.hasOwnProperty.call(found.income_fields,incomeKey)),current=provided?found.income_fields[incomeKey]:{};
    incomeFields[incomeKey]={...(current||{}),entry_deadline:current?.entry_deadline||entryDeadline,_server_provided:provided};
  }
  return {...(found||{}),record_type:"day",record_key:normalized,income_fields:incomeFields,detail_deadlines:found?.detail_deadlines||{},detail_items:Array.isArray(found?.detail_items)?found.detail_items:[]};
}
function entryTimingText(deadline,now=Date.now()){
  const stamp=Date.parse(deadline||"");
  if(!Number.isFinite(stamp))return "";
  const diff=stamp-now;
  if(diff<=0)return state.language==="en"?"expired":"已截止";
  const total=Math.floor(diff/1000),hours=Math.floor(total/3600),minutes=Math.floor(total%3600/60),seconds=total%60;
  const clock=`${String(hours).padStart(2,"0")}:${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}`;
  return state.language==="en"?`${clock} remaining`:`剩余 ${clock}`;
}
function entryDeadlineOpen(deadline,now=Date.now()){
  const stamp=Date.parse(deadline||"");
  return Number.isFinite(stamp)&&now<stamp;
}
function entryIncomeStates(window,now=Date.now()){
  const incomeFields=window?.income_fields||{},recordKey=window?.record_key||$("ledgerDate")?.value||"",row=recordKey?dailyRow(dayPayload(recordKey),recordKey):{};
  return Object.entries(ENTRY_INCOME_UI).map(([key,config])=>{
    const info=incomeFields[key]||{},input=$(config.input),savedField=String(info.field||config.field),legacySaved=entered(row?.[savedField]),saved=info._server_provided?Boolean(info.saved_at||info.edit_deadline):legacySaved,deadline=saved?info.edit_deadline:(info.entry_deadline||entryLocalRevenueDeadline(window?.record_key||"")),validDeadline=Number.isFinite(Date.parse(deadline||"")),editable=saved?(validDeadline&&entryDeadlineOpen(deadline,now)):(!validDeadline||entryDeadlineOpen(deadline,now)),label=String(info.label||config.label());
    if(input){input.disabled=!editable;input.dataset.entryTimingLocked=editable?"":"1";input.title=editable?(saved?"首次保存后 30 分钟内可修改":"最晚可在第二天 11:00 前首次录入"):(saved?"保存已超过 30 分钟，录入账号不可修改":"首次录入时间已截止");}
    return {key,label,saved,deadline,editable};
  });
}
function renderEntryTiming(){
  const notice=$("entryTimingNotice");
  if(!notice)return;
  const visible=currentRole()==="entry",window=entryTimingWindowForDate();
  notice.classList.toggle("hidden",!visible||!window);
  if(!visible||!window){notice.textContent="";for(const config of Object.values(ENTRY_INCOME_UI)){const input=$(config.input);if(input){input.disabled=false;delete input.dataset.entryTimingLocked;input.title="";}}for(const config of Object.values(ENTRY_DETAIL_UI)){const input=$(config.input),picker=config.picker?$(config.picker):null,savedNode=$(config.saved);if(input)input.disabled=false;if(picker)picker.disabled=false;if(savedNode)savedNode.classList.add("hidden");}return;}
  const now=Date.now(),incomeStates=entryIncomeStates(window,now),detailParts=[],categoryParts=[];
  const detailDeadlines=window.detail_deadlines||{};
  for(const [category,config] of Object.entries(ENTRY_DETAIL_UI)){
    const deadline=detailDeadlines[category]||"",hasDeadline=Number.isFinite(Date.parse(deadline));
    categoryParts.push(`<span class="entry-timing-row ${hasDeadline&&!entryDeadlineOpen(deadline,now)?"is-locked":"is-open"}"><b>${escapeHtml(config.label)}新增</b><em>${hasDeadline?escapeHtml(entryTimingText(deadline,now)):"首次保存后开始 12 小时"}</em></span>`);
  }
  for(const item of (window.detail_items||[])){
    const category=ENTRY_DETAIL_UI[item?.category],deadline=item?.edit_deadline||"",open=entryDeadlineOpen(deadline,now),label=String(item?.label||category?.label||"明细");
    detailParts.push(`<span class="entry-timing-row ${open?"is-open":"is-locked"}" title="${escapeHtml(label)}"><b>${escapeHtml(label)}</b><em>${open?escapeHtml(entryTimingText(deadline,now)):"已锁"}</em></span>`);
  }
  const incomeParts=incomeStates.map(item=>`<span class="entry-timing-row ${item.editable?"is-open":"is-locked"}"><b>${escapeHtml(item.label)}</b><em>${item.editable?`${item.saved?"修改":"首次录入"} · ${escapeHtml(entryTimingText(item.deadline,now))}`:(item.saved?"已锁":"未录入 · 已截止")}</em></span>`).join("");
  notice.innerHTML=`<header><strong>录入倒计时</strong><small>9 项收入、食材、佐料、其它分别计时；每条已保存明细的 30 分钟修改时间也独立</small></header><div class="entry-timing-groups"><section><h3>9 项收入</h3><div class="entry-timing-grid income-timing-grid">${incomeParts}</div></section><section><h3>当日明细新增（分类独立）</h3><div class="entry-timing-grid">${categoryParts.join("")}</div></section>${detailParts.length?`<section><h3>已保存明细修改</h3><div class="entry-timing-grid detail-item-timing-grid">${detailParts.join("")}</div></section>`:""}</div>`;
  configureEntryDetailInputs($("ledgerDate")?.value||"",true);
}
function renderLedgerDetailSummaries(){
  for(const id of ["ledgerFoodDetail","ledgerSpiceDetail"]){
    const input=$(id);if(!input)continue;let rows=null;
    try{const parsed=JSON.parse(input.value);if(Array.isArray(parsed)&&parsed.every(item=>item&&typeof item==="object"&&!Array.isArray(item)))rows=parsed;}catch(_){}
    let summary=$(id+"Summary");
    if(!summary){summary=document.createElement("div");summary.id=id+"Summary";summary.className="ledger-detail-summary";summary.setAttribute("role","textbox");summary.setAttribute("aria-readonly","true");summary.setAttribute("aria-label",id==="ledgerFoodDetail"?"已保存食材明细":"已保存佐料明细");input.insertAdjacentElement("afterend",summary);}
    input.type=rows?"hidden":"text";summary.hidden=!rows;
    if(rows){const items=parseDetailItems(rows);summary.textContent=items.length?items.map(item=>`${item.name}${entered(item.quantity)?` ${compactDecimal(item.quantity)}${item.unit||""}`:""}${entered(item.total)?` · ${compactDecimal(item.total)} 元`:""}${item.note?`（${item.note}）`:""}`).join("； "):"暂无采购明细";summary.title="通过右侧选择按钮查看或编辑明细";}
  }
}
function configureEntryDetailInputs(key,keepText=false){
  if(!key)return;
  const entry=currentRole()==="entry",row=dailyRow(dayPayload(key),key),window=entryTimingWindowForDate(),deadlines=window?.detail_deadlines||{};
  for(const [category,config] of Object.entries(ENTRY_DETAIL_UI)){
    const input=$(config.input),savedNode=$(config.saved),picker=config.picker?$(config.picker):null;if(!input)continue;
    const savedValue=row?.[config.field]??(category==="other"?row?.其它明细:"")??"",saved=Array.isArray(savedValue)?JSON.stringify(savedValue):String(savedValue).trim();
    if(!entry){input.dataset.savedValue="";input.dataset.entryKey="";input.disabled=false;if(savedNode)savedNode.classList.add("hidden");if(picker)picker.disabled=false;continue;}
    input.dataset.entryKey=key;input.dataset.savedValue=saved;
    if(!keepText&&!readEditorDraft("ledger",key)&&String(input.value||"").trim()!==saved)input.value=saved;
    if(savedNode){savedNode.textContent=saved?"已保存明细完整保留；各条修改与新增时限见上方。":`尚未保存；第一条${config.label}成功保存后，只启动${config.label}自己的 12 小时新增窗口。`;savedNode.classList.remove("hidden");}
    const deadline=deadlines[category]||"",hasCategoryDeadline=Number.isFinite(Date.parse(deadline)),additionOpen=!hasCategoryDeadline||entryDeadlineOpen(deadline),itemEditOpen=(window?.detail_items||[]).some(item=>item?.category===category&&entryDeadlineOpen(item?.edit_deadline)),editable=additionOpen||itemEditOpen;
    input.disabled=!editable;
    input.placeholder=!editable?"新增和修改时间均已截止":additionOpen?"可修改仍在 30 分钟内的条目，或继续新增":"只能修改右上角仍在 30 分钟内的已保存条目";
    if(picker)picker.disabled=!editable;
  }
  renderLedgerDetailSummaries();
}
function startEntryTimingTicker(){
  if(entryTimingTimer)clearInterval(entryTimingTimer);
  entryTimingTimer=null;
  renderEntryTiming();
  if(currentRole()==="entry")entryTimingTimer=setInterval(()=>renderEntryTiming(),1000);
}
function stopEntryTimingTicker(){
  if(!entryTimingTimer)return;
  clearInterval(entryTimingTimer);
  entryTimingTimer=null;
}

function bindStatsTablePageWheel(){
  document.querySelectorAll("#statsTableCard .stats-table-wrap,.inventory-stats-card .table-scroll").forEach(node=>{
    // Keep only horizontal overflow inside the table. Vertical wheel input must
    // bubble to the document so the whole page scrolls smoothly over the table.
    node.style.overflowY="hidden";
    node.style.overscrollBehaviorY="auto";
  });
}

function bindProUI(){
  proInstallDateButtons();
  bindStatsTablePageWheel();
  startEntryTimingTicker();
  document.addEventListener("input",event=>{if(event.target.closest?.("#cashPositionCard"))$("cashPositionCard").dataset.dirty="1";});
  document.addEventListener("input",event=>{if(event.target.matches("[data-picker-search]")){const q=event.target.value.trim().toLocaleLowerCase("zh-CN");document.querySelectorAll("[data-picker-row]").forEach(row=>row.hidden=!row.querySelector("[data-pick-name]").textContent.toLocaleLowerCase("zh-CN").includes(q));}});
  $("ledgerDate").addEventListener("change",()=>captureBeforeDateChange("ledgerDate","ledger",refreshLedger));$("fixedMonth").addEventListener("change",()=>captureBeforeDateChange("fixedMonth","fixed",refreshFixed));$("historyMonth").addEventListener("change",renderHistory);$("saveLedgerButton").addEventListener("click",()=>safely(saveLedger));$("syncWechatButton")?.addEventListener("click",()=>safely(syncWechatBill));$("saveFixedButton").addEventListener("click",()=>safely(saveFixed));$("saveCashPosition")?.addEventListener("click",()=>safely(saveCashPosition));$("undoLedgerButton").addEventListener("click",()=>{forgetEditorDraft("ledger",$("ledgerDate").value);refreshLedger();});$("openFixedExpenses").addEventListener("click",openFixedExpensesModal);
  $("ledgerPickFood").addEventListener("click",()=>openItemPicker("食材",$("ledgerFoodDetail").value,items=>{$("ledgerFoodDetail").value=serializeItems(items);$("ledgerFoodCost").value=sumItems(items);renderLedgerDetailSummaries();captureLedgerDraft();}));$("ledgerPickSpice").addEventListener("click",()=>openItemPicker("佐料",$("ledgerSpiceDetail").value,items=>{$("ledgerSpiceDetail").value=serializeItems(items);$("ledgerSpiceCost").value=sumItems(items);renderLedgerDetailSummaries();captureLedgerDraft();}));
  ["ledgerACash","ledgerBCash","ledgerAWechatAdd","ledgerAWechatOverride","ledgerAAlipayAdd","ledgerAAlipayOverride","ledgerBWechatAdd","ledgerBWechatOverride","ledgerBAlipayAdd","ledgerBAlipayOverride","ledgerStudentTakeout","ledgerATakeout","ledgerBTakeout"].forEach(id=>$(id).addEventListener("input",syncLedgerRevenueBreakdown));
  $("dishDate").addEventListener("change",()=>captureBeforeDateChange("dishDate","dishes",refreshDishes));$("addDishButton").addEventListener("click",()=>{addDishRow();captureDishesDraft();});$("deleteDishButton").addEventListener("click",()=>{deleteSelectedDish();captureDishesDraft();});$("saveDishesButton").addEventListener("click",()=>safely(saveDishes));$("undoDishesButton").addEventListener("click",()=>{forgetEditorDraft("dishes",$("dishDate").value);refreshDishes();});
  for(const kind of ["food","spice"]){$(kind+"Date").addEventListener("change",()=>captureBeforeDateChange(kind+"Date",kind,()=>refreshDetail(kind)));$("add"+(kind==="food"?"Food":"Spice")+"RowButton").addEventListener("click",()=>{addDetailRow(kind);captureDetailDraft(kind);});$("save"+(kind==="food"?"Food":"Spice")+"Button").addEventListener("click",()=>safely(()=>saveDetail(kind)));document.querySelector(`[data-undo-detail="${kind}"]`).addEventListener("click",()=>{forgetEditorDraft(kind,$(kind+"Date").value);refreshDetail(kind);});document.querySelector(`[data-delete-detail="${kind}"]`).addEventListener("click",()=>{deleteDetailRows(kind);captureDetailDraft(kind);});document.querySelector(`[data-move-detail="${kind}"]`).addEventListener("click",()=>safely(async()=>{await moveDetailRows(kind);captureDetailDraft(kind);captureDetailDraft(kind==="food"?"spice":"food");}));}
  $("addInventoryRowButton")?.addEventListener("click",()=>{addInventoryRow();captureInventoryDraft();});
  $("deleteInventoryRowsButton")?.addEventListener("click",()=>{deleteInventoryRows();captureInventoryDraft();});
  $("saveInventoryButton")?.addEventListener("click",()=>safely(saveInventory));
  document.querySelectorAll("[data-manage-units]").forEach(button=>button.addEventListener("click",manageUnits));
  $("statsPreviousYear").addEventListener("click",()=>shiftStatsYear(-1));$("statsThisYear").addEventListener("click",()=>{const y=String(new Date().getFullYear());if(![...$("statsYear").options].some(o=>o.value===y))$("statsYear").add(new Option(y,y));$("statsYear").value=y;renderStats();});$("statsNextYear").addEventListener("click",()=>shiftStatsYear(1));$("statsExport").addEventListener("click",exportStatsCsv);
  $("purchaseIngredients").addEventListener("click",()=>selectStatIngredients("purchase"));$("consumptionIngredients").addEventListener("click",()=>selectStatIngredients("consumption"));
  $("clearPurchaseIngredients").addEventListener("click",()=>{proSelectedPurchase=[];$("purchaseIngredients").textContent="选择食材（不选则看经营指标）";renderStats();});
  $("clearConsumptionIngredients").addEventListener("click",()=>{proSelectedConsumption=[];$("consumptionIngredients").textContent="选择消耗食材（未选择）";renderStats();});
  document.querySelectorAll("[data-stats-metrics]").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll("#statsMetricChecks input").forEach(i=>i.checked=b.dataset.statsMetrics==="all");if(b.dataset.statsMetrics==="none")document.querySelector('#statsMetricChecks input[value="net"]').checked=true;renderStats();}));document.querySelectorAll("[data-stats-views]").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".stats-view-check").forEach(i=>i.checked=b.dataset.statsViews==="all"||(b.dataset.statsViews==="table"&&i.value==="table"));renderStats();}));
  ["selectedDate","selectedMonth","selectedYear","trendMetric"].forEach(id=>$(id)?.addEventListener("change",()=>setTimeout(fitDashboardMonthChart,0)));
  document.addEventListener("click",event=>{const button=event.target.closest?.("[data-expand-chart]");if(button)toggleChartExpanded(button);});
  document.addEventListener("keydown",event=>{if(event.key==="Escape")closeExpandedCharts();});
}

function installChartScrollControls(card){
  card._chartScrollCleanup?.();
  card._chartScrollRestore?.();
  let viewport=card.querySelector(".svg-chart,.chart-scroll-shell"),directShell=null;
  if(!viewport){
    const directContent=[...card.children].find(node=>node.matches?.(".donut-layout,.bar-chart,.horizontal-bars"));
    if(!directContent)return;
    directShell=document.createElement("div");directShell.className="chart-scroll-shell chart-direct-scroll-shell";directShell.tabIndex=-1;
    directContent.parentNode.insertBefore(directShell,directContent);directShell.appendChild(directContent);viewport=directShell;
  }
  const frame=document.createElement("div"),controls=document.createElement("div");
  frame.className="chart-scroll-frame";
  controls.className="chart-scroll-controls";
  controls.innerHTML='<label class="chart-scroll-x-wrap"><span>左右滚动</span><input class="chart-scroll-x" type="range" min="0" step="1" value="0" aria-label="左右滚动"></label><label class="chart-scroll-y-wrap"><span>上下</span><input class="chart-scroll-y" type="range" min="0" step="1" value="0" aria-label="上下滚动" aria-orientation="vertical"></label>';
  viewport.parentNode.insertBefore(frame,viewport);
  frame.append(viewport,controls);
  const x=controls.querySelector(".chart-scroll-x"),y=controls.querySelector(".chart-scroll-y"),yWrap=controls.querySelector(".chart-scroll-y-wrap");
  let syncFrame=0;
  const clamp=(value,max)=>Math.max(0,Math.min(max,value));
  const limits=()=>({x:Math.max(0,viewport.scrollWidth-viewport.clientWidth),y:Math.max(0,viewport.scrollHeight-viewport.clientHeight)});
  const syncLimits=()=>{
    const max=limits();
    x.max=String(max.x);y.max=String(max.y);
    x.disabled=max.x===0;y.disabled=max.y===0;
    x.value=String(clamp(viewport.scrollLeft,max.x));
    y.value=String(clamp(viewport.scrollTop,max.y));
    y.style.setProperty("width",`${Math.max(90,yWrap.clientHeight-58)}px`,"important");
  };
  const scheduleSync=()=>{cancelAnimationFrame(syncFrame);syncFrame=requestAnimationFrame(syncLimits);};
  const onXInput=()=>{const max=limits().x;viewport.scrollLeft=clamp(Number(x.value),max);};
  const onYInput=()=>{const max=limits().y;viewport.scrollTop=clamp(Number(y.value),max);};
  const onYKeydown=event=>{
    if(event.key!=="ArrowUp"&&event.key!=="ArrowDown")return;
    event.preventDefault();
    const max=limits().y,step=Math.max(1,Math.round(viewport.clientHeight/12));
    y.value=String(clamp(Number(y.value)+(event.key==="ArrowDown"?step:-step),max));
    onYInput();
  };
  const onViewportScroll=()=>{const max=limits();x.value=String(clamp(viewport.scrollLeft,max.x));y.value=String(clamp(viewport.scrollTop,max.y));};
  x.addEventListener("input",onXInput);y.addEventListener("input",onYInput);y.addEventListener("keydown",onYKeydown);viewport.addEventListener("scroll",onViewportScroll,{passive:true});
  const resizeObserver=typeof ResizeObserver==="function"?new ResizeObserver(scheduleSync):null;
  resizeObserver?.observe(frame);resizeObserver?.observe(viewport);
  const mutationObserver=new MutationObserver(scheduleSync);mutationObserver.observe(viewport,{childList:true,subtree:true});
  window.addEventListener("resize",scheduleSync);
  card._chartScrollCleanup=()=>{cancelAnimationFrame(syncFrame);resizeObserver?.disconnect();mutationObserver.disconnect();window.removeEventListener("resize",scheduleSync);x.removeEventListener("input",onXInput);y.removeEventListener("input",onYInput);y.removeEventListener("keydown",onYKeydown);viewport.removeEventListener("scroll",onViewportScroll);delete card._chartScrollCleanup;};
  card._chartScrollRestore=()=>{viewport.scrollLeft=0;viewport.scrollTop=0;if(frame.isConnected){frame.parentNode.insertBefore(viewport,frame);frame.remove();}if(directShell?.isConnected){const content=directShell.firstElementChild;if(content)directShell.parentNode.insertBefore(content,directShell);directShell.remove();}delete card._chartScrollRestore;};
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    syncLimits();
    viewport.scrollLeft=0;
    const svg=viewport.querySelector(".detailed-trend-svg"),line=svg?.querySelector(".trend-line");
    if(svg&&line){
      try{
        const box=line.getBBox(),viewHeight=svg.viewBox.baseVal.height||svg.clientHeight||1,scale=svg.clientHeight/viewHeight;
        const plotCenter=(box.y+box.height/2)*scale;
        viewport.scrollTop=clamp(plotCenter-viewport.clientHeight/2,limits().y);
      }catch(_){viewport.scrollTop=0;}
    }else if(viewport.querySelector(".interactive-bars,.bar-chart")){
      viewport.scrollTop=limits().y;
    }else viewport.scrollTop=0;
    syncLimits();
  }));
}
function toggleChartExpanded(button){const card=button.closest(".chart-card");if(!card)return;const opening=!card.classList.contains("chart-expanded");closeExpandedCharts();if(opening){card.classList.add("chart-expanded");document.body.classList.add("chart-modal-open");button.textContent=state.language==="en"?" Close":" 退出全屏";setTimeout(()=>{installChartScrollControls(card);card.querySelector(".svg-chart,.chart-scroll-shell")?.focus?.();},0);}}
function closeExpandedCharts(){document.querySelectorAll(".chart-card.chart-expanded").forEach(card=>{card._chartScrollCleanup?.();card._chartScrollRestore?.();card.classList.remove("chart-expanded");const button=card.querySelector("[data-expand-chart]");if(button)button.textContent=state.language==="en"?" Expand":" 放大";});document.body.classList.remove("chart-modal-open");}

function ingredientDictionary(category){const record=currentRecord("global","ingredients"),payload=record?unpackPayload(record):{},rows=Array.isArray(payload.ingredients)?payload.ingredients:[];const names=rows.filter(row=>!category||String(row.分类||"食材")===category).map(row=>String(row.词条名称||row.食材名称||"").trim()).filter(Boolean);for(const day of state.days){for(const item of parseDetailItems(day[category==="佐料"?"佐料明细":"食材明细"]))if(item.name)names.push(item.name);}return [...new Set(names)].sort((a,b)=>a.localeCompare(b,"zh-CN"));}
async function saveDictionary(category,names){const record=currentRecord("global","ingredients"),payload=clone(record?unpackPayload(record):{}),all=Array.isArray(payload.ingredients)?payload.ingredients:[],others=all.filter(row=>String(row.分类||"食材")!==category);payload.ingredients=[...others,...names.map(name=>({词条名称:name,分类:category}))];await saveRecord("global","ingredients",payload);}

function inventoryPayload(){const record=currentRecord("global","inventory"),payload=record?clone(unpackPayload(record)):{};if(!Array.isArray(payload.entries))payload.entries=[];return payload;}
function inventoryEntries(){return inventoryPayload().entries.filter(entry=>!(entry.voided===true||entry.voided===1||["true","1"].includes(String(entry.voided||"").toLowerCase()))).map(entry=>({...entry,id:String(entry.id||uuid()),date:String(entry.date||entry.日期||""),category:String(entry.category||entry.分类||"食材")==="佐料"?"佐料":"食材",name:String(entry.name||entry.名称||"").trim(),quantity:num(entry.quantity??entry.数量),unit:String(entry.unit||entry.单位||"").trim(),unitPrice:entry.price_known===false?"":(entered(entry.unit_price??entry.单价)?Exact.decimal(Exact.price(entry.unit_price??entry.单价)):""),total:entry.price_known===false?"":(entered(entry.total??entry.总价)?Exact.decimal(Exact.amount(entry.total??entry.总价)):""),note:String(entry.note||entry.备注||"")})).filter(entry=>entry.name);}
function inventoryConsumption(){const used=new Map();for(const day of state.days){const date=String(day.日期||"");const {rows}=dishData(date);for(const dish of rows)for(const item of parseDetailItems(dish.食材明细)){if(!item.name||!num(item.quantity))continue;const unit=String(item.unit||"").trim(),key=`食材\u0000${item.name}\u0000${unit}`;const row=used.get(key)||{quantity:0,lastDate:""};row.quantity+=num(item.quantity);if(date>row.lastDate)row.lastDate=date;used.set(key,row);}}return used;}
function inventoryBalances(){const used=inventoryConsumption(),balances=new Map();for(const entry of inventoryEntries()){const key=`${entry.category}\u0000${entry.name}\u0000${entry.unit}`,row=balances.get(key)||{category:entry.category,name:entry.name,unit:entry.unit,received:0,receivedValue:0,used:0,lastDate:""};row.received+=entry.quantity;row.receivedValue+=entry.total||entry.quantity*entry.unitPrice;if(entry.date>row.lastDate)row.lastDate=entry.date;balances.set(key,row);}for(const [key,value] of used){const row=balances.get(key);if(row)row.used=value.quantity;}return [...balances.values()].map(row=>({...row,remaining:row.received-row.used})).sort((a,b)=>a.category.localeCompare(b.category,"zh-CN")||a.name.localeCompare(b.name,"zh-CN")||a.unit.localeCompare(b.unit,"zh-CN"));}
function inventoryStatus(row){if(row.remaining<=0)return{key:"out",zh:"已用完",en:"Out"};if(row.received>0&&row.remaining/row.received<=0.2)return{key:"low",zh:"库存偏低",en:"Low"};return{key:"ok",zh:"充足",en:"In stock"};}

/* Inventory counts have two explicit adjustment paths: an absolute overwrite and a delta adjustment. */
function inventoryPayload(){const record=currentRecord("global","inventory"),payload=record?clone(unpackPayload(record)):{};if(!Array.isArray(payload.entries))payload.entries=[];if(!Array.isArray(payload.adjustments))payload.adjustments=[];if(!Array.isArray(payload.overrides))payload.overrides=[];return payload;}
function inventoryKey(row){return `${row.category}\u0000${row.name}\u0000${row.unit}`;}
function inventoryAdjustmentRows(payload=inventoryPayload()){return (payload.adjustments||[]).map((item,index)=>({...item,id:String(item.id||`adjustment:${index}`),date:String(item.date||item.日期||""),recorded_at:item.recorded_at||"",kind:String(item.kind||item.类型||"normal")==="loss"?"loss":"normal",category:String(item.category||item.分类||"食材")==="佐料"?"佐料":"食材",name:String(item.name||item.名称||"").trim(),unit:String(item.unit||item.单位||"").trim(),quantity:Number(item.quantity??item.数量??0),note:String(item.note||item.备注||"")})).filter(item=>item.name&&Number.isFinite(item.quantity)&&item.quantity!==0);}
function inventoryOverrideRows(payload=inventoryPayload()){return (payload.overrides||[]).map((item,index)=>({...item,id:String(item.id||`override:${index}`),date:String(item.date||item.日期||""),recorded_at:item.recorded_at||"",category:String(item.category||item.分类||"食材")==="佐料"?"佐料":"食材",name:String(item.name||item.名称||"").trim(),unit:String(item.unit||item.单位||"").trim(),quantity:Math.max(0,num(item.quantity??item.数量??0)),note:String(item.note||item.备注||"")})).filter(item=>item.name&&item.date);}
function inventoryConsumption(){const used=new Map();for(const day of state.days){const date=String(day.日期||"");const {rows}=dishData(date);for(const dish of rows)for(const item of parseDetailItems(dish.食材明细)){if(!item.name||!num(item.quantity))continue;const key=inventoryKey({category:"食材",name:item.name,unit:String(item.unit||"").trim()}),row=used.get(key)||{quantity:0,lastDate:""};row.quantity+=num(item.quantity);if(date>row.lastDate)row.lastDate=date;used.set(key,row);}}return used;}
function inventoryBalances(){const used=inventoryConsumption(),adjustments=inventoryAdjustmentRows(),overrides=inventoryOverrideRows(),latestOverrides=new Map(),entries=inventoryEntries();for(const item of overrides){const key=inventoryKey(item),previous=latestOverrides.get(key);if(!previous||item.date>=previous.date)latestOverrides.set(key,item);}const balances=new Map();for(const entry of entries){const key=inventoryKey(entry),row=balances.get(key)||{category:entry.category,name:entry.name,unit:entry.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null};row.received+=entry.quantity;row.receivedValue+=entry.total||entry.quantity*entry.unitPrice;if(entry.date>row.lastDate)row.lastDate=entry.date;balances.set(key,row);}for(const [key,value] of used){const row=balances.get(key);if(row)row.used=value.quantity;}for(const item of adjustments){const key=inventoryKey(item),row=balances.get(key)||{category:item.category,name:item.name,unit:item.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null};if(item.quantity>0){row.manualUsed+=item.quantity;if(item.kind==="loss")row.loss+=item.quantity;else row.normalUsed+=item.quantity;}balances.set(key,row);}for(const [key,item] of latestOverrides){const row=balances.get(key)||{category:item.category,name:item.name,unit:item.unit,received:0,receivedValue:0,used:0,manualUsed:0,loss:0,normalUsed:0,lastDate:"",override:null};row.override=item;balances.set(key,row);}return [...balances.values()].map(row=>{const cutoff=row.override?.date||"",key=inventoryKey(row),futureReceived=cutoff?entries.filter(item=>inventoryKey(item)===key&&item.date>cutoff).reduce((sum,item)=>sum+item.quantity,0):0,futureUsed=cutoff?[...used.entries()].filter(([usedKey])=>usedKey===key).reduce((sum,[,value])=>sum+(value.lastDate>cutoff?value.quantity:0),0):0,futureManual=cutoff?adjustments.filter(item=>inventoryKey(item)===key&&item.date>cutoff).reduce((sum,item)=>sum+item.quantity,0):0,remaining=row.override?row.override.quantity+futureReceived-futureUsed-futureManual:row.received-row.used-row.manualUsed;return {...row,remaining,overridden:Boolean(row.override)};}).sort((a,b)=>a.category.localeCompare(b.category,"zh-CN")||a.name.localeCompare(b.name,"zh-CN")||a.unit.localeCompare(b.unit,"zh-CN"));}
function addInventoryRow(entry={}){
  const tr=document.createElement("tr"),date=entry.date||isoDate(new Date()),category=entry.category==="佐料"?"佐料":"食材";
  tr.dataset.entryId=entry.id||uuid();
  tr.innerHTML=`<td><input data-inventory-check type="checkbox"></td><td><input data-inventory="date" type="date" value="${escapeHtml(date)}"></td><td><select data-inventory="category"><option value="食材" ${category==="食材"?"selected":""}>${state.language==="en"?"Ingredient":"食材"}</option><option value="佐料" ${category==="佐料"?"selected":""}>${state.language==="en"?"Seasoning":"佐料"}</option></select></td><td><input data-inventory="name" value="${escapeHtml(entry.name||"")}"></td><td><input data-inventory="quantity" type="number" step="any" min="0" value="${entered(entry.quantity)?escapeHtml(entry.quantity):""}"></td><td><select data-inventory="unit">${proUnitOptions(entry.unit||"")}</select></td><td><input data-inventory="unitPrice" type="number" step="0.000001" min="0" value="${entered(entry.unitPrice)?num(entry.unitPrice).toFixed(6):""}"></td><td><input data-inventory="total" type="number" step="0.01" min="0" value="${entered(entry.total)?num(entry.total).toFixed(2):""}"></td><td><input data-inventory="note" value="${escapeHtml(entry.note||"")}"></td>`;
  const quantityField=tr.querySelector('[data-inventory="quantity"]'),priceField=tr.querySelector('[data-inventory="unitPrice"]'),totalField=tr.querySelector('[data-inventory="total"]');
  const recalculate=source=>{proSyncAmountFields(quantityField,priceField,totalField,source);updateInventoryEntryTotal();};
  quantityField.addEventListener("input",()=>recalculate("quantity"));
  priceField.addEventListener("input",()=>recalculate("price"));
  totalField.addEventListener("input",()=>recalculate("total"));
  tr.querySelectorAll("input,select").forEach(input=>input.addEventListener("input",updateInventoryEntryTotal));
  $("inventoryRows").appendChild(tr);updateInventoryEntryTotal();
}
function collectInventoryRows(){if(!$("inventoryRows"))return [];return [...$("inventoryRows").querySelectorAll("tr")].map(tr=>{const get=key=>tr.querySelector(`[data-inventory="${key}"]`).value;return{id:tr.dataset.entryId||uuid(),date:get("date"),category:get("category"),name:get("name").trim(),quantity:num(get("quantity")),unit:get("unit").trim(),unit_price:entered(get("unitPrice"))?num(get("unitPrice")):"",total:entered(get("total"))?num(get("total")):(entered(get("unitPrice"))?num(get("quantity"))*num(get("unitPrice")):""),price_known:entered(get("total"))||entered(get("unitPrice")),note:get("note").trim()};}).filter(entry=>entry.name&&entry.date&&entry.quantity>0);}
function updateInventoryEntryTotal(){if(!$("inventoryRows"))return;const rows=[...$("inventoryRows").querySelectorAll('[data-inventory="total"]')],total=rows.reduce((sum,input)=>sum+num(input.value),0);$("inventoryEntryTotal").textContent=(state.language==="en"?"Receiving total: ":"入库金额合计：")+money(total);}
function deleteInventoryRows(){const selected=[...$("inventoryRows").querySelectorAll("tr")].filter(tr=>tr.querySelector("[data-inventory-check]").checked);if(!selected.length)return;selected.forEach(tr=>tr.remove());updateInventoryEntryTotal();}
function renderInventoryBalance(){const balances=inventoryBalances(),en=state.language==="en",displayUnit=unit=>typeof v8DisplayUnit==="function"?v8DisplayUnit(unit):unit;$("inventoryBalanceTotal").textContent=en?`${balances.length} stock item(s)`: `${balances.length} 个库存项目`;$("inventoryBalanceGrid").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row);return `<article class="inventory-balance-item is-${status.key}"><header><strong>${escapeHtml(row.name)}</strong><span>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</span></header><div><b>${compactDecimal(row.remaining)}</b><em>${escapeHtml(displayUnit(row.unit)||"—")}</em></div><small>${en?`Received ${compactDecimal(row.received)} · Used ${compactDecimal(row.used)}`:`入库 ${compactDecimal(row.received)} · 已用 ${compactDecimal(row.used)}`}</small><span class="inventory-status">${en?status.en:status.zh}</span></article>`;}).join(""):`<div class="inventory-empty">${en?"No receiving entries yet.":"还没有入库记录。"}</div>`;}
function renderInventory(){if(!$("inventoryRows"))return;$("inventoryPermission").textContent=canEdit()?(state.language==="en"?"Editable":"可修改"):(state.language==="en"?"Read only":"只读账号");const draft=readEditorDraft("inventory","current"),entries=draft?.entries?.length?draft.entries:inventoryEntries().sort((a,b)=>b.date.localeCompare(a.date));$("inventoryRows").innerHTML="";entries.forEach(addInventoryRow);renderInventoryBalance();updateInventoryEntryTotal();}
async function saveInventory(){if(!canEdit())throw new Error(state.language==="en"?"This account is read only.":"当前账号只读，不能修改入库记录。");const payload=inventoryPayload();payload.entries=collectInventoryRows();payload.updated_at=new Date().toISOString();await saveRecord("global","inventory",payload,"inventoryResult");forgetEditorDraft("inventory","current");renderInventory();renderInventoryStats();}
function renderInventoryStats(){if(!$("inventoryStatsRows"))return;const balances=inventoryBalances(),en=state.language==="en";$("inventoryStatsRows").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row);return `<tr><td>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.unit||"—")}</td><td>${compactDecimal(row.received)}</td><td>${compactDecimal(row.used)}</td><td><strong class="inventory-remaining is-${status.key}">${compactDecimal(row.remaining)}</strong></td><td>${en?status.en:status.zh}</td><td>${escapeHtml(row.lastDate||"—")}</td></tr>`;}).join(""):`<tr><td colspan="8">${en?"No inventory data.":"暂无库存数据。"}</td></tr>`;$("inventoryStatsUpdated").textContent=en?"Live balance":"实时结余";}

function parseDetailItems(raw){if(!entered(raw))return[];if(Array.isArray(raw))return raw.map(normalizeItem);const text=String(raw).trim();try{const parsed=JSON.parse(text);if(Array.isArray(parsed))return parsed.map(normalizeItem);}catch(_){}const unitPattern=proUnits().sort((a,b)=>b.length-a.length).map(u=>u.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join("|");return text.split(/[,，;；\n]+/).map(part=>part.trim()).filter(Boolean).map(part=>{let note="";const nm=part.match(/\s+备注[:：](.*)$/);if(nm){note=nm[1].trim();part=part.slice(0,nm.index).trim();}const full=part.match(new RegExp(`^(.*?)\\s+(\\d+(?:\\.\\d+)?)\\s*(${unitPattern})?\\s+(\\d+(?:\\.\\d+)?)$`));if(full){const quantity=num(full[2]),total=num(full[4]);return{name:full[1].trim(),quantity,unit:full[3]||"",price:quantity?total/quantity:0,total,note};}const custom=part.match(/^(.*?)\s+(\d+(?:\.\d+)?)\s*([^\d\s]+)\s+(\d+(?:\.\d+)?)$/);if(custom){const quantity=num(custom[2]),total=num(custom[4]);return{name:custom[1].trim(),quantity,unit:custom[3],price:quantity?total/quantity:0,total,note};}const amountOnly=/^\d+(?:\.\d+)?$/.test(part)?null:part.match(/^(.+?)(?:\s+)?(\d+(?:\.\d+)?)$/);return amountOnly?{name:amountOnly[1].trim(),quantity:"",unit:"",price:"",total:num(amountOnly[2]),note}:{name:part,quantity:"",unit:"",price:"",total:"",note};});}
function inventoryPromptValue(message,initial){const value=window.prompt(message,String(initial));if(value===null)return null;const parsed=Number(String(value).trim());if(!Number.isFinite(parsed)||parsed<0)throw new Error(state.language==="en"?"Enter a number greater than or equal to 0.":"请输入大于或等于 0 的数字。");return parsed;}
async function overwriteInventoryBalance(key){if(!canEdit())throw new Error(state.language==="en"?"This account is read only.":"当前账号只读，不能修改库存。");const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(!row)return;const value=inventoryPromptValue(state.language==="en"?`Overwrite current balance for ${row.name} (${row.unit||"no unit"})`:`强制覆盖「${row.name}（${row.unit||"无单位"}）」的当前剩余量`,row.remaining);if(value===null)return;const payload=inventoryPayload();payload.overrides=payload.overrides.filter(item=>inventoryKey({category:String(item.category||item.分类||"食材")==="佐料"?"佐料":"食材",name:String(item.name||item.名称||""),unit:String(item.unit||item.单位||"")})!==key);payload.overrides.push({id:uuid(),date:isoDate(new Date()),category:row.category,name:row.name,unit:row.unit,quantity:value,note:"强制覆盖库存"});await saveRecord("global","inventory",payload,"inventoryResult");renderInventory();renderInventoryStats();}
async function modifyInventoryBalance(key){if(!canEdit())throw new Error(state.language==="en"?"This account is read only.":"当前账号只读，不能修改库存。");const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(!row)return;const value=inventoryPromptValue(state.language==="en"?`Enter the new balance for ${row.name} (${row.unit||"no unit"}). The difference will be recorded as automatic usage.`:`请输入「${row.name}（${row.unit||"无单位"}）」的新剩余量，差额会自动记录为消耗。`,row.remaining);if(value===null)return;const difference=row.remaining-value;if(!difference)return;const payload=inventoryPayload();payload.adjustments.push({id:uuid(),date:isoDate(new Date()),category:row.category,name:row.name,unit:row.unit,quantity:difference,note:difference>0?"修改库存自动计算消耗":"修改库存自动补回"});await saveRecord("global","inventory",payload,"inventoryResult");renderInventory();renderInventoryStats();}
async function applyInventoryBalanceAdjustment(key,mode,value){const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(!row)return;if(mode==="overwrite"){const payload=inventoryPayload();payload.overrides=payload.overrides.filter(item=>inventoryKey({category:String(item.category||item.分类||"食材")==="佐料"?"佐料":"食材",name:String(item.name||item.名称||""),unit:String(item.unit||item.单位||"")})!==key);payload.overrides.push({id:uuid(),date:isoDate(new Date()),category:row.category,name:row.name,unit:row.unit,quantity:value,note:"强制覆盖库存"});await saveRecord("global","inventory",payload,"inventoryResult");}else{const difference=row.remaining-value;if(!difference)return;const payload=inventoryPayload();payload.adjustments.push({id:uuid(),date:isoDate(new Date()),kind:mode==="loss"?"loss":"normal",category:row.category,name:row.name,unit:row.unit,quantity:difference,note:mode==="loss"?"差值计入损耗":"差值算作正常消耗"});await saveRecord("global","inventory",payload,"inventoryResult");}renderInventory();renderInventoryStats();}
const guardedInventoryBalanceAdjustment=applyInventoryBalanceAdjustment;
applyInventoryBalanceAdjustment=async function(key,mode,value){const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(["modify","normal","loss"].includes(mode)&&row&&value>row.remaining)throw new Error("调整后的库存不能大于当前剩余量；如需增加库存请使用直接覆盖调整。");return guardedInventoryBalanceAdjustment(key,mode,value);};
function openInventoryAdjustmentModal(key,mode){if(!canEdit()){showError(new Error(state.language==="en"?"This account is read only.":"当前账号只读，不能修改库存。"));return;}const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(!row)return;const en=state.language==="en",overwrite=mode==="overwrite";$("proModalHost").innerHTML=`<div class="pro-modal-backdrop"><section class="pro-modal inventory-adjust-modal"><header><h2>${overwrite?(en?"Force overwrite inventory":"强制覆盖库存"):(en?"Modify inventory":"修改库存")}</h2><button data-close-modal class="pro-button">${en?"Close":"关闭"}</button></header><div class="modal-body"><p><strong>${escapeHtml(row.name)}</strong> · ${escapeHtml(row.unit||"—")}</p><label class="inventory-adjust-field">${en?"New current balance":"新的当前剩余量"}<input data-inventory-value type="number" min="0" ${overwrite?"":"max=\""+escapeHtml(row.remaining)+"\""} step="any" value="${escapeHtml(row.remaining)}"></label><small>${overwrite?(en?"This directly sets the current balance and does not add purchase value.":"直接设置当前剩余量，不增加采购金额。"):(en?"The difference from the old balance will be recorded as automatic usage.":"与原剩余量的差额会自动记录为消耗。")}</small></div><footer><button data-close-modal class="pro-button">${en?"Cancel":"取消"}</button><button data-inventory-submit class="pro-button green">${en?"Save":"保存"}</button></footer></section></div>`;const host=$("proModalHost"),close=()=>closeProModal();host.querySelectorAll("[data-close-modal]").forEach(button=>button.addEventListener("click",close));host.querySelector("[data-inventory-value]").focus();host.querySelector("[data-inventory-submit]").addEventListener("click",()=>safely(async()=>{const value=Number(host.querySelector("[data-inventory-value]").value);if(!Number.isFinite(value)||value<0||(!overwrite&&value>row.remaining))throw new Error(en?"Modify can only reduce the current balance; use force overwrite to set a higher balance.":"修改只能减少当前剩余量；如需增加库存，请使用强制覆盖库存。");await applyInventoryBalanceAdjustment(key,mode,value);close();}));}
function bindInventoryBalanceActions(){document.querySelectorAll("[data-inventory-overwrite]").forEach(button=>button.addEventListener("click",()=>openInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryOverwrite),"overwrite")));document.querySelectorAll("[data-inventory-modify]").forEach(button=>button.addEventListener("click",()=>openInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryModify),"modify")));}
function renderInventoryBalance(){const balances=inventoryBalances(),en=state.language==="en",displayUnit=unit=>typeof v8DisplayUnit==="function"?v8DisplayUnit(unit):unit;$("inventoryBalanceTotal").textContent=en?`${balances.length} stock item(s)`: `${balances.length} 个库存项目`;$("inventoryBalanceGrid").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row),key=escapeHtml(inventoryKey(row));return `<article class="inventory-balance-item is-${status.key}"><header><strong>${escapeHtml(row.name)}</strong><span>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</span></header><div><b>${compactDecimal(row.remaining)}</b><em>${escapeHtml(displayUnit(row.unit)||"—")}</em></div><small>${en?`Received ${compactDecimal(row.received)} · Dish usage ${compactDecimal(row.used)} · Auto usage ${compactDecimal(row.manualUsed)}`:`入库 ${compactDecimal(row.received)} · 菜品消耗 ${compactDecimal(row.used)} · 自动消耗 ${compactDecimal(row.manualUsed)}`}</small><span class="inventory-status">${en?status.en:status.zh}${row.overridden?(en?" · Overwritten":" · 已覆盖"):""}</span><div class="inventory-balance-actions"><button class="soft edit-action" type="button" data-inventory-overwrite="${key}">${en?"Force overwrite":"强制覆盖库存"}</button><button class="primary edit-action" type="button" data-inventory-modify="${key}">${en?"Modify":"修改"}</button></div></article>`;}).join(""):`<div class="inventory-empty">${en?"No receiving entries yet.":"还没有入库记录。"}</div>`;bindInventoryBalanceActions();}
function renderInventory(){if(!$("inventoryRows"))return;$("inventoryPermission").textContent=canEdit()?(state.language==="en"?"Editable":"可修改"):(state.language==="en"?"Read only":"只读账号");const draft=readEditorDraft("inventory","current"),entries=draft?.entries?.length?draft.entries:inventoryEntries().sort((a,b)=>b.date.localeCompare(a.date));$("inventoryRows").innerHTML="";entries.forEach(addInventoryRow);renderInventoryBalance();updateInventoryEntryTotal();}
function renderInventoryStats(){if(!$("inventoryStatsRows"))return;const balances=inventoryBalances(),en=state.language==="en";$("inventoryStatsRows").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row);return `<tr><td>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.unit||"—")}</td><td>${compactDecimal(row.received)}</td><td>${compactDecimal(row.used)}</td><td>${compactDecimal(row.manualUsed)}</td><td><strong class="inventory-remaining is-${status.key}">${compactDecimal(row.remaining)}</strong></td><td>${en?status.en:status.zh}</td><td>${escapeHtml(row.lastDate||"—")}</td></tr>`;}).join(""):`<tr><td colspan="9">${en?"No inventory data.":"暂无库存数据。"}</td></tr>`;$("inventoryStatsUpdated").textContent=en?"Live balance":"实时结余";}
function bindInventoryBalanceActions(){document.querySelectorAll("[data-inventory-overwrite]").forEach(button=>button.addEventListener("click",()=>safely(()=>overwriteInventoryBalance(decodeURIComponent(button.dataset.inventoryOverwrite)))));document.querySelectorAll("[data-inventory-modify]").forEach(button=>button.addEventListener("click",()=>safely(()=>modifyInventoryBalance(decodeURIComponent(button.dataset.inventoryModify)))));}
renderInventoryBalance=function(){const balances=inventoryBalances(),en=state.language==="en",displayUnit=unit=>typeof v8DisplayUnit==="function"?v8DisplayUnit(unit):unit;$("inventoryBalanceTotal").textContent=en?`${balances.length} stock item(s)`: `${balances.length} 个库存项目`;$("inventoryBalanceGrid").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row),key=encodeURIComponent(inventoryKey(row));return `<article class="inventory-balance-item is-${status.key}"><header><strong>${escapeHtml(row.name)}</strong><span>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</span></header><div><b>${compactDecimal(row.remaining)}</b><em>${escapeHtml(displayUnit(row.unit)||"—")}</em></div><small>${en?`Received ${compactDecimal(row.received)} · Dish usage ${compactDecimal(row.used)} · Auto usage ${compactDecimal(row.manualUsed)}`:`入库 ${compactDecimal(row.received)} · 菜品消耗 ${compactDecimal(row.used)} · 自动消耗 ${compactDecimal(row.manualUsed)}`}</small><span class="inventory-status">${en?status.en:status.zh}${row.overridden?(en?" · Overwritten":" · 已覆盖"):""}</span><div class="inventory-balance-actions"><button class="soft edit-action" type="button" data-inventory-overwrite="${key}">${en?"Force overwrite":"强制覆盖库存"}</button><button class="primary edit-action" type="button" data-inventory-modify="${key}">${en?"Modify":"修改"}</button></div></article>`;}).join(""):`<div class="inventory-empty">${en?"No receiving entries yet.":"还没有入库记录。"}</div>`;bindInventoryBalanceActions();};
renderInventory=function(){if(!$("inventoryRows"))return;$("inventoryPermission").textContent=canEdit()?(state.language==="en"?"Editable":"可修改"):(state.language==="en"?"Read only":"只读账号");const draft=readEditorDraft("inventory","current"),entries=draft?(draft.entries||[]):inventoryEntries().sort((a,b)=>b.date.localeCompare(a.date));$("inventoryRows").innerHTML="";entries.forEach(addInventoryRow);renderInventoryBalance();updateInventoryEntryTotal();};
renderInventoryStats=function(){if(!$("inventoryStatsRows"))return;const balances=inventoryBalances(),en=state.language==="en";$("inventoryStatsRows").innerHTML=balances.length?balances.map(row=>{const status=inventoryStatus(row);return `<tr><td>${en?(row.category==="佐料"?"Seasoning":"Ingredient"):row.category}</td><td>${escapeHtml(row.name)}</td><td>${escapeHtml(row.unit||"—")}</td><td>${compactDecimal(row.received)}</td><td>${compactDecimal(row.used)}</td><td>${compactDecimal(row.normalUsed)}</td><td>${compactDecimal(row.loss)}</td><td><strong class="inventory-remaining is-${status.key}">${compactDecimal(row.remaining)}</strong></td><td>${en?status.en:status.zh}</td><td>${escapeHtml(row.lastDate||"—")}</td></tr>`;}).join(""):`<tr><td colspan="10">${en?"No inventory data.":"暂无库存数据。"}</td></tr>`;$("inventoryStatsUpdated").textContent=en?"Live balance":"实时结余";};
function openNormalInventoryAdjustmentModal(key){const row=inventoryBalances().find(item=>inventoryKey(item)===key);if(!row)return;$("proModalHost").innerHTML=`<div class="pro-modal-backdrop"><section class="pro-modal inventory-adjust-modal"><header><h2>正常使用调整</h2><button data-close-modal class="pro-button">关闭</button></header><div class="modal-body"><p><strong>${escapeHtml(row.name)}</strong> · ${escapeHtml(row.unit||"—")}</p><label class="inventory-adjust-field">新的当前剩余量<input data-inventory-value type="number" min="0" max="${escapeHtml(row.remaining)}" step="any" value="${escapeHtml(row.remaining)}"></label><label class="inventory-adjust-field">调整方式<select data-inventory-kind><option value="normal">差值算作正常消耗</option><option value="loss">差值计入损耗</option><option value="overwrite">直接覆盖调整（不影响统计）</option></select></label></div><footer><button data-close-modal class="pro-button">取消</button><button data-inventory-submit class="pro-button green">保存</button></footer></section></div>`;const host=$("proModalHost"),close=()=>closeProModal();host.querySelectorAll("[data-close-modal]").forEach(button=>button.addEventListener("click",close));host.querySelector("[data-inventory-submit]").addEventListener("click",()=>safely(async()=>{const value=Number(host.querySelector("[data-inventory-value]").value),mode=host.querySelector("[data-inventory-kind]").value;if(!Number.isFinite(value)||value<0||(mode!=="overwrite"&&value>row.remaining))throw new Error("调整后的库存不能大于当前剩余量；如需增加库存请选直接覆盖调整。");await applyInventoryBalanceAdjustment(key,mode,value);close();}));}
bindInventoryBalanceActions=function(){document.querySelectorAll("[data-inventory-overwrite]").forEach(button=>button.addEventListener("click",()=>openInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryOverwrite),"overwrite")));document.querySelectorAll("[data-inventory-modify]").forEach(button=>button.addEventListener("click",()=>openInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryModify),"modify")));document.querySelectorAll("[data-inventory-normal]").forEach(button=>button.addEventListener("click",()=>openNormalInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryNormal))));};
const renderInventoryBalanceV24=renderInventoryBalance;
renderInventoryBalance=function(){renderInventoryBalanceV24();document.querySelectorAll(".inventory-balance-actions").forEach(box=>{if(box.querySelector("[data-inventory-normal]"))return;const source=box.querySelector("[data-inventory-modify]");if(!source)return;const button=document.createElement("button");button.className="soft edit-action";button.type="button";button.textContent=state.language==="en"?"Normal-use adjustment":"正常使用调整";button.dataset.inventoryNormal=source.dataset.inventoryModify;button.addEventListener("click",()=>openNormalInventoryAdjustmentModal(decodeURIComponent(button.dataset.inventoryNormal)));box.appendChild(button);});};
const proOriginalRefreshOpenEditors=refreshOpenEditors;
refreshOpenEditors=function(){captureExistingWebEditorDrafts();proOriginalRefreshOpenEditors();};
function normalizeItem(item){return{name:item.name??item.名称??item.食材名称??item.佐料名称??"",quantity:item.quantity??item.数量??"",unit:item.unit??item.单位??"",price:entered(item.price??item.unit_price??item.单价)?num(item.price??item.unit_price??item.单价):"",total:entered(item.total??item.总价)?num(item.total??item.总价):"",note:item.note??item.备注??""};}
/* Historical details can contain only a total price.  When a quantity is
   supplied later, retain that known total and recover unit price first. */
function proDerivedUnitPriceText(total,quantity){const amount=num(total),count=num(quantity);if(!(count>0)||!Number.isFinite(amount))return"";return Exact.price(amount/count);}
function proSyncAmountFields(quantityField,priceField,totalField,source){
  const hasValue=field=>String(field?.value??"").trim()!=="",quantity=num(quantityField?.value);
  if(!(quantity>0))return;
  if((source==="quantity"||source==="price")&&hasValue(priceField)){
    totalField.value=(quantity*num(Exact.price(priceField.value))).toFixed(2);
  }else if((source==="quantity"||source==="total")&&hasValue(totalField)&&!hasValue(priceField)){
    priceField.value=proDerivedUnitPriceText(totalField.value,quantity);
  }
}
function serializeItems(items){return items.filter(item=>item.name).map(item=>{const qty=entered(item.quantity)?item.quantity:"",unit=item.unit||"",total=entered(item.total)?Exact.amount(item.total):"";let text=item.name;if(qty!==""&&unit&&total)text+=` ${qty}${unit} ${total}`;else if(total)text+=` ${total}`;if(item.note)text+=` 备注:${item.note}`;return text;}).join(", ");}
function sumItems(items){return items.reduce((sum,item)=>sum+num(item.total),0);}

function pickerSelectionRows(host){return [...host.querySelectorAll("tbody tr")].filter(tr=>tr.querySelector("[data-pick-check]")?.checked).map(tr=>({name:tr.querySelector("[data-pick-name]").textContent,quantity:tr.querySelector('[data-pick="quantity"]').value,unit:tr.querySelector('[data-pick="unit"]').value,price:tr.querySelector('[data-pick="price"]').value,total:tr.querySelector('[data-pick="total"]').value,note:tr.querySelector('[data-pick="note"]').value}));}
function openItemPicker(category,current,callback,title=""){proPickerCallback=callback;const selected=new Map(parseDetailItems(current).map(item=>[item.name,item])),names=[...new Set([...ingredientDictionary(category),...selected.keys()])];$("proModalHost").innerHTML=`<div class="selector-backdrop"><section class="selector-dialog"><header><h2>${title||` 选择当天的${category}`}</h2><button class="pro-button" data-close-modal>关闭</button></header><div class="modal-body"><div class="desktop-table-wrap"><table class="desktop-table selector-table"><thead><tr><th></th><th>${category}名称</th><th>数量</th><th>单位</th><th>单价（元）</th><th>总价（元）</th><th>备注</th></tr></thead><tbody>${names.map(name=>{const item=selected.get(name)||{name};return `<tr><td><input data-pick-check type="checkbox" ${selected.has(name)?"checked":""}></td><td data-pick-name>${escapeHtml(name)}</td><td><input data-pick="quantity" type="number" step="any" value="${escapeHtml(item.quantity??"")}"></td><td><select data-pick="unit">${proUnitOptions(item.unit)}</select></td><td><input data-pick="price" type="number" step="0.000001" value="${entered(item.price)?num(item.price).toFixed(6):""}"></td><td><input data-pick="total" type="number" step="0.01" value="${entered(item.total)?num(item.total).toFixed(2):""}"></td><td><input data-pick="note" value="${escapeHtml(item.note||"")}"></td></tr>`;}).join("")}</tbody></table></div></div><footer><button data-select-all class="pro-button"> 全选</button><span class="selector-add-inline"><input data-add-word-input aria-label="新增${category}名称" placeholder="新增${category}名称"><button data-add-word class="pro-button">＋ 新增</button></span><button data-manage-units-modal class="pro-button"> 管理单位</button><button data-delete-words class="pro-button red"> 删除勾选词条</button><button data-confirm-picker class="pro-button green confirm"> 确认带回</button></footer></section></div>`;const host=$("proModalHost");const initialSelection=JSON.stringify(pickerSelectionRows(host));host.querySelectorAll("[data-close-modal]").forEach(b=>b.addEventListener("click",closeProModal));host.querySelector("[data-select-all]").addEventListener("click",()=>host.querySelectorAll("[data-pick-check]").forEach(i=>i.checked=true));const addWord=async()=>{const input=host.querySelector("[data-add-word-input]"),word=input.value.trim();if(!word){input.focus();return;}await saveDictionary(category,[...ingredientDictionary(category),word]);openItemPicker(category,current,callback,title);};host.querySelector("[data-add-word]").addEventListener("click",()=>safely(addWord));host.querySelector("[data-add-word-input]").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();safely(addWord);}});host.querySelector("[data-manage-units-modal]").addEventListener("click",manageUnits);host.querySelector("[data-delete-words]").addEventListener("click",async()=>{const remove=[...host.querySelectorAll("tbody tr")].filter(tr=>tr.querySelector("[data-pick-check]").checked).map(tr=>tr.querySelector("[data-pick-name]").textContent);if(remove.length&&confirm(`确定从字库删除 ${remove.length} 个词条吗？`)){await saveDictionary(category,ingredientDictionary(category).filter(name=>!remove.includes(name)));openItemPicker(category,"",callback,title);}});const syncPickerAmounts=(tr,source)=>proSyncAmountFields(tr.querySelector('[data-pick="quantity"]'),tr.querySelector('[data-pick="price"]'),tr.querySelector('[data-pick="total"]'),source);host.querySelectorAll('[data-pick="quantity"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"quantity")));host.querySelectorAll('[data-pick="price"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"price")));host.querySelectorAll('[data-pick="total"]').forEach(input=>input.addEventListener("input",()=>syncPickerAmounts(input.closest("tr"),"total")));host.querySelector("[data-confirm-picker]").addEventListener("click",()=>{const items=pickerSelectionRows(host);if(state.activePage==="ledger"&&["ledgerFoodDetail","ledgerSpiceDetail"].some(id=>$(id)?.value===current)&&JSON.stringify(items)===initialSelection){closeProModal();return;}callback(items);closeProModal();});}
function closeProModal(){$("proModalHost").innerHTML="";}
function manageUnits(){const extra=prompt("请输入要增加的单位（多个用逗号分隔）。现有单位不会被删除：","");if(extra){const list=extra.split(/[,，]/).map(x=>x.trim()).filter(Boolean);localStorage.setItem("restaurant_web_units",JSON.stringify([...new Set([...proUnits(),...list])]));alert("单位已保存。重新打开选择窗口即可使用。");}}

const PRO_LEDGER_DRAFT_FIELDS=["ledgerRevenue","ledgerTotalCash","ledgerACash","ledgerBCash","ledgerTotalOnline","ledgerFees","ledgerAvailableBalance","ledgerShareholderLoan","ledgerAWechatAdd","ledgerAWechatOverride","ledgerAAlipayAdd","ledgerAAlipayOverride","ledgerBWechatAdd","ledgerBWechatOverride","ledgerBAlipayAdd","ledgerBAlipayOverride","ledgerARevenue","ledgerBRevenue","ledgerStudentTakeout","ledgerATakeout","ledgerBTakeout","ledgerNewCustomers","ledgerCustomers","ledgerFoodCost","ledgerSpiceCost","ledgerUtilities","ledgerOther","ledgerFoodDetail","ledgerSpiceDetail","ledgerOtherDetail","ledgerNote"];
const PRO_FIXED_DRAFT_FIELDS=["fixedLabour","fixedRent","fixedWaterSpent","fixedElectricSpent","fixedActualWater","fixedExpectedWater","fixedActualElectric","fixedExpectedElectric","fixedExpectedGas","fixedGas","fixedOther","fixedNote"];
function draftFieldValues(ids){return Object.fromEntries(ids.filter(id=>$(id)).map(id=>[id,$(id).value]));}
function restoreDraftFields(values){Object.entries(values||{}).forEach(([id,value])=>{if($(id))$(id).value=String(value??"");});}
function captureLedgerDraft(key=$("ledgerDate")?.value){if(key)rememberEditorDraft("ledger",key,{values:draftFieldValues(PRO_LEDGER_DRAFT_FIELDS)});}
function captureFixedDraft(key=$("fixedMonth")?.value){if(key)rememberEditorDraft("fixed",key,{values:draftFieldValues(PRO_FIXED_DRAFT_FIELDS)});}
function captureDishesDraft(key=$("dishDate")?.value){if(key&&$("dishRows"))rememberEditorDraft("dishes",key,{rows:collectDishRows(),note:$("dishDayNote")?.value||""});}
function captureDetailDraft(kind,key=$(kind+"Date")?.value){if(key&&$(kind+"Rows"))rememberEditorDraft(kind,key,{rows:detailRows(kind)});}
function collectInventoryDraftRows(){return [...($("inventoryRows")?.querySelectorAll("tr")||[])].map(tr=>({id:tr.dataset.entryId||crypto.randomUUID?.()||String(Date.now()+Math.random()),date:tr.querySelector('[data-inventory="date"]')?.value||"",category:tr.querySelector('[data-inventory="category"]')?.value||"食材",name:tr.querySelector('[data-inventory="name"]')?.value||"",quantity:tr.querySelector('[data-inventory="quantity"]')?.value||"",unit:tr.querySelector('[data-inventory="unit"]')?.value||"",unitPrice:tr.querySelector('[data-inventory="unitPrice"]')?.value||"",total:tr.querySelector('[data-inventory="total"]')?.value||"",note:tr.querySelector('[data-inventory="note"]')?.value||""}));}
function captureInventoryDraft(){if($("inventoryRows"))rememberEditorDraft("inventory","current",{entries:collectInventoryDraftRows()});}
function captureWebEditorDraft(target){
  if(!target?.closest)return false;
  if(target.closest("#pageLedger")){
    if(PRO_FIXED_DRAFT_FIELDS.includes(target.id))captureFixedDraft();
    else captureLedgerDraft();
    return true;
  }
  else if(target.closest("#pageDishes")){captureDishesDraft();return true;}
  else if(target.closest("#pageFood")){captureDetailDraft("food");return true;}
  else if(target.closest("#pageSpice")){captureDetailDraft("spice");return true;}
  else if(target.closest("#pageInventory")){captureInventoryDraft();return true;}
  else if(target.closest("#pageUsers")){captureUsersDraft();return true;}
  return false;
}
window.captureWebEditorDraft=captureWebEditorDraft;
function captureExistingWebEditorDrafts(){
  if(readEditorDraft("ledger",$("ledgerDate")?.value))captureLedgerDraft();
  if(readEditorDraft("fixed",$("fixedMonth")?.value))captureFixedDraft();
  if(readEditorDraft("dishes",$("dishDate")?.value))captureDishesDraft();
  if(readEditorDraft("food",$("foodDate")?.value))captureDetailDraft("food");
  if(readEditorDraft("spice",$("spiceDate")?.value))captureDetailDraft("spice");
  if(readEditorDraft("inventory","current"))captureInventoryDraft();
  if(readEditorDraft("users","current"))captureUsersDraft();
}
function captureBeforeDateChange(id,section,onChange){
  const node=$(id),old=node?.dataset.loadedKey,next=node?.value;
  if(old&&old!==next){
    if(section==="ledger")captureLedgerDraft(old);
    else if(section==="fixed")captureFixedDraft(old);
    else if(section==="dishes")captureDishesDraft(old);
    else if(section==="food"||section==="spice")captureDetailDraft(section,old);
    if(state.editorDirty){
      node.value=old;
      allowEditorNavigation(()=>{
        node.value=next;
        node.dataset.loadedKey=next;
        onChange?.();
      });
      return false;
    }
  }
  if(node)node.dataset.loadedKey=next;
  return true;
}
function syncLedgerRevenueBreakdown(capture=true){const fields=["ledgerACash","ledgerBCash","ledgerAWechatAdd","ledgerAWechatOverride","ledgerAAlipayAdd","ledgerAAlipayOverride","ledgerBWechatAdd","ledgerBWechatOverride","ledgerBAlipayAdd","ledgerBAlipayOverride","ledgerStudentTakeout","ledgerATakeout","ledgerBTakeout"],has=fields.some(id=>$(id)?.value.trim()!==""&&num($(id).value)!==0);if(!has&&capture===false)return;const cashA=num($("ledgerACash").value),cashB=num($("ledgerBCash").value),aWechat=$("ledgerAWechatOverride").value.trim()!==""?num($("ledgerAWechatOverride").value):num($("ledgerAWechatAdd").value),aAlipay=$("ledgerAAlipayOverride").value.trim()!==""?num($("ledgerAAlipayOverride").value):num($("ledgerAAlipayAdd").value),bWechat=$("ledgerBWechatOverride").value.trim()!==""?num($("ledgerBWechatOverride").value):num($("ledgerBWechatAdd").value),bAlipay=$("ledgerBAlipayOverride").value.trim()!==""?num($("ledgerBAlipayOverride").value):num($("ledgerBAlipayAdd").value),student=num($("ledgerStudentTakeout").value),aTakeout=num($("ledgerATakeout").value),bTakeout=num($("ledgerBTakeout").value),a=cashA+aWechat+aAlipay+aTakeout,b=cashB+bWechat+bAlipay+bTakeout;$("ledgerTotalCash").value=(cashA+cashB).toFixed(2);$("ledgerTotalOnline").value=(aWechat+aAlipay+bWechat+bAlipay+student+aTakeout+bTakeout).toFixed(2);$("ledgerARevenue").value=a.toFixed(2);$("ledgerBRevenue").value=b.toFixed(2);$("ledgerRevenue").value=(a+b+student).toFixed(2);if(capture)captureLedgerDraft();}
function refreshLedger(){const key=$("ledgerDate").value||$("selectedDate").value;if(!key)return;$("ledgerDate").dataset.loadedKey=key;const draft=readEditorDraft("ledger",key);if(draft){restoreDraftFields(draft.values);syncLedgerRevenueBreakdown(false);return;}const row=dailyRow(dayPayload(key),key);const map={ledgerRevenue:"收益",ledgerTotalCash:"总现金",ledgerACash:"A店现金",ledgerBCash:"B店现金",ledgerTotalOnline:"总线上",ledgerFees:"手续费",ledgerAvailableBalance:"可用余额",ledgerShareholderLoan:"向股东借款",ledgerAWechatAdd:"A店微信增加",ledgerAWechatOverride:"A店微信覆盖",ledgerAAlipayAdd:"A店支付宝增加",ledgerAAlipayOverride:"A店支付宝覆盖",ledgerBWechatAdd:"B店微信增加",ledgerBWechatOverride:"B店微信覆盖",ledgerBAlipayAdd:"B店支付宝增加",ledgerBAlipayOverride:"B店支付宝覆盖",ledgerARevenue:"A店收入",ledgerBRevenue:"B店收入",ledgerStudentTakeout:"学生外卖",ledgerATakeout:"A店外卖",ledgerBTakeout:"B店外卖",ledgerNewCustomers:"新客人数量",ledgerCustomers:"总客人数",ledgerFoodCost:"食材成本",ledgerSpiceCost:"佐料成本",ledgerUtilities:"水电",ledgerOther:"其他",ledgerFoodDetail:"食材明细",ledgerSpiceDetail:"佐料明细",ledgerOtherDetail:"其他明细",ledgerNote:"当日备注"};Object.entries(map).forEach(([id,name])=>setValue(id,Array.isArray(row[name])?JSON.stringify(row[name]):row[name]));syncLedgerRevenueBreakdown(false);rememberEditorBaseline("ledger",key,{values:draftFieldValues(PRO_LEDGER_DRAFT_FIELDS)});}
function entryDetailUnchanged(row,field,text){const value=row[field]??"";return String(Array.isArray(value)?JSON.stringify(value):value).trim()===String(text).trim();}
function entryDetailStoredValue(row,field,text){return entryDetailUnchanged(row,field,text)?(row[field]??""):text;}
function entryDetailCombinedValue(id){const node=$(id);return node?node.value.trim():"";}
async function saveLedger(){const key=$("ledgerDate").value,payload=dayPayload(key),row=dailyRow(payload,key),foodText=entryDetailCombinedValue("ledgerFoodDetail",true),spiceText=entryDetailCombinedValue("ledgerSpiceDetail",true),otherText=entryDetailCombinedValue("ledgerOtherDetail"),food=parseDetailItems(foodText),spice=parseDetailItems(spiceText),other=parseDetailItems(otherText),entry=currentRole()==="entry";Object.assign(row,{日期:key,收益:blankValue("ledgerRevenue",true),总现金:blankValue("ledgerTotalCash",true),A店现金:blankValue("ledgerACash",true),B店现金:blankValue("ledgerBCash",true),总线上:blankValue("ledgerTotalOnline",true),手续费:num($("ledgerFees").value),可用余额:entered($("ledgerAvailableBalance")?.value)?num($("ledgerAvailableBalance").value):(row.可用余额??""),向股东借款:entered($("ledgerShareholderLoan")?.value)?num($("ledgerShareholderLoan").value):(row.向股东借款??""),A店微信增加:blankValue("ledgerAWechatAdd",true),A店微信覆盖:blankValue("ledgerAWechatOverride",true),A店支付宝增加:blankValue("ledgerAAlipayAdd",true),A店支付宝覆盖:blankValue("ledgerAAlipayOverride",true),B店微信增加:blankValue("ledgerBWechatAdd",true),B店微信覆盖:blankValue("ledgerBWechatOverride",true),B店支付宝增加:blankValue("ledgerBAlipayAdd",true),B店支付宝覆盖:blankValue("ledgerBAlipayOverride",true),A店收入:blankValue("ledgerARevenue",true),B店收入:blankValue("ledgerBRevenue",true),学生外卖:blankValue("ledgerStudentTakeout",true),A店外卖:blankValue("ledgerATakeout",true),B店外卖:blankValue("ledgerBTakeout",true),新客人数量:blankValue("ledgerNewCustomers",true),总客人数:blankValue("ledgerCustomers",true),食材明细:entryDetailUnchanged(row,"食材明细",foodText)?row.食材明细:(entry?foodText:serializeItems(food)),食材成本:entryDetailUnchanged(row,"食材明细",foodText)?(row.食材成本??0):sumItems(food)||num($("ledgerFoodCost").value),佐料明细:entryDetailUnchanged(row,"佐料明细",spiceText)?row.佐料明细:(entry?spiceText:serializeItems(spice)),佐料成本:entryDetailUnchanged(row,"佐料明细",spiceText)?(row.佐料成本??0):sumItems(spice)||num($("ledgerSpiceCost").value),水电:num($("ledgerUtilities").value),其他:entryDetailUnchanged(row,"其他明细",otherText)?(row.其他??0):sumItems(other)||num($("ledgerOther").value),其他明细:entryDetailStoredValue(row,"其他明细",otherText),当日备注:$("ledgerNote").value});payload.daily=[row];await saveRecord("day",key,payload,"ledgerResult");forgetEditorDraft("ledger",key);}
async function syncWechatBill(){const key=$("ledgerDate").value;if(!key)throw new Error("请先选择要同步的日期。");if(key>=isoDate(new Date()))throw new Error("微信交易账单只能同步已经结束的历史日期；当天账单需次日上午10点后获取。");if(!state.dataset?.id)throw new Error("当前没有可用账本。");if(state.editorDirty&&!confirm("当前页面有未保存修改。同步微信账单会从云端重新加载这一天，是否继续？"))return;const button=$("syncWechatButton"),result=$("ledgerResult");button.disabled=true;result.textContent="正在向微信支付获取交易账单……";try{const response=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/wechat/sync?bill_date=${encodeURIComponent(key)}`,{method:"POST"});forgetEditorDraft("ledger",key);await loadCloudData({silent:true,datasetId:state.dataset.id});refreshLedger();renderHistory();renderDashboard();const stores=response?.stores||{},parts=[];if(stores.A)parts.push(`A店微信 ${money(stores.A.amount)}`);if(stores.B)parts.push(`B店微信 ${money(stores.B.amount)}`);result.textContent=`微信账单同步完成${parts.length?"："+parts.join("；"):""}`;}finally{button.disabled=false;}}

function monthExpenseRows(month){const rows=[];for(const record of state.records){if(String(record.record_type||record.type)!=="day")continue;const payload=unpackPayload(record);for(const row of (payload.fixed_expenses||[]))if(String(row.日期||"").startsWith(month))rows.push({...row});}return rows.sort((a,b)=>String(a.日期).localeCompare(String(b.日期)));}
function fixedCategories(){const record=currentRecord("global","fixed_categories"),payload=record?unpackPayload(record):{},rows=Array.isArray(payload.fixed_categories)?payload.fixed_categories:[],names=rows.map(row=>String(row.类别名称||"").trim()).filter(Boolean);return [...new Set([...names,"水费","电费","煤气费","人工","房租及物业费","其它"])];}
async function manageFixedCategories(){const current=fixedCategories(),answer=prompt("请按显示顺序输入固定成本类别，多个类别用逗号分隔：",current.join("，"));if(answer===null)return false;const names=[...new Set(answer.split(/[,，]/).map(name=>name.trim()).filter(Boolean))];if(!names.length)throw new Error("至少保留一个固定成本类别。");const record=currentRecord("global","fixed_categories"),payload=clone(record?unpackPayload(record):{});payload.fixed_categories=names.map(name=>({类别名称:name}));await saveRecord("global","fixed_categories",payload);return true;}
function refreshFixed(){const key=$("fixedMonth").value;if(!key)return;$("fixedMonth").dataset.loadedKey=key;const draft=readEditorDraft("fixed",key);if(draft){restoreDraftFields(draft.values);}else{const row=state.months.get(key)||{},values={fixedLabour:"人工总额",fixedRent:"房租总额",fixedWaterSpent:"水费支出",fixedElectricSpent:"电费支出",fixedActualWater:"实际使用水费",fixedExpectedWater:"预计水费",fixedActualElectric:"实际使用电费",fixedExpectedElectric:"预计电费",fixedExpectedGas:"预计煤气费",fixedGas:"煤气费",fixedOther:"其它固定成本",fixedNote:"月度备注"};Object.entries(values).forEach(([id,name])=>setValue(id,Array.isArray(row[name])?JSON.stringify(row[name]):row[name]));}const expenses=monthExpenseRows(key),f=fixedBreakdown(Number(key.slice(0,4)),Number(key.slice(5)));$("fixedSummary").innerHTML=`<span>本月实际支出合计 <strong>${money(f.spentTotal)}</strong></span><span>成本计算：水费 <strong>${money(f.water)}</strong></span><span>电费 <strong>${money(f.electric)}</strong></span><span>煤气费 <strong>${money(f.gas)}</strong></span><span>固定成本口径合计 <strong>${money(f.effectiveTotal)}</strong></span><span>逐笔记录 <strong>${expenses.length}</strong></span>`;}
async function saveFixed(){const key=$("fixedMonth").value,record=currentRecord("month",key),payload=clone(record?unpackPayload(record):{}),row=clone((payload.monthly_fixed||[]).slice(-1)[0]||{月份:key});row.月份=key;row.实际使用水费=$("fixedActualWater").value.trim()===""?"":num($("fixedActualWater").value);row.预计水费=blankValue("fixedExpectedWater",true);row.实际使用电费=$("fixedActualElectric").value.trim()===""?"":num($("fixedActualElectric").value);row.预计电费=blankValue("fixedExpectedElectric",true);row.预计煤气费=blankValue("fixedExpectedGas",true);payload.monthly_fixed=[row];await saveRecord("month",key,payload,"fixedResult");forgetEditorDraft("fixed",key);}
function openFixedExpensesModal(){const month=$("fixedMonth").value,rows=monthExpenseRows(month),categories=["水费","电费","煤气费","人工","房租及物业费","其它"];$("proModalHost").innerHTML=`<div class="pro-modal-backdrop"><section class="pro-modal"><header><h2> ${month} 增加／修改 固定成本</h2><button data-close-modal class="pro-button">关闭</button></header><div class="modal-body"><div class="stats-command-bar"><strong>显示类别：</strong>${categories.map(c=>`<label><input type="checkbox" checked> ${c}</label>`).join("")}<button data-add-fixed class="pro-button">＋ 新增一笔</button></div><p>显示范围：${month}-01 至 ${month}-${daysInMonth(Number(month.slice(0,4)),Number(month.slice(5)))}（整月固定成本支出）</p><div class="desktop-table-wrap"><table class="desktop-table"><thead><tr><th></th><th>支出日期</th><th>类别</th><th>对象／说明</th><th>金额（元）</th></tr></thead><tbody id="fixedExpenseRows"></tbody></table></div></div><footer><button data-delete-fixed class="pro-button red"> 删除选中支出</button><span class="grow"></span><strong id="fixedExpenseTotal"></strong><button data-save-fixed class="pro-button green"> 保存修改</button></footer></section></div>`;const add=(data={})=>{const tr=document.createElement("tr");tr.innerHTML=`<td><input data-fixed-check type="checkbox"></td><td><input data-fixed="日期" type="date" value="${escapeHtml(data.日期||month+"-01")}"></td><td><select data-fixed="类别">${categories.map(c=>`<option ${c===data.类别?"selected":""}>${c}</option>`).join("")}</select></td><td><input data-fixed="明细" value="${escapeHtml(data.明细||"")}"></td><td><input data-fixed="金额" type="number" step="0.01" value="${entered(data.金额)?num(data.金额).toFixed(2):""}"></td>`;$("fixedExpenseRows").appendChild(tr);tr.querySelector('[data-fixed="金额"]').addEventListener("input",update);update();};const update=()=>{$("fixedExpenseTotal").textContent="当前显示合计："+money([...$("fixedExpenseRows").querySelectorAll('[data-fixed="金额"]')].reduce((s,i)=>s+num(i.value),0));};rows.forEach(add);$("proModalHost").querySelector("[data-close-modal]").addEventListener("click",closeProModal);$("proModalHost").querySelector("[data-add-fixed]").addEventListener("click",()=>add());$("proModalHost").querySelector("[data-delete-fixed]").addEventListener("click",()=>{$("fixedExpenseRows").querySelectorAll("tr").forEach(tr=>{if(tr.querySelector("[data-fixed-check]").checked)tr.remove();});update();});$("proModalHost").querySelector("[data-save-fixed]").addEventListener("click",()=>safely(async()=>{const next=[...$("fixedExpenseRows").querySelectorAll("tr")].map(tr=>Object.fromEntries([...tr.querySelectorAll("[data-fixed]")].map(input=>[input.dataset.fixed,input.dataset.fixed==="金额"?num(input.value):input.value]))).filter(row=>row.日期&&row.金额>0);const byDate=new Map();for(const row of next){if(!byDate.has(row.日期))byDate.set(row.日期,[]);byDate.get(row.日期).push(row);}const oldDates=[...new Set(rows.map(r=>r.日期))];for(const date of new Set([...oldDates,...byDate.keys()])){const payload=dayPayload(date);payload.fixed_expenses=byDate.get(date)||[];await saveRecord("day",date,payload);}await rebuildMonthFixedFromExpenses(month,next);closeProModal();refreshFixed();}));}
/* Keep the legacy modal markup above callable for old cached scripts, while
   this definition adds the balance-inclusion flag to every fixed expense. */
function openFixedExpensesModal(){
  const month=$("fixedMonth").value,rows=monthExpenseRows(month),categories=["水费","电费","煤气费","人工","房租及物业费","其它"];
  $("proModalHost").innerHTML=`<div class="pro-modal-backdrop"><section class="pro-modal"><header><h2> ${month} 增加／修改 固定成本</h2><button data-close-modal class="pro-button">关闭</button></header><div class="modal-body"><div class="stats-command-bar"><strong>显示类别：</strong>${categories.map(c=>`<label><input type="checkbox" checked> ${c}</label>`).join("")}<button data-add-fixed class="pro-button">＋ 新增一笔</button></div><p>显示范围：${month}-01 至 ${month}-${daysInMonth(Number(month.slice(0,4)),Number(month.slice(5)))}（整月固定成本支出）</p><div class="desktop-table-wrap"><table class="desktop-table"><thead><tr><th></th><th>支出日期</th><th>类别</th><th>对象／说明</th><th>金额（元）</th><th>计入可用余额</th></tr></thead><tbody id="fixedExpenseRows"></tbody></table></div></div><footer><button data-delete-fixed class="pro-button red"> 删除选中支出</button><span class="grow"></span><strong id="fixedExpenseTotal"></strong><button data-save-fixed class="pro-button green"> 保存修改</button></footer></section></div>`;
  const add=(data={})=>{
    const tr=document.createElement("tr"),include=fixedExpenseCountsForCash(data);
    tr.innerHTML=`<td><input data-fixed-check type="checkbox"></td><td><input data-fixed="日期" type="date" value="${escapeHtml(data.日期||month+"-01")}"></td><td><select data-fixed="类别">${categories.map(c=>`<option ${c===data.类别?"selected":""}>${c}</option>`).join("")}</select></td><td><input data-fixed="明细" value="${escapeHtml(data.明细||"")}"></td><td><input data-fixed="金额" type="number" step="0.01" value="${entered(data.金额)?num(data.金额).toFixed(2):""}"></td><td class="fixed-cash-checkbox"><input data-fixed="计入可用余额" type="checkbox" ${include?"checked":""} aria-label="计入可用余额"></td>`;
    $("fixedExpenseRows").appendChild(tr);tr.querySelector('[data-fixed="金额"]').addEventListener("input",update);update();
  };
  const update=()=>{$("fixedExpenseTotal").textContent="当前显示合计："+money([...$("fixedExpenseRows").querySelectorAll('[data-fixed="金额"]')].reduce((s,i)=>s+num(i.value),0));};
  rows.forEach(add);
  $("proModalHost").querySelector("[data-close-modal]").addEventListener("click",closeProModal);
  $("proModalHost").querySelector("[data-add-fixed]").addEventListener("click",()=>add());
  $("proModalHost").querySelector("[data-delete-fixed]").addEventListener("click",()=>{$("fixedExpenseRows").querySelectorAll("tr").forEach(tr=>{if(tr.querySelector("[data-fixed-check]").checked)tr.remove();});update();});
  $("proModalHost").querySelector("[data-save-fixed]").addEventListener("click",()=>safely(async()=>{
    const next=[...$("fixedExpenseRows").querySelectorAll("tr")].map(tr=>{const result={};tr.querySelectorAll("[data-fixed]").forEach(input=>{const key=input.dataset.fixed;result[key]=key==="金额"?num(input.value):key==="计入可用余额"?input.checked:input.value;});return result;}).filter(row=>row.日期&&row.金额>0);
    const byDate=new Map();for(const row of next){if(!byDate.has(row.日期))byDate.set(row.日期,[]);byDate.get(row.日期).push(row);}const oldDates=[...new Set(rows.map(r=>r.日期))];
    for(const date of new Set([...oldDates,...byDate.keys()])){const payload=dayPayload(date);payload.fixed_expenses=byDate.get(date)||[];await saveRecord("day",date,payload);}
    await rebuildMonthFixedFromExpenses(month,next);closeProModal();refreshFixed();
  }));
}

async function rebuildMonthFixedFromExpenses(month,rows){const totals={};for(const row of rows)totals[row.类别]=(totals[row.类别]||0)+num(row.金额);const record=currentRecord("month",month),payload=clone(record?unpackPayload(record):{}),old=clone((payload.monthly_fixed||[]).slice(-1)[0]||{});Object.assign(old,{月份:month,人工总额:totals["人工"]||0,房租总额:totals["房租及物业费"]||0,水费支出:totals["水费"]||0,电费支出:totals["电费"]||0,水电费:(totals["水费"]||0)+(totals["电费"]||0),煤气费:totals["煤气费"]||0,其它固定成本:totals["其它"]||0,月度备注:rows.filter(r=>r.类别==="房租及物业费").map(r=>r.明细).filter(Boolean).join("；")});payload.monthly_fixed=[old];await saveRecord("month",month,payload);}

function dishRowMarkup(data={},fixed=false){const servings=data.份数??data.菜品份数??"";return `<tr class="${fixed?"fixed-project-row":""}"><td>${fixed?"<input data-dish=\"name\" readonly":"<input data-dish-check type=\"checkbox\"><input data-dish=\"name\""} value="${escapeHtml(data.菜品名称||"")}"></td><td><input data-dish="servings" type="number" min="0" step="1" value="${escapeHtml(servings)}"></td><td><textarea data-dish="detail" readonly>${escapeHtml(data.食材明细||"")}</textarea></td><td><input data-dish="cost" readonly value="${entered(data.成本)?num(data.成本).toFixed(2):""}"></td><td><input data-dish="note" value="${escapeHtml(data.备注||"")}"></td><td><button data-pick-dish class="pro-button edit-action"> 选择／修改食材</button></td></tr>`;}
function addDishRow(data={}){$("dishRows").insertAdjacentHTML("beforeend",dishRowMarkup(data,false));bindDishRow($("dishRows").lastElementChild);updateDishTotal();}
function bindDishRow(tr){tr.querySelector("[data-pick-dish]").addEventListener("click",()=>{const name=tr.querySelector('[data-dish="name"]').value||"这道菜";openItemPicker("食材",tr.querySelector('[data-dish="detail"]').value,items=>{tr.querySelector('[data-dish="detail"]').value=serializeItems(items);tr.querySelector('[data-dish="cost"]').value=sumItems(items).toFixed(2);updateDishTotal();updateDishSummary();captureDishesDraft();},` 选择「${name}」使用的食材`);});tr.querySelectorAll("input").forEach(input=>input.addEventListener("input",()=>{updateDishTotal();updateDishSummary();}));}
function refreshDishes(){const key=$("dishDate").value;if(!key)return;$("dishDate").dataset.loadedKey=key;const draft=readEditorDraft("dishes",key),source=draft?{rows:draft.rows||[],raw:{备注:draft.note||""}}:dishData(key),rows=source.rows||[],regular=rows.filter(r=>(r.分区||"菜品")!=="固定项目"),fixed=rows.filter(r=>r.分区==="固定项目");$("dishRows").innerHTML="";regular.forEach(addDishRow);if(!regular.length)addDishRow();$("fixedDishRows").innerHTML="";for(const name of PRO_FIXED_NAMES){const data=fixed.find(r=>r.菜品名称===name)||{菜品名称:name};$("fixedDishRows").insertAdjacentHTML("beforeend",dishRowMarkup(data,true));bindDishRow($("fixedDishRows").lastElementChild);}$("dishDayNote").value=source.raw?.备注||"";updateDishTotal();updateDishSummary();}
function collectDishRows(){return [...document.querySelectorAll("#dishRows tr,#fixedDishRows tr")].map(tr=>({菜品名称:tr.querySelector('[data-dish="name"]').value.trim(),份数:num(tr.querySelector('[data-dish="servings"]').value),食材明细:tr.querySelector('[data-dish="detail"]').value,成本:num(tr.querySelector('[data-dish="cost"]').value),备注:tr.querySelector('[data-dish="note"]').value,分区:tr.closest("tbody").id==="fixedDishRows"?"固定项目":"菜品"})).filter(r=>r.分区==="固定项目"?r.份数||r.食材明细||r.成本||r.备注:r.菜品名称||r.食材明细);}
function deleteSelectedDish(){$("dishRows").querySelectorAll("tr").forEach(tr=>{if(tr.querySelector("[data-dish-check]")?.checked)tr.remove();});updateDishTotal();updateDishSummary();}
function updateDishTotal(){const total=collectDishRows().reduce((s,r)=>s+r.成本,0);$("dishTotal").textContent="当日全部食材成本合计："+money(total);}
function updateDishSummary(){const map=new Map();for(const row of collectDishRows())for(const item of parseDetailItems(row.食材明细)){const key=`${item.name}|${item.unit}`,data=map.get(key)||{name:item.name,unit:item.unit,quantity:0,cost:0,sources:[]};data.quantity+=num(item.quantity);data.cost+=num(item.total);if(!data.sources.includes(row.菜品名称))data.sources.push(row.菜品名称);map.set(key,data);}$("dishIngredientSummary").innerHTML=[...map.values()].map(i=>`<tr><td>${escapeHtml(i.name)}</td><td>${compactNumber(i.quantity)}</td><td>${escapeHtml(i.unit||"—")}</td><td>${money(i.cost)}</td><td>${escapeHtml(i.sources.join("、"))}</td></tr>`).join("")||'<tr><td colspan="5">尚未选择食材</td></tr>';}
async function saveDishes(){const key=$("dishDate").value,{payload,raw}=dishData(key),rows=collectDishRows(),total=rows.reduce((s,r)=>s+r.成本,0);Object.assign(raw,{日期:key,菜品明细:rows.map(r=>r.菜品名称).filter(Boolean).join("；"),菜品数据:JSON.stringify(rows),总成本:total,备注:$("dishDayNote").value});payload.dishes=[raw];await saveRecord("day",key,payload,"dishResult");forgetEditorDraft("dishes",key);}

function addDetailRow(kind,data={}){
  const item=normalizeItem(data),tr=document.createElement("tr");
  tr.innerHTML=`<td><input data-detail-check type="checkbox"></td><td><input data-detail="name" value="${escapeHtml(item.name)}"></td><td><input data-detail="quantity" type="number" step="any" value="${escapeHtml(item.quantity)}"></td><td><select data-detail="unit">${proUnitOptions(item.unit)}</select></td><td><input data-detail="price" type="number" step="0.000001" value="${entered(item.price)?num(item.price).toFixed(6):""}"></td><td><input data-detail="total" type="number" step="0.01" value="${entered(item.total)?num(item.total).toFixed(2):""}"></td><td><input data-detail="note" value="${escapeHtml(item.note)}"></td>`;
  $(kind+"Rows").appendChild(tr);
  const quantityField=tr.querySelector('[data-detail="quantity"]'),priceField=tr.querySelector('[data-detail="price"]'),totalField=tr.querySelector('[data-detail="total"]');
  const recalculate=source=>{proSyncAmountFields(quantityField,priceField,totalField,source);updateDetailTotal(kind);};
  quantityField.addEventListener("input",()=>recalculate("quantity"));
  priceField.addEventListener("input",()=>recalculate("price"));
  totalField.addEventListener("input",()=>recalculate("total"));
  tr.querySelectorAll("input,select").forEach(i=>i.addEventListener("input",()=>updateDetailTotal(kind)));
}
function detailRows(kind){return [...$(kind+"Rows").querySelectorAll("tr")].map(tr=>({name:tr.querySelector('[data-detail="name"]').value.trim(),quantity:tr.querySelector('[data-detail="quantity"]').value,unit:tr.querySelector('[data-detail="unit"]').value,price:tr.querySelector('[data-detail="price"]').value,total:tr.querySelector('[data-detail="total"]').value,note:tr.querySelector('[data-detail="note"]').value})).filter(i=>i.name);}
function refreshDetail(kind){const key=$(kind+"Date").value;if(!key)return;$(kind+"Date").dataset.loadedKey=key;const draft=readEditorDraft(kind,key),items=draft?(draft.rows||[]):parseDetailItems(dailyRow(dayPayload(key),key)[kind==="food"?"食材明细":"佐料明细"]);$(kind+"Rows").innerHTML="";items.forEach(item=>addDetailRow(kind,item));if(!items.length)addDetailRow(kind);updateDetailTotal(kind);}
function updateDetailTotal(kind){const rows=detailRows(kind);$(kind+"Total").textContent=`${kind==="food"?"食材":"佐料"}种类：${rows.length}　总金额：${money(sumItems(rows))}`;}
async function saveDetail(kind){const key=$(kind+"Date").value,payload=dayPayload(key),row=dailyRow(payload,key),items=detailRows(kind),total=sumItems(items);row.日期=key;row[kind==="food"?"食材明细":"佐料明细"]=serializeItems(items);row[kind==="food"?"食材成本":"佐料成本"]=total;payload.daily=[row];await saveRecord("day",key,payload,kind+"Result");forgetEditorDraft(kind,key);}
function deleteDetailRows(kind){$(kind+"Rows").querySelectorAll("tr").forEach(tr=>{if(tr.querySelector("[data-detail-check]").checked)tr.remove();});updateDetailTotal(kind);}
async function moveDetailRows(kind){const selected=[...$(kind+"Rows").querySelectorAll("tr")].filter(tr=>tr.querySelector("[data-detail-check]").checked);if(!selected.length)throw new Error("请先勾选要移动的行。");const key=$(kind+"Date").value,payload=dayPayload(key),row=dailyRow(payload,key),source=detailRows(kind),selectedNames=new Set(selected.map(tr=>tr.querySelector('[data-detail="name"]').value)),moved=source.filter(i=>selectedNames.has(i.name)),remain=source.filter(i=>!selectedNames.has(i.name)),other=kind==="food"?"spice":"food",otherItems=parseDetailItems(row[other==="food"?"食材明细":"佐料明细"]);row[kind==="food"?"食材明细":"佐料明细"]=serializeItems(remain);row[kind==="food"?"食材成本":"佐料成本"]=sumItems(remain);row[other==="food"?"食材明细":"佐料明细"]=serializeItems([...otherItems,...moved]);row[other==="food"?"食材成本":"佐料成本"]=sumItems([...otherItems,...moved]);payload.daily=[row];await saveRecord("day",key,payload);forgetEditorDraft(kind,key);forgetEditorDraft(other,$(other+"Date").value);refreshDetail(kind);refreshDetail(other);}

const proStatsMetrics={revenue:["收入","Revenue",m=>m.revenue],gross:["毛利润","Gross Profit",m=>m.gross],grossRate:["毛利率（%）","Gross Margin (%)",m=>m.revenue?m.gross/m.revenue*100:0],net:["净利润","Net Profit",m=>m.net],netRate:["净利率（%）","Net Margin (%)",m=>m.revenue?m.net/m.revenue*100:0],customers:["总客人数","Total Customers",m=>m.customers],newCustomers:["新客人数量","New Customers",m=>m.newCustomers],oldCustomers:["老客人数","Returning Customers",m=>m.oldCustomers],newRatio:["新客比例（%）","New Customer Ratio (%)",m=>m.customers?m.newCustomers/m.customers*100:0],oldRatio:["老客比例（%）","Returning Customer Ratio (%)",m=>m.customers?m.oldCustomers/m.customers*100:0],ticket:["客单价（平均）","Average Spend",m=>m.customers?m.revenue/m.customers:0],foodSpice:["食材＋佐料成本","Ingredient + Seasoning",m=>m.food+m.spice],utilities:["水电＋其他","Utilities + Other",m=>m.waterDaily+m.other],fixedDaily:["固定成本","Fixed Cost",m=>m.fixedDaily],variable:["（总成本－固定成本）","Variable Cost",m=>m.variable],total:["总成本","Total Cost",m=>m.total]};
function initializeStats(){const years=[...new Set(state.days.map(r=>String(r.日期).slice(0,4)))].sort().reverse();if(!years.length)years.push(String(new Date().getFullYear()));$("statsYear").innerHTML=years.map(y=>`<option>${y}</option>`).join("");if(!$("statsMonthChecks").querySelector("input")){for(let m=1;m<=12;m++)$("statsMonthChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${m}" ${m===Number($("selectedMonth").value)?"checked":""}> ${m}月</label>`);$("statsMonthChecks").insertAdjacentHTML("beforeend",`<button data-month-preset="previous" class="pro-button">上个月</button><button data-month-preset="current" class="pro-button">本月</button><button data-month-preset="next" class="pro-button">下个月</button><button data-month-preset="1,2,3" class="pro-button">Q1</button><button data-month-preset="4,5,6" class="pro-button">Q2</button><button data-month-preset="7,8,9" class="pro-button">Q3</button><button data-month-preset="10,11,12" class="pro-button">Q4</button><button data-month-preset="all" class="pro-button">全选</button><button data-month-preset="none" class="pro-button">全不选</button>`);["一","二","三","四","五","六","日"].forEach((name,index)=>$("statsWeekdayChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${index}" checked> ${name}</label>`));$("statsWeekdayChecks").insertAdjacentHTML("beforeend",`<button data-week-preset="all" class="pro-button">全选</button><button data-week-preset="none" class="pro-button">全不选</button><button data-week-preset="work" class="pro-button">工作日</button><button data-week-preset="weekend" class="pro-button">周末</button>`);Object.entries(proStatsMetrics).forEach(([key,item])=>$("statsMetricChecks").insertAdjacentHTML("beforeend",`<label><input type="checkbox" value="${key}" ${key==="net"?"checked":""}> <span data-pro-metric="${key}">${item[state.language==="en"?1:0]}</span></label>`));$("pageStats").querySelectorAll("input,select").forEach(i=>i.addEventListener("change",renderStats));$("pageStats").querySelectorAll("[data-month-preset]").forEach(b=>b.addEventListener("click",()=>applyMonthPreset(b.dataset.monthPreset)));$("pageStats").querySelectorAll("[data-week-preset]").forEach(b=>b.addEventListener("click",()=>applyWeekPreset(b.dataset.weekPreset)));}renderStats();}
function applyMonthPreset(value){let months=[];const now=new Date(),base=now.getMonth()+1;if(value==="all")months=Array.from({length:12},(_,i)=>i+1);else if(value==="none")months=[];else if(value==="previous")months=[base===1?12:base-1];else if(value==="current")months=[base];else if(value==="next")months=[base===12?1:base+1];else months=value.split(",").map(Number);document.querySelectorAll("#statsMonthChecks input").forEach(i=>i.checked=months.includes(Number(i.value)));renderStats();}
function applyWeekPreset(value){const chosen=value==="all"?[0,1,2,3,4,5,6]:value==="work"?[0,1,2,3,4]:value==="weekend"?[5,6]:[];document.querySelectorAll("#statsWeekdayChecks input").forEach(i=>i.checked=chosen.includes(Number(i.value)));renderStats();}
function selectedProMetrics(){const list=[...document.querySelectorAll("#statsMetricChecks input:checked")].map(i=>i.value);return list.length?list:["net"];}
function filteredStatsItems(){const year=$("statsYear").value,months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(i=>Number(i.value)),week=[...document.querySelectorAll("#statsWeekdayChecks input:checked")].map(i=>Number(i.value));return state.days.map(dayMetrics).filter(m=>m&&m.date.startsWith(year+"-")&&months.includes(Number(m.date.slice(5,7)))&&week.includes((parseDate(m.date).getDay()+6)%7));}
function proMetricText(key,value,m){if(["grossRate","netRate","newRatio","oldRatio"].includes(key))return `${value.toFixed(1)}%`;if(key==="gross"||key==="net")return `${Number(value).toLocaleString(undefined,{maximumFractionDigits:2})} (${percent(value,m.revenue)})`;if(["customers","newCustomers","oldCustomers"].includes(key))return compactNumber(value);return Number(value).toLocaleString(undefined,{maximumFractionDigits:2});}
function statsDateAllowed(date){const year=$("statsYear").value,months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(i=>Number(i.value)),week=[...document.querySelectorAll("#statsWeekdayChecks input:checked")].map(i=>Number(i.value));return String(date).startsWith(year+"-")&&months.includes(Number(String(date).slice(5,7)))&&week.includes((parseDate(String(date)).getDay()+6)%7);}
function statsPurchaseRows(){const rows=[];for(const day of state.days){const date=String(day.日期||"");if(!statsDateAllowed(date))continue;for(const item of parseDetailItems(day.食材明细)){if(!proSelectedPurchase.includes(item.name)||!num(item.quantity))continue;rows.push({date,name:item.name,unit:item.unit||"无单位",quantity:num(item.quantity),total:num(item.total),price:num(item.total)/num(item.quantity)});}}return rows;}
function statsConsumptionRows(){const rows=[];for(const day of state.days){const date=String(day.日期||"");if(!statsDateAllowed(date))continue;const {rows:dishes}=dishData(date);for(const dish of dishes)for(const item of parseDetailItems(dish.食材明细)){if(!proSelectedConsumption.includes(item.name)||!num(item.quantity))continue;rows.push({date,name:item.name,unit:item.unit||"无单位",quantity:num(item.quantity),total:num(item.total),dish:dish.菜品名称||"未命名菜品"});}}return rows;}
function aggregateByDate(rows,value){const map=new Map();for(const row of rows){const item=map.get(row.date)||{date:row.date,quantity:0,total:0,count:0};item.quantity+=row.quantity;item.total+=row.total;item.count++;map.set(row.date,item);}return [...map.values()].sort((a,b)=>a.date.localeCompare(b.date)).map(item=>({date:item.date,value:value(item),revenue:0}));}
function aggregateByMonth(rows,value){return Array.from({length:12},(_,index)=>{const month=index+1,list=rows.filter(row=>Number(row.date.slice(5,7))===month),quantity=list.reduce((s,row)=>s+row.quantity,0),total=list.reduce((s,row)=>s+row.total,0),days=new Set(list.map(row=>row.date)).size;return{label:`${month}月`,value:value({quantity,total,days}),revenue:0};});}
function proStatsCell(value,display=value){return{value,display};}
function proSetStatsTable(headers,rows,emptyMessage="当前筛选条件没有可导出的数据"){
  const cellParts=cell=>cell&&typeof cell==="object"&&Object.prototype.hasOwnProperty.call(cell,"value")?cell:{value:cell,display:cell};
  proLastStatsExport={headers:[...headers],rows:rows.map(row=>row.map(cell=>cellParts(cell).value))};
  $("statsHead").innerHTML=`<tr>${headers.map(header=>`<th>${escapeHtml(String(header))}</th>`).join("")}</tr>`;
  $("statsRows").innerHTML=rows.length?rows.map(row=>`<tr>${row.map(cell=>`<td>${escapeHtml(String(cellParts(cell).display??""))}</td>`).join("")}</tr>`).join(""):`<tr><td colspan="${Math.max(1,headers.length)}">${escapeHtml(emptyMessage)}</td></tr>`;
}
function proGroupStatsRows(rows,keyOf){const groups=new Map();for(const row of rows){const key=keyOf(row);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}return [...groups.values()];}
function renderIngredientStats(type){
  for(const id of ["statsMonthlyChart","statsWeekdayChart"]){const node=$(id);node.classList.remove("business-grouped-chart");node.style.removeProperty("height");node.style.removeProperty("padding");}
  const purchase=type==="purchase",rows=purchase?statsPurchaseRows():statsConsumptionRows(),metric=purchase?$("purchaseMetric").value:$("consumptionMetric").value,names=purchase?proSelectedPurchase:proSelectedConsumption,title=names.join("、"),value=purchase?(item=>metric==="unit"||metric==="monthlyAverageUnit"?(item.quantity?item.total/item.quantity:0):metric==="monthlyTotal"?item.total:item.quantity):(item=>item.quantity);
  let points=aggregateByDate(rows,value);
  if(!purchase&&metric==="cumulative"){let running=0;points=points.map(point=>({...point,value:(running+=point.value)}));}
  $("statsTrendTitle").textContent=`${title} · ${purchase?$("purchaseMetric").selectedOptions[0].textContent:$("consumptionMetric").selectedOptions[0].textContent}`;
  $("statsChart").innerHTML=proLineSvg(points,false,"ingredient");bindInteractiveChart($("statsChart"));
  const monthly=aggregateByMonth(rows,item=>purchase?value(item):(metric==="monthlyAverage"?(item.days?item.quantity/item.days:0):item.quantity));renderProBars($("statsMonthlyChart"),monthly,"ingredient");
  const weekNames=["周一","周二","周三","周四","周五","周六","周日"],groups=weekNames.map(()=>[]);rows.forEach(row=>groups[(parseDate(row.date).getDay()+6)%7].push(row));renderWeekBars($("statsWeekdayChart"),groups.map((group,index)=>{const quantity=group.reduce((s,row)=>s+row.quantity,0),total=group.reduce((s,row)=>s+row.total,0),days=new Set(group.map(row=>row.date)).size;return{label:weekNames[index],value:purchase?value({quantity,total,days}):(days?quantity/days:0),revenue:0};}),"ingredient");
  const detail=$("statsDetail").checked,average=$("statsAverage").checked;
  if(purchase){
    const tableRows=[];
    if(detail&&metric==="unit")for(const row of rows)tableRows.push(["采购明细",row.date,row.name,proStatsCell(row.quantity,compactDecimal(row.quantity)),row.unit,proStatsCell(row.total,money(row.total)),proStatsCell(row.price,compactDecimal(row.price)),"",""]);
    if(rows.length&&(average||metric!=="unit"))for(const group of proGroupStatsRows(rows,row=>`${row.date.slice(0,7)}\u0000${row.name}\u0000${row.unit}`)){
      const first=group[0],quantity=group.reduce((sum,row)=>sum+row.quantity,0),total=group.reduce((sum,row)=>sum+row.total,0),days=Math.max(1,new Set(group.map(row=>row.date)).size);
      tableRows.push(["月度汇总",first.date.slice(0,7),first.name,proStatsCell(quantity,compactDecimal(quantity)),first.unit,proStatsCell(total,money(total)),proStatsCell(quantity?total/quantity:0,compactDecimal(quantity?total/quantity:0)),proStatsCell(total/days,money(total/days)),proStatsCell(quantity/days,compactDecimal(quantity/days))]);
    }
    proSetStatsTable(["类型","日期／月份","食材","数量","单位","总价","单价","采购日均总价","采购日均数量"],tableRows,"当前筛选条件没有所选食材采购记录");
  }else{
    const tableRows=[];
    if(detail)for(const group of proGroupStatsRows(rows,row=>`${row.date}\u0000${row.name}\u0000${row.unit}`)){
      const first=group[0],quantity=group.reduce((sum,row)=>sum+row.quantity,0),total=group.reduce((sum,row)=>sum+row.total,0),dishes=[...new Set(group.map(row=>row.dish).filter(Boolean))].join("、");
      tableRows.push(["每日消耗",first.date,first.name,proStatsCell(quantity,compactDecimal(quantity)),first.unit,proStatsCell(total,money(total)),"",dishes]);
    }
    if(rows.length&&(average||metric==="monthlyTotal"||metric==="monthlyAverage"))for(const group of proGroupStatsRows(rows,row=>`${row.date.slice(0,7)}\u0000${row.name}\u0000${row.unit}`)){
      const first=group[0],quantity=group.reduce((sum,row)=>sum+row.quantity,0),total=group.reduce((sum,row)=>sum+row.total,0),days=Math.max(1,new Set(group.map(row=>row.date)).size),dishes=[...new Set(group.map(row=>row.dish).filter(Boolean))].join("、");
      tableRows.push(["月度汇总",first.date.slice(0,7),first.name,proStatsCell(quantity,compactDecimal(quantity)),first.unit,proStatsCell(total,money(total)),proStatsCell(quantity/days,compactDecimal(quantity/days)),dishes]);
    }
    for(const group of proGroupStatsRows(rows,row=>`${row.name}\u0000${row.unit}`)){
      const first=group[0],quantity=group.reduce((sum,row)=>sum+row.quantity,0),total=group.reduce((sum,row)=>sum+row.total,0),days=Math.max(1,new Set(group.map(row=>row.date)).size),dates=group.map(row=>row.date).sort(),dishes=[...new Set(group.map(row=>row.dish).filter(Boolean))].join("、");
      tableRows.push(["所选期间总量",`${dates[0]} 至 ${dates[dates.length-1]}`,first.name,proStatsCell(quantity,compactDecimal(quantity)),first.unit,proStatsCell(total,money(total)),proStatsCell(quantity/days,compactDecimal(quantity/days)),dishes]);
    }
    proSetStatsTable(["类型","日期／月份","食材","数量","单位","记录成本","消耗日均","使用于"],tableRows,"当前筛选条件没有所选食材消耗记录");
  }
}
function compactDecimal(value){return Number(value||0).toLocaleString(state.language==="en"?"en-US":"zh-CN",{maximumFractionDigits:3});}
function proAggregateBusinessMetric(items,key,average=false){
  if(!items.length)return 0;
  const sum=field=>items.reduce((total,item)=>total+num(item[field]||0),0);
  if(key==="grossRate")return sum("revenue")?sum("gross")/sum("revenue")*100:0;
  if(key==="netRate")return sum("revenue")?sum("net")/sum("revenue")*100:0;
  if(key==="newRatio")return sum("customers")?sum("newCustomers")/sum("customers")*100:0;
  if(key==="oldRatio")return sum("customers")?sum("oldCustomers")/sum("customers")*100:0;
  if(key==="ticket")return sum("customers")?sum("revenue")/sum("customers"):0;
  const total=items.reduce((result,item)=>result+proStatsMetrics[key][2](item),0);
  return average?total/items.length:total;
}
function proBusinessMetricCell(key,value,context){const display=proMetricText(key,value,context);return proStatsCell(key==="gross"||key==="net"?display:value,display);}
const PRO_STATS_COLORS=["#365f96","#7d95b6","#4a5666","#a3b3c9","#778695","#536f95","#bac7d8","#8b9cb4","#344e73","#627b9c","#a1aab6","#455970","#9aacc5","#5f6a78","#7c8fa9","#c0cad8"];
function proBusinessModeAverage(){return Boolean($("statsAverage")?.checked);}
function proBusinessMetricLabel(key,suffix=""){const meta=proStatsMetrics[key],name=meta?.[state.language==="en"?1:0]||key;return suffix?`${name}（${suffix}）`:name;}
function proBusinessContext(list,average){const revenue=list.reduce((sum,item)=>sum+item.revenue,0);return{revenue:average&&list.length?revenue/list.length:revenue};}
function proBusinessGroupValue(list,key,average){return{value:proAggregateBusinessMetric(list,key,average),...proBusinessContext(list,average)};}
function proBusinessTrendGroups(items,average){
  if(!average)return items.map(item=>({label:item.date.slice(5),tooltip:item.date,list:[item]}));
  const year=$("statsYear").value;
  const months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(input=>Number(input.value)).sort((a,b)=>a-b);
  return months.map(month=>{const list=items.filter(item=>Number(item.date.slice(5,7))===month);return{label:`${month}${state.language==="en"?"":"月"}`,tooltip:`${year}-${String(month).padStart(2,"0")}`,list};});
}
function proBusinessLineSvg(groups,keys,average){
  if(!groups.length)return'<div class="empty-chart">没有符合筛选条件的数据</div>';
  const legendRows=Math.ceil(keys.length/3),pointSpacing=average?150:keys.length>1?128:86,width=Math.max(720,groups.length*pointSpacing+150),height=430+Math.max(0,legendRows-1)*24,pad={l:86,r:40,t:70+legendRows*24,b:64};
  const series=keys.map((key,index)=>({key,color:PRO_STATS_COLORS[index%PRO_STATS_COLORS.length],points:groups.map(group=>({...proBusinessGroupValue(group.list,key,average),group}))}));
  const values=series.flatMap(item=>item.points.map(point=>point.value)),min=Math.min(0,...values),max=Math.max(1,...values),range=max-min||1,x=index=>groups.length===1?pad.l+(width-pad.l-pad.r)/2:pad.l+index*(width-pad.l-pad.r)/(groups.length-1),y=value=>pad.t+(max-value)/range*(height-pad.t-pad.b),zeroY=y(0),ticks=5;
  const grid=Array.from({length:ticks+1},(_,index)=>{const value=max-range*index/ticks,py=y(value);return`<g><line class="grid-line" x1="${pad.l}" x2="${width-pad.r}" y1="${py}" y2="${py}"/><text class="stats-axis-label" x="${pad.l-10}" y="${py+4}" text-anchor="end">${proChartAxisNumber(value,Math.max(Math.abs(min),Math.abs(max)))}</text></g>`;}).join("");
  const legend=keys.map((key,index)=>{const col=index%3,row=Math.floor(index/3),lx=pad.l+col*Math.max(235,(width-pad.l-pad.r)/3),ly=24+row*24,color=PRO_STATS_COLORS[index%PRO_STATS_COLORS.length],suffix=average?(state.language==="en"?"Daily avg":"日均"):"";return`<g><line x1="${lx}" x2="${lx+24}" y1="${ly}" y2="${ly}" stroke="${color}" stroke-width="4"/><circle cx="${lx+12}" cy="${ly}" r="4" fill="${color}"/><text class="stats-legend-label" x="${lx+31}" y="${ly+4}">${escapeHtml(proBusinessMetricLabel(key,suffix))}</text></g>`;}).join("");
  const paths=series.map((item,seriesIndex)=>{const path=item.points.map((point,index)=>`${index?"L":"M"}${x(index)},${y(point.value)}`).join(" ");const labels=keys.length<=3?item.points.map((point,index)=>{const text=proMetricText(item.key,point.value,point),labelY=y(point.value)+(seriesIndex%2?24:-13);return`<text class="stats-value-label" x="${x(index)}" y="${labelY}" text-anchor="middle" fill="${item.color}">${escapeHtml(text)}</text>`;}).join(""):"";const points=item.points.map((point,index)=>{const text=proMetricText(item.key,point.value,point);return`<g class="business-series-point" data-series="${escapeHtml(item.key)}" data-chart-point data-tooltip="${escapeHtml(point.group.tooltip)}\n${escapeHtml(proBusinessMetricLabel(item.key))}: ${escapeHtml(text)}" tabindex="0"><circle cx="${x(index)}" cy="${y(point.value)}" r="5" fill="${item.color}" stroke="#fff" stroke-width="2"/></g>`;}).join("");return`<path class="business-series-line" data-series="${escapeHtml(item.key)}" d="${path}" fill="none" stroke="${item.color}" stroke-width="3"/>${points}${labels}`;}).join("");
  const xLabels=groups.map((group,index)=>`<text class="chart-label" x="${x(index)}" y="${height-18}" text-anchor="middle">${escapeHtml(group.label)}</text>`).join("");
  return`<svg class="business-stats-svg" preserveAspectRatio="none" style="width:${width}px" viewBox="0 0 ${width} ${height}">${grid}<line class="axis-line" x1="${pad.l}" x2="${width-pad.r}" y1="${zeroY}" y2="${zeroY}"/>${legend}${paths}${xLabels}</svg>`;
}
function proChartAxisNumber(value,reference=Math.abs(Number(value)||0)){
  const n=Number(value)||0,en=state.language==="en",absolute=Math.abs(reference),scale=en?(absolute>=1000000?1000000:absolute>=1000?1000:1):(absolute>=10000?10000:1),suffix=en?(scale===1000000?"m":scale===1000?"k":""):(scale===10000?"万":"");
  return (n/scale).toLocaleString(en?"en-US":"zh-CN",{maximumFractionDigits:2})+suffix;
}
function proBusinessGroupedBars(node,groups,keys,average,minimumWidth=900){
  const parent=node.closest('.chart-scroll-shell')||node.parentElement,width=Math.max(260,Math.floor(parent.clientWidth||node.clientWidth||560)),legendColumns=Math.max(1,Math.min(3,Math.floor((width-32)/205))),legendRows=Math.max(1,Math.ceil(keys.length/legendColumns)),height=270+legendRows*22,pad={l:width<400?42:58,r:12,t:30+legendRows*22,b:40};
  const prepared=groups.map(group=>({group,values:group.values||keys.map(key=>({key,...proBusinessGroupValue(group.list,key,average)}))})),all=prepared.flatMap(group=>group.values.map(item=>item.value)),min=Math.min(0,...all),max=Math.max(1,...all),range=max-min||1,y=value=>pad.t+(max-value)/range*(height-pad.t-pad.b),zeroY=y(0),plotWidth=width-pad.l-pad.r,slot=plotWidth/Math.max(1,groups.length),barWidth=Math.max(1,Math.min(26,(slot-6)/Math.max(1,keys.length))),ticks=4;
  const grid=Array.from({length:ticks+1},(_,index)=>{const value=max-range*index/ticks,py=y(value);return`<g><line class="grid-line" x1="${pad.l}" x2="${width-pad.r}" y1="${py}" y2="${py}"/><text class="stats-axis-label" x="${pad.l-7}" y="${py+4}" text-anchor="end">${proChartAxisNumber(value,Math.max(Math.abs(min),Math.abs(max)))}</text></g>`;}).join("");
  const suffix=average?(state.language==="en"?"Daily avg":"日均"):(state.language==="en"?"Total":"合计"),labelFor=key=>key==="ingredient"?(state.language==="en"?"Selected ingredients":"所选食材"):proBusinessMetricLabel(key,suffix),legend=keys.map((key,index)=>{const col=index%legendColumns,row=Math.floor(index/legendColumns),lx=pad.l+col*(plotWidth/legendColumns),ly=16+row*22,color=PRO_STATS_COLORS[index%PRO_STATS_COLORS.length];return`<g><rect x="${lx}" y="${ly-8}" width="14" height="9" rx="1" fill="${color}"/><text class="stats-legend-label" x="${lx+20}" y="${ly+1}">${escapeHtml(labelFor(key))}</text></g>`;}).join("");
  const nonzero=all.filter(value=>Math.abs(value)>1e-9).length,bars=prepared.map((entry,groupIndex)=>{
    const center=pad.l+slot*(groupIndex+.5),start=center-entry.values.length*barWidth/2;
    const columns=entry.values.map((item,index)=>{const px=start+index*barWidth+Math.min(1,barWidth*.1),py=y(item.value),top=Math.min(py,zeroY),barHeight=Math.abs(zeroY-py),color=PRO_STATS_COLORS[index%PRO_STATS_COLORS.length],text=proMetricText(item.key,item.value,item),showLabel=keys.length<=2&&Math.abs(item.value)>1e-9&&(slot>=55||nonzero<=3),labelY=item.value>=0?Math.max(pad.t-8,top-8-index*13):Math.min(height-pad.b+14,top+barHeight+12+index*13);return`<g class="business-series-bar" data-series="${escapeHtml(item.key)}" data-group="${escapeHtml(entry.group.label)}" data-chart-point data-tooltip="${escapeHtml(entry.group.tooltip)}\n${escapeHtml(labelFor(item.key))}: ${escapeHtml(text)}" tabindex="0"><rect x="${px}" y="${top}" width="${Math.max(.5,barWidth-Math.min(2,barWidth*.2))}" height="${barHeight}" rx="1" fill="${color}"/>${showLabel?`<text class="stats-value-label" x="${center}" y="${labelY}" text-anchor="middle">${proChartAxisNumber(item.value)}</text>`:""}</g>`;}).join("");return`${columns}<text class="chart-label" x="${center}" y="${height-14}" text-anchor="middle" style="font-size:${width<400&&groups.length>7?9:11}px">${escapeHtml(entry.group.label)}</text>`;
  }).join("");
  node.classList.add("business-grouped-chart");node.style.minWidth="0";node.style.width="100%";node.style.setProperty('--business-chart-height',height+'px');parent.classList.add('fit-category-chart');parent.style.setProperty('--business-chart-height',height+'px');node.innerHTML=`<svg class="business-stats-svg category-stats-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(groups.map(group=>group.label).join('、'))}">${grid}<line class="axis-line" x1="${pad.l}" x2="${width-pad.r}" y1="${zeroY}" y2="${zeroY}"/>${legend}${bars}</svg>`;parent.scrollLeft=0;bindInteractiveChart(node.parentElement||node);
  node._categoryChartArgs=[groups,keys,average,minimumWidth];node._categoryChartWidth=width;
  if(!node._categoryResizeObserver&&typeof ResizeObserver!=="undefined"){node._categoryResizeObserver=new ResizeObserver(()=>{const measured=Math.floor(parent.clientWidth);if(measured>=260&&Math.abs(measured-node._categoryChartWidth)>1&&node.classList.contains('business-grouped-chart'))proBusinessGroupedBars(node,...node._categoryChartArgs);});node._categoryResizeObserver.observe(parent);}
}
function renderBusinessStats(){
  const items=filteredStatsItems(),keys=selectedProMetrics(),average=proBusinessModeAverage(),year=$("statsYear").value,trendGroups=proBusinessTrendGroups(items,average);
  $("statsTrendTitle").textContent=state.language==="en"?`${year} ${average?"Selected-month daily-average trend":"Selected-date detail trend"}`:`${year}年 ${average?"所选月份日均趋势":"所选日期明细趋势"}`;
  $("statsMonthlyTitle").textContent=state.language==="en"?`${year} Monthly comparison`:`${year}年 月度对比`;
  $("statsWeekdayTitle").textContent=state.language==="en"?"Weekday distribution":"星期分布";
  $("statsChart").innerHTML=proBusinessLineSvg(trendGroups,keys,average);if(trendGroups.length)bindInteractiveChart($("statsChart"));
  const monthGroups=Array.from({length:12},(_,index)=>{const month=index+1;return{label:`${month}${state.language==="en"?"":"月"}`,tooltip:`${year}-${String(month).padStart(2,"0")}`,list:items.filter(item=>Number(item.date.slice(5,7))===month)}});proBusinessGroupedBars($("statsMonthlyChart"),monthGroups,keys,average,900);
  const weekNames=state.language==="en"?["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]:["周一","周二","周三","周四","周五","周六","周日"],weekdayGroups=weekNames.map((label,index)=>({label,tooltip:label,list:items.filter(item=>(parseDate(item.date).getDay()+6)%7===index)})),weekdayWidth=Math.max(980,Math.min(1400,document.documentElement.clientWidth-140));proBusinessGroupedBars($("statsWeekdayChart"),weekdayGroups,keys,average,weekdayWidth);
  const tableRows=[],dayNames=["周日","周一","周二","周三","周四","周五","周六"];
  if($("statsDetail").checked)for(const item of items)tableRows.push(["明细",item.date,dayNames[parseDate(item.date).getDay()],...keys.map(metricKey=>proBusinessMetricCell(metricKey,proStatsMetrics[metricKey][2](item),item))]);
  if($("statsAverage").checked){
    const months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(input=>Number(input.value)).sort((a,b)=>a-b);
    for(const month of months){const list=items.filter(item=>Number(item.date.slice(5,7))===month),context={revenue:list.length?list.reduce((sum,item)=>sum+item.revenue,0)/list.length:0};tableRows.push(["月平均",`${$("statsYear").value}-${String(month).padStart(2,"0")}`,"—",...keys.map(metricKey=>proBusinessMetricCell(metricKey,proAggregateBusinessMetric(list,metricKey,true),context))]);}
  }
  proSetStatsTable(["类型","日期／月份","星期",...keys.map(metricKey=>proStatsMetrics[metricKey][state.language==="en"?1:0])],tableRows,"当前筛选条件或统计方式没有可导出的数据");
}
function renderStats(){if(!$("statsYear")?.options.length)return;if(proSelectedConsumption.length)renderIngredientStats("consumption");else if(proSelectedPurchase.length)renderIngredientStats("purchase");else renderBusinessStats();const views=new Set([...document.querySelectorAll(".stats-view-check:checked")].map(i=>i.value));$("statsTrendCard").classList.toggle("hidden",!views.has("trend"));$("statsMonthlyCard").classList.toggle("hidden",!views.has("monthly"));$("statsWeekdayCard").classList.toggle("hidden",!views.has("weekday"));$("statsTableCard").classList.toggle("hidden",!views.has("table"));renderInventoryStats();}
function proLineSvg(points,fitAll=false,key="net"){if(!points.length)return'<div class="empty-chart">没有符合筛选条件的数据</div>';const pointWidth=fitAll?42:82,width=Math.max(fitAll?1120:900,points.length*pointWidth+100),height=350,pad={l:60,r:35,t:34,b:48},values=points.map(p=>p.value),min=Math.min(0,...values),max=Math.max(1,...values),range=max-min||1,x=i=>pad.l+i*(width-pad.l-pad.r)/Math.max(1,points.length-1),y=v=>pad.t+(max-v)/range*(height-pad.t-pad.b),path=points.map((p,i)=>`${i?"L":"M"}${x(i)},${y(p.value)}`).join(" ");return `<svg class="clean-trend-svg" style="width:${width}px" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line class="axis-line" x1="${pad.l}" x2="${width-pad.r}" y1="${y(0)}" y2="${y(0)}"/><path class="trend-line" d="${path}"/>${points.map((p,i)=>{const label=key==="gross"||key==="net"?`${Math.round(p.value).toLocaleString()} (${percent(p.value,p.revenue)})`:compactDecimal(p.value),dateLabel=fitAll?String(Number(p.date.slice(8))):p.date.slice(5);return `<g data-chart-point data-tooltip="${p.date}\n${label}" tabindex="0"><circle class="trend-point" cx="${x(i)}" cy="${y(p.value)}" r="5"/><text class="chart-label" x="${x(i)}" y="${height-14}" text-anchor="middle">${dateLabel}</text></g>`;}).join("")}</svg>`;}
function renderProBars(node,items,key){proBusinessGroupedBars(node,items.map(item=>({label:item.label,tooltip:item.label,values:[{key,...item}]})),[key],false);}
function renderWeekBars(node,items,key){renderProBars(node,items,key);}

function exportStatsCsv(){
  const {headers,rows}=proLastStatsExport;
  if(!headers.length||!rows.length){alert("当前筛选条件没有可导出的数据。");return;}
  const csvField=value=>{if(Exact.is(value))return value.toFixed(2);if(typeof value==="number"&&Number.isFinite(value))return value.toFixed(2);let text=String(value??"").replace(/\r\n?/g,"\n");if(/^\s*[=+\-@]/.test(text))text="'"+text;return /[",\n]/.test(text)?`"${text.replace(/"/g,'""')}"`:text;};
  const csv="\ufeff"+[headers,...rows].map(row=>row.map(csvField).join(",")).join("\r\n"),blob=new Blob([csv],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),a=document.createElement("a");
  const months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(input=>String(input.value).padStart(2,"0")),scope=proSelectedConsumption.length?"食材消耗":proSelectedPurchase.length?"食材采购":"经营指标",mode=[$("statsDetail").checked?"明细":"",$("statsAverage").checked?"平均":""].filter(Boolean).join("＋")||"未选方式";
  a.href=url;a.download=`更多统计_${$("statsYear").value}_${months.length===12?"全年":months.join("-")||"无月份"}_${scope}_${mode}.csv`;a.hidden=true;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function selectStatIngredients(type){const selected=type==="purchase"?proSelectedPurchase:proSelectedConsumption,current=selected.join(", ");openItemPicker("食材",current,items=>{const names=[...new Set(items.map(i=>i.name).filter(Boolean))];if(type==="purchase"){proSelectedPurchase=names;proSelectedConsumption=[];$("consumptionIngredients").textContent="选择消耗食材（未选择）";}else{proSelectedConsumption=names;proSelectedPurchase=[];$("purchaseIngredients").textContent="选择食材（不选则看经营指标）";}$(type==="purchase"?"purchaseIngredients":"consumptionIngredients").textContent=names.length?names.join("、"):(type==="purchase"?"选择食材（不选则看经营指标）":"选择消耗食材（未选择）");renderStats();});}

function fitDashboardMonthChart(){if(!$("trendChart")||!$("selectedYear")?.value)return;const year=Number($("selectedYear").value),month=Number($("selectedMonth").value),key=$("trendMetric").value,lookup=new Map(state.days.filter(r=>String(r.日期).startsWith(`${year}-${String(month).padStart(2,"0")}`)).map(r=>[Number(String(r.日期).slice(8)),dayMetrics(r)])),points=[];for(let day=1;day<=daysInMonth(year,month);day++){const m=lookup.get(day),value=m?(key==="revenue"?m.revenue:key==="food"?m.food+m.spice:key==="gross"?m.gross:m.net):0;points.push({date:`${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`,value,revenue:m?.revenue||0});}$("trendChart").classList.add("fit-month-chart");$("trendChart").innerHTML=proLineSvg(points,true,key);bindInteractiveChart($("trendChart"));const hint=$("trendChart").parentElement.querySelector(".chart-hint");if(hint)hint.textContent="整月 1–"+points.length+" 日已生成；悬停或点按查看，左右拖动浏览";}

const proOriginalRenderDashboard=renderDashboard;
renderDashboard=function(){proOriginalRenderDashboard();fitDashboardMonthChart();};
const proOriginalApplyLanguage=applyLanguage;
applyLanguage=function(){proOriginalApplyLanguage();document.querySelectorAll("[data-pro-metric]").forEach(node=>{const item=proStatsMetrics[node.dataset.proMetric];if(item)node.textContent=item[state.language==="en"?1:0];});setTimeout(fitDashboardMonthChart,0);};
const proOpenItemPickerV24=openItemPicker;
openItemPicker=function(category,current,callback,title=""){proOpenItemPickerV24(category,current,callback,title);const body=document.querySelector(".selector-dialog .modal-body");if(!body||body.querySelector("[data-picker-search]"))return;const search=document.createElement("input");search.type="search";search.placeholder=`搜索${category}名称`;search.dataset.pickerSearch="true";search.className="picker-search-input";body.insertBefore(search,body.firstChild);search.addEventListener("input",()=>{const q=search.value.trim().toLocaleLowerCase("zh-CN");body.querySelectorAll("tbody tr").forEach(row=>{const name=row.querySelector("[data-pick-name]")?.textContent||"";row.hidden=Boolean(q&&!name.toLocaleLowerCase("zh-CN").includes(q));});});};
function renderForecastBannerV24(){const banner=$("statsForecastBanner");if(!banner)return;const year=Number($("statsYear")?.value||new Date().getFullYear()),months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(i=>Number(i.value));const currentMonth=Number($("selectedMonth")?.value||new Date().getMonth()+1),month=months.includes(currentMonth)?currentMonth:(months[0]||currentMonth),items=state.days.map(dayMetrics).filter(m=>m&&m.date.startsWith(`${year}-${String(month).padStart(2,"0")}`)),days=daysInMonth(year,month),elapsed=Math.max(1,items.length),revenue=items.reduce((s,m)=>s+m.revenue,0),net=items.reduce((s,m)=>s+m.net,0),avgRevenue=revenue/elapsed,avgNet=net/elapsed,projectedNet=net+avgNet*Math.max(0,days-elapsed);banner.innerHTML=`<strong>平本收入预测</strong><span>按当前${month}月日均收入，预计月底收入 <b>${money(revenue+avgRevenue*Math.max(0,days-elapsed))}</b>，预计月底盈亏 <b class="${projectedNet>=0?"positive":"negative"}">${money(projectedNet)}</b></span>`;}

/* Keep the advanced-analytics forecast on the same elapsed-calendar-day and
   previous-month-cost basis as the dashboard forecast. */
function renderForecastBannerV24(){
  const banner=$("statsForecastBanner");if(!banner)return;
  const year=Number($("statsYear")?.value||new Date().getFullYear()),months=[...document.querySelectorAll("#statsMonthChecks input:checked")].map(i=>Number(i.value)),currentMonth=Number($("selectedMonth")?.value||new Date().getMonth()+1),month=months.includes(currentMonth)?currentMonth:(months[0]||currentMonth),monthKey=`${year}-${String(month).padStart(2,"0")}`;
  const items=dataDayMetrics().filter(m=>m.date.startsWith(monthKey)&&m.date<=isoDate(new Date())),days=daysInMonth(year,month),elapsed=Math.max(1,periodElapsedDays(year,month)||items.length),revenue=items.reduce((s,m)=>s+m.revenue,0),dailyRevenue=revenue/elapsed,forecastRevenue=dailyRevenue*days;
  const previousDate=new Date(year,month-2,1),previousKey=`${previousDate.getFullYear()}-${String(previousDate.getMonth()+1).padStart(2,"0")}`,previousItems=dataDayMetrics().filter(m=>m.date.startsWith(previousKey)&&m.date<=isoDate(new Date()));
  const currentTotal=items.reduce((s,m)=>s+m.variable,0)+fixedBreakdown(year,month).spentTotal,previousTotal=previousItems.length?previousItems.reduce((s,m)=>s+m.variable,0)+fixedBreakdown(previousDate.getFullYear(),previousDate.getMonth()+1).spentTotal:currentTotal,expectedNet=forecastRevenue-previousTotal;
  banner.innerHTML=`<strong>本月收入预测 (本月截至目前的日均收入 x 本月总天数)</strong><span>预计月底收入 <b>${money(forecastRevenue)}</b>；<strong>(根据上月总成本和本月收入预测) 预计月底盈亏</strong> <b class="${expectedNet>=0?"positive":"negative"}">${money(expectedNet)}</b></span>`;
}
const renderStatsV24=renderStats;
renderStats=function(){renderStatsV24();renderForecastBannerV24();};

/* Keep a saved-value baseline for every editor. Drafts remain untouched while
   the user is typing, but a successful save establishes a new baseline. */
function setDraftComparableValue(id,row){const map={ledgerTotalCash:"总现金",ledgerACash:"A店现金",ledgerBCash:"B店现金",ledgerTotalOnline:"总线上",ledgerAWechatAdd:"A店微信增加",ledgerAWechatOverride:"A店微信覆盖",ledgerAAlipayAdd:"A店支付宝增加",ledgerAAlipayOverride:"A店支付宝覆盖",ledgerBWechatAdd:"B店微信增加",ledgerBWechatOverride:"B店微信覆盖",ledgerBAlipayAdd:"B店支付宝增加",ledgerBAlipayOverride:"B店支付宝覆盖",ledgerARevenue:"A店收入",ledgerBRevenue:"B店收入",ledgerStudentTakeout:"学生外卖",ledgerATakeout:"A店外卖",ledgerBTakeout:"B店外卖",ledgerNewCustomers:"新客人数量",ledgerCustomers:"总客人数",ledgerFoodCost:"食材成本",ledgerSpiceCost:"佐料成本",ledgerUtilities:"水电",ledgerOther:"其他",ledgerFoodDetail:"食材明细",ledgerSpiceDetail:"佐料明细",ledgerOtherDetail:"其他明细",ledgerNote:"当日备注"};return row[map[id]]??"";}
const proRefreshLedgerWithBaseline=refreshLedger;
refreshLedger=function(){
  const key=$("ledgerDate")?.value;
  /* A legacy desktop record can contain 收益=0 plus a non-zero 总金额.
     Discard only the stale zero-valued draft created before normalization;
     genuine edits remain protected by the navigation warning. */
  if(key){
    const raw=dailyRow(dayPayload(key),key),normalizedRow=typeof dayRowForDate==="function"?dayRowForDate(key):null,draft=readEditorDraft("ledger",key),legacyRow=normalizedRow||raw,legacy=typeof legacyRevenueValue==="function"?legacyRevenueValue(legacyRow):[legacyRow.收益,legacyRow.总金额,legacyRow.收入,legacyRow.总收入].find(value=>entered(value)&&num(value)!==0);
    const baselineRevenue=state.editorBaselines?.[editorDraftKey("ledger",key)]?.values?.ledgerRevenue;
    if(draft&&legacy!==undefined&&num(draft.values?.ledgerRevenue)===0&&num(baselineRevenue)===0){
      const comparable=PRO_LEDGER_DRAFT_FIELDS.filter(id=>id!=="ledgerRevenue");
      const current=Object.fromEntries(comparable.map(id=>[id,setDraftComparableValue(id,raw)]));
      const numeric=new Set(comparable.filter(id=>/Revenue|Cash|Online|Cost|Utilities|Other|Customers/.test(id)));
      const unchanged=comparable.every(id=>numeric.has(id)?num(draft.values?.[id])===num(current[id]):String(draft.values?.[id]??"").trim()===String(current[id]??"").trim());
      if(unchanged)forgetEditorDraft("ledger",key);
    }
  }
  proRefreshLedgerWithBaseline();
  configureEntryDetailInputs(key);
  if(currentRole()==="entry")renderEntryTiming();
  /* Final compatibility guard: the dashboard and ledger must show the same
     normalized legacy revenue.  Some old records expose the value only after
     dayMetrics() resolves aliases, so use that exact value for the input. */
  if(key&&!readEditorDraft("ledger",key)){
    const source=typeof dayRowForDate==="function"?dayRowForDate(key):state.days.find(row=>String(row.日期)===String(key)||String(row.日期).replace(/\//g,"-")===String(key));
    const normalized=source&&typeof dayMetrics==="function"?dayMetrics(source)?.revenue:0;
    if(Number.isFinite(normalized)&&normalized!==0&&num($("ledgerRevenue")?.value)===0){
      $("ledgerRevenue").value=String(normalized);
    }
  }
  if(key&&!readEditorDraft("ledger",key))rememberEditorBaseline("ledger",key,{values:draftFieldValues(PRO_LEDGER_DRAFT_FIELDS)});
};
const proRefreshFixedWithBaseline=refreshFixed;
refreshFixed=function(){proRefreshFixedWithBaseline();const key=$("fixedMonth")?.value;if(key&&!readEditorDraft("fixed",key))rememberEditorBaseline("fixed",key,{values:draftFieldValues(PRO_FIXED_DRAFT_FIELDS)});};
const proRefreshDishesWithBaseline=refreshDishes;
refreshDishes=function(){proRefreshDishesWithBaseline();const key=$("dishDate")?.value;if(key&&!readEditorDraft("dishes",key))rememberEditorBaseline("dishes",key,{rows:collectDishRows(),note:$("dishDayNote")?.value||""});};
const proRefreshDetailWithBaseline=refreshDetail;
refreshDetail=function(kind){proRefreshDetailWithBaseline(kind);const key=$(kind+"Date")?.value;if(key&&!readEditorDraft(kind,key))rememberEditorBaseline(kind,key,{rows:detailRows(kind)});};
const proRenderInventoryWithBaseline=renderInventory;
renderInventory=function(){if(!$("inventoryRows"))return;proRenderInventoryWithBaseline();if(!readEditorDraft("inventory","current"))rememberEditorBaseline("inventory","current",{entries:collectInventoryRows()});};
const proSaveLedgerWithBaseline=saveLedger;
saveLedger=async function(){const key=$("ledgerDate")?.value;await proSaveLedgerWithBaseline();if(currentRole()==="entry"&&state.dataset?.id){const windows=await api(`/datasets/${encodeURIComponent(state.dataset.id)}/entry-windows`);state.entryWindows=Array.isArray(windows)?windows:(windows?.items||[]);Object.values(ENTRY_DETAIL_UI).forEach(config=>{if($(config.input))$(config.input).dataset.entryKey="";});refreshLedger();renderEntryTiming();}if(key&&!readEditorDraft("ledger",key))rememberEditorBaseline("ledger",key,{values:draftFieldValues(PRO_LEDGER_DRAFT_FIELDS)},{force:true});};
const proSaveFixedWithBaseline=saveFixed;
saveFixed=async function(){const key=$("fixedMonth")?.value;await proSaveFixedWithBaseline();if(key&&!readEditorDraft("fixed",key))rememberEditorBaseline("fixed",key,{values:draftFieldValues(PRO_FIXED_DRAFT_FIELDS)},{force:true});};
const proSaveDishesWithBaseline=saveDishes;
saveDishes=async function(){const key=$("dishDate")?.value;await proSaveDishesWithBaseline();if(key&&!readEditorDraft("dishes",key))rememberEditorBaseline("dishes",key,{rows:collectDishRows(),note:$("dishDayNote")?.value||""},{force:true});};
const proSaveDetailWithBaseline=saveDetail;
saveDetail=async function(kind){const key=$(kind+"Date")?.value;await proSaveDetailWithBaseline(kind);if(key&&!readEditorDraft(kind,key))rememberEditorBaseline(kind,key,{rows:detailRows(kind)},{force:true});};
const proSaveInventoryWithBaseline=saveInventory;
saveInventory=async function(){await proSaveInventoryWithBaseline();if(!readEditorDraft("inventory","current"))rememberEditorBaseline("inventory","current",{entries:collectInventoryRows()},{force:true});};

installProUI();
applyLanguage();
if(state.token){const role=state.user?.role||"viewer";$("ledgerPermission").textContent=["admin","editor"].includes(role)?"可修改":"只读账号";refreshOpenEditors();setTimeout(fitDashboardMonthChart,0);}
