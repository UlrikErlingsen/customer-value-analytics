"""Customer lifetime value from margin, retention, and a discount rate.

Answers "what is a customer worth today?" with the margin-multiple model of
Gupta & Lehmann (2003, "Customers as Assets", Journal of Interactive
Marketing): a customer contributing margin m per period, retained with
probability r and discounted at rate d, is worth m * r / (1 + d - r) over
an infinite horizon. Variants cover finite horizons, margin growth, and
arbitrary period windows, plus the elasticity of CLV to retention.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


def _validate(margin: float, retention: float, discount: float) -> None:
    """Reject margins, retention rates, or discount rates outside their valid ranges."""
    if margin < 0:
        raise ValueError("Margin cannot be negative.")
    if not 0 <= retention <= 1:
        raise ValueError("Retention must be between 0 and 1.")
    if discount <= -1:
        raise ValueError("Discount rate must be greater than -100%.")


def gupta_lehmann_clv(margin: float, retention: float, discount: float) -> float:
    """Infinite-horizon CLV = margin * retention / (1 + discount - retention), per Gupta & Lehmann (2003)."""
    _validate(margin, retention, discount)
    denominator = 1 + discount - retention
    if denominator <= 0:
        raise ValueError("The infinite-horizon CLV does not converge for these inputs.")
    return float(margin * retention / denominator)


def finite_horizon_clv(margin: float, retention: float, discount: float, periods: int) -> float:
    """CLV truncated after ``periods`` future periods (geometric series of margin * (retention / (1 + discount))^t)."""
    _validate(margin, retention, discount)
    if periods < 0:
        raise ValueError("Periods cannot be negative.")
    if periods == 0:
        return 0.0
    ratio = retention / (1 + discount)
    if np.isclose(ratio, 1):
        return float(margin * periods)
    return float(margin * ratio * (1 - ratio**periods) / (1 - ratio))


def growth_clv(margin: float, retention: float, discount: float, growth: float) -> float:
    """Infinite-horizon CLV when the per-period margin grows at rate ``growth``."""
    _validate(margin, retention, discount)
    denominator = 1 + discount - retention * (1 + growth)
    if denominator <= 0:
        raise ValueError("The infinite-horizon growth CLV does not converge for these inputs.")
    return float(margin * retention / denominator)


def timed_clv(
    margin: float,
    retention: float,
    discount: float,
    first_period: int,
    last_period: int,
) -> float:
    """CLV earned only between ``first_period`` and ``last_period`` (inclusive); period 0 means an undiscounted margin today."""
    _validate(margin, retention, discount)
    if first_period < 0 or last_period < first_period:
        raise ValueError("Require 0 <= first period <= last period.")
    ratio = retention / (1 + discount)
    return float(margin * sum(ratio**period for period in range(first_period, last_period + 1)))


def retention_elasticity(retention: float, discount: float) -> float:
    """Percent change in CLV per one-percent change in retention: 1 plus the margin multiple (Gupta & Lehmann 2003)."""
    multiple = gupta_lehmann_clv(1.0, retention, discount)
    return float(1 + multiple)


@dataclass(frozen=True)
class CLVSummary:
    """CLV headline numbers: value, net of acquisition cost, the margin multiple (CLV / margin), and the two elasticities."""

    clv: float
    acquisition_cost: float
    net_value: float
    margin_multiple: float
    margin_elasticity: float
    retention_elasticity: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def summarize_clv(margin: float, retention: float, discount: float, acquisition_cost: float = 0.0) -> CLVSummary:
    """Compute the infinite-horizon CLV and its standard companions in one call.

    Margin elasticity is exactly 1 in this model (CLV is proportional to
    margin); retention elasticity is typically much larger, which is the
    model's core managerial message.
    """
    clv = gupta_lehmann_clv(margin, retention, discount)
    multiple = clv / margin if margin else 0.0
    return CLVSummary(
        clv=clv,
        acquisition_cost=float(acquisition_cost),
        net_value=clv - acquisition_cost,
        margin_multiple=multiple,
        margin_elasticity=1.0,
        retention_elasticity=retention_elasticity(retention, discount),
    )
