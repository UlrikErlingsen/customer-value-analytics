"""Contractual (subscription) retention with the shifted-beta-geometric (sBG) model.

Business question: given how many subscribers survived each past renewal period,
how many will still be active in future periods, and how long does a typical
customer stay? Each customer churns each period with a constant probability drawn
from a Beta(alpha, beta) distribution; mixing over customers reproduces the common
pattern of aggregate retention rates rising over time as loyal customers come to
dominate the base.

Reference: Fader & Hardie (2007), "How to Project Customer Retention",
Journal of Interactive Marketing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import betaln


def sbg_survival(period: np.ndarray | float, alpha: float, beta: float) -> np.ndarray:
    """Probability S(t) that a customer is still active after `period` renewals."""
    t = np.asarray(period, dtype=float)
    return np.exp(betaln(alpha, beta + t) - betaln(alpha, beta))


def sbg_retention(period: np.ndarray | float, alpha: float, beta: float) -> np.ndarray:
    """Aggregate retention rate r(t): the share of period t-1 survivors who renew in period t."""
    t = np.asarray(period, dtype=float)
    return (beta + t - 1) / (alpha + beta + t - 1)


def sbg_duration_probability(period: np.ndarray | float, alpha: float, beta: float) -> np.ndarray:
    """Probability P(T = t) that a customer churns exactly in `period`."""
    t = np.asarray(period, dtype=float)
    return np.exp(betaln(alpha + 1, beta + t - 1) - betaln(alpha, beta))


@dataclass(frozen=True)
class SBGFit:
    """Fitted sBG parameters (Beta churn-probability mixture) and the maximized log-likelihood."""

    alpha: float
    beta: float
    log_likelihood: float
    success: bool

    def to_dict(self) -> dict[str, float | bool]:
        return asdict(self)


def _prepare_survivors(periods: np.ndarray, survivors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate and sort the survivor curve: periods must run 0..K with non-increasing counts."""
    data = pd.DataFrame({"period": periods, "survivors": survivors}).dropna().sort_values("period")
    t = data["period"].to_numpy(dtype=int)
    s = data["survivors"].to_numpy(dtype=float)
    if len(t) < 3 or t[0] != 0 or not np.array_equal(t, np.arange(t[-1] + 1)):
        raise ValueError("Periods must be consecutive integers beginning at 0.")
    if np.any(s < 0) or np.any(np.diff(s) > 1e-9) or s[0] <= 0:
        raise ValueError("Survivor counts must be non-negative and cannot increase over time.")
    return t, s


def fit_sbg(periods: np.ndarray, survivors: np.ndarray) -> SBGFit:
    """Fit alpha and beta by maximum likelihood from an observed survivor curve.

    Customers lost between periods contribute the churn probability for that period;
    those still active at the last observed period are treated as censored. Optimizes
    in log-parameter space from several starting points and keeps the best solution.
    """
    t, s = _prepare_survivors(periods, survivors)
    failures = s[:-1] - s[1:]
    censor_period = int(t[-1])
    censored = float(s[-1])

    def objective(log_params: np.ndarray) -> float:
        alpha, beta = np.exp(log_params)
        failure_periods = np.arange(1, censor_period + 1)
        log_failure = betaln(alpha + 1, beta + failure_periods - 1) - betaln(alpha, beta)
        log_survival = betaln(alpha, beta + censor_period) - betaln(alpha, beta)
        value = np.dot(failures, log_failure) + censored * log_survival
        return float(-value) if np.isfinite(value) else 1e100

    best = None
    for start in ([1.0, 1.0], [0.5, 2.0], [2.0, 5.0], [0.2, 0.8]):
        result = minimize(objective, np.log(start), method="L-BFGS-B", bounds=[(-12, 12), (-12, 12)])
        if best is None or result.fun < best.fun:
            best = result
    assert best is not None
    alpha, beta = np.exp(best.x)
    return SBGFit(float(alpha), float(beta), float(-best.fun), bool(best.success))


def contractual_forecast(
    periods: np.ndarray,
    survivors: np.ndarray,
    forecast_horizon: int,
) -> tuple[SBGFit, pd.DataFrame, dict[str, float]]:
    """Fit the sBG model and project survival and retention out to `forecast_horizon`.

    Returns the fit, a period-by-period table (actual vs. predicted survival, predicted
    retention rate, predicted survivor counts), and summary metrics including the
    model-based expected customer lifetime in periods.
    """
    t, s = _prepare_survivors(periods, survivors)
    fit = fit_sbg(t, s)
    horizon = max(int(forecast_horizon), int(t[-1]))
    forecast_t = np.arange(0, horizon + 1)
    predicted_survival = sbg_survival(forecast_t, fit.alpha, fit.beta)
    retention = np.full_like(predicted_survival, np.nan, dtype=float)
    retention[1:] = sbg_retention(forecast_t[1:], fit.alpha, fit.beta)
    actual_survival = np.full_like(predicted_survival, np.nan, dtype=float)
    actual_survival[: len(s)] = s / s[0]
    table = pd.DataFrame(
        {
            "period": forecast_t,
            "actual_survival": actual_survival,
            "predicted_survival": predicted_survival,
            "predicted_retention": retention,
            "predicted_survivors": predicted_survival * s[0],
        }
    )
    metrics = {
        "observed_expected_lifetime_lower_bound": float(np.sum(s / s[0])),
        "forecast_expected_lifetime": float(predicted_survival.sum()),
        "mean_defection_probability": float(fit.alpha / (fit.alpha + fit.beta)),
    }
    return fit, table, metrics

