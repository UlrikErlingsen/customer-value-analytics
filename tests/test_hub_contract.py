"""Signal Hub contract: importable UI entry point, Streamlit only under ui/, slug-namespaced state."""

import ast
from pathlib import Path
import re
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from cva import __version__


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "cva"
UI = PACKAGE / "ui"
UI_ONLY_LIBRARIES = {"streamlit", "plotly"}
CORE_MODULES = (
    "cva", "cva.bgbb", "cva.bgnbd", "cva.clv", "cva.complaints", "cva.contractual", "cva.equity",
    "cva.investment", "cva.io", "cva.markov", "cva.schema", "cva.selection", "cva.templates", "cva.validation",
)
# Every Streamlit call that creates a stateful widget (or a keyed chart) must pass an explicit key.
KEYED_CALLS = {
    "button", "checkbox", "data_editor", "date_input", "download_button", "file_uploader", "multiselect",
    "number_input", "chart", "plotly_chart", "radio", "selectbox", "slider", "text_input", "toggle",
}
PAGES = [
    "Start & data check",
    "Customer selection",
    "Customer lifetime value",
    "Customer equity",
    "Acquisition & retention budgets",
    "Markov ROI",
    "Contractual retention",
    "BG/NBD continuous time",
    "BG/BB discrete time",
    "Complaints & recovery",
    "About this app",
]
RENDER_SCRIPT = """
from cva.ui import render

render()
"""


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_ui_entry_point_matches_the_hub_contract() -> None:
    from cva.ui import APP_INFO, render

    assert callable(render)
    assert APP_INFO == {
        "product": "Worth Signal",
        "version": __version__,
        "repo": "customer-value-analytics",
        "slug": "worth",
    }


def test_only_the_ui_package_imports_streamlit_or_plotly() -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(_imported_roots(path) & UI_ONLY_LIBRARIES)
        for path in PACKAGE.rglob("*.py")
        if UI not in path.parents and _imported_roots(path) & UI_ONLY_LIBRARIES
    }
    assert not offenders, offenders


def test_core_package_imports_without_streamlit_or_plotly() -> None:
    # A fresh interpreter, so modules already imported by other tests cannot hide a stray import.
    code = (
        f"import sys\nsys.path.insert(0, {str(ROOT / 'src')!r})\n"
        f"import importlib\nfor name in {CORE_MODULES!r}:\n    importlib.import_module(name)\n"
        "loaded = sorted(name for name in ('streamlit', 'plotly') if name in sys.modules)\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_render_works_from_the_packaged_files_alone(tmp_path: Path) -> None:
    # Signal Hub installs the release as a normal package: only src/cva/**/*.py and the declared package data
    # ("cva.ui": assets/marks/*) exist there, so render() must not read examples/, docs/ or assets/ at the repo root.
    for path in PACKAGE.rglob("*"):
        relative = path.relative_to(PACKAGE)
        packaged = path.suffix == ".py" or relative.parent == Path("ui", "assets", "marks")
        if path.is_file() and packaged and "__pycache__" not in relative.parts:
            target = tmp_path / "site" / "cva" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    site = str(tmp_path / "site")
    script = f"import sys\nsys.path.insert(0, {site!r})\nfrom cva.ui import render\nrender()\n"
    code = (
        f"import sys\nsys.path.insert(0, {site!r})\n"
        "from pathlib import Path\n"
        "from streamlit.testing.v1 import AppTest\n"
        "import cva\n"
        f"assert Path(cva.__file__).is_relative_to({site!r}), cva.__file__\n"
        "from cva.ui import signal_theme as sig\n"
        "assert Path(sig.page_config('worth')['page_icon']).exists()\n"
        f"app = AppTest.from_string({script!r}, default_timeout=120)\n"
        "app.run()\n"
        "assert not app.exception, [error.value for error in app.exception]\n"
        "app.sidebar.radio[0].set_value('Customer selection').run()\n"
        "assert not app.exception, [error.value for error in app.exception]\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_render_never_sets_page_config_or_navigation() -> None:
    for path in UI.glob("*.py"):
        if path.name == "signal_theme.py":
            continue
        source = path.read_text(encoding="utf-8")
        for call in ("st.set_page_config(", "st.navigation(", "st.Page(", "st.stop("):
            assert call not in source, (path.name, call)


def test_render_runs_from_a_script_without_set_page_config() -> None:
    app = AppTest.from_string(RENDER_SCRIPT, default_timeout=120)
    app.run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.sidebar.radio[0].key == "worth:page"
    assert "worth:upload" in app.session_state
    assert "_worthsignal_upload" not in app.session_state
    body = "\n".join(str(item.value) for item in app.markdown)
    assert "FROM ROWS TO RELATIONSHIPS" in body
    assert "OPEN CUSTOMER VALUE TOOLKIT" in body
    assert f"Worth Signal v{__version__}" in body


@pytest.mark.parametrize("page", PAGES)
def test_every_widget_key_is_namespaced(page: str) -> None:
    app = AppTest.from_string(RENDER_SCRIPT, default_timeout=120)
    app.run()
    app.sidebar.radio[0].set_value(page).run()

    assert not app.exception, [error.value for error in app.exception]
    widgets = [
        *app.radio, *app.selectbox, *app.checkbox, *app.toggle, *app.button, *app.number_input,
        *app.multiselect, *app.slider, *app.date_input,
    ]
    assert widgets
    unkeyed = [(type(widget).__name__, widget.label) for widget in widgets if widget.key is None]
    assert not unkeyed, unkeyed
    assert all(widget.key.startswith("worth:") for widget in widgets)


def test_every_widget_call_passes_an_explicit_key() -> None:
    # Most data-driven widgets only appear after an upload, which AppTest cannot simulate; check the source too.
    tree = ast.parse((UI / "app.py").read_text(encoding="utf-8"))
    unkeyed = [
        (node.lineno, node.func.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in KEYED_CALLS
        and not any(keyword.arg == "key" for keyword in node.keywords)
    ]
    assert not unkeyed, unkeyed


def test_session_state_and_widget_keys_go_through_the_namespace_helper() -> None:
    source = (UI / "app.py").read_text(encoding="utf-8")
    state_keys = re.findall(r"session_state(?:\[|\.get\(|\.pop\()\s*([^,\])]+)", source)
    widget_keys = re.findall(r"\bkey=([^,)\n]+)", source)
    assert state_keys and widget_keys
    assert all(key.startswith("k(") for key in state_keys), state_keys
    # column_select forwards a key its callers already built with k().
    assert all(key.startswith("k(") or key == "key" for key in widget_keys), widget_keys
    assert 'NS = "worth"' in source
