"""File loading, profiling, and export helpers.

Turns an uploaded file into named pandas tables: Excel workbooks
(.xlsx/.xls/.xlsm) yield one table per sheet, a CSV yields a single "data"
table, and JSON yields one table per top-level list/dict (a top-level list of
records becomes a single "data" table; top-level scalars are collected into a
"summary" table). Sources may be file paths or open binary streams, such as
uploads from a web form. Run locally there is no limit on file size, rows or
cells (memory is the limit, and running out of it is a plain DataProblem); a
public demo (``SIGNAL_PUBLIC=1``) applies the caps in ``cva.limits``. Companion
helpers profile a table's columns and export result tables to a formatted Excel
workbook (streamed, split across sheets beyond Excel's row limit), JSON records
or a zip of CSV files; exports neutralize formula-like strings so opening them is
safe.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from cva import limits

EXCEL_MAX_DATA_ROWS = 1_048_575  # Excel's own sheet limit (1,048,576 rows) minus the header row
WIDTH_SAMPLE_ROWS = 2_000  # rows inspected to size export columns
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
    """Apply the public demo's row and cell caps (no-op when run locally)."""
    limits.check_tables({name: (int(frame.shape[0]), int(frame.shape[1])) for name, frame in tables.items()})


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
    ValueError for unsupported extensions and DataProblem (a ValueError) when the
    computer runs out of memory or, in a public demo (``SIGNAL_PUBLIC=1``), a file
    exceeds the demo's upload, expansion, or table-size caps.
    """
    source_name = name or getattr(source, "name", None) or str(source)
    suffix = Path(source_name).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".xlsm", ".csv", ".json"}:
        raise ValueError("Supported files are .xlsx, .xls, .xlsm, .json, and .csv.")

    raw = _source_bytes(source)
    limits.check_upload_bytes(len(raw), json_file=suffix == ".json")
    try:
        if suffix in {".xlsx", ".xls", ".xlsm"}:
            if suffix in {".xlsx", ".xlsm"}:
                with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
                    limits.check_workbook_expansion(sum(member.file_size for member in workbook.infolist()))
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
            tables = {str(k): v for k, v in sheets.items()}
        elif suffix == ".csv":
            tables = {"data": pd.read_csv(io.BytesIO(raw))}
        else:
            payload = json.loads(raw.decode("utf-8-sig"))
            tables = _flatten_json_payload(payload)
    except MemoryError as exc:  # includes pyarrow's ArrowMemoryError
        raise limits.out_of_memory() from exc

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


def _sheet_name(raw_name: object, used: set[str], part: int = 0) -> str:
    """Excel-safe, unique sheet name of at most 31 characters; parts of a split table get " (2)", " (3)" ..."""
    base = "".join(ch if ch not in "[]:*?/\\" else "_" for ch in str(raw_name))[:31] or "Results"
    if part > 1:
        tail = f" ({part})"
        base = f"{base[:31 - len(tail)]}{tail}"
    name = base
    counter = 2
    while name in used:
        suffix = f"_{counter}"
        name = f"{base[:31-len(suffix)]}{suffix}"
        counter += 1
    used.add(name)
    return name


def _excel_value(value: object) -> object:
    """Python value openpyxl can store: NaN/NaT/None become empty cells, numpy scalars become Python scalars."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def results_to_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    """Write result tables to an Excel workbook (one sheet per table) and return the bytes.

    Sheet names are sanitized, truncated to Excel's 31-character limit, and de-duplicated;
    every frame passes through `safe_for_spreadsheet` so formula-like strings stay inert;
    each sheet gets a bold, frozen, filterable header row and readable column widths.
    Rows are streamed (openpyxl write-only mode), so millions of rows do not need
    gigabytes of memory, and a table longer than Excel's sheet limit continues on
    further sheets ("Customer scores (2)", ...) instead of failing: every row is kept.
    """
    workbook = Workbook(write_only=True)
    used: set[str] = set()
    for raw_name, frame in tables.items():
        safe = safe_for_spreadsheet(frame)
        starts = range(0, max(len(safe), 1), EXCEL_MAX_DATA_ROWS)
        for part, start in enumerate(starts, start=1):
            chunk = safe.iloc[start:start + EXCEL_MAX_DATA_ROWS]
            sheet = workbook.create_sheet(_sheet_name(raw_name, used, part if len(starts) > 1 else 0))
            sample = chunk.head(WIDTH_SAMPLE_ROWS)
            for index, column in enumerate(chunk.columns, start=1):
                lengths = sample[column].map(lambda value: len(str(value)) if pd.notna(value) else 0)
                widest = max([len(str(column)), *lengths.tolist()]) if len(sample) else len(str(column))
                sheet.column_dimensions[get_column_letter(index)].width = min(45, max(10, widest + 2))
            sheet.freeze_panes = "A2"
            if len(chunk.columns):
                sheet.auto_filter.ref = f"A1:{get_column_letter(len(chunk.columns))}{len(chunk) + 1}"
            header = []
            for column in chunk.columns:
                cell = WriteOnlyCell(sheet, value=str(column))
                cell.font = Font(bold=True)
                header.append(cell)
            sheet.append(header)
            for row in chunk.itertuples(index=False, name=None):
                sheet.append([_excel_value(value) for value in row])
    if not used:
        workbook.create_sheet("Results")
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def results_to_csv_zip(tables: dict[str, pd.DataFrame]) -> bytes:
    """Every result table as a UTF-8 CSV file (Excel-friendly BOM) in one zip archive; fast for millions of rows."""
    output = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for raw_name, frame in tables.items():
            name = _sheet_name(raw_name, used)
            archive.writestr(f"{name}.csv", safe_for_spreadsheet(frame).to_csv(index=False).encode("utf-8-sig"))
    return output.getvalue()


COMPACT_JSON_ROWS = 100_000  # above this many rows in total, JSON is written compactly by pandas' C encoder


def results_to_json(tables: dict[str, pd.DataFrame]) -> bytes:
    """Serialize result tables to UTF-8 JSON: {table name: list of records}, with missing values as null.

    Small exports are indented for reading; above COMPACT_JSON_ROWS rows the same structure is written
    compactly by pandas (much faster and lighter for millions of rows).
    """
    if sum(len(frame) for frame in tables.values()) <= COMPACT_JSON_ROWS:
        payload = {name: frame.where(pd.notna(frame), None).to_dict(orient="records") for name, frame in tables.items()}
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    parts = [
        json.dumps(str(name), ensure_ascii=False) + ":" + frame.to_json(orient="records", date_format="iso", force_ascii=False)
        for name, frame in tables.items()
    ]
    return ("{" + ",".join(parts) + "}").encode("utf-8")
