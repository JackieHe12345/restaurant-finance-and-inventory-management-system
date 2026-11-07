# Changelog

[中文](CHANGELOG%20%28%E4%B8%AD%E6%96%87%29.md)

## v1.0.1 — 2026 Nov 07

This release fixes errors in ledger details, cash balances, cloud synchronization and inventory reporting, and allows long text to wrap in the web financial reports. The main problems included expenses surviving deletion of their last detail, separate purchases being merged or moved together because they shared a name, newer data being replaced by older responses during book changes or synchronization, and inconsistent rules for reading, saving and version-checking legacy cash records.

The changes below are relative to `old/v1.0.0` at commit `f7987c03e005d8e74251fd0df857ad04b1914581`. Existing issue IDs are retained so that each change can be traced to its tests. Paths are relative to the repository root. Web business logic is maintained in `build/web-exact-source/` and compiled into the files served from `web/`.

### Web ledger and financial reports

#### A001 — Deleting the last detail left its expense on the ledger

Code: `build/web-exact-source/pro.js`, `web/test_v1_0_1_regressions.js`

Deleting the final expense detail in the main ledger, or changing its amount to zero, could leave the old expense total in the saved record. In `pro.js`, the changed-detail branches of `saveLedger()` used expressions such as `sumItems(food) || num($("ledgerFoodCost").value)`. When the new sum was zero, `||` selected the previous value from the hidden amount input. The ingredient, seasoning or other-expense detail could therefore be empty while its saved total remained nonzero and continued to reduce the cash balance.

Those branches now save the result of `sumItems(...)` directly, including zero. The existing `entryDetailUnchanged()` branch still preserves the stored total when the user has not changed the details. Older amount-only records can legitimately have no detail text; opening and saving one must not erase its amount. This change does not automatically rewrite historical records.

In `web/test_v1_0_1_regressions.js`, `zeroLedger()` tests clearing details, entering explicit zero amounts and leaving legacy amount-only records unchanged. Ingredient, seasoning and other-expense totals of 20, 5 and 15.80 respectively become zero in the first two cases and retain their original values in the third. `historicalOtherCorrection()` also exercises a specific stale record with empty other-expense details and a total of 15.80. Saving a zero-valued correction note, then deleting that note and saving again, produces zero in both requests. The assertions check that the day's revenue, other charges, notes and custom fields, as well as the other day's daily record and the existing dish and fixed-expense arrays, remain intact.

#### W002 — The item picker discarded separate purchases with the same name

Code: `build/web-exact-source/v8.js`, `build/web-exact-source/pro.js`, `web/test_v1_0_1_regressions.js`

A detail list can contain separate purchases with the same name, such as potatoes bought as 2 jin for 10 and as 1 box for 20. The old `openItemPicker()` in `v8.js` built `new Map(parseDetailItems(current).map(item => [item.name, item]))`, using the name as a unique key. The second potato purchase replaced the first before the picker was displayed. Confirming the selection could then write the shortened list back to the ledger or purchase editor, reducing both the purchase total and the quantities later derived from those details for inventory receipts.

`pickerRows()` in `pro.js` now retains each existing detail as its own selectable row, with its quantity, unit, unit price, total and note. A set of names is used only to omit redundant empty suggestions from the dictionary; it no longer combines purchase records. The main ledger's ingredient and seasoning pickers also remember their initial selection. Confirming without changes skips the callback that rewrites the details, preserving the original text and amount. This no-rewrite behavior is specific to those two main-ledger pickers.

`duplicatePicker()` runs the actual picker functions with the two potato purchases and a dictionary suggestion for greens. Both potato rows remain present. Adding greens as 1 jin for 5 and confirming returns three details totaling 35, with the original amounts of 10 and 20 retained separately. A second case opens a legacy main-ledger entry of 3 jin of potatoes for 1 and immediately confirms it. The test verifies that no callback runs, so merely opening the dialog does not rewrite the record using the displayed precision.

#### W003 — Moving selected details also moved unchecked namesakes

Code: `build/web-exact-source/pro.js`, `web/test_v1_0_1_regressions.js`

The ingredient and seasoning tables allow selected rows to be moved to the other category. The old `moveDetailRows()` collected the names of checked rows into `selectedNames`, then filtered the entire source list with `selectedNames.has(item.name)`. An unchecked purchase with the same name was moved too. This changed the allocation of expenses between categories and the category assigned to the purchases in inventory, even though the user had selected only one of them.

`detailRows(kind, selection)` now selects `selected` or `remaining` rows using each table row's own checkbox before reading its fields, trimming the name or discarding blank rows. `moveDetailRows()` appends the selected details to the destination, keeps unchecked details in the source and recalculates the two category totals. Neither the item name nor an index in a filtered array is used to infer the selection.

`selectedRows()` supplies a checked blank row, a checked potato row with spaces around its name (2 jin for 10), and an unchecked potato row (1 box for 20). The seasoning category initially contains scallions, 1 jin for 3. After the move, ingredients still contain the box of potatoes and a total of 20; seasonings contain the scallions and the selected potatoes, totaling 13. Assertions inspect the saved row counts, units and amounts, including the effect of the blank row and surrounding spaces.

#### W004 — Editing one day in a legacy compound record removed other days' dishes

Code: `build/web-exact-source/app.js`, `build/web-exact-source/pro.js`, `web/test_v1_0_1_regressions.js`

Some legacy records store several business dates in the `daily`, `dishes` and `fixed_expenses` arrays of one payload. The dish editor's `saveDishes()` submits the selected day with `payload.dishes = [raw]`. The old `saveRecord()` merged sibling dates only in certain `daily` cases; it did not do the same for dishes or fixed expenses. Saving one day's dishes could consequently reduce the entire `dishes` array to that day. The removed dishes would also disappear from subsequent consumption statistics and inventory calculations.

There was a separate read error. If `dishData()` could not find the selected date, it used `payload.dishes[payload.dishes.length - 1]`. A date with no dishes could display the last dish record from another day. Saving that view could then assign the borrowed contents to the selected date.

`saveRecord()` now merges `daily`, `dishes` and `fixed_expenses` separately by normalized business date, replacing only rows belonging to the edited day. It preserves other dates and undated legacy rows in a compound record that cannot be unambiguously assigned to the target day. `dishData()` returns an empty list when no matching date exists. An undated dish record is used only when its parent record unambiguously identifies the selected single day. Slash-formatted dates are normalized for comparison while writes retain the original record key.

