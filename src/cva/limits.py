"""Data limits: none when the app runs on your own computer; hard caps only in a public demo (``SIGNAL_PUBLIC=1``).

Signal suite contract (Signal Hub ``docs/APP_CONTRACT.md`` § 9): run locally — standalone, a local Signal Hub, an
internal company deployment or as a Python library — Worth Signal imposes no limit on file size, rows or cells; the
computer's memory is the limit, and running out of memory is reported as a plain message. A public demo server sets
``SIGNAL_PUBLIC=1`` (Signal Hub's public Docker image does), and then the caps below protect the shared server.
Every cap lives in this module, and the environment is read at call time.
"""

from __future__ import annotations

import os

from cva.validation import DataProblem

DEMO_MAX_UPLOAD_MB = 50
DEMO_MAX_JSON_MB = 50
DEMO_MAX_UNCOMPRESSED_EXCEL_MB = 400
DEMO_MAX_TABLE_ROWS = 1_000_000
DEMO_MAX_TOTAL_CELLS = 10_000_000
DEMO_NOTE = "This is a limit of the public demo; the downloaded app has no built-in limit."
OUT_OF_MEMORY = DataProblem(
    "There is not enough memory on this computer for this file or analysis.",
    "Close other programs, keep only the columns the analysis needs, or group customers with identical histories "
    "into one row with a count column (BG/NBD and BG/BB give identical results).",
)


def public_demo() -> bool:
    """True on a public demo server (``SIGNAL_PUBLIC=1``); independent of Signal Hub mode (``SIGNAL_HUB``)."""
    return os.environ.get("SIGNAL_PUBLIC") == "1"


def out_of_memory() -> DataProblem:
    """A fresh copy of the plain out-of-memory message (raise it ``from`` the MemoryError)."""
    return DataProblem(OUT_OF_MEMORY.problem, OUT_OF_MEMORY.fix)


def check_upload_bytes(size: int, *, json_file: bool = False) -> None:
    if not public_demo():
        return
    if size > DEMO_MAX_UPLOAD_MB * 1024 * 1024:
        raise DataProblem(f"Uploads are limited to {DEMO_MAX_UPLOAD_MB} MB.", DEMO_NOTE)
    if json_file and size > DEMO_MAX_JSON_MB * 1024 * 1024:
        raise DataProblem(f"JSON uploads are limited to {DEMO_MAX_JSON_MB} MB.", DEMO_NOTE)


def check_workbook_expansion(expanded_bytes: int) -> None:
    if public_demo() and expanded_bytes > DEMO_MAX_UNCOMPRESSED_EXCEL_MB * 1024 * 1024:
        raise DataProblem(
            f"This workbook expands beyond {DEMO_MAX_UNCOMPRESSED_EXCEL_MB} MB when unpacked.",
            "Keep only the sheets the analysis needs. " + DEMO_NOTE,
        )


def check_tables(shapes: dict[str, tuple[int, int]]) -> None:
    """Rows per table and cells in total, for the parsed tables of one file."""
    if not public_demo():
        return
    total_cells = 0
    for table_name, (rows, columns) in shapes.items():
        total_cells += rows * columns
        if rows > DEMO_MAX_TABLE_ROWS or total_cells > DEMO_MAX_TOTAL_CELLS:
            raise DataProblem(
                f"The table '{table_name}' pushes this file past the demo limit of {DEMO_MAX_TABLE_ROWS:,} rows per "
                f"table or {DEMO_MAX_TOTAL_CELLS:,} cells in total.",
                DEMO_NOTE,
            )
