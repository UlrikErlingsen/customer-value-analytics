#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [[ -x "/opt/anaconda3/bin/python" ]]; then
  PYTHON_BIN="/opt/anaconda3/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' ; then
  echo "WorthSignal needs Python 3.10 or newer."
  read "?Press Return to close."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Preparing WorthSignal for first use..."
  "$PYTHON_BIN" -m venv .venv
fi

# Check that every dependency is importable and meets the version floors in
# requirements.txt.
if ! .venv/bin/python - >/dev/null 2>&1 <<'PYCHECK'
import importlib

FLOORS = {
    "numpy": (1, 24), "openpyxl": (3, 1), "pandas": (2, 0), "plotly": (5, 18),
    "scipy": (1, 10), "sklearn": (1, 3), "statsmodels": (0, 14),
    "streamlit": (1, 38), "xlrd": (2, 0),
}
for module_name, floor in FLOORS.items():
    module = importlib.import_module(module_name)
    version = tuple(int(part) for part in module.__version__.split(".")[:2])
    if version < floor:
        raise SystemExit(1)
PYCHECK
then
  echo "Installing the app's required components (first use only)..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python -m streamlit run app.py --browser.gatherUsageStats false "$@"
