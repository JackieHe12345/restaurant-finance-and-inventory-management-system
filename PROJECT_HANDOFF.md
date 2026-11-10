# Project handoff

Date: 2026 Nov 10  
Distributions: `For自己记账系统Nov10V1.0.2.zip` / `无隐私记账系统Nov10V1.0.2.zip`, each containing `Nov10/`  
Application version: `v1.0.2`  
Final build revision: `20261110-analytics-english-final`  
中文：[项目交接说明.md](项目交接说明.md)

## 1. What is being delivered

This is the complete delivery of a restaurant bookkeeping, expense, cash-balance and inventory system: browser application, FastAPI backend, macOS app, full source, tests, deployment tools, changelogs and build evidence. Independent datasets represent separate books. A book can record A/B store cash, WeChat, Alipay and takeaway revenue separately.

This release continues from V1.0.1 baseline `9ab90f8c546c33ebe5443fe57dbcc775148474e7`, preserved on `old/V1.0.1`; `main` contains the current V1.0.2 source. **The repository root corresponds to `Nov10/source/` in the ZIP**, with public handoffs and sanitized acceptance evidence added. The packaged app, server archive, complete-package manifest and private operations material belong only to their distributions, not Git. See `SOURCE_COMMIT.txt`, `RELEASE_INFO.json` and [release status](docs/RELEASE_STATUS_v1.0.2.md).

The two ZIPs have the same application version and shared software source, but different privacy boundaries. `无隐私记账系统Nov10V1.0.2.zip` excludes real server identities, database dumps, production workbooks, passwords, private keys and runtime environment values. `For自己记账系统Nov10V1.0.2.zip` additionally contains the explicitly requested `私人运维资料/` folder with the supplied SSH key, original server connection details and an accounting-system configuration/database snapshot. Read that folder's own inventory for exactly what was collected and when. Do not copy that folder into the clean package, a public repository, the web root or a server release tar. Synthetic fixtures and historical review evidence must not be imported as a real ledger. An internal Excel export is not a full database backup.

## 2. Accepted final product requirements

The five homepage cards appear in this order, left to right on a wide desktop and in the same sequence when wrapped:

1. `日均收入` — Average daily revenue
2. `日均毛利润 (毛利率)` — Average daily gross profit (gross margin)
3. `预计月底盈亏 (根据 上个月总成本 和 这个月日均收入 计算)` — Estimated month-end profit/loss
4. `日均净利润 (净利率)` — Average daily net profit (net margin)
5. `净利润 (净利率)` — Net profit (net margin)

All five cards use the same neutral background and border treatment, including Net profit. Positive/negative amount colors retain their meaning. The third card's parenthetical explanation starts on a new line. Preserve its words, parentheses and spaces. Gross profit and both net profit amounts display their corresponding margins in parentheses. Each of the five cards includes a higher/lower percentage comparison with the corresponding previous-month metric, or an unchanged/unavailable explanation.

Starting on the first day of the following month, a completed month's estimated month-end profit/loss amount becomes its actual monthly net profit. The rule applies to every month, including year boundaries, on the homepage and full monthly report. The current month continues to use the forecast. Shared chart axes must remain readable on phones, computers and resized containers, while preserving every point and full detail readouts.

The full report's exact Chinese wording is:

- `预计月底盈亏(根据 上月总成本 和 本月收入预测 计算)`
- `平本 需要 日均收入 增加`

Remove the standalone cash Balance correction section; retain Add an item → Force balance adjustment and protections on old system-locked entries.

The user expressly chose **not to change gross-profit definitions, Other expenses or consumable classification**. A prior discussion of packaging and phone charges is not authorization to reclassify them or change formulas merely to make gross profit minus fixed expenses equal net profit.

Both changelogs describe the final delivered behavior once, rather than narrating intermediate same-day designs. Preserve v1.0.1 and older history. Keep the application version at v1.0.2 and use the two requested ZIP names. The fixed browser interface is fully localized in English mode; user-authored product, dish, store, book, income-item names and notes are preserved. The existing native desktop interface remains Chinese; this release does not add a native English switch.