`compoundDates()` creates a record containing two adjacent dates. After changing the first day's dish cost from 10 to 15, it checks that the second day's dishes, both daily records and all three fixed-expense rows remain. Clearing the first day's fixed expenses then preserves the second day's expense and an undated legacy expense. The test also checks both an empty dish result for an absent date and successful reading of an undated dish in an unambiguous single-day record.

#### W005 — Switching books during an asynchronous operation changed its target or result

Code: `build/web-exact-source/app.js`, `build/web-exact-source/v28.js`, `web/test_v1_0_1_regressions.js`

After Save is clicked in book A, the browser may still be waiting for device registration, checksum calculation or the server response. The old `saveRecord()` continued to read mutable `state.dataset` across these waits. Switching to B could send a payload originating in A's editor to B's URL. A request already sent to A could also update the local record cache while B was on screen. This can happen when the user is legitimately authorized for both books; server membership checks do not ensure that the browser selects the intended book.

A save now captures `datasetId`, the login token and `contextGeneration` at the start. `ensureWebDevice(datasetId)` uses that same ID for registration and its device-cache key. Before sending PUT, the code checks that the captured values still match the active state and cancels an unsubmitted save if they do not. If the switch is detected after PUT completes, the user is told that the original book was saved and is directed back to it; the response is not applied to the current page or cache. The generation counter also detects an A→B→A round trip that an ID-only comparison would miss.

Store-name and WeChat-configuration functions in `v28.js` now retain the context in which their requests began. `loadStoreSettings()` additionally compares a request number and a settings revision so a late read cannot undo newer settings. Configuration saves, deletion, verification and bill requests check the active book before applying their results. A separate same-book race is handled by `recordWriteRevision`: a successful record save advances it, and `loadCloudData()` discards an older record snapshot if a save has completed since that refresh began.

`writeRace()` pauses at device registration, checksum calculation and the response, then changes books. It checks that PUT is either not sent or remains addressed to A, and that the current record value of 999 is not replaced by A's response; it also tests A→B→A. `deviceRegistration()` verifies that A's device ID is stored only under A's cache key. `settingsLoadRace()` and `settingsWriteRaces()` test out-of-order settings responses, a changed login and the five settings operations above. In `mainRefreshRace(true)`, a refresh starts with revenue 100, a save of 200 completes, and the old response is then released. The local record remains 200.00. This last assertion concerns the browser's copy of an accepted save; the delayed GET does not perform another server write.

#### W006 — The cash page retained stale data and late refreshes restored an older balance

Code: `build/web-exact-source/app.js`, `build/web-exact-source/sep04.js`, `web/test_v1_0_1_regressions.js`

The cash page used to keep its own server response in the closure variable `cashServerV4` in `sep04.js`, while the main page used `state.cashPosition`. A main refresh or a book switch did not reliably update both copies. The ledger could therefore contain newer amounts while the cash table still showed the balance from its previous load, or temporarily showed another book's result. This is a read/display problem; fixing it does not correct an erroneous expense already stored in a record, such as A001.

Cash loading and rendering now share `state.cashPosition`, with `cashPositionDatasetId` identifying its book. A book switch clears the cached cash data and old table and shows a loading state. Only data associated with the current book is used to render the cash table. `loadCloudData()` also applies its cash response before taking the early return for unchanged daily records. Cash data, including opening-balance adjustments, can change independently of those records.

The shared cache also needs protection against response order. Both `loadCashLedgerV4()` and the main refresh's cash GET capture the cash revision, then check it along with the book, login and generation before applying a response. If another valid read has already updated cash, or a record save has advanced the revision, the older request is discarded. This closes a gap in the intermediate implementation: a dedicated cash request could display 200, only for an earlier main refresh returning 100 to replace it.

`cashContext()` checks a same-book refresh from 100 to 150, a switch to a book with 900, and a late response from the previous book that must not replace the current 250. It also checks that an old dedicated request cannot undo a newer main refresh. `cashMainRefresh()` changes the cash balance from 100 to 150 while the daily-record array remains identical. `mainRefreshRace()` controls the opposite response order: the dedicated response of 200 completes first and the main refresh's old response of 100 completes afterward; the final balance stays 200. `mainRefreshRace(true)` adds a successful record save before releasing the old response.

#### W007 — Purchase and consumption charts combined quantities with different units

Code: `build/web-exact-source/pro.js`, `build/web-exact-source/charts-oct30.js`, `web/test_v1_0_1_regressions.js`

When several ingredients were selected, or one ingredient appeared in units such as jin and kilograms, the old charts summed quantities by date, month or weekday before calculating unit prices or cumulative quantities. They did not first separate item name and unit. For example, 1 jin of potatoes costing 10 and 1 kilogram costing 30 became an amount of 40 divided by a quantity of 2. The resulting price of 20 has no valid unit. Cumulative consumption charts similarly combined quantities that could not be added directly.

`ingredientSeriesGroups()` now groups by `[row.name, row.unit]`. Date, month and weekday aggregation takes place inside each group, and the labels identify both the item and its unit. The statistical functions in `pro.js` and the active chart implementation in `charts-oct30.js` use these groups. Units remain as entered; the application neither assumes a jin-to-kilogram conversion nor combines different items into one unit-price denominator.

Unpriced purchases still contribute to quantity statistics, but average unit prices use only quantities whose amounts are known. `ingredientAggregate()` keeps total quantity and `pricedQuantity` separately, preserves unknown amounts as `null` and treats an explicit zero as known. For two rice purchases of 10 jin each, one costing 20 and the other not yet priced, the reported quantity is 20 jin and the priced portion averages 2 per jin, with a priced-only label. It does not divide 20 by all 20 jin and report 1 per jin.

`groupedCharts()` checks separate potato/jin, potato/kilogram and greens/jin series in the trend, monthly and weekday panels. Their sample unit prices are 10, 30 and 6; cumulative consumption quantities are 1, 1 and 2. `unknownPriceStats()` checks the 20-jin rice example, a wholly unpriced group with no numeric price, and an explicitly free purchase that retains a known zero unit price. These assertions inspect series produced by the actual chart functions and the quantities and price annotations in the statistics table.

