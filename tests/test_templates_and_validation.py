"""Tests for the data templates and the friendly validation layer."""

import io

import pandas as pd
import pytest

from cva.io import load_data
from cva.templates import TEMPLATES, example_frames, example_json, template_csv, template_workbook
from cva.validation import (
    DataProblem,
    binary_series,
    date_series,
    friendly_message,
    numeric_series,
    require_distinct,
    skipped_rows_note,
)


def test_every_template_has_matching_example_columns():
    frames = example_frames(small=True)
    for key, spec in TEMPLATES.items():
        frame = frames[key]
        assert not frame.empty, key
        expected = [column.name for column in spec.columns]
        assert list(frame.columns) == expected, key


def test_template_workbook_roundtrips_through_loader():
    workbook = template_workbook(small=True)
    loaded = load_data(io.BytesIO(workbook), "template.xlsx")
    sheet_names = {spec.sheet_name for spec in TEMPLATES.values()}
    assert sheet_names <= set(loaded.tables)
    assert "READ ME" in loaded.tables
    assert not loaded.tables["transactions"].empty


def test_template_csv_roundtrips_through_loader():
    loaded = load_data(io.BytesIO(template_csv("transactions")), "transactions.csv")
    assert list(loaded.tables["data"].columns) == ["customer_id", "purchase_date", "amount"]


def test_example_json_keeps_historical_keys():
    loaded = load_data(io.BytesIO(example_json()), "example.json")
    assert {"equity", "contractual_survival", "bgnbd", "bgbb_histories", "events"} <= set(loaded.tables)


def test_template_columns_are_auto_suggested_for_their_roles():
    """The app must auto-map every template column to the role its page asks for."""
    from cva.schema import suggest_column

    expectations = {
        "transactions": [("customer_id", "customer_id"), ("date", "purchase_date"), ("amount", "amount")],
        "rfm_customers": [
            ("recency", "recency_days"),
            ("frequency", "frequency_per_month"),
            ("monetary", "monetary_average"),
            ("response", "response"),
        ],
        "response_model": [("response", "response")],
        "equity": [("period", "period"), ("customers", "customers")],
        "contractual_survival": [("period", "period"), ("customers", "survivors")],
        "bgnbd_summary": [("frequency", "x"), ("tx", "tx"), ("T", "T")],
        "bgbb_histories": [("customers", "n"), ("tx", "tx"), ("frequency", "x"), ("weight", "count")],
        "events": [("customer_id", "customer_id"), ("date", "event_date"), ("event_type", "event_type")],
    }
    frames = example_frames(small=True)
    for key, pairs in expectations.items():
        columns = list(frames[key].columns)
        for role, expected in pairs:
            assert suggest_column(columns, role) == expected, (key, role)


def test_derived_rfm_metrics_never_suggest_a_response_column():
    """Regression: 'last_purchase' (a date) must not be auto-picked as the 0/1 response."""
    from cva.schema import suggest_column
    from cva.selection import rfm_from_transactions

    frame = example_frames(small=True)["transactions"]
    metrics = rfm_from_transactions(frame, "customer_id", "purchase_date", "amount", "2025-06-30")
    suggestion = suggest_column(metrics.columns, "response")
    assert suggestion is None, f"suggested {suggestion!r} from {list(metrics.columns)}"


def test_numeric_series_explains_text_columns():
    frame = pd.DataFrame({"amount": ["kr 100,50", "kr 200,00"]})
    with pytest.raises(DataProblem) as excinfo:
        numeric_series(frame, "amount", "transaction amount")
    assert "amount" in str(excinfo.value)
    assert "kr 100,50" in str(excinfo.value)


def test_numeric_series_passes_numbers_and_notes_skips():
    frame = pd.DataFrame({"amount": [1, "x", 3]})
    series = numeric_series(frame, "amount", "amount")
    assert series.notna().sum() == 2
    assert "1 of 3" in skipped_rows_note(series, "amount")
    assert skipped_rows_note(numeric_series(pd.DataFrame({"a": [1, 2]}), "a", "a"), "a") is None


def test_numeric_series_rejects_missing_column():
    with pytest.raises(DataProblem):
        numeric_series(pd.DataFrame({"a": [1]}), "b", "period")


def test_numeric_series_distinguishes_too_few_rows_from_unreadable():
    frame = pd.DataFrame({"a": [1, 2, 3]})
    message = str(pytest.raises(DataProblem, numeric_series, frame, "a", "period", 5).value)
    assert "at least 5" in message
    assert "currency" not in message


def test_date_series_accepts_dates_and_rejects_text():
    frame = pd.DataFrame({"good": ["2025-01-02", "2025-02-03"], "bad": ["hello", "world"]})
    assert date_series(frame, "good", "date").notna().all()
    with pytest.raises(DataProblem):
        date_series(frame, "bad", "date")


def test_binary_series_accepts_yes_no_and_rejects_other_values():
    frame = pd.DataFrame({"resp": ["yes", "no", "yes"], "score": [1, 2, 3]})
    assert binary_series(frame, "resp", "response").tolist() == [1, 0, 1]
    with pytest.raises(DataProblem):
        binary_series(frame, "score", "response")


def test_require_distinct_rejects_duplicates():
    require_distinct({"recency": "r", "frequency": "f", "optional": None})
    with pytest.raises(DataProblem):
        require_distinct({"recency": "r", "frequency": "r"})


def test_friendly_message_translates_common_failures():
    assert "column" in friendly_message(KeyError("amount")).lower()
    assert "text" in friendly_message(ValueError("could not convert string to float: 'abc'"))
    problem = DataProblem("Something specific.", "Do this.")
    assert friendly_message(problem) == "Something specific. Do this."