### Final analytics workflow

The calculation-basis/comparison strip names the selected scope and prior-month relationship. Three observation cards summarize recorded-day coverage and the largest expense, plus a perspective-specific measure: profitable recorded days, saved-month-minus-itemized fixed-cost gap, or busiest customer day/customer coverage. The metric trend supports line/bar selection and displays exact mean/minimum/maximum with observation count. Details sort by column, show signed amounts and total all filtered rows across pages; CSV follows filter/sort. These are transparent observations, not new predictions or financial classifications.

The native Chinese More statistics view provides a selected-scope/source-count banner, wrapping filters, collapsible purchase/consumption/method sections and one or two chart columns according to available width. Mixed amount/count/rate selections have a notice. Export uses current filtered records even if the table is hidden; no-data export is disabled. Its financial and storage contracts remain unchanged.

## 3. Financial contracts

These are the application's established bookkeeping rules, not a claim that the management view is a complete statutory income statement. Calculate with Decimal/Exact and round at the specified storage/display boundary.

| Metric | Contract |
| --- | --- |
| Revenue | Normalize existing channel fields and legacy total-only fields such as `收益` and `总金额`. Meaningful current channel entries take precedence over stale derived totals; never count both. |
| Daily gross profit | Revenue minus food, seasoning and transaction fees. |
| Daily variable expense | Food + seasoning + daily utilities + Other + fees. |
| Monthly fixed expenditure | Labour + rent/property charges + water paid + electricity paid + gas paid + other fixed costs. |
| Monthly total cost | Sum of daily variable expense plus the full saved monthly fixed expenditure. |
| Actual monthly net profit | Monthly revenue minus monthly total cost; includes recorded activity today and excludes future dates. |
| Average daily revenue/gross | Current-month records through yesterday divided by elapsed calendar days; completed months use the full calendar month. Missing observations or zero elapsed days do not invent an average. |
| Average daily net profit | Actual monthly net profit divided by elapsed calendar days, or all calendar days for a completed month. The numerator includes today's activity and the full monthly fixed expenditure. It is unavailable on day one when elapsed days are zero. |
| Both net margins | The same actual monthly net profit divided by the same month's actual revenue, including today. Missing or zero revenue makes the margin unavailable. Do not use a different ratio of daily net to revenue through yesterday. |
| Current-month forecast | Average daily revenue through yesterday × days in the selected month − previous-month total cost. Missing previous-month cost is not replaced with current cost. |
| Forecast amount for a closed month | Actual net profit for that month. Switching display does not write or freeze a result in the ledger. |
| Monthly comparison | Difference divided by the absolute previous-month value × 100%; the sign of the difference controls higher/lower wording. Distinguish zero, missing and valid negative values. |

The local client calendar determines whether a month is complete, independently of the selected day. Browser and native clients independently check the date about every five seconds even when cloud or workbook content is unchanged. The browser checks when visible again. Native refresh is deferred during modal dialogs and retried after read failures. The selected period is not changed. Date-boundary tests should inject the clock. Authorized historical corrections recalculate closed-month values; there is no immutable accounting close in this change.

| Client's current date | Selected month | Forecast-card amount |
| --- | --- | --- |
| 2026-10-31 | 2026-10 | Current-month projection. |
| 2026-11-01 | 2026-10 | October actual net profit; September costs are no longer required. |
| 2026-11-01 | 2026-11 | Forecast unavailable until a day has elapsed; actual net profit can exist separately. |
| 2027-01-01 | 2026-12 | December actual net profit. |
| 2026-11-10 | 2026-12 | Future month: no actual profit or forecast. |

The daily detailed card can use dish cost when present. Monthly and average daily gross profit continue to sum the daily bookkeeping gross-profit calculation. This distinction is retained. Actual/expected utility fields can affect expense detail presentation; monthly actual net and fixed expenditure use paid amounts. Monthly saved fixed totals and dated fixed-expense entries are reconciliation views, not amounts to add twice.

