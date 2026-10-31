"""IS459 Group 7 | Following the Money: dashboard home page."""
import streamlit as st

st.set_page_config(page_title="Following the Money", page_icon="🏦", layout="wide")
st.title("🏦 Following the Money: IS459 Group 7")
st.caption("IBM AML transactions (HI-Medium). Data is read live from Athena.")

c1, c2 = st.columns(2)
with c1:
    st.subheader("BQ1: Account risk prioritisation")
    st.write("Which accounts should investigators review first under limited daily capacity, "
             "and which behaviours matter most?")
    st.page_link("pages/1_BQ1_Account_Risk.py", label="Open BQ1 dashboard", icon=":material/bar_chart:")
with c2:
    st.subheader("BQ2: Laundering networks")
    st.write("How do laundering networks move funds differently from normal transactions, "
             "and which banks are disproportionate entry and exit points?")
    st.page_link("pages/2_BQ2_Cross_bank_movement.py", label="Open BQ2 dashboard", icon=":material/hub:")
