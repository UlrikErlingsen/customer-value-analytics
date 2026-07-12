"""Ready-made data templates and example datasets.

Every analysis in the app expects a table of a particular shape. This module
defines those shapes in one place: column names, plain-language descriptions,
and small realistic example tables. The app uses it for its "Download
template" buttons, and ``scripts/generate_examples.py`` uses it to build the
files in ``examples/``. Keeping templates, examples, and documentation in one
module guarantees they can never drift apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cva.io import results_to_excel


@dataclass(frozen=True)
class ColumnSpec:
    """One template column: its name and what to put in it."""

    name: str
    description: str


@dataclass(frozen=True)
class TemplateSpec:
    """One uploadable table shape used by an analysis page."""

    key: str
    sheet_name: str
    title: str
    purpose: str
    used_by: tuple[str, ...]
    columns: tuple[ColumnSpec, ...]


TEMPLATES: dict[str, TemplateSpec] = {
    spec.key: spec
    for spec in [
        TemplateSpec(
            key="transactions",
            sheet_name="transactions",
            title="Transaction log",
            purpose="One row per purchase. The app turns this into RFM metrics or BG/NBD inputs for you.",
            used_by=("Customer selection", "BG/NBD continuous time"),
            columns=(
                ColumnSpec("customer_id", "Any identifier for the customer (number, code, or name)."),
                ColumnSpec("purchase_date", "The date of the purchase, e.g. 2025-03-14."),
                ColumnSpec("amount", "What the purchase was worth, as a plain number without currency symbols."),
            ),
        ),
        TemplateSpec(
            key="rfm_customers",
            sheet_name="rfm_customers",
            title="Customer-level RFM metrics",
            purpose="One row per customer with recency, frequency, and monetary value already computed.",
            used_by=("Customer selection",),
            columns=(
                ColumnSpec("customer_id", "Any identifier for the customer."),
                ColumnSpec("recency_days", "Days since the customer's last purchase. Lower is better."),
                ColumnSpec("frequency_per_month", "Average purchases per month. Higher is better."),
                ColumnSpec("monetary_average", "Average amount per purchase. Higher is better."),
                ColumnSpec("response", "Optional: 1 if the customer responded to a campaign, 0 if not."),
            ),
        ),
        TemplateSpec(
            key="response_model",
            sheet_name="response_model",
            title="Campaign response data",
            purpose="One row per customer with an observed 0/1 outcome and anything that might predict it.",
            used_by=("Customer selection",),
            columns=(
                ColumnSpec("customer_id", "Any identifier for the customer."),
                ColumnSpec("recency_days", "Example predictor: days since last purchase."),
                ColumnSpec("purchases_last_year", "Example predictor: number of purchases in the last year."),
                ColumnSpec("average_amount", "Example predictor: average purchase amount."),
                ColumnSpec("months_as_customer", "Example predictor: how long they have been a customer."),
                ColumnSpec("newsletter", "Example predictor: 1 if subscribed to the newsletter, 0 if not."),
                ColumnSpec("response", "The outcome to predict: 1 = responded, 0 = did not."),
            ),
        ),
        TemplateSpec(
            key="equity",
            sheet_name="equity",
            title="Customer counts over time",
            purpose="One row per period with the number of active customers, for customer-equity valuation.",
            used_by=("Customer equity",),
            columns=(
                ColumnSpec("period", "Consecutive period numbers: 0, 1, 2, …"),
                ColumnSpec("customers", "How many active customers you had in that period."),
            ),
        ),
        TemplateSpec(
            key="contractual_survival",
            sheet_name="contractual_survival",
            title="Subscriber survival counts",
            purpose="How many of an original group of subscribers were still active after each period.",
            used_by=("Contractual retention",),
            columns=(
                ColumnSpec("period", "Periods since the group started: 0, 1, 2, … Period 0 is the full group."),
                ColumnSpec("survivors", "How many were still subscribed. Can never increase over time."),
            ),
        ),
        TemplateSpec(
            key="bgnbd_summary",
            sheet_name="bgnbd_summary",
            title="BG/NBD customer summaries",
            purpose="One row per customer summarising their repeat-purchase history in continuous time.",
            used_by=("BG/NBD continuous time",),
            columns=(
                ColumnSpec("customer_id", "Any identifier for the customer."),
                ColumnSpec("x", "Number of repeat purchases (the first purchase does not count)."),
                ColumnSpec("tx", "Time from first purchase to the last repeat purchase. 0 when x is 0."),
                ColumnSpec("T", "Time from first purchase to the end of the observation window."),
            ),
        ),
        TemplateSpec(
            key="bgbb_histories",
            sheet_name="bgbb_histories",
            title="BG/BB purchase histories",
            purpose="Repeat-purchase histories in discrete periods; identical histories may be grouped with a count.",
            used_by=("BG/BB discrete time",),
            columns=(
                ColumnSpec("n", "Number of observed periods after the first purchase."),
                ColumnSpec("tx", "Period of the last repeat purchase. 0 when there was none."),
                ColumnSpec("x", "Number of repeat purchases."),
                ColumnSpec("count", "Optional: how many customers share this exact history."),
            ),
        ),
        TemplateSpec(
            key="events",
            sheet_name="events",
            title="Purchase and complaint events",
            purpose="One row per event, mixing purchases and complaints, for complaint-model input preparation.",
            used_by=("Complaints & recovery",),
            columns=(
                ColumnSpec("customer_id", "Any identifier for the customer."),
                ColumnSpec("event_date", "The date of the event, e.g. 2025-03-14."),
                ColumnSpec("event_type", "Text containing 'purchase' (or 'order') or 'complaint'."),
            ),
        ),
    ]
}


def _example_transactions(n_customers: int, seed: int = 11) -> pd.DataFrame:
    """Deterministic, realistic-looking transaction log."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2025-06-30")
    rows = []
    for i in range(n_customers):
        first = start + pd.Timedelta(days=float(rng.uniform(0, 330)))
        date = first
        for _ in range(1 + int(rng.poisson(2.2))):
            if date > end:
                break
            rows.append(
                {
                    "customer_id": f"C{i + 1:03d}",
                    "purchase_date": date.date().isoformat(),
                    "amount": float(np.round(rng.lognormal(3.9, 0.5), 2)),
                }
            )
            date = date + pd.Timedelta(days=float(rng.exponential(70)) + 1)
    return pd.DataFrame(rows)


