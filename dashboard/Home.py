"""IS459 Group 7 | Following the Money: dashboard entry point (streamlit run Home.py).

Draws the header bar with the dataset-run menu, then the page picked in the top navigation.
Pages are grouped per business question; every page reads the run picked in the header.
"""
import streamlit as st

st.set_page_config(page_title="Following the Money", page_icon=":material/account_balance:", layout="wide")

from common import theme, ui  # noqa: E402  (after set_page_config)
from common.runs import registry  # noqa: E402

theme.apply()

overview = st.Page("views/overview.py", title="Overview", icon=":material/home:", default=True)
bq2 = [
    st.Page("views/bq2_summary.py", title="Summary", icon=":material/dashboard:", url_path="bq2-summary"),
    st.Page("views/bq2_banks.py", title="Entry and exit banks", icon=":material/account_balance:",
            url_path="bq2-banks"),
    st.Page("views/bq2_schemes.py", title="Schemes", icon=":material/hub:", url_path="bq2-schemes"),
    st.Page("views/bq2_routes.py", title="Country routes", icon=":material/public:", url_path="bq2-routes"),
    st.Page("views/bq2_flows.py", title="Laundering vs normal", icon=":material/compare_arrows:",
            url_path="bq2-flows"),
]
bq1 = [
    st.Page("views/bq1_account_risk.py", title="Account risk", icon=":material/bar_chart:",
            url_path="bq1-account-risk"),
    st.Page("views/bq1_pilot_queue.py", title="Pilot queue", icon=":material/checklist:",
            url_path="bq1-pilot-queue"),
]
manage = st.Page("views/manage_runs.py", title="Manage runs", icon=":material/settings:", url_path="runs")

has_runs = bool(registry().list_runs())
nav = st.navigation({"": [overview], "BQ2 · Laundering networks": bq2, "BQ1 · Account risk": bq1,
                     "Runs": [manage]} if has_runs else {"Runs": [manage]},
                    position="top")
run = ui.header_bar()
nav.run()
