"""Markov brand-switching: CLV and marketing ROI when customers switch brands.

Follows the return-on-marketing framework of Rust, Lemon & Zeithaml (2004,
"Return on Marketing", Journal of Marketing): customers move between
competing companies purchase-by-purchase according to a transition matrix
of switching probabilities. Propagating those probabilities forward and
discounting the focal company's expected margins yields a CLV per customer,
and comparing customer equity before and after a marketing-induced change
in the matrix yields the investment's ROI. Inputs are the transition
matrix (rows sum to 1), spend per purchase, margin, purchase frequency,
discount rate, and planning horizon.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


def validate_transition_matrix(matrix: np.ndarray, tolerance: float = 1e-8) -> np.ndarray:
    """Check that the matrix is square with probabilities in [0, 1] and rows summing to 1, and return it as a float array."""
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("Transition matrix must be square.")
    if np.any(values < 0) or np.any(values > 1):
        raise ValueError("Transition probabilities must be between 0 and 1.")
    if not np.allclose(values.sum(axis=1), 1, atol=tolerance):
        raise ValueError("Every row of the transition matrix must sum to 1.")
    return values


def choice_probabilities(matrix: np.ndarray, previous_choice: int, occasions: int) -> pd.DataFrame:
    """Probability of buying from each company on the next ``occasions`` purchases, starting from a customer whose last purchase was ``previous_choice`` (0-based)."""
    transition = validate_transition_matrix(matrix)
    if not 0 <= previous_choice < transition.shape[0] or occasions < 1:
        raise ValueError("Previous choice or number of occasions is invalid.")
    vector = np.zeros(transition.shape[0])
    vector[previous_choice] = 1.0
    rows = []
    for occasion in range(occasions):
        vector = vector @ transition
        rows.append(vector.copy())
    columns = [f"company_{index + 1}" for index in range(transition.shape[0])]
    result = pd.DataFrame(rows, columns=columns)
    result.insert(0, "occasion", np.arange(occasions))
    return result


def markov_clv(
    matrix: np.ndarray,
    previous_choice: int,
    focal_company: int,
    amount_per_purchase: float,
    profit_margin: float,
    purchases_per_year: float,
    discount_rate: float,
    horizon_years: float,
) -> tuple[float, pd.DataFrame]:
    """CLV of one customer to the focal company over a purchase horizon.

    Each purchase occasion contributes (choice probability x amount x margin),
    discounted at an annual rate converted to the between-purchase interval,
    as in Rust, Lemon & Zeithaml (2004). Returns the total plus an
    occasion-by-occasion breakdown.
    """
    if amount_per_purchase < 0 or not 0 <= profit_margin <= 1 or purchases_per_year <= 0 or horizon_years < 0:
        raise ValueError("Amount, margin, purchase frequency, or horizon is invalid.")
    occasions = int(np.floor(horizon_years * purchases_per_year)) + 1
    probabilities = choice_probabilities(matrix, previous_choice, occasions)
    if not 0 <= focal_company < np.asarray(matrix).shape[0]:
        raise ValueError("Focal company index is invalid.")
    t = probabilities["occasion"].to_numpy(dtype=float)
    focal = probabilities[f"company_{focal_company + 1}"].to_numpy(dtype=float)
    discount = np.power(1 + discount_rate, -t / purchases_per_year)
    contribution = discount * amount_per_purchase * profit_margin * focal
    details = pd.DataFrame(
        {
            "occasion": t.astype(int),
            "years_from_now": t / purchases_per_year,
            "choice_probability": focal,
            "discount_factor": discount,
            "clv_contribution": contribution,
        }
    )
    return float(contribution.sum()), details


@dataclass(frozen=True)
class ROIResult:
    """Marketing ROI output: average CLV before and after the change, the resulting change in customer equity, the investment, net profit, and ROI."""

    old_average_clv: float
    new_average_clv: float
    change_in_customer_equity: float
    investment: float
    net_profit: float
    roi: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def markov_roi(
    old_matrix: np.ndarray,
    new_matrix: np.ndarray,
    previous_choice_weights: np.ndarray,
    focal_company: int,
    amount_per_purchase: float,
    profit_margin: float,
    purchases_per_year: float,
    discount_rate: float,
    horizon_years: float,
    industry_customers: float,
    investment: float,
) -> ROIResult:
    """ROI of a marketing action that shifts the brand-switching matrix.

    Averages the focal company's CLV over customers' previous choices
    (weighted by ``previous_choice_weights``, e.g. market shares) under the
    old and new matrices, scales the CLV gain by the number of customers in
    the industry, and nets out the investment — the customer-equity ROI test
    of Rust, Lemon & Zeithaml (2004).
    """
    old = validate_transition_matrix(old_matrix)
    new = validate_transition_matrix(new_matrix)
    if old.shape != new.shape:
        raise ValueError("Old and new transition matrices must have the same shape.")
    weights = np.asarray(previous_choice_weights, dtype=float)
    if len(weights) != old.shape[0] or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Previous-choice weights must be non-negative and match the matrix size.")
    weights = weights / weights.sum()
    old_clv = 0.0
    new_clv = 0.0
    for previous, weight in enumerate(weights):
        old_value, _ = markov_clv(
            old, previous, focal_company, amount_per_purchase, profit_margin, purchases_per_year, discount_rate, horizon_years
        )
        new_value, _ = markov_clv(
            new, previous, focal_company, amount_per_purchase, profit_margin, purchases_per_year, discount_rate, horizon_years
        )
        old_clv += weight * old_value
        new_clv += weight * new_value
    change = (new_clv - old_clv) * industry_customers
    net = change - investment
    roi = net / investment if investment != 0 else np.nan
    return ROIResult(float(old_clv), float(new_clv), float(change), float(investment), float(net), float(roi))
