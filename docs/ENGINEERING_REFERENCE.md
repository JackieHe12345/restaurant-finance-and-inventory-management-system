# Engineering reference — v1.0.2

Date: **2026 Nov 10**. Build revision: **20261110-analytics-english-final**. This file describes the source at the repository root (equivalent to `Nov10/source/` in the ZIP). Actual deployment state is recorded in [release status](RELEASE_STATUS_v1.0.2.md). [中文版](ENGINEERING_REFERENCE.zh-CN.md) · [Root handoff](../PROJECT_HANDOFF.md).

## 1. Product and ownership boundaries

The system combines restaurant revenue recording, purchases, daily expenses, monthly fixed expenditure, cash balance, dish usage, inventory, multiple independent books, accounts/permissions, audit history and Excel exchange. A book can contain A/B store income channels. Store labels and business names are user data; books remain separate authorization and persistence domains.

There are three executable forms: a static browser client; a FastAPI service backed by PostgreSQL; and a PySide6 macOS desktop application that works with local Excel and cloud synchronization. The server tar contains API and web runtime files. The outer complete ZIP additionally contains native runtime, complete source, documentation and verification material. The clean and private ZIPs have the same software version; only the private ZIP adds `私人运维资料/`.

Do not confuse these objects:

| Object | Authority | Does not prove |
| --- | --- | --- |
| `VERSION` / API `v1.0.2` | Product compatibility/version label. | That two same-version builds have identical features or files. |
| HTML build revision / `RELEASE_INFO.json` | Identifies this same-day revision. | That the currently running server has received it. |
| Repository root (ZIP `source/`) | Editable source of this release. | That a historical Git commit contains all current edits. |
| Server `MANIFEST.json` | SHA-256 of the runtime archive's files. | Preservation of real ledger records during deployment. |
| `PACKAGE_MANIFEST.json` and outer `.sha256` | Full distribution files, modes/symlinks and ZIP bytes. | That a private snapshot can be restored without checking its dependencies. |
| Deployment before/after evidence | Particular server state and comparison at a recorded time. | Current availability of old backups or success of later edits. |

The interface is a management-bookkeeping view. Do not infer formal accounting classifications, a completed payment, or immutable month closing from a displayed profit figure. The user expressly retained existing gross-profit and Other-expense definitions.

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

Authoritative business JavaScript is under `build/web-exact-source/`. `node build/compile_exact_web.cjs` parses with Acorn and emits the corresponding `web/*.js`. Do not edit generated copies alone. HTML, CSS, `money.js`, `workbench.js`, the localization asset and licenses are direct static sources. Consult the compiler's own file list before classifying a new asset. Runtime browsers do not require Node, Acorn, a bundler or CDN.

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

The homepage's five cards are defined in the root handoff. The essential asymmetry is intentional: current-month average revenue/gross exclude today and divide by elapsed calendar days, whereas actual monthly net includes today's recorded activity and the full monthly fixed expenditure. Daily net is that actual monthly net divided by elapsed calendar days; both net margins use actual monthly revenue. Day one has no elapsed-day average. Completed months use their full calendar days and their forecast card becomes actual net on the next month's first day. Future months are unavailable. Local calendar watchers re-evaluate even when data content is unchanged; they do not write or freeze results.

| Financial concept | Required meaning |
| --- | --- |
| Gross profit | Revenue − food − seasoning − transaction fees. |
| Variable expense | Food + seasoning + daily utilities + Other + fees. |
| Monthly fixed expense | Saved labour + rent/property + paid water/electricity/gas + other fixed. |
| Monthly net | Revenue − variable expense − full saved monthly fixed expense. |
| Current forecast | Average revenue through yesterday × calendar days − previous month's total cost. |
| Change percentage | `(current − prior) / abs(prior) × 100`; zero/missing prior needs an explicit unavailable reason. |
| Cash force adjustment | Set target actual balance as of a date; not operating income or cost. |
| Expense basis comparison | Saved monthly fixed totals versus itemized dated fixed payments; do not add both. |

Inventory identity is category/name/unit. Different units are not silently converted. FIFO keeps original lot quantity/value/price and remaining quantity. Each issue cost is the change in rounded cumulative allocation: `round(original lot amount × cumulative issued / original quantity, 2) − already allocated`. A fully consumed lot allocates all remaining cents. Remaining value equals original booked value minus allocated value, not rounded remaining quantity × displayed price. Unknown-priced quantities remain explicit.

