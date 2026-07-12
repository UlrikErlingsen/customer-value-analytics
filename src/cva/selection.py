"""Customer selection: RFM segmentation and response-model targeting.

Answers the business question "which customers should receive the next
campaign?" using two classic direct-marketing toolkits: RFM scoring
(nested quintile scores on recency, frequency, and monetary value, where
score 1 marks the best customers) and response models (logistic
regression and decision trees) evaluated with lift tables and a
break-even profit threshold. Inputs are per-customer behavioral fields
or a raw transaction log plus the profit of a response vs. no response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier, export_text


def _quantile_score(series: pd.Series, higher_is_better: bool, groups: int = 5) -> pd.Series:
    """Assign quantile scores 1..groups where 1 is always the best value.

    Ranks first (ties broken by row order) so equal-sized groups are formed
    even with heavily tied data; shrinks the number of groups when there are
    fewer valid or distinct values than requested.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.notna()
    result = pd.Series(pd.NA, index=series.index, dtype="Int64")
    if not valid.any():
        return result
    bins = min(groups, int(valid.sum()), int(numeric[valid].nunique()))
    if bins <= 1:
        result.loc[valid] = 1
        return result
    ranked = numeric[valid].rank(method="first", ascending=not higher_is_better)
    result.loc[valid] = pd.qcut(ranked, q=bins, labels=range(1, bins + 1)).astype(int)
    return result