def _example_rfm_customers(n_customers: int, seed: int = 12) -> pd.DataFrame:
    """Deterministic customer-level RFM metrics with a plausible response pattern."""
    rng = np.random.default_rng(seed)
    recency = np.round(rng.lognormal(4.0, 0.9, n_customers)).clip(1, 720)
    frequency = np.round(rng.lognormal(0.0, 0.7, n_customers), 2).clip(0.05, 12)
    monetary = np.round(rng.lognormal(4.2, 0.6, n_customers), 2)
    utility = -0.8 - 0.006 * recency + 0.45 * frequency + 0.002 * monetary
    response = (rng.uniform(size=n_customers) < 1 / (1 + np.exp(-utility))).astype(int)
    return pd.DataFrame(
        {
            "customer_id": [f"C{i + 1:03d}" for i in range(n_customers)],
            "recency_days": recency.astype(int),
            "frequency_per_month": frequency,
            "monetary_average": monetary,
            "response": response,
        }
    )


def _example_response_model(n_customers: int, seed: int = 13) -> pd.DataFrame:
    """Deterministic campaign-response table where the predictors carry real signal."""
    rng = np.random.default_rng(seed)
    recency = np.round(rng.lognormal(4.0, 0.8, n_customers)).clip(1, 600)
    purchases = rng.poisson(3.0, n_customers)
    amount = np.round(rng.lognormal(4.0, 0.5, n_customers), 2)
    tenure = np.round(rng.uniform(1, 96, n_customers)).astype(int)
    newsletter = (rng.uniform(size=n_customers) < 0.4).astype(int)
    utility = -1.4 - 0.005 * recency + 0.22 * purchases + 0.003 * amount + 0.012 * tenure + 0.5 * newsletter
    response = (rng.uniform(size=n_customers) < 1 / (1 + np.exp(-utility))).astype(int)
    return pd.DataFrame(
        {
            "customer_id": [f"C{i + 1:03d}" for i in range(n_customers)],
            "recency_days": recency.astype(int),
            "purchases_last_year": purchases,
            "average_amount": amount,
            "months_as_customer": tenure,
            "newsletter": newsletter,
            "response": response,
        }
    )


