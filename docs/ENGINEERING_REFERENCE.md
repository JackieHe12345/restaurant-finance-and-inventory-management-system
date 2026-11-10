# Engineering reference — v1.0.2

This reference describes the architecture, data contracts, build tools and operational boundaries of the repository. Product changes are recorded in [CHANGELOG](../CHANGELOG.md); installation and deployment procedures are in [DEPLOYMENT](DEPLOYMENT.md). [中文版](ENGINEERING_REFERENCE.zh-CN.md).

## 1. Product and ownership boundaries

The system combines restaurant revenue recording, purchases, daily expenses, monthly fixed expenditure, cash balance, dish usage, inventory, multiple independent books, accounts/permissions, audit history and Excel exchange. A book can contain A/B store income channels. Store labels and business names are user data; books remain separate authorization and persistence domains.

There are three executable forms: a static browser client; a FastAPI service backed by PostgreSQL; and a PySide6 macOS desktop application that works with local Excel and cloud synchronization. The repository contains their sources, tests and build/deployment tools. Server archives and native applications are generated release artifacts, separate from the source tree.

Do not confuse these objects:

| Object | Authority | Does not prove |
| --- | --- | --- |
| `VERSION` / API `v1.0.2` | Product compatibility/version label. | That two same-version builds have identical features or files. |
| HTML build revision | Identifies a particular build within the product version. | That the currently running server has received it. |
| Git commit and source tree | Identifies the exact versioned source. | That uncommitted edits or installed binaries match it. |
| Server `MANIFEST.json` | SHA-256 of the runtime archive's files. | Preservation of real ledger records during deployment. |
| `PACKAGE_MANIFEST.json` and outer `.sha256` | Full distribution files, modes/symlinks and ZIP bytes. | That a data backup can be restored without checking its dependencies. |
| Deployment before/after evidence | Particular server state and comparison at a recorded time. | Current availability of old backups or success of later edits. |

The interface is a management-bookkeeping view. A displayed profit figure does not establish formal accounting classification, payment completion or an immutable month closing. Gross-profit and expense definitions are explicit application contracts described below.

## 2. Source topology and browser load order

The browser is plain JavaScript rather than a component framework. It has one HTML document with page panels, shared mutable `state`, feature modules and later wrappers/overrides. Keep the `<script>` order in `web/index.html` deliberate: exact arithmetic must be available before business modules, and the current workbench/chart/dashboard/analytics layers load after their older foundations. Locate the last active definition when debugging. A grep hit in `app.js` alone is not enough.

| Source location | Primary responsibility / edit caution |
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
| `build/web-exact-source/analytics-oct30.js`, `web/analytics-oct30.css` | Analytics state, operating/expense/customer exploration, expense bases, source tables and professional workspace presentation. |
| `desktop/restaurant_cost_manager.py` | Native widgets and native data/financial/synchronization logic in a large single module. Use symbol/class context, not old line numbers. |
| `backend/app/main.py` | Public API routes, record policy, authorization, cash aggregation, startup compatibility and audit maintenance. |
| `backend/app/models.py`, `database.py`, `security.py` | SQLAlchemy schema, exact JSON persistence, sessions and JWT/password operations. |
| `backend/app/money.py`, `money_routes.py`, `excel_io.py` | Monetary input/serialization, exact JSON HTTP parsing and workbook import/export. |
| `backend/app/inventory_balance.py`, `inventory_validation.py` | Quantity replay and transaction-time stock/amount guards; not a third FIFO cost engine. |
| `backend/app/name_corrections.py`, `ingredient_corrections.py` | Preview, coordinated name updates, stock adjustment, stale-state detection and durable idempotency receipts. |
| `backend/app/store_settings.py`, `wechat_pay.py`, `wechat_sync.py` | Store configuration and retained merchant bill code; old scheduler is not started by current startup. |

Authoritative business JavaScript is under `build/web-exact-source/`. `node build/compile_exact_web.cjs` parses with Acorn and emits the corresponding `web/*.js`. Do not edit generated copies alone. HTML, CSS, `money.js`, `workbench.js`, the localization assets and licenses are direct static sources. Consult the compiler's own file list before classifying a new asset. Runtime browsers do not require Node, Acorn, a bundler or CDN.

## 3. Persistence model and identity

PostgreSQL is the supported production store. SQLAlchemy JSONB is used for flexible business payloads; the SQLite adapter in tests is not a supported production storage option. Initialization is `create_all` plus narrowly implemented compatibility additions, not a general migration engine.

| Table | Identity and purpose | Maintenance invariant |
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

## 4. Request lifecycle, concurrency and permissions