def rfm_scores(
    frame: pd.DataFrame,
    recency: str,
    frequency: str,
    monetary: str,
    groups: int = 5,
    nested: bool = True,
) -> pd.DataFrame:
    """Score each customer on Recency, Frequency, and Monetary value (1 = best).

    Classic direct-marketing RFM scoring. With ``nested=True`` (the traditional
    nested approach), frequency quintiles are computed within each recency
    group and monetary quintiles within each recency-frequency cell; with
    ``nested=False`` each dimension is scored independently. Adds R/F/M scores,
    a combined "R-F-M" segment label, and the total score.
    """
    result = frame.copy()
    result["R_score"] = _quantile_score(result[recency], higher_is_better=False, groups=groups)
    if nested:
        result["F_score"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        result["M_score"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        for _, r_index in result.groupby("R_score", dropna=True).groups.items():
            result.loc[r_index, "F_score"] = _quantile_score(
                result.loc[r_index, frequency], higher_is_better=True, groups=groups
            )
        for _, rf_index in result.groupby(["R_score", "F_score"], dropna=True).groups.items():
            result.loc[rf_index, "M_score"] = _quantile_score(
                result.loc[rf_index, monetary], higher_is_better=True, groups=groups
            )
    else:
        result["F_score"] = _quantile_score(result[frequency], higher_is_better=True, groups=groups)
        result["M_score"] = _quantile_score(result[monetary], higher_is_better=True, groups=groups)
    result["RFM_segment"] = result[["R_score", "F_score", "M_score"]].astype("string").agg("-".join, axis=1)
    result["RFM_total"] = result[["R_score", "F_score", "M_score"]].sum(axis=1, min_count=3)
    return result


def rfm_from_transactions(
    transactions: pd.DataFrame,
    customer_id: str,
    date: str,
    amount: str,
    observation_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Aggregate a raw transaction log into per-customer RFM inputs.

    Returns one row per customer with recency in days (relative to
    ``observation_date``, defaulting to the last transaction date), purchase
    count, average purchases per month, and average and total spend.
    """
    data = transactions[[customer_id, date, amount]].copy()
    data[date] = pd.to_datetime(data[date], errors="coerce")
    data[amount] = pd.to_numeric(data[amount], errors="coerce")
    data = data.dropna(subset=[customer_id, date, amount])
    if data.empty:
        raise ValueError("No valid transaction rows remain after parsing customer, date, and amount.")
    end = pd.Timestamp(observation_date) if observation_date is not None else data[date].max()
    start = data[date].min()
    months = max((end - start).days / 30.4375, 1 / 30.4375)
    grouped = data.groupby(customer_id).agg(
        last_purchase=(date, "max"),
        purchase_count=(date, "size"),
        monetary_average=(amount, "mean"),
        monetary_total=(amount, "sum"),
    )
    grouped["recency_days"] = (end - grouped["last_purchase"]).dt.days
    grouped["frequency_per_month"] = grouped["purchase_count"] / months
    return grouped.reset_index()


def gini(response_rate: float) -> float:
    """Gini impurity 2p(1-p) of a group with response rate p."""
    p = float(response_rate)
    if not 0 <= p <= 1:
        raise ValueError("Response rate must be between 0 and 1.")
    return 2 * p * (1 - p)


def weighted_split_gini(group_sizes: Sequence[float], responders: Sequence[float]) -> float:
    """Size-weighted Gini impurity across the groups produced by a split.

    Lower values mean the split separates responders from non-responders
    better; this is the quantity a Gini-based decision tree minimizes.
    """
    sizes = np.asarray(group_sizes, dtype=float)
    responses = np.asarray(responders, dtype=float)
    if sizes.shape != responses.shape or np.any(sizes <= 0) or np.any(responses < 0) or np.any(responses > sizes):
        raise ValueError("Each group needs a positive size and responders between zero and group size.")
    return float(np.sum((sizes / sizes.sum()) * 2 * (responses / sizes) * (1 - responses / sizes)))


def minimum_profitable_probability(profit_if_response: float, profit_if_no_response: float) -> float:
    """Break-even response probability above which contacting a customer pays off.

    Solves p * profit_if_response + (1 - p) * profit_if_no_response = 0, the
    standard direct-marketing targeting threshold.
    """
    difference = profit_if_response - profit_if_no_response
    if difference <= 0:
        raise ValueError("Profit if response must exceed profit if no response.")
    threshold = -profit_if_no_response / difference
    return float(np.clip(threshold, 0, 1))


def lift_table(actual: Sequence[float], predicted: Sequence[float], groups: int = 10) -> pd.DataFrame:
    """Decile lift table: sort by predicted score, split into groups, compare to the base rate.

    Reports two cumulative measures: ``summed_decile_lift`` is the running
    sum of per-decile lifts (a simple additive convention), while
    ``standard_cumulative_lift`` is the conventional definition — cumulative
    response rate of the top deciles divided by the overall base rate.
    """
    data = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if data.empty:
        raise ValueError("Actual and predicted values are empty after removing missing values.")
    groups = min(groups, len(data))
    data = data.sort_values("predicted", ascending=False).reset_index(drop=True)
    data["decile"] = pd.qcut(data.index + 1, q=groups, labels=range(1, groups + 1)).astype(int)
    base_rate = float(data["actual"].mean())
    table = data.groupby("decile", as_index=False).agg(
        customers=("actual", "size"), responses=("actual", "sum"), response_rate=("actual", "mean")
    )
    table["lift"] = table["response_rate"] / base_rate if base_rate > 0 else np.nan
    table["summed_decile_lift"] = table["lift"].cumsum()
    table["cumulative_response_rate"] = table["responses"].cumsum() / table["customers"].cumsum()
    table["standard_cumulative_lift"] = table["cumulative_response_rate"] / base_rate if base_rate > 0 else np.nan
    return table


@dataclass
class LogisticResult:
    """Fitted logistic response model: per-row predicted probabilities, a coefficient table (with Wald statistics and odds ratios), and model/null log-likelihoods."""

    predictions: pd.Series
    coefficients: pd.DataFrame
    log_likelihood: float
    null_log_likelihood: float


def fit_logistic(frame: pd.DataFrame, outcome: str, predictors: Sequence[str]) -> LogisticResult:
    """Fit a logistic regression of a 0/1 response on the given predictors.

    Categorical predictors are dummy-coded, missing numeric values are filled
    with the column median, and predictions are returned aligned to the
    original frame's index (NaN where the outcome was missing).
    """
    data = frame[[outcome, *predictors]].copy()
    y = pd.to_numeric(data.pop(outcome), errors="coerce")
    x = pd.get_dummies(data, drop_first=True, dtype=float)
    x = x.apply(pd.to_numeric, errors="coerce")
    x = x.fillna(x.median(numeric_only=True)).fillna(0.0)
    valid = y.notna()
    y = y.loc[valid].astype(float)
    x = x.loc[valid]
    if y.nunique() != 2:
        raise ValueError("The response column must contain both 0 and 1.")
    design = sm.add_constant(x, has_constant="add")
    model = sm.Logit(y, design).fit(disp=False, maxiter=500)
    params = pd.DataFrame(
        {
            "term": model.params.index,
            "coefficient": model.params.values,
            "std_error": model.bse.values,
            "wald": np.square(model.params.values / model.bse.values),
            "p_value": model.pvalues.values,
            "odds_ratio": np.exp(model.params.values),
        }
    )
    predictions = pd.Series(np.nan, index=frame.index, name="predicted_probability")
    predictions.loc[valid] = model.predict(design)
    return LogisticResult(predictions, params, float(model.llf), float(model.llnull))


@dataclass
class TreeResult:
    """Fitted decision-tree response model: per-row predicted probabilities, a text rendering of the tree rules, and feature importances."""

    predictions: pd.Series
    rules: str
    feature_importance: pd.DataFrame


def fit_decision_tree(
    frame: pd.DataFrame,
    outcome: str,
    predictors: Sequence[str],
    max_depth: int = 4,
    min_samples_leaf: int = 50,
) -> TreeResult:
    """Fit a CART classification tree (Gini impurity splits) to a 0/1 response.

    Numeric predictors get median imputation; categorical predictors get
    most-frequent imputation plus one-hot encoding. ``max_depth`` and
    ``min_samples_leaf`` keep the tree small enough to read as rules.
    """
    data = frame[[outcome, *predictors]].copy()
    y = pd.to_numeric(data.pop(outcome), errors="coerce")
    valid = y.notna()
    x = data.loc[valid]
    y = y.loc[valid].astype(int)
    if y.nunique() != 2:
        raise ValueError("The response column must contain both 0 and 1.")
    numeric = [column for column in predictors if pd.api.types.is_numeric_dtype(x[column])]
    categorical = [column for column in predictors if column not in numeric]
    transformer = ColumnTransformer(
        [
            ("numeric", SimpleImputer(strategy="median"), numeric),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    estimator = DecisionTreeClassifier(
        criterion="gini", max_depth=max_depth, min_samples_leaf=min_samples_leaf, random_state=42
    )
    pipeline = Pipeline([("preprocess", transformer), ("tree", estimator)])
    pipeline.fit(x, y)
    probabilities = pipeline.predict_proba(x)[:, 1]
    predictions = pd.Series(np.nan, index=frame.index, name="predicted_probability")
    predictions.loc[valid] = probabilities
    feature_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    tree = pipeline.named_steps["tree"]
    importance = pd.DataFrame({"feature": feature_names, "importance": tree.feature_importances_}).sort_values(
        "importance", ascending=False
    )
    rules = export_text(tree, feature_names=list(feature_names), decimals=4)
    return TreeResult(predictions, rules, importance)


def targeting_profit(
    actual: Sequence[float],
    predicted: Sequence[float],
    profit_if_response: float,
    profit_if_no_response: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Target every customer above the break-even probability and tally the profit.

    Returns the per-customer detail (target flag, expected and realized
    profit) plus a summary with the threshold, counts, and total realized
    profit of the targeted group.
    """
    threshold = minimum_profitable_probability(profit_if_response, profit_if_no_response)
    result = pd.DataFrame({"actual": actual, "predicted_probability": predicted})
    result["target"] = result["predicted_probability"] > threshold
    result["expected_profit"] = result["predicted_probability"] * profit_if_response + (
        1 - result["predicted_probability"]
    ) * profit_if_no_response
    result["realized_profit"] = np.where(
        result["target"], np.where(result["actual"] == 1, profit_if_response, profit_if_no_response), 0.0
    )
    summary = {
        "threshold": threshold,
        "customers_targeted": float(result["target"].sum()),
        "responses_targeted": float(result.loc[result["target"], "actual"].sum()),
        "realized_profit": float(result["realized_profit"].sum()),
    }
    return result, summary