#### W008 — The batch drawer reconstructed the wrong remainder from quantity and unit price

Code: `build/web-exact-source/inventory-workspace.js`, `web/test_v1_0_1_regressions.js`

When the inventory batch drawer was opened, `openItem()` displayed each remaining lot's value as `amount(batch.quantity * batch.unit_price)`. The FIFO engine allocates the original lot amount cumulatively to whole cents, so the amount already consumed may include a cent assigned by an earlier rounding step. Multiplying the remaining quantity by the original unit price and rounding again does not account for that allocation. The drawer could differ from the inventory balance by a cent even when the original unit price was stored exactly.

The drawer now displays `amount(batch.original_value - batch.consumed_value)`: the original lot value less the cost already allocated to consumption. The FIFO allocation algorithm is unchanged; the detail view now uses the engine's existing booked remainder. Lots with unknown prices continue to show a pending-price label rather than a zero amount.

`fifoDisplay()` runs the actual `InventoryFIFO.replay()` with a receipt of 4 portions at 0.005 each, totaling 0.02, followed by consumption of 1 portion. The engine allocates 0.01 to that consumption, leaving a booked value of 0.01 for the remaining 3 portions. The old expression recalculated `3 × 0.005 = 0.015` and rounded it to 0.02. The test inspects the drawer HTML produced by the real `openItem()` function and requires 0.01 instead of the reconstructed 0.02.

#### W009 — Text serialization lost detail fields, and blank totals could become zero costs

Code: `build/web-exact-source/pro.js`, `build/web-exact-source/app.js`, `build/web-exact-source/sep07.js`, `build/web-exact-source/v28.js`, `backend/app/main.py`, `desktop/restaurant_cost_manager.py`, `web/test_v1_0_1_regressions.js`, `build/test_v1_0_1_desktop_qt.py`

The old `serializeItems()` joined purchase details into comma-separated text, while `parseDetailItems()` split that text at commas, Chinese commas, semicolons and newlines. A note containing those characters could turn one purchase into several: the note “赊账, 运费5” could cause its “运费5” fragment to be parsed as another detail. The serializer also wrote quantity and unit only when quantity, unit and total were all present. A purchase with a known quantity but no price could therefore be reduced to its name. Reopening, saving or synchronizing the result could lose fields and change expense amounts or the quantities used for inventory receipts.

`serializeItems()` now writes a JSON array containing `name`, `quantity`, `unit`, `price`, `total` and `note`; the legacy text parser remains available for existing records. Commas, quotes, backslashes and newlines stay inside their fields, and purchase notes use a multiline `textarea`. Dish summaries, history and read-only views produce readable display text while keeping the original JSON in the stored field. They do not save the summary back as source data. Web, API and desktop readers preserve the distinction between a missing value and an explicit zero.

`detailAmount()` and the corresponding readers apply a specific amount rule: use an entered total, including zero; otherwise derive quantity times unit price only when both are known; otherwise retain an unknown amount. Quantities with unknown amounts are excluded from the denominator of priced averages. The desktop purchase page had also been summing `total` directly, so quantity=2, price=3 and a blank total could contribute zero during a save or move. Loading, summaries, saving and moving in `PurchaseDetailTab` now obtain their amounts through `detail_total_cost()`. The effective cost is 6 while the original `total` field stays blank, preserving what the user actually entered.

Web tests `losslessDetails()`, `savedDetailRoundTrip()` and `purchaseControlRoundTrip()` exercise six-field serialization, PUT payloads, reloading and a further save. Notes retain commas, Chinese punctuation, newlines and quotes exactly. A quantity of 2 at a unit price of 5 with no total contributes 10, while an explicit total of zero contributes zero; editing only the note leaves the amount unchanged. `unknownPriceStats()` distinguishes unknown and zero prices, and `entryFormatTiming()` checks that using JSON does not reset server-provided editing deadlines. The desktop Qt case `test_W009_derived_amount_survives_purchase_save_and_move` saves the 2×3 detail at a cost of 6, then moves it into a category with an existing derived cost of 2. The source becomes zero and the destination becomes 8, with the quantity, price, note and blank total retained.

#### UI001 — Long monthly forecast labels were clipped in the full operating report

Code: `web/sep07.css`, `web/reporting-oct30.css`, `web/test_sep11v1_frontend.js`

In the expanded full operating report, the day, week, month and year cards appear side by side. Long labels in the monthly forecast, including the explanation of the daily Revenue increase needed to break even, extended past the card's right edge. `sep07.css` set `white-space:nowrap` on `.forecast-title` and `.forecast-formula`, and `min-width:max-content` on the amount. The later `reporting-oct30.css` changed forecast rows to block layout without removing those inner no-wrap rules. Narrower cards or larger text could not wrap the explanation, and long amounts could also force the content wider.

Forecast titles and formulas now use `white-space:normal` and `overflow-wrap:anywhere`. Amounts may shrink and wrap while retaining right alignment. Within the full report, cards have `min-width:0`, ordinary metric rows use two `minmax(0,1fr)` columns, and their labels and values may wrap inside those columns. This addresses the monthly forecast and keeps long amounts inside the day, week and year cards as well. The wording, number formatting and financial formulas are unchanged.

Local browser checks loaded the actual CSS in `web/index.html` order and used report-rendering functions from the generated `app.js`, with synthetic data only. All 20 combinations passed: Chinese or English, widths of 320/375/768/1024/1440 pixels, and normal or enlarged text. Each case contained all four cards and checked card and metric-row `scrollWidth/clientWidth`, text rectangles for forecasts and amounts against their card bounds, and document-level horizontal overflow, using a 1.1-pixel tolerance. The saved browser DOM reports 20/20 PASS; separate screenshots show the 1440-pixel four-column report and the narrow Chinese view for visual inspection. Assertions in `web/test_sep11v1_frontend.js` that previously required unwrapped forecast text now check wrapping and shrinkable, right-aligned amounts.

### API and data recovery

#### B01 — Temporary date permissions allowed changes to other dates

Code: `backend/app/main.py`, `backend/app/inventory_balance.py`, `backend/tests/test_v1_0_1_regressions.py`

