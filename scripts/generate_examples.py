"""Regenerate the files in examples/ from the template definitions.

Run from the repository root:

    .venv/bin/python scripts/generate_examples.py

The example *data* is deterministic (fixed random seeds), so the tables only
change when ``src/cva/templates.py`` changes. The ``.xlsx`` files still differ
byte-for-byte between runs because Excel workbooks embed a creation timestamp —
only regenerate and commit them when the templates actually changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cva.templates import example_json, template_csv, template_workbook  # noqa: E402


def main() -> None:
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)
    (examples / "example_data.xlsx").write_bytes(template_workbook(small=False))
    (examples / "quick_test.xlsx").write_bytes(template_workbook(small=True))
    (examples / "transactions.csv").write_bytes(template_csv("transactions", small=False))
    (examples / "example_data.json").write_bytes(example_json(small=False))
    for name in ["example_data.xlsx", "quick_test.xlsx", "transactions.csv", "example_data.json"]:
        size = (examples / name).stat().st_size
        print(f"wrote examples/{name} ({size:,} bytes)")


if __name__ == "__main__":
    main()
