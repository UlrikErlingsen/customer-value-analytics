from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from cva.bgbb import score_bgbb, summary_from_binary_periods
from cva.bgnbd import score_bgnbd, summarize_transactions
from cva.clv import finite_horizon_clv, growth_clv, summarize_clv, timed_clv
from cva.complaints import complaint_summary, recovery_value
from cva.contractual import contractual_forecast
from cva.equity import annual_elasticities, customer_equity
from cva.investment import optimize_budgets
from cva.io import LoadedData, load_data, profile_table, results_to_excel, results_to_json
from cva.markov import markov_clv, markov_roi
from cva.schema import normalize_name, suggest_column
from cva.selection import (
    fit_decision_tree,
    fit_logistic,
    lift_table,
    rfm_from_transactions,
    rfm_scores,
    targeting_profit,
)
from cva.templates import TEMPLATES, template_csv, template_workbook
from cva.validation import (
    DataProblem,
    binary_series,
    date_series,
    friendly_message,
    numeric_series,
    require_distinct,
    skipped_rows_note,
)

MEASUREMENT_WARNING = (
    "**Before you trust any number here:** marketing measurement is hard. John Wanamaker's "
    "century-old line still applies — “Half the money I spend on advertising is wasted; "
    "the trouble is I don't know which half.” And as a rule of thumb, only about 30% of "
    "marketing activities can be meaningfully measured at all. Treat every result as "
    "decision support, not as truth."
)


st.set_page_config(page_title="Customer Value Analytics", page_icon="📊", layout="wide")


def fmt_number(value: float) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.2f}"


def show_error(exc: Exception) -> None:
    """Explain a failure in plain language; keep the technical details one click away."""
    st.error(friendly_message(exc))
    if not isinstance(exc, DataProblem):
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


@st.cache_data(show_spinner=False)
def cached_template_workbook(keys: tuple[str, ...] | None, small: bool) -> bytes:
    return template_workbook(list(keys) if keys else None, small=small)


@st.cache_data(show_spinner=False)
def cached_template_csv(key: str) -> bytes:
    return template_csv(key)


def data_help(keys: tuple[str, ...], page_key: str, intro: str | None = None) -> None:
    """An expander that says exactly which data the page needs, with template downloads."""
    with st.expander("What data do I need? (templates inside)"):
        if intro:
            st.write(intro)
        for key in keys:
            spec = TEMPLATES[key]
            st.markdown(f"**{spec.title}** — {spec.purpose}")
            st.markdown("\n".join(f"- `{column.name}`: {column.description}" for column in spec.columns))
            left, right = st.columns(2)
            left.download_button(
                "Download Excel template",
                data=cached_template_workbook((key,), True),
                file_name=f"template_{key}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"tmpl_xlsx_{page_key}_{key}",
            )
            right.download_button(
                "Download CSV template",
                data=cached_template_csv(key),
                file_name=f"template_{key}.csv",
                mime="text/csv",
                key=f"tmpl_csv_{page_key}_{key}",
            )
        st.caption(
            "Templates come filled with example rows — replace them with your own data and upload the file. "
            "Column names are recognised automatically, and you can always correct the mapping by hand."
        )


def latest_valid_date(frame: pd.DataFrame, column: str) -> object:
    parsed = pd.to_datetime(frame[column], errors="coerce")
    return (parsed.max() if parsed.notna().any() else pd.Timestamp.today()).date()


def column_select(label: str, frame: pd.DataFrame, role: str, key: str, allow_none: bool = False) -> str | None:
    columns = [str(column) for column in frame.columns]
    suggestion = suggest_column(columns, role)
    options = (["— none —"] if allow_none else []) + columns
    default = options.index(suggestion) if suggestion in options else 0
    selected = st.selectbox(label, options, index=default, key=key)
    return None if selected == "— none —" else selected


def render_downloads(name: str, tables: dict[str, pd.DataFrame], key: str) -> None:
    left, right = st.columns(2)
    with left:
        st.download_button(
            "Download Excel results",
            data=results_to_excel(tables),
            file_name=f"{name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"xlsx_{key}",
        )
    with right:
        st.download_button(
            "Download JSON results",
            data=results_to_json(tables),
            file_name=f"{name}.json",
            mime="application/json",
            key=f"json_{key}",
        )


def chosen_table(data: LoadedData | None, key: str, preferred: tuple[str, ...] = ()) -> pd.DataFrame | None:
    if data is None:
        st.info("Upload an Excel, CSV, or JSON file in the sidebar first.")
        return None
    names = list(data.tables)
    # Pre-select the sheet this page most likely needs; never default to a READ ME sheet.
    normalized = [normalize_name(name) for name in names]
    default = next(
        (normalized.index(normalize_name(want)) for want in preferred if normalize_name(want) in normalized),
        next((index for index, name in enumerate(normalized) if name not in {"read_me", "readme"}), 0),
    )
    table_name = st.selectbox("Data table / Excel sheet", names, index=default, key=f"table_{key}")
    frame = data.tables[table_name]
    st.caption(f"{len(frame):,} rows × {len(frame.columns):,} columns")
    with st.expander("Preview source data", expanded=False):
        st.dataframe(frame.head(100), use_container_width=True)
    return frame


