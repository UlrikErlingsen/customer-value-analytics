"""BG/BB model of repeat behavior in a discrete-time noncontractual setting.

Business question: when transaction opportunities come in fixed periods (annual
donations, yearly orders), which customers are still "alive" and how many future
transactions should we expect from each? While alive, a customer transacts in a
period with probability p (Beta(alpha, beta) across customers) and dies between
periods with probability q (Beta(gamma, delta) across customers). Inputs per
customer: n = number of observed periods, x = periods with a transaction,
tx = last period with a transaction (0 if none).

Reference: Fader, Hardie & Shang (2010), "Customer-Base Analysis in a
Discrete-Time Noncontractual Setting", Marketing Science.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import betaln, logsumexp


@dataclass(frozen=True)
class BGBBParams:
    """Fitted BG/BB parameters: Beta(alpha, beta) transaction and Beta(gamma, delta) death probabilities."""

    alpha: float
    beta: float
    gamma: float
    delta: float
    log_likelihood: float
    success: bool

    def to_dict(self) -> dict[str, float | bool]:
        return asdict(self)


def history_probability_no_heterogeneity(n: int, tx: int, x: int, p: float, q: float) -> float:
    """Likelihood of one (n, tx, x) history for fixed p and q — the single-customer building block.

    Sums the "still alive through period n" path and every possible death period after
    the last observed transaction.
    """
    _validate(np.array([n]), np.array([tx]), np.array([x]))
    if not 0 <= p <= 1 or not 0 <= q <= 1:
        raise ValueError("p and q must be between 0 and 1.")
    stay_to_end = p**x * (1 - p) ** (n - x) * (1 - q) ** n
    dropout = sum(
        p**x * (1 - p) ** (tx - x + j) * q * (1 - q) ** (tx + j)
        for j in range(max(0, n - tx))
    )
    return float(stay_to_end + dropout)


def probability_alive_no_heterogeneity(n: int, tx: int, x: int, p: float, q: float) -> float:
    """Probability the customer is still alive entering period n + 1, for fixed p and q."""
    likelihood = history_probability_no_heterogeneity(n, tx, x, p, q)
    if likelihood == 0:
        return 0.0
    alive_path_and_enters_future = p**x * (1 - p) ** (n - x) * (1 - q) ** (n + 1)
    return float(alive_path_and_enters_future / likelihood)


def _history_log_likelihood(n: int, tx: int, x: int, params: tuple[float, float, float, float]) -> float:
    """Log-likelihood of one history with Beta mixing over p and q (log-sum-exp over death periods)."""
    alpha, beta, gamma, delta = params
    log_beta_p = betaln(alpha, beta)
    log_beta_q = betaln(gamma, delta)
    terms = [
        betaln(alpha + x, beta + n - x) - log_beta_p
        + betaln(gamma, delta + n) - log_beta_q
    ]
    for j in range(max(0, n - tx)):
        terms.append(
            betaln(alpha + x, beta + tx - x + j) - log_beta_p
            + betaln(gamma + 1, delta + tx + j) - log_beta_q
        )
    return float(logsumexp(terms))


def _validate(n: np.ndarray, tx: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Coerce to integer arrays and enforce n >= 1, 0 <= x <= tx <= n."""
    n = np.asarray(n, dtype=int)
    tx = np.asarray(tx, dtype=int)
    x = np.asarray(x, dtype=int)
    if len(n) == 0 or not (len(n) == len(tx) == len(x)):
        raise ValueError("n, tx, and x must be non-empty and have equal length.")
    if np.any(n < 1) or np.any(x < 0) or np.any(x > n) or np.any(tx < 0) or np.any(tx > n) or np.any(tx < x):
        raise ValueError("Require n >= 1, 0 <= x <= tx <= n.")
    return n, tx, x


