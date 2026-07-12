"""Column-name suggestion for uploaded tables.

Each analysis needs columns in specific roles (customer id, date, amount, the
x/tx/T model inputs, ...). `SYNONYMS` maps each role to header spellings commonly
seen in the wild; `suggest_column` normalizes headers (lowercase, runs of
non-alphanumerics collapsed to "_") and returns the first exact synonym match,
falling back to prefix/substring matches. Suggestions only pre-fill selection
widgets — the user can always pick a different column.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


SYNONYMS: dict[str, tuple[str, ...]] = {
    "customer_id": ("customer_id", "customer", "client_id", "client", "cust_id", "user_id", "donor_id", "id"),
    "date": ("purchase_date", "transaction_date", "order_date", "event_date", "date", "timestamp"),
    "amount": ("total_amount", "amount", "revenue", "sales", "order_value", "monetary", "spend", "value"),
    "recency": ("recency", "recency_days", "days_since_last", "months_since_last", "r"),
    "frequency": ("frequency", "purchase_frequency", "orders_per_month", "transactions", "repeat_purchases", "x", "f"),
    "monetary": ("monetary", "avg_order_value", "average_amount", "spend", "revenue", "m"),
    # "purchase" is deliberately not a response synonym: derived columns like
    # "last_purchase" hold dates, and suggesting one as a 0/1 response would
    # silently corrupt segment response rates.
    "response": ("response", "responded", "outcome", "target", "converted", "y"),
    "period": ("period", "time", "quarter", "month", "year", "t"),
    "customers": ("customers", "customer_count", "active_customers", "survivors", "number_customers", "n_customers", "n"),
    "tx": ("tx", "t_x", "last_purchase_time", "recency_time", "last_event_period"),
    "T": ("T", "observation_period", "observation_length", "age", "tenure"),
    "weight": ("weight", "count", "customers", "n_customers", "frequency_count"),
    "event_type": ("event_type", "type", "event", "interaction_type"),
    "recovered": ("recovered", "recovery", "resolved", "complaint_recovered"),
}


def normalize_name(value: object) -> str:
    """Normalize a header for matching: lowercase, non-alphanumeric runs become single underscores."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def suggest_column(columns: Iterable[object], role: str) -> str | None:
    """Return the column that most likely fills `role`, or None if nothing matches.

    Tries the role's synonyms as exact normalized matches first, then as
    prefix/substring matches against the normalized headers.
    """
    original = [str(column) for column in columns]
    normalized = {normalize_name(column): column for column in original}
    candidates = SYNONYMS.get(role, (role,))
    for candidate in candidates:
        key = normalize_name(candidate)
        if key in normalized:
            return normalized[key]
    for candidate in candidates:
        key = normalize_name(candidate)
        # Short synonyms like "y", "x", or "tx" only count as exact matches above —
        # as prefixes/substrings they would match almost any header.
        if len(key) < 3:
            continue
        for normalized_name, original_name in normalized.items():
            if normalized_name.startswith(key) or (len(key) >= 4 and key in normalized_name):
                return original_name
    return None

