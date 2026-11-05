"""IS459 Group 7 | Following the Money: dashboard entry point (streamlit run Home.py).

Draws the dataset-run bar and the two-level menu, runs the selected page, then shows "up next".
Pages live in views/ and are grouped per business question; every page reads the run picked at the top.
"""
import streamlit as st

st.set_page_config(page_title="Following the Money", page_icon=":material/currency_exchange:", layout="wide")

from common import theme, ui  # noqa: E402  (after set_page_config)
from common.runs import registry  # noqa: E402

theme.apply()

P = st.Page
overview = P("views/overview.py", title="Overview", icon=":material/space_dashboard:", default=True)
bq1 = [
    P("views/bq1_account_risk.py", title="Account risk", icon=":material/manage_search:", url_path="bq1-account-risk"),
    P("views/bq1_pilot_queue.py", title="Pilot queue", icon=":material/fact_check:", url_path="bq1-pilot-queue"),
]
bq2 = [
    P("views/bq2_summary.py", title="Summary", icon=":material/insights:", url_path="bq2-summary"),
    P("views/bq2_banks.py", title="Entry and exit banks", icon=":material/account_balance:", url_path="bq2-banks"),
    P("views/bq2_schemes.py", title="Schemes", icon=":material/account_tree:", url_path="bq2-schemes"),
    P("views/bq2_routes.py", title="Country routes", icon=":material/travel_explore:", url_path="bq2-routes"),
    P("views/bq2_flows.py", title="Laundering vs normal", icon=":material/compare_arrows:", url_path="bq2-flows"),
]
manage = P("views/manage_runs.py", title="Manage runs", icon=":material/tune:", url_path="runs")

sections = [
    ui.Section("Overview", "Overview", ":material/space_dashboard:", [overview]),
    ui.Section("BQ1 · Account risk", "BQ1", ":material/person_search:", bq1),
    ui.Section("BQ2 · Laundering networks", "BQ2", ":material/hub:", bq2),
    ui.Section("Runs", "Runs", ":material/database:", [manage]),
]
if not registry().list_runs():
    sections = [sections[-1]]

page = st.navigation([p for s in sections for p in s.pages], position="hidden")
ui.top_bar(manage)
ui.menu(sections, page)
page.run()
ui.up_next(sections, page)
