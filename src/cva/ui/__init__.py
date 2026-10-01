"""Worth Signal user interface: the Signal Hub entry point.

The only package under ``cva`` that imports Streamlit or Plotly. ``render()`` draws the whole app on the current
page and never calls ``st.set_page_config``; the standalone ``app.py`` or Signal Hub owns the page config.
"""

from cva import __version__
from cva.ui import signal_theme
from cva.ui.app import render

APP_INFO = {"product": "Worth Signal", "version": __version__, "repo": "customer-value-analytics", "slug": "worth"}

__all__ = ["APP_INFO", "render", "signal_theme"]
