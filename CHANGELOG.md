# Changelog

[中文版](CHANGELOG%20(%E4%B8%AD%E6%96%87).md)

## v1.0.1 — 2026 Nov 07

Change date: **2026 Nov 07 (Asia/Shanghai)**. Delivery: `Nov07.zip`; internal product version: `v1.0.1`; Git commit summary: `Nov07 V1.0.1`.

Relative to `old/v1.0.0` / commit `f7987c03e005d8e74251fd0df857ad04b1914581`, this version includes the original 23 audited fixes, the 2026 Nov 07 follow-up corrections, and report wrapping. Nov05 is the intermediate delivery source, not this final version. Original identifiers are retained: A001/W002–W009, B01–B05/B07 and D001–D008. B06 was an unconfirmed product-workflow difference and is not claimed as a fix.

The English and Chinese files describe the same changes, with matching entries, causes, impacts, implementation and verification scope. Paths are relative to the source root. Editable web business logic is under `build/web-exact-source/`, with generated counterparts in `web/`.

### A001 — Expense left behind after deleting the final detail

Code: `build/web-exact-source/pro.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** The old saveLedger joined the recomputed detail total and the hidden previous amount with ||. JavaScript treated a valid zero as false, restoring the old amount after the last detail was removed.
- **Impact:** An empty detail list could retain an expense and continue reducing the cash balance. The same path affected ingredients, seasonings and other expenses.
- **Implementation:** Track whether details actually changed. Changed details save their recomputed value, including explicit zero; unchanged legacy amount-only records retain their amount. No bulk historical cleanup is performed.
- **Verification scope:** Cover clearing details, explicit zero, unchanged amount-only records, and the two-step targeted correction that adds then removes a zero-valued explanation.

### W002 — Duplicate detail rows collapsed by the picker

Code: `build/web-exact-source/v8.js`; `build/web-exact-source/pro.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** The old picker keyed a Map by item name, giving rows with different units, lots or prices the same identity.
- **Impact:** Confirming the selection could lose rows or amounts and merge independent purchases.
- **Implementation:** Retain per-row identity and original fields; duplicate names remain independently selectable. Confirming the ledger food/spice pickers without edits preserves the original data instead of rebuilding it from display text.
- **Verification scope:** Cover duplicate names with different units/amounts, repeated rows and an unchanged confirmation control.

### W003 — Moving a detail also moved unselected namesakes

Code: `build/web-exact-source/pro.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** The old move operation filtered all details by selected names instead of the actual checked rows.
- **Impact:** Selecting one purchase could move other purchases with the same name, changing their category or amount distribution.
- **Implementation:** Move by checked row identity and leave unchecked namesakes in place. Blank lines and surrounding whitespace must not shift the selected identity.
- **Verification scope:** Use a selected row and an unselected namesake, with blank-line and whitespace cases.

### W004 — Legacy compound records overwritten as a whole

Code: `build/web-exact-source/app.js`; `build/web-exact-source/pro.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** A legacy payload may contain several business dates. Editing one day replaced the entire dishes collection, while an empty-day lookup could fall back to dishes from another date.
- **Impact:** Saving one day could erase other dates or display another day’s consumption, affecting inventory.
- **Implementation:** Replace only the target business date and retain other daily/dishes/fixed_expenses data. A day without dishes returns an empty list rather than borrowing another day.
- **Verification scope:** Cover compound multi-date records, a single-day edit, a day with no dishes and preservation of other dates.

### W005 — Asynchronous reads and writes crossing books

Code: `build/web-exact-source/app.js`; `build/web-exact-source/v28.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** Old async functions reread the mutable active book around awaits. Switching books during device registration, checksum calculation or a response could separate the request target from the payload’s origin; late settings responses could overwrite the new view.
- **Impact:** A user authorized for both books could write A’s content to B or contaminate B’s cache with A’s result. This was not a cross-membership authorization bypass.
- **Implementation:** Bind each request to its originating book, session and generation, including device registration. Apply the same context and request-order checks to settings and payment-related operations; late responses do not update the active view. Successful saves advance recordWriteRevision so an already-started main-data GET cannot roll the saved local cache back to stale content.
- **Verification scope:** Cover pauses at registration, checksum and response stages, A→B→A switching, and out-of-order settings reads/writes.

### W006 — Stale cash cache and late-response rollback

Code: `build/web-exact-source/app.js`; `build/web-exact-source/sep04.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** The cash page retained a closure cache that was not reliably cleared by a main refresh or book switch. Nov05’s main-refresh cash GET also lacked update-order protection shared with dedicated cash requests.
- **Impact:** The cash page could show an old value after the ledger changed. A dedicated request could show 200 and then an older main-refresh response roll the view back to 100. This is a cache/display defect, distinct from A001’s persisted wrong amount.
- **Implementation:** Clear cash caches when changing books and refresh cash with valid main-data updates. Apply cash revision/context protection across main refreshes, dedicated refreshes and saves so obsolete results cannot replace newer state.
- **Verification scope:** Cover same-book refresh, book switching, unchanged daily records, late requests and the deterministic case where an old main refresh arrives after a newer dedicated response.