The web uses same-origin `/api/v1`; Nginx serves assets and proxies `/api/` without removing that prefix. A static file server alone can show the page but cannot authenticate or store a ledger. Login returns a bearer JWT; backend authorization reloads the account and active state. Roles are `viewer`, `entry`, `editor`, `admin`. Administrators have deliberate cross-book authority; other users need membership. Temporary grants can narrow the permitted business dates/time.

A typical save sequence is: capture book/login/context generation → preserve editor baseline and unrelated payload fields → register/reuse that book's device → normalize known monetary fields and checksum → send the write with expected version → enforce server access/timing/inventory rules under transaction → commit version/sequence/audit → apply response only if the active UI still represents the captured context. An A→B→A switch must still invalidate an old asynchronous operation. A successful newer local write increments a revision so an older refresh cannot overwrite its cache.

Cash has its own server result and revision. It can change without daily-record changes; an unchanged main-record snapshot is not permission to skip a new cash response. Every cash load must check book identity and revision before rendering. Keep shared cash state synchronized rather than adding another independent stale cache.

Entry-only users have server-owned per-field/per-item policies. The existing principal windows are 30-minute corrections and a 12-hour detail-addition window, plus business-date/income cutoff rules. Use `_effective_record_role`, `_entry_timing_updates` and related tests as the implementation authority. Do not use the mutable record `updated_at` as the only clock; changing a note or saving equivalent numeric text must not reopen old entries.

Inventory writes lock the relevant book before replaying quantities and checking new shortages. Expected version checks reject stale inventory documents. Name correction first builds a preview/write-set, then checks current state and applies all linked changes in one transaction with a durable request receipt. Do not implement the same workflow as a loop of unrelated client PUT requests.

The API's audit retention is 366 days with administrator maintenance routes. Startup can purge expired audit rows; deployment comparison therefore distinguishes allowed retention from business-data changes.

## 5. Financial and inventory contracts

Use `build/MONEY_CONTRACT.txt`, `build/FIFO_CONTRACT.md` and `backend/MONEY_BACKEND.txt` alongside this section. Amounts are decimal strings at new/changed API boundaries, Python `Decimal` and browser `Exact` during arithmetic, two decimal places for money and six for unit prices, `ROUND_HALF_UP`. Reject invalid text, boolean, NaN, Infinity and out-of-range single inputs. Known zero differs from unknown price. Single-input amount limits are ±999999999999.99; unit-price limit is ±999999999999.999999. Valid derived totals are treated separately from per-entry caps.

Legacy numeric JSON is read without losing its original decimal spelling. OOXML numeric cells are inspected before conversion where necessary. Only known financial fields and their known structured detail paths are normalized; arbitrary metadata is not converted wholesale. Chart coordinates may become ordinary floats at the final drawing boundary, never for financial persistence. Formatting an Exact value must not silently invoke `Number` during calculation.

The homepage has five cards in this order: average daily revenue; average daily gross profit (gross margin); estimated month-end profit/loss; average daily net profit (net margin); net profit (net margin). All use the same neutral card treatment; positive/negative amount colors retain their meaning. Each compares the corresponding previous-month metric. The forecast explanation starts on a new line. Exact Chinese labels and report wording are recorded in the v1.0.2 [changelog](../CHANGELOG.md).

Current-month average revenue/gross exclude today and divide by elapsed calendar days, whereas actual monthly net includes today's recorded activity, excludes future dates and includes the full saved monthly fixed expenditure. Average daily net divides that actual net by elapsed calendar days. Both net margins divide actual monthly net by the same month's actual revenue, including today; missing/zero revenue makes the margin unavailable. Day one has no elapsed-day average. Completed months use all calendar days; future months are unavailable. Missing previous-month cost does not fall back to current-month cost.

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
| Current forecast | Average revenue through yesterday × calendar days − previous month's total cost. |
| Change percentage | `(current − prior) / abs(prior) × 100`; zero/missing prior needs an explicit unavailable reason. |
| Cash force adjustment | Set target actual balance as of a date; not operating income or cost. |
| Expense basis comparison | Saved monthly fixed totals versus itemized dated fixed payments; do not add both. |

Inventory identity is category/name/unit. Different units are not silently converted. FIFO keeps original lot quantity/value/price and remaining quantity. Each issue cost is the change in rounded cumulative allocation: `round(original lot amount × cumulative issued / original quantity, 2) − already allocated`. A fully consumed lot allocates all remaining cents. Remaining value equals original booked value minus allocated value, not rounded remaining quantity × displayed price. Unknown-priced quantities remain explicit.