Purchase/expense accounting and FIFO consumption accounting remain separate. The inventory engine tracks batches and units, but monthly profit has not been silently converted to consumption-based cost of goods sold. Under the retained formulas, gross profit minus fixed expenditure still requires deduction of daily utilities and Other expenses to equal net profit.

## 4. Architecture and edit locations

Paths below are relative to the repository root.

| Location | Responsibility |
| --- | --- |
| `build/web-exact-source/app.js` | Record normalization, day/month calculations, month forecast and full reports. |
| `build/web-exact-source/dashboard-oct30.js` | Five homepage metrics, comparisons and dashboard chart entry points. |
| `build/web-exact-source/charts-oct30.js` | Shared SVG renderer, axis layout, pointer/keyboard inspection and resize handling. |
| `build/web-exact-source/analytics-oct30.js`, `pro.js` | More statistics, expense bases, filters, procurement/consumption charts and editors. |
| `build/web-exact-source/sep04.js`, `web/index.html` | Cash balance interface and entry points. |
| `web/` | HTML, CSS, Decimal runtime and generated JavaScript actually served by Nginx. |
| `desktop/restaurant_cost_manager.py` | PySide6 client, Excel/cloud synchronization, Decimal calculations, monthly overview and native widgets. |
| `backend/app/main.py`, `models.py` | FastAPI routes, authorization, versioned writes, models and compatibility initialization. |
| `backend/app/excel_io.py`, `money.py` | Workbook boundaries and precise monetary rules. |
| `backend/app/inventory_balance.py`, `inventory_validation.py` | Server quantity replay and stock validation, not a third FIFO cost engine. |
| `build/`, `backend/tests/`, `web/test_*.js` | Builds and regression checks. |
| `deploy/`, `docs/DEPLOYMENT*.md` | Native upgrades, independent Compose installation, file and database-summary verification. |

Edit browser business logic in `build/web-exact-source/` and run `node build/compile_exact_web.cjs`. The compiler uses Acorn to transform arithmetic into BigInt-backed Exact operations. Editing only generated files is lost on rebuild; bypassing the compiler can reintroduce floating-point money errors. HTML, CSS and `web/money.js` are maintained directly. The compiler's file list identifies generated files.

The macOS app must contain newly compiled main Python bytecode and a renewed local signature. Replacing a nearby source file or version string is insufficient. The rebuild tool reuses a valid app's universal runtime, then verifies main bytecode against the delivered source.

## 5. Data and runtime boundaries

Production uses PostgreSQL with SQLAlchemy/FastAPI. Nginx serves static browser assets and proxies the unchanged `/api/` path to the API. The desktop supports both local workbooks and cloud synchronization.

A business record is uniquely identified by `dataset_id + record_type + record_key`, with payload, checksum, version, sequence and deletion state. Writes require expected-version checks. Late reads must not overwrite a newer local edit or completed write. Dataset switching must preserve request-start identity and generation checks. These v1.0.1 protections remain required.

Internal Excel commonly contains `__day_records`, `__month_records`, `__global_records`, `__meta` and `__audit_records`, with structured `payload_json`. Day payloads commonly contain `daily`, `dishes` and `fixed_expenses`; monthly payloads contain `monthly_fixed`. Legacy payloads can contain multiple dates, aliases or total-only rows. Use existing import/normalization functions; replacing a whole payload with one edited day can destroy other data.

Known monetary fields generally serialize as decimal strings. Money has two decimals, unit prices up to six, using ROUND_HALF_UP. Preserve deliberate zero versus unknown price. Do not reinterpret dates, IDs, people counts or extension fields as amounts. Different units are not silently combined or converted. FIFO remaining value is original batch value minus allocated value, not rounded remaining quantity times unit price.

Force balance adjustment accepts the target balance and is neither operating revenue nor expense. Old `system_locked` entries remain protected after the UI is removed. An upgrade does not clean financial data, reclassify consumables or fix historical residual amounts automatically.

