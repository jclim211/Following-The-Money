"""Landing page: what this run is and where to go. No numbers here (the BQ2 Summary has the headline figures)."""
import streamlit as st

from common import theme
from common.runs import current_run

run = current_run()
theme.page_header("Following the Money",
                  "Two business questions on the IBM AML transactions, answered from the pipeline's Athena "
                  "outputs. Pick a dataset run in the header; every page then shows that run.",
                  eyebrow=f"{run.name} · {run.period}" if run.period else run.name)

c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown('<div class="snow-eyebrow">BQ2</div>', unsafe_allow_html=True)
    st.markdown("#### Laundering networks")
    st.write("How do laundering networks move funds differently from normal transactions, and which banks are "
             "disproportionate entry and exit points?")
    st.page_link("views/bq2_summary.py", label="Open the BQ2 summary", icon=":material/arrow_forward:")
with c2.container(border=True):
    st.markdown('<div class="snow-eyebrow">BQ1</div>', unsafe_allow_html=True)
    st.markdown("#### Account risk prioritisation")
    st.write("Which accounts should investigators review first under limited daily capacity, and which "
             "behaviours matter most?")
    st.page_link("views/bq1_account_risk.py", label="Open BQ1 account risk", icon=":material/arrow_forward:")

st.caption("Data flow: S3 (.sql) → Athena → S3 (result .csv) → this app. Results are cached for an hour.")