@st.cache_data(show_spinner=False)
def cached_load(raw: bytes, filename: str) -> LoadedData:
    import io

    return load_data(io.BytesIO(raw), filename)


st.title("Customer Value Analytics")
st.caption("Classic customer-value models for your own Excel, CSV, or JSON data — free, open source, runs entirely on your computer")

with st.sidebar:
    st.header("1. Add your data")
    upload = st.file_uploader("Excel, CSV, or JSON", type=["xlsx", "xls", "xlsm", "json", "csv"])
    loaded: LoadedData | None = None
    if upload is not None:
        try:
            loaded = cached_load(upload.getvalue(), upload.name)
            st.success(f"Loaded {upload.name}")
        except Exception as exc:
            st.error(f"Could not read the file: {exc}")
            st.caption(
                "The file should have column names in its first row. "
                "Supported: Excel (.xlsx, .xls, .xlsm), CSV, and JSON (a list of records, or named tables)."
            )
    else:
        st.download_button(
            "No file yet? Get a test workbook",
            data=cached_template_workbook(None, True),
            file_name="cva_quick_test.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption(
            "One example sheet per analysis — upload it as-is to try everything, "
            "then replace the rows with your own data."
        )
    st.header("2. Choose an analysis")
    page = st.radio(
        "Analysis",
        [
            "Start & data check",
            "Customer selection",
            "Customer lifetime value",
            "Customer equity",
            "Acquisition & retention budgets",
            "Markov ROI",
            "Contractual retention",
            "BG/NBD continuous time",
            "BG/BB discrete time",
            "Complaints & recovery",
            "About this app",
        ],
        label_visibility="collapsed",
    )


if page == "Start & data check":
    st.warning(MEASUREMENT_WARNING, icon="⚠️")
    st.header("Start here")
    st.write(
        "Upload one file, choose the analysis that matches your business question, confirm the suggested columns, "
        "and press the analysis button. Your source file is never changed, and nothing leaves your computer."
    )
    st.markdown(
        """
        **First time here?**

        1. Download the test workbook from the sidebar (or use `examples/quick_test.xlsx`) and upload it.
        2. Pick an analysis on the left — every page has a *"What data do I need?"* section with
           downloadable templates you can fill with your own data.
        3. Results can be downloaded as Excel or JSON on every page.

        **What the app can do:**

        - Find the customers most worth contacting: RFM segmentation, response models, profit-based targeting, and lift
        - Value customers over time: customer lifetime value (CLV) and customer equity, with elasticities
        - Split marketing budgets between winning new customers and keeping existing ones
        - Judge marketing investments when customers switch between competing brands (Markov ROI)
        - Forecast how long subscribers stay (contractual retention)
        - Spot which customers are still active without them ever telling you (BG/NBD and BG/BB models)
        - Prepare complaint data and put a defensible price on winning back an unhappy customer
        """
    )
    if loaded:
        st.subheader(f"Data check: {loaded.source_name}")
        name = st.selectbox("Table / sheet", list(loaded.tables), key="profile_sheet")
        frame = loaded.tables[name]
        a, b, c = st.columns(3)
        a.metric("Rows", f"{len(frame):,}")
        b.metric("Columns", f"{len(frame.columns):,}")
        c.metric("Duplicate rows", f"{frame.duplicated().sum():,}")
        st.dataframe(profile_table(frame), use_container_width=True, hide_index=True)
        suggestions = []
        for role in ["customer_id", "date", "amount", "recency", "frequency", "monetary", "response", "period", "customers", "tx", "T"]:
            candidate = suggest_column(frame.columns, role)
            if candidate:
                suggestions.append({"role": role, "suggested_column": candidate})
        if suggestions:
            st.subheader("Automatic column suggestions")
            st.dataframe(pd.DataFrame(suggestions), use_container_width=True, hide_index=True)
    else:
        st.info("Upload a file to see its sheets, data quality, and automatic column suggestions.")


