# Data guide

This guide explains, analysis by analysis, exactly what data the app needs, what it should look like, and where to find a working example. It is written for people who are comfortable with spreadsheets, not programming.

**The short version:** put your data in a spreadsheet with clear column names in the first row, one record per row, and upload it. The app suggests which column plays which role and lets you correct every suggestion before anything runs.

## Supported file formats

The app reads **`.xlsx`**, **`.xls`**, **`.xlsm`**, **`.csv`**, and **`.json`** files. It never changes your uploaded file — results are always separate downloads.

- **Excel** (`.xlsx`, `.xls`, `.xlsm`): a workbook may contain several sheets; each sheet becomes a separate table you can pick from a dropdown.
- **CSV** (`.csv`): one table.
- **JSON** (`.json`): either a **list of records** — `[{"customer_id": "C001", "amount": 120}, …]` — which becomes one table, or an **object whose keys map to lists of records** — `{"transactions": […], "equity": […]}` — which becomes one table per key (the JSON equivalent of an Excel workbook with named sheets).

## Column names are flexible

You do not need to rename your columns to match this guide. The app recognizes many common names (for example `customer`, `client_id`, and `user_id` are all understood as a customer identifier; `revenue`, `sales`, and `order_value` as an amount) and pre-selects the most likely column for each role. Always glance at the suggestions and correct any that are wrong — the dropdowns list every column in your table.

## Templates and example files

- Every analysis page that reads a file has a **"What data do I need?"** section with **Download template** buttons that give you a pre-formatted file with the right columns — fill it with your own data and upload it back. (CLV, budgets, and Markov ROI need no file; their inputs are typed directly into the page.)
- **`examples/quick_test.xlsx`** — a small ready-made file for a first test drive.
- **`examples/example_data.xlsx`** and **`examples/example_data.json`** — fuller multi-table examples with one sheet/table per analysis: `transactions`, `rfm_customers`, `response_model`, `equity`, `contractual_survival`, `bgnbd_summary` (named `bgnbd` in the JSON file), `bgbb_histories`, and `events`.
- **`examples/transactions.csv`** — a raw transaction-log example.

---

## What each analysis needs

### Customer selection: RFM segmentation

**Question it answers:** which customers are your best, based on how **R**ecently they bought, how **F**requently they buy, and how much **M**oney they spend?

The app accepts two input styles.

**Style 1 — one row per customer**, with the three RFM measures already computed:

- recency: time since last purchase (lower is better)
- frequency: purchases per period (higher is better)
- monetary value: average amount per purchase (higher is better)
- optional: a customer identifier and a response column coded `0`/`1` (to see how response rates differ across segments)

| customer_id | recency_days | frequency_per_month | monetary_average | response |
|---|---|---|---|---|
| C001 | 12 | 2.5 | 84.50 | 1 |
| C002 | 210 | 0.3 | 41.00 | 0 |
| C003 | 45 | 1.1 | 130.25 | 0 |
| C004 | 7 | 3.0 | 95.10 | 1 |

*Example: sheet `rfm_customers` in `examples/example_data.xlsx`.*

**Style 2 — one row per transaction.** The app computes recency in days, purchases per month, average purchase amount, and total amount for you. You also pick the "observation date" (the day the clock stops; the app suggests the latest date in the file).

| customer_id | purchase_date | amount |
|---|---|---|
| C001 | 2025-03-14 | 120.00 |
| C001 | 2025-05-02 | 84.50 |
| C002 | 2024-11-30 | 41.00 |
| C003 | 2025-04-18 | 130.25 |

*Example: sheet `transactions` in `examples/example_data.xlsx`, or `examples/transactions.csv`.*

### Customer selection: response models and profitable targeting

**Question it answers:** which customers are likely enough to respond that contacting them is profitable?

One row per customer, with:

- a response column coded `0` (did not respond) or `1` (responded)
- one or more numeric predictor columns (anything you believe drives response: recency, frequency, spend, tenure, …)