An account allowed to edit only one day could previously change revenue for an earlier, unauthorized date by appending a row for the authorized date to the request. The old `_effective_record_role()` called `_record_day(record_key, payload)` once and used that single date to authorize the entire record. `_record_day()` prepended each date from `daily` to its candidate list, allowing the last valid row date to take precedence over the record date in the URL. Because legacy records can contain several business dates, permission for one row became permission for the whole record.

`_effective_record_role()` now receives both the previous and proposed payloads. It groups `daily`, `fixed_expenses` and `dishes` by business date and identifies the dates whose contents change. Removing a row, moving it to another date or deleting the record also requires permission for the original date. The function evaluates permission for each affected date and uses the lowest resulting role. Undated metadata is attributed to the record's own date; retaining an unchanged historical row does not by itself prevent an otherwise permitted edit.

Authorization also accounts for changes in source precedence. Saving a packed legacy record gives it a higher `sequence`, which can make one of its unchanged historical rows the effective source again. The code therefore compares the results of `canonical_daily_rows()` and `canonical_dish_rows()` before and after the proposed write. A request that edits only an authorized date still needs permission for another date if promoting the record would replace that date's effective revenue or dish consumption.

In `test_b01_mixed_dates_cannot_elevate_whole_record`, appending the authorized date no longer permits the historical revenue change from 100 to 999: the response is 403 and revenue remains 100. In `test_b01_unchanged_legacy_dates_do_not_block_permitted_edit`, the historical row is retained while revenue for the authorized day changes from 50 to 60 successfully. Two additional source-precedence tests reject an edit that would revert unauthorized revenue from 200 to 100, and an edit that would change dish consumption despite identical revenue values. The same API test group checks removal of fixed-expense and dish rows, as well as deletion of a whole record.

#### B02 — Expense totals, revenue totals and format changes bypassed entry deadlines

Code: `backend/app/main.py`, `backend/tests/test_v1_0_1_regressions.py`

After an entry-role user saved a rice purchase of 1 jin for 10.00 and store A cash income of 100, changing the detail or cash input an hour later was rejected. The old code nevertheless accepted changing only `食材成本` (ingredient cost) to 99 or only `A店收入` (store A revenue) to 999. Detail items and payment inputs had first-save timestamps, but their totals were treated as derived fields and exempted from the ordinary field restrictions. The server then stored the totals supplied by the client. Reports and cash balances could therefore change while the underlying detail appeared untouched.

`_entry_timing_updates()` now calls `_validate_entry_totals()` to distinguish a change to a total from a change to the details or payment inputs that produce it. Where details exist, expense totals are summed from their amounts. An explicit total on a structured item takes precedence; otherwise the amount is calculated when both quantity and unit price are known. Revenue is recalculated with the existing payment-channel formula, including an explicitly entered zero. A changed total inconsistent with its inputs returns 422. Changing only a total after its 30-minute deadline returns 403. Valid legacy records containing an amount without details or payment channels remain supported, and untouched historical values are not automatically rewritten by this check.

Adding detail items still follows the existing 12-hour addition rule. In `test_b02_append_does_not_authorize_arbitrary_total`, a user saves an ingredient purchase of 10 and adds vegetables costing 5 an hour later. Submitting a total of 999 returns 422; submitting 15 succeeds. `test_b02_locked_derived_totals_cannot_change_alone` separately rejects changing cost from 10 to 99 without changing the detail, and revenue from 100 to 999 without changing the cash input, both with 403. This preserves legitimate additions that change a total after the original items' correction deadlines.

Converting legacy total-only income to payment channels also allowed the deadline to be bypassed. A record containing only `A店收入=100` or `收益=100` could be changed an hour later by adding `A店现金=999` and setting the revenue total to 999. The earlier check treated the cash field as a new input and started a new clock. The code now recognizes a conversion where an old total is present, its old channel inputs are all blank, and channel values are being introduced. Once the original first-save time plus 30 minutes has been reached, the conversion cannot change the recorded amount. Each introduced channel also receives the earlier of its existing timestamp and the original total's timestamp, preventing a fresh correction window on a later request.

An equal-value conversion remains allowed. In `test_b02_equivalent_total_conversion_preserves_clock`, adding store A cash of 100 to a record that contains only store A revenue of 100 succeeds an hour after the first save. An immediate follow-up request changing both values to 999 returns 403. `test_b02_legacy_store_total_keeps_lock_when_channels_appear` and `test_b02_legacy_grand_total_keeps_lock_when_channels_appear` also reject direct 100-to-999 conversions for the store total and the daily total respectively.

Converting legacy detail text to JSON also preserves item timestamps. `_entry_timing_updates()` matches equivalent item content instead of giving a serialized item another 30-minute window. `test_b02_json_format_upgrade_keeps_old_item_clock_and_allows_append` converts the two rice purchases “米 1斤 10.00, 米 1公斤 20.00” to structured data and adds vegetables costing 5 after an hour; the resulting total of 35 saves successfully. Subsequent changes to the original rice item's quantity, amount, note or unit return 403. Adding another item 13 hours after the first save is also rejected.

#### B03 — Generic record and sync endpoints exposed restricted cash records

Code: `backend/app/main.py`, `desktop/restaurant_cost_manager.py`, `backend/tests/test_v1_0_1_regressions.py`, `build/test_v1_0_1_desktop.py`

The dedicated cash endpoint already limited reads to administrators and editors, but the same data remained accessible through generic endpoints. The old `read_record()`, `list_records()` and `changes()` checked authentication and ledger membership without checking the record type and key. A viewer or entry-role account could receive 403 from `/cash-position` and still retrieve the opening balance and cash transactions through `/records/global/cash_position`, the record list or change synchronization.

`_record_visible()` now applies the role restriction to all three supported keys: `cash_position`, `cash_balance` and `base_balance`. Direct reads by accounts without cash access return 403, and record-list queries exclude these records before pagination. `changes()` calculates `next_sequence` and `has_more` from the unfiltered page before filtering its returned items. A page containing only hidden cash records therefore still advances the client's cursor, allowing it to reach subsequent records.

Once the server filters records, desktop synchronization must distinguish a permission change from deletion of business data. `EmbeddedCloudSyncWorker._sync_records()` removes cash entries from a viewer's or entry user's local cache, excludes their identities from the current local and cloud record sets, and removes their saved synchronization baselines. The missing local cache entry consequently does not become a request to delete the cloud record.

