"""The dashboard in the Atlassian Design System layout: one Streamlit page that hosts the
front end in ui/frontend/index.html as a custom component.

Python stays in charge of the data. The front end draws every page and sends back the page
the user opens ({"path", "n"}); this module then reads that page's data from Athena
(common/ui_data.py, cached for an hour) and passes it in. The page is kept in the URL as
?view=<path>, for example ?view=hi-small-1-bq2, so links and reloads open the same page.

While Athena runs, the component from the previous run stays on screen with its loading
popup, so no Streamlit spinner is shown.
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from common.runs import list_runs
from common.ui_data import bq1_payload, bq2_payload

FRONTEND = Path(__file__).resolve().parents[1] / "ui" / "frontend"
KEY = "ftm"
_frontend = components.declare_component("ftm", path=str(FRONTEND))

# The design is a full page of its own: hide Streamlit's chrome and let the frame fill the window.
CSS = """<style>
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
footer, #MainMenu { display: none !important; }
[data-testid="stMainBlockContainer"], .block-container { padding: 0 !important; max-width: none !important; }
.st-key-ftm_work { display: none !important; }
.st-key-ftm_box iframe { position: fixed; inset: 0; width: 100vw !important; height: 100vh !important;
  height: 100dvh !important; border: 0; z-index: 999990; }
[data-stale="true"], .stale-element { opacity: 1 !important; transition: none !important; }
</style>"""


def _resolve(path: str, runs: list):
    """'bq1', 'bq2', '<run>-bq1', '<run>-bq2' or 'home' -> (kind, run dict or None)."""
    if path in ("bq1", "bq2"):
        return path, None
    for r in runs:
        for kind in ("bq1", "bq2"):
            if path == f"{r['run']}-{kind}":
                return kind, r
    return "home", None


def page():
    st.markdown(CSS, unsafe_allow_html=True)
    box = st.container(key="ftm_box")    # the component; kept on screen while the next data loads
    work = st.container(key="ftm_work")  # hidden: anything Streamlit shows while loading goes here

    try:
        runs, runs_error = list_runs(), ""
    except Exception as err:  # the original HI-Medium dashboards still work without the run list
        runs, runs_error = [], str(err)[:200]

    nav, handled = st.session_state.get(KEY), st.session_state.get("ftm_n", 0)
    if isinstance(nav, dict) and nav.get("n", 0) != handled:  # the user opened a page in the front end
        handled = st.session_state["ftm_n"] = nav.get("n", 0)
        path = str(nav.get("path") or "home")
    else:
        path = st.query_params.get("view", "home")
    kind, run = _resolve(path, runs)
    if kind == "home":
        path = "home"
        if "view" in st.query_params:
            del st.query_params["view"]
    elif st.query_params.get("view") != path:
        st.query_params["view"] = path

    args = {"runs": runs, "runs_error": runs_error, "path": path, "n": handled}
    if kind != "home" and not st.session_state.get("ftm_mounted"):
        # First visit straight to a dashboard: draw the frame with its loading popup, then load.
        st.session_state["ftm_mounted"] = True
        with box:
            _frontend(**args, pending=True, data=None, key=KEY, default=None)
        st.rerun()

    data = None
    if kind != "home":
        with work:
            try:
                data = bq1_payload(run) if kind == "bq1" else bq2_payload(run)
            except Exception as err:  # shown in the design, with a Try again button
                data = {"kind": kind, "error": str(err)[:800]}
    with box:
        _frontend(**args, pending=False, data=data, key=KEY, default=None)
    st.session_state["ftm_mounted"] = True
