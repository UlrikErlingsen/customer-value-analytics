"""BG/NBD model of repeat purchasing in a noncontractual, continuous-time setting.

Business question: which customers are probably still active, and how many purchases
will each make over a future horizon, when customers can silently walk away? While
active, a customer buys at a Poisson rate (Gamma-distributed across customers) and may
drop out after any purchase with a fixed probability (Beta-distributed across customers).
Inputs per customer: x = number of repeat purchases in the observation window,
tx = time of the last purchase, T = length of the window (both measured from the
first purchase, in the same time units).

Reference: Fader, Hardie & Lee (2005), "'Counting Your Customers' the Easy Way:
An Alternative to the Pareto/NBD Model", Marketing Science.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1, logsumexp


@dataclass(frozen=True)
class BGNBDParams:
    """Fitted BG/NBD parameters: Gamma(r, alpha) purchase rates, Beta(a, b) dropout probabilities."""

    r: float
    alpha: float
    a: float
    b: float
    log_likelihood: float
    success: bool

    def to_dict(self) -> dict[str, float | bool]:
        return asdict(self)


def bgnbd_log_likelihood(
    x: np.ndarray, tx: np.ndarray, T: np.ndarray, r: float, alpha: float, a: float, b: float
) -> np.ndarray:
    """Per-customer log-likelihood of the (x, tx, T) summary under parameters (r, alpha, a, b)."""
    x = np.asarray(x, dtype=float)
    tx = np.asarray(tx, dtype=float)
    T = np.asarray(T, dtype=float)
    if min(r, alpha, a, b) <= 0:
        return np.full_like(x, -np.inf)
    a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
    a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
    a3 = -(r + x) * np.log(alpha + T)
    dropout_denominator = np.where(x > 0, b + x - 1, 1.0)
    a4 = np.log(a) - np.log(dropout_denominator) - (r + x) * np.log(alpha + tx)
    a4 = np.where(x > 0, a4, -np.inf)
    return a1 + a2 + np.logaddexp(a3, a4)


def _validate_summary(x: np.ndarray, tx: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop non-finite rows and enforce x >= 0, 0 <= tx <= T, T > 0."""
    x = np.asarray(x, dtype=float)
    tx = np.asarray(tx, dtype=float)
    T = np.asarray(T, dtype=float)
    valid = np.isfinite(x) & np.isfinite(tx) & np.isfinite(T)
    x, tx, T = x[valid], tx[valid], T[valid]
    if len(x) == 0 or np.any(x < 0) or np.any(tx < 0) or np.any(T <= 0) or np.any(tx > T):
        raise ValueError("Require x >= 0, 0 <= tx <= T, and T > 0.")
    return x, tx, T


def fit_bgnbd(
    x: np.ndarray,
    tx: np.ndarray,
    T: np.ndarray,
    weights: np.ndarray | None = None,
) -> BGNBDParams:
    """Fit BG/NBD parameters by maximum likelihood on per-customer (x, tx, T) summaries.

    Optional `weights` allow aggregated inputs where one row represents several customers
    with identical histories. Optimizes in log-parameter space from several starting
    points and keeps the best solution.
    """
    x, tx, T = _validate_summary(x, tx, T)
    w = np.ones_like(x) if weights is None else np.asarray(weights, dtype=float)
    if len(w) != len(x) or np.any(w < 0):
        raise ValueError("Weights must be non-negative and match the number of rows.")

    def objective(log_params: np.ndarray) -> float:
        params = np.exp(log_params)
        ll = bgnbd_log_likelihood(x, tx, T, *params)
        value = np.dot(w, ll)
        return float(-value) if np.isfinite(value) else 1e100

    median_T = max(float(np.median(T)), 1e-3)
    starts = [
        [0.5, median_T / 2, 1.5, 3.0],
        [1.0, median_T, 2.0, 4.0],
        [0.2, median_T / 10, 0.8, 2.0],
        [2.0, median_T * 2, 3.0, 3.0],
    ]
    best = None
    for start in starts:
        result = minimize(objective, np.log(start), method="L-BFGS-B", bounds=[(-12, 16)] * 4)
        if best is None or result.fun < best.fun:
            best = result
    assert best is not None
    r, alpha, a, b = np.exp(best.x)
    return BGNBDParams(float(r), float(alpha), float(a), float(b), float(-best.fun), bool(best.success))