Profit per response and cost per contact are typed directly into the page — they are not part of the file.

| customer_id | recency_days | purchases_last_year | average_amount | months_as_customer | newsletter | response |
|---|---|---|---|---|---|---|
| C001 | 12 | 8 | 84.50 | 26 | 1 | 1 |
| C002 | 210 | 1 | 41.00 | 5 | 0 | 0 |
| C003 | 45 | 3 | 130.25 | 14 | 0 | 0 |
| C004 | 7 | 11 | 95.10 | 48 | 1 | 1 |

*Example: sheet `response_model` in `examples/example_data.xlsx`.*

### Customer lifetime value (CLV)

**Question it answers:** what is one customer worth today, given margin, retention, and discounting?

**No file needed.** All inputs (margin per period, retention rate, discount rate, acquisition cost, and the horizon/growth/timing options) are typed directly into the page.

### Customer equity

**Question it answers:** what is your whole customer base worth — including the customers you will acquire in the future?

One row per time period (quarter, year, …), with:

- period: consecutive numbers starting at 0 (0, 1, 2, …)
- number of current customers in that period

At least **five rows** are needed — the acquisition curve is fitted to the period-to-period changes, so five counts give the four observations the fit requires (more history gives a much better fit). Retention, margin, discount, tax, and acquisition-cost assumptions are entered on the page.

| period | customers |
|---|---|
| 0 | 1000 |
| 1 | 1250 |
| 2 | 1810 |
| 3 | 2390 |
| 4 | 2850 |
| 5 | 3100 |

*Example: sheet `equity` in `examples/example_data.xlsx`.*

### Acquisition and retention budgets

**Question it answers:** how should you split spending between winning new customers and keeping existing ones?

**No file needed.** Current spend levels, current acquisition/retention rates, the maximum achievable rates, margin, and discount rate are all typed directly into the page.

### Markov switching ROI

**Question it answers:** if a marketing investment changes how customers switch between brands, what is the return on that investment?

**No file needed.** The before-and-after brand-switching matrices are edited in small grids directly on the page, along with purchase amount, margin, frequency, horizon, discount rate, industry size, and the investment amount.

### Contractual retention

**Question it answers:** how quickly does a cohort of subscribers melt away, and how many will be left in future periods?

One row per period, with:

- period: starting at `0` (the start of the cohort) and increasing by one
- surviving customers: how many of the original cohort are still active — this number can never increase over time

| period | survivors |
|---|---|
| 0 | 1000 |
| 1 | 872 |
| 2 | 776 |
| 3 | 703 |
| 4 | 646 |

*Example: sheet `contractual_survival` in `examples/example_data.xlsx`.*

### BG/NBD (continuous-time purchasing)

**Question it answers:** when customers can buy at any time and never tell you they've left, who is probably still active and how many purchases should you expect from each?

The app accepts two input styles.

**Style 1 — one summary row per customer:**

- `x`: number of repeat purchases (excluding the very first purchase)
- `tx`: time between the first purchase and the last repeat purchase (`0` when `x = 0`)
- `T`: time from the first purchase to the end of the observation period
- optional: a count/weight column if one row represents many customers with the same history

All three time quantities must use the same unit (weeks, days, or months).

| customer_id | x | tx | T |
|---|---|---|---|
| 1 | 2 | 30.43 | 38.86 |
| 2 | 1 | 1.71 | 38.86 |
| 3 | 0 | 0.00 | 38.86 |
| 4 | 5 | 24.30 | 38.86 |

(The optional count/weight column from the bullet list above is not in the example sheet — each of its rows is a single customer.)

*Example: sheet `bgnbd_summary` in `examples/example_data.xlsx`.*

**Style 2 — one row per transaction** with a customer ID and purchase date; the app builds `x`, `tx`, and `T` for you after you pick the time unit and observation end date.

