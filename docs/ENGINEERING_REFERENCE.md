# Engineering reference · v1.0.2

**[← Back to the English README](../README.en.md)** · [简体中文](ENGINEERING_REFERENCE.zh-CN.md) · [Changelog](../CHANGELOG.md) · [Deployment guide](DEPLOYMENT.md)

Use this reference when changing the application or tracking down a figure on screen. Pick a starting point below. For installation commands, use the deployment guide linked above.

| What are you working on? | Start here |
| --- | --- |
| Find the code for a page or trace a save | [Source map](#source-map) · [Database records](#database) · [Saving and permissions](#saving) |
| Reconcile a number or change a chart | [Profit and inventory](#calculations) · [Month-end forecast](#month-end-profitloss) · [Charts and exports](#charts) |
| Translate a form or an error message | [Interface languages](#languages) |
| Run tests, build a release or restore an installation | [Settings](#settings) · [Tests and builds](#tests) · [Packaging and recovery](#recovery) |
| Diagnose a fault or look up an endpoint | [Troubleshooting](#troubleshooting) · [HTTP routes](#api-routes) · [Privacy checks](#privacy) |

## How the application fits together

A **book** holds a set of business records. The same book can track sales through channels for stores A and B. A store name identifies the income source on screen. The book ID tells the server which records to read and whose account may change them.

The browser loads static HTML, JavaScript and CSS. The FastAPI service authenticates users and stores the books in PostgreSQL. The macOS app uses PySide6 and can work with a local Excel workbook or synchronize with the service. All three have source and tests in this repository. Build the server archive and macOS app separately.

| What do you want to check? | Where to look |
| --- | --- |
| Product version | `VERSION` and the API health response report `v1.0.2`. Several builds can have that version. |
| Code behind a build | A Git commit identifies the tracked source. The build revision in the HTML distinguishes frontend updates within the same product version. |
| What the server serves | Compare the deployed files and HTTP responses with the SHA-256 hashes in the server archive’s `MANIFEST.json`. |
| Contents of a complete ZIP | The outer `.sha256` covers the ZIP bytes. `PACKAGE_MANIFEST.json` records the files, permissions and symlinks inside. |
| Whether an upgrade preserved a ledger | Compare the database checks taken before and after the upgrade. To test recovery, restore the backup and its matching configuration in an isolated installation. |

The financial reports use the store’s management-accounting definitions below. A month can change after a correction. Use payment records to verify settlement and the applicable accounting records for statutory reporting.

<a id="source-map"></a>

## Find the source for a feature

Start with `web/index.html`. Each panel shares the same `state`, and some scripts wrap or replace a function defined earlier. For a dashboard bug, follow the script order through the workbench, charts, dashboard and analytics modules to find the function the browser actually calls. Keep the exact-arithmetic runtime ahead of the business code.

| Source | What to edit here |
| --- | --- |
| `web/index.html` | Base DOM, IDs used by scripts, stylesheet/script order, build revision and cache queries. Do not rename IDs without checking all callers. |
| `web/money.js` | BigInt-backed exact decimal runtime; maintained directly, not generated from a duplicate source. |
| `build/web-exact-source/app.js` | Shared state, authorization helpers, record normalization, API operations, editor baselines, reports, date/period logic and language switching. |
| `build/web-exact-source/pro.js` | Rich ledger/purchase/dish editors, parsing and detail controls, enhanced reports and older statistics entry points. |
| `web/i18n-en.js`, `i18n-inventory-en.js`, `i18n-backend-en.js`, `i18n-extra-en.js` | Four direct presentation catalogs loaded before v8: shared UI, inventory, API/audit and remaining legacy templates. Preserve user-authored data. |
| `web/i18n-controls.js` | English month-input display adapter: ISO `YYYY-MM` overlay while keeping the native input, value, validation, events and calendar picker. Loaded after the four catalogs and before v8. |
| `build/web-exact-source/v8.js`, `v28.js` | Pickers and later workflow/settings integration; request context guards matter during book changes. |
| `build/web-exact-source/sep04.js` | Cash balance view, cache synchronization, cash entry operations and legacy compatibility. |
| `build/web-exact-source/sep05.js`, `sep07.js` | Additional report/editor/permission/customer integrations; preserve their active wrappers. |
| `build/web-exact-source/inventory-fifo.js` | Browser FIFO replay, batch allocation and exact cost conservation. |
| `build/web-exact-source/oct29.js` | Extended ledger/inventory/workflow behavior and associated tests. |
| `build/web-exact-source/inventory-workspace.js` | Inventory workspace, documents, source details and name-correction UI. |
| `web/workbench.js`, `web/workbench.css` | Application shell, navigation, page headings and responsive workbench layout. Maintained directly. |
| `build/web-exact-source/charts-oct30.js` | Shared SVG chart geometry, axes, hover/touch/focus/keyboard inspection and resize lifecycle. |
| `build/web-exact-source/dashboard-oct30.js` | Five homepage KPIs, comparison wording and dashboard charts. |
| `build/web-exact-source/analytics-oct30.js`, `web/analytics-oct30.css` | Analytics filters, operating/expense/customer views, expense calculations, source tables and layout. |
| `desktop/restaurant_cost_manager.py` | Native widgets and native data/financial/synchronization logic in a large single module. Use symbol/class context, not old line numbers. |
| `backend/app/main.py` | Public API routes, record policy, authorization, cash aggregation, startup compatibility and audit maintenance. |
| `backend/app/models.py`, `database.py`, `security.py` | SQLAlchemy schema, exact JSON persistence, sessions and JWT/password operations. |
| `backend/app/money.py`, `money_routes.py`, `excel_io.py` | Monetary input/serialization, exact JSON HTTP parsing and workbook import/export. |
| `backend/app/inventory_balance.py`, `inventory_validation.py` | Quantity replay and transaction-time stock/amount guards; not a third FIFO cost engine. |
| `backend/app/name_corrections.py`, `ingredient_corrections.py` | Preview, coordinated name updates, stock adjustment, stale-state detection and durable idempotency receipts. |
| `backend/app/store_settings.py`, `wechat_pay.py`, `wechat_sync.py` | Store configuration and retained merchant bill code; old scheduler is not started by current startup. |

Authoritative business JavaScript is under `build/web-exact-source/`. `node build/compile_exact_web.cjs` parses with Acorn and emits the corresponding `web/*.js`. Do not edit generated copies alone. HTML, CSS, `money.js`, `workbench.js`, the localization assets and licenses are direct static sources. Consult the compiler's own file list before classifying a new asset. Runtime browsers do not require Node, Acorn, a bundler or CDN.

<a id="database"></a>

## How a book is stored

Production uses PostgreSQL. Record contents with variable fields live in JSONB columns. Startup calls SQLAlchemy’s `create_all` and applies a short list of compatibility updates. A new schema change needs its own migration plan. Tests also run against a SQLite adapter.

| Table | What it stores | What to preserve when changing it |
| --- | --- | --- |
| `app_users` | UUID, unique username, display name, bcrypt hash, role, active flag. | Existing administrator password is not reset merely by changing startup environment values. |
| `datasets` | Stable book ID, name, schema version. | Renaming changes display name, not ID. IDs determine record and permission scope. |
| `user_dataset_memberships` | Unique user/book pair and default-book flag. | Non-admin access requires membership; don't infer access from a UI selection. |
| `devices` | Device ID belonging to one book, platform/name, last seen time. | Device registration and caching must use the book captured when a request starts. |
| `sync_records` | Unique `(dataset_id, record_type, record_key)`, payload, checksum, version, sequence, deletion state. | Keep expected-version checks and deletion tombstones; do not treat record names as unique item identity. |
| `entry_timings` | Server-owned first-save times, item/field timing maps and legacy clocks. | Payload edits cannot extend correction or addition windows. |
| `audit_logs` | Before/after payload, actor, source/event/device, version transition, sequence and times. | Retention/admin deletion means it is review history, not an immutable backup. |
| `temporary_permissions` | User/book, role, allowed business-date range and activation interval. | Both business dates and real activation time matter. |
| `sync_conflicts` | Local/cloud versions and payloads, status, resolution and note. | Conflict resolution must pass the same financial and permission boundaries as an ordinary write. |
| `inventory_name_corrections` | Unique book/request ID, request hash, request/response payload and reason. | Durable idempotency survives audit pruning; changing a request while reusing its ID is invalid. |

Day records can contain `daily`, `dishes` and `fixed_expenses`; month records contain `monthly_fixed`; global records hold settings, dictionaries, cash and inventory-related data according to their existing keys. Legacy records can contain multiple business dates in one payload. A one-day edit must merge the matching date inside each array and preserve sibling/undated data that cannot safely be assigned. Missing requested-day dishes must not fall back to another day's last dish list.

IDs, dates, versions, record keys, custom metadata, names and notes are not monetary fields. Preserve unknown extension fields during import/edit. Same-name purchases with different units, prices or notes remain separate rows; moving/deleting a selected row must use row identity, not a name-wide selection.

The internal workbook has record-oriented sheets such as `__day_records`, `__month_records`, `__global_records`, `__meta` and `__audit_records`, with structured `payload_json`. It is an exchange artifact, not a complete server backup of users, memberships, clocks, merchant keys, environment and service configuration. A user workbook has business-facing sheets; merge and replace are different operations and must remain explicit.

<a id="saving"></a>

## Follow a save from the editor to the database

The browser sends requests to `/api/v1` on the same origin that serves the page. Nginx forwards `/api/` with its prefix intact. Login returns a bearer JWT. Each authorized request reloads the account and checks that it is active. The roles are `viewer`, `entry`, `editor` and `admin`. Administrators can work across books. Other users need membership in the selected book.

1. The editor captures the active login, book and context generation. It keeps a baseline of the record and preserves fields outside the edit.
2. The client registers or reuses a device for that book, normalizes known monetary fields, calculates the checksum and sends the expected record version.
3. In one transaction, the server checks the user’s rights, applicable time limits, expected version and relevant inventory rules. It writes the new record version, sync sequence and audit entry.
4. The client applies the response only while the original context is current. Switching A → B → A invalidates pending work from the first visit to A. A newer local save also advances the revision so an older refresh cannot overwrite it.

**Cash balances.** A cash adjustment can change the balance while the daily records stay the same. Check the book and cash revision on every cash response, even when the main record snapshot is unchanged. All cash views read the shared cache.

**Entry permissions.** The server tracks when each field or line was first saved. The main correction window is 30 minutes and the window for adding detail lines is 12 hours. Business dates and income cutoffs also apply. A temporary grant can raise a user’s rights for day records during the grant’s active period and for the business dates it covers. Check `_effective_record_role` and `_entry_timing_updates` before changing these rules. Editing a note or resaving an equivalent amount must keep the original clock.

**Inventory changes.** The server locks the book, replays stock movements and checks for new shortages. Stale document versions are rejected. A name correction previews the affected records, rechecks them and applies them in one transaction. A saved request receipt lets a retry identify work that already succeeded.

**Audit history.** The server keeps 366 days and lets administrators maintain the log. Startup can delete expired entries. Account for expiry when comparing the database before and after an upgrade.

<a id="calculations"></a>

## How the ledger calculates profit and inventory

For the exact formats and test cases, see [money in the clients](../build/MONEY_CONTRACT.txt), [FIFO](../build/FIFO_CONTRACT.md) and [money in the API](../backend/MONEY_BACKEND.txt). New or changed monetary fields cross the API as decimal strings. Python uses `Decimal` and the browser uses `Exact`. Amounts have two decimal places and unit prices have six, with `ROUND_HALF_UP`. The absolute limit is 999999999999.99 for a single amount and 999999999999.999999 for a unit price. Totals calculated from valid inputs have separate rules. Reject invalid text, booleans, NaN and infinity. A known price of zero counts as a price.

Legacy numeric JSON is read without losing its original decimal spelling. OOXML numeric cells are inspected before conversion where necessary. Only known financial fields and their known structured detail paths are normalized; arbitrary metadata is not converted wholesale. Chart coordinates may become ordinary floats at the final drawing boundary, never for financial persistence. Formatting an Exact value must not silently invoke `Number` during calculation.

The homepage cards show, in order, average daily revenue, average daily gross profit with gross margin, estimated month-end profit/loss, estimated daily profit/loss this month, and actual net profit with net margin. The first two use records through yesterday divided by elapsed calendar days. Card 4 shows money per calendar day. The percentage below it compares that daily amount with the previous month. Card 5 includes today’s entries and the full saved monthly fixed expense. Its net margin divides that actual net by actual revenue through today and is unavailable for a missing or zero revenue denominator. The full monthly report’s actual average daily net profit divides actual net by elapsed calendar days.

The daily trend and weekday averages default to revenue when the dashboard opens. Each has its own metric selector. Revenue, gross profit and net profit read the existing daily ledger measures. The ingredient series combines ingredient and seasoning purchases. The daily trend leaves unrecorded dates empty. Weekday averages group recorded dates from the selected month by weekday and divide each group by its own record count. A zero measure on a day with business activity counts. Empty rows are skipped. A weekday without records has no value. The chart sample count is separate from the calendar-day denominator used for the forecast.

The dashboard cost ring groups expenses for the selected day. A category keeps its color as other categories appear or disappear. The legend pairs each swatch with its label, amount and share. The centered figure is the sum of the amounts plotted for that day. The daily ring uses positive expenses and the existing daily fixed-cost allocations. The native monthly expense chart uses whole-month fixed costs and its existing categories, which exclude fees. Reconcile its center against the sum of slices in that chart. The month-end forecast below derives its own monthly figures from the ledger.

`dayMetrics` provides category keys for the daily ring. In `build/web-exact-source/app.js`, `costDonutColors` maps each key to a color and `renderCostDonut` uses that mapping for both gradient stops and legend markers. Recompile with `build/compile_exact_web.cjs` after editing. The ring’s responsive dimensions and centered label, amount and currency unit are in `web/reporting-oct30.css`. The native charts use `DashboardTab._draw_cost_ring`.

### Month-end profit/loss

The dashboard and full monthly report use the same result. In Chinese both show `预计月底盈亏` above `(根据 本月预计成本 和 本月预计收入 计算)`. In English the lines read **Estimated month-end profit/loss** and **(based on this month’s projected costs and revenue)**. The adjacent **i** opens on hover or click and explains the calculation, cutoffs and change to actuals. The web help follows the interface language. The advanced analytics banner reuses this explanation. When a refresh replaces its button, an open popup reconnects to the new button and shows the latest cost inputs. The native app presents the same rules in Chinese.

Let **D** be the number of calendar days in the selected current month. Last month’s daily averages use its complete calendar month, including across a year boundary. This month uses the same denominator for all three daily rates: calendar days elapsed through yesterday. The revenue numerator stops at yesterday. The ingredient and other cost numerators include entries dated today as soon as they are saved. Later-dated entries are excluded. A day without an entry still counts in the denominator. All amounts below are for the same book.

| Component | Calculation |
| --- | --- |
| Projected revenue | Current daily average revenue × D. |
| Projected fixed costs | Higher of last month’s and this month’s saved whole-month fixed expenses. Use paid utility amounts in the fixed total. |
| Projected ingredients | Combine ingredient and seasoning purchases for each period. Multiply the higher of the two daily averages by D. |
| Projected other costs | For each period, take total cost minus ingredients (including seasonings) minus its whole-month fixed expenses. This leaves daily utilities, fees and other expenses. Multiply the higher of the two daily averages by D. |
| Projected profit/loss | Projected revenue − projected fixed costs − projected ingredients − projected other costs. |
| Estimated daily profit/loss this month | Unrounded month-end profit/loss ÷ D. A closed month uses actual net profit ÷ that month’s calendar days. A missing monthly result gives a dash. |

**Example: a purchase entered on November 11.** Ten days have elapsed, October has 31 days and November has 30. Suppose the book contains these amounts in CNY.

| | October | November so far | November projection |
| --- | ---: | ---: | ---: |
| Fixed costs | 6,000 | 6,500 | 6,500 |
| Ingredients and seasonings | 9,300 (300/day) | 2,600 (260/day) | 9,000 |
| Other costs | 1,550 (50/day) | 750 (75/day) | 2,250 |
| Revenue through yesterday | — | 8,000 (800/day) | 24,000 |

The help shows average daily total cost of **591.67**, total cost of **17,750.00** and revenue of **24,000.00**. Projected profit is **6,250**. Now save a CNY 600 grocery purchase dated November 11. November’s ingredient rate becomes 3,200 ÷ 10 = 320/day, above October’s 300/day. Projected ingredient cost rises to 9,600 and profit falls to **5,650**. A sale recorded for November 11 first enters the revenue projection on November 12.

To preserve half cents, put both daily rates over the same denominator. Let **e** be the elapsed days and **p** the previous month’s length. For each variable category the two numerators are `current total × p` and `previous total × e`, over the common denominator `e × p`. Choose the larger numerator for each category. For projected net, subtract the two winning numerators from `current revenue × p`, multiply the result by D, and subtract `projected fixed costs × e × p`. Divide this combined numerator by `e × p` once. Display the result rounded to cents. This also preserves an exact half cent when the individual daily rates repeat. The original ledger categories feed both months. In particular, the forecast’s “other costs” include fees and daily utilities in addition to entries categorized as “Other”. If the current month has no saved fixed-cost record, use the previous month’s fixed amount directly. A saved current amount of zero participates in the comparison. A recorded zero or a previous month containing only a saved fixed-cost record provides a valid cost basis. The current month needs a completed operating record. On day one, without that current record, or with the previous month entirely missing, the estimate is unavailable. Future months are unavailable.

The help displays the monthly cost and the daily total cost separately. Use the same unrounded cost numerator as the profit calculation. Divide by its denominator for the monthly amount, or by the denominator times **D** for the daily amount, then format to cents. This daily cost includes the fixed component. When the month closes, the same three rows show actual total cost divided by its full calendar length, actual total cost and actual revenue. If an input is unavailable, the corresponding row shows a dash.

Card 4 uses the same profit numerator as card 3, divided once by `e × p × D`, then rounded to cents for display. In the November example above it moves from 6,250 ÷ 30 = **CNY 208.33/day** to 5,650 ÷ 30 = **CNY 188.33/day** after the purchase. At a rounding boundary, an exact November estimate of CNY 0.145 displays as CNY 0.15 on card 3. Its daily value is 0.145 ÷ 30 and displays as **CNY 0.00/day**.

To reproduce the month-on-month comparison in an empty test book, record CNY 310 revenue on January 1, 2024 and CNY 580 on February 1, 2024. Leave all costs at zero. Select February after it has closed. Card 3 shows CNY 580.00. Card 4 compares 580 ÷ 29 = **CNY 20.00/day** with January’s 310 ÷ 31 = **CNY 10.00/day**, an increase of **100.0%**. Card 5 shows actual net of CNY 580.00 and a 100.0% net margin. The same fixture in 2023 uses CNY 560 for February and 28 calendar days.

Compare the two unrounded daily rates over a common denominator. If November’s net is CNY 0.03 and October’s is CNY 2.00, the rates are 0.03 ÷ 30 and 2.00 ÷ 31. The decrease is exactly 98.45%, displayed as **98.5%**.

**Where to make a change.** In `build/web-exact-source/app.js`, `monthOverviewMetricsV102` gathers the ledger totals and `monthForecastV102` derives the forecast on each refresh. It returns `net`, `dailyNet`, `netNumerator` and `dailyNetDenominator`. The dashboard’s `summary` in `dashboard-oct30.js` passes each month’s numerator and divisor to `monthChangeV102`. The dashboard and monthly report both read that forecast. Their help compares the unrounded candidates, shows both amounts and identifies the month used or a tie. Fixed costs are monthly amounts. Ingredient and other costs are daily rates.

The desktop equivalent is `calc_dashboard_month_kpis` in `desktop/restaurant_cost_manager.py`. It returns `projected_daily_net` for `DashboardTab._refresh_month_headlines`. Run `node web/test_v1_0_2_dashboard.js` for the February example and rounding cases, `python build/test_v1_0_2_desktop.py` for the desktop calculation and `QT_QPA_PLATFORM=offscreen python build/test_v1_0_2_desktop_qt.py` for the actual card order, amounts and margins. A fixture that takes ingredients from one month and other costs from the other catches accidental coupling. Include today’s purchase and a seasoning item to exercise the cutoff and catch double counting.

The local client calendar determines whether a month is complete, independently of the selected day. Browser and native date watchers re-evaluate about every five seconds even when data is unchanged; the browser also checks on becoming visible. Native refresh waits until modal dialogs close and retries after read failures. A completed month's forecast card shows actual net from the next month's first day, including December/January rollover. This neither changes the selected period nor writes/freezes a ledger value; a valid historical correction recalculates it.

| Client date | Selected month | Forecast-card amount |
| --- | --- | --- |
| October 31 | October | Current-month projection. |
| November 1 | October | October actual net; previous-month cost is no longer needed. |
| November 1 | November | Unavailable until a day elapses; actual net can exist separately. |
| January 1 | Previous December | December actual net. |
| November 10 | December | Unavailable future period. |

| Financial concept | Required meaning |
| --- | --- |
| Revenue | Normalize current channel entries and legacy total-only fields such as `收益` / `总金额`; meaningful channel entries take precedence over stale derived totals, never count both. |
| Gross profit | Revenue − food − seasoning − transaction fees. |
| Gross margin | Average daily gross ÷ average daily revenue on the same cutoff basis; unavailable for missing/zero denominator. |
| Variable expense | Food + seasoning + daily utilities + Other + fees. |
| Monthly fixed expense | Saved labour + rent/property + paid water/electricity/gas + other fixed. |
| Monthly total cost | Sum of daily variable expense + full saved monthly fixed expense. |
| Monthly net | Revenue − monthly total cost. |
| Change percentage | `(current − prior) / abs(prior) × 100`; zero/missing prior needs an explicit unavailable reason. |
| Cash force adjustment | Set target actual balance as of a date; not operating income or cost. |
| Expense basis comparison | Saved monthly fixed totals versus itemized dated fixed payments; do not add both. |

Inventory identity is category/name/unit. Different units are not silently converted. FIFO keeps original lot quantity/value/price and remaining quantity. Each issue cost is the change in rounded cumulative allocation: `round(original lot amount × cumulative issued / original quantity, 2) − already allocated`. A fully consumed lot allocates all remaining cents. Remaining value equals original booked value minus allocated value, not rounded remaining quantity × displayed price. Unknown-priced quantities remain explicit.

Purchasing expense and FIFO consumption cost answer different questions. Monthly operating profit uses the purchase/expense basis. Packaging, consumables and phone costs retain their recorded expense classification. Gross minus fixed can therefore still differ from net by daily utilities and Other expenses. The detailed daily card can use dish cost when present, while monthly/average gross totals use daily bookkeeping gross. Expected utility amounts may appear in expense details; actual monthly fixed expenditure and net use paid amounts.

The cash balance sheet has one manual target-balance entry point: Add an item → Force balance adjustment. This adjusts balance as of a date without creating revenue/expense or replacing earlier transactions. Ordinary entries retain their deletion rules; historical `system_locked` entries remain protected. There is no separate balance-correction form.

<a id="languages"></a>

## Translate the interface and preserve what people entered

The browser offers English and Chinese. The macOS app uses Chinese. In the browser, translate the words supplied by the application, including dialog buttons, validation messages, roles and chart legends. Keep the spelling of ledger, store, product, dish and custom income names, notes, people, suppliers and units exactly as entered. Stored keys and enum values keep their original meaning in either language.

When adding a translated field:

1. Add the fixed label to the rendering code or catalog. Keep the stored field key and value stable.
2. For a store name followed by a payment channel, escape the store name for HTML and translate the channel suffix. For an error message, translate the sentence template and insert the user’s value as entered.
3. Switch languages with an unsaved draft open. The current panel and any later dialog must use the selected language. Check the book, date, amount, draft and outbound save payload.
4. Test a product whose name exactly matches a dictionary entry. Inspect role-specific screens, placeholders, titles and accessible labels as well as the visible text.

English uses `CNY` for the same yuan amount. For `input[type=month]`, `web/i18n-controls.js` displays `YYYY-MM` over the native control so the field has the same format on different operating systems. The original control still handles its value, validation, events and picker. The browser and operating system supply the popup calendar.

### Where translations are applied

`web/index.html` loads these four catalogs after `app.js` and `pro.js`, before `v8.js` builds its lookup table.

| File | Scope |
| --- | --- |
| `web/i18n-en.js` | Shared fixed labels, system-message templates, `systemMessage` and alert/confirm/prompt presentation. |
| `web/i18n-inventory-en.js` | Inventory workspace, receiving/issues/stocktakes, batch and name-correction dialogs. |
| `web/i18n-backend-en.js` | Known API error/validation/status templates, canonical field display labels and structured audit summaries. |
| `web/i18n-extra-en.js` | Remaining legacy ledger/report/cash, picker, account, grant and Excel labels/messages. |

These files extend `SYSTEM_EN` and `SYSTEM_EN_PATTERNS`. Load the month control adapter after all four catalogs and before `v8.js`. Edit the catalogs directly. They ship in the server manifest with the same cache revision as the other scripts. The Exact compiler processes a separate set of business scripts.

`v8.js` translates fixed text nodes and display attributes such as `placeholder`, `title`, `aria-*` and `data-label`. It remembers each original string and its translation. If an asynchronous render changes that string, the observer translates the new source. It batches updates and writes only changed values. `v28.js` uses compatible metadata to retain the store name while translating the fixed payment-channel label.

Mark names, notes and other user-entered text with `data-user-content`. Editable fields and designated book/account selectors also have explicit exclusions. `sep07.js` applies the marker to read-only copies of input values and updates them only when the value changes. Preserve this marker when recreating a node. Otherwise the translation observer and read-only view can overwrite each other repeatedly.

An HTML option without a `value` submits its displayed label. Set the option’s original value explicitly before translating the label. A cash type or fixed-cost category will then submit the same value in either language. Keep both the identifier and text of user-created options.

`translateBackendMessage` matches known server messages against anchored patterns. It translates known field names, error locations and nested errors, and preserves usernames, notes, units and paths. Add a catalog entry when introducing a new API error template. The response payload and its stored keys stay intact.

`translateAuditSummary(summary, item)` reads the structured `before_payload`, `after_payload` and reason. It names known fields, keeps their entered values and labels each change Added, Removed, Changed or Cleared. The summary shows up to 20 changes and limits recursion depth. For a full comparison, inspect the original payloads. Older responses may lack these fields. Translate recognized fixed wording in those summaries and preserve ambiguous text, including a note containing semicolons.

Regression entry points include `build/qa_english_ui.cjs`, `build/qa_inventory_english.cjs`, `build/test_i18n_backend.cjs`, `build/qa_enhanced_analytics.cjs` and the retained business/money tests. Verify English and Chinese round-trips, dynamic dialogs, error paths, unchanged option values, arbitrary user names matching catalog words, read-only mirrors and absence of observer loops.

<a id="charts"></a>

## Read the charts and reconcile a CSV export

The **Analytics** page has three views: operations, expenses and customers. Start with the selected period, metric and comparison month above the chart. The source table shows the records behind the total. In the expense view, compare monthly fixed-cost entries with dated payments. They are two ways of looking at the same expense.

| On screen | How to check it |
| --- | --- |
| Summary cards | Every view shows the number of recorded days. Operations adds the largest expense category and the number of profitable days. Expenses shows the largest category and the difference between monthly fixed costs and itemized payments. Customers shows the busiest day and how many recorded days have a positive customer count. |
| Trend | Line and bar views use the same observations. The statistics show their count, mean, minimum and maximum. An unrecorded date leaves a gap and a loss plots below zero. |
| Detail table and CSV | Sorting and filtering apply to the export. The total covers all filtered rows across pages. CSV headings follow the selected language and user-entered values keep their spelling. |
| Axis labels | The SVG renderer measures the available width, shortens dates when the period supplies context, reserves space at the ends and wraps category labels. Resizing changes the labels’ spacing. All observations stay available. |
| Exact chart values | Hover, tap or focus a point to read the complete date or category and amount. Use the arrow keys or Home/End to move through the observations. The figures come from the same calculation as the table. |

The desktop **更多统计** view shows the selected range and source count. Filters wrap on narrow windows and charts switch between one and two columns. The purchases, consumption and method sections can be collapsed. A notice appears when a selection mixes currency, counts and rates. Export still uses the filtered records when the table is hidden. It is disabled when there are no rows.

<a id="settings"></a>

## Settings and startup behavior

| Setting | Meaning / important boundary |
| --- | --- |
| `DATABASE_URL` | Required backend SQLAlchemy/PostgreSQL DSN; private value. |
| `SECRET_KEY` | Required JWT signing secret; changing invalidates existing authentication expectations. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Initial administrator provisioning; existing account is not reset by startup. |
| `CORS_ORIGINS` | Comma-separated origin policy. Same-origin web deployment does not need a separate browser API host. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Main token duration, default 1440 in config. |
| `TEST_LOGIN_ENABLED` | Explicitly configure false for a private instance. Runtime code's missing-value default is true, while supplied public templates/Compose set false. Do not assume omission disables it. |
| `TEST_USERNAME`, `TEST_DATASET_ID`, `TEST_ACCESS_TOKEN_EXPIRE_MINUTES` | Optional demo account/book and token duration. Demo behavior has separate restrictions. |
| `MAX_WORKBOOK_UPLOAD_BYTES` | Backend workbook upload cap, default 25 MiB; Nginx must be compatible with upload handling. |
| `PAYMENT_SECRET_ROOT` | Protected per-book/store merchant file root. Separate from web assets and database rows. |
| `BUSINESS_TIMEZONE`, `WECHAT_TIMEZONE` | Business timing policy/fallback timezone; avoid confusing server policy with local display month boundaries. |
| `WECHAT_*` settings | Retained bill integration configuration; current startup deliberately does not start legacy synchronization. |
| Desktop local connection settings | The native monitor reads `~/.restaurant_finance_sync/config.json`; ports default to 47650/47651 via `RESTAURANT_MAIN_STATUS_PORT` / `RESTAURANT_ASSISTANT_STATUS_PORT`. Do not package a user's file as a public default. |

Compose reads the settings described by `.env.example`. To run the API directly, use `backend/.env.example`. Keep actual credentials in the installation’s private configuration. Compose specifies PostgreSQL 16 and Nginx 1.28, binds the default web port to loopback, and mounts separate volumes for the database, payment secrets and recovery files. An ordinary upgrade must preserve those volumes. The `-v` flag in `docker compose down -v` deletes them.

On startup, the API creates missing tables, adds the supported entry-timing columns, purges expired audit records, provisions the first administrator and handles legacy and test memberships. Other schema migrations and historical amount corrections need explicit work. The legacy WeChat synchronization thread stays off. Payment initiation, refunds, settlement, bank feeds, high availability and centralized monitoring require separate services.

<a id="tests"></a>

## Test a change and build a release

Run the commands below from the repository root with Python 3.12. Install the versions in the repository’s dependency files and Acorn lockfile. The packaged macOS app carries its own Python/Qt runtime, so test that app as well as the source environment. Keep generated reports, screenshots, exports and QA applications under ignored `work/`, `dist/` or external CI storage.

### Source environment and regression tests

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r build/test-requirements.txt -r desktop/requirements.txt
npm ci --prefix build/js-transform
node build/compile_exact_web.cjs

(cd backend && PYTHONPATH=.:tests python -m pytest -q tests)
for test in web/test_*.js; do node "$test" || exit 1; done
node build/test_exact_web.cjs
node build/test_i18n_backend.cjs
python build/test_fifo_contract.py
python build/test_deployment_cache_revision.py
python build/test_distribution_privacy.py
for test in build/test_v1_0_1_desktop.py build/test_v1_0_1_desktop_qt.py \
  build/test_v1_0_2_desktop.py build/test_v1_0_2_desktop_qt.py \
  build/test_v1_0_2_analytics_qt.py; do
  QT_QPA_PLATFORM=offscreen python "$test" || exit 1
done
```

The FIFO test imports the desktop module and requires Node on `PATH`, or `NODE_BINARY` set to the executable's absolute path. Native source imports `fcntl`; Windows support is not claimed. Qt tests use the offscreen platform, while ordinary native use needs a graphical session. Tests use isolated fixtures; do not load a production environment file or real ledger. Historical test filenames identify retained regression coverage and should not be renamed solely because the application version changed.

### Browser QA

Install Playwright in a separate tool directory and use its Chromium installation, or set `CHROME_EXECUTABLE` to an existing supported Chrome/Chromium executable:

```bash
npm install --prefix work/browser-qa-tools --save-exact playwright
work/browser-qa-tools/node_modules/.bin/playwright install chromium

for test in qa_web_browser qa_dashboard_charts qa_cost_ring qa_english_ui qa_inventory_english \
  qa_enhanced_analytics qa_analytics_english_advanced; do
  PLAYWRIGHT_MODULE="$PWD/work/browser-qa-tools/node_modules/playwright" \
  QA_OUTPUT_DIR="$PWD/work/qa/$test" node "build/$test.cjs" || exit 1
done
```

`QA_OUTPUT_DIR` must be a writable absolute directory. Use a new directory per run when retaining evidence; the harnesses write their reports/screenshots there. `PLAYWRIGHT_MODULE` selects the installed Node module, `CHROME_EXECUTABLE` optionally selects a browser binary, and `RELEASE_SOURCE_ROOT` optionally selects another source tree. Without that override, scripts load this repository's `web/index.html` as a local file. HTTP traffic is blocked and synthetic records replace live accounts. Keep the default assertion mode; `QA_DIAGNOSTIC=1` is a diagnostic option, not a passing acceptance run.

`build/qa_web_browser.cjs` exercises the purchase editor, same-book synchronization and both forecast displays against synthetic data. `build/qa_dashboard_charts.cjs` checks the five rendered dashboard cards and both chart selectors against fixture amounts, and captures the bilingual KPI, trend and forecast illustrations. `build/qa_cost_ring.cjs` checks the rendered center, legend and category colors across phone and desktop widths and captures the ring illustrations. On the desktop, successful workbook writes notify the open dashboard and report so that their forecast and cost inputs can be redrawn.

Browser checks cover phone/desktop widths, selected period and date rollover, chart labels/inspection, fixed English text, unchanged user values and canonical saved enums. Test the actual compiled assets after changing authored JavaScript. Screenshots alone do not establish financial or permission correctness.

### Server archive

Use a Git checkout whose intended runtime inputs are tracked. Review uncommitted changes before building; the builder requires tracked paths but is not a substitute for a clean-tree review.

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
(cd dist && shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256)
```

The output must not already exist. The archive root is `restaurant-cloud-v1.0.2/`, containing API/static web files, deployment tools, configuration examples, `VERSION` and a SHA-256 `MANIFEST.json`. It excludes databases and runtime credentials. Compare archive file hashes with the selected source, then use the deployment and file-verification procedures in [DEPLOYMENT](DEPLOYMENT.md). A product-version health response alone does not verify the build revision or served assets.

### macOS application and packaged-runtime QA

The native rebuild helper requires macOS, Python 3.12 and a trusted existing universal Python/Qt app as `--runtime-app`. That runtime is a release input supplied separately from Git. The helper replaces the main script bytecode while preserving other runtime entries, updates both architectures, sets macOS 15 as the minimum, and produces an ad-hoc signature; it does not perform Apple notarization. Choose new output paths.

```bash
python build/rebuild_macos_app.py \
  --runtime-app /absolute/path/to/Runtime.app \
  --source desktop/restaurant_cost_manager.py \
  --output dist/Finance.app --version v1.0.2 \
  --report work/qa/app-build.json

python build/verify_macos_app.py \
  --app dist/Finance.app --source desktop/restaurant_cost_manager.py \
  --runtime-app /absolute/path/to/Runtime.app --version v1.0.2 \
  --report work/qa/app-verification.json
codesign --verify --deep --strict dist/Finance.app
```

`build/qa_packaged_desktop.py` is a separate offline QA application's entry point. Do not put it into the production candidate. Build a second app and have it load the main bytecode from the candidate being tested:

```bash
python build/rebuild_macos_app.py \
  --runtime-app /absolute/path/to/Runtime.app \
  --source build/qa_packaged_desktop.py \
  --output dist/Finance-QA.app --version v1.0.2 \
  --report work/qa/qa-app-build.json

V101_SOURCE_ROOT="$PWD" \
V101_PRODUCTION_APP="$PWD/dist/Finance.app" \
V101_QA_DIR="$PWD/work/qa/packaged-arm64" \
/usr/bin/arch -arm64 "$PWD/dist/Finance-QA.app/Contents/MacOS/Finance-QA"
```

Run the same QA executable with `/usr/bin/arch -x86_64` and a separate `V101_QA_DIR` on a compatible host; Apple Silicon requires Rosetta for that run. If the reused runtime lacks `unittest.mock`, `V101_QA_STDLIB` may point to a Python 3.12 standard-library directory solely for the test harness. These variables retain historical `V101` names but test the candidate supplied in `V101_PRODUCTION_APP`. The harness blocks network and redirects writable user paths into its QA directory.

Record the tested source commit, revision, environment and actual results. Distinguish rerun checks from inherited evidence. SQLite fixtures do not prove PostgreSQL concurrency under production load; Rosetta execution does not mean physical Intel hardware was tested; a readable database dump is not a full restore rehearsal.

<a id="recovery"></a>

## Assemble a ZIP or recover an installation

To distribute the source, documentation, checked server archive and optional macOS app together, assemble them in a staging directory outside the checkout. Put `VERSION` and a generated `RELEASE_INFO.json` in its root. The builder requires `build_revision`. Include the source commit and artifact hashes as well so the recipient can trace each file. The server tar uses its own builder. For a complete ZIP, run the following commands.

```bash
python -B build/make_complete_package.py \
  --root /absolute/path/to/staging/Release \
  --output "$PWD/dist/complete-release.zip"
python -B build/verify_package.py --root /absolute/path/to/extracted/Release
```

The ZIP output must be outside the staging root and must not exist. The assembler refreshes `PACKAGE_MANIFEST.json`, preserves UTF-8 filenames, Unix modes and internal symlinks, and writes an outer `.sha256`. Exclude `.git`, dependency/virtual-environment directories and caches from staging. Re-extract to a new location and verify the manifest, embedded server archive and native signature. Public software artifacts must not contain actual server identities, personal workstation paths, business records, runtime environment values or credentials. Keep operational backups in separate protected storage.

A recoverable operational backup needs the database dump, matching application/configuration versions, runtime secrets, relevant external files, service/Nginx layout and database/role assumptions. Merchant files may live outside PostgreSQL under `PAYMENT_SECRET_ROOT`. SSH private keys, database passwords, JWT signing secrets and merchant keys serve different purposes. First rehearse restoration in an isolated environment and verify schema, data and key workflows; an Excel exchange workbook is not a complete system backup.

Program rollback and database restoration are different operations. Do not automatically overwrite a newer database with a pre-upgrade snapshot. Retain a current backup while validating a deployment and review exact targets before any later backup cleanup. The shipped deployment script retains backups and does not perform database restoration. Pause business writes through before/after database verification; inspect concurrent writes and allowed audit retention before interpreting a changed digest as corruption.

<a id="troubleshooting"></a>

## Troubleshoot a running installation

| Symptom | First checks | Avoid |
| --- | --- | --- |
| Same v1.0.2 but older page | HTML build revision, referenced asset query values, actual HTTP file hashes and service/web root. | Repeated cache clearing without checking deployed files. |
| English page still shows Chinese | Decide whether text is fixed UI or user content; inspect late render/modal, catalog and selected language. | Translating all Chinese strings or changing payload keys. |
| Net differs from gross minus fixed | Daily utilities and Other expenses; monthly saved fixed versus dated itemized basis. | Altering gross definition to force equality. |
| Day-one average unavailable | Elapsed calendar days is zero; actual net is separately valid. | Dividing by one or inventing an average. |
| Historic forecast looks like actual net | This is required after the next month's first day; compare local current date. | Restoring the old projection for a completed month. |
| Cash updates after a book switch | Book context and revision guards, shared cash cache, stale request ordering. | A new independent cash cache or optimistic application of any late response. |
| Imported amount differs | Original XML/JSON decimal spelling, normalization path, line rounding versus total rounding. | Binary float parsing followed by string conversion. |
| FIFO value drifts by cents | Cumulative lot allocation and final remainder, zero/unknown distinction. | Quantity × rounded displayed average. |
| Chart labels collide | Actual font/available width, last-label reservation, wrap space and resize observation. | Removing observations to make axis labels fit. |
| Native window too wide | Minimum sizes, control rows, scroll area ownership and Matplotlib layout. | Enlarging all controls or forcing a 1600px screen. |
| Upload fails before API route | Nginx body limit, backend cap, content type, file structure, current authorization. | Bypassing workbook validation or importing into the wrong book. |
| Deployment verifier reports changed DB | Check authorized concurrent writes and audit retention against before/after evidence. | Deleting backups or automatic DB restore before investigating. |
| Newly built macOS app behaves old | Candidate app's main bytecode hash vs final source, actual executable launched, signature and architecture. | Updating only version text or nearby `.py` file. |

<a id="api-routes"></a>

## HTTP routes by operation

Use the function name in the last column to find the route’s request model, response and permission checks. The running instance also publishes its own `/openapi.json`. A `record_key:path` can contain path-like characters and needs correct URL encoding. The two spellings of the cash route are supported aliases.

| Method | Route | Source function |
| --- | --- | --- |
| GET | `/api/v1/health` | `main.py:health` |
| POST | `/api/v1/auth/login` | `main.py:login` |
| POST | `/api/v1/auth/test-login` | `main.py:test_login` |
| GET | `/api/v1/auth/me` | `main.py:me` |
| GET | `/api/v1/users` | `main.py:list_users` |
| POST | `/api/v1/users` | `main.py:create_user` |
| PATCH | `/api/v1/users/{user_id}` | `main.py:update_user` |
| DELETE | `/api/v1/users/{user_id}` | `main.py:delete_user` |
| GET | `/api/v1/temporary-permissions` | `main.py:list_temporary_permissions` |
| POST | `/api/v1/temporary-permissions` | `main.py:create_temporary_permission` |
| DELETE | `/api/v1/temporary-permissions/{permission_id}` | `main.py:delete_temporary_permission` |
| GET | `/api/v1/datasets` | `main.py:list_datasets` |
| POST | `/api/v1/datasets` | `main.py:create_dataset` |
| PATCH | `/api/v1/datasets/{dataset_id}` | `main.py:rename_dataset` |
| DELETE | `/api/v1/datasets/{dataset_id}` | `main.py:delete_dataset` |
| GET | `/api/v1/datasets/{dataset_id}/workbooks/internal` | `main.py:download_internal_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/internal` | `main.py:upload_internal_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/internal-overwrite` | `main.py:upload_internal_workbook_with_backup` |
| GET | `/api/v1/datasets/{dataset_id}/workbooks/user` | `main.py:download_user_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/user` | `main.py:upload_user_workbook` |
| POST | `/api/v1/datasets/{dataset_id}/workbooks/user-merge` | `main.py:merge_user_workbook` |
| POST | `/api/v1/devices/register` | `main.py:register_device` |
| GET | `/api/v1/datasets/{dataset_id}/store-settings` | `main.py:get_store_settings` |
| PUT | `/api/v1/datasets/{dataset_id}/store-settings` | `main.py:update_store_settings` |
| GET | `/api/v1/datasets/{dataset_id}/cash-position` | `main.py:get_cash_position` |
| GET | `/api/v1/datasets/{dataset_id}/cash_position` | `main.py:get_cash_position` |
| PUT | `/api/v1/datasets/{dataset_id}/cash-position` | `main.py:update_cash_position` |
| PUT | `/api/v1/datasets/{dataset_id}/cash_position` | `main.py:update_cash_position` |
| GET | `/api/v1/datasets/{dataset_id}/entry-windows` | `main.py:list_entry_windows` |
| POST | `/api/v1/datasets/{dataset_id}/records/bulk-delete` | `main.py:bulk_delete_records` |
| POST | `/api/v1/datasets/{dataset_id}/records/delete-month` | `main.py:delete_month_records` |
| POST | `/api/v1/datasets/{source_dataset_id}/copy-to-ledger` | `main.py:copy_entire_ledger` |
| GET | `/api/v1/datasets/{dataset_id}/records` | `main.py:list_records` |
| GET | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}` | `main.py:read_record` |
| PUT | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}` | `main.py:write_record` |
| POST | `/api/v1/datasets/{dataset_id}/records/{record_type}/{record_key:path}/delete` | `main.py:delete_record` |
| GET | `/api/v1/datasets/{dataset_id}/changes` | `main.py:changes` |
| GET | `/api/v1/audit` | `main.py:audit_logs` |
| DELETE | `/api/v1/audit/{audit_id}` | `main.py:delete_audit_log` |
| DELETE | `/api/v1/audit` | `main.py:delete_audit_logs` |
| POST | `/api/v1/audit/delete` | `main.py:delete_audit_logs_body` |
| GET | `/api/v1/conflicts` | `main.py:list_conflicts` |
| POST | `/api/v1/conflicts/{conflict_id}/resolve` | `main.py:resolve_conflict` |
| POST | `/api/v1/datasets/{dataset_id}/inventory/name-corrections/preview` | `name_corrections.py:preview_correction` |
| POST | `/api/v1/datasets/{dataset_id}/inventory/name-corrections/apply` | `name_corrections.py:apply_correction` |

<a id="privacy"></a>

## Check a package before sharing it

Run `build/audit_distribution_privacy.py` on an extracted directory, ZIP, tar or macOS app. Give it a file containing the identifiers you need to check, either a JSON array of strings or one UTF-8 value per line. Keep this file outside both the repository and the distribution. The tool reads the package without executing its code. It searches UTF-8 and UTF-16 data, detects complete private-key blocks, validates archive paths and links, and inspects the PyInstaller CArchive/PYZ contents of both Mach-O architectures. Its findings omit secret excerpts. Run `build/test_distribution_privacy.py` to check the scanner against synthetic fixtures.

From the repository root, scan the built archive and write the report to the ignored QA directory.

```bash
python -B build/audit_distribution_privacy.py \
  dist/restaurant-cloud-v1.0.2-deploy.tar.gz \
  --forbid-file /absolute/private/identifiers.txt \
  --report work/qa/privacy-report.json
```

Repeat the scan on the complete ZIP or extracted staging directory. Review flagged workbooks, databases and configs, and inspect screenshots and logs before sharing them. The scanner counts images but does no OCR. It can match known identifiers and key signatures. Credentials, live data and recovery backups belong in private storage. Store acceptance results with the release or CI run so their source and build can be identified.