Purchasing expense and FIFO consumption cost answer different questions. Monthly operating profit uses the purchase/expense basis. Packaging, consumables and phone costs retain their recorded expense classification. Gross minus fixed can therefore still differ from net by daily utilities and Other expenses. The detailed daily card can use dish cost when present, while monthly/average gross totals use daily bookkeeping gross. Expected utility amounts may appear in expense details; actual monthly fixed expenditure and net use paid amounts.

The cash balance sheet has one manual target-balance entry point: Add an item → Force balance adjustment. This adjusts balance as of a date without creating revenue/expense or replacing earlier transactions. Ordinary entries retain their deletion rules; historical `system_locked` entries remain protected. There is no separate balance-correction form.

## 6. English display versus user data

The browser English mode must cover fixed navigation, labels, placeholders, dialog controls, validation/status messages, report/graph legends, fixed categories, role labels and dynamic system text. It must not translate user input. User-origin book/store/product/dish/custom income names, notes, people, suppliers and arbitrary units remain byte-for-byte semantically unchanged. Stored Chinese schema keys and enum values remain compatibility keys even when their displayed labels are English. The native app remains Chinese; there is no native English mode in this version.

Rules for extending localization:

1. Add a fixed English label at the rendering boundary and a Chinese label in the existing language path/catalog. Keep storage keys independent of presentation.
2. For a label such as `<store name> + payment channel`, preserve the store name and translate only the known channel suffix. Escape user strings before HTML insertion.
3. For dynamic error text, translate the system sentence/template and separately preserve interpolated user content. Never replace all Chinese text in record JSON, field values or audit payloads.
4. Language changes must re-render current panels and future dialogs without triggering a save, discarding an unsaved draft or changing selected book/date/amount.
5. Check all pages, role-specific panels and modals, not just the visible sidebar. Check placeholders/title/aria text as well as normal text nodes.
6. Include synthetic Chinese user names that exactly match dictionary entries, to catch accidental user-data translation; check outbound save payloads remain unchanged after language switching.

Changing language never changes CNY into USD or exchanges a currency amount. A display unit may become `CNY`/English text; the underlying money remains the same currency and amount. In English mode, `input[type=month]` uses an ISO `YYYY-MM` display overlay supplied by `web/i18n-controls.js`, removing OS-localized year/month suffixes from the application field. The original native input retains its `.value`, validation, events and calendar-picker behavior. The picker popup itself and browser chrome remain controlled by the browser/operating system; the application does not claim to translate them.


### Localization runtime architecture

The four direct static catalogs load after `app.js`/`pro.js` and **before `v8.js`** builds its presentation map:

| File | Scope |
| --- | --- |
| `web/i18n-en.js` | Shared fixed labels, system-message templates, `systemMessage` and alert/confirm/prompt presentation. |
| `web/i18n-inventory-en.js` | Inventory workspace, receiving/issues/stocktakes, batch and name-correction dialogs. |
| `web/i18n-backend-en.js` | Known API error/validation/status templates, canonical field display labels and structured audit summaries. |
| `web/i18n-extra-en.js` | Remaining legacy ledger/report/cash, picker, account, grant and Excel labels/messages. |

After these four catalogs, `web/i18n-controls.js` installs the month-input display adapter; it also loads before `v8.js`. This adapter changes the displayed month format, not its canonical `YYYY-MM` value or input behavior.

Catalogs extend `SYSTEM_EN` / `SYSTEM_EN_PATTERNS`; adding a catalog after `v8.js` has built its map is not equivalent to loading it in the documented order. These assets are maintained directly, included in the server manifest, and carry the same current cache revision as other scripts. They are not part of the Exact arithmetic compiler's business-source input set.

`v8.js` translates fixed text nodes and display attributes such as placeholder/title/aria/data-label, preserving source/output pairs in metadata. When an asynchronous renderer changes a node, the new content becomes the translation source instead of reusing an obsolete remembered sentence. The queued observer coalesces updates and only writes different values. `v28.js` uses compatible source/output metadata for store-name substitution; fixed payment-channel wording is translated separately from the actual store name. Do not reintroduce an observer that rewrites identical values or repeatedly translates its own output.

User-origin cells, names, descriptions and other opaque renderings are marked `data-user-content`; editable fields and specific book/account selectors also have explicit exclusions. `sep07.js` marks read-only projections as opaque user content and changes them only when their underlying display value changes. Without this boundary, a read-only field mirror and a translation observer can repeatedly overwrite one another or translate a user's Chinese value. Preserve the marker when rebuilding these nodes.

