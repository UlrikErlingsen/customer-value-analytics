"""Reference examples pinning each model to values from the published literature.

Every expected number below is either derived analytically from the cited
paper's formulas or reproduces a worked reference example, so these tests
guard the implementations against accidental changes in behavior. The
numeric values and assertions are fixed; if a test fails, the code — not the
expected value — is wrong.
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
from cva.investment import curve_steepness, optimize_budgets, response_rate
from cva.markov import choice_probabilities, markov_clv
from cva.selection import minimum_profitable_probability, rfm_scores, weighted_split_gini


def test_clv_reference_example_and_elasticity():
    """Margin-multiple CLV per Gupta & Lehmann (2003): margin 80, retention 0.84, discount 0.12 gives CLV 240 (multiple 3) and retention elasticity 4."""
    assert gupta_lehmann_clv(80, 0.84, 0.12) == pytest.approx(240.0)
    assert retention_elasticity(0.84, 0.12) == pytest.approx(4.0)
    assert finite_horizon_clv(80, 0.84, 0.12, 5) == pytest.approx(sum(80 * 0.75**t for t in range(1, 6)))


def test_targeting_threshold_and_gini():
    """Break-even targeting probability and size-weighted Gini impurity, both computed directly from their definitions."""
    assert minimum_profitable_probability(20, -1) == pytest.approx(1 / 21)
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


def test_blattberg_deighton_reference_values():
    """Acquisition/retention budget optimization reference example per Blattberg & Deighton (1996)."""
    beta = curve_steepness(8, 0.40, 0.70)
    assert response_rate(8, 0.70, beta) == pytest.approx(0.40)
    result = optimize_budgets(5, 0.20, 0.40, 8, 0.40, 0.70, 50, 0.12)
    assert result.optimal_acquisition_spend == pytest.approx(10.08, abs=0.08)
    assert result.optimal_retention_spend == pytest.approx(15.93, abs=0.10)
    assert result.optimal_value == pytest.approx(11.88, abs=0.05)


def test_markov_choice_path_and_clv():
    """Markov brand-switching reference example per Rust, Lemon & Zeithaml (2004): choice probabilities propagate through the transition matrix and discount to a CLV."""
    matrix = np.array([[0.8, 0.2], [0.3, 0.7]])
    path = choice_probabilities(matrix, previous_choice=0, occasions=3)
    assert path["company_1"].to_list() == pytest.approx([0.8, 0.7, 0.65])
    value, _ = markov_clv(matrix, 0, 0, 100, 0.20, 2, 0.12, 3)
    assert value == pytest.approx(78.87, abs=0.05)


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
    """BG/BB building blocks per Fader, Hardie & Shang (2010): the fixed-parameter alive probability and a finite expected-purchases forecast."""
    alive = probability_alive_no_heterogeneity(n=3, tx=1, x=1, p=0.5, q=0.2)
    assert alive == pytest.approx(0.2909090909)
    params = BGBBParams(1.204, 0.750, 0.657, 2.783, 0.0, True)
    expected = bgbb_expected(6, 6, 3, 5, params)
    assert expected > 0


def test_recovery_value_reference_example():
    """Complaint-recovery reference example per Knox & van Oest (2014): the value retained by recovery caps the financially justified recovery spend."""
    result = recovery_value(200, 0.90, 0.60, 0)
    assert result["maximum_financially_justified_recovery_cost"] == pytest.approx(60)
