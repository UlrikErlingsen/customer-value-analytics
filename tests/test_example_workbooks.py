"""The shipped example workbooks must work end to end, exactly as a user would use them.

These tests mirror what the app does after an upload: load the workbook, take the
sheet each analysis needs, and run the full computation on it.
"""

from pathlib import Path

import pytest

from cva.contractual import contractual_forecast
from cva.bgbb import score_bgbb
from cva.bgnbd import score_bgnbd, summarize_transactions
from cva.complaints import complaint_summary
from cva.equity import customer_equity
from cva.io import load_data
from cva.selection import fit_decision_tree, fit_logistic, lift_table, rfm_from_transactions, rfm_scores, targeting_profit

EXAMPLES = Path(__file__).parents[1] / "examples"


@pytest.fixture(scope="module", params=["quick_test.xlsx", "example_data.xlsx"])
def workbook(request):
    return load_data(EXAMPLES / request.param).tables


def test_workbook_has_all_template_sheets(workbook):
    expected = {
        "transactions", "rfm_customers", "response_model", "equity",
        "contractual_survival", "bgnbd_summary", "bgbb_histories", "events",
    }
    assert expected <= set(workbook)


def test_rfm_from_transactions_sheet(workbook):
    frame = workbook["transactions"]
    metrics = rfm_from_transactions(frame, "customer_id", "purchase_date", "amount", "2025-06-30")
    scored = rfm_scores(metrics, "recency_days", "frequency_per_month", "monetary_average", nested=True)
    assert scored["RFM_segment"].notna().all()


def test_rfm_customers_sheet(workbook):
    scored = rfm_scores(workbook["rfm_customers"], "recency_days", "frequency_per_month", "monetary_average")
    assert set(scored["R_score"].unique()) <= {1, 2, 3, 4, 5}


def test_response_model_sheet(workbook):
    frame = workbook["response_model"]
    predictors = ["recency_days", "purchases_last_year", "average_amount", "months_as_customer", "newsletter"]
    logistic = fit_logistic(frame, "response", predictors)
    tree = fit_decision_tree(frame, "response", predictors, 4, 10)
    for fitted in [logistic, tree]:
        targeting, summary = targeting_profit(frame["response"], fitted.predictions, 20.0, -1.0)
        assert 0 <= summary["threshold"] <= 1
        assert len(targeting) == len(frame)
    assert (lift_table(frame["response"], logistic.predictions)["lift"] >= 0).all()


def test_equity_sheet(workbook):
    frame = workbook["equity"]
    result = customer_equity(frame["period"].to_numpy(), frame["customers"].to_numpy(), 100, 80, 0.84, 0.12, 0.38, 50)
    assert result.summary.customer_equity > 0


def test_contractual_sheet(workbook):
    frame = workbook["contractual_survival"]
    fit, forecast, _ = contractual_forecast(frame["period"], frame["survivors"], 20)
    assert fit.success
    assert forecast["predicted_survival"].between(0, 1).all()


def test_bgnbd_sheets(workbook):
    params, scored = score_bgnbd(workbook["bgnbd_summary"], "x", "tx", "T", 39)
    assert params.success
    assert scored["probability_active"].between(0, 1).all()
    summary = summarize_transactions(workbook["transactions"], "customer_id", "purchase_date", "2025-06-30", "weeks")
    assert {"x", "tx", "T"} <= set(summary.columns)
    assert (summary["T"] >= summary["tx"]).all()
    # The app's "Transaction rows" path continues straight into a fit — test that too.
    derived_params, derived_scored = score_bgnbd(summary, "x", "tx", "T", 39)
    assert derived_params.success
    assert derived_scored["probability_active"].between(0, 1).all()


def test_bgbb_sheet(workbook):
    params, scored = score_bgbb(workbook["bgbb_histories"], "n", "tx", "x", 5, "count")
    assert params.success
    assert scored["probability_alive"].between(0, 1).all()


def test_events_sheet(workbook):
    summary = complaint_summary(workbook["events"], "customer_id", "event_date", "event_type", "2025-06-01")
    assert len(summary) == workbook["events"]["customer_id"].nunique()