There is no general schema migration framework. Existing startup compatibility additions do not make arbitrary schema changes safe; structural changes need a separate compatibility and migration design.

## 6. Builds and verification

See `版本说明/06_Nov10V1.0.2更新说明.md` for current commands and app rebuild parameters, and `README.md` for dependencies. Use Python 3.12 and Node.js. Dependency inputs are `build/test-requirements.txt`, `desktop/requirements.txt` and `build/js-transform/package-lock.json`.

Extract into a clean working directory and verify before installing dependencies. Do not run source tests against production or load `.env.runtime`. Do not point tests at a real internal workbook. Full desktop-module and packaged-app QA need an isolated directory, disabled network and test configuration; `build/qa_packaged_desktop.py` provides this approach and must remain separate from the production app.

Minimum acceptance coverage:

- Five-card ordering, all requested spaces/parentheses, forecast newline, five comparisons and three margin displays.
- Closed-month actuals, current forecast, day-one behavior, December/January rollover, future dates, missing data and explicitly saved zero costs.
- Today's revenue/expenses included in actual net but excluded from average revenue/gross; both net margins consistent with the full monthly report.
- Chinese/English chart geometry on narrow and wide screens, long dates/categories, the final two ticks and resized containers; full pointer and keyboard readouts.
- Old cash-lock protection and the retained add-item force adjustment.
- Exact-money and existing browser/API/desktop regressions; final app bytecode matching source and actual execution of claimed architectures.
- Re-extracted archive integrity, Unix symlinks, app signature and server MANIFEST matching the final source.

The final evidence under `docs/acceptance/Nov10Final/` is authoritative. Do not infer current success from Nov07 counts. Historical test filenames can remain when they test retained behavior.

The server builder accepts only Git-tracked runtime inputs. The distributed source intentionally omits `.git` and installed dependencies. In a separate extracted source copy, initialize Git and add only release-relevant source inputs. Do not track virtual environments, node_modules, ledgers or credentials. The tar builder requires a new output path and refuses overwrites.

Browser geometry acceptance is implemented in `build/qa_web_browser.cjs`. It runs the shipped page offline with synthetic fixtures, blocks HTTP, and requires Playwright plus Chromium. `QA_OUTPUT_DIR` is required; `PLAYWRIGHT_MODULE` and `CHROME_EXECUTABLE` can select installed tools, while `RELEASE_SOURCE_ROOT` optionally selects the source directory. This is distinct from the browser calculation and chart unit checks.

## 7. Deployment boundary and same-version upgrades

Packaging and deployment are verified separately. The actual publication/deployment state and checks are recorded in [release status](docs/RELEASE_STATUS_v1.0.2.md). A v1.0.2 health response alone therefore cannot identify this package's English and analytics changes. Use the current build revision plus the final server tar and per-file hashes. Authoritative actual server identifiers, the latest known backup inventory and snapshot date belong only in `私人运维资料/` in the private ZIP. This clean technical guide deliberately does not contain them.

The native Ubuntu deployment tools assume this installation layout:

| Component | Expected path or service |
| --- | --- |
| Public endpoint | A separately configured domain or server address; obtain it from the private handoff. |
| API | `/opt/restaurant-cloud/api` |
| Python environment | `/opt/restaurant-cloud/.venv` |
| Runtime configuration | `/opt/restaurant-cloud/.env.runtime` |
| Static web directory | `/var/www/restaurant-web` |
| Service | `restaurant-cloud.service` |
| Nginx fragment | `/etc/nginx/conf.d/restaurant-cloud-upload.conf` |
| Protected rollback/evidence root | `/opt/restaurant-cloud/backups` |

Before another deployment, verify the target host, active service, available disk space, configuration, requirements and current files. Take a fresh database/configuration backup and verify the dump can be read. Do not use a historical path in an old document as proof that a backup still exists. Compare the final tar hash before extraction, then follow `docs/DEPLOYMENT.md` and the native-layout script. Its exclusive lock, preflight checks, staged copies, brief service stop, read-only database baseline, atomic API/web switches, health checks and file verification are part of the deployment contract.

