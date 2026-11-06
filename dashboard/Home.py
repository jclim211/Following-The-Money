"""IS459 Group 7 | Following the Money: the dashboard app.

The main page is the Atlassian Design System layout (common/ui.py, front end in ui/frontend/):
home, then a BQ1 and a BQ2 dashboard for the original HI-Medium tables and for every finished
pipeline run, all inside one page.

The previous Streamlit pages stay available at /classic-bq1 and /classic-bq2 (original
HI-Medium tables). The whole previous version, with its run sidebar, is the classic-ui branch.
"""
import streamlit as st

from common.runs import RUN_KEY

BQ1_PAGE = "pages/1_BQ1_Account_Profiles.py"
BQ2_PAGE = "pages/2_BQ2_Cross_bank_movement.py"

st.set_page_config(page_title="Following the Money", page_icon="🏦", layout="wide")

from common import ui  # noqa: E402  (after set_page_config)

main = st.Page(ui.page, title="Following the Money", url_path="home", default=True)
classic = [st.Page(BQ1_PAGE, title="BQ1 Account Profiles (classic)", url_path="classic-bq1"),
           st.Page(BQ2_PAGE, title="BQ2 Cross-bank Movement (classic)", url_path="classic-bq2")]
page = st.navigation([main, *classic], position="hidden")
if page.url_path != main.url_path:
    st.session_state[RUN_KEY] = None  # the classic pages show the original HI-Medium tables
page.run()