def fit_bgbb(
    n: np.ndarray, tx: np.ndarray, x: np.ndarray, weights: np.ndarray | None = None
) -> BGBBParams:
    """Fit BG/BB parameters by maximum likelihood on per-customer (n, tx, x) summaries.

    Optional `weights` allow aggregated inputs where one row counts several customers
    with the same history. Optimizes in log-parameter space from several starting
    points and keeps the best solution.
    """
    n, tx, x = _validate(n, tx, x)
    w = np.ones(len(n)) if weights is None else np.asarray(weights, dtype=float)
    if len(w) != len(n) or np.any(w < 0):
        raise ValueError("Weights must be non-negative and match the rows.")

    def objective(log_params: np.ndarray) -> float:
        params = tuple(np.exp(log_params))
        ll = np.array([_history_log_likelihood(int(ni), int(txi), int(xi), params) for ni, txi, xi in zip(n, tx, x)])
        value = np.dot(w, ll)
        return float(-value) if np.isfinite(value) else 1e100

    starts = ([1.2, 0.8, 0.7, 2.8], [1, 1, 1, 3], [2, 2, 0.5, 2], [0.5, 2, 2, 5])
    best = None
    for start in starts:
        result = minimize(objective, np.log(start), method="L-BFGS-B", bounds=[(-12, 12)] * 4)
        if best is None or result.fun < best.fun:
            best = result
    assert best is not None
    alpha, beta, gamma, delta = np.exp(best.x)
    return BGBBParams(float(alpha), float(beta), float(gamma), float(delta), float(-best.fun), bool(best.success))


def probability_alive(n: int, tx: int, x: int, params: BGBBParams) -> float:
    """Probability the customer is still alive entering period n + 1, given the fitted parameters."""
    log_likelihood = _history_log_likelihood(n, tx, x, (params.alpha, params.beta, params.gamma, params.delta))
    numerator = (
        betaln(params.alpha + x, params.beta + n - x) - betaln(params.alpha, params.beta)
        + betaln(params.gamma, params.delta + n + 1) - betaln(params.gamma, params.delta)
    )
    return float(np.exp(numerator - log_likelihood))


def expected_future_purchases(n: int, tx: int, x: int, future_periods: int, params: BGBBParams) -> float:
    """Expected number of transactions in the next `future_periods` periods for one customer."""
    if future_periods < 0:
        raise ValueError("Future periods cannot be negative.")
    if future_periods == 0:
        return 0.0
    log_likelihood = _history_log_likelihood(n, tx, x, (params.alpha, params.beta, params.gamma, params.delta))
    log_purchase = betaln(params.alpha + x + 1, params.beta + n - x) - betaln(params.alpha, params.beta)
    future_terms = np.array(
        [
            betaln(params.gamma, params.delta + n + k) - betaln(params.gamma, params.delta)
            for k in range(1, future_periods + 1)
        ]
    )
    return float(np.exp(log_purchase - log_likelihood + logsumexp(future_terms)))


def summary_from_binary_periods(frame: pd.DataFrame, period_columns: list[str]) -> pd.DataFrame:
    """Convert per-period 0/1 activity columns (in chronological order) into n, tx, and x columns."""
    values = frame[period_columns].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()
    if np.any((values != 0) & (values != 1)):
        raise ValueError("Discrete period columns must contain only 0 and 1.")
    periods = np.arange(1, len(period_columns) + 1)
    x = values.sum(axis=1).astype(int)
    tx = np.where(x > 0, np.max(np.where(values == 1, periods, 0), axis=1), 0).astype(int)
    result = frame.copy()
    result["n"] = len(period_columns)
    result["tx"] = tx
    result["x"] = x
    return result


def score_bgbb(
    frame: pd.DataFrame,
    n_col: str,
    tx_col: str,
    x_col: str,
    future_periods: int,
    weight_col: str | None = None,
) -> tuple[BGBBParams, pd.DataFrame]:
    """Fit BG/BB on a summary table and append per-customer scores.

    Adds `probability_alive` and `expected_future_purchases` columns for the given
    `future_periods`; rows with non-numeric inputs are dropped.
    """
    data = frame.copy()
    n = pd.to_numeric(data[n_col], errors="coerce")
    tx = pd.to_numeric(data[tx_col], errors="coerce")
    x = pd.to_numeric(data[x_col], errors="coerce")
    valid = n.notna() & tx.notna() & x.notna()
    n_values = n.loc[valid].astype(int).to_numpy()
    tx_values = tx.loc[valid].astype(int).to_numpy()
    x_values = x.loc[valid].astype(int).to_numpy()
    weights = None if weight_col is None else pd.to_numeric(data.loc[valid, weight_col], errors="coerce").fillna(0).to_numpy()
    params = fit_bgbb(n_values, tx_values, x_values, weights)
    scored = data.loc[valid].copy()
    scored["probability_alive"] = [
        probability_alive(int(ni), int(txi), int(xi), params)
        for ni, txi, xi in zip(n_values, tx_values, x_values)
    ]
    scored["expected_future_purchases"] = [
        expected_future_purchases(int(ni), int(txi), int(xi), future_periods, params)
        for ni, txi, xi in zip(n_values, tx_values, x_values)
    ]
    return params, scored