The upgrade script preserves the existing virtual environment and runtime configuration. A requirements or Nginx mismatch stops the routine upgrade rather than silently replacing the environment. It retains the old API/static directories; failure after switching triggers program rollback. It does not restore a database automatically. A database restore is a separate operation that must account for writes after the backup. Database comparison can legitimately change if another user writes during post-start verification; inspect evidence before treating that as corruption or deleting any backups.

The last deployment performed before this packaging task removed historical backup directories at the user's request and retained that deployment's fresh rollback set. Future projects must inspect the private inventory/server again; do not assume old historical backup names in archived review evidence are available. Neither building these ZIPs nor running a package verifier deletes server backups or modifies live data.

For a new independent installation, use Compose or the new-server sections of the guide and generate independent secrets. The existing native-layout upgrade script is not a universal installer. Production database state, user memberships and merchant credentials are separate from software source.

## 8. Evidence and release maintenance

This repository maintains root changelogs; when producing complete ZIPs, their root and ZIP `source/` copies must match. The v1.0.2 entries describe the final state; older history retains its wording and dates. Current evidence is under `docs/acceptance/Nov10Final/`; older evidence and the pre-fix audit are available only under `私人运维资料/历史开发证据/` in the owner ZIP. The clean ZIP retains historical changelog text but not those logs/screenshots or release notes 01–05.

`PACKAGE_MANIFEST.json` checks file contents, modes and symlinks across the full distribution. The server tar's `MANIFEST.json` checks deployable files. An outer `.sha256` checks archive bytes. From the extracted `Nov10/` directory:

```bash
python3 source/build/verify_package.py --root .
shasum -a 256 -c restaurant-cost-server-v1.0.2.tar.gz.sha256
```

Do not change delivered files after generating the manifest without regenerating it. Preserve app symlinks and executable modes, and encode Chinese ZIP entry names with UTF-8 flags.

After future changes, update both languages and relevant tests, compile browser assets, rebuild affected application/server deliverables and verify the actual extracted artifacts. Version strings, source trees, archives and the running server are separate objects; build revision, timestamp and hashes establish which changes they contain.


## 9. Building the complete ZIP

First compile browser assets, rebuild the server tar and macOS app, update release metadata/documentation and gather final evidence. Package a clean distribution copy; exclude the development Git repository, node_modules, Python caches and virtual environments without deleting the working development repository itself.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 source/build/make_complete_package.py \
  --root /absolute/path/to/Nov10 \
  --output /absolute/path/to/output/无隐私记账系统Nov10V1.0.2.zip