`test_b03_all_cash_aliases_hidden_and_cursor_progresses` saves an opening balance of 54321 under each cash key, followed by an ordinary daily record. Direct reads of all three keys return 403 for both viewer and entry roles. A record list with `limit=1` returns the daily record, and paginated changes advance past the cash records to reach it; an administrator can still read all four records. The desktop test `test_B03_low_role_cash_removed_locally_without_cloud_delete` starts with a cash cache entry and its saved baseline, then synchronizes an empty visible cloud list as an entry user. It verifies that the local entry and baseline are removed without invoking an upload or cloud deletion.

#### B04 — Cash alias migration failed or checked the wrong version

Code: `backend/app/main.py`, `backend/tests/test_v1_0_1_regressions.py`

A legacy ledger can contain a deleted canonical `cash_position` row alongside an active `cash_balance` alias. The deleted row still owns its database unique key. The old `_save_cash_position_record()` selected an active row first and then renamed its key to `cash_position`, causing a unique-key violation and a failed cash-settings save in this state.

Read and write selection was also inconsistent. GET only put the canonical key first, while PUT additionally sorted by `updated_at` descending. With a deleted canonical row and active `base_balance` and `cash_balance` aliases, GET could return one alias's version and PUT could validate against the other. A user could consequently receive 409 immediately after opening and saving the page, without an intervening write.

Both paths now use `_cash_record_candidates()`. It sorts the canonical key first, then `updated_at`, `sequence` and `version` descending, followed by `record_key` and `id` ascending. Both paths select the first active record in that order. Saving locks all candidates and checks the client's version against that same visible record. An existing canonical database identity is reused even when marked deleted; after a successful save, other active aliases are marked deleted with audit entries. The existing compatibility rule for `expected_version=0` remains; a nonzero version obtained from GET is checked for equality.

The restored canonical version must also differ from a stale alias version. For example, restoring a deleted canonical v7 while the visible alias is v8 would produce another v8 if the canonical version were merely incremented. A second request holding the old page's v8 could then pass validation. The implementation now uses `max(item.version for item in candidates) + 1`, producing v9 in this example. Requests with the old version subsequently receive 409, while the new version can be used for the next save.

`test_b04_three_aliases_get_then_save_and_stale_version` creates a canonical tombstone at v7, an alias at v5 with a balance of 100, and a newer alias at v8 with a balance of 200. GET selects the 200 record, saving 201 with that version succeeds, and only the canonical record remains active. Reusing v8 to save 999 is rejected and the balance remains 201. Other tests exercise equal update timestamps, ties in timestamps and sequence/version, and an active canonical record older than its aliases. In `test_b04_alias_changed_after_read_rejects_old_version`, another request changes the visible record to 300 between GET and PUT. The stale page's attempt to save 999 returns 409 and leaves 300 intact.

#### B05 — Cash totals added overlapping sources for the same day

Code: `backend/app/main.py`, `backend/app/inventory_balance.py`, `backend/tests/test_v1_0_1_regressions.py`

Importing an ordinary user workbook with two rows for the same day, or reading legacy packed records with overlapping dates, previously caused the cash report to add every row. For example, two sources for one day contain revenue of 100 and 150 and other expenses of 10 and 20. The daily ledger uses the later effective source and shows 150 and 20, while the old cash calculation reported revenue of 250 and expenses of 30. `_cash_flow_summary_db()` summed each `daily` row in every day record directly, and its date count duplicated the day as well.

The calculation now reads day records in `sequence` and record-ID order, then calls `canonical_daily_rows()` to resolve the effective content for each business date. Cash income, daily expenses and the date count are calculated from that result. The function uses the source precedence already used by the ledger and inventory: sequence, version, record position and row position, with field merging. A blank field in the newer source does not erase an existing nonblank value, while an explicit numeric zero is a supplied value. Fixed expenses continue through the existing fixed-expense calculation.

`test_b05_user_excel_duplicate_rows_count_once` encodes the two-row example as a real XLSX file and uploads it through the workbook API. The cash endpoint then returns revenue of 150, daily expenses of 20 and a date count of 1. `test_b05_duplicate_dates_follow_canonical_merging` uses two differently keyed records that refer to the same day. The older source also contains ingredient cost of 3, while that field is blank in the newer source. The result is revenue of 150 and daily expenses of 23: the newer other expense of 20 plus the retained ingredient cost of 3. The date is still counted once.

#### B07 — Internal workbook restore changed which overlapping record took precedence

Code: `backend/app/excel_io.py`, `backend/app/main.py`, `backend/app/inventory_balance.py`, `desktop/restaurant_cost_manager.py`, `backend/tests/test_v1_0_1_regressions.py`, `build/test_v1_0_1_desktop_qt.py`

Old internal workbooks stored payloads and checksums without the source order used to resolve overlapping dates. `build_internal_workbook()` sorted by record type and key; `apply_workbook_records()` also wrote in key order and assigned new sequences. If the original sequence order differed from key order, restoring intact payloads could change the effective ledger. For example, a record keyed 2 October is saved first with revenue of 50 and 5 jin of rice. A record keyed 1 October is saved later but also contains data for 2 October, with revenue of 100 and 10 jin of rice. The effective result is 100 and 10 jin. Restoring in key order makes the 50 and 5-jin record the later source instead.

New internal workbooks add `source_order` to every business record to preserve relative precedence at backup time. Export sorts by an existing source_order or sequence, then version and original position, and assigns consecutive values starting at 1. If the column is used, parsing requires a distinct positive integer for every business record. Import schedules writes in that order while allowing the target ledger to allocate its own sequences; the saved value is not reused as a synchronization cursor.

Partial restores need another safeguard. Restoring only the older member of an overlapping group would give it a new sequence beyond the newer member, whose unchanged payload otherwise needs no write. `apply_workbook_records()` therefore groups records connected by shared daily or dish dates. If any member needs restoration, has changed content, or is in the wrong current order, the group is rewritten in backup order. Records sharing only a dish date participate as well. An identical import whose order is already correct remains unchanged, without refreshing versions and timestamps for unrelated dates.

