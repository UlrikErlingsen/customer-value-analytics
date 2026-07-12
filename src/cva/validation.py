"""Friendly validation of user-supplied tables.

Anything can arrive in an uploaded file: numbers stored as text, currency
symbols, mixed date formats, duplicate column choices. The helpers here catch
those problems early and explain them in plain language, so the app can show
"column 'amount' contains text like 'kr 1.200,50'" instead of a pandas
traceback. Analyses keep their full power; only the error messages change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class DataProblem(ValueError):
    """An input problem described in plain language, with a hint on how to fix it."""

    def __init__(self, problem: str, fix: str | None = None):
        self.problem = problem
        self.fix = fix
        super().__init__(problem if fix is None else f"{problem} {fix}")


def _examples_of(series: pd.Series, count: int = 3) -> str:
    values = series.dropna().astype(str).head(count).tolist()
    return ", ".join(f"'{value[:40]}'" for value in values) or "(the column is empty)"


def require_distinct(selections: dict[str, str | None]) -> None:
    """Reject the same column being chosen for two different roles."""
    chosen = {label: column for label, column in selections.items() if column is not None}
    by_column: dict[str, list[str]] = {}
    for label, column in chosen.items():
        by_column.setdefault(column, []).append(label)
    clashes = {column: labels for column, labels in by_column.items() if len(labels) > 1}
    if clashes:
        described = "; ".join(f"'{column}' is chosen as both {' and '.join(labels)}" for column, labels in clashes.items())
        raise DataProblem(
            f"The same column is selected for more than one role: {described}.",
            "Pick a different column for each role.",
        )


def numeric_series(frame: pd.DataFrame, column: str, label: str, minimum_rows: int = 1) -> pd.Series:
    """Return ``frame[column]`` as numbers, or explain why that is impossible.

    Values that cannot be read as numbers become missing; if none (or too few)
    remain, a ``DataProblem`` explains what the column actually contains.
    """
    if column not in frame.columns:
        raise DataProblem(
            f"The column '{column}' (used as {label}) is not in the current table.",
            "You may have switched to a different sheet after choosing columns — pick the column again.",
        )
    coerced = pd.to_numeric(frame[column], errors="coerce")
    usable = int(coerced.notna().sum())
    if usable == 0:
        raise DataProblem(
            f"The column '{column}' (used as {label}) does not contain usable numbers. "
            f"Its first values look like: {_examples_of(frame[column])}.",
            "If the numbers are stored as text — with currency symbols, spaces, or commas as decimals — "
            "clean the column in Excel first, or export the file again with plain numbers.",
        )
    if usable < minimum_rows:
        raise DataProblem(
            f"Only {usable:,} of {len(coerced):,} rows in '{column}' (used as {label}) are readable numbers, "
            f"but this analysis needs at least {minimum_rows}.",
            "Add more rows of history, or clean the rows whose values cannot be read as numbers.",
        )
    return coerced


def date_series(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    """Return ``frame[column]`` as dates, or explain why that is impossible."""
    if column not in frame.columns:
        raise DataProblem(
            f"The column '{column}' (used as {label}) is not in the current table.",
            "You may have switched to a different sheet after choosing columns — pick the column again.",
        )
    parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    if not parsed.notna().any():
        raise DataProblem(
            f"The column '{column}' (used as {label}) does not contain readable dates. "
            f"Its first values look like: {_examples_of(frame[column])}.",
            "Dates in a form like 2025-03-14 or 14.03.2025 work best.",
        )
    return parsed


def binary_series(frame: pd.DataFrame, column: str, label: str) -> pd.Series:
    """Return ``frame[column]`` as 0/1 values, accepting yes/no style text."""
    if column not in frame.columns:
        raise DataProblem(
            f"The column '{column}' (used as {label}) is not in the current table.",
            "You may have switched to a different sheet after choosing columns — pick the column again.",
        )
    lookup = {"yes": 1, "no": 0, "y": 1, "n": 0, "true": 1, "false": 0, "ja": 1, "nei": 0}
    mapped = frame[column].map(lambda value: lookup.get(str(value).strip().lower(), value))
    coerced = pd.to_numeric(mapped, errors="coerce")
    values = set(coerced.dropna().unique())
    if not values:
        raise DataProblem(
            f"The column '{column}' (used as {label}) contains no usable 0/1 values. "
            f"Its first values look like: {_examples_of(frame[column])}.",
            "Use 1 for yes/responded and 0 for no.",
        )
    if not values <= {0, 1}:
        extras = ", ".join(str(value) for value in sorted(values - {0, 1})[:5])
        raise DataProblem(
            f"The column '{column}' (used as {label}) should only contain 0 and 1, but also has: {extras}.",
            "Recode the column so 1 means yes/responded and 0 means no.",
        )
    return coerced


def skipped_rows_note(coerced: pd.Series, column: str) -> str | None:
    """A short note when some rows were unreadable and will be skipped."""
    skipped = int(coerced.isna().sum())
    if skipped == 0:
        return None
    return f"{skipped:,} of {len(coerced):,} rows in '{column}' could not be read and will be skipped."


def friendly_message(exc: BaseException) -> str:
    """Translate an exception into a message a non-technical user can act on."""
    if isinstance(exc, DataProblem):
        return str(exc)
    text = str(exc)
    if isinstance(exc, KeyError):
        return (
            f"A column the analysis needs ({text}) was not found in the current table. "
            "You may have switched sheets after choosing columns — pick the columns again."
        )
    if "could not convert string to float" in text or "Unable to parse string" in text:
        return (
            "A column that should contain numbers contains text. "
            "Remove currency symbols and thousands separators, or export the file again with plain numbers. "
            f"(Details: {text})"
        )
    if "singular matrix" in text.lower():
        return (
            "The model could not be estimated because one of the predictor columns uniquely identifies rows "
            "(this is typical for ID columns) or duplicates another column. "
            "Remove ID-like or duplicate columns from the predictor list and run again."
        )
    if "convergence" in text.lower() or "did not converge" in text.lower():
        return (
            "The model could not be estimated from this data. This usually means there are too few rows, "
            f"or too little variation in the values. (Details: {text})"
        )
    return f"The analysis stopped: {text}"
