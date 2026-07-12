"""End-to-end tests over the bundled example dataset.

Each test loads examples/example_data.json and runs one analysis pipeline —
file loading and export, customer equity, contractual (sBG) retention, BG/NBD,
BG/BB, and complaint summarization — asserting that fits succeed and outputs
stay finite and within their valid ranges.
"""

from pathlib import Path

import numpy as np

from cva.bgbb import score_bgbb
from cva.bgnbd import score_bgnbd
from cva.complaints import complaint_summary
from cva.contractual import contractual_forecast
from cva.equity import customer_equity
from cva.io import load_data, results_to_excel, results_to_json


EXAMPLE = Path(__file__).parents[1] / "examples" / "example_data.json"


def test_example_json_and_exports():
    loaded = load_data(EXAMPLE)
    assert {"equity", "contractual_survival", "bgnbd", "bgbb_histories", "events"} <= set(loaded.tables)
    tables = {"Test": loaded.tables["equity"]}
    assert results_to_excel(tables)[:2] == b"PK"
    assert b'"Test"' in results_to_json(tables)


def test_equity_example_is_fitted_and_finite():
    frame = load_data(EXAMPLE).tables["equity"]
    result = customer_equity(
        frame["period"].to_numpy(), frame["customers"].to_numpy(), 100, 80, 0.84, 0.12, 0.38, 100
    )
    assert result.curve_fit.r_squared > 0.95
    assert np.isfinite(result.summary.customer_equity)
    assert len(result.forecast) == 100


def test_contractual_example_forecast():
    frame = load_data(EXAMPLE).tables["contractual_survival"]
    fit, forecast, metrics = contractual_forecast(frame["period"], frame["survivors"], 20)
    assert fit.success
    assert 0 < fit.alpha < 10
    assert forecast["predicted_survival"].between(0, 1).all()
    assert metrics["forecast_expected_lifetime"] > 1


def test_bgnbd_example_fit_and_scoring():
    frame = load_data(EXAMPLE).tables["bgnbd"]
    params, scored = score_bgnbd(frame, "x", "tx", "T", 39)
    assert params.success
    assert scored["probability_active"].between(0, 1).all()
    assert (scored["expected_future_purchases"] >= 0).all()


def test_bgbb_example_fit_and_scoring():
    frame = load_data(EXAMPLE).tables["bgbb_histories"]
    params, scored = score_bgbb(frame, "n", "tx", "x", 5, "count")
    assert params.success
    assert scored["probability_alive"].between(0, 1).all()
    assert (scored["expected_future_purchases"] >= 0).all()


def test_complaint_summary_fields():
    frame = load_data(EXAMPLE).tables["events"]
    summary = complaint_summary(frame, "customer_id", "event_date", "event_type", "2025-06-01")
    row_a = summary.loc[summary["customer_id"] == "A"].iloc[0]
    assert row_a["xp_repeat_purchases"] == 1
    assert row_a["xc_given_p_same_day_complaints"] == 1
    assert row_a["xc_other_complaints"] == 1
