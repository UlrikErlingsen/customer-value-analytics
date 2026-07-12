"""File loading, profiling, and export helpers.

Turns an uploaded file into named pandas tables: Excel workbooks
(.xlsx/.xls/.xlsm) yield one table per sheet, a CSV yields a single "data"
table, and JSON yields one table per top-level list/dict (a top-level list of
records becomes a single "data" table; top-level scalars are collected into a
"summary" table). Sources may be file paths or open binary streams, such as
uploads from a web form. Companion helpers profile a table's columns and export
result tables to a formatted Excel workbook or JSON records.
"""

from __future__ import annotations

import io
import json
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd


@dataclass(frozen=True)
class LoadedData:
    """Named tables parsed from one uploaded file, plus the file's display name."""

    tables: dict[str, pd.DataFrame]
    source_name: str


def _flatten_json_payload(payload: Any) -> dict[str, pd.DataFrame]:
    """Map a decoded JSON payload to named tables (see the module docstring for the rules)."""
    if isinstance(payload, list):
        return {"data": pd.json_normalize(payload)}
    if not isinstance(payload, dict):
        return {"data": pd.DataFrame({"value": [payload]})}

    tables: dict[str, pd.DataFrame] = {}
    scalar_items = {key: value for key, value in payload.items() if not isinstance(value, (list, dict))}
    if scalar_items:
        tables["summary"] = pd.DataFrame([scalar_items])
    for key, value in payload.items():
        if isinstance(value, list):
            tables[str(key)] = pd.json_normalize(value)
        elif isinstance(value, dict):
            nested = pd.json_normalize(value)
            tables[str(key)] = nested
    return tables or {"data": pd.json_normalize(payload)}


def load_data(source: str | Path | BinaryIO, name: str | None = None) -> LoadedData:
    """Load an Excel, CSV, or JSON source into named tables.

    `source` may be a path or an open binary stream; the format is chosen from the
    file extension (pass `name` to supply one for anonymous streams). Raises
    ValueError for unsupported extensions.
    """
    source_name = name or getattr(source, "name", None) or str(source)
    suffix = Path(source_name).suffix.lower()
    if hasattr(source, "seek"):
        source.seek(0)

    if suffix in {".xlsx", ".xls", ".xlsm"}:
        sheets = pd.read_excel(source, sheet_name=None)
        return LoadedData({str(k): v for k, v in sheets.items()}, Path(source_name).name)
    if suffix == ".csv":
        return LoadedData({"data": pd.read_csv(source)}, Path(source_name).name)
    if suffix == ".json":
        if hasattr(source, "read"):
            raw = source.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8-sig")
            payload = json.loads(raw)
        else:
            payload = json.loads(Path(source).read_text(encoding="utf-8-sig"))
        return LoadedData(_flatten_json_payload(payload), Path(source_name).name)
    raise ValueError("Supported files are .xlsx, .xls, .xlsm, .json, and .csv.")


def profile_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Describe each column of a table: dtype, non-missing count, missing share, uniques, example value."""
    rows = []
    for column in frame.columns:
        series = frame[column]
        rows.append(
            {
                "column": str(column),
                "type": str(series.dtype),
                "non_missing": int(series.notna().sum()),
                "missing_pct": float(series.isna().mean()),
                "unique": int(series.nunique(dropna=True)),
                "example": "" if series.dropna().empty else str(series.dropna().iloc[0])[:100],
            }
        )
    return pd.DataFrame(rows)


def results_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Write result tables to an Excel workbook (one sheet per table) and return the bytes.

    Sheet names are sanitized, truncated to Excel's 31-character limit, and de-duplicated;
    each sheet gets a bold, frozen, filterable header row and readable column widths.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        used: set[str] = set()
        for raw_name, frame in tables.items():
            base = "".join(ch if ch not in "[]:*?/\\" else "_" for ch in str(raw_name))[:31] or "Results"
            name = base
            counter = 2
            while name in used:
                suffix = f"_{counter}"
                name = f"{base[:31-len(suffix)]}{suffix}"
                counter += 1
            used.add(name)
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.book[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                font = copy(cell.font)
                font.bold = True
                cell.font = font
            for column_cells in sheet.columns:
                width = min(45, max(10, max(len(str(cell.value or "")) for cell in column_cells) + 2))
                sheet.column_dimensions[column_cells[0].column_letter].width = width
    return output.getvalue()


def results_to_json(tables: dict[str, pd.DataFrame]) -> bytes:
    """Serialize result tables to UTF-8 JSON: {table name: list of records}, with missing values as null."""
    payload = {name: frame.where(pd.notna(frame), None).to_dict(orient="records") for name, frame in tables.items()}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
