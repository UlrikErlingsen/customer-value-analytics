"""Splitting the marketing budget between acquisition and retention.

Implements the customer-equity budgeting model of Blattberg & Deighton
(1996, "Manage Marketing by the Customer Equity Test", Harvard Business
Review). Acquisition and retention rates respond to per-prospect spending
along saturating "ceiling" curves calibrated from a single observed
(spend, rate) point and a managerial estimate of the maximum achievable
rate; the model then finds the spending pair that maximizes the value of a
prospect, i.e. expected acquisition margin plus the discounted retention
stream.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import differential_evolution


def curve_steepness(spend: float, observed_rate: float, maximum_rate: float) -> float:
    """Solve the ceiling response curve for its steepness beta so that it passes through one observed (spend, rate) point."""
    if spend <= 0 or not 0 < observed_rate < maximum_rate <= 1:
        raise ValueError("Require spend > 0 and 0 < observed rate < maximum rate <= 1.")
    return float(-np.log((maximum_rate - observed_rate) / maximum_rate) / spend)


def response_rate(spend: float | np.ndarray, maximum_rate: float, beta: float) -> float | np.ndarray:
    """Ceiling response curve: rate = maximum_rate * (1 - exp(-beta * spend)), rising with diminishing returns toward the ceiling."""
    return maximum_rate * (1 - np.exp(-beta * np.asarray(spend)))


def _effective_cost(spend: float, rate: float, maximum_rate: float, beta: float) -> float:
    """Spend per customer actually won (spend / rate), using the analytic zero-spend limit 1 / (maximum_rate * beta) when the rate vanishes."""
    if rate > 1e-12:
        return spend / rate
    return 1 / (maximum_rate * beta)


def prospect_value(
    acquisition_spend: float,
    retention_spend: float,
    maximum_acquisition: float,
    maximum_retention: float,
    acquisition_beta: float,
    retention_beta: float,
    margin: float,
    discount: float,
) -> tuple[float, float, float, float]:
    """Value of one prospect under given acquisition and retention spending.

    Returns (prospect value, acquisition rate, retention rate, value per
    acquired customer). A customer is worth the first-period margin net of
    effective acquisition cost plus the discounted stream of retained margins
    net of effective retention cost; the prospect value multiplies this by
    the acquisition probability, as in Blattberg & Deighton (1996).
    """
    a = float(response_rate(acquisition_spend, maximum_acquisition, acquisition_beta))
    r = float(response_rate(retention_spend, maximum_retention, retention_beta))
    effective_retention = _effective_cost(retention_spend, r, maximum_retention, retention_beta)
    denominator = 1 + discount - r
    if denominator <= 0:
        return -np.inf, a, r, -np.inf
    customer = (margin - _effective_cost(acquisition_spend, a, maximum_acquisition, acquisition_beta)) + (
        margin - effective_retention
    ) * r / denominator
    prospect = a * customer
    return float(prospect), a, r, float(customer)


@dataclass(frozen=True)
class BudgetResult:
    """Budget optimization output: calibrated curve steepnesses, prospect value at current vs. optimal spending, the optimal spends and response rates, and the percent improvement."""

    acquisition_beta: float
    retention_beta: float
    current_value: float
    optimal_value: float
    optimal_acquisition_spend: float
    optimal_retention_spend: float
    optimal_acquisition_rate: float
    optimal_retention_rate: float
    improvement_pct: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def optimize_budgets(
    acquisition_spend: float,
    acquisition_rate: float,
    maximum_acquisition: float,
    retention_spend: float,
    retention_rate: float,
    maximum_retention: float,
    margin: float,
    discount: float,
) -> BudgetResult:
    """Find the acquisition and retention spending pair that maximizes prospect value.

    Calibrates each response curve from its observed (spend, rate) point and
    ceiling, then searches spending levels with a global optimizer (fixed
    seed, so results are reproducible) and compares the optimum to current
    spending.
    """
    beta_a = curve_steepness(acquisition_spend, acquisition_rate, maximum_acquisition)
    beta_r = curve_steepness(retention_spend, retention_rate, maximum_retention)
    current, _, _, _ = prospect_value(
        acquisition_spend,
        retention_spend,
        maximum_acquisition,
        maximum_retention,
        beta_a,
        beta_r,
        margin,
        discount,
    )
    upper_a = max(acquisition_spend * 10, -np.log(1e-5) / beta_a)
    upper_r = max(retention_spend * 10, -np.log(1e-5) / beta_r)

    def objective(values: np.ndarray) -> float:
        value, _, _, _ = prospect_value(
            values[0], values[1], maximum_acquisition, maximum_retention, beta_a, beta_r, margin, discount
        )
        return -value if np.isfinite(value) else 1e100

    fit = differential_evolution(
        objective, bounds=[(0, upper_a), (0, upper_r)], seed=6435, polish=True, tol=1e-10
    )
    optimal, a_opt, r_opt, _ = prospect_value(
        fit.x[0], fit.x[1], maximum_acquisition, maximum_retention, beta_a, beta_r, margin, discount
    )
    improvement = (optimal / current - 1) * 100 if current != 0 else np.nan
    return BudgetResult(
        beta_a,
        beta_r,
        current,
        optimal,
        float(fit.x[0]),
        float(fit.x[1]),
        a_opt,
        r_opt,
        float(improvement),
    )