### W007 — Charts combining incompatible units

Code: `build/web-exact-source/charts-oct30.js`; `build/web-exact-source/pro.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** Purchase/consumption charts added quantities across rows without fully separating item identity and unit before calculating unit prices.
- **Impact:** Jin, kilograms or other units could share a denominator and produce a meaningless average price.
- **Implementation:** Group by item name and unit, preserving the amount/quantity/unit relationship without inferring conversions.
- **Verification scope:** Verify unit separation and group amounts/quantities in all three chart panels.

### W008 — FIFO remainder recomputed from the original unit price

Code: `build/web-exact-source/inventory-workspace.js`; `web/test_v1_0_1_regressions.js`

- **Previous defect:** The batch drawer multiplied remaining quantity by the original unit price and rounded the result. Even an exact unit price cannot reconstruct the booked remainder after prior cent allocations.
- **Impact:** The displayed value could differ by a cent from the balance obtained by cumulative allocation of the original lot amount.
- **Implementation:** Display the booked remainder as batch.original_value - batch.consumed_value. Preserve cumulative allocation and cent conservation rather than reverse-calculating from the original unit price.
- **Verification scope:** Use fractional-unit-price/cent-remainder examples to compare the drawer with the engine, alongside the existing cross-client FIFO contract.

### W009 — Lossless purchase details and effective amounts

Code: `build/web-exact-source/pro.js`; `build/web-exact-source/app.js`; `backend/app/main.py`; `desktop/restaurant_cost_manager.py`

- **Previous defect:** The old text serializer did not escape note delimiters: a comma could be parsed as another purchase, and unpriced quantities/units could disappear. Nov05’s desktop detail page also summed only total instead of applying the quantity-times-price fallback.
- **Impact:** Editing, synchronization, statistics and another save could alter details or amounts. A row with quantity=2, price=3 and blank total became zero in some desktop save/move paths instead of six; unknown amounts could also enter a priced-average denominator.
- **Implementation:** Write structured JSON retaining name/quantity/unit/price/total/note and continue reading legacy text. An explicit total, including zero, takes precedence; otherwise known quantity and price yield an effective amount. Align web/API/desktop semantics. Desktop summaries, saves and moves reuse the effective-amount function while retaining the original blank total. Show readable summaries and keep unknown prices distinct from zero.
- **Verification scope:** Cover comma-containing notes, duplicates, legacy text, JSON round trips, unknown price, explicit zero, inferred six from blank total, note-only edits, real save payloads, Qt detail saves/moves and inheritance of server edit deadlines.

### B01 — Incomplete temporary date authorization

Code: `backend/app/main.py`; `backend/app/inventory_balance.py`; `backend/tests/test_v1_0_1_regressions.py`

- **Previous defect:** The old check let one authorized date in a compound payload stand for the entire record. Promoting a record in source order could also change effective data on other dates.
- **Impact:** An account authorized for one day could alter an unauthorized day’s ledger or dish consumption through a compound record.
- **Implementation:** Check each changed business date and compare effective daily/dish data before and after source-order promotion. Unchanged historical dates may remain, but ordering must not change their effective result without authorization.
- **Verification scope:** Cover mixed authorized/forbidden dates, unchanged historical dates, ordering-only changes and overlaps containing only dish dates.

### B02 — Bypassing detail deadlines through aggregate fields

Code: `backend/app/main.py`; `backend/tests/test_v1_0_1_regressions.py`

- **Previous defect:** Entry restrictions checked deadlines on details and channel fields without fully validating their associated expense/revenue totals. Converting text to JSON could also be mistaken for a new item. Nov05 additionally treated the first channel inputs on a legacy total-only income record as new input, potentially restarting its clock.
- **Impact:** A locked detail could still affect reports and cash through an arbitrary total change; a format conversion could incorrectly restart the editing window.
- **Implementation:** Validate expense totals against details and revenue against channel inputs while retaining valid legacy amount-only records. Match equivalent text/structured items to their original timing, preserving the 30-minute correction and 12-hour addition windows. An equal-value conversion from total-only income to channels inherits the original first-save time; an expired total cannot be changed through first-time channel input or by converting first and editing later.
- **Verification scope:** Cover expired aggregate tampering, valid legacy amounts, equivalent format conversion, inherited item timing and effective quantity/price-derived amounts; add expired total-only 100-to-999 changes, editing after equal conversion.

### B03 — Cash read permissions differed by endpoint

Code: `backend/app/main.py`; `desktop/restaurant_cost_manager.py`; `backend/tests/test_v1_0_1_regressions.py`

- **Previous defect:** The dedicated cash endpoint rejected unauthorized roles, but generic records/changes could still expose legacy cash aliases. Treating a filtered record as a cloud deletion could also make the desktop send a deletion back.
- **Impact:** A role could read restricted cash data through another route, and client filtering could damage synchronization state.
- **Implementation:** Apply the same cash-read policy to cash_position, cash_balance and base_balance. Remove unreadable desktop cache entries locally without inferring a cloud deletion.
- **Verification scope:** Cover dedicated/generic endpoints, all aliases, role differences and the desktop synchronization control after filtering.

### B04 — Cash aliases, tombstones and version conflicts

Code: `backend/app/main.py`; `backend/tests/test_v1_0_1_regressions.py`

- **Previous defect:** The old save renamed an active alias to cash_position, colliding with a deleted canonical row that still held the unique key. Nov05 reused the tombstone but GET only prioritized the canonical key while PUT also ordered by update time, selecting different aliases; migrated versions could collide with old aliases.
- **Impact:** This could raise a unique-key error, or return v5 from GET and reject an immediate nonconcurrent save against another alias at v9. Coincident version values could instead admit a stale request.
- **Implementation:** Share a deterministic read/write order: canonical key first, then updated_at/sequence/version descending and record_key/id ascending, selecting the first active item. Reuse the canonical identity, retire other aliases and retain audit history. Advance beyond every candidate version to prevent migration collisions.
- **Verification scope:** Cover a canonical tombstone plus two active aliases, timestamp ties, complete ties, canonical priority, successful immediate GET/PUT, and rejection of genuinely stale concurrent/migration-collision versions.

### B05 — Cash double-counted overlapping daily sources

Code: `backend/app/main.py`; `backend/app/inventory_balance.py`; `backend/tests/test_v1_0_1_regressions.py`

- **Previous defect:** Cash aggregation summed every daily row, whereas ledger/inventory logic selected the effective source for each date.
- **Impact:** Imports or legacy compound records with overlapping dates could make cash income, expenses and operating-day counts disagree with the ledger.
- **Implementation:** Use the same effective-source selection per date for cash and count effective business dates; retain the existing fixed-expense basis.
- **Verification scope:** Cover duplicate daily rows, overlaps introduced by ordinary Excel import and agreement with effective ledger/inventory results.

### B07 — Backup restore lost source precedence

Code: `backend/app/excel_io.py`; `backend/app/main.py`; `backend/app/inventory_balance.py`; `desktop/restaurant_cost_manager.py`

- **Previous defect:** Old internal backups stored payloads without the precedence that resolves overlaps. Restore insertion order, partial overlaps and dish-only dates could change the winner; the desktop could ignore sequence/version changes when payloads stayed equal.
- **Impact:** Restoring a backup could change money, dish consumption or inventory, and the desktop could retain stale ordering after the cloud was correct.
- **Implementation:** Include globally unique source_order in new backups and retain relative precedence during restore, including dish-only overlaps. Live desktop sync recognizes ordering-metadata changes and follows cloud order.
- **Verification scope:** Cover complete/partial overlaps, fresh and tombstoned restore targets, dish-only dates and equal-payload ordering changes. Order absent from an old backup cannot be reconstructed.

### D001 — New local edits incorrectly acknowledged during sync

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`; `build/test_v1_0_1_desktop_qt.py`

