"""Worth Signal Streamlit UI.

Everything that draws the app runs inside ``render()`` (or the functions it calls), so it runs on every rerun,
both in the standalone ``app.py`` and inside Signal Hub. Module-level code here only defines constants and
functions. ``render()`` never calls ``st.set_page_config`` or ``st.navigation``.
"""

from __future__ import annotations

import hashlib
import io
import traceback

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from cva import __version__
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
from cva.ui import signal_theme as sig
from cva.validation import (
    DataProblem,
    binary_series,
    date_series,
    friendly_message,
    numeric_series,
    require_distinct,
    skipped_rows_note,
)


NS = "worth"


def k(name: str) -> str:
    """Namespace a session-state or widget key with the app slug, so apps can share one Hub session."""
    return f"{NS}:{name}"


MODEL_WARNING = (
    "**Use estimates wisely.** Every model simplifies real customer behaviour and depends on the quality "
    "of your inputs. Use results to compare options, test assumptions, and support judgement — not as a "
    "precise promise about the future."
)
SIDEBAR_TAGLINE = "Find the customers, value, and moves that matter."
MASTHEAD_KICKER = "OPEN CUSTOMER VALUE TOOLKIT"
MASTHEAD_PROMISES = ["Local-first", "Explainable", "Open source"]
FOOTER_LINE = "Customer-value estimates, not future truth"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEMO_FILENAME = "worthsignal_quick_test.xlsx"
DEMO_NAME = "Fictional demo workbook"


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
        for template_key in keys:
            spec = TEMPLATES[template_key]
            st.markdown(f"**{spec.title}** — {spec.purpose}")
            st.markdown("\n".join(f"- `{column.name}`: {column.description}" for column in spec.columns))
            left, right = st.columns(2)
            left.download_button(
                "Download Excel template",
                data=cached_template_workbook((template_key,), True),
                file_name=f"template_{template_key}.xlsx",
                mime=XLSX_MIME,
                key=k(f"tmpl_xlsx_{page_key}_{template_key}"),
            )
            right.download_button(
                "Download CSV template",
                data=cached_template_csv(template_key),
                file_name=f"template_{template_key}.csv",
                mime="text/csv",
                key=k(f"tmpl_csv_{page_key}_{template_key}"),
            )
        st.caption(
            "Templates come filled with example rows — replace them with your own data and upload the file. "
            "Column names are recognised automatically, and you can always correct the mapping by hand."
        )


def latest_valid_date(frame: pd.DataFrame, column: str) -> object:
    parsed = pd.to_datetime(frame[column], errors="coerce")
    return (parsed.max() if parsed.notna().any() else pd.Timestamp.today()).date()


def column_select(label: str, frame: pd.DataFrame, role: str, key: str, allow_none: bool = False) -> str | None:
    """Column picker pre-set to the suggested column. ``key`` is already namespaced by the caller with k()."""
    columns = [str(column) for column in frame.columns]
    suggestion = suggest_column(columns, role)
    options = (["— none —"] if allow_none else []) + columns
    default = options.index(suggestion) if suggestion in options else 0
    selected = st.selectbox(label, options, index=default, key=key)
    return None if selected == "— none —" else selected


def render_downloads(name: str, tables: dict[str, pd.DataFrame], stem: str) -> None:
    left, right = st.columns(2)
    with left:
        st.download_button(
            "Download Excel results",
            data=results_to_excel(tables),
            file_name=f"{name}.xlsx",
            mime=XLSX_MIME,
            key=k(f"xlsx_{stem}"),
        )
    with right:
        st.download_button(
            "Download JSON results",
            data=results_to_json(tables),
            file_name=f"{name}.json",
            mime="application/json",
            key=k(f"json_{stem}"),
        )


def chosen_table(data: LoadedData | None, stem: str, preferred: tuple[str, ...] = ()) -> pd.DataFrame | None:
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
    table_name = st.selectbox("Data table / Excel sheet", names, index=default, key=k(f"table_{stem}"))
    frame = data.tables[table_name]
    st.caption(f"{len(frame):,} rows × {len(frame.columns):,} columns")
    with st.expander("Preview source data", expanded=False):
        st.dataframe(frame.head(100), width="stretch")
    return frame


