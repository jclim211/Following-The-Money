"""Landing page: what this run is, the two business questions, and where each page answers them. No numbers."""
import streamlit as st

from common import theme
from common.runs import current_run

run = current_run()
st.markdown(
    f'<div class="rv-hero"><div class="k">{theme.esc(run.name)} · dataset run</div>'
    '<div class="t">Following the money between banks</div>'
    '<div class="s">Two business questions answered from the pipeline\'s Athena outputs: which accounts an '
    'investigation team should review first, and how laundering networks move money between banks.</div>'
    '<div class="tags">'
    + "".join(f'<span class="tag">{theme.icon(i, "#FFFFFF", 16)}&nbsp; {theme.esc(t)}</span>'
              for i, t in [("calendar_month", run.period or run.created_at), ("database", "Athena · S3"),
                           ("bolt", "Cached for 1 hour"), ("verified", run.status)])
    + "</div></div>", unsafe_allow_html=True)
st.write("")

PAGES_BQ1 = [
    ("views/bq1_account_risk.py", "Account risk", ":material/manage_search:",
     "Daily investigator queue, capacity vs detection, which behaviours matter, account drill-down"),
    ("views/bq1_pilot_queue.py", "Pilot queue", ":material/fact_check:",
     "The 100-reviews-per-day pilot: queue with explanations, capacity trade-off, methodology"),
]
PAGES_BQ2 = [
    ("views/bq2_summary.py", "Summary", ":material/insights:", "Headline numbers, findings and the top 5 banks and schemes"),
    ("views/bq2_banks.py", "Entry and exit banks", ":material/account_balance:",
     "Where schemes put money in and take it out, against each bank's size"),
    ("views/bq2_schemes.py", "Schemes", ":material/account_tree:", "Every reconstructed scheme, drawn entry → exit"),
    ("views/bq2_routes.py", "Country routes", ":material/travel_explore:", "Where laundering crosses borders"),
    ("views/bq2_flows.py", "Laundering vs normal", ":material/compare_arrows:",
     "Payment formats, borders, currencies and holding time"),
]


def question_card(key, tag, title, question, ic, color, pages):
    with theme.card(key):
        st.markdown(f'<div class="rv-qcard-head">{theme.chip(ic, color, 52)}<div><div class="k">{tag}</div>'
                    f'<div class="t">{title}</div></div></div><div class="rv-qcard-q">{question}</div>',
                    unsafe_allow_html=True)
        for path, label, icon, desc in pages:
            st.page_link(path, label=label, icon=icon)
            st.caption(desc)


c1, c2 = st.columns(2, gap="medium")
with c1:
    question_card("card_q1", "BQ1", "Account risk prioritisation",
                  "Which accounts should investigators review first under limited daily capacity, and which "
                  "behaviours matter most?", "person_search", theme.PURPLE, PAGES_BQ1)
with c2:
    question_card("card_q2", "BQ2", "Laundering networks",
                  "How do laundering networks move funds differently from normal transactions, and which banks "
                  "are disproportionate entry and exit points?", "hub", theme.PINK, PAGES_BQ2)

st.write("")
theme.section("How the data gets here", "Every number on these pages comes from this pipeline",
              "conversion_path", theme.TEAL)
st.markdown('<div class="rv-steps">' + "".join(
    f'<div class="rv-step">{theme.chip(i, c, 40)}<div><div class="n">{n}</div><div class="d">{d}</div></div></div>'
    for i, c, n, d in [
        ("cloud_upload", theme.BLUE, "S3 raw data", "IBM AML transactions, accounts and patterns"),
        ("memory", theme.PURPLE, "Spark on EMR", "Cleaning, account profiles, risk scores, schemes"),
        ("table_view", theme.ORANGE, "Athena", "Stored .sql queries write result .csv files to S3"),
        ("monitoring", theme.GREEN, "This dashboard", "Reads the result files, cached for an hour"),
    ]) + "</div>", unsafe_allow_html=True)
