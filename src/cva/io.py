"""File loading, profiling, and export helpers.

Turns an uploaded file into named pandas tables: Excel workbooks
(.xlsx/.xls/.xlsm) yield one table per sheet, a CSV yields a single "data"
table, and JSON yields one table per top-level list/dict (a top-level list of
records becomes a single "data" table; top-level scalars are collected into a
"summary" table). Sources may be file paths or open binary streams, such as
uploads from a web form. Uploads are size-checked before parsing so a single
file cannot exhaust local memory. Companion helpers profile a table's columns
and export result tables to a formatted Excel workbook or JSON records; Excel
exports neutralize formula-like strings so opening them is safe.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from cva.validation import DataProblem

MAX_UPLOAD_MB = max(1, min(int(os.getenv("CVA_MAX_UPLOAD_MB", "200")), 1000))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_JSON_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_EXCEL_BYTES = 400 * 1024 * 1024
MAX_TABLE_ROWS = 1_000_000
MAX_TOTAL_CELLS = 10_000_000
ILLEGAL_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class LoadedData:
    """Named tables parsed from one uploaded file, plus the file's display name."""

    tables: dict[str, pd.DataFrame]
    source_name: str


def _source_bytes(source: str | Path | BinaryIO) -> bytes:
    """Return the raw bytes behind a path or open binary stream."""
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "seek"):
        source.seek(0)
    raw = source.read()
    return raw if isinstance(raw, bytes) else str(raw).encode("utf-8")


def _check_table_sizes(tables: dict[str, pd.DataFrame]) -> None:
    """Reject parsed tables that exceed the local row and cell safety limits."""
    total_cells = 0
    for table_name, frame in tables.items():
        total_cells += int(frame.shape[0] * frame.shape[1])
        if len(frame) > MAX_TABLE_ROWS or total_cells > MAX_TOTAL_CELLS:
            raise DataProblem(
                f"The table '{table_name}' pushes this file past the local safety limit "
                f"of {MAX_TABLE_ROWS:,} rows per table or {MAX_TOTAL_CELLS:,} cells in total.",
                "Keep fewer rows or columns and upload again.",
            )


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
    ValueError for unsupported extensions and DataProblem (a ValueError) when a
    file exceeds the upload, expansion, or table-size limits.
    """
    source_name = name or getattr(source, "name", None) or str(source)
    suffix = Path(source_name).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".xlsm", ".csv", ".json"}:
        raise ValueError("Supported files are .xlsx, .xls, .xlsm, .json, and .csv.")

    raw = _source_bytes(source)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DataProblem(
            f"This file is larger than the configured {MAX_UPLOAD_MB} MB upload limit.",
            "Remove unneeded sheets, rows, or columns — or raise CVA_MAX_UPLOAD_MB if you truly need more.",
        )

    if suffix in {".xlsx", ".xls", ".xlsm"}:
        if suffix in {".xlsx", ".xlsm"}:
            with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
                expanded_size = sum(member.file_size for member in workbook.infolist())
                if expanded_size > MAX_UNCOMPRESSED_EXCEL_BYTES:
                    raise DataProblem(
                        "This workbook expands beyond 400 MB when unpacked.",
                        "Keep only the sheets the analysis needs and upload again.",
                    )
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        tables = {str(k): v for k, v in sheets.items()}
    elif suffix == ".csv":
        tables = {"data": pd.read_csv(io.BytesIO(raw))}
    else:
        if len(raw) > MAX_JSON_BYTES:
            raise DataProblem(
                "JSON uploads are limited to 50 MB because they expand in memory.",
                "Export the same data as CSV or Excel instead.",
            )
        payload = json.loads(raw.decode("utf-8-sig"))
        tables = _flatten_json_payload(payload)

    _check_table_sizes(tables)
    return LoadedData(tables, Path(source_name).name)


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


def _unique_column_names(columns: list[object]) -> list[str]:
    """De-duplicate column labels so a sanitized header row stays unambiguous."""
    result: list[str] = []
    used: set[str] = set()
    for index, column in enumerate(columns):
        base = str(column).strip() or f"column_{index + 1}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}__{suffix}"
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result


def safe_for_spreadsheet(frame: pd.DataFrame) -> pd.DataFrame:
    """Neutralize strings that spreadsheet programs could interpret as formulas.

    Both cell values and column headers are prefixed with an apostrophe when they
    start with ``=``, ``+``, ``-``, or ``@``, and characters that are illegal in
    Excel's XML are stripped, so opening an export can never execute anything.
    """
    safe = frame.copy()

    def neutralize(value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = ILLEGAL_XML_CHARACTERS.sub("", value)
        return "'" + cleaned if cleaned.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else cleaned

    safe.columns = _unique_column_names([neutralize(str(column)) for column in safe.columns])
    for column in safe.columns:
        series = safe[column].astype(object) if isinstance(safe[column].dtype, pd.CategoricalDtype) else safe[column]
        safe[column] = series.map(neutralize)
    return safe


def results_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Write result tables to an Excel workbook (one sheet per table) and return the bytes.

    Sheet names are sanitized, truncated to Excel's 31-character limit, and de-duplicated;
    every frame passes through `safe_for_spreadsheet` so formula-like strings stay inert;
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
            safe_for_spreadsheet(frame).to_excel(writer, sheet_name=name, index=False)
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