- **Previous defect:** While v2 was uploading, a local save could create v3. The old response handler reread the current file’s hash and acknowledged v3 even though it was never sent. A check/write race also existed before caching cloud data.
- **Impact:** The next cycle could see no change and omit v3, or a download could overwrite a new local edit.
- **Implementation:** Acknowledge only the transmitted snapshot’s hash/version. Recheck the local version under the same file lock used to apply cloud results; retain mismatching local edits for the next cycle.
- **Verification scope:** Use deterministic scheduling to insert local saves during upload/response and between pre-lock checks and writes, verifying that v3 remains pending.

### D002 — Annual mirrors changed the global cash balance

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`

- **Previous defect:** Cash calculations read operating data from the currently open annual Excel mirror although cash is a cross-year global record.
- **Impact:** Changing the viewed year could substantially change the same book’s cash balance by omitting transactions outside that mirror.
- **Implementation:** Calculate cash from effective records across all years in the internal workbook. Annual mirrors limit viewing/editing, not the global cash basis.
- **Verification scope:** Switch annual mirrors for the same internal book and verify unchanged cash results and effective selection of overlapping daily sources.

### D003 — Stale cash dialogs overwrote newer transactions

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`; `build/test_v1_0_1_desktop_qt.py`

- **Previous defect:** An old dialog retained the transactions array from load time and rewrote it wholesale. A modal window blocked UI refresh but not background synchronization.
- **Impact:** Cash transactions added by another device or sync could silently disappear.
- **Implementation:** Retain the original record hash loaded by the cash editor and compare it under the write lock. Reject stale submissions and request a refresh instead of guessing how to merge transaction intent.
- **Verification scope:** Use real cash methods and temporary Excel files to verify added transactions survive stale rejection and unchanged records remain editable; these method tests are not a full cash-dialog interaction acceptance.