An HTML option without an explicit `value` otherwise inherits its displayed text as the submitted value. Before translating such an option's label, the canonical original value is saved as its `value` attribute. This preserves fixed-cost categories, cash types and other saved enums across language changes. User-owned select choices retain original identifiers and text.

`translateBackendMessage` recognizes anchored, known server templates. Declared field/location/nested-error parameters receive system translations; usernames, notes, units, paths and arbitrary interpolated values remain opaque. The API's canonical storage keys and response data are unchanged. New API error templates require matching display catalog updates rather than a blanket Chinese-to-English replacement over any server string.

`translateAuditSummary(summary, item)` uses the supplied structured `before_payload`, `after_payload` and reason to produce English Added/Removed/Changed/Cleared framing and known field labels while preserving original values. It does not parse arbitrary user notes by semicolons. The display summary is bounded (up to 20 changes, with a depth guard); it is not a substitute for full before/after records. For old responses without structured payloads, recognized fixed templates can be localized, but ambiguous unescaped user text is preserved rather than guessed. Nothing in this presentation step rewrites audit history.

Regression entry points include `build/qa_english_ui.cjs`, `build/qa_inventory_english.cjs`, `build/test_i18n_backend.cjs`, `build/qa_enhanced_analytics.cjs` and the retained business/money tests. Verify English and Chinese round-trips, dynamic dialogs, error paths, unchanged option values, arbitrary user names matching catalog words, read-only mirrors and absence of observer loops.

## 7. Analytics interpretation and chart contracts

Analytics has operating, expense and customer perspectives with a selected year/month/metric and date/filter context. Existing source details connect aggregate figures to underlying records. Expense views distinguish monthly saved totals from itemized fixed payments. CSV exports must correspond to the displayed/filter scope; user values are exported unchanged and fixed headings follow interface language. Product changes are recorded in [CHANGELOG](../CHANGELOG.md).

Charts show every data point while choosing only as many axis labels as fit. The renderer measures text, abbreviates dates/months with period context, reserves edge/final labels, wraps category labels and recalculates on container resize. Missing observations are gaps, not fabricated zero-income days. A negative net amount must remain below zero with its correct sign. Pointer, touch, focus, arrow and Home/End inspection must expose full date/category and exact amounts. Data table totals and chart series must share the same calculation source; styling must not create a parallel financial engine.

Professional presentation here means explicit period/basis, coherent selection, comparable metric summaries, useful trend/category/source views, and readable tables/empty states. Do not add pseudo-AI forecasts, invented data, misleading performance labels or probability claims that are not backed by recorded values. A more polished visualization does not change the financial basis.


### Analytics workflow

The calculation-basis/comparison strip names the selected scope and prior-month relationship. Three observation cards summarize recorded-day coverage and the largest expense, plus a perspective-specific measure: profitable recorded days, saved-month-minus-itemized fixed-cost gap, or busiest customer day/customer coverage. The metric trend supports line/bar selection and displays exact mean/minimum/maximum with observation count. Details sort by column, show signed amounts and total all filtered rows across pages; CSV follows filter/sort. These are transparent observations, not new predictions or financial classifications.

The native Chinese More statistics view provides a selected-scope/source-count banner, wrapping filters, collapsible purchase/consumption/method sections and one or two chart columns according to available width. Mixed amount/count/rate selections have a notice. Export uses current filtered records even if the table is hidden; no-data export is disabled. Its financial and storage contracts remain unchanged.

## 8. Configuration and operational behavior

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

Templates are `.env.example` for Compose and `backend/.env.example` for native API execution. They have different purposes. Never copy private `runtime.env` into one of these example files. Compose uses PostgreSQL 16 and Nginx 1.28 image tags from its YAML, mounts distinct database/payment-secret/recovery volumes and binds the demonstration web port to loopback by default. Do not run `docker compose down -v` during an ordinary upgrade because volumes hold persistent data.

Backend startup creates missing tables, performs narrow entry-timing compatibility additions, purges expired audit, ensures initial admin and handles legacy/test memberships. It does not run an arbitrary migration, rescan/repair all old amounts, or start the retained old WeChat scheduler. The system has no payment initiation/refund/settlement gateway, bank feed, high-availability architecture or central monitoring service.

## 9. Development, tests and release builds

Run commands below from the repository root unless noted. Use Python 3.12, the dependency files and Acorn lockfile. A reused native runtime can contain different library patch versions from a new source environment; inspect the actual app instead of inferring its dependencies from local pip packages. Keep generated logs, screenshots, JSON reports, exports and QA binaries in ignored `work/` or `dist/`, or in external CI/release artifacts. They are outputs, not source inputs.

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