elif page == "Customer selection":
    st.header("Customer selection and profitable targeting")
    st.caption(
        "Who is worth contacting? Score customers with RFM (score 1 is best), fit a response model, "
        "and target only the customers whose expected profit is positive."
    )
    data_help(("transactions", "rfm_customers", "response_model"), "selection")
    frame = chosen_table(loaded, "selection", preferred=("transactions", "rfm_customers", "response_model"))
    if frame is not None:
        analysis = st.radio("Method", ["RFM analysis", "Logistic regression", "Decision tree"], horizontal=True)
        if analysis == "RFM analysis":
            source_kind = st.radio("Your data", ["Customer-level R, F, M columns", "Transaction rows"], horizontal=True)
            if source_kind.startswith("Customer"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    recency = column_select("Recency", frame, "recency", "rfm_r")
                with c2:
                    frequency = column_select("Frequency", frame, "frequency", "rfm_f")
                with c3:
                    monetary = column_select("Monetary value", frame, "monetary", "rfm_m")
                metrics = frame
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    customer = column_select("Customer ID", frame, "customer_id", "rfm_id")
                with c2:
                    date = column_select("Purchase date", frame, "date", "rfm_date")
                with c3:
                    amount = column_select("Transaction amount", frame, "amount", "rfm_amount")
                observation = st.date_input("Observation date", value=latest_valid_date(frame, date))
                try:
                    require_distinct({"customer ID": customer, "purchase date": date, "transaction amount": amount})
                    date_series(frame, date, "purchase date")
                    numeric_series(frame, amount, "transaction amount")
                    metrics = rfm_from_transactions(frame, customer, date, amount, observation)
                except Exception as exc:
                    show_error(exc)
                    st.stop()
                recency, frequency, monetary = "recency_days", "frequency_per_month", "monetary_average"
            nested = st.toggle("Use nested RFM (equal group sizes, recommended)", value=True)
            response = column_select("Optional response column for segment response rates", metrics, "response", "rfm_response", True)
            if st.button("Run RFM analysis", type="primary"):
                try:
                    require_distinct({"recency": recency, "frequency": frequency, "monetary value": monetary})
                    for column, label in [(recency, "recency"), (frequency, "frequency"), (monetary, "monetary value")]:
                        numeric_series(metrics, column, label)
                    scored = rfm_scores(metrics, recency, frequency, monetary, nested=nested)
                    aggregations = {"customers": ("RFM_segment", "size")}
                    if response:
                        scored[response] = binary_series(scored, response, "response (0/1)")
                        aggregations["response_rate"] = (response, "mean")
                        aggregations["responses"] = (response, "sum")
                    segments = scored.groupby("RFM_segment", as_index=False).agg(**aggregations).sort_values(
                        ["RFM_segment"]
                    )
                    st.success("RFM analysis complete")
                    st.dataframe(segments, use_container_width=True, hide_index=True)
                    render_downloads("rfm_analysis", {"Customer scores": scored, "Segments": segments}, "rfm")
                except Exception as exc:
                    show_error(exc)
        else:
            outcome = column_select("Response (0/1)", frame, "response", "model_outcome")

            def usable_default_predictor(column: object) -> bool:
                """Keep columns that can actually carry signal: no outcome, no IDs, no constants."""
                series = frame[column]
                distinct = series.nunique(dropna=True)
                if str(column) == outcome or distinct <= 1 or distinct == len(series.dropna()):
                    return False
                return pd.api.types.is_numeric_dtype(series) or distinct <= 20

            id_column = suggest_column([str(column) for column in frame.columns], "customer_id")
            default_predictors = [
                column for column in frame.columns if str(column) != str(id_column) and usable_default_predictor(column)
            ][:8]
            predictors = st.multiselect("Predictor columns", list(frame.columns), default=default_predictors)
            c1, c2 = st.columns(2)
            with c1:
                profit_response = st.number_input("Profit if response", value=25.0)
            with c2:
                profit_no_response = st.number_input("Profit if no response", value=-2.0)
            max_depth, min_leaf = 4, 50
            if analysis == "Decision tree":
                c1, c2 = st.columns(2)
                with c1:
                    max_depth = st.slider("Maximum tree depth", 1, 10, 4)
                with c2:
                    min_leaf = st.number_input("Minimum customers per leaf", 2, value=min(50, max(2, len(frame) // 20)))
            if st.button(f"Run {analysis.lower()}", type="primary", disabled=not predictors):
                try:
                    actual = binary_series(frame, outcome, "response")
                    if outcome in predictors:
                        raise DataProblem(
                            "The response column is also selected as a predictor, which would let the model cheat.",
                            "Remove it from the predictor list.",
                        )
                    # Fit on the validated 0/1 response so yes/no-style columns work end to end.
                    model_frame = frame.copy()
                    model_frame[outcome] = actual
                    if analysis == "Logistic regression":
                        fitted = fit_logistic(model_frame, outcome, predictors)
                        coefficients = fitted.coefficients
                        rules = None
                    else:
                        fitted = fit_decision_tree(model_frame, outcome, predictors, max_depth, int(min_leaf))
                        coefficients = fitted.feature_importance
                        rules = fitted.rules
                    scored = frame.copy()
                    scored["predicted_probability"] = fitted.predictions
                    targeting, summary = targeting_profit(
                        actual, fitted.predictions, profit_response, profit_no_response
                    )
                    scored = pd.concat([scored, targeting[["target", "expected_profit", "realized_profit"]]], axis=1)
                    lift = lift_table(actual, fitted.predictions)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Minimum profitable probability", f"{summary['threshold']:.2%}")
                    m2.metric("Customers targeted", f"{summary['customers_targeted']:,.0f}")
                    m3.metric("Realized hold-out profit", fmt_number(summary["realized_profit"]))
                    st.plotly_chart(px.line(lift, x="decile", y="lift", markers=True, title="Lift by decile"), use_container_width=True)
                    st.dataframe(coefficients, use_container_width=True, hide_index=True)
                    if rules:
                        st.code(rules, language="text")
                    render_downloads(
                        "targeting_analysis",
                        {"Customer scores": scored, "Lift": lift, "Model": coefficients},
                        "targeting",
                    )
                except Exception as exc:
                    show_error(exc)


elif page == "Customer lifetime value":
    st.header("Customer lifetime value")
    st.caption(
        "What is one customer worth over time? Future margins, discounted, weighted by the chance the customer "
        "is still around (Gupta–Lehmann margin-multiple approach, with finite-horizon, growth, and custom-timing variants)."
    )
    st.info("No data file is needed here — type your assumptions directly.", icon="✍️")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        margin = st.number_input("Net margin per period", min_value=0.0, value=100.0)
    with c2:
        retention = st.number_input("Retention rate", min_value=0.0, max_value=1.0, value=0.90)
    with c3:
        discount = st.number_input("Discount rate", min_value=0.0, value=0.10)
    with c4:
        acquisition_cost = st.number_input("Acquisition cost per customer", min_value=0.0, value=120.0)
    model = st.selectbox("CLV version", ["Infinite horizon", "Finite horizon", "Margin growth", "Custom first and last period"])
    extra: dict[str, float | int] = {}
    if model == "Finite horizon":
        extra["periods"] = st.number_input("Number of periods", min_value=1, value=5)
    elif model == "Margin growth":
        extra["growth"] = st.number_input("Margin growth per period", value=0.02)
    elif model == "Custom first and last period":
        c1, c2 = st.columns(2)
        with c1:
            extra["first"] = st.number_input("First margin period", min_value=0, value=1)
        with c2:
            extra["last"] = st.number_input("Last margin period", min_value=0, value=5)
    if st.button("Calculate CLV", type="primary"):
        try:
            core = summarize_clv(margin, retention, discount, acquisition_cost)
            if model == "Infinite horizon":
                value = core.clv
            elif model == "Finite horizon":
                value = finite_horizon_clv(margin, retention, discount, int(extra["periods"]))
            elif model == "Margin growth":
                value = growth_clv(margin, retention, discount, float(extra["growth"]))
            else:
                value = timed_clv(margin, retention, discount, int(extra["first"]), int(extra["last"]))
            summary = core.to_dict() | {"selected_model": model, "selected_model_clv": value, "selected_net_value": value - acquisition_cost}
            cols = st.columns(4)
            cols[0].metric("CLV", fmt_number(value))
            cols[1].metric("Net value", fmt_number(value - acquisition_cost))
            cols[2].metric("Margin multiple", f"{core.margin_multiple:.2f}×")
            cols[3].metric("Retention elasticity", f"{core.retention_elasticity:.2f}")
            table = pd.DataFrame([summary])
            st.dataframe(table, use_container_width=True, hide_index=True)
            render_downloads("clv_results", {"CLV": table}, "clv")
        except Exception as exc:
            show_error(exc)


elif page == "Customer equity":
    st.header("Customer equity")
    st.caption(
        "What is your whole customer base worth? Fits a bell-shaped customer-acquisition curve to your history, "
        "then values current and future customers (Gupta, Lehmann & Stuart approach)."
    )
    data_help(("equity",), "equity")
    frame = chosen_table(loaded, "equity", preferred=("equity",))
    if frame is not None:
        c1, c2 = st.columns(2)
        with c1:
            period_col = column_select("Period", frame, "period", "equity_period")
        with c2:
            customer_col = column_select("Number of current customers", frame, "customers", "equity_customers")
        c1, c2, c3 = st.columns(3)
        with c1:
            acquisition_cost = st.number_input("Acquisition cost per customer", min_value=0.0, value=120.0, key="eq_acq")
            margin = st.number_input("Net margin per period", min_value=0.0, value=100.0, key="eq_margin")
        with c2:
            retention = st.number_input("Retention per period", min_value=0.0, max_value=1.0, value=0.90, key="eq_ret")
            discount = st.number_input("Discount per period", min_value=0.0, value=0.10, key="eq_disc")
        with c3:
            tax = st.number_input("Corporate tax rate", min_value=0.0, max_value=1.0, value=0.38)
            forecast_periods = st.number_input("Future periods", min_value=10, value=100)
            periods_per_year = st.number_input("Periods per year", min_value=1, value=4)
        if st.button("Calculate customer equity", type="primary"):
            try:
                require_distinct({"period": period_col, "number of customers": customer_col})
                period_series = numeric_series(frame, period_col, "period", minimum_rows=5)
                count_series = numeric_series(frame, customer_col, "number of customers", minimum_rows=5)
                for note in [skipped_rows_note(period_series, period_col), skipped_rows_note(count_series, customer_col)]:
                    if note:
                        st.caption(note)
                periods = period_series.to_numpy()
                counts = count_series.to_numpy()
                valid = np.isfinite(periods) & np.isfinite(counts)
                if int(valid.sum()) < 5:
                    raise DataProblem(
                        "Customer equity needs at least five rows where both the period and the number of customers "
                        "are readable numbers — acquisitions are computed from period-to-period changes, so five counts "
                        "give the four observations the curve fit needs.",
                        "Add more history rows, or clean the rows with unreadable values.",
                    )
                result = customer_equity(
                    periods[valid], counts[valid], acquisition_cost, margin, retention, discount, tax, int(forecast_periods)
                )
                elasticities = annual_elasticities(
                    periods[valid], counts[valid], acquisition_cost, margin, retention, discount, tax, int(periods_per_year), int(forecast_periods)
                )
                summary = pd.DataFrame([result.summary.to_dict() | result.curve_fit.__dict__])
                m1, m2, m3 = st.columns(3)
                m1.metric("Current-customer value", fmt_number(result.summary.current_customer_value))
                m2.metric("Future-customer value", fmt_number(result.summary.future_customer_value))
                m3.metric("Customer equity after tax", fmt_number(result.summary.customer_equity))
                chart = pd.concat(
                    [
                        result.history.rename(columns={"observed_acquired": "customers"}).assign(series="Observed")[["period", "customers", "series"]],
                        result.history.rename(columns={"fitted_acquired": "customers"}).assign(series="Fitted")[["period", "customers", "series"]],
                        result.forecast.rename(columns={"forecast_acquired": "customers"}).assign(series="Forecast")[["period", "customers", "series"]],
                    ]
                )
                st.plotly_chart(px.line(chart, x="period", y="customers", color="series", title="Acquired customers"), use_container_width=True)
                st.dataframe(elasticities, use_container_width=True, hide_index=True)
                render_downloads(
                    "customer_equity",
                    {"Summary": summary, "History": result.history, "Forecast": result.forecast, "Elasticities": elasticities},
                    "equity",
                )
            except Exception as exc:
                show_error(exc)


elif page == "Acquisition & retention budgets":
    st.header("Optimal acquisition and retention budgets")
    st.caption(
        "How much should you spend to win a new customer versus keeping an existing one? "
        "Blattberg–Deighton spending optimization based on how your acquisition and retention rates respond to money."
    )
    st.info("No data file is needed here — type your current rates and spending directly.", icon="✍️")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Acquisition")
        A = st.number_input("Current spend per prospect", min_value=0.01, value=6.0)
        a = st.number_input("Current acquisition rate", min_value=0.0001, max_value=0.9999, value=0.25)
        Ca = st.number_input("Maximum possible acquisition rate", min_value=0.0002, max_value=1.0, value=0.45)
    with c2:
        st.subheader("Retention")
        R = st.number_input("Current retention spend per customer", min_value=0.01, value=10.0)
        r = st.number_input("Current retention rate", min_value=0.0001, max_value=0.9999, value=0.50)
        Cr = st.number_input("Maximum possible retention rate", min_value=0.0002, max_value=1.0, value=0.80)
    c1, c2 = st.columns(2)
    with c1:
        margin = st.number_input("Profit margin per period", min_value=0.0, value=60.0, key="bd_margin")
    with c2:
        discount = st.number_input("Discount rate", min_value=0.0, value=0.10, key="bd_discount")
    if st.button("Optimize budgets", type="primary"):
        try:
            result = optimize_budgets(A, a, Ca, R, r, Cr, margin, discount)
            table = pd.DataFrame([result.to_dict()])
            cols = st.columns(4)
            cols[0].metric("Optimal acquisition spend", fmt_number(result.optimal_acquisition_spend))
            cols[1].metric("Optimal retention spend", fmt_number(result.optimal_retention_spend))
            cols[2].metric("Optimal acquisition rate", f"{result.optimal_acquisition_rate:.1%}")
            cols[3].metric("Optimal retention rate", f"{result.optimal_retention_rate:.1%}")
            st.metric("Improvement in prospect value", f"{result.improvement_pct:.1f}%")
            render_downloads("optimal_budgets", {"Optimization": table}, "budgets")
        except Exception as exc:
            show_error(exc)


elif page == "Markov ROI":
    st.header("Markov customer equity and ROI")
    st.caption(
        "Is a marketing investment worth it when customers switch between competing brands? "
        "Models brand switching as transition probabilities and values the shift they cause "
        "(Rust, Lemon & Zeithaml return-on-marketing approach)."
    )
    st.info("No data file is needed here — fill in the switching probabilities directly.", icon="✍️")
    companies = st.number_input("Number of companies", min_value=2, max_value=5, value=2)
    n = int(companies)
    default_old = np.eye(n) * 0.7 + (np.ones((n, n)) - np.eye(n)) * (0.3 / (n - 1))
    default_new = default_old.copy()
    if n == 2:
        default_old = np.array([[0.75, 0.25], [0.2, 0.8]])
        default_new = np.array([[0.8, 0.2], [0.15, 0.85]])
    c1, c2 = st.columns(2)
    with c1:
        st.write("Current transition matrix (rows = previous choice)")
        old_df = st.data_editor(pd.DataFrame(default_old), key=f"old_matrix_{n}", use_container_width=True)
    with c2:
        st.write("New transition matrix after investment")
        new_df = st.data_editor(pd.DataFrame(default_new), key=f"new_matrix_{n}", use_container_width=True)
    weights = st.data_editor(
        pd.DataFrame({"previous_choice_weight": np.repeat(1 / n, n)}), key=f"weights_{n}", use_container_width=True
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        focal = st.selectbox("Focal company", list(range(1, n + 1))) - 1
        amount = st.number_input("Amount per purchase", min_value=0.0, value=120.0)
        profit_margin = st.number_input("Net profit margin", min_value=0.0, max_value=1.0, value=0.25)
    with c2:
        frequency = st.number_input("Purchases per year", min_value=0.01, value=2.0)
        horizon = st.number_input("Planning horizon (years)", min_value=0.0, value=4.0)
        discount = st.number_input("Annual discount rate", min_value=0.0, value=0.10, key="markov_discount")
    with c3:
        industry = st.number_input("Customers in industry", min_value=1.0, value=500_000.0)
        investment = st.number_input("Marketing investment", min_value=0.0, value=5_000_000.0)
    if st.button("Calculate Markov ROI", type="primary"):
        try:
            matrices: dict[str, np.ndarray] = {}
            for name, matrix in [("current", old_df.to_numpy(float)), ("new", new_df.to_numpy(float))]:
                row_sums = matrix.sum(axis=1)
                if not np.allclose(row_sums, 1.0, atol=0.02):
                    raise DataProblem(
                        f"Each row of the {name} transition matrix should sum to 1 — "
                        "the row holds the probabilities of choosing each company next.",
                        "Adjust the row values so every row adds up to 1.",
                    )
                # Rounding like 0.33+0.33+0.33 is fine to type; rescale rows to sum exactly to 1.
                matrices[name] = matrix / row_sums[:, np.newaxis]
                if not np.allclose(row_sums, 1.0, atol=1e-9):
                    st.caption(f"Rows of the {name} matrix were rescaled to sum exactly to 1.")
            result = markov_roi(
                matrices["current"], matrices["new"], weights.iloc[:, 0].to_numpy(float), focal,
                amount, profit_margin, frequency, discount, horizon, industry, investment
            )
            _, path = markov_clv(matrices["new"], focal, focal, amount, profit_margin, frequency, discount, horizon)
            table = pd.DataFrame([result.to_dict()])
            cols = st.columns(3)
            cols[0].metric("Increase in customer equity", fmt_number(result.change_in_customer_equity))
            cols[1].metric("Net profit", fmt_number(result.net_profit))
            cols[2].metric("ROI", f"{result.roi:.1%}")
            st.plotly_chart(px.line(path, x="years_from_now", y="choice_probability", markers=True), use_container_width=True)
            render_downloads("markov_roi", {"ROI": table, "New choice path": path}, "markov")
        except Exception as exc:
            show_error(exc)


elif page == "Contractual retention":
    st.header("Contractual retention forecasting")
    st.caption(
        "How long do subscribers stay? Fits the shifted beta-geometric model (Fader & Hardie) to your "
        "survival counts — far more reliable than extending a straight line through past retention rates."
    )
    data_help(("contractual_survival",), "contractual")
    frame = chosen_table(loaded, "contractual", preferred=("contractual_survival",))
    if frame is not None:
        c1, c2 = st.columns(2)
        with c1:
            period = column_select("Period (0, 1, 2, …)", frame, "period", "contract_period")
        with c2:
            survivors = column_select("Surviving customers", frame, "customers", "contract_survivors")
        horizon = st.number_input("Forecast through period", min_value=3, value=20)
        if st.button("Forecast retention", type="primary"):
            try:
                require_distinct({"period": period, "surviving customers": survivors})
                period_series = numeric_series(frame, period, "period", minimum_rows=3)
                survivor_series = numeric_series(frame, survivors, "surviving customers", minimum_rows=3)
                paired = pd.DataFrame({"period": period_series, "survivors": survivor_series}).dropna().sort_values("period")
                if not paired["survivors"].is_monotonic_decreasing:
                    raise DataProblem(
                        "The surviving-customer counts increase somewhere, which is impossible for one starting group.",
                        "Count only the survivors of the original group in every period — new customers get their own cohort.",
                    )
                fit, forecast, metrics = contractual_forecast(
                    period_series.to_numpy(),
                    survivor_series.to_numpy(),
                    int(horizon),
                )
                params = pd.DataFrame([fit.to_dict() | metrics])
                st.dataframe(params, use_container_width=True, hide_index=True)
                chart = forecast.melt("period", ["actual_survival", "predicted_survival"], var_name="series", value_name="survival")
                st.plotly_chart(px.line(chart, x="period", y="survival", color="series", markers=True), use_container_width=True)
                render_downloads("contractual_retention", {"Parameters": params, "Forecast": forecast}, "contractual")
            except Exception as exc:
                show_error(exc)


elif page == "BG/NBD continuous time":
    st.header("BG/NBD continuous-time customer base analysis")
    st.caption(
        "Which customers are still active when they never tell you they left? The BG/NBD model "
        "(Fader, Hardie & Lee) estimates each customer's probability of being active and their expected "
        "future purchases, from purchase history alone."
    )
    data_help(("bgnbd_summary", "transactions"), "bgnbd")
    frame = chosen_table(loaded, "bgnbd", preferred=("bgnbd_summary", "bgnbd", "transactions"))
    if frame is not None:
        source = st.radio("Input format", ["Summary columns x, tx, T", "Transaction rows"], horizontal=True)
        if source.startswith("Transaction"):
            c1, c2 = st.columns(2)
            with c1:
                customer = column_select("Customer ID", frame, "customer_id", "bgnbd_id")
            with c2:
                purchase_date = column_select("Purchase date", frame, "date", "bgnbd_date")
            unit = st.selectbox("Time unit", ["weeks", "days", "months"])
            end = st.date_input("Observation end", value=latest_valid_date(frame, purchase_date))
            try:
                require_distinct({"customer ID": customer, "purchase date": purchase_date})
                date_series(frame, purchase_date, "purchase date")
                summary = summarize_transactions(frame, customer, purchase_date, end, unit)
            except Exception as exc:
                show_error(exc)
                st.stop()
            x_col, tx_col, T_col = "x", "tx", "T"
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                x_col = column_select("x: repeat purchases", frame, "frequency", "bgnbd_x")
            with c2:
                tx_col = column_select("tx: time of last repeat purchase", frame, "tx", "bgnbd_tx")
            with c3:
                T_col = column_select("T: observation length", frame, "T", "bgnbd_T")
            summary = frame
        weight = column_select("Optional count/weight column", summary, "weight", "bgnbd_weight", True)
        horizon = st.number_input("Future horizon (same time unit)", min_value=0.0, value=39.0)
        if st.button("Fit BG/NBD and score customers", type="primary"):
            try:
                require_distinct({"x": x_col, "tx": tx_col, "T": T_col})
                for column, label in [(x_col, "repeat purchases x"), (tx_col, "last-purchase time tx"), (T_col, "observation length T")]:
                    numeric_series(summary, column, label)
                with st.spinner("Estimating model parameters…"):
                    params, scored = score_bgnbd(summary, x_col, tx_col, T_col, horizon, weight)
                parameter_table = pd.DataFrame([params.to_dict()])
                cols = st.columns(4)
                for col, name in zip(cols, ["r", "alpha", "a", "b"]):
                    col.metric(name, f"{getattr(params, name):.4f}")
                st.plotly_chart(px.scatter(scored, x=tx_col, y="expected_future_purchases", color=x_col), use_container_width=True)
                render_downloads("bgnbd_results", {"Parameters": parameter_table, "Customer scores": scored}, "bgnbd")
            except Exception as exc:
                show_error(exc)


elif page == "BG/BB discrete time":
    st.header("BG/BB discrete-time customer base analysis")
    st.caption(
        "Which customers are still active when you observe fixed periods — years of donations, "
        "seasons of ticket buying? The BG/BB model (Fader, Hardie & Shang) estimates who is still "
        "alive and how many future purchases to expect."
    )
    data_help(("bgbb_histories",), "bgbb")
    frame = chosen_table(loaded, "bgbb", preferred=("bgbb_histories",))
    if frame is not None:
        source = st.radio("Input format", ["Summary columns n, tx, x", "One 0/1 column per period"], horizontal=True)
        if source.startswith("One"):
            period_columns = st.multiselect("Period columns in chronological order", list(frame.columns))
            try:
                summary = summary_from_binary_periods(frame, period_columns) if period_columns else frame
            except Exception as exc:
                show_error(exc)
                st.stop()
            n_col, tx_col, x_col = "n", "tx", "x"
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                n_col = column_select("n: observed periods", frame, "customers", "bgbb_n")
            with c2:
                tx_col = column_select("tx: period of last purchase", frame, "tx", "bgbb_tx")
            with c3:
                x_col = column_select("x: repeat purchases", frame, "frequency", "bgbb_x")
            summary = frame
        weight = column_select("Optional count/weight column", summary, "weight", "bgbb_weight", True)
        future = st.number_input("Future periods", min_value=0, value=5)
        if st.button("Fit BG/BB and score customers", type="primary"):
            try:
                if source.startswith("One") and not period_columns:
                    raise DataProblem("No period columns are selected yet.", "Choose at least one 0/1 period column above.")
                if not source.startswith("One"):
                    require_distinct({"n": n_col, "tx": tx_col, "x": x_col})
                    for column, label in [(n_col, "observed periods n"), (tx_col, "last-purchase period tx"), (x_col, "repeat purchases x")]:
                        numeric_series(summary, column, label)
                with st.spinner("Estimating model parameters…"):
                    params, scored = score_bgbb(summary, n_col, tx_col, x_col, int(future), weight)
                parameter_table = pd.DataFrame([params.to_dict()])
                cols = st.columns(4)
                for col, name in zip(cols, ["alpha", "beta", "gamma", "delta"]):
                    col.metric(name, f"{getattr(params, name):.4f}")
                st.plotly_chart(px.scatter(scored, x=tx_col, y="expected_future_purchases", color=x_col), use_container_width=True)
                render_downloads("bgbb_results", {"Parameters": parameter_table, "Customer scores": scored}, "bgbb")
            except Exception as exc:
                show_error(exc)


elif page == "Complaints & recovery":
    st.header("Complaints and recovery")
    st.caption(
        "What is a complaining customer worth saving? Prepares the six per-customer inputs of the "
        "Knox–van Oest complaint model from your raw event log, and puts a defensible ceiling on "
        "recovery spending: the CLV difference between winning the customer back and losing them."
    )
    data_help(("events",), "complaints")
    tab1, tab2 = st.tabs(["Prepare complaint-model inputs", "Recovery value"])
    with tab1:
        frame = chosen_table(loaded, "complaints", preferred=("events",))
        if frame is not None:
            c1, c2, c3 = st.columns(3)
            with c1:
                customer = column_select("Customer ID", frame, "customer_id", "complaint_id")
            with c2:
                event_date = column_select("Event date", frame, "date", "complaint_date")
            with c3:
                event_type = column_select("Event type (purchase / complaint)", frame, "event_type", "complaint_type")
            unit = st.selectbox("Time unit", ["weeks", "days", "months"], key="complaint_unit")
            end = st.date_input("Observation end", value=latest_valid_date(frame, event_date), key="complaint_end")
            if st.button("Prepare six summary statistics", type="primary"):
                try:
                    require_distinct({"customer ID": customer, "event date": event_date, "event type": event_type})
                    date_series(frame, event_date, "event date")
                    summary = complaint_summary(frame, customer, event_date, event_type, end, unit)
                    st.dataframe(summary, use_container_width=True, hide_index=True)
                    render_downloads("complaint_model_inputs", {"Customer summaries": summary}, "complaint_inputs")
                except Exception as exc:
                    show_error(exc)
    with tab2:
        future_value = st.number_input("Future value if the customer stays", min_value=0.0, value=250.0)
        recovered = st.number_input("Stay probability with recovery", min_value=0.0, max_value=1.0, value=0.85)
        unrecovered = st.number_input("Stay probability without recovery", min_value=0.0, max_value=1.0, value=0.55)
        cost = st.number_input("Proposed recovery cost", min_value=0.0, value=25.0)
        if st.button("Value recovery", type="primary"):
            values = recovery_value(future_value, recovered, unrecovered, cost)
            table = pd.DataFrame([values])
            c1, c2 = st.columns(2)
            c1.metric("Maximum justified recovery cost", fmt_number(values["maximum_financially_justified_recovery_cost"]))
            c2.metric("Net value of recovery", fmt_number(values["net_value_of_recovery"]))
            render_downloads("recovery_value", {"Recovery value": table}, "recovery")


elif page == "About this app":
    st.header("About this app")
    st.warning(MEASUREMENT_WARNING, icon="⚠️")
    st.markdown(
        """
        ### What it is

        Customer Value Analytics turns a customer data file — Excel, CSV, or JSON — into the classic
        customer-value analyses: segmentation, targeting, lifetime value, retention forecasting, and
        marketing ROI. It is built to be usable without a statistics background: upload a file, confirm
        the suggested columns, press a button. Everything runs locally on your computer; your data is
        never uploaded anywhere, and your source file is never changed.

        ### What the numbers can and cannot tell you

        The models here are the classic, widely taught models of customer analytics — each page names
        the published work it follows, and the formulas are documented in `docs/methods.md`. They are
        deliberately simple: they assume the future will broadly behave like the past, and they compress
        messy human behaviour into a handful of parameters. Research has moved beyond them —
        hierarchical Bayesian models, machine-learning approaches, causal attribution — and those are
        outside the scope of this project. If a decision is expensive to get wrong, use these results as
        a starting point for judgement, not a substitute for it.

        ### Built with AI assistance

        This app was developed with the help of AI coding assistants. The implementations were checked
        against the published papers, and an automated test suite reproduces reference examples on every
        change. Even so: verify results independently before using them for important decisions. No
        warranty of any kind is given.

        ### Open source

        The project is free software under the **AGPL-3.0-or-later** license. Anyone — individuals and
        companies alike — may use it, study it, and change it, including private changes for internal
        use. What the license forbids is closing it: whoever distributes this software or offers it to
        others as an online service, original or modified, must pass on the source code and the same
        freedoms. Improvements are welcome — see `CONTRIBUTING.md` in the repository for how to get
        started.

        The license covers this app's code. The statistical models it implements are the published
        work of the researchers cited on each page and in `docs/methods.md` — this project claims no
        ownership of the theory.
        """
    )