def load_for_session(raw: bytes, filename: str) -> LoadedData:
    """Parse an upload once per browser session without placing customer data in a global cache."""
    fingerprint = (filename, hashlib.sha256(raw).hexdigest())
    cached = st.session_state.get(k("upload"))
    if cached is not None and cached["key"] == fingerprint:
        return cached["data"]
    parsed = load_data(io.BytesIO(raw), filename)
    st.session_state[k("upload")] = {"key": fingerprint, "data": parsed}
    return parsed


def demo_data() -> LoadedData:
    """The generated test workbook (one fictional example sheet per analysis), parsed like an upload."""
    parsed = load_data(io.BytesIO(cached_template_workbook(None, True)), DEMO_FILENAME)
    return LoadedData(tables=parsed.tables, source_name=DEMO_NAME)


def _ensure_state() -> None:
    # The parsed upload lives only in this browser session (never in a global cache).
    if k("upload") not in st.session_state:
        st.session_state[k("upload")] = None
    # First run: preload the fictional demo workbook so every page works before anything is uploaded.
    if k("demo") not in st.session_state:
        st.session_state[k("demo")] = demo_data()


def page_start(loaded: LoadedData | None) -> None:
    sig.hero(
        NS,
        eyebrow="FROM ROWS TO RELATIONSHIPS",
        title="Customer value,",
        em="without the black box.",
        body=(
            "Worth Signal turns the customer data you already have into transparent segmentation, lifetime value, "
            "retention, and ROI decisions — with methods you can inspect and results you can export."
        ),
        pills=["Excel, CSV & JSON", "No account required", "Published models", "AGPL open source"],
    )
    sig.note("warn", MODEL_WARNING)
    st.header("Start here")
    st.write(
        "Upload one file, choose the analysis that matches your business question, confirm the suggested columns, "
        "and press the analysis button. Your source file is never changed."
    )
    sig.note(
        "muted",
        "**Privacy:** when you run Worth Signal on your own computer, your data stays there. On a hosted "
        "deployment, uploads are processed by that deployment's server; Worth Signal itself adds no accounts, "
        "telemetry, or persistent customer-data storage.",
    )
    st.markdown(
        """
        **First time here?**

        1. A fictional demo workbook is already loaded — one example sheet per analysis, no real customers.
           Upload your own Excel, CSV, or JSON file in the sidebar to replace it; remove the upload to
           return to the demo.
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
        name = st.selectbox("Table / sheet", list(loaded.tables), key=k("profile_sheet"))
        frame = loaded.tables[name]
        a, b, c = st.columns(3)
        a.metric("Rows", f"{len(frame):,}")
        b.metric("Columns", f"{len(frame.columns):,}")
        c.metric("Duplicate rows", f"{frame.duplicated().sum():,}")
        st.dataframe(profile_table(frame), width="stretch", hide_index=True)
        suggestions = []
        for role in ["customer_id", "date", "amount", "recency", "frequency", "monetary", "response", "period", "customers", "tx", "T"]:
            candidate = suggest_column(frame.columns, role)
            if candidate:
                suggestions.append({"role": role, "suggested_column": candidate})
        if suggestions:
            st.subheader("Automatic column suggestions")
            st.dataframe(pd.DataFrame(suggestions), width="stretch", hide_index=True)
    else:
        st.info("Upload a file to see its sheets, data quality, and automatic column suggestions.")


def page_selection(loaded: LoadedData | None) -> None:
    sig.header("Analysis 1", "Customer selection and profitable targeting")
    st.caption(
        "Who is worth contacting? Score customers with RFM (score 1 is best), fit a response model, "
        "and target only the customers whose expected profit is positive. RFM groups customers by value "
        "behaviour only — for multi-variable segmentation on needs, attitudes, or demographics, use our "
        "sibling app **Segment Signal**; to learn which product features customers value, use **Choice Signal**."
    )
    data_help(("transactions", "rfm_customers", "response_model"), "selection")
    frame = chosen_table(loaded, "selection", preferred=("transactions", "rfm_customers", "response_model"))
    if frame is None:
        return
    analysis = st.radio(
        "Method", ["RFM analysis", "Logistic regression", "Decision tree"], horizontal=True, key=k("selection_method")
    )
    if analysis == "RFM analysis":
        # Default to the layout the chosen sheet looks like (the demo opens on its transaction rows).
        columns = [str(column) for column in frame.columns]
        looks_like_transactions = suggest_column(columns, "recency") is None and all(
            suggest_column(columns, role) for role in ("customer_id", "date", "amount")
        )
        source_kind = st.radio(
            "Your data",
            ["Customer-level R, F, M columns", "Transaction rows"],
            index=1 if looks_like_transactions else 0,
            horizontal=True,
            key=k("rfm_source"),
        )
        if source_kind.startswith("Customer"):
            c1, c2, c3 = st.columns(3)
            with c1:
                recency = column_select("Recency", frame, "recency", k("rfm_r"))
            with c2:
                frequency = column_select("Frequency", frame, "frequency", k("rfm_f"))
            with c3:
                monetary = column_select("Monetary value", frame, "monetary", k("rfm_m"))
            metrics = frame
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                customer = column_select("Customer ID", frame, "customer_id", k("rfm_id"))
            with c2:
                date = column_select("Purchase date", frame, "date", k("rfm_date"))
            with c3:
                amount = column_select("Transaction amount", frame, "amount", k("rfm_amount"))
            default_observation = latest_valid_date(frame, date)
            # The default follows the data: a new file or date column starts from its own latest date.
            observation = st.date_input(
                "Observation date", value=default_observation, key=k(f"rfm_observation_{default_observation}")
            )
            try:
                require_distinct({"customer ID": customer, "purchase date": date, "transaction amount": amount})
                date_series(frame, date, "purchase date")
                numeric_series(frame, amount, "transaction amount")
                metrics = rfm_from_transactions(frame, customer, date, amount, observation)
            except Exception as exc:
                show_error(exc)
                return
            recency, frequency, monetary = "recency_days", "frequency_per_month", "monetary_average"
        nested = st.toggle("Use nested RFM (equal group sizes, recommended)", value=True, key=k("rfm_nested"))
        response = column_select(
            "Optional response column for segment response rates", metrics, "response", k("rfm_response"), True
        )
        if st.button("Run RFM analysis", type="primary", key=k("run_rfm")):
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
                st.dataframe(segments, width="stretch", hide_index=True)
                render_downloads("rfm_analysis", {"Customer scores": scored, "Segments": segments}, "rfm")
            except Exception as exc:
                show_error(exc)
        return

    outcome = column_select("Response (0/1)", frame, "response", k("model_outcome"))

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
    predictors = st.multiselect(
        "Predictor columns", list(frame.columns), default=default_predictors, key=k("model_predictors")
    )
    c1, c2 = st.columns(2)
    with c1:
        profit_response = st.number_input("Profit if response", value=25.0, key=k("profit_response"))
    with c2:
        profit_no_response = st.number_input("Profit if no response", value=-2.0, key=k("profit_no_response"))
    max_depth, min_leaf = 4, 50
    if analysis == "Decision tree":
        c1, c2 = st.columns(2)
        with c1:
            max_depth = st.slider("Maximum tree depth", 1, 10, 4, key=k("tree_depth"))
        with c2:
            min_leaf = st.number_input(
                "Minimum customers per leaf", 2, value=min(50, max(2, len(frame) // 20)), key=k("tree_min_leaf")
            )
    if st.button(f"Run {analysis.lower()}", type="primary", disabled=not predictors, key=k("run_model")):
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
            targeting, summary = targeting_profit(actual, fitted.predictions, profit_response, profit_no_response)
            scored = pd.concat([scored, targeting[["target", "expected_profit", "realized_profit"]]], axis=1)
            lift = lift_table(actual, fitted.predictions)
            m1, m2, m3 = st.columns(3)
            m1.metric("Minimum profitable probability", f"{summary['threshold']:.2%}")
            m2.metric("Customers targeted", f"{summary['customers_targeted']:,.0f}")
            m3.metric("Realized hold-out profit", fmt_number(summary["realized_profit"]))
            fig = px.line(lift, x="decile", y="lift", markers=True, title="Lift by decile", template=sig.template(NS))
            sig.chart(NS, fig, key=k("lift_chart"))
            st.dataframe(coefficients, width="stretch", hide_index=True)
            if rules:
                st.code(rules, language="text")
            render_downloads(
                "targeting_analysis",
                {"Customer scores": scored, "Lift": lift, "Model": coefficients},
                "targeting",
            )
        except Exception as exc:
            show_error(exc)


def page_clv(loaded: LoadedData | None) -> None:
    sig.header("Analysis 2", "Customer lifetime value")
    st.caption(
        "What is one customer worth over time? Future margins, discounted, weighted by the chance the customer "
        "is still around (Gupta–Lehmann margin-multiple approach, with finite-horizon, growth, and custom-timing variants)."
    )
    st.info("No data file is needed here — type your assumptions directly.", icon="✍️")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        margin = st.number_input("Net margin per period", min_value=0.0, value=100.0, key=k("clv_margin"))
    with c2:
        retention = st.number_input("Retention rate", min_value=0.0, max_value=1.0, value=0.90, key=k("clv_retention"))
    with c3:
        discount = st.number_input("Discount rate", min_value=0.0, value=0.10, key=k("clv_discount"))
    with c4:
        acquisition_cost = st.number_input(
            "Acquisition cost per customer", min_value=0.0, value=120.0, key=k("clv_acquisition_cost")
        )
    model = st.selectbox(
        "CLV version",
        ["Infinite horizon", "Finite horizon", "Margin growth", "Custom first and last period"],
        key=k("clv_model"),
    )
    extra: dict[str, float | int] = {}
    if model == "Finite horizon":
        extra["periods"] = st.number_input("Number of periods", min_value=1, value=5, key=k("clv_periods"))
    elif model == "Margin growth":
        extra["growth"] = st.number_input("Margin growth per period", value=0.02, key=k("clv_growth"))
    elif model == "Custom first and last period":
        c1, c2 = st.columns(2)
        with c1:
            extra["first"] = st.number_input("First margin period", min_value=0, value=1, key=k("clv_first"))
        with c2:
            extra["last"] = st.number_input("Last margin period", min_value=0, value=5, key=k("clv_last"))
    if st.button("Calculate CLV", type="primary", key=k("run_clv")):
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
            st.dataframe(table, width="stretch", hide_index=True)
            render_downloads("clv_results", {"CLV": table}, "clv")
        except Exception as exc:
            show_error(exc)


def page_equity(loaded: LoadedData | None) -> None:
    sig.header("Analysis 3", "Customer equity")
    st.caption(
        "What is your whole customer base worth? Fits a bell-shaped customer-acquisition curve to your history, "
        "then values current and future customers (Gupta, Lehmann & Stuart approach)."
    )
    data_help(("equity",), "equity")
    frame = chosen_table(loaded, "equity", preferred=("equity",))
    if frame is None:
        return
    c1, c2 = st.columns(2)
    with c1:
        period_col = column_select("Period", frame, "period", k("equity_period"))
    with c2:
        customer_col = column_select("Number of current customers", frame, "customers", k("equity_customers"))
    c1, c2, c3 = st.columns(3)
    with c1:
        acquisition_cost = st.number_input("Acquisition cost per customer", min_value=0.0, value=120.0, key=k("eq_acq"))
        margin = st.number_input("Net margin per period", min_value=0.0, value=100.0, key=k("eq_margin"))
    with c2:
        retention = st.number_input("Retention per period", min_value=0.0, max_value=1.0, value=0.90, key=k("eq_ret"))
        discount = st.number_input("Discount per period", min_value=0.0, value=0.10, key=k("eq_disc"))
    with c3:
        tax = st.number_input("Corporate tax rate", min_value=0.0, max_value=1.0, value=0.38, key=k("eq_tax"))
        forecast_periods = st.number_input("Future periods", min_value=10, value=100, key=k("eq_forecast_periods"))
        periods_per_year = st.number_input("Periods per year", min_value=1, value=4, key=k("eq_periods_per_year"))
    if st.button("Calculate customer equity", type="primary", key=k("run_equity")):
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
            fig = px.line(
                chart, x="period", y="customers", color="series", title="Acquired customers", template=sig.template(NS)
            )
            sig.chart(NS, fig, key=k("equity_chart"))
            st.dataframe(elasticities, width="stretch", hide_index=True)
            render_downloads(
                "customer_equity",
                {"Summary": summary, "History": result.history, "Forecast": result.forecast, "Elasticities": elasticities},
                "equity",
            )
        except Exception as exc:
            show_error(exc)


def page_budgets(loaded: LoadedData | None) -> None:
    sig.header("Analysis 4", "Optimal acquisition and retention budgets")
    st.caption(
        "How much should you spend to win a new customer versus keeping an existing one? "
        "Blattberg–Deighton spending optimization based on how your acquisition and retention rates respond to money."
    )
    st.info("No data file is needed here — type your current rates and spending directly.", icon="✍️")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Acquisition")
        A = st.number_input("Current spend per prospect", min_value=0.01, value=6.0, key=k("bd_acq_spend"))
        a = st.number_input(
            "Current acquisition rate", min_value=0.0001, max_value=0.9999, value=0.25, key=k("bd_acq_rate")
        )
        Ca = st.number_input(
            "Maximum possible acquisition rate", min_value=0.0002, max_value=1.0, value=0.45, key=k("bd_acq_ceiling")
        )
    with c2:
        st.subheader("Retention")
        R = st.number_input("Current retention spend per customer", min_value=0.01, value=10.0, key=k("bd_ret_spend"))
        r = st.number_input(
            "Current retention rate", min_value=0.0001, max_value=0.9999, value=0.50, key=k("bd_ret_rate")
        )
        Cr = st.number_input(
            "Maximum possible retention rate", min_value=0.0002, max_value=1.0, value=0.80, key=k("bd_ret_ceiling")
        )
    c1, c2 = st.columns(2)
    with c1:
        margin = st.number_input("Profit margin per period", min_value=0.0, value=60.0, key=k("bd_margin"))
    with c2:
        discount = st.number_input("Discount rate", min_value=0.0, value=0.10, key=k("bd_discount"))
    if st.button("Optimize budgets", type="primary", key=k("run_budgets")):
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


def page_markov(loaded: LoadedData | None) -> None:
    sig.header("Analysis 5", "Markov customer equity and ROI")
    st.caption(
        "Is a marketing investment worth it when customers switch between competing brands? "
        "Models brand switching as transition probabilities and values the shift they cause "
        "(Rust, Lemon & Zeithaml return-on-marketing approach)."
    )
    st.info("No data file is needed here — fill in the switching probabilities directly.", icon="✍️")
    companies = st.number_input("Number of companies", min_value=2, max_value=5, value=2, key=k("markov_companies"))
    n = int(companies)
    default_old = np.eye(n) * 0.7 + (np.ones((n, n)) - np.eye(n)) * (0.3 / (n - 1))
    default_new = default_old.copy()
    if n == 2:
        default_old = np.array([[0.75, 0.25], [0.2, 0.8]])
        default_new = np.array([[0.8, 0.2], [0.15, 0.85]])
    c1, c2 = st.columns(2)
    with c1:
        st.write("Current transition matrix (rows = previous choice)")
        old_df = st.data_editor(pd.DataFrame(default_old), key=k(f"old_matrix_{n}"), width="stretch")
    with c2:
        st.write("New transition matrix after investment")
        new_df = st.data_editor(pd.DataFrame(default_new), key=k(f"new_matrix_{n}"), width="stretch")
    weights = st.data_editor(
        pd.DataFrame({"previous_choice_weight": np.repeat(1 / n, n)}), key=k(f"weights_{n}"), width="stretch"
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        focal = st.selectbox("Focal company", list(range(1, n + 1)), key=k("markov_focal")) - 1
        amount = st.number_input("Amount per purchase", min_value=0.0, value=120.0, key=k("markov_amount"))
        profit_margin = st.number_input(
            "Net profit margin", min_value=0.0, max_value=1.0, value=0.25, key=k("markov_profit_margin")
        )
    with c2:
        frequency = st.number_input("Purchases per year", min_value=0.01, value=2.0, key=k("markov_frequency"))
        horizon = st.number_input("Planning horizon (years)", min_value=0.0, value=4.0, key=k("markov_horizon"))
        discount = st.number_input("Annual discount rate", min_value=0.0, value=0.10, key=k("markov_discount"))
    with c3:
        industry = st.number_input("Customers in industry", min_value=1.0, value=500_000.0, key=k("markov_industry"))
        investment = st.number_input("Marketing investment", min_value=0.0, value=5_000_000.0, key=k("markov_investment"))
    if st.button("Calculate Markov ROI", type="primary", key=k("run_markov")):
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
            fig = px.line(path, x="years_from_now", y="choice_probability", markers=True, template=sig.template(NS))
            sig.chart(NS, fig, key=k("markov_chart"))
            render_downloads("markov_roi", {"ROI": table, "New choice path": path}, "markov")
        except Exception as exc:
            show_error(exc)


def page_contractual(loaded: LoadedData | None) -> None:
    sig.header("Analysis 6", "Contractual retention forecasting")
    st.caption(
        "How long do subscribers stay? Fits the shifted beta-geometric model (Fader & Hardie) to your "
        "survival counts — far more reliable than extending a straight line through past retention rates."
    )
    data_help(("contractual_survival",), "contractual")
    frame = chosen_table(loaded, "contractual", preferred=("contractual_survival",))
    if frame is None:
        return
    c1, c2 = st.columns(2)
    with c1:
        period = column_select("Period (0, 1, 2, …)", frame, "period", k("contract_period"))
    with c2:
        survivors = column_select("Surviving customers", frame, "customers", k("contract_survivors"))
    horizon = st.number_input("Forecast through period", min_value=3, value=20, key=k("contract_horizon"))
    if st.button("Forecast retention", type="primary", key=k("run_contractual")):
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
            st.dataframe(params, width="stretch", hide_index=True)
            chart = forecast.melt("period", ["actual_survival", "predicted_survival"], var_name="series", value_name="survival")
            fig = px.line(chart, x="period", y="survival", color="series", markers=True, template=sig.template(NS))
            sig.chart(NS, fig, key=k("contractual_chart"))
            render_downloads("contractual_retention", {"Parameters": params, "Forecast": forecast}, "contractual")
        except Exception as exc:
            show_error(exc)


def page_bgnbd(loaded: LoadedData | None) -> None:
    sig.header("Analysis 7", "BG/NBD continuous-time customer base analysis")
    st.caption(
        "Which customers are still active when they never tell you they left? The BG/NBD model "
        "(Fader, Hardie & Lee) estimates each customer's probability of being active and their expected "
        "future purchases, from purchase history alone."
    )
    data_help(("bgnbd_summary", "transactions"), "bgnbd")
    frame = chosen_table(loaded, "bgnbd", preferred=("bgnbd_summary", "bgnbd", "transactions"))
    if frame is None:
        return
    source = st.radio(
        "Input format", ["Summary columns x, tx, T", "Transaction rows"], horizontal=True, key=k("bgnbd_source")
    )
    if source.startswith("Transaction"):
        c1, c2 = st.columns(2)
        with c1:
            customer = column_select("Customer ID", frame, "customer_id", k("bgnbd_id"))
        with c2:
            purchase_date = column_select("Purchase date", frame, "date", k("bgnbd_date"))
        unit = st.selectbox("Time unit", ["weeks", "days", "months"], key=k("bgnbd_unit"))
        default_end = latest_valid_date(frame, purchase_date)
        end = st.date_input("Observation end", value=default_end, key=k(f"bgnbd_end_{default_end}"))
        try:
            require_distinct({"customer ID": customer, "purchase date": purchase_date})
            date_series(frame, purchase_date, "purchase date")
            summary = summarize_transactions(frame, customer, purchase_date, end, unit)
        except Exception as exc:
            show_error(exc)
            return
        x_col, tx_col, T_col = "x", "tx", "T"
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            x_col = column_select("x: repeat purchases", frame, "frequency", k("bgnbd_x"))
        with c2:
            tx_col = column_select("tx: time of last repeat purchase", frame, "tx", k("bgnbd_tx"))
        with c3:
            T_col = column_select("T: observation length", frame, "T", k("bgnbd_T"))
        summary = frame
    weight = column_select("Optional count/weight column", summary, "weight", k("bgnbd_weight"), True)
    horizon = st.number_input("Future horizon (same time unit)", min_value=0.0, value=39.0, key=k("bgnbd_horizon"))
    if st.button("Fit BG/NBD and score customers", type="primary", key=k("run_bgnbd")):
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
            fig = px.scatter(scored, x=tx_col, y="expected_future_purchases", color=x_col, template=sig.template(NS))
            sig.chart(NS, fig, key=k("bgnbd_chart"))
            render_downloads("bgnbd_results", {"Parameters": parameter_table, "Customer scores": scored}, "bgnbd")
        except Exception as exc:
            show_error(exc)


def page_bgbb(loaded: LoadedData | None) -> None:
    sig.header("Analysis 8", "BG/BB discrete-time customer base analysis")
    st.caption(
        "Which customers are still active when you observe fixed periods — years of donations, "
        "seasons of ticket buying? The BG/BB model (Fader, Hardie & Shang) estimates who is still "
        "alive and how many future purchases to expect."
    )
    data_help(("bgbb_histories",), "bgbb")
    frame = chosen_table(loaded, "bgbb", preferred=("bgbb_histories",))
    if frame is None:
        return
    source = st.radio(
        "Input format", ["Summary columns n, tx, x", "One 0/1 column per period"], horizontal=True, key=k("bgbb_source")
    )
    period_columns: list = []
    if source.startswith("One"):
        period_columns = st.multiselect(
            "Period columns in chronological order", list(frame.columns), key=k("bgbb_period_columns")
        )
        try:
            summary = summary_from_binary_periods(frame, period_columns) if period_columns else frame
        except Exception as exc:
            show_error(exc)
            return
        n_col, tx_col, x_col = "n", "tx", "x"
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            n_col = column_select("n: observed periods", frame, "customers", k("bgbb_n"))
        with c2:
            tx_col = column_select("tx: period of last purchase", frame, "tx", k("bgbb_tx"))
        with c3:
            x_col = column_select("x: repeat purchases", frame, "frequency", k("bgbb_x"))
        summary = frame
    weight = column_select("Optional count/weight column", summary, "weight", k("bgbb_weight"), True)
    future = st.number_input("Future periods", min_value=0, value=5, key=k("bgbb_future"))
    if st.button("Fit BG/BB and score customers", type="primary", key=k("run_bgbb")):
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
            fig = px.scatter(scored, x=tx_col, y="expected_future_purchases", color=x_col, template=sig.template(NS))
            sig.chart(NS, fig, key=k("bgbb_chart"))
            render_downloads("bgbb_results", {"Parameters": parameter_table, "Customer scores": scored}, "bgbb")
        except Exception as exc:
            show_error(exc)


def page_complaints(loaded: LoadedData | None) -> None:
    sig.header("Analysis 9", "Complaints and recovery")
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
                customer = column_select("Customer ID", frame, "customer_id", k("complaint_id"))
            with c2:
                event_date = column_select("Event date", frame, "date", k("complaint_date"))
            with c3:
                event_type = column_select("Event type (purchase / complaint)", frame, "event_type", k("complaint_type"))
            unit = st.selectbox("Time unit", ["weeks", "days", "months"], key=k("complaint_unit"))
            default_end = latest_valid_date(frame, event_date)
            end = st.date_input("Observation end", value=default_end, key=k(f"complaint_end_{default_end}"))
            if st.button("Prepare six summary statistics", type="primary", key=k("run_complaint_inputs")):
                try:
                    require_distinct({"customer ID": customer, "event date": event_date, "event type": event_type})
                    date_series(frame, event_date, "event date")
                    summary = complaint_summary(frame, customer, event_date, event_type, end, unit)
                    st.dataframe(summary, width="stretch", hide_index=True)
                    render_downloads("complaint_model_inputs", {"Customer summaries": summary}, "complaint_inputs")
                except Exception as exc:
                    show_error(exc)
    with tab2:
        future_value = st.number_input(
            "Future value if the customer stays", min_value=0.0, value=250.0, key=k("recovery_future_value")
        )
        recovered = st.number_input(
            "Stay probability with recovery", min_value=0.0, max_value=1.0, value=0.85, key=k("recovery_recovered")
        )
        unrecovered = st.number_input(
            "Stay probability without recovery", min_value=0.0, max_value=1.0, value=0.55, key=k("recovery_unrecovered")
        )
        cost = st.number_input("Proposed recovery cost", min_value=0.0, value=25.0, key=k("recovery_cost"))
        if st.button("Value recovery", type="primary", key=k("run_recovery")):
            values = recovery_value(future_value, recovered, unrecovered, cost)
            table = pd.DataFrame([values])
            c1, c2 = st.columns(2)
            c1.metric("Maximum justified recovery cost", fmt_number(values["maximum_financially_justified_recovery_cost"]))
            c2.metric("Net value of recovery", fmt_number(values["net_value_of_recovery"]))
            render_downloads("recovery_value", {"Recovery value": table}, "recovery")


def page_about(loaded: LoadedData | None) -> None:
    sig.header("About", "About Worth Signal")
    sig.note("warn", MODEL_WARNING)
    st.markdown(
        """
        ### What it is

        Worth Signal turns a customer data file — Excel, CSV, or JSON — into the classic
        customer-value analyses: segmentation, targeting, lifetime value, retention forecasting, and
        marketing ROI. It is built to be usable without a statistics background: upload a file, confirm
        the suggested columns, press a button. When you run it locally, your data stays on your computer,
        and your source file is never changed. On a hosted deployment, uploads are processed by that host;
        Worth Signal itself adds no accounts, telemetry, or persistent customer-data storage. See `PRIVACY.md`.

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

        The project is free software under the **AGPL-3.0-or-later** license. Commercial use is allowed.
        If you distribute the original or a modified version, the corresponding-source and license
        conditions apply. If users interact with a modified version over a network, you must offer those
        users the corresponding source for that version. Private modifications do not have to be posted
        publicly merely because they were made. The full `LICENSE` text controls; this is only a practical
        summary. Improvements are welcome — see `CONTRIBUTING.md` in the repository.

        The license covers this app's code. The statistical models it implements are the published
        work of the researchers cited on each page and in `docs/methods.md` — this project claims no
        ownership of the theory.

        **Source:** [github.com/UlrikErlingsen/customer-value-analytics](https://github.com/UlrikErlingsen/customer-value-analytics)
        """
    )


PAGES = {
    "Start & data check": page_start,
    "Customer selection": page_selection,
    "Customer lifetime value": page_clv,
    "Customer equity": page_equity,
    "Acquisition & retention budgets": page_budgets,
    "Markov ROI": page_markov,
    "Contractual retention": page_contractual,
    "BG/NBD continuous time": page_bgnbd,
    "BG/BB discrete time": page_bgbb,
    "Complaints & recovery": page_complaints,
    "About this app": page_about,
}


def _sidebar() -> tuple[str, LoadedData | None]:
    """Draw the sidebar lockup, upload, template download and page selector; return the page and parsed upload."""
    sig.sidebar_brand(NS, SIDEBAR_TAGLINE)
    loaded: LoadedData | None = None
    with st.sidebar:
        st.header("1. Bring your data")
        upload = st.file_uploader(
            "Excel, CSV, or JSON", type=["xlsx", "xls", "xlsm", "json", "csv"], key=k("upload_file")
        )
        if upload is not None:
            try:
                loaded = load_for_session(upload.getvalue(), upload.name)
                st.success(f"Loaded {upload.name}")
            except Exception as exc:
                st.error(f"Could not read the file: {exc}")
                st.caption(
                    "The file should have column names in its first row. "
                    "Supported: Excel (.xlsx, .xls, .xlsm), CSV, and JSON (a list of records, or named tables)."
                )
        else:
            loaded = st.session_state[k("demo")]
            st.info("Showing the **fictional demo workbook**. Upload a file to replace it.")
            st.download_button(
                "Download the demo workbook",
                data=cached_template_workbook(None, True),
                file_name=DEMO_FILENAME,
                mime=XLSX_MIME,
                key=k("download_quick_test"),
            )
            st.caption(
                "One fictional example sheet per analysis — replace the rows with your own data "
                "and upload it to analyse your customers."
            )
        st.header("2. Choose your lens")
        page = st.radio("Analysis", list(PAGES), label_visibility="collapsed", key=k("page"))
    return page, loaded


def render() -> None:
    """Draw the whole Worth Signal app on the current page. Never calls st.set_page_config or st.navigation."""
    sig.apply(NS)
    _ensure_state()
    page, loaded = _sidebar()
    sig.masthead(NS, MASTHEAD_PROMISES, MASTHEAD_KICKER)
    try:
        PAGES[page](loaded)
    except Exception as exc:
        show_error(exc)
    sig.footer(NS, __version__, FOOTER_LINE)
