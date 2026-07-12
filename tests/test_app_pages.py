"""Every page of the Streamlit app must render without raising.

Uses Streamlit's built-in AppTest harness. File uploads cannot be simulated
here, so pages render their "upload a file first" guidance — which is exactly
what a first-time visitor sees.
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