Purchasing expense and FIFO consumption cost answer different questions. Monthly operating profit still uses the established purchase/expense basis. No packaging, consumable or phone-cost reclassification was authorized for this revision. Gross minus fixed can therefore still differ from net by daily utilities and Other expenses.

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

Analytics has operating, expense and customer perspectives with a selected year/month/metric and date/filter context. Existing source details connect aggregate figures to underlying records. Expense views distinguish monthly saved totals from itemized fixed payments. CSV exports must correspond to the displayed/filter scope; user values are exported unchanged and fixed headings follow interface language. The precise final presentation is listed in the current Nov10 changelog and release notes.

Charts show every data point while choosing only as many axis labels as fit. The renderer measures text, abbreviates dates/months with period context, reserves edge/final labels, wraps category labels and recalculates on container resize. Missing observations are gaps, not fabricated zero-income days. A negative net amount must remain below zero with its correct sign. Pointer, touch, focus, arrow and Home/End inspection must expose full date/category and exact amounts. Data table totals and chart series must share the same calculation source; styling must not create a parallel financial engine.

Professional presentation here means explicit period/basis, coherent selection, comparable metric summaries, useful trend/category/source views, and readable tables/empty states. Do not add pseudo-AI forecasts, invented data, misleading performance labels or probability claims that are not backed by recorded values. A more polished visualization does not change the financial basis.


### Final analytics workflow

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

## 9. Build and acceptance procedure

Use the exact source and instructions in the root handoff/release notes. Keep tooling outside the distribution tree. A source environment uses Python 3.12, pinned API/desktop dependencies and locked Acorn npm installation; a reused packaged native runtime can contain different library patch versions, recorded by app verification. Do not claim new source dependency versions are necessarily the bundled runtime's versions.

Recommended order:

1. Verify source/package provenance and establish clean staging for both privacy flavors.
2. Install `build/test-requirements.txt`, required desktop packages and `npm ci --prefix build/js-transform` in isolated development environments.
3. Edit authored web business scripts and direct static files; compile with `node build/compile_exact_web.cjs`.
4. Run exact-money, FIFO, browser regression, current dashboard/chart/localization/analytics checks and necessary API/native tests.
5. Run real-browser layout/interaction checks at phone through desktop widths, Chinese and English, with synthetic data and HTTP blocked. Check UI text, preserved user content, chart bounds and responsive table behavior.
6. Rebuild native main bytecode from the final desktop source using `build/rebuild_macos_app.py`. Verify source/bytecode, executable permissions, universal architectures and signature. Run claimed architecture QA against the actual candidate app in an isolated harness, not only source imports.
7. Build the server tar using `build/make_release.py` from explicitly Git-tracked runtime inputs. Its output must be new. Record and verify its manifest/hash.
8. Finish current-revision test evidence and bilingual docs. Distinguish rerun results, inherited results and limitations. Do not copy old passed counts into a new acceptance declaration.
9. Build the clean outer ZIP and private outer ZIP from separate explicit staging directories. Private payload stays outside server tar and app. Generate manifests/ZIP hashes after all contents are final.
10. Re-extract both packages into new directories; verify file contents, modes, symlinks, native signature and server manifest. Repeat privacy checks on extracted/nested artifacts.

The existing QA entry points include `web/test_v1_0_1_regressions.js`, `web/test_v1_0_2_dashboard.js`, `web/test_v1_0_2_charts.js`, `build/test_exact_web.cjs`, `build/test_fifo_contract.py`, `build/test_v1_0_1_desktop*.py`, `build/test_v1_0_2_desktop*.py`, `build/qa_web_browser.cjs`, `build/qa_packaged_desktop.py`, `build/test_deployment_cache_revision.py`, and `backend/tests/`. Any new English/analytics regression paths are recorded in the current evidence and changelog.

Acceptance must cover preservation of source/user data and permissions, not merely screenshots. Do not run tests against the private dump or real server. SQLite fixture tests do not prove PostgreSQL concurrency under production load; x86_64 execution under Rosetta does not mean separate Intel hardware was tested; a readable pg_dump does not mean a full restore rehearsal passed.