The desktop retains `source_order` when reading and writing internal workbooks. Its sync comparison now considers cloud sequence/version changes as well as payload hashes. `_embedded_align_source_order()` uses the complete set of cloud records acknowledged in the current cycle to arrange local precedence, while preserving local changes that have not been uploaded and differ from the cloud. `test_B07_source_order_survives_real_excel_and_new_write_advances_rank` writes and rereads a real internal XLSX file. With source-order values `[2, 1]` in physical row order, revenue of 200 remains effective; editing the older record to 300 then promotes that new write to the effective source.

The backend test `test_b07_backup_new_ledger_and_full_restore_keep_business_order` exports the 100-revenue, 10-jin example as XLSX and restores it into both a new ledger and the original ledger after its records have been soft-deleted. Revenue and stock remain unchanged. Reimporting the untouched backup returns `unchanged=2` and preserves both records' sequence/version values. `test_b07_partial_restore_keeps_unchanged_winner` checks a one-record restore, while `test_b07_partial_restore_keeps_shared_dish_only_date` retains the 10-jin consumption where only dish dates overlap. Older workbooks without source_order remain readable, but precedence that was never saved cannot be reconstructed from their payloads; a new backup should be taken after upgrading.

### Desktop application

#### D001 — Edits saved during an upload were left out of the next sync

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

A user can continue editing while the desktop client uploads a record. Previously, `EmbeddedCloudSyncWorker._sync_records` read local revision v2 before sending the request, then reread the local file when the upload finished and used that newer content to build its sync baseline. If the user had saved v3 while the request was in flight, the baseline recorded local v3 alongside cloud v2. Neither side appeared to have changed in the next cycle, so v3 remained on the computer even though only v2 had been uploaded. A later cloud change could also replace that unsent local revision.

`_sync_records` now retains the records read at the start of the cycle and tracks `acknowledged_local` and `acknowledged_cloud` separately. After an upload, the cloud state comes from the version returned by that PUT; a later list response cannot acknowledge another device’s intervening write. The local state likewise excludes edits made while the upload was running. `_build_baseline` records the states actually processed, while records with conflicts retain their previous baseline for the next comparison.

Downloads receive a corresponding check. `_embedded_apply_cloud_records` takes `expected_hashes` and rereads the record hashes after acquiring the internal workbook’s file lock. If a local save changed the same record while the download was pending, the function raises an error and preserves the local content instead of writing on the strength of an earlier, unlocked check.

In `test_D001_upload_during_GUI_save_remains_pending`, a local save is inserted during the first upload response. Two sync cycles must produce uploads [2, 3], rather than sending only 2. `test_D001_cloud_apply_checks_snapshot_inside_lock` supplies an expected hash that differs from the record read under the lock, then asserts that the operation is rejected and the file writer is never called. These tests exercise both the skipped upload and the download that could replace a newer local save.

#### D002 — Changing the annual workbook changed the same book’s cash balance

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

The opening cash balance, reference date and manual cash `transactions` belong to the whole book. The old `_cash_position_ledger` nevertheless called `load_daily()` and `load_fixed_expenses()`, which read the annual Excel workbook currently open. Switching from 2026 to 2025 therefore changed the operating income and expenses included in the calculation. The same opening balance and reference date could produce a different cash balance without any transaction being edited, because movements across the year boundary were not considered together.

The new `_cash_position_source_frames` reads across years from the internal workbook. It obtains effective daily records through `_inventory_day_sheet("daily")` and takes fixed-expense entries from the internal day records, rather than relying on rows present in the selected annual mirror. `_cash_position_ledger` still includes only movements after the reference date and no later than today. The month filter selects the `transactions` shown on screen without changing the calculation of current cash.

The regression `test_D002_cross_year_cash_does_not_follow_active_mirror` uses an opening balance of 5, December 2025 income of 100 and expenses of 10, and January 2026 income of 200 and expenses of 20. With either the 2026 or 2025 mirror selected, the balance must be 275.00: 5 + 100 − 10 + 200 − 20. The balance brought forward into January 2026 must be 95.00. A future-dated income entry of 999 must not increase current cash. The change makes cash use data across years; annual viewing and editing retain their existing behavior.

