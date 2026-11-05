"""IS459 Group 7 | Following the Money: dashboard home page and sidebar.

Every finished pipeline run gets its own sidebar section, with one BQ1 and one BQ2 page.
"""
import streamlit as st

from common.runs import RUN_KEY, list_runs

BQ1_PAGE = "pages/1_BQ1_Account_Profiles.py"
BQ2_PAGE = "pages/2_BQ2_Cross_bank_movement.py"

st.set_page_config(page_title="Following the Money", page_icon="🏦", layout="wide")

try:
    runs, runs_error = list_runs(), None
except Exception as err:  # keep the original pages usable if S3 cannot be read
    runs, runs_error = [], str(err)[:200]

current_bq1 = st.Page(BQ1_PAGE, title="BQ1 Account Profiles", url_path="bq1", icon=":material/bar_chart:")
current_bq2 = st.Page(BQ2_PAGE, title="BQ2 Cross-bank Movement", url_path="bq2", icon=":material/hub:")
run_pages = {}
for run in runs:
    run_pages[run["run"]] = [
        st.Page(BQ1_PAGE, title="BQ1 Account Profiles", url_path=f"{run['run']}-bq1", icon=":material/bar_chart:"),
        st.Page(BQ2_PAGE, title="BQ2 Cross-bank Movement", url_path=f"{run['run']}-bq2", icon=":material/hub:"),
    ]


def home():
    st.title("🏦 Following the Money: IS459 Group 7")
    st.caption("IBM AML transactions. Each pipeline run is kept as its own set of pages.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("BQ1: Account risk prioritisation")
        st.write("Which accounts should investigators review first under limited daily capacity, "
                 "and which behaviours matter most?")
        st.page_link(current_bq1, label="Open BQ1 dashboard")
    with c2:
        st.subheader("BQ2: Laundering networks")
        st.write("How do laundering networks move funds differently from normal transactions, "
                 "and which banks are disproportionate entry and exit points?")
        st.page_link(current_bq2, label="Open BQ2 dashboard")

    st.subheader("Pipeline runs")
    if runs_error:
        st.warning(f"Could not read the run list from S3: {runs_error}")
    elif not runs:
        st.info("No pipeline runs have finished yet.")
    else:
        st.dataframe(
            [{"Run": r["run"], "Dataset": r["dataset"], "Started (UTC)": r["started"][:16].replace("T", " "),
              "Finished (UTC)": r["finished"][:16].replace("T", " ")} for r in runs],
            hide_index=True, width="stretch")


sections = {"Overview": [st.Page(home, title="Home", url_path="home", icon=":material/home:", default=True)],
            "HI-Medium (current)": [current_bq1, current_bq2]}
sections.update(run_pages)
page = st.navigation(sections)

run_by_url = {p.url_path: r for r in runs for p in run_pages[r["run"]]}
selected_run = run_by_url.get(page.url_path)
if st.session_state.get(RUN_KEY) != selected_run:  # selections from one run mean nothing in another
    st.session_state.clear()
st.session_state[RUN_KEY] = selected_run
page.run()
