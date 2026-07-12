# Customer Value Analytics

Customer Value Analytics is a free, open-source app that turns a customer data file (Excel, CSV, or JSON) into the classic customer-value analyses — segmentation, lifetime value, retention, and marketing ROI — through a point-and-click interface. Upload a file, confirm the column suggestions, press a button, and download the results as Excel or JSON. The app runs entirely on your own computer: your data never leaves your machine.

## Read this first

> **Two honest warnings before you trust any number this app produces.**
>
> John Wanamaker famously said that half the money he spent on advertising was wasted — the trouble was he didn't know which half. More than a century later that is still largely true: a practical rule of thumb is that only roughly 30% of marketing activities can be meaningfully measured.
>
> The models in this app are useful precisely because they bring structure to that uncertainty. But every output is an estimate built on assumptions. Treat each number as **decision support, not truth**: use it to compare options, challenge gut feelings, and frame discussions — not as a precise prediction of the future.

## Get the app

You need the project folder on your computer first. Two ways — pick one:

- **No tools needed (easiest):** on the project's GitHub page, click the green **Code** button → **Download ZIP**. Unzip it anywhere (for example your Desktop) and open the unzipped folder.
- **With git:**

  ```bash
  git clone https://github.com/UlrikErlingsen/customer-value-analytics.git
  ```

You also need **Python 3.10 or newer** — many computers already have it. If not, install it free from [python.org/downloads](https://www.python.org/downloads/). **On Windows, tick the "Add python.exe to PATH" checkbox during installation** — it matters.

## Quick start

**Windows**

1. In the project folder, double-click `run_app.bat`.
2. The first start creates a local `.venv` folder and installs everything the app needs (a few minutes). Later starts skip this.
3. A browser tab opens with the app.

If Windows shows a protection warning for a downloaded file, click **More info → Run anyway**.

**Mac**

1. In the project folder, double-click `run_app.command`.
2. The first start installs everything into a local `.venv` folder. Later starts skip this.
3. A browser tab opens with the app.

If macOS blocks the first double-click, right-click `run_app.command`, choose **Open**, then confirm.

**Any operating system (terminal)**

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

(Use `python3` instead of `python` if that is what your system calls it.)

**Docker**

A `Dockerfile` is included at the repository root:

```bash
docker build -t cva . && docker run -p 8501:8501 cva
```

Then open http://localhost:8501.

**Deploying for your team**

This is a standard Streamlit app, so it can be deployed on [Streamlit Community Cloud](https://streamlit.io/cloud) straight from a GitHub repository (private repositories work too) — just point the deployment at `app.py`.

## Try it in two minutes

1. Start the app and upload `examples/quick_test.xlsx` — a small, ready-made file that works with the data-driven analyses out of the box.
2. Pick an analysis in the sidebar, keep the suggested column mappings, and press the run button.

For fuller examples, `examples/example_data.xlsx` and `examples/example_data.json` contain one table per analysis, and `examples/transactions.csv` is a raw transaction-log example. Every analysis page that reads a file also has a **"What data do I need?"** section with **Download template** buttons that give you a pre-formatted file to fill with your own data. (Three analyses — CLV, budgets, and Markov ROI — need no file at all; you type your assumptions directly.)

## What it can do

Nine analysis areas, each answering a concrete business question:

1. **Customer selection and profitable targeting** — *Which customers should get the next campaign?* RFM segmentation using the classic direct-marketing nested-quintile scoring (score 1 = best), logistic-regression and decision-tree response models, a profit-based targeting rule, and lift charts.
2. **Customer lifetime value (CLV)** — *What is a customer worth today?* Infinite-horizon, finite-horizon, growing-margin, and custom-timing variants of the margin-multiple approach (Gupta & Lehmann 2003, "Customers as Assets").
3. **Customer equity and elasticities** — *What is the whole customer base worth, including customers you haven't acquired yet?* Fits an acquisition curve, forecasts future customers, applies tax, and reports annual elasticities (Gupta, Lehmann & Stuart 2004, "Valuing Customers").
4. **Acquisition and retention budgets** — *How much should you spend on winning new customers versus keeping the ones you have?* Optimizes both budgets against the customer-equity test (Blattberg & Deighton 1996, "Manage Marketing by the Customer Equity Test").
5. **Markov switching ROI** — *Does a marketing investment that shifts brand-switching behavior actually pay off?* Turns before/after brand-switching matrices into CLV, customer equity, and ROI (Rust, Lemon & Zeithaml 2004, "Return on Marketing").
6. **Contractual retention** — *How many of your subscribers will still be with you in a year? In five?* Fits the shifted beta-geometric survival model and forecasts retention (Fader & Hardie 2007, "How to Project Customer Retention").
7. **BG/NBD customer-base analysis** — *When customers can buy at any time, who is still active and how many purchases should you expect?* Maximum-likelihood estimation and per-customer scoring (Fader, Hardie & Lee 2005, "Counting Your Customers the Easy Way").
8. **BG/BB customer-base analysis** — *Same question when activity is recorded period by period (bought / didn't buy).* Maximum-likelihood estimation and per-customer scoring (Fader, Hardie & Shang 2010, "Customer-Base Analysis in a Discrete-Time Noncontractual Setting").
9. **Complaints and recovery** — *What is it worth to win back a complaining customer?* Prepares the customer summaries needed by the complaint-and-recovery customer-base model (Knox & van Oest 2014, "Customer Complaints and Recovery Effectiveness") and values recovery spending as the CLV difference between a recovered and an unrecovered customer.

A practical rule for choosing among the retention models: in a **contractual** setting the firm knows when a customer leaves; in a **non-contractual** setting inactivity is hidden and must be inferred. With **continuous** time purchases can happen at any moment (BG/NBD); with **discrete** time each period records purchase / no purchase (BG/BB).

## Data formats

The app reads `.xlsx`, `.xls`, `.xlsm`, `.csv`, and `.json`, suggests which columns to use, and lets you correct every mapping. It never modifies your uploaded file. See **[docs/data_guide.md](docs/data_guide.md)** for exactly what each analysis needs, with example tables and troubleshooting tips.

## Methods and accuracy

Every formula and convention the app uses is documented in **[docs/methods.md](docs/methods.md)**, with citations to the original papers. An automated test suite reproduces published and reference examples to check the implementations:

```bash
python3 -m pytest
```

## About this project

This app was built with AI assistance and reviewed against the published models it implements. The methods are classic, deliberately simple models — chosen because they are transparent, well-documented, and easy to sanity-check. More advanced statistical approaches exist for every one of these problems and are beyond this app's scope.

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GPL-3.0-or-later. In plain words:

- **Anyone — including companies — may use, study, and modify this software freely.** Changes kept for internal use never have to be published.
- **What may not happen:** taking this project, closing the source, and selling it as a proprietary product. Anyone who *distributes* the software — original or modified, paid or free — must pass on the same source code and the same freedoms they received.

That combination is deliberate: this should be a project everyone can benefit from and improve, and that nobody can take away. The full legal text is in [LICENSE](LICENSE).
