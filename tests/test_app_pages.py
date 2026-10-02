"""Every page of the Streamlit app must render without raising.

Uses Streamlit's built-in AppTest harness. The app preloads its fictional demo
workbook on first run, so every page renders demo-backed content — which is
exactly what a first-time visitor sees. File-uploader widgets cannot be driven
here, so the upload-replaces-demo path is exercised through session state.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / "app.py")

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


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    test = AppTest.from_file(APP, default_timeout=30)
    test.run()
    test.sidebar.radio[0].set_value(page).run()
    assert not test.exception, f"{page} raised: {[e.value for e in test.exception]}"


def test_typed_input_pages_produce_results():
    test = AppTest.from_file(APP, default_timeout=30)
    test.run()
    test.sidebar.radio[0].set_value("Customer lifetime value").run()
    test.button[0].click().run()
    assert not test.exception
    assert test.metric[0].value != "—"


def test_fresh_run_preloads_the_fictional_demo():
    test = AppTest.from_file(APP, default_timeout=30)
    test.run()
    assert not test.exception
    demo = test.session_state["worth:demo"]
    assert demo.source_name == "Fictional demo workbook"
    assert {"transactions", "rfm_customers", "equity", "events"} <= set(demo.tables)
    assert any("Data check: Fictional demo workbook" in s.value for s in test.subheader)
    assert any("fictional demo workbook" in i.value for i in test.sidebar.info)
    assert not any("Upload a file to see" in i.value for i in test.info)


@pytest.mark.parametrize(
    ("page", "sheet"),
    [
        ("Customer selection", "transactions"),
        ("Customer equity", "equity"),
        ("Contractual retention", "contractual_survival"),
        ("BG/NBD continuous time", "bgnbd_summary"),
        ("BG/BB discrete time", "bgbb_histories"),
    ],
)
def test_data_pages_use_the_demo_sheet(page, sheet):
    test = AppTest.from_file(APP, default_timeout=30)
    test.run()
    test.sidebar.radio[0].set_value(page).run()
    assert not test.exception
    assert not any("Upload an Excel, CSV, or JSON file" in i.value for i in test.info)
    assert test.selectbox(key=f"worth:table_{page_stem(page)}").value == sheet


def page_stem(page):
    return {
        "Customer selection": "selection",
        "Customer equity": "equity",
        "Contractual retention": "contractual",
        "BG/NBD continuous time": "bgnbd",
        "BG/BB discrete time": "bgbb",
    }[page]


def test_demo_rfm_runs_end_to_end():
    test = AppTest.from_file(APP, default_timeout=30)
    test.run()
    test.sidebar.radio[0].set_value("Customer selection").run()
    test.button(key="worth:run_rfm").click().run()
    assert not test.exception
    assert any("RFM analysis complete" in s.value for s in test.success)


def test_upload_replaces_the_demo(monkeypatch):
    """A parsed upload takes the demo's place on every page."""
    import pandas as pd
    import streamlit as st

    from cva.io import LoadedData
    from cva.ui import app as ui

    upload = LoadedData(tables={"my_sheet": pd.DataFrame({"customer_id": [1, 2], "amount": [5.0, 7.0]})}, source_name="mine.csv")

    class FakeUpload:
        name = "mine.csv"

        def getvalue(self):
            return b"customer_id,amount\n1,5\n2,7\n"

    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: FakeUpload())
    monkeypatch.setattr(ui, "load_for_session", lambda raw, filename: upload)
    st.session_state.clear()
    ui._ensure_state()
    page, loaded = ui._sidebar()
    assert loaded is upload
    assert st.session_state[ui.k("demo")].source_name == "Fictional demo workbook"