### D004 — Fixed costs omitted from weekly/monthly/yearly reports

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`

- **Previous defect:** Weekly reporting counted fixed expenses only on days with operating records; month/year logic returned early when no meaningful daily records existed, overlooking independently configured fixed expenses.
- **Impact:** Fixed costs on closed days were omitted, and cost/loss could disappear for fixed-expense-only months or years.
- **Implementation:** Allocate weekly fixed costs over elapsed calendar days. Monthly reports retain the configured whole-month amount; annual reports sum elapsed months, including the current month’s whole fixed amount. Periods with fixed costs remain reportable even without meaningful daily records.
- **Verification scope:** Cover a week with only one operating day but daily fixed costs, plus fixed-expense-only months and years.

### D005 — Legacy total revenue replaced by empty channels

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`

- **Previous defect:** The legacy compatibility path always recomputed revenue from channels, without distinguishing absent inputs from explicit zero.
- **Impact:** A valid historical total-only record could change from 1000 to zero in cash calculations. Normal overwrite-save already supported total revenue; an unreachable legacy add branch is excluded from this finding.
- **Implementation:** Sum channels only when channel values were actually entered; otherwise retain the valid total-revenue field. Explicit zero remains an entered value and must not fall back to an old total.
- **Verification scope:** Cover total-only revenue, entered channels, explicit zero and the normal overwrite-save path.

### D006 — Silent truncation of oversized Excel JSON

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`

- **Previous defect:** The internal workbook stored a business payload in one cell. The writer truncated it at 32,767 characters while the old workflow still reported success.
- **Impact:** The next read could fail JSON parsing or integrity validation, making the record/workbook unusable.
- **Implementation:** Check the character limit before writing, write a temporary workbook, reread and validate business JSON/integrity, then atomically replace the original. Failure preserves the original file; storage is not made unlimited.
- **Verification scope:** Use an oversized synthetic record to verify explicit rejection and an unchanged original, plus normal Excel round trips.

### D007 — Cache recovery inferred deletion of other years

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`; `build/test_v1_0_1_desktop_qt.py`

- **Previous defect:** When the internal cache was missing but an annual mirror survived, startup rebuilt only that year while retaining a cross-year sync baseline and skipping full cloud initialization.
- **Impact:** Missing years could be interpreted as intentional local deletions and sent to the cloud.
- **Implementation:** Mark recovery, clear inapplicable baselines and obtain a complete cloud snapshot first. If the cloud is empty, retain the mirror and request reconciliation instead of inferring deletions from an incomplete copy.
- **Verification scope:** Dynamically cover missing internal files, surviving annual mirrors and cloud records from other years, verifying that recovery sends no historical deletions. The empty-cloud guard is checked by code inspection.

### D008 — Editor contents detached from the conflict baseline

Code: `desktop/restaurant_cost_manager.py`; `build/test_v1_0_1_desktop.py`; `build/test_v1_0_1_desktop_qt.py`

- **Previous defect:** Background refresh advanced the global save baseline before skipping UI refresh because the form had unsaved input or a modal dialog.
- **Impact:** The form could still show an old amount of 10 while its baseline described the cloud’s 20; editing only a note could overwrite 20 with 10 without a conflict.
- **Implementation:** Advance the editor baseline only with a version actually loaded into the form. Keeping old input also keeps its old baseline, allowing the save-time hash check to reject stale overwrites.
- **Verification scope:** Run the full load→background update→note-only edit→save chain with consistent old/new purchase details, plus dirty-form/modal and normal-refresh controls.