```

The output must be new and outside the distribution root. The builder refreshes PACKAGE_MANIFEST, preserves UTF-8 names, Unix modes and app symlinks, and writes a ZIP SHA256 file. It packages existing artifacts and does not replace compilation, testing or deployment. Re-extract the result to a new directory and verify the package manifest, app signature and server tar rather than checking only the uncompressed staging tree.

## 10. Complete engineering reference and reading order

The concise handoff above is backed by [the detailed engineering reference](docs/ENGINEERING_REFERENCE.md), which is part of the required handoff rather than an optional marketing description. It maps source loading and overrides, persistence tables, the HTTP route inventory, data flow, authorization and concurrency boundaries, translation and user-content rules, finance/FIFO invariants, deployment configuration, package privacy, acceptance coverage and troubleshooting. The same reference is available in Chinese at [工程技术详解](docs/ENGINEERING_REFERENCE.zh-CN.md).

Recommended sequence for another project:

1. Read `00_交接必读.md`, this file and `RELEASE_INFO.json` to identify the distribution flavor, exact revision and authoritative source.
2. Read the engineering reference and both contracts under `build/` before altering money, inventory, normalization, import or synchronization.
3. Verify the extracted package manifest and server tar, then install tools outside the distribution and run isolated tests. Use synthetic books, not a private database snapshot.
4. Find the last active implementation in the loaded browser scripts or native class definitions. The browser intentionally layers historical modules; a same-named function earlier in `app.js` can be superseded by a later-loaded module.
5. Read the final acceptance evidence for this revision. Historical evidence and prior success counts do not prove that a newly edited build passed.
6. Make one reviewed change, update matching Chinese/English UI and final-state changelogs, rebuild generated assets and affected binaries, rerun relevant checks, and create new manifests. Keep API version and build revision distinct.

## 11. Language and user-owned content contract

English mode applies to the browser application's fixed interface, including navigation, headings, form labels, placeholders, help text, buttons, dialog text, validation/status messages, chart labels, report labels and system enums. The native desktop remains Chinese because no native English mode existed in the delivered baseline. Package documentation is bilingual regardless of native interface language.

User-authored strings are data, not translation keys: preserve book/store/product/dish/custom income-item names, suppliers, people, notes, arbitrary user units and other entered values exactly. A Chinese shop name is expected to remain Chinese in an English interface. Default system category labels and role names need English display labels, but their storage values and legacy Chinese JSON/Excel keys must stay compatible. Localizing the UI must never rewrite a book or turn a product named “现金” into a different product.

Prefer translation at UI construction or rendering boundaries. Translate fixed portions of a combined label while separately rendering escaped user content; do not perform unrestricted search/replace over user fields, imported JSON, HTML values or audit payloads. Language changes must not submit editors, change selected dates/books, alter numeric values or restart permission clocks. Re-run language checks after asynchronously opening a dialog or changing a book; an English login screen alone is insufficient.

## 12. Package privacy and handoff responsibilities

| Distribution | Intended use | Included boundary |
| --- | --- | --- |
| `无隐私记账系统Nov10V1.0.2.zip` | Share with another development project or install a fresh independent instance. | Software, generic deployment examples, bilingual documentation, synthetic tests and sanitized verification evidence. No original public IP/hostname, personal local paths, production database or secret material. |
| `For自己记账系统Nov10V1.0.2.zip` | The owner's private operations and recovery handoff. | Same software plus `私人运维资料/` containing the specifically requested private artifacts. The private inventory states what was actually captured; possession of a ZIP does not establish a live connection or a successful restoration. |

Both server tarballs remain software-only. Private credentials/configuration/database files are stored alongside the software in the private ZIP, never under served `web/`, never compiled into the app and never inside the deployable runtime tar. The two outer ZIP hashes and manifests differ because their contents differ. The application version stays v1.0.2.

Before sharing a derivative clean package, inspect nested tar/ZIP contents, evidence/logs, app bundles and document links as well as file names. A private key scan alone will not catch a server IP, a username in an absolute build path, a database identifier or a screenshot containing a customer ledger. Generate each flavor from an explicit staging tree, verify after extraction, and record the privacy scan's scope and limitations. Do not label the private ZIP as redacted or safe for public distribution.


### Location of historical and private material

Only current synthetic/sanitized verification under `docs/acceptance/Nov10Final/` is common to both ZIPs. The clean ZIP deliberately omits the pre-fix audit, older Nov07/Nov10 logs/screenshots and historical release-note files 01–05 because they can contain original workstation, server or business information. The owner ZIP archives these under `私人运维资料/历史开发证据/`; that archive is historical context, not the authoritative current source or acceptance result. Historical CHANGELOG entries remain in both packages. Their statements about an older delivery's included files describe that delivery; the current package inventory takes precedence.

The owner folder additionally provides the supplied `Admin.pem`, `known_hosts`, `accounting-server-private.tar.gz` and private operations instructions/inventory. The server snapshot is a read-only capture of this accounting system's PostgreSQL data, runtime/service configuration and relevant payment-secret files, with exact scope and time recorded by its inventory. It is not an archive of unrelated services. Consult the private operations instructions before using credentials or planning a restore. No real host identity or credential value is needed in the common technical guides.
