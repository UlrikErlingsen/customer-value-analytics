"""Complaint and service-recovery analytics for a customer base.

Business question: how do complaints sit alongside repeat purchasing, and how much
is it worth spending to win back a complaining customer? `complaint_summary`
condenses a purchase/complaint event log into per-customer counts in the spirit of
the customer-base complaint model of Knox & van Oest (2014, "Customer Complaints
and Recovery Effectiveness: A Customer Base Approach", Journal of Marketing).
`recovery_value` compares expected customer value with and without a successful
recovery to put a ceiling on justifiable recovery spending.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def complaint_summary(
    events: pd.DataFrame,
    customer_id: str,
    event_date: str,
    event_type: str,
    observation_end: str | pd.Timestamp | None = None,
    time_unit: str = "weeks",
) -> pd.DataFrame:
    """Summarize a purchase/complaint event log into one row per customer.

    Event types containing "purchase" or "order" count as purchases; types containing
    "complaint" count as complaints. Per customer (measured from the first purchase, in
    the chosen time unit): repeat-purchase count, complaints filed on a purchase day vs.
    other days, time of the last event, whether the last event involves a complaint, and
    the observation length up to `observation_end` (default: the latest date in the data).
    Customers with no purchases are skipped.
    """
    data = events[[customer_id, event_date, event_type]].copy()
    data[event_date] = pd.to_datetime(data[event_date], errors="coerce")
    data[event_type] = data[event_type].astype(str).str.strip().str.lower()
    data = data.dropna(subset=[customer_id, event_date]).sort_values([customer_id, event_date])
    if data.empty:
        raise ValueError("No valid event rows remain after parsing.")
    divisor = {"days": 1.0, "weeks": 7.0, "months": 30.4375}.get(time_unit)
    if divisor is None:
        raise ValueError("Time unit must be days, weeks, or months.")
    end = pd.Timestamp(observation_end) if observation_end is not None else data[event_date].max()
    rows = []
    for customer, group in data.groupby(customer_id):
        purchases = group[group[event_type].str.contains("purchase|order", regex=True)]
        complaints = group[group[event_type].str.contains("complaint", regex=True)]
        if purchases.empty:
            continue
        initial = purchases[event_date].min()
        repeat_purchases = max(len(purchases) - 1, 0)
        purchase_days = set(purchases[event_date].dt.normalize())
        same_day = int(complaints[event_date].dt.normalize().isin(purchase_days).sum())
        other = int(len(complaints) - same_day)
        last_event = group[event_date].max()
        last_rows = group[group[event_date] == last_event]
        last_is_complaint = int(last_rows[event_type].str.contains("complaint").any())
        rows.append(
            {
                customer_id: customer,
                "xp_repeat_purchases": repeat_purchases,
                "xc_given_p_same_day_complaints": same_day,
                "xc_other_complaints": other,
                "tx_last_event": (last_event - initial).days / divisor,
                "zc_last_event_involves_complaint": last_is_complaint,
                "T_observation_length": (end - initial).days / divisor,
            }
        )
    return pd.DataFrame(rows)


def recovery_value(
    future_value_if_customer_stays: float,
    stay_probability_recovered: float,
    stay_probability_unrecovered: float,
    recovery_cost: float = 0.0,
) -> dict[str, float]:
    """Value a service-recovery effort for one complaining customer.

    Compares expected future value if the recovery succeeds vs. if it does not; the
    difference is the maximum spend a recovery can financially justify, and subtracting
    the entered `recovery_cost` gives the net value of attempting it.
    """
    if future_value_if_customer_stays < 0 or not 0 <= stay_probability_recovered <= 1 or not 0 <= stay_probability_unrecovered <= 1:
        raise ValueError("Future value must be non-negative and probabilities must be between 0 and 1.")
    recovered_clv = future_value_if_customer_stays * stay_probability_recovered
    unrecovered_clv = future_value_if_customer_stays * stay_probability_unrecovered
    maximum_cost = recovered_clv - unrecovered_clv
    return {
        "clv_if_recovered": recovered_clv,
        "clv_if_unrecovered": unrecovered_clv,
        "maximum_financially_justified_recovery_cost": maximum_cost,
        "entered_recovery_cost": recovery_cost,
        "net_value_of_recovery": maximum_cost - recovery_cost,
    }
