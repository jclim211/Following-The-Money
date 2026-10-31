"""
BQ2 | How do laundering networks move funds, and which banks are entry and exit points?

STARTER PAGE for the BQ2 team. It reads what exists today:
  aml_clean.schemes  (one row per scheme transfer, from Patterns.txt)
  aml_clean.banks    (bank names and countries)
When BQ2 curated tables exist (e.g. aml_curated.bq2_*), add queries below the same way.
"""
import altair as alt
import streamlit as st

from common.athena import run_query

DB = "aml_clean"

st.set_page_config(page_title="BQ2 Laundering Networks", layout="wide")
st.title("BQ2: How do laundering networks move funds?")
st.caption("Starter page reading aml_clean.schemes. BQ2 team: extend this page with your curated outputs.")

# ---------------------------------------------------------------- 1. scheme types
types = run_query("""
    SELECT scheme_type,
           COUNT(DISTINCT scheme_id) AS schemes,
           COUNT(*) AS transfers,
           SUM(amount_usd) AS total_usd,
           AVG(CASE WHEN cross_border THEN 1.0 ELSE 0.0 END) AS cross_border_share,
           AVG(CASE WHEN crypto_involved THEN 1.0 ELSE 0.0 END) AS crypto_share
    FROM schemes
    GROUP BY scheme_type
    ORDER BY schemes DESC""", database=DB)

c1, c2, c3 = st.columns(3)
c1.metric("Schemes", f"{int(types['schemes'].sum()):,}")
c2.metric("Scheme transfers", f"{int(types['transfers'].sum()):,}")
c3.metric("Total moved (USD)", f"${types['total_usd'].sum():,.0f}")

st.subheader("Schemes by type")
st.altair_chart(
    alt.Chart(types).mark_bar().encode(
        x=alt.X("schemes:Q", title="Number of schemes"),
        y=alt.Y("scheme_type:N", sort="-x", title=None),
        tooltip=["scheme_type", "schemes", "transfers", alt.Tooltip("total_usd:Q", format=",.0f"),
                 alt.Tooltip("cross_border_share:Q", format=".0%"), alt.Tooltip("crypto_share:Q", format=".0%")]),
    width="stretch")
st.dataframe(types, width="stretch", hide_index=True,
             column_config={"total_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
                            "cross_border_share": st.column_config.NumberColumn("Cross-border", format="%.2f"),
                            "crypto_share": st.column_config.NumberColumn("Crypto", format="%.2f")})

# ---------------------------------------------------------------- 2. entry and exit banks
st.subheader("Entry and exit banks")
role = st.radio("Bank role", ["Entry (first transfer of a scheme)", "Exit (last transfer of a scheme)"], horizontal=True)
top_n = st.slider("Banks to show", 5, 30, 15)
bank_col, pick = ("from_bank", "first_step") if role.startswith("Entry") else ("to_bank", "last_step")
banks = run_query(f"""
    WITH s AS (
      SELECT scheme_id, step, from_bank, to_bank,
             MIN(step) OVER (PARTITION BY scheme_id) AS first_step,
             MAX(step) OVER (PARTITION BY scheme_id) AS last_step
      FROM schemes)
    SELECT s.{bank_col} AS bank_id, COALESCE(b.bank_name, s.{bank_col}) AS bank_name, b.country,
           COUNT(DISTINCT s.scheme_id) AS schemes, MAX(b.total_txns) AS bank_total_txns
    FROM s LEFT JOIN banks b ON b.bank_id = s.{bank_col}
    WHERE s.step = s.{pick}
    GROUP BY 1, 2, 3
    ORDER BY schemes DESC
    LIMIT {top_n}""", database=DB)
banks["schemes_per_1k_txns"] = 1000 * banks["schemes"] / banks["bank_total_txns"].clip(lower=1)
st.altair_chart(
    alt.Chart(banks).mark_bar().encode(
        x=alt.X("schemes:Q", title="Schemes"),
        y=alt.Y("bank_name:N", sort="-x", title=None),
        tooltip=["bank_id", "bank_name", "country", "schemes", "bank_total_txns",
                 alt.Tooltip("schemes_per_1k_txns:Q", format=".2f")]),
    width="stretch")
st.caption("schemes_per_1k_txns adjusts for bank size: a high value means the bank is disproportionately used.")

# ---------------------------------------------------------------- 3. scheme explorer
st.subheader("Scheme explorer")
stype = st.selectbox("Scheme type", types["scheme_type"].tolist())
ids = run_query(f"SELECT DISTINCT scheme_id FROM schemes WHERE scheme_type = '{stype}' ORDER BY 1 LIMIT 200",
                database=DB)["scheme_id"].tolist()
sid = st.selectbox("Scheme id", ids)
if sid is not None:
    steps = run_query(f"""
        SELECT step, ts, from_bank, from_account, to_bank, to_account, amount_usd,
               payment_format, cross_border, in_clean
        FROM schemes WHERE scheme_id = {int(sid)} ORDER BY step, ts""", database=DB)
    st.dataframe(steps, width="stretch", hide_index=True)