def probability_active(
    x: np.ndarray, tx: np.ndarray, T: np.ndarray, params: BGNBDParams
) -> np.ndarray:
    """Probability that each customer is still active at the end of the observation window.

    Customers with no repeat purchases (x = 0) cannot have dropped out under the model,
    so their probability is 1.
    """
    x, tx, T = _validate_summary(x, tx, T)
    factor = np.where(
        x > 0,
        params.a / (params.b + x - 1) * np.power((params.alpha + T) / (params.alpha + tx), params.r + x),
        0.0,
    )
    return 1 / (1 + factor)


def expected_future_purchases(
    x: np.ndarray,
    tx: np.ndarray,
    T: np.ndarray,
    horizon: float,
    params: BGNBDParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expected purchases per customer over the next `horizon` time units.

    Returns (probability_active, expected purchases conditional on being active,
    unconditional expected purchases). Uses the Gaussian hypergeometric expression
    from Fader, Hardie & Lee (2005).
    """
    if horizon < 0:
        raise ValueError("Future horizon cannot be negative.")
    x, tx, T = _validate_summary(x, tx, T)
    p_alive = probability_active(x, tx, T, params)
    if horizon == 0:
        zeros = np.zeros_like(x)
        return p_alive, zeros, zeros
    z = horizon / (params.alpha + T + horizon)
    hyper = hyp2f1(params.r + x, params.b + x, params.a + params.b + x - 1, z)
    bracket = 1 - np.power((params.alpha + T) / (params.alpha + T + horizon), params.r + x) * hyper
    active = (params.a + params.b + x - 1) / (params.a - 1) * bracket
    expected = p_alive * active
    invalid = ~np.isfinite(expected) | (expected < -1e-8)
    if invalid.any():
        raise ArithmeticError("BG/NBD future-purchase calculation became unstable for the fitted parameters.")
    return p_alive, np.maximum(active, 0), np.maximum(expected, 0)


def summarize_transactions(
    transactions: pd.DataFrame,
    customer_id: str,
    purchase_date: str,
    observation_end: str | pd.Timestamp | None = None,
    time_unit: str = "weeks",
) -> pd.DataFrame:
    """Collapse a raw transaction log into per-customer (x, tx, T) summaries.

    x counts repeat purchases (total purchases minus the first), tx is the time from
    a customer's first to last purchase, and T is the time from the first purchase to
    `observation_end` (default: the latest date in the data), in the chosen time unit.
    """
    data = transactions[[customer_id, purchase_date]].copy()
    data[purchase_date] = pd.to_datetime(data[purchase_date], errors="coerce")
    data = data.dropna().sort_values([customer_id, purchase_date])
    if data.empty:
        raise ValueError("No valid customer/date transactions were found.")
    end = pd.Timestamp(observation_end) if observation_end is not None else data[purchase_date].max()
    divisor = {"days": 1.0, "weeks": 7.0, "months": 30.4375}.get(time_unit)
    if divisor is None:
        raise ValueError("Time unit must be days, weeks, or months.")
    grouped = data.groupby(customer_id)[purchase_date].agg(["min", "max", "size"])
    grouped["x"] = grouped["size"] - 1
    grouped["tx"] = (grouped["max"] - grouped["min"]).dt.days / divisor
    grouped["T"] = (end - grouped["min"]).dt.days / divisor
    return grouped.reset_index()[[customer_id, "x", "tx", "T"]]


def score_bgnbd(
    frame: pd.DataFrame,
    x_col: str,
    tx_col: str,
    T_col: str,
    horizon: float,
    weight_col: str | None = None,
) -> tuple[BGNBDParams, pd.DataFrame]:
    """Fit BG/NBD on a summary table and append per-customer scores.

    Adds `probability_active`, `expected_if_active`, and `expected_future_purchases`
    columns for the given `horizon`; rows with non-numeric inputs are dropped.
    """
    data = frame.copy()
    x = pd.to_numeric(data[x_col], errors="coerce").to_numpy()
    tx = pd.to_numeric(data[tx_col], errors="coerce").to_numpy()
    T = pd.to_numeric(data[T_col], errors="coerce").to_numpy()
    valid = np.isfinite(x) & np.isfinite(tx) & np.isfinite(T)
    weights = None if weight_col is None else pd.to_numeric(data.loc[valid, weight_col], errors="coerce").fillna(0).to_numpy()
    params = fit_bgnbd(x[valid], tx[valid], T[valid], weights)
    p_alive, active, expected = expected_future_purchases(x[valid], tx[valid], T[valid], horizon, params)
    scored = data.loc[valid].copy()
    scored["probability_active"] = p_alive
    scored["expected_if_active"] = active
    scored["expected_future_purchases"] = expected
    return params, scored
