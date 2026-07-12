"""Customer equity: valuing the whole customer base, current and future.

Implements the approach of Gupta, Lehmann & Stuart (2004, "Valuing
Customers", Journal of Marketing Research): back out per-period customer
acquisitions from a history of customer counts and a retention rate, fit an
S-shaped diffusion curve to project future acquisitions, and value the firm
as (current customers x CLV) plus the discounted net value of customers yet
to be acquired. Inputs are the customer-count history, per-customer margin,
retention, discount rate, acquisition cost, and optionally a tax rate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from .clv import gupta_lehmann_clv


def acquired_customers(customer_counts: np.ndarray, retention: float) -> np.ndarray:
    """Back out per-period acquisitions from customer counts: acquired_t = n_t - retention * n_{t-1}."""
    counts = np.asarray(customer_counts, dtype=float)
    if counts.ndim != 1 or len(counts) < 2 or np.any(counts < 0):
        raise ValueError("Customer counts must be a non-negative one-dimensional series with at least two periods.")
    if not 0 <= retention <= 1:
        raise ValueError("Retention must be between 0 and 1.")
    acquired = counts[1:] - retention * counts[:-1]
    return acquired


def acquisition_curve(period: np.ndarray | float, alpha: float, beta: float, gamma: float) -> np.ndarray:
    """New customers acquired in a period under an S-shaped diffusion of cumulative acquisitions.

    This is the derivative of the logistic curve alpha / (1 + exp(-beta -
    gamma * t)) used by Gupta, Lehmann & Stuart (2004): alpha is the ceiling
    on total customers ever acquired, beta shifts the curve in time, and
    gamma controls how fast acquisition peaks and tails off.
    """
    t = np.asarray(period, dtype=float)
    z = np.clip(-beta - gamma * t, -700, 700)
    exp_z = np.exp(z)
    return alpha * gamma * exp_z / np.square(1 + exp_z)


@dataclass(frozen=True)
class CurveFit:
    """Fitted acquisition-curve parameters (alpha, beta, gamma) with the sum of squared errors and R-squared."""

    alpha: float
    beta: float
    gamma: float
    sse: float
    r_squared: float


def fit_acquisition_curve(periods: np.ndarray, acquired: np.ndarray) -> CurveFit:
    """Fit the acquisition curve to observed acquisitions by bounded nonlinear least squares, keeping the best of several starting points."""
    t = np.asarray(periods, dtype=float)
    y = np.asarray(acquired, dtype=float)
    valid = np.isfinite(t) & np.isfinite(y) & (y >= 0)
    t, y = t[valid], y[valid]
    if len(y) < 4:
        raise ValueError("At least four non-negative acquisition observations are needed.")
    scale = max(float(np.sum(y) * 2), float(np.max(y) * 4), 1.0)
    starts = [
        np.array([scale, -2.0, 0.2]),
        np.array([scale * 2, -4.0, 0.1]),
        np.array([scale, 0.0, 0.5]),
        np.array([scale * 4, -6.0, 0.05]),
    ]

    def residuals(params: np.ndarray) -> np.ndarray:
        alpha, beta, gamma = params
        return acquisition_curve(t, alpha, beta, gamma) - y

    best = None
    lower = np.array([1e-10, -50.0, 1e-8])
    upper = np.array([max(scale * 1000, 1e12), 50.0, 20.0])
    for start in starts:
        fit = least_squares(residuals, np.clip(start, lower, upper), bounds=(lower, upper), max_nfev=20000)
        if best is None or np.sum(fit.fun**2) < np.sum(best.fun**2):
            best = fit
    assert best is not None
    sse = float(np.sum(best.fun**2))
    total = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1 - sse / total if total > 0 else 1.0
    return CurveFit(float(best.x[0]), float(best.x[1]), float(best.x[2]), sse, r_squared)


@dataclass(frozen=True)
class EquitySummary:
    """Customer-equity headline numbers: per-customer CLV, value of current customers, discounted net value of future customers, and the pre- and post-tax totals."""

    clv: float
    current_customer_value: float
    future_customer_value: float
    pre_tax_customer_equity: float
    customer_equity: float
    tax_rate: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class EquityResult:
    """Full customer-equity output: the summary, the fitted acquisition curve, observed-vs-fitted history, and the period-by-period forecast."""

    summary: EquitySummary
    curve_fit: CurveFit
    history: pd.DataFrame
    forecast: pd.DataFrame


def customer_equity(
    periods: np.ndarray,
    customer_counts: np.ndarray,
    acquisition_cost: float,
    margin: float,
    retention: float,
    discount: float,
    tax_rate: float = 0.0,
    forecast_periods: int = 100,
) -> EquityResult:
    """Value the customer base following Gupta, Lehmann & Stuart (2004).

    Current-customer value is the latest customer count times the
    infinite-horizon CLV; future-customer value discounts each forecast
    cohort's (CLV - acquisition cost) back to today; the after-tax total is
    the customer-equity estimate of firm value.
    """
    periods = np.asarray(periods, dtype=float)
    counts = np.asarray(customer_counts, dtype=float)
    if len(periods) != len(counts):
        raise ValueError("Periods and customer counts must have equal length.")
    if not 0 <= tax_rate <= 1:
        raise ValueError("Tax rate must be between 0 and 1.")
    acquired = acquired_customers(counts, retention)
    acquisition_periods = periods[1:]
    if np.any(acquired < -1e-8):
        raise ValueError("The selected retention rate implies negative acquired customers in the history.")
    acquired = np.maximum(acquired, 0)
    fit = fit_acquisition_curve(acquisition_periods, acquired)
    clv = gupta_lehmann_clv(margin, retention, discount)
    current = float(counts[-1] * clv)
    future_t = np.arange(1, int(forecast_periods) + 1, dtype=float)
    absolute_t = periods[-1] + future_t
    forecast_acquired = acquisition_curve(absolute_t, fit.alpha, fit.beta, fit.gamma)
    discounted = forecast_acquired / np.power(1 + discount, future_t)
    future = float((clv - acquisition_cost) * discounted.sum())
    pre_tax = current + future
    total = pre_tax * (1 - tax_rate)
    history = pd.DataFrame(
        {
            "period": acquisition_periods,
            "observed_acquired": acquired,
            "fitted_acquired": acquisition_curve(acquisition_periods, fit.alpha, fit.beta, fit.gamma),
        }
    )
    forecast = pd.DataFrame(
        {
            "period_ahead": future_t.astype(int),
            "period": absolute_t,
            "forecast_acquired": forecast_acquired,
            "discounted_acquired": discounted,
            "future_value_contribution": (clv - acquisition_cost) * discounted,
        }
    )
    return EquityResult(
        EquitySummary(clv, current, future, pre_tax, total, tax_rate), fit, history, forecast
    )


def annual_elasticities(
    periods: np.ndarray,
    customer_counts: np.ndarray,
    acquisition_cost: float,
    margin: float,
    retention: float,
    discount: float,
    tax_rate: float,
    periods_per_year: int,
    forecast_periods: int = 100,
    change: float = 0.01,
) -> pd.DataFrame:
    """Measure which lever moves customer equity most: margin, retention, or acquisition cost.

    Recomputes customer equity after a one-percent annual improvement in each
    driver (retention is compounded to the per-period rate via
    ``periods_per_year``) and reports the resulting elasticity, i.e. the
    percent change in equity per percent change in the driver.
    """
    if periods_per_year < 1:
        raise ValueError("Periods per year must be at least one.")
    base = customer_equity(
        periods, customer_counts, acquisition_cost, margin, retention, discount, tax_rate, forecast_periods
    ).summary.customer_equity
    if base == 0:
        raise ValueError("Elasticities are undefined when base customer equity is zero.")
    scenarios = {
        "margin increase": dict(margin=margin * (1 + change), retention=retention, acquisition_cost=acquisition_cost),
        "retention increase": dict(
            margin=margin,
            retention=min(retention * (1 + change) ** (1 / periods_per_year), 1 - 1e-10),
            acquisition_cost=acquisition_cost,
        ),
        "acquisition cost reduction": dict(
            margin=margin, retention=retention, acquisition_cost=acquisition_cost * (1 - change)
        ),
    }
    rows = []
    for driver, values in scenarios.items():
        revised = customer_equity(
            periods,
            customer_counts,
            values["acquisition_cost"],
            values["margin"],
            values["retention"],
            discount,
            tax_rate,
            forecast_periods,
        ).summary.customer_equity
        rows.append(
            {
                "driver": driver,
                "base_customer_equity": base,
                "revised_customer_equity": revised,
                "elasticity": (revised - base) / base / change,
            }
        )
    return pd.DataFrame(rows)