#### D003 — Saving from a stale cash window could discard another device’s transaction

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`, `build/test_v1_0_1_desktop_qt.py`

After the cash page or an add-transaction window opens, `CashPositionTab` retains the loaded `_payload`, including its `transactions` array. A modal window prevents the screen from refreshing, but background sync can still write another device’s new transaction into the local internal workbook. The old `save_cash_position_record` passed the window’s stale data to `_save_global_record_payload`. That function acquired the file lock but did not check whether the record had changed before writing back the whole cash record. Adding a transaction locally could therefore also remove a transaction that had just arrived through sync.

The cash page now keeps `_payload_hash`, the hash of the original loaded payload. Adding or deleting a transaction and correcting the balance all pass it to the save function as `expected_hash`. Within the same file lock, `_save_global_record_payload` reads the current record and compares its hash. A mismatch rejects the save and asks the user to refresh before submitting again. Legacy cash names are checked in the same order as loading: `cash_position`, `cash_balance`, then `base_balance`. This keeps the save check tied to the record the window actually loaded.

The regression `test_D003_stale_cash_update_is_rejected_but_matching_save_works` adds a transaction of 20 to the current record, then submits using the old window’s hash. It checks that the submission is rejected, the new transaction survives, and a save with the current hash succeeds. The regression `test_D003_cash_alias_migration_checks_loaded_record_hash` uses a real temporary XLSX containing a `cash_balance` record with an opening balance of 100. After loading it, the test writes another device’s income transaction of 20. Rejecting the stale save must leave the XLSX byte-for-byte unchanged. Reloading and changing the opening balance to 120 then creates `cash_position` while retaining the transaction of 20.

These regressions execute the actual cash read and save methods and temporary Excel I/O. The latter lives in the Qt test file but does not simulate clicking buttons in the cash window. Desktop cloud sync continues to use the generic record endpoint with the record name and version. This change checks for conflicts before a local save; it does not automatically merge stale window contents with newly received `transactions`.

#### D004 — Fixed costs were missed on closed days and in periods without daily records

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

The old `calc_week_summary` first selected daily records for which `day_has_meaningful_data` was true, then added the fixed-cost allocations from those records. If only one day of a week had operating activity, it counted only one day of rent, wages and other fixed costs, even when the other six days had already passed. `calc_month_summary` and `calc_year_summary` also returned `None` before calculating fixed costs when no meaningful daily records existed. A month without trading could therefore show no cost or loss despite having wages or rent configured.

Weekly reporting now calculates fixed costs separately from operating records. It calls `calc_day_metrics()` for each day of the selected Monday–Sunday week that is not in the future, then sums those fixed-cost allocations. Revenue and variable costs still come from meaningful daily records. A closed day therefore contributes fixed costs to weekly cost and net profit without becoming an active trading day. Monthly and annual reporting calculates fixed costs before deciding whether to return a result; either operating records or fixed costs are enough to produce a report.

Monthly reporting retains the configured whole-month fixed amount, including for the current month. Annual reporting sums months through the current month, also taking the current month’s whole fixed amount and excluding future months. Neither monthly nor annual fixed costs have been changed to daily accrual. Months containing only fixed costs also enter the divisor for average monthly net profit, so they no longer disappear from that average.

In `test_D004_empty_days_month_year_keep_fixed_costs`, October has fixed costs of 3,100, or 100 per day. A week with income of 1,000 recorded only on Monday must have fixed costs of 700, net profit of 300 and one active day. Adding zero-income records for the other six days leaves those results unchanged. With the operating records removed, October still reports net profit of −3,100; the annual report has fixed costs of 3,100 and average monthly net profit of −3,100. The test also configures fixed costs of 3,100 for a future December and confirms that they are not included early.

#### D005 — Cash calculations treated total-only revenue as zero

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

Some older daily records contain only the total in the 收益 field, with no cash, WeChat, Alipay or other channel breakdown. The old `_cash_position_ledger` called `recalculate_revenue_fields` for every row and read its 收益 result. That function summed empty channels to zero and returned a 收益 key, so the fallback in `.get("收益", original_revenue)` was never used. A stored total of 1,000 consequently became zero in the cash calculation. A later fallback to the older 总金额 field could not recover a record containing only 收益; it could also revive an old total when a channel had explicitly been set to zero.

`_cash_daily_revenue` now uses `money_value_was_entered` to check whether any channel value was actually entered. It recalculates from channels only when such input exists. Otherwise, it checks 收益, 总金额, 收入 and 总收入 in that order and uses the first entered value. Zero is an entered amount, not an empty field, and does not fall back to another stored total. `_cash_position_ledger` uses this function to obtain operating revenue.

The regression `test_D005_total_only_legacy_and_explicit_channel_zero` exercises three records. A record with only 收益=1000 adds 1,000.00 to cash; one with only the legacy 总金额=123.45 adds 123.45; and one with 收益=1000, 总金额=999 and A店现金=0 contributes 0.00 rather than 1,000 or 999. This change concerns reading older data for cash calculations. The regular ledger form’s `save_record(mode="overwrite")` already supported total-only revenue.

#### D006 — Saving an oversized JSON cell could silently damage the internal workbook

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

The internal Excel workbook stores each business record’s JSON in a single cell. As purchase or inventory data grows, `payload_json` can exceed Excel’s 32,767-character cell limit. openpyxl truncates an oversized string when writing it, yet the resulting XLSX can still be opened. The old `_write_internal_frames` checked only that the temporary file could be opened as an Excel workbook before replacing the original with `os.replace`. A save could therefore appear successful, with JSON parsing or hash validation failing only on the next read.

Before writing, the function now checks column names and string-cell lengths, then calls `_validate_internal_frames_integrity` to validate the business JSON and hashes. Oversized cells or already malformed JSON cause an error before the original file is replaced, with the size error identifying the sheet, row and field. Storage remains Excel-based: an oversized record must be shortened before saving, and the cell limit has not been increased.

After these checks, the function writes a temporary XLSX, rereads its sheets with `read_excel_exact`, validates the JSON and hashes again, and compares each `payload_json` value with the intended value. Only then does it call `os.replace`. Errors remove the temporary file and preserve the original. This checks the business content actually read back, as well as whether the workbook container can be opened.

The regression `test_D006_oversize_and_corrupt_json_never_replace_existing_file` first writes a valid temporary workbook and saves its original bytes. It then attempts three writes: one inventory record containing 300 synthetic receipt entries, with JSON exceeding 32,767 characters; malformed JSON containing “{broken”; and a simulated readback in which `payload_json` has changed to “{}”. Each attempt must raise an exception and leave the original XLSX byte-for-byte unchanged. The last case specifically verifies that a valid XLSX container is insufficient when its business content does not match what was written.

#### D007 — Recovering from an annual workbook could delete other years from the cloud

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

When the internal workbook is missing but the current year’s user workbook survives, startup calls `_create_internal_automatically_from_user` to rebuild internal storage. Previously, it imported only that annual workbook while retaining the old `embedded_baselines` spanning multiple years. If the baseline contained 2025 and 2026 but the reconstructed local file contained only 2026, the next `_sync_records` cycle saw 2025 records present in the baseline and absent locally. It interpreted that absence as an intentional local deletion and sent delete requests to the cloud. The error was treating a partially recovered copy as sufficient evidence of deletion.

Before rebuilding, the program now clears `embedded_baselines` and sets `embedded_cache_recovery`. The next connected sync cycle obtains the cloud records and restores that snapshot with `_embedded_apply_cloud_records(..., replace_all=True)`. The 2025 records therefore return to the internal file instead of first being submitted as local deletions. The recovery marker is cleared only after the cycle successfully builds a new baseline and saves the configuration.

The regression `test_D007_missing_internal_recovery_never_deletes_other_year` starts with old baseline and cloud records for both 2025 and 2026, while its annual-workbook import restores only 2026. It executes the actual recovery and sync methods, using test substitutes to record uploads, deletions and local reconstruction. The resulting local data contains both years, the cloud deletion list is empty, no unexpected upload occurs, and the recovery marker is removed after success. The test records these operations through sync substitutes without connecting to a live cloud service.

If recovery is active and the surviving annual mirror contains data but the cloud has no active records, `_sync_records` raises an error first, retains the mirror and asks the user to confirm the selected book. It does not proceed to infer deletions. This branch was checked by reading the code; the automated test described above executes recovery with both years still present in the cloud.

#### D008 — Background refresh updated the save baseline while the form still showed old data

Code: `desktop/restaurant_cost_manager.py`, `build/test_v1_0_1_desktop.py`

The ledger form and the baseline used to detect save conflicts must describe the same data. Previously, `MainWindow._refresh_cloud_files_in_background` called `sync_internal_to_user_excels(update_baseline=True)` first, writing new cloud content to the mirror and updating the global baseline. Only after that background I/O finished did it check for unsaved form input. If the user began editing during the I/O, the old form stayed on screen while its baseline had already advanced. A cost still displayed as 10 could therefore replace a cloud value of 20 when the user saved a note-only edit, because the conflict check was comparing against the newer baseline.

The background task now reads the internal frames, writes the annual mirror and captures file signatures under the file lock, explicitly using `update_baseline=False` for the mirror write. Back on the main thread, unsaved input or an open modal window leaves the existing form and editing baseline in place, while allowing a later refresh to retry. Only after `_refresh_visible_tab_after_cloud_update` has refreshed the controls does `_set_app_baseline_from_internal` install the baseline from that read.

The regression `test_D008_real_form_handler_rejects_stale_background_editor` starts with a form showing cost 10 and the detail “米 1斤 10.00”. The background record becomes cost 20 with its matching detail, and a note-only user edit is inserted during the background I/O. The test then executes the actual `LedgerTab.get_form_data`, `save_record(mode="overwrite")` and `_commit_user_sheet_to_internal` functions. The save must be rejected as a conflict, with zero records written; internal storage must retain 20.00 and the cloud record’s original note. Input controls are test substitutes in this case, while parsing and saving use the actual source methods.

The regression `test_D008_clean_reload_binds_snapshot_after_widgets_and_modal_defers` checks both a normal refresh and an open modal window. With no unsaved input, controls must load before the baseline is set from the same read. With a modal window open, only the mirror changes; neither the editing baseline nor the recorded refresh signatures advance. Background sync can therefore continue without allowing an old form to pass its save check using a newer record’s hash.

### Build and distribution

#### BUILD001 — Consistent version identifiers and checks for packaged builds

Code: `VERSION`, `build/make_release.py`, `build/rebuild_macos_app.py`, `build/verify_macos_app.py`, `build/verify_package.py`, `build/qa_packaged_desktop.py`, `web/index.html`, `deploy/verify_release_files.py`

Previously, the root version file, API version, desktop application name and web cache parameters still used old release identifiers. Renaming the ZIP alone could leave browsers requesting the same cached assets and gave deployment checks no reliable indication of the installed version. The version-character allowlist in `make_release.py` also omitted the period, so it rejected `v1.0.1` outright.

The product version is now `v1.0.1` in `VERSION`, the FastAPI application, desktop `APP_VERSION`, the web page's `data-build` attribute and footer, JS/CSS version parameters, and the expected values used by build scripts, deployment checks and regression tests. The server packager accepts periods in version strings while continuing to reject path separators and other invalid characters. Referenced module filenames such as those containing `oct30` remain in place; their cache parameters use the current product version.

The macOS numeric fields `CFBundleVersion` and `CFBundleShortVersionString` contain `1.0.1`. The full product label, `v1.0.1`, is stored separately in `RestaurantReleaseVersion` and used in the application name. `bundle_version()` accepts only a three-part numeric version with an optional leading `v`, preventing arbitrary build labels from being written into these numeric fields.

The desktop main program was recompiled with CPython 3.12 and replaced in both the arm64 and x86_64 executable slices, retaining the bundled Python, Qt and other dependencies. The builder renews the signatures. The verifier recursively compares the embedded main code objects with the delivered source and checks runtime files, permissions, links and architectures. All 190 Mach-O components contained both architectures; the runtime requires macOS 15 or later. The app is ad-hoc signed and has not been notarized by Apple.

The server archive's 55 files were hashed with SHA-256 and compared with the delivered source. Its extracted API and web assets were run in an isolated environment, where checks compared 48 runtime files, requested 32 pages or assets, and checked the health endpoint and OpenAPI version. The complete ZIP was also checked for CRC errors, extracted again, and compared for file content, permissions and symbolic links; the extracted app's signature was checked again. The production app and the separate offline QA app are kept distinct. QA uses synthetic workbooks, and its test harness is not installed as the production entry point.

### Test results

The following checks were completed for the v1.0.1 release.

| Check | Result |
| --- | --- |
| Full backend suite | 148 tests and 15 subtests passed; the logs retain four existing warnings |
| Web business regressions | 25 groups passed, along with three existing regression scripts |
| Web exact-money calculations | 232 checks passed |
| Cross-client FIFO calculations | 77 fixtures and 1,020 checks passed |
| Desktop methods and Excel I/O | 12 tests passed |
| Desktop Qt regressions | 10 tests passed |
| Packaged app | Passed on arm64 and x86_64 through Rosetta; each architecture constructed and switched among 12 interface modules in Qt offscreen mode and ran the desktop regressions |
| Report text layout | 20 combinations of Chinese/English, five widths and normal/enlarged text passed |
| Generated web files | All 13 business scripts rebuilt byte-for-byte from source |

Backend tests primarily use isolated SQLite, and app tests use synthetic Excel files with networking disabled. These results do not include production PostgreSQL concurrency stress, merchant-network integration, separate Intel hardware or long-running multi-device tests. Command output, failing controls and verification reports are included in the ZIP under `测试与构建核验/`.

### Existing data and upgrades

Fixing detail deletion does not remove amounts already saved in older records. A nonzero amount with empty details may also be a valid early-format entry, so those records must not be cleared in bulk. Check each suspected historical remnant and follow the targeted correction instructions in the package. This update did not modify real workbooks or deploy the production server.

Upgrade the server, web application and desktop clients together to avoid older clients converting structured details back into lossy text. Internal backups now retain source ordering. Ordering that was never saved in an old backup cannot be reconstructed automatically; take a new backup after upgrading. The packaged desktop app requires macOS 15 or later.

The previous source remains on `old/v1.0.0`. GitHub `main` contains source, tests, build and deployment tools, example configuration and documentation. The complete app, server archive and local verification records are distributed in the ZIP.