for test in qa_web_browser qa_english_ui qa_inventory_english \
  qa_enhanced_analytics qa_analytics_english_advanced; do
  PLAYWRIGHT_MODULE="$PWD/work/browser-qa-tools/node_modules/playwright" \
  QA_OUTPUT_DIR="$PWD/work/qa/$test" node "build/$test.cjs" || exit 1
done
```

`QA_OUTPUT_DIR` must be a writable absolute directory. Use a new directory per run when retaining evidence; the harnesses write their reports/screenshots there. `PLAYWRIGHT_MODULE` selects the installed Node module, `CHROME_EXECUTABLE` optionally selects a browser binary, and `RELEASE_SOURCE_ROOT` optionally selects another source tree. Without that override, scripts load this repository's `web/index.html` as a local file. HTTP traffic is blocked and synthetic records replace live accounts. Keep the default assertion mode; `QA_DIAGNOSTIC=1` is a diagnostic option, not a passing acceptance run.

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

## 10. Distribution assembly and operational recovery

`build/make_complete_package.py` is an optional distribution assembler, separate from the server tar builder. It operates on an explicit staging tree outside the source checkout. Assemble the desired source/documentation, verified server archive and optional native app there. The staging root must contain `VERSION` and a generated `RELEASE_INFO.json` with a `build_revision` field; record source commit and artifact hashes there as release provenance. These generated metadata files belong to the artifact, not to the repository root.

```bash
python -B build/make_complete_package.py \
  --root /absolute/path/to/staging/Release \
  --output "$PWD/dist/complete-release.zip"
python -B build/verify_package.py --root /absolute/path/to/extracted/Release
```

The ZIP output must be outside the staging root and must not exist. The assembler refreshes `PACKAGE_MANIFEST.json`, preserves UTF-8 filenames, Unix modes and internal symlinks, and writes an outer `.sha256`. Exclude `.git`, dependency/virtual-environment directories and caches from staging. Re-extract to a new location and verify the manifest, embedded server archive and native signature. Public software artifacts must not contain actual server identities, personal workstation paths, business records, runtime environment values or credentials. Keep operational backups in separate protected storage.

A recoverable operational backup needs the database dump, matching application/configuration versions, runtime secrets, relevant external files, service/Nginx layout and database/role assumptions. Merchant files may live outside PostgreSQL under `PAYMENT_SECRET_ROOT`. SSH private keys, database passwords, JWT signing secrets and merchant keys serve different purposes. First rehearse restoration in an isolated environment and verify schema, data and key workflows; an Excel exchange workbook is not a complete system backup.

Program rollback and database restoration are different operations. Do not automatically overwrite a newer database with a pre-upgrade snapshot. Retain a current backup while validating a deployment and review exact targets before any later backup cleanup. The shipped deployment script retains backups and does not perform database restoration. Pause business writes through before/after database verification; inspect concurrent writes and allowed audit retention before interpreting a changed digest as corruption.

## 11. Troubleshooting map

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

## 12. Public HTTP route inventory

The following table is derived from route decorators in the source. `record_key:path` can contain path-like characters and must be URL-encoded by clients. Some legacy aliases are intentionally retained. Read request/response models and the route's dependencies for exact body/authorization requirements; a route's presence is not permission to call it. `/openapi.json` on a running API is useful for that exact build, but may not match a stale local document.

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


## 13. Read-only artifact privacy audit

`build/audit_distribution_privacy.py` audits an extracted tree, ZIP, tar or macOS app without executing contained code. Supply actual private identifiers in a separate file **outside the distribution and repository** (JSON string array or one UTF-8 identifier per line). The implementation has no installation-specific identifier list and does not print secret excerpts. It checks UTF-8/UTF-16 bytes, complete private-key armor, archive entries and link boundaries, including decompressed PyInstaller CArchive/PYZ data within universal Mach-O slices. `build/test_distribution_privacy.py` provides synthetic scanner regressions.

Run from the repository root, using the built archive as input and an ignored report directory:

```bash
python -B build/audit_distribution_privacy.py \
  dist/restaurant-cloud-v1.0.2-deploy.tar.gz \
  --forbid-file /absolute/private/identifiers.txt \
  --report work/qa/privacy-report.json
```

Apply the same check to complete software ZIPs or extracted staging trees. Keep credentials, databases, real workbooks and operational backups outside public software artifacts. The scanner counts images but does not OCR or classify their contents. Workbook/database/configuration candidates require manual review; signatures cannot establish absence of every unknown secret. Use synthetic fixtures for reproducible tests and review screenshots/logs before sharing them. Store generated acceptance results with their release or CI run, rather than committing them as application source.
