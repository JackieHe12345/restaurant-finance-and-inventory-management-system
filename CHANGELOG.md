# CHANGELOG

**[← Back to the English README](README.en.md)** · [中文更新日志](<CHANGELOG (中文).md>)

## Versions

- [2026 Nov 10 V1.0.2](#2026-nov-10-v102) — Profit forecasts, expense analysis, and cash reconciliation
- [2026 Nov 07 V1.0.1](#2026-nov-07-v101) — Corrections to ledger entries, inventory values, cash balances, and synchronization
- [2026 Oct 30 V1.0.0](#2026-oct-30-v100) — First archived release

## 2026 Nov 10 V1.0.2

### Dashboard and monthly report

The dashboard displays five figures for the selected month. Each card includes a comparison with the previous month.

| Dashboard card, from left to right | Calculation for the current month |
| --- | --- |
| Average daily revenue | Revenue from the first of the month through yesterday divided by the number of calendar days in that period. |
| Average daily gross profit (Margin) | Gross profit through yesterday divided by the same number of days, with the gross margin for that period. |
| Estimated month-end profit/loss | Projected revenue less projected costs for the whole month. The caption reads **(based on this month’s projected costs and revenue)**. |
| Estimated daily profit/loss this month | The unrounded month-end estimate divided by the number of calendar days in the month, expressed in CNY per day. The caption reads **(Estimated month-end profit/loss ÷ days in the month)**. |
| Net profit (Margin) | Actual revenue less expenses through today, including the fixed expenses saved for the whole month. Net margin is actual net profit divided by actual revenue. |

The month-over-month comparison for estimated daily profit/loss uses each month’s own day count. The full monthly report also shows actual average daily net profit, calculated from actual net profit to date and the calendar days elapsed through yesterday. If the forecast shows a loss and the gross margin is positive, the report gives the additional daily revenue required to break even.

### Month-end forecast

The dashboard and the full monthly report use the same forecast. Average daily revenue through yesterday, multiplied by the number of days in the month, gives projected revenue. The forecast deducts the following costs. Each category is evaluated independently.

| Projected cost | Calculation |
| --- | --- |
| Fixed expenses | Take the higher of last month’s actual fixed expenses and this month’s saved fixed expenses. Use last month’s amount until a figure has been saved for this month. |
| Ingredients, including seasonings | Compare the two months’ daily ingredient costs. Multiply the higher daily rate by the number of days in the current month. |
| Other costs | For each month, subtract ingredient costs (including seasonings) and fixed expenses from total costs. Compare the resulting daily rates and multiply the higher rate by the number of days in the current month. |

A purchase or expense dated today can change projected costs as soon as it is saved. Today’s revenue enters the forecast tomorrow. Last month’s daily rates use its full calendar month. This month’s rates use the days elapsed through yesterday, including dates with no entries.

The forecast requires at least one daily operating record in the current month through yesterday and either a daily record or a saved monthly cost record for last month. A recorded zero is valid. A dash indicates that the available records are insufficient or that the month has just begun. At local midnight on the first of the following month, the estimate for the completed month changes to actual net profit. The daily figure becomes actual net profit divided by the length of that month. Subsequent ledger corrections update both figures.

The **ⓘ** beside the estimate shows each cost for both months and identifies the amount used. Its last three lines show projected average daily total cost, projected total cost, and projected revenue. Average daily total cost uses the full length of the month. For a completed month, the same lines show actual costs and revenue. Saving or syncing the ledger preserves the selected month and refreshes the figures in the open explanation, including in Advanced analytics.

### Charts and expense analysis

- The daily trend and weekday averages default to revenue. Each chart can independently display revenue, gross profit, net profit, or ingredient costs including seasonings. Weekday averages use only recorded dates for each weekday.
- The cost breakdown uses a distinct color for each category across the ring chart and its legend. On phones, the total and currency unit are centered inside the ring.
- Operating, expense, and customer statistics show the reporting period, the number of days with records, and the comparison with last month. The detail table identifies the largest expense category, dates with a profit, differences between monthly fixed expenses and itemized payments, and the busiest day by customer count.
- Line and bar charts show individual values, the average, the range, and the observation count. Labels adjust to screen width, and values can be inspected by mouse, touch, or keyboard. Sorting and filtering apply to the entire detail table. Totals and CSV exports include all matching rows, even when the desktop detail table is collapsed. Active filters remain visible on desktop.

### Cash reconciliation, language support, and deployment

- **Add cash entry → Balance override** on the cash sheet sets the balance for a selected date to the amount counted. This adjustment affects cash only. Earlier transactions and their editing restrictions remain in effect.
- The English web interface covers forms, reports, charts, dialogs, errors, and audit summaries. User-entered names and notes retain their original wording. Amounts are in CNY. The native macOS app uses Chinese.
- The application and API report `v1.0.2`. The browser build is `20261112-daily-pl`. Deployment verification checks this build identifier, the asset URLs, and the file hashes. [Deployment Guide](docs/DEPLOYMENT.md) · [Engineering Reference](docs/ENGINEERING_REFERENCE.md)

## 2026 Nov 07 V1.0.1

### Ledger entries, purchases, and reports

- Deleting the last line in an ingredient, seasoning, or other-expense entry clears the corresponding total. Opening and saving an older entry that contains only an amount preserves that amount.
- Separate purchases with the same item name retain their own quantities, units, and prices. Moving selected lines moves only those lines. Purchase details preserve notes and punctuation, distinguish a missing price from a zero price, and calculate a missing total when both quantity and unit price are available.
- Editing a single day in an older multi-day record preserves the other days’ dishes and expenses. A date without dish entries opens with an empty dish list. Switching ledgers during a save or refresh keeps each update with the correct ledger. The cash sheet refreshes after a save and discards older responses.
- Purchase and consumption charts group items by name and unit. Inventory details show the remaining book value of each first-in, first-out (FIFO) lot to the cent. Long forecast labels wrap in the full report.

### Cash records, permissions, and internal backups

- Temporary editing access applies to the authorized business dates. Revenue and expense totals inherit their entries’ editing deadlines, including after an older record is converted. The general API and synchronization endpoints enforce the same role restrictions as the cash sheet.
- The system checks record versions when migrating cash records saved under older names. When several records cover the same business date, that date is counted once in cash totals. Internal Excel backups preserve which record takes precedence on restore.

### Desktop and upgrade notes

- Edits made during an upload remain queued for the next sync. Cash balances include transactions across calendar years within the same ledger. A cash window or ledger form opened before a change on another device detects the conflict before saving.
- Weekly totals include fixed expenses on days the restaurant was closed. Monthly and annual reports include months with only fixed expenses. Cash totals include older entries that contain only a revenue total and preserve explicitly recorded zeros.
- Before replacing an internal workbook, the desktop app checks Excel cell limits, JSON records, and record hashes. Recovery from an annual workbook also retrieves cloud records for the ledger’s other years.
- The API, web app, server archive, and macOS app use the same version label. Release verification covered 148 backend tests with 15 additional subtests, 232 web monetary calculation checks, and 1,020 FIFO checks. The packaged app was tested on Apple Silicon both natively and under Rosetta in Intel mode. It requires macOS 15 or later.

**Upgrade from V1.0.0.** Update the server and clients together, then create a new internal backup to preserve record precedence. Review historical expenses with empty detail lines individually. Some older entries legitimately contain only an amount. [V1.0.1 fixes and test results](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/blob/9ab90f8c546c33ebe5443fe57dbcc775148474e7/CHANGELOG.md)

## 2026 Oct 30 V1.0.0

The first release supported daily sales, purchasing, ingredient consumption by dish, inventory, cash balances, operating reports, and Excel import and export. The web app, API, and desktop app identified the build as `Oct30LingChen`. The source is archived as V1.0.0. [V1.0.0 source](https://github.com/JackieHe12345/restaurant-finance-and-inventory-management-system/tree/old/v1.0.0)
