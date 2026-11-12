# Changelog

[简体中文](<CHANGELOG (中文).md>)

## Versions

- [2026 Nov 10 V1.0.2](#2026-nov-10-v102)
- [2026 Nov 07 V1.0.1](#2026-nov-07-v101)
- [2026 Oct 30 V1.0.0](#2026-oct-30-v100)

## 2026 Nov 10 V1.0.2

### Month-end profit or loss

The dashboard and full monthly report show the same estimate. Projected revenue equals average daily revenue through yesterday multiplied by the number of calendar days in this month. The report subtracts three projected costs from that revenue.

| Cost | How the report estimates this month |
| --- | --- |
| Fixed expenses | Use the higher of last month’s and this month’s saved whole-month fixed expenses. If this month has no saved fixed expenses, use last month’s figure. |
| Ingredients, including seasonings | Compare the two months’ daily ingredient costs. Multiply the higher daily rate by the number of days in this month. |
| Other costs | For each month, subtract ingredients (including seasonings) and fixed expenses from total cost. Compare the two daily rates and multiply the higher one by the number of days in this month. |

Saving a purchase, seasoning or other expense dated today immediately updates the cost comparison. Today’s revenue enters the projection tomorrow. Last month’s daily rates use its full calendar month. This month divides by the days elapsed through yesterday, including days with no entries. The estimate is unavailable on the first day of the month, when the current month has no operating records through yesterday, or when the previous month has no cost basis. A recorded zero is valid. From the first day of the next month, both views show that month’s actual net profit, including across December and January. The figure updates if the ledger is corrected later.

Both views label the figure **Estimated month-end profit/loss** with **(based on this month’s projected costs and revenue)** on the next line. Saving or syncing the same book keeps the selected reporting month. Open **i** in either view to see both months’ fixed costs and daily ingredient and other costs, the amount used and which month supplied it. Three final lines show projected average daily total cost, projected total cost and projected revenue. Daily total cost uses the full length of the month. Completed months show actual amounts. The explanation follows the selected language and refreshes its amounts while open, including in Advanced analytics.

### Dashboard and reports

- The five dashboard cards show average daily revenue, average daily gross profit with margin, estimated month-end profit/loss, **Estimated daily profit/loss this month**, and actual net profit with margin. The fourth card’s second line reads **(Estimated month-end profit/loss ÷ days in the month)**. Its amount uses the unrounded third-card result divided by all calendar days in the selected month, displayed in CNY per day. For a completed month, it uses actual net profit divided by that month’s length. Its comparison uses each month’s own daily amount.
- Daily revenue and gross-profit averages use records through yesterday. The fifth card includes today’s entries and the whole month’s saved fixed expenses. Its net margin uses actual revenue through today. The full monthly report also gives actual average daily net profit on an elapsed-day basis and, for a projected loss with a positive gross margin, the extra daily revenue needed to break even.
- The daily trend and weekday averages open on revenue. Each chart has its own selector for revenue, gross profit, net profit or ingredient costs including seasonings. Weekday averages count only dates with records.
- The cost breakdown ring uses a distinct color for each category, with matching legend markers. On phones the total and its currency unit are centered inside the ring.
- Operating, expense and customer statistics show the selected period, how many days have records and the previous-month comparison. Users can trace the largest expense category, profitable recorded days, differences between saved and itemized fixed expenses, and the busiest customer day back to the source records.
- Trends switch between lines and bars and show the mean, range and number of observations. Sorting and filtering apply to the entire detail table, its totals and the CSV export. Charts adapt to the screen width and expose exact values by mouse, touch or keyboard. On desktop, the statistics window shows the active filters, folds away detail sections and exports the current selection even when its table is hidden.

### Language, cash and distribution

- English browser mode covers forms, reports, charts, dialogs, errors and audit summaries. Book names, dish names, notes and other user-entered text keep their original wording. Currency remains CNY. The native app uses Chinese.
- On the cash sheet, **Add an item → Force balance adjustment** sets the actual balance on a selected date. The adjustment changes the cash balance without adding operating revenue or expense. Earlier transactions stay in the ledger, and historically locked entries keep their protection.
- The browser build is `20261112-daily-pl`. The application and API version is v1.0.2. Deployment verification checks the browser revision, asset URLs and file hashes. [Deployment guide](docs/DEPLOYMENT.md) · [Engineering reference and formulas](docs/ENGINEERING_REFERENCE.md)

## 2026 Nov 07 V1.0.1

### Ledger, purchases and reports

- Clearing the last ingredient, seasoning or other-expense detail now clears its total. A historical entry containing only an amount keeps that amount when opened and saved unchanged. Separate purchases of an item with the same name keep their individual quantities, units and prices. Moving selected rows moves only those checked. (A001, W002, W003)
- Editing one day in an older multi-day record preserves the other days’ dishes and expenses. A day without dish entries opens empty. Switching books while saving or refreshing keeps the result attached to the correct book. The cash sheet updates after a save and discards stale responses. (W004–W006)
- Purchase and consumption charts group items by name and unit. The inventory drawer shows each FIFO lot’s booked remaining value down to the cent. Structured purchase details preserve notes and punctuation, distinguish an unknown price from zero and calculate a missing total when both quantity and unit price are known. Long forecast labels wrap in the full report. (W007–W009, UI001)

### Cash, permissions and backups

- Temporary editing permission applies to its authorized dates. Expense and revenue totals follow the same deadlines as their source entries, including after a format conversion. Generic API reads and synchronization now enforce the cash sheet’s role restrictions. (B01–B03)
- Cash records saved under older names migrate with version checks. Overlapping entries for one business date count once in cash totals. New internal Excel backups preserve which overlapping entry takes precedence when restored. (B04, B05, B07)

### Desktop and upgrades

- Edits made during an upload stay queued for the next sync. Cash balances include movements across years in the same book. A stale cash window or ledger form detects a conflicting update before it can overwrite another device’s work. (D001–D003, D008)
- Weekly totals include fixed costs on closed days. Monthly and annual reports include months with only fixed costs. Older total-only revenue entries count toward cash, and an explicitly recorded zero retains its value. (D004, D005)
- The desktop app checks Excel cell limits, JSON and hashes before replacing an internal workbook. During recovery from an annual workbook it retrieves the cloud records for the book, including other years. (D006, D007)
- Version labels were aligned across the API, browser, server archive and macOS app. The release checks covered 148 backend tests and 15 subtests, 232 web money checks, 1,020 FIFO checks and the packaged app on arm64 and x86_64 through Rosetta. The packaged desktop app requires macOS 15 or later. (BUILD001)

When upgrading from the original build, update all clients together and create a fresh internal backup so it includes source order. Review historical expenses with empty details individually, as some older entries legitimately contain only an amount. [Full V1.0.1 change and test notes](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/blob/9ab90f8c546c33ebe5443fe57dbcc775148474e7/CHANGELOG.md)

## 2026 Oct 30 V1.0.0

The original build, labeled `Oct30LingChen` in the browser, API and desktop app, is archived as V1.0.0. It provided daily restaurant bookkeeping, purchasing and dish consumption, inventory, cash tracking, operating reports and Excel exchange. October 30 identifies the original build. [Archived V1.0.0 source](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/tree/old/v1.0.0)