# Reference tables shared by the JSON example, the Excel examples, and the
# test suite. The model-input examples reproduce well-behaved fits, so a
# first-time user always sees the app succeed.
_EQUITY = pd.DataFrame(
    {"period": range(10), "customers": [1000, 1080, 1210, 1410, 1680, 1980, 2250, 2440, 2530, 2510]}
)
# Survival counts from the published example in Fader & Hardie (2007, "How to
# Project Customer Retention"), originally from Berry & Linoff (2004).
_CONTRACTUAL = pd.DataFrame(
    {"period": range(8), "survivors": [1000, 631, 468, 382, 326, 289, 262, 241]}
)
_BGNBD = pd.DataFrame(
    {
        "customer_id": range(1, 13),
        "x": [2, 6, 0, 1, 3, 5, 1, 4, 7, 2, 0, 3],
        "tx": [12.0, 20.0, 0.0, 35.0, 30.0, 37.0, 2.0, 12.0, 38.0, 28.0, 0.0, 18.0],
        "T": [39.0, 39.0, 39.0, 39.0, 39.0, 39.0, 39.0, 39.0, 39.0, 39.0, 20.0, 25.0],
    }
)
_BGBB = pd.DataFrame(
    {
        "n": [6] * 15,
        "tx": [0, 1, 2, 3, 4, 5, 6, 2, 4, 6, 4, 6, 6, 6, 6],
        "x": [0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 4, 5, 6],
        "count": [1150, 310, 180, 125, 95, 80, 70, 130, 115, 105, 75, 85, 55, 30, 15],
    }
)
_EVENTS = pd.DataFrame(
    [
        {"customer_id": "A", "event_date": "2025-01-01", "event_type": "purchase"},
        {"customer_id": "A", "event_date": "2025-02-01", "event_type": "purchase"},
        {"customer_id": "A", "event_date": "2025-02-01", "event_type": "complaint"},
        {"customer_id": "A", "event_date": "2025-03-15", "event_type": "complaint"},
        {"customer_id": "B", "event_date": "2025-01-10", "event_type": "purchase"},
        {"customer_id": "B", "event_date": "2025-04-10", "event_type": "purchase"},
        {"customer_id": "C", "event_date": "2025-01-20", "event_type": "purchase"},
        {"customer_id": "C", "event_date": "2025-01-25", "event_type": "complaint"},
    ]
)


def example_frames(small: bool = False) -> dict[str, pd.DataFrame]:
    """All example tables keyed by template key.

    ``small=True`` returns a compact variant that still exercises every
    analysis, used for the two-minute quick-test file.
    """
    return {
        "transactions": _example_transactions(15 if small else 80),
        "rfm_customers": _example_rfm_customers(30 if small else 120),
        "response_model": _example_response_model(120 if small else 400),
        "equity": _EQUITY.copy(),
        "contractual_survival": _CONTRACTUAL.copy(),
        "bgnbd_summary": _BGNBD.copy(),
        "bgbb_histories": _BGBB.copy(),
        "events": _EVENTS.copy(),
    }


def readme_frame(keys: list[str]) -> pd.DataFrame:
    """One row per template column, for the READ ME sheet of a workbook."""
    rows = []
    for key in keys:
        spec = TEMPLATES[key]
        for index, column in enumerate(spec.columns):
            rows.append(
                {
                    "sheet": spec.sheet_name,
                    "what the sheet is for": spec.purpose if index == 0 else "",
                    "column": column.name,
                    "what to put in it": column.description,
                }
            )
    return pd.DataFrame(rows)


def template_workbook(keys: list[str] | None = None, small: bool = True) -> bytes:
    """An Excel workbook with a READ ME sheet plus one example sheet per template.

    Users replace the example rows with their own data and upload the file
    back into the app; the column names are already the ones the app
    recognises automatically.
    """
    keys = keys or list(TEMPLATES)
    frames = example_frames(small=small)
    tables: dict[str, pd.DataFrame] = {"READ ME": readme_frame(keys)}
    for key in keys:
        tables[TEMPLATES[key].sheet_name] = frames[key]
    return results_to_excel(tables)


def template_csv(key: str, small: bool = True) -> bytes:
    """A single template as CSV with example rows."""
    return example_frames(small=small)[key].to_csv(index=False).encode("utf-8")


def example_json(small: bool = False) -> bytes:
    """The multi-table example as JSON.

    Keeps the historical key ``bgnbd`` (rather than ``bgnbd_summary``) so
    existing files and tests keep working.
    """
    frames = example_frames(small=small)
    payload = {
        "transactions": frames["transactions"].to_dict(orient="records"),
        "rfm_customers": frames["rfm_customers"].to_dict(orient="records"),
        "response_model": frames["response_model"].to_dict(orient="records"),
        "equity": frames["equity"].to_dict(orient="records"),
        "contractual_survival": frames["contractual_survival"].to_dict(orient="records"),
        "bgnbd": frames["bgnbd_summary"].to_dict(orient="records"),
        "bgbb_histories": frames["bgbb_histories"].to_dict(orient="records"),
        "events": frames["events"].to_dict(orient="records"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
