"""Analytic reference tests pinning each model to the cited literature.

Every expected value below is derived by hand, inside this file, from the
published formulas the modules cite — geometric sums, probability-path
arithmetic, or optimality conditions — so the tests are independent of any
particular worked example. If a test fails, the code — not the expected
value — is wrong.
"""

import numpy as np
import pandas as pd
import pytest

from cva.bgbb import (
    BGBBParams,
    expected_future_purchases as bgbb_expected,
    probability_alive_no_heterogeneity,
)
from cva.bgnbd import BGNBDParams, expected_future_purchases as bgnbd_expected, probability_active
from cva.clv import finite_horizon_clv, gupta_lehmann_clv, retention_elasticity
from cva.complaints import recovery_value
from cva.contractual import sbg_retention, sbg_survival
from cva.investment import curve_steepness, optimize_budgets, prospect_value, response_rate
from cva.markov import choice_probabilities, markov_clv
from cva.selection import minimum_profitable_probability, rfm_scores, weighted_split_gini


def test_clv_analytic_identities_and_elasticity():
    """Margin-multiple CLV per Gupta & Lehmann (2003), checked against hand algebra: m*r/(1+i-r) with m=100, r=0.9, i=0.1 is 100*0.9/0.2 = 450; elasticity is 1 + r/(1+i-r) = 5.5."""
    assert gupta_lehmann_clv(100, 0.90, 0.10) == pytest.approx(450.0)
    assert retention_elasticity(0.90, 0.10) == pytest.approx(5.5)
    assert finite_horizon_clv(100, 0.90, 0.10, 5) == pytest.approx(sum(100 * (0.9 / 1.1) ** t for t in range(1, 6)))


def test_targeting_threshold_and_gini():
    """Break-even targeting probability and size-weighted Gini impurity, both computed directly from their definitions: -vN/(vR-vN) with vR=30, vN=-2 is 2/32."""
    assert minimum_profitable_probability(30, -2) == pytest.approx(1 / 16)
    split = weighted_split_gini([2000, 400], [110, 10])
    expected = 2000 / 2400 * 2 * (110 / 2000) * (1 - 110 / 2000) + 400 / 2400 * 2 * (10 / 400) * (1 - 10 / 400)
    assert split == pytest.approx(expected)


def test_rfm_score_one_is_best():
    """RFM quintile scoring follows the classic direct-marketing convention: score 1 marks the best customers on each dimension."""
    frame = pd.DataFrame({"r": range(1, 11), "f": range(1, 11), "m": range(10, 0, -1)})
    scored = rfm_scores(frame, "r", "f", "m", groups=5, nested=False)
    assert scored.loc[0, "R_score"] == 1
    assert scored.loc[9, "R_score"] == 5
    assert scored.loc[9, "F_score"] == 1
    assert scored.loc[0, "M_score"] == 1


def test_blattberg_deighton_calibration_and_optimality():
    """Blattberg & Deighton (1996) budget model: the calibrated curve reproduces the observed point, and the optimizer's answer is a genuine maximum of prospect value."""
    beta = curve_steepness(10, 0.50, 0.80)
    assert response_rate(10, 0.80, beta) == pytest.approx(0.50)
    result = optimize_budgets(6, 0.25, 0.45, 10, 0.50, 0.80, 60, 0.10)

    def value_at(acquisition_spend: float, retention_spend: float) -> float:
        value, _, _, _ = prospect_value(
            acquisition_spend, retention_spend, 0.45, 0.80,
            result.acquisition_beta, result.retention_beta, 60, 0.10,
        )
        return value

    assert result.optimal_value >= result.current_value
    assert value_at(result.optimal_acquisition_spend, result.optimal_retention_spend) == pytest.approx(result.optimal_value)
    for delta_a, delta_r in [(0.5, 0.0), (-0.5, 0.0), (0.0, 0.5), (0.0, -0.5)]:
        perturbed = value_at(result.optimal_acquisition_spend + delta_a, result.optimal_retention_spend + delta_r)
        assert perturbed <= result.optimal_value + 1e-9
    assert 0 < result.optimal_acquisition_rate < 0.45
    assert 0 < result.optimal_retention_rate < 0.80