### UI001 — Forecast text clipped in full operating reports

Code: `web/sep07.css`; `web/reporting-oct30.css`

- **Previous defect:** white-space:nowrap on forecast-title/forecast-formula forced one line, and the amount had min-width:max-content. Later styles made the forecast row a block without removing the inner no-wrap rules.
- **Impact:** In the monthly forecast within the daily/weekly/monthly/yearly four-card layout, long Chinese explanations and English Revenue-related labels overflowed and were clipped, especially at narrow widths.
- **Implementation:** Within detailed-report/forecast rows, remove no-wrap and min-content restrictions, allow labels/formulas/amounts to wrap naturally and allow columns to shrink with min-width:0. Preserve text and calculation logic.
- **Verification scope:** Use actual CSS and forecast-row structure in desktop four-card and narrow Chinese/English fixtures; check text bounds and visually inspect browser screenshots.

### BUILD001 — Consistent versioning and reproducible delivery

Code: `VERSION`; `backend/app/main.py`; `desktop/restaurant_cost_manager.py`; `web/index.html`; `build/`; `deploy/`; `docs/`

- **Previous defect:** Earlier active identities were Oct30LingChen or Nov05. The server packager’s allowed characters excluded dots and rejected v1.0.1; old app labels also did not follow macOS numeric version formatting.
- **Impact:** Renaming a ZIP alone would leave old page-cache/API/desktop identities, dotted-version packaging would fail, and app metadata would carry a nonnumeric version.
- **Implementation:** Use v1.0.1 for product identity, API, desktop, web data-build/footer/cache queries, generated headers, deployment expectations, test entry points and documentation. Allow dots in server versions while rejecting path separators. The app’s full product label is v1.0.1; Apple numeric fields use the corresponding 1.0.1 with a separate full-label field. Rebuild the universal app, server archive and Nov07.zip. Historical audit records/module names retain their historical meaning.
- **Verification scope:** Check active identities, generated JS/source equality, server manifests, both architectures’ main bytecode/signature/runtime, ZIP contents/modes/symlinks and extraction; keep issue identifiers and verification scope aligned between both changelogs.

### Validation for this version

The full backend suite passed 148 tests and 15 subtests (four existing warnings). Web checks passed 25 regression groups, 232 exact-money checks and three existing scripts. Cross-client FIFO passed 77 fixtures and 1,020 checks. Desktop checks passed 12 method regressions and 10 Qt interaction tests. The packaged app ran on arm64 and x86_64 through Rosetta; 12 interface modules were constructed/switched and the desktop suites passed in each runtime. Browser layout checks passed all 20 combinations of Chinese/English, 320/375/768/1024/1440px and normal/enlarged text. All 13 generated business scripts rebuilt byte-for-byte.

### Data, upgrade and validation boundaries

Fixing the program does not correct existing real ledger entries. Empty details with a nonzero amount may be valid legacy data and must not be cleared in bulk; confirmed historical remnants require the targeted procedure in the package. Original workbooks and production services have not been modified/deployed. Upgrade server, browser and desktop together to prevent old clients from damaging structured details. Missing source order in old backups cannot be recovered automatically; take new backups after upgrading.

Preserve exact-money rounding, cumulative FIFO allocation and existing business categories. Tests use synthetic data; backend checks primarily use isolated SQLite and do not replace real PostgreSQL concurrency, merchant-network or long-running multi-device acceptance. The desktop app requires macOS 15+, uses ad-hoc signing without Apple notarization, and Intel execution is checked through Rosetta. Numeric app metadata follows [Apple’s version-field format](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleshortversionstring) and corresponds to product label v1.0.1.

`main` holds the updated source; `old/v1.0.0` retains the pre-fix baseline. GitHub contains source, tests, example configuration, build/deployment tools and documentation. The complete app, packaged artifacts, historical audit and local verification evidence belong to the separate ZIP; real workbooks, runtime credentials and temporary files are not uploaded. No additional GitHub Release is created for this update.

## v1.0.0 — 2026 Nov 05

Preserved the Oct30LingChen pre-fix source at commit `f7987c03e005d8e74251fd0df857ad04b1914581`, corresponding to branch `old/v1.0.0` and the existing v1.0.0 tag/Release. This version retains the behaviors described above; saving the baseline was not a repair.
