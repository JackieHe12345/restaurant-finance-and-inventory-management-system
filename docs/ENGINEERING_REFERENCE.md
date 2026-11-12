# Engineering Reference · v1.0.2

**[← Back to the English README](../README.en.md)** · [简体中文](ENGINEERING_REFERENCE.zh-CN.md) · [CHANGELOG](../CHANGELOG.md) · [Deployment Guide](DEPLOYMENT.md)

For a change to a report, start with the calculation and its tests. For a save or sync bug, trace the record from the editor through the API to PostgreSQL. For installation steps, see the [Deployment Guide](DEPLOYMENT.md).

| What are you working on? | Start here |
| --- | --- |
| Find the code for a page or trace a save | [Source map](#source-map) · [Database records](#database) · [Saving and permissions](#saving) |
| Reconcile a number or change a chart | [Profit and inventory](#calculations) · [Month-end forecast](#month-end-profitloss) · [Charts and exports](#charts) |
| Translate a form or an error message | [Interface languages](#languages) |
| Run tests, build a release, or restore an installation | [Settings](#settings) · [Tests and builds](#tests) · [Packaging and recovery](#recovery) |
| Diagnose a fault or look up an endpoint | [Troubleshooting](#troubleshooting) · [HTTP routes](#api-routes) · [Privacy checks](#privacy) |

## How the application fits together

A **book** holds a set of business records. The same book can track sales through channels for stores A and B. A store name identifies the income source on screen. The book ID tells the server which records to read and whose account may change them.

The browser loads static HTML, JavaScript, and CSS. The FastAPI service authenticates users and stores the books in PostgreSQL. The macOS app uses PySide6 and can work with a local Excel workbook or synchronize with the service. All three have source and tests in this repository. Build the server archive and macOS app separately.

| What do you want to check? | Where to look |
| --- | --- |
| Product version | `VERSION` and the API health response report `v1.0.2`. Several builds can have that version. |
| Code behind a build | A Git commit identifies the tracked source. The build revision in the HTML distinguishes frontend updates within the same product version. |
| What the server serves | Compare the deployed files and HTTP responses with the SHA-256 hashes in the server archive’s `MANIFEST.json`. |
| Contents of a complete ZIP | The outer `.sha256` covers the ZIP bytes. `PACKAGE_MANIFEST.json` records the files, permissions, and symlinks inside. |
| Whether an upgrade preserved a ledger | Compare the database checks taken before and after the upgrade. To test recovery, restore the backup and its matching configuration in an isolated installation. |

The financial reports use the store’s management-accounting definitions below. A month can change after a correction. Use payment records to verify settlement and the applicable accounting records for statutory reporting.

<a id="source-map"></a>

## Find the source for a feature

Start with `web/index.html`. Each panel shares the same `state`, and some scripts wrap or replace a function defined earlier. For a dashboard bug, follow the script order through the workbench, charts, dashboard, and analytics modules to find the function the browser actually calls. Keep the exact-arithmetic runtime ahead of the business code.

| Source | What to edit here |
| --- | --- |
| `web/index.html` | Page markup, DOM IDs, stylesheet and script load order, build revision, and cache query strings. Check ID references before renaming an element. |
| `web/money.js` | Exact decimal arithmetic backed by BigInt. Edit this file directly. |
| `build/web-exact-source/app.js` | Shared state, permission checks, API calls, and record normalization. Also owns the original record used for editing, reports, reporting periods, and language switching. |
| `build/web-exact-source/pro.js` | Ledger, purchase, and dish editors. Also parses detail lines and provides reports and the earlier statistics screens. |
| `web/i18n-en.js`, `i18n-inventory-en.js`, `i18n-backend-en.js`, `i18n-extra-en.js` | English labels and messages for the main interface, inventory, API errors and audit history, and older screens. Load the four catalogs before `v8.js`. |
| `web/i18n-controls.js` | Displays an English month field as `YYYY-MM` and keeps the native picker, value, events, and validation. Load after the catalogs and before `v8.js`. |
| `build/web-exact-source/v8.js`, `v28.js` | Selection dialogs, store settings, and the checks that stop a request for one book from updating another. |
| `build/web-exact-source/sep04.js` | Cash balance screen, cash entries, cache updates, and support for older records. |
| `build/web-exact-source/sep05.js`, `sep07.js` | Extend existing handlers for reports, editing, permissions, and customer counts. Check which wrapper runs last. |
| `build/web-exact-source/inventory-fifo.js` | Replays stock movements in FIFO order and allocates each lot’s full value across its issues. |
| `build/web-exact-source/oct29.js` | Additional ledger and inventory controls used by the bookkeeping screens. |
| `build/web-exact-source/inventory-workspace.js` | Inventory documents, the records behind each movement, and the interface for correcting an item name. |
| `web/workbench.js`, `web/workbench.css` | Navigation, page headings, and responsive layout. Edit both files directly. |
| `build/web-exact-source/charts-oct30.js` | SVG plots and axes. Handles pointer, touch, and keyboard input and redraws charts when their container changes size. |
| `build/web-exact-source/dashboard-oct30.js` | The five dashboard cards, their month-on-month comparisons, and the dashboard charts. |
| `build/web-exact-source/analytics-oct30.js`, `web/analytics-oct30.css` | Analytics filters and views for operations, expenses, and customers. Includes the expense calculations, detail tables, and layout. |
| `desktop/restaurant_cost_manager.py` | PySide6 widgets, financial calculations, workbook access, and cloud sync. Search by class or function name in this module. |
| `backend/app/main.py` | API routes, record permissions, cash totals, database compatibility updates at startup, and audit-log maintenance. |
| `backend/app/models.py`, `database.py`, `security.py` | SQLAlchemy models, database sessions, exact JSON storage, password hashing, and JWT handling. |
| `backend/app/money.py`, `money_routes.py`, `excel_io.py` | Monetary values in HTTP requests, JSON serialization, and Excel import and export. |
| `backend/app/inventory_balance.py`, `inventory_validation.py` | Reconstruct stock quantities and validate stock levels and document amounts in the write transaction. See the browser and desktop implementations for FIFO costing. |
| `backend/app/name_corrections.py`, `ingredient_corrections.py` | Preview affected records, update linked names and stock adjustments together, detect stale requests, and save receipts so retries are safe. |
| `backend/app/store_settings.py`, `wechat_pay.py`, `wechat_sync.py` | Store settings and WeChat merchant bill integration. The legacy sync scheduler stays off at startup. |

Edit business scripts under `build/web-exact-source/`. Run `node build/compile_exact_web.cjs` to parse them with Acorn and regenerate the corresponding `web/*.js`, then commit both sets of files together. Edit HTML, CSS, `money.js`, `workbench.js`, translation catalogs, and licenses directly. The compiler lists the files it generates. In production, the browser loads the static files without Node, Acorn, a bundler, or a CDN.

<a id="database"></a>

## How a book is stored

Production uses PostgreSQL. Record contents with variable fields live in JSONB columns. Startup calls SQLAlchemy’s `create_all` and applies a short list of compatibility updates. A new schema change needs its own migration plan. Tests also run against a SQLite adapter.

| Table | What it stores | What to preserve when changing it |
| --- | --- | --- |
| `app_users` | UUID, unique username, display name, password hash (bcrypt), role, and active status. | Changing the bootstrap password in the environment leaves an existing administrator’s password in place. |
| `datasets` | Stable book ID, display name, and schema version. | Renaming preserves the ID used to look up records and permissions. |
| `user_dataset_memberships` | One row per user and book, with a default-book flag. | The server checks membership for a non-admin user even if the book is visible in the UI. |
| `devices` | Device ID, book ID, platform, device name, and last-seen time. | Use the book that was active when registration or a cache request began. |
| `sync_records` | Unique `(dataset_id, record_type, record_key)`, payload, checksum, version, sync sequence, and deletion state. | Check the expected version on write. Preserve deletion markers so other clients can apply deletions. Identify rows independently of item names. |
| `entry_timings` | First-save times, per-field and per-item timestamps, and timing data for older records. | A change to the payload must preserve the original deadlines for correcting or adding entries. |
| `audit_logs` | Values before and after a change, actor, source, event, device, version change, sequence, and timestamps. | Audit rows can expire or be deleted by an administrator. Keep independent backups. |
| `temporary_permissions` | User, book, granted role, business dates covered, and times the grant is active. | Check the date of the record as well as the time the user makes the change. |
| `sync_conflicts` | Local and server versions, both payloads, conflict status, resolution, and note. | Apply the same financial validation and permissions as for any other write. |
| `inventory_name_corrections` | Unique book and request ID pair, request hash, request and response payloads, and reason for the correction. | Receipts survive audit pruning. A retry with the original ID must carry the original request. See [name correction and recovery](../backend/NAME_CORRECTION_RECOVERY.en.txt). |

A day record can hold `daily`, `dishes`, and `fixed_expenses` arrays. Month records hold `monthly_fixed`. Global records hold settings, dictionaries, cash entries, and inventory data. Older payloads can contain rows from several business dates. An edit to one day must merge just that day’s rows in each array and preserve other dates and undated rows. If the day has no dish entries, show an empty list.

During import or editing, leave IDs, dates, versions, record keys, names, notes, and custom metadata in their original types. Preserve unfamiliar fields. Two purchases with the same name can have different units, prices, or notes. Move or delete the selected row by its identity.

An internal workbook represents records in sheets such as `__day_records`, `__month_records`, `__global_records`, `__meta`, and `__audit_records`. Record sheets carry structured `payload_json`. User workbooks organize the same business information into sheets people can edit. The import routes distinguish merging records from replacing them. For server recovery, separately back up accounts, book memberships, entry timestamps, merchant keys, runtime settings, and service configuration.

<a id="saving"></a>

## Follow a save from the editor to the database

The browser sends requests to `/api/v1` on the same origin that serves the page. Nginx forwards `/api/` with its prefix intact. Login returns a bearer JWT. Each authorized request reloads the account and checks that it is active. The roles are `viewer`, `entry`, `editor`, and `admin`. Administrators can work across books. Other users need membership in the selected book.

1. The editor captures the active login, book, and context generation. It keeps a baseline of the record and preserves fields outside the edit.
2. The client registers or reuses a device for that book, normalizes known monetary fields, calculates the checksum, and sends the expected record version.
3. In one transaction, the server checks the user’s rights, applicable time limits, expected version, and relevant inventory rules. It writes the new record version, sync sequence, and audit entry.
4. The client applies the response only while the original context is current. Switching A → B → A invalidates pending work from the first visit to A. A newer local save also advances the revision so an older refresh cannot overwrite it.

**Cash balances.** A cash adjustment can change the balance while the daily records stay the same. Check the book and cash revision on every cash response, even when the main record snapshot is unchanged. All cash views read the shared cache.

**Entry permissions.** The server tracks when each field or line was first saved. The main correction window is 30 minutes and the window for adding detail lines is 12 hours. Business dates and income cutoffs also apply. A temporary grant can raise a user’s rights for day records during the grant’s active period and for the business dates it covers. Check `_effective_record_role` and `_entry_timing_updates` before changing these rules. Editing a note or resaving an equivalent amount must keep the original clock.

**Inventory changes.** The server locks the book, replays stock movements, and checks for new shortages. Stale document versions are rejected. A name correction previews the affected records, rechecks them, and applies them in one transaction. A saved request receipt lets a retry identify work that already succeeded.

**Audit history.** The server keeps 366 days and lets administrators maintain the log. Startup can delete expired entries. Account for expiry when comparing the database before and after an upgrade.

<a id="calculations"></a>

## How the ledger calculates profit and inventory

For field formats and rounding rules, see the [shared monetary rules](../build/MONEY_CONTRACT.en.txt), [browser arithmetic and tests](../build/WEB_EXACT_MONEY.en.txt), and [API monetary rules](../backend/MONEY_BACKEND.en.txt). The [FIFO test](../build/FIFO_CONTRACT.md) follows a stock issue across two purchase lots. New or changed monetary fields cross the API as decimal strings. Python uses `Decimal` and the browser uses `Exact`. Amounts have two decimal places and unit prices have six, with `ROUND_HALF_UP`. The absolute limit is 999999999999.99 for a single amount and 999999999999.999999 for a unit price. Totals calculated from valid inputs have separate rules. Reject invalid text, booleans, NaN, and infinity. A unit price explicitly entered as zero is a known price.

When reading legacy JSON, retain the decimal text before any conversion to floating point. Read the underlying OOXML numeric cell when Excel conversion would lose precision. Normalize only the documented monetary fields, including fields inside detail rows. Preserve other metadata. Keep values in `Exact` during calculations and formatting. Convert a chart coordinate to a float only when drawing it.

The homepage cards show, in order, average daily revenue, average daily gross profit with gross margin, estimated month-end profit/loss, estimated daily profit/loss this month, and actual net profit with net margin. For the current month, the first two use records through yesterday divided by the number of calendar days through yesterday. For a completed month, they use the full month’s figures and calendar days. Card 4 shows money per calendar day. The percentage below it compares that daily amount with the previous month. Card 5 includes today’s entries and the full saved monthly fixed expense. Its net margin divides that actual net by actual revenue through today and is unavailable for a missing or zero revenue denominator. The full monthly report’s actual average daily net profit divides actual net by elapsed calendar days.

The daily trend and weekday averages both open on revenue. Each has its own selector for revenue, gross profit, net profit, or ingredient cost. The first three use daily ledger figures. Ingredient cost includes seasoning purchases. The daily trend leaves unrecorded dates empty. For a weekday average, divide the sum for that weekday by the number of its recorded dates in the selected month. A recorded day with a zero amount counts. An empty row does not. With no recorded days, that weekday has no average. The forecast uses elapsed calendar days instead.

The dashboard cost ring groups expenses for the selected day. A category keeps its color as other categories appear or disappear. The legend pairs each swatch with its label, amount, and share. The centered figure is the sum of the amounts plotted for that day. The daily ring uses positive expenses and the existing daily fixed-cost allocations. The native monthly expense chart uses whole-month fixed costs and its existing categories, which exclude fees. Reconcile its center against the sum of slices in that chart. The month-end forecast below derives its own monthly figures from the ledger.

`dayMetrics` provides category keys for the daily ring. In `build/web-exact-source/app.js`, `costDonutColors` maps each key to a color and `renderCostDonut` uses that mapping for both gradient stops and legend markers. Recompile with `build/compile_exact_web.cjs` after editing. The ring’s responsive dimensions and centered label, amount, and currency unit are in `web/reporting-oct30.css`. The native charts use `DashboardTab._draw_cost_ring`.

### Month-end profit/loss

The dashboard and full monthly report use the same result. In Chinese both show `预计月底盈亏` above `(根据 本月预计成本 和 本月预计收入 计算)`. In English the lines read **Estimated month-end profit/loss** and **(based on this month’s projected costs and revenue)**. The adjacent **i** opens on hover or click and explains the calculation, cutoffs, and change to actuals. The web help follows the interface language. The advanced analytics banner reuses this explanation. When a refresh replaces its button, an open popup reconnects to the new button and shows the latest cost inputs. The native app presents the same rules in Chinese.

For the current month, **D** is the total number of calendar days. Use the same book for every value. Last month’s averages use all its calendar days, even across a year boundary. For this month, divide revenue, ingredient costs, and other costs by the number of calendar days through yesterday. Include revenue only through yesterday. Include costs dated today as soon as they are saved, and exclude future entries. Days without records still count.

| Component | Calculation |
| --- | --- |
| Projected revenue | Current daily average revenue × D. |
| Projected fixed costs | Higher of last month’s and this month’s saved whole-month fixed expenses. Use paid utility amounts in the fixed total. |
| Projected ingredients | Combine ingredient and seasoning purchases for each period. Multiply the higher of the two daily averages by D. |
| Projected other costs | For each period, take total cost minus ingredients (including seasonings) minus its whole-month fixed expenses. This leaves daily utilities, fees, and other expenses. Multiply the higher of the two daily averages by D. |
| Projected profit/loss | Projected revenue − projected fixed costs − projected ingredients − projected other costs. |
| Estimated daily profit/loss this month | The caption reads **(Estimated month-end profit/loss ÷ days in the month)**. Divide the unrounded month-end profit/loss by D. A closed month uses actual net profit ÷ that month’s calendar days. A missing monthly result gives a dash. |

**A grocery purchase on November 11.** Ten days have elapsed in the current month. October has 31 days, and November has 30. The amounts below are in CNY.

| Item | October | November so far | November projection |
| --- | ---: | ---: | ---: |
| Fixed costs | 6,000 | 6,500 | 6,500 |
| Ingredients and seasonings | 9,300 (300/day) | 2,600 (260/day) | 9,000 |
| Other costs | 1,550 (50/day) | 750 (75/day) | 2,250 |
| Revenue through yesterday | — | 8,000 (800/day) | 24,000 |

The help shows average daily total cost of **591.67**, total cost of **17,750.00**, and revenue of **24,000.00**. Projected profit is **6,250**. Now save a CNY 600 grocery purchase dated November 11. November’s ingredient rate becomes 3,200 ÷ 10 = 320/day, above October’s 300/day. Projected ingredient cost rises to 9,600 and profit falls to **5,650**. A sale recorded for November 11 first enters the revenue projection on November 12.

**Rounding.** Let **e** be the elapsed days this month and **p** last month’s length. For each variable cost, compare `current total × p` with `previous total × e`. Both have the denominator `e × p`. Subtract the larger numerator for each of the two costs from `current revenue × p`, multiply by **D**, and subtract `projected fixed costs × e × p`. Divide the result by `e × p` once. This preserves an exact half cent even when a daily rate repeats.

**Missing entries.** If this month has no saved fixed-cost record, use last month’s fixed cost. An explicitly saved zero takes part in the comparison. Last month may contain a recorded zero or just a fixed-cost record. This month needs at least one operating record through yesterday. The forecast is unavailable on the first day of the month, for a future month, or when either period lacks the required data. In both months, “other costs” includes fees, daily utilities, and entries in the Other category.

The help shows projected costs, including the fixed component. Let **N** be the unrounded projected cost numerator used to calculate profit. Monthly total cost is `N ÷ (e × p)` and average daily total cost is `N ÷ (e × p × D)`. Round each result to cents for display. When the month closes, the same three rows show actual total cost divided by its full calendar length, actual total cost, and actual revenue. If an input is unavailable, the corresponding row shows a dash.

Card 4 uses the same profit numerator as card 3, divided once by `e × p × D`, then rounded to cents for display. In the November example above it moves from 6,250 ÷ 30 = **CNY 208.33/day** to 5,650 ÷ 30 = **CNY 188.33/day** after the purchase. At a rounding boundary, an exact November estimate of CNY 0.145 displays as CNY 0.15 on card 3. Its daily value is 0.145 ÷ 30 and displays as **CNY 0.00/day**.

To reproduce the month-on-month comparison in an empty test book, record CNY 310 revenue on January 1, 2024, and CNY 580 on February 1, 2024. Leave all costs at zero. Select February after it has closed. Card 3 shows CNY 580.00. Card 4 compares 580 ÷ 29 = **CNY 20.00/day** with January’s 310 ÷ 31 = **CNY 10.00/day**, an increase of **100.0%**. Card 5 shows actual net of CNY 580.00 and a 100.0% net margin. The same fixture in 2023 uses CNY 560 for February and 28 calendar days.

Compare the two unrounded daily rates over a common denominator. If November’s net is CNY 0.03 and October’s is CNY 2.00, the rates are 0.03 ÷ 30 and 2.00 ÷ 31. The decrease is exactly 98.45%, displayed as **98.5%**.

**Where to make a change.** In `build/web-exact-source/app.js`, `monthOverviewMetricsV102` gathers the ledger totals and `monthForecastV102` derives the forecast on each refresh. It returns `net`, `dailyNet`, `netNumerator`, and `dailyNetDenominator`. The dashboard’s `summary` in `dashboard-oct30.js` passes each month’s numerator and divisor to `monthChangeV102`. The dashboard and monthly report both read that forecast. Their help compares the unrounded candidates, shows both amounts, and identifies the month used or a tie. Fixed costs are monthly amounts. Ingredient and other costs are daily rates.

The desktop equivalent is `calc_dashboard_month_kpis` in `desktop/restaurant_cost_manager.py`. It returns `projected_daily_net` for `DashboardTab._refresh_month_headlines`. Run `node web/test_v1_0_2_dashboard.js` for the February example and rounding cases, `python build/test_v1_0_2_desktop.py` for the desktop calculation, and `QT_QPA_PLATFORM=offscreen python build/test_v1_0_2_desktop_qt.py` for the actual card order, amounts, and margins. A fixture that takes ingredients from one month and other costs from the other catches accidental coupling. Include today’s purchase and a seasoning item to exercise the cutoff and catch double counting.

The client’s local date determines when a month ends. Both clients check for a date change about every five seconds, even if the ledger has no new entries. The browser checks again when its tab becomes visible. The macOS app waits for an open dialog to close and retries a failed read. From the first of the next month, the forecast card for the completed month shows actual net profit. The selected period stays in place. The client derives this figure from the ledger, so a correction to an earlier month changes its displayed result.

| Client date | Selected month | Forecast-card amount |
| --- | --- | --- |
| October 31 | October | Current-month projection. |
| November 1 | October | October actual net; previous-month cost is no longer needed. |
| November 1 | November | Unavailable until a day elapses; actual net can exist separately. |
| January 1 | Previous December | December actual net. |
| November 10 | December | Unavailable future period. |

| Metric | Calculation or accounting treatment |
| --- | --- |
| Revenue | Use the current channel entries when present. For older records with a total only, read `收益` or `总金额`. A stored total may already include the individual channels. |
| Gross profit | Revenue − food − seasoning − transaction fees. |
| Gross margin | Average daily gross profit ÷ average daily revenue, using the same cutoff. An unknown or zero revenue denominator leaves the margin unavailable. |
| Variable expense | Food + seasoning + daily utilities + Other + fees. |
| Monthly fixed expense | Saved monthly wages, rent and property charges, paid utilities (water, electricity, and gas), and other fixed expenses. |
| Monthly total cost | Sum of daily variable expense + full saved monthly fixed expense. |
| Monthly net | Revenue − monthly total cost. |
| Change percentage | `(current − prior) / abs(prior) × 100`. Show the reason when a missing or zero prior value prevents comparison. |
| Cash force adjustment | Set the actual cash balance on a given date. This adjustment leaves operating income and costs unchanged. |
| Expense basis comparison | Compare saved monthly fixed totals with dated payments recorded one by one. Adding both would count the same costs twice. |

Inventory identifies an item by category, name, and unit. A different unit identifies a different stock item. Each FIFO lot keeps its original quantity, amount, and unit price, plus its remaining quantity. The cost of an issue is `round(original lot amount × cumulative issued / original quantity, 2) − already allocated`. The last issue takes any remaining cents. Subtract the allocated cost from the lot’s booked amount to find its remaining value. Keep quantities with unknown prices identifiable throughout.

Monthly operating profit uses purchases and expenses recorded in the ledger. FIFO measures the cost of stock used. Packaging, consumables, and phone charges keep their recorded expense category. When reconciling gross profit against net profit, also deduct daily utilities and Other expenses alongside fixed costs. The detailed daily card can use dish costs when available. Monthly and average gross profit use gross profit from the daily ledger. Expense details may show expected utility bills. Monthly fixed costs and net profit use the amounts paid.

To set an actual cash balance, open **Add cash entry → Balance override** and enter the date and balance. This posts a balance adjustment and preserves the earlier cash entries. It creates no revenue or expense. Ordinary entries follow their existing deletion rules. Historical entries marked `system_locked` stay protected.

<a id="languages"></a>

## Translate the interface and preserve what people entered

The browser supports English and Chinese. The macOS app uses Chinese. Translate system text such as dialog buttons, validation messages, role names, and chart legends. Preserve the original spelling of names for books, stores, products, dishes, and custom income sources. Do the same for notes, people, suppliers, and units. Both languages use the same stored keys and enum values.

For each new translated field, check the following behavior.

1. Add the fixed label to the rendering code or catalog. Keep the stored field key and value stable.
2. For a store name followed by a payment channel, escape the store name for HTML and translate the channel suffix. For an error message, translate the sentence template and insert the user’s value as entered.
3. Switch languages with an unsaved draft open. The current panel and any later dialog must use the selected language. Check the book, date, amount, draft, and outbound save payload.
4. Test a product whose name exactly matches a dictionary entry. Inspect role-specific screens, placeholders, titles, and accessible labels as well as the visible text.

English uses `CNY` for the same yuan amount. For `input[type=month]`, `web/i18n-controls.js` displays `YYYY-MM` over the native control so the field has the same format on different operating systems. The original control still handles its value, validation, events, and picker. The browser and operating system supply the popup calendar.

### Where translations are applied

`web/index.html` loads these four catalogs after `app.js` and `pro.js`, before `v8.js` builds its lookup table.

| File | Scope |
| --- | --- |
| `web/i18n-en.js` | Shared labels, system-message templates, `systemMessage`, and text for alerts, confirmations, and prompts. |
| `web/i18n-inventory-en.js` | Inventory screens, receiving, issues, stocktakes, and the dialogs for batches and name corrections. |
| `web/i18n-backend-en.js` | API errors, validation and status messages, field labels, and structured audit summaries. |
| `web/i18n-extra-en.js` | Labels and messages for older ledger, reporting, and cash screens, as well as selectors, accounts, temporary grants, and Excel operations. |

These files extend `SYSTEM_EN` and `SYSTEM_EN_PATTERNS`. Load the month control adapter after all four catalogs and before `v8.js`. Edit the catalogs directly. They ship in the server manifest with the same cache revision as the other scripts. The Exact compiler processes a separate set of business scripts.

`v8.js` translates fixed text nodes and display attributes such as `placeholder`, `title`, `aria-*`, and `data-label`. It remembers each original string and its translation. If an asynchronous render changes that string, the observer translates the new source. It batches updates and writes only changed values. `v28.js` uses compatible metadata to retain the store name while translating the fixed payment-channel label.

Mark names, notes, and other user-entered text with `data-user-content`. Editable fields and designated book/account selectors also have explicit exclusions. `sep07.js` applies the marker to read-only copies of input values and updates them only when the value changes. Preserve this marker when recreating a node. Otherwise the translation observer and read-only view can overwrite each other repeatedly.

An HTML option without a `value` submits its displayed label. Set the option’s original value explicitly before translating the label. A cash type or fixed-cost category will then submit the same value in either language. Keep both the identifier and text of user-created options.

`translateBackendMessage` matches known server messages against anchored patterns. It translates known field names, error locations, and nested errors, and preserves usernames, notes, units, and paths. Add a catalog entry when introducing a new API error template. The response payload and its stored keys stay intact.

`translateAuditSummary(summary, item)` reads the structured `before_payload`, `after_payload`, and reason. It names known fields, keeps their entered values, and labels each change Added, Removed, Changed, or Cleared. The summary shows up to 20 changes and limits recursion depth. For a full comparison, inspect the original payloads. Older responses may lack these fields. Translate recognized fixed wording in those summaries and preserve ambiguous text, including a note containing semicolons.

Run `build/qa_english_ui.cjs`, `build/qa_inventory_english.cjs`, `build/test_i18n_backend.cjs`, and `build/qa_enhanced_analytics.cjs` alongside the ledger and money tests. Switch to English and back with a modal open. Check API errors, saved option values, and read-only copies of user input. A name that matches a catalog entry should survive the round trip verbatim, and translation should stop once the text has settled.

<a id="charts"></a>

## Read the charts and reconcile a CSV export

Open **Analytics** and select operations, expenses, or customers. Start with the selected period, metric, and comparison month above the chart. The source table shows the records behind the total. In the expense view, compare monthly fixed-cost entries with dated payments. They are two ways of looking at the same expense.

| On screen | How to check it |
| --- | --- |
| Summary cards | Every view shows the number of recorded days. Operations adds the largest expense category and the number of profitable days. Expenses shows the largest category and the difference between monthly fixed costs and itemized payments. Customers shows the busiest day and how many recorded days have a positive customer count. |
| Trend | Line and bar views use the same observations. The statistics show their count, mean, minimum, and maximum. An unrecorded date leaves a gap and a loss plots below zero. |
| Detail table and CSV | Sorting and filtering apply to the export. The total covers all filtered rows across pages. CSV headings follow the selected language and user-entered values keep their spelling. |
| Axis labels | The SVG renderer measures the available width, shortens dates when the period supplies context, reserves space at the ends, and wraps category labels. Resizing changes the labels’ spacing. All observations stay available. |
| Exact chart values | Hover, tap, or focus a point to read the complete date or category and amount. Use the arrow keys or Home/End to move through the observations. The figures come from the same calculation as the table. |

The desktop **更多统计** view shows the selected range and source count. Filters wrap on narrow windows and charts switch between one and two columns. The purchases, consumption, and method sections can be collapsed. A notice appears when a selection mixes currency, counts, and rates. Export still uses the filtered records when the table is hidden. It is disabled when there are no rows.

<a id="settings"></a>

## Settings and startup behavior

| Setting | Effect and default |
| --- | --- |
| `DATABASE_URL` | Required SQLAlchemy connection string for PostgreSQL. It can contain credentials. |
| `SECRET_KEY` | JWT signing key. Replacing it invalidates tokens signed with the previous key. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Credentials for creating the first administrator. Restarting with different values leaves existing accounts in place. |
| `CORS_ORIGINS` | Comma-separated allowed origins. With a same-origin deployment, the browser reaches the API on the same host as the page. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Lifetime of a standard access token in minutes. The default is 1,440 (24 hours). |
| `TEST_LOGIN_ENABLED` | Set explicitly to `false` for a private installation. If omitted, the API defaults to `true`. The supplied templates and Compose set it to `false`. |
| `TEST_USERNAME`, `TEST_DATASET_ID`, `TEST_ACCESS_TOKEN_EXPIRE_MINUTES` | Demo username, book ID, and token lifetime. The demo account has its own access restrictions. |
| `MAX_WORKBOOK_UPLOAD_BYTES` | Maximum workbook upload size. The backend defaults to 25 MiB. Check the Nginx request limit as well. |
| `PAYMENT_SECRET_ROOT` | Directory for merchant files, organized by book and store. Protect and back up this directory separately from the database and web assets. |
| `BUSINESS_TIMEZONE`, `WECHAT_TIMEZONE` | The server’s business timezone and its fallback. The dashboard uses the client’s local date for month rollover. |
| `WECHAT_*` settings | Merchant bill settings for the WeChat integration. The API startup sequence leaves the legacy scheduler off. |
| Desktop local connection settings | The desktop monitor reads `~/.restaurant_finance_sync/config.json`. `RESTAURANT_MAIN_STATUS_PORT` defaults to 47650 and `RESTAURANT_ASSISTANT_STATUS_PORT` to 47651. Keep user-specific config files out of public distributions. |

Compose reads the settings described by `.env.example`. To run the API directly, use `backend/.env.example`. Keep actual credentials in the installation’s private configuration. Compose specifies PostgreSQL 16 and Nginx 1.28, binds the default web port to loopback, and mounts separate volumes for the database, payment secrets, and recovery files. An ordinary upgrade must preserve those volumes. The `-v` flag in `docker compose down -v` deletes them.

On startup, the API creates missing tables, adds the supported entry-timing columns, purges expired audit records, provisions the first administrator, and handles legacy and test memberships. Other schema migrations and historical amount corrections need explicit work. The legacy WeChat synchronization thread stays off. Payment initiation, refunds, settlement, bank feeds, high availability, and centralized monitoring require separate services.

<a id="tests"></a>

## Test a change and build a release

Run the commands below from the repository root with Python 3.12. Install the versions in the repository’s dependency files and Acorn lockfile. The packaged macOS app carries its own Python/Qt runtime, so test that app as well as the source environment. Keep generated reports, screenshots, exports, and QA applications under ignored `work/`, `dist/`, or external CI storage.

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

The FIFO test imports the desktop module and runs Node. Put Node on `PATH` or set `NODE_BINARY` to its absolute path. The desktop source imports `fcntl` and requires a compatible operating system. The Qt tests run offscreen. To use the desktop application interactively, start a graphical session. Run tests with the isolated fixtures. File names containing older versions identify regressions that still need coverage.

### Browser QA

Install Playwright and its Chromium binary under a dedicated tools directory. To reuse a supported Chrome or Chromium installation, set `CHROME_EXECUTABLE` to the browser executable.

```bash
npm install --prefix work/browser-qa-tools --save-exact playwright
work/browser-qa-tools/node_modules/.bin/playwright install chromium

for test in qa_web_browser qa_dashboard_charts qa_cost_ring qa_english_ui qa_inventory_english \
  qa_enhanced_analytics qa_analytics_english_advanced; do
  PLAYWRIGHT_MODULE="$PWD/work/browser-qa-tools/node_modules/playwright" \
  QA_OUTPUT_DIR="$PWD/work/qa/$test" node "build/$test.cjs" || exit 1
done
```

Set `QA_OUTPUT_DIR` to a writable absolute path. Choose a fresh directory for each run whose reports and screenshots you want to keep. `PLAYWRIGHT_MODULE` points to the installed Node module. Set `CHROME_EXECUTABLE` to select another browser binary, or `RELEASE_SOURCE_ROOT` to test a different source checkout. By default the tests open this repository’s `web/index.html` as a local file, block HTTP traffic, and use synthetic records. Leave assertions enabled when recording pass/fail results. `QA_DIAGNOSTIC=1` is for investigating failures.

`build/qa_web_browser.cjs` checks the purchase editor, synchronization within one book, and both forecast displays. `build/qa_dashboard_charts.cjs` checks the amounts on all five cards and both chart selectors, then captures the dashboard, trend, and forecast in both languages. `build/qa_cost_ring.cjs` checks the ring’s center, legend, and category colors at phone and desktop widths. The macOS client refreshes an open dashboard and report after a successful workbook write.

After editing the business JavaScript, run the browser tests against the regenerated files. They check layout at phone and desktop widths, period changes and midnight rollover, chart interaction, translated labels, and preservation of user text and stored enum values. Run the calculation and permission tests alongside these UI checks.

### Server archive

Build from a Git checkout. The builder checks that runtime files are tracked, then reads their current contents, including uncommitted changes. Review `git status` and the diff before packaging.

```bash
python build/make_release.py --output dist/restaurant-cloud-v1.0.2-deploy.tar.gz
(cd dist && shasum -a 256 -c restaurant-cloud-v1.0.2-deploy.tar.gz.sha256)
```

Choose a new output path. The archive expands to `restaurant-cloud-v1.0.2/` and contains the API, static web files, deployment tools, configuration examples, `VERSION`, and `MANIFEST.json` with SHA-256 hashes. Leave the database and runtime credentials in the installation. Compare the archived files with your chosen source revision. After deployment, check the HTML build revision and the hashes of the files actually served. The health endpoint reports only the product version. Follow the [Deployment Guide](DEPLOYMENT.md).

### macOS application and packaged-runtime QA

On macOS, use Python 3.12 and pass an existing trusted universal Python/Qt app to `--runtime-app`. Obtain the runtime separately from the Git checkout. The builder replaces the main script’s bytecode in both architectures, preserves the other runtime entries, sets macOS 15 as the minimum, and signs the app ad hoc. Apple notarization is a separate step. Use a fresh path for the output.

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

Build a second, offline QA app with `build/qa_packaged_desktop.py` as its entry point. This app loads the main bytecode from the production candidate and tests that exact copy.

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

On a compatible host, run the QA executable again with `/usr/bin/arch -x86_64` and a fresh `V101_QA_DIR`. Apple Silicon requires Rosetta for the Intel run. If the runtime lacks `unittest.mock`, set `V101_QA_STDLIB` to a Python 3.12 standard-library directory for this test. The `V101` variable names remain for compatibility. `V101_PRODUCTION_APP` selects the app under test. The harness blocks network access and redirects user writes into its QA directory.

When reporting results, record the source commit, build revision, test environment, and outcome. Identify any checks reused from a previous build. Use PostgreSQL under representative load to assess production concurrency, identify Rosetta when reporting Intel results, and restore a dump in isolation to demonstrate recovery.

<a id="recovery"></a>

## Assemble a ZIP or recover an installation

To distribute the source, documentation, checked server archive, and optional macOS app together, assemble them in a staging directory outside the checkout. Put `VERSION` and a generated `RELEASE_INFO.json` in its root. The builder requires `build_revision`. Include the source commit and artifact hashes as well so the recipient can trace each file. The server tar uses its own builder. For a complete ZIP, run the following commands.

```bash
python -B build/make_complete_package.py \
  --root /absolute/path/to/staging/Release \
  --output "$PWD/dist/complete-release.zip"
python -B build/verify_package.py --root /absolute/path/to/extracted/Release
```

Choose a new ZIP path outside the staging directory. The builder updates `PACKAGE_MANIFEST.json`, preserves UTF-8 filenames, Unix file modes, and internal symlinks, and writes a `.sha256` for the ZIP. Leave Git metadata, dependencies, virtual environments, and caches out of staging. Extract the ZIP elsewhere and check the manifest, embedded server archive, and app signature. A public package must exclude server identifiers, personal workstation paths, business records, runtime configuration values, and credentials. Keep operational backups in protected storage.

For recovery, keep the database dump with the matching program version, runtime configuration and secrets, external files, service and Nginx configuration, and database role requirements. Include the merchant files under `PAYMENT_SECRET_ROOT` if the installation uses them. Account separately for SSH keys, database passwords, JWT signing secrets, and merchant keys. Rehearse the restore in isolation, then verify the schema, records, and essential workflows. Excel exchange covers business records only.

The deployment script keeps upgrade backups and leaves the database in place when rolling back the application. Keep business writes paused until the before-and-after database checks finish. If a digest changes, check for concurrent writes and expired audit records before considering a restore. Restoring an older dump can discard later entries. Retain the backup through verification, and review the exact paths before deleting old copies.

<a id="troubleshooting"></a>

## Troubleshoot a running installation

| Symptom | What to check |
| --- | --- |
| The footer says v1.0.2 but the page still looks old | Read the build revision in the served HTML. Follow its asset URLs, compare the returned hashes with the manifest, and confirm the active service and web root. |
| Chinese text appears in English mode | Check whether the text is a built-in label or a value the user entered. For fixed text, check the active language, catalog, and render path. In the cash table, some automatic descriptions, including `当日收入` (daily revenue), go through the same rendering path as user notes and still appear in Chinese. |
| Gross profit minus fixed costs differs from net profit | Reconcile daily utilities and Other expenses. Compare saved monthly fixed costs and itemized payments on their own terms. |
| The daily average is blank on the first of the month | Zero calendar days have elapsed. An actual net profit can already exist even though the daily average is unavailable. |
| A past forecast shows actual net profit | Check the client’s date. From the first day of the following month, the card uses actual net profit. |
| A balance changes after switching books | Trace which book and cash revision each request captured. Check the shared cache and the order in which responses arrived. |
| An imported amount differs from the source | Read the original decimal text in XML or JSON, trace its normalization, and check whether rounding occurred per row or on the total. |
| FIFO costs differ by a cent | Check the cumulative allocation and the last issue from each lot. Preserve the distinction between a known zero price and an unknown price. |
| Axis labels overlap | Measure text at the actual font and container width. Check space for the final tick and wrapped labels, then check that resizing triggers a redraw. |
| The desktop window is too wide | Inspect minimum widget widths, wrapping of control rows, scroll areas, and the Matplotlib layout at the affected window size. |
| A workbook upload fails | Check the Nginx request limit first, then the backend size limit, content type, workbook structure, target book, and user permissions. |
| Database verification reports a changed digest | Compare the before-and-after records and investigate authorized writes or audit expiry while the backup is still available. |
| A rebuilt macOS app has the previous behavior | Identify the executable that launched. Compare the packaged main bytecode against the final source, then check the app signature and the architecture that ran. |

<a id="api-routes"></a>

## HTTP routes by operation

Use the function name in the last column to find the route’s request model, response, and permission checks. The running instance also publishes its own `/openapi.json`. A `record_key:path` can contain path-like characters and needs correct URL encoding. The two spellings of the cash route are supported aliases.

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

Run `build/audit_distribution_privacy.py` on an extracted directory, ZIP, tar, or macOS app. Give it a file containing the identifiers you need to check, either a JSON array of strings or one UTF-8 value per line. Keep this file outside both the repository and the distribution. The tool reads the package without executing its code. It searches UTF-8 and UTF-16 data, detects complete private-key blocks, validates archive paths and links, and inspects the PyInstaller CArchive/PYZ contents of both Mach-O architectures. Its findings omit secret excerpts. Run `build/test_distribution_privacy.py` to check the scanner against synthetic fixtures.

From the repository root, scan the built archive and write the report to the ignored QA directory.

```bash
python -B build/audit_distribution_privacy.py \
  dist/restaurant-cloud-v1.0.2-deploy.tar.gz \
  --forbid-file /absolute/private/identifiers.txt \
  --report work/qa/privacy-report.json
```

Repeat the scan on the complete ZIP or extracted staging directory. Review any flagged workbooks, databases, or configuration files. Inspect screenshots and logs before sharing them. The scanner counts images and matches known identifiers and key signatures. Text visible only in an image requires a separate review. Keep credentials, live data, and recovery backups in private storage. Save test reports with the release or CI run that produced them.
