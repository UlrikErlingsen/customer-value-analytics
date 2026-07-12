@echo off
rem Customer Value Analytics - Windows launcher.
rem Double-click this file. The first start creates a local .venv folder and
rem installs everything the app needs; later starts skip the installation.
setlocal
cd /d "%~dp0"

rem Find Python 3 (the py launcher comes with the python.org installer).
set "PYTHON_BIN=py -3"
%PYTHON_BIN% -c "import sys" >nul 2>nul || set "PYTHON_BIN=python"
%PYTHON_BIN% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul || (
  echo Customer Value Analytics needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" during installation, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparing Customer Value Analytics for first use...
  %PYTHON_BIN% -m venv .venv
)

rem Install/upgrade dependencies when anything is missing or older than requirements.txt allows.
".venv\Scripts\python.exe" -c "import importlib, sys; floors = {'numpy': (1, 24), 'openpyxl': (3, 1), 'pandas': (2, 0), 'plotly': (5, 18), 'scipy': (1, 10), 'sklearn': (1, 3), 'statsmodels': (0, 14), 'streamlit': (1, 38), 'xlrd': (2, 0)}; sys.exit(0 if all(tuple(int(p) for p in importlib.import_module(m).__version__.split('.')[:2]) >= f for m, f in floors.items()) else 1)" >nul 2>nul || (
  echo Installing the app's required components. The first time this takes a few minutes...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo Starting Customer Value Analytics - a browser tab will open shortly.
".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats false
pause
