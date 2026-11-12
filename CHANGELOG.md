# Changelog

**[← Back to the English README](README.en.md)** · [中文更新日志](<CHANGELOG (中文).md>)

## Versions

- [2026 Nov 10 V1.0.2](#2026-nov-10-v102) — Daily and month-end profit forecasts, dashboard charts and cash adjustments
- [2026 Nov 07 V1.0.1](#2026-nov-07-v101) — Fixes to saved entries, stock values, cash balances and synchronization
- [2026 Oct 30 V1.0.0](#2026-oct-30-v100) — First archived version

## 2026 Nov 10 V1.0.2

### Read the five dashboard figures

| From left to right | What the figure shows |
| --- | --- |
| Average daily revenue | Revenue recorded through yesterday, divided by the calendar days elapsed through yesterday. |
| Average daily gross profit (Margin) | Gross profit over the same days, shown alongside the gross margin. |
| Estimated month-end profit/loss | Projected revenue for the whole month less projected costs. The second line reads **(based on this month’s projected costs and revenue)** while the month is open. |
| Estimated daily profit/loss this month | The second line reads **(Estimated month-end profit/loss ÷ days in the month)**. The calculation uses the third card’s unrounded result and displays CNY per day. |
| Net profit (Margin) | Actual revenue and expenses recorded through today, including the whole month’s saved fixed expenses. Net margin is actual net profit divided by actual revenue. |

Each card compares its figure with the previous month. For daily profit or loss, each month uses its own calendar length. Once a month ends, the third card shows actual net profit and the fourth shows that profit per calendar day. The full monthly report also lists actual average daily net profit. During the month it divides actual net profit by the days elapsed through yesterday.

### How the month-end forecast works

The dashboard and the full monthly report use the same calculation. Projected revenue equals average daily revenue through yesterday multiplied by the number of calendar days in the month. Three costs are deducted from it.

| Cost | Amount used in the forecast |
| --- | --- |
| Fixed expenses | The higher of last month’s actual fixed expenses and this month’s saved fixed expenses. Until this month’s amount is saved, the forecast uses last month’s. |
| Ingredients and seasonings | The higher of the two months’ daily ingredient costs, multiplied by the number of days in this month. Seasonings count as ingredients. |
| Other costs | For each month, take total costs less ingredients, seasonings and fixed expenses. Use the higher daily rate and multiply it by the number of days in this month. |

- **When today’s entries count.** A purchase or expense dated today can change the forecast as soon as it is saved. Today’s revenue enters tomorrow. Last month’s daily rates use all its calendar days. This month’s use the calendar days elapsed through yesterday, including dates with no entries.
- **When a figure appears.** The forecast needs at least one operating record through yesterday this month and daily records or saved monthly costs for last month. A recorded zero counts. On the first of the month the forecast shows a dash. At local midnight on the first of the following month, the report switches the completed month to actuals. Later corrections update those actuals.
- **Where to check the figures.** Hover over or tap **ⓘ** beside either estimate to see both months’ figures and which one was used for each cost. The final three lines give projected average daily total cost, projected total cost and projected revenue. The daily total uses the full length of the month. Completed months show the actual equivalents. Saving or syncing the same ledger keeps the selected month, and the open explanation updates with it, including in Advanced analytics.
- **When the forecast shows a loss.** If the gross margin is positive, the full report also gives the extra daily revenue needed to break even.

### Charts and expense details

- The daily trend and weekday charts both open on revenue. Each has its own selector for revenue, gross profit, net profit or ingredient costs including seasonings. Weekday averages use dates with entries for that weekday.
- Each cost category has its own color in the ring chart and the matching legend. On phones, the total and its currency unit are centered inside the ring.
- The operating, expense and customer views show the period, days with records and comparison with last month. Open the detail table to check the largest expense category, profitable days, the difference between monthly fixed totals and itemized payments, or the day with the most customers.
- Switch trends between lines and bars to inspect individual values, the average, the range and the number of observations. Charts adjust their labels to the available width and support mouse, touch and keyboard. You can sort and filter the whole detail table. Its totals and CSV export cover the full filtered selection. On desktop you can see the active filters, collapse the details and still export them.

### Cash, language and deployment

- To reconcile a cash count, open the cash sheet, choose **Add cash entry → Balance override**, and enter the counted balance for the date. This adjusts cash only. Earlier transactions and locks on older entries are preserved.
- English browser mode covers forms, reports, charts, dialogs, errors and audit summaries. Names and notes entered by users keep their original spelling. Amounts are in CNY. The native macOS app uses Chinese.
- This release uses browser build `20261112-daily-pl` and application/API version `v1.0.2`. The deployment check verifies the browser build, asset URLs and file hashes. [Deployment guide](docs/DEPLOYMENT.md) · [Engineering reference](docs/ENGINEERING_REFERENCE.md)

## 2026 Nov 07 V1.0.1

### Recording purchases and correcting old entries

- Deleting the last ingredient, seasoning or other-expense detail clears its total. Opening and saving an older amount-only record preserves its original amount.
- Two purchases with the same item name keep their separate quantities, units and prices. Moving checked rows moves only those rows. Purchase details retain notes and punctuation, distinguish a missing price from zero, and calculate a missing total from the quantity and unit price.
- Editing one day in an older multi-day record preserves dishes and expenses for the other dates. A day with no dishes opens empty. Switching ledgers during a save or refresh keeps each record in the right ledger. The cash sheet refreshes after a save and ignores older responses.
- Purchase and consumption charts group items by name and unit. The inventory drawer shows the remaining booked value of each first-in, first-out (FIFO) lot to the cent. Long forecast labels wrap in the full report.

### Cash, permissions and internal backups

- Temporary editing permission applies only to the authorized dates. Revenue and expense totals follow the deadlines on their entries, including after an old record is converted. The general API and sync endpoints enforce role restrictions on cash records.
- Migrating cash records saved under older names checks their versions. If several records cover one business date, the cash total counts it once. Internal Excel backups now retain the order used to choose the record for that date.

### Desktop fixes and upgrading

- Edits made during an upload stay queued for the next sync. Cash balances include movements across years in the same ledger. A stale cash window or ledger form now detects a conflict before it can overwrite another device’s changes.
- Weekly totals include fixed expenses on closed days. Monthly and annual reports include months with only fixed expenses. Older entries with only a revenue total count toward cash. An explicitly recorded zero keeps its value.
- Before replacing an internal workbook, the app checks Excel’s cell limits, JSON records and their hashes. When recovering from an annual workbook, it also retrieves the ledger’s cloud records for other years.
- The API, browser, server archive and macOS app share the same version label. Release checks covered 148 backend tests plus 15 subtests, 232 web money checks and 1,020 FIFO checks. The packaged app ran on Apple Silicon and in Intel mode through Rosetta. It requires macOS 15 or later.

**Upgrading from V1.0.0.** Update the server and clients together, then save a new internal backup to capture the record order. Review historical expenses with empty details individually. Some were entered with an amount only. [Original V1.0.1 fixes and test notes](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/blob/9ab90f8c546c33ebe5443fe57dbcc775148474e7/CHANGELOG.md)

## 2026 Oct 30 V1.0.0

The first version recorded daily sales, purchases and ingredients used in dishes. It tracked stock and cash, produced operating reports, and imported and exported Excel workbooks. The browser, API and desktop app called this build `Oct30LingChen`. It is archived under V1.0.0. [V1.0.0 source](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/tree/old/v1.0.0)