*Example: sheet `transactions` in `examples/example_data.xlsx`.*

### BG/BB (discrete-time purchasing)

**Question it answers:** the same as BG/NBD, but for settings where each period simply records "bought" or "didn't buy" (annual donations, yearly renewals, monthly activity flags).

The app accepts two input styles.

**Style 1 — one summary row per customer (or per group of identical histories):**

- `n`: number of observed periods
- `tx`: the period of the last purchase (`0` when no repeat purchase occurred)
- `x`: number of repeat purchases
- optional: a count/weight column for aggregated identical histories

| n | tx | x | count |
|---|---|---|---|
| 6 | 6 | 6 | 1203 |
| 6 | 6 | 5 | 728 |
| 6 | 5 | 4 | 512 |
| 6 | 0 | 0 | 3464 |

*Example: sheet `bgbb_histories` in `examples/example_data.xlsx`.*

**Style 2 — one `0`/`1` column per period**, in chronological order (for example `year_1`, `year_2`, … with a `1` where the customer bought). You select the period columns in order and the app builds the summary.

### Complaints and recovery

**Question it answers:** what does the complaint-and-recovery model need to know about each customer, and how much is it worth spending to recover a complaining customer?

For the input-preparation step, one row per **event**:

- customer ID
- event date
- event type: text containing `purchase`/`order` or `complaint`

| customer_id | event_date | event_type |
|---|---|---|
| C001 | 2025-01-05 | purchase |
| C001 | 2025-01-05 | complaint |
| C001 | 2025-02-11 | purchase |
| C002 | 2025-01-20 | order |
| C002 | 2025-03-02 | complaint |

The app builds the six per-customer summary statistics the model requires: repeat purchases, same-day complaints, other complaints, last-event time, last-event type, and observation length.

*Example: sheet `events` in `examples/example_data.xlsx`.*

The recovery-value calculator on the same page needs **no file** — future value and stay probabilities are typed directly into the page.

---

## Common problems (and how to fix them)

**Numbers stored as text.** Spreadsheets sometimes hold `"1 250"` or `"84,50"` as text instead of numbers. The app converts what it can, but values it cannot read become missing. Fix: in Excel, select the column and set its format to Number, or use *Data → Text to Columns*; watch for the little green triangles Excel shows on text-formatted numbers.

**Merged or multi-row headers.** The first row of each sheet must contain the column names — nothing else. Merged title cells, a logo row, or two stacked header rows will make the app read your headers as data (you'll see columns named `Unnamed: 1` or your title text in the data check). Fix: delete decorative rows so row 1 is the header, and unmerge any merged header cells.

**Date formats.** Unambiguous formats like `2025-03-14` always work. Ambiguous ones like `03/04/2025` may be read as March 4 or April 3 depending on convention. If dates matter (RFM from transactions, BG/NBD, complaints), prefer `YYYY-MM-DD` or true Excel date cells.

**Thousands separators and decimal commas.** `1,250` may be read as one thousand two hundred fifty or as 1.25 depending on locale, and `84,50` (comma as decimal) is often read as text. Fix: store plain numbers without separators, using a dot as the decimal mark, or use real numeric cells in Excel.

**Empty rows.** Blank rows inside the data become rows of missing values, and rows missing key values are dropped from the calculation. Harmless in small numbers, but if results look thin, check the data-check page — it shows the missing-value percentage for every column.

**Multiple sheets.** When a workbook has several sheets, the app asks which one to use for each analysis. If the columns you expect aren't in the dropdowns, you are probably on the wrong sheet.

**Error messages.** The app fails politely rather than silently: problems appear in a red box on the page explaining what went wrong (for example an unsupported file type — `Supported files are .xlsx, .xls, .xlsm, .json, and .csv.` — a column that isn't numeric, a survivor count that increases over time, or too few rows to fit a model). The **Start & data check** page shows every column's type, missing-value share, and an example value, which resolves most puzzles quickly.