def test_markov_choice_path_and_clv():
    """Markov brand-switching per Rust, Lemon & Zeithaml (2004): the choice path is hand-propagated matrix algebra, and the CLV matches the documented discounted sum recomputed from first principles."""
    matrix = np.array([[0.75, 0.25], [0.2, 0.8]])
    path = choice_probabilities(matrix, previous_choice=0, occasions=3)
    # By hand: 0.75; 0.75*0.75 + 0.25*0.2 = 0.6125; 0.6125*0.75 + 0.3875*0.2 = 0.536875.
    assert path["company_1"].to_list() == pytest.approx([0.75, 0.6125, 0.536875])
    amount, margin, frequency, discount, horizon = 120.0, 0.25, 2.0, 0.10, 3.0
    state = np.array([1.0, 0.0])
    expected = 0.0
    for occasion in range(int(horizon * frequency) + 1):
        state = state @ matrix
        expected += (1 + discount) ** (-occasion / frequency) * margin * amount * state[0]
    value, _ = markov_clv(matrix, 0, 0, amount, margin, frequency, discount, horizon)
    assert value == pytest.approx(expected)


def test_shifted_beta_geometric_identities():
    """Shifted-beta-geometric retention identities per Fader & Hardie (2007) with alpha = beta = 1."""
    assert sbg_retention(1, 1, 1) == pytest.approx(0.5)
    assert sbg_retention(2, 1, 1) == pytest.approx(2 / 3)
    assert sbg_survival(3, 1, 1) == pytest.approx(0.25)


def test_bgnbd_probability_active_special_cases():
    """BG/NBD special cases per Fader, Hardie & Lee (2005): a customer with no repeat purchases is active with probability 1, and P(active) has a closed form when t_x = T."""
    params = BGNBDParams(0.5, 5.0, 1.5, 3.0, 0.0, True)
    p0 = probability_active(np.array([0]), np.array([0.0]), np.array([10.0]), params)
    assert p0[0] == pytest.approx(1.0)
    p = probability_active(np.array([2]), np.array([10.0]), np.array([10.0]), params)
    assert p[0] == pytest.approx(1 / (1 + 1.5 / 4.0))
    _, active, expected = bgnbd_expected(np.array([2]), np.array([8.0]), np.array([10.0]), 5.0, params)
    assert active[0] >= expected[0] >= 0


def test_bgbb_no_heterogeneity_and_finite_expectation():
    """BG/BB building blocks per Fader, Hardie & Shang (2010): the fixed-parameter alive probability is recomputed here by enumerating the possible dropout paths by hand."""
    stay, buy = 0.7, 0.4  # survival probability 1-q and purchase probability p
    alive = probability_alive_no_heterogeneity(n=3, tx=1, x=1, p=buy, q=1 - stay)
    # History: purchase in period 1, nothing in periods 2-3. Paths consistent with it:
    survived_all = stay * buy * (stay * (1 - buy)) ** 2
    dropped_before_2 = stay * buy * (1 - stay)
    dropped_before_3 = stay * buy * stay * (1 - buy) * (1 - stay)
    total = survived_all + dropped_before_2 + dropped_before_3
    # "Alive" includes surviving into the next period, hence the final * stay.
    assert alive == pytest.approx(survived_all / total * stay)
    params = BGBBParams(1.204, 0.750, 0.657, 2.783, 0.0, True)  # published estimates, FHS 2010
    expected = bgbb_expected(6, 6, 3, 5, params)
    assert expected > 0


def test_recovery_value_rule():
    """The recovery rule (Knox & van Oest 2014): the justified spend cap is future value times the stay-probability difference — 250 * (0.85 - 0.55) = 75 by hand."""
    result = recovery_value(250, 0.85, 0.55, 0)
    assert result["maximum_financially_justified_recovery_cost"] == pytest.approx(75)