## 10. Packaging, private snapshot and recovery

The clean ZIP excludes original server IP/hostname, personal workstation paths/chat links, live account/book details, database dumps, runtime environment values, credentials, private keys and user content. Synthetic fixtures may intentionally contain Chinese test names and fake values. The private ZIP adds the owner-authorized `私人运维资料/` inventory, supplied SSH credential, server connection information and accounting-system snapshot. Exact collection scope and timestamp come from that inventory, not from this generic guide.

Private artifacts are never web-served and never compiled into either executable. Keep the software tar identical in intent across flavors. SSH private keys, database passwords, JWT secrets and merchant signing keys are different credentials; do not assume one substitutes for another. Merchant files may live outside PostgreSQL under `PAYMENT_SECRET_ROOT` and must be considered separately during an authorized full restore. Do not copy unrelated services' files just because they share a machine.

A restore handoff needs the database dump, matching app/config versions, runtime secrets, relevant external files, service/nginx layout and database/role assumptions. First restore into an isolated environment, inspect schema/counts/key functions, and verify credentials/configuration separately. Program rollback and database restore are different operations. Never automatically overwrite a newer production database with a pre-upgrade snapshot.

Keep a new current backup while validating a deployment; any later cleanup must target a reviewed list of old app backup directories. The deployment script itself does not delete backups. Historical paths are evidence at a time, not deletion instructions. Attached documents and old audit notes describe context; they do not authorize new production edits.

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

The following table is generated from route decorators in the delivered source. `record_key:path` can contain path-like characters and must be URL-encoded by clients. Some legacy aliases are intentionally retained. Read request/response models and the route's dependencies for exact body/authorization requirements; a route's presence is not permission to call it. `/openapi.json` on a running API is useful for that exact build, but may not match a stale local document.

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


## 13. Location of historical and private material

Only current synthetic/sanitized verification under `docs/acceptance/Nov10Final/` is common to both ZIPs. The clean ZIP deliberately omits the pre-fix audit, older Nov07/Nov10 logs/screenshots and historical release-note files 01–05 because they can contain original workstation, server or business information. The owner ZIP archives these under `私人运维资料/历史开发证据/`; that archive is historical context, not the authoritative current source or acceptance result. Historical CHANGELOG entries remain in both packages. Their statements about an older delivery's included files describe that delivery; the current package inventory takes precedence.

The owner folder additionally provides the supplied `Admin.pem`, `known_hosts`, `accounting-server-private.tar.gz` and private operations instructions/inventory. The server snapshot is a read-only capture of this accounting system's PostgreSQL data, runtime/service configuration and relevant payment-secret files, with exact scope and time recorded by its inventory. It is not an archive of unrelated services. Consult the private operations instructions before using credentials or planning a restore. No real host identity or credential value is needed in the common technical guides.


## 14. Read-only distribution privacy audit

`build/audit_distribution_privacy.py` audits an extracted tree, ZIP, tar or macOS app without executing contained code. Supply the actual private identifiers in a separate file **outside the distribution** (JSON string array or one UTF-8 identifier per line). The implementation has no installation-specific identifier list and does not print secret excerpts. It checks UTF-8/UTF-16 bytes, complete private-key armor, archive entries and link boundaries, including decompressed PyInstaller CArchive/PYZ data within universal Mach-O slices. `build/test_distribution_privacy.py` provides synthetic scanner regressions.

From the extracted `Nov10/` root, for a clean package:

```bash
python3 build/audit_distribution_privacy.py \
  /absolute/path/to/无隐私记账系统Nov10V1.0.2.zip \
  --forbid-file /absolute/private/identifiers.txt \
  --report /absolute/path/to/clean-privacy-report.json
```

The private owner ZIP intentionally contains credentials and a database snapshot, so do not expect a clean-package signature policy to pass on it. Instead verify its explicit private-folder inventory and ensure those artifacts are absent from the common app/server tar and clean ZIP. The scanner counts images; it does not OCR or classify their contents. Workbook/database/configuration candidates still require review, and signatures cannot establish absence of every unknown secret. That is why old screenshots/logs/audits and release notes 01–05 are kept only in the owner's historical archive, while common evidence uses current synthetic fixtures.
