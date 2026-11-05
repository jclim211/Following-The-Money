"""BQ2: the reconstructed laundering schemes. Pick one to see its flow and bank path."""
from functools import partial

import streamlit as st

from common import bq2, theme, ui
from common.bq2 import SCHEME_TYPES

theme.page_header("Laundering schemes",
                  "The schemes reconstructed from Patterns.txt. Open one to follow the money from the entry "
                  "bank, through the intermediaries, to the exit bank.", eyebrow="BQ2 · Schemes")
profile = bq2.profile()

# ---------------------------------------------------------------- scheme list
c1, c2, c3 = st.columns([2, 2, 2], vertical_alignment="center")
stype = c1.selectbox("Scheme type", ["All types"] + sorted(profile["scheme_type"].unique()), key="scheme_type",
                     label_visibility="collapsed")
order = c2.segmented_control("Sort", ["Largest USD", "Most transfers", "Most banks"], default="Largest USD",
                             key="scheme_sort", label_visibility="collapsed") or "Largest USD"
with c3:
    n = ui.top_n("schemes")
sort_col = {"Largest USD": "total_usd", "Most transfers": "n_transfers", "Most banks": "n_banks"}[order]
prof_f = profile if stype == "All types" else profile[profile["scheme_type"] == stype]
if stype != "All types":
    st.info(bq2.describe_type(stype, profile))

lst = ui.head(prof_f.sort_values(sort_col, ascending=False), n).copy()
with st.container(border=True):
    st.markdown(f"#### {'Top ' + str(len(lst)) if n else 'All ' + str(len(lst))} schemes · {order.lower()}")
    ids = lst["scheme_id"].astype(int).tolist()
    key = f"scheme_tbl_{stype}_{order}_{n}"
    st.dataframe(
        lst[["scheme_id", "scheme_type", "n_transfers", "n_accounts", "n_banks", "n_countries", "duration_hours",
             "total_usd"]],
        key=key, on_select=partial(bq2.pick_from_table, key, ids, "scheme"), selection_mode="single-row",
        width="stretch", hide_index=True,
        column_config={
            "scheme_id": "Scheme", "scheme_type": "Type", "n_transfers": "Transfers", "n_accounts": "Accounts",
            "n_banks": "Banks", "n_countries": "Countries",
            "duration_hours": st.column_config.NumberColumn("Duration (h)", format="%.0f"),
            "total_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
        })
    st.caption("Click a row to open the scheme.")

pick_labels = {int(r.scheme_id): f"#{int(r.scheme_id)} {r.scheme_type}: {int(r.n_transfers)} transfers, "
                                 f"{int(r.n_banks)} banks, ${r.total_usd:,.0f}"
               for r in prof_f.sort_values("n_transfers", ascending=False).itertuples()}


def _open_from_box():
    if st.session_state.get("scheme_pick") is not None:
        bq2.open_scheme(st.session_state["scheme_pick"])


st.selectbox("Or open any scheme", list(pick_labels), format_func=pick_labels.get, index=None,
             placeholder="Type a scheme number or pick one (largest first)", key="scheme_pick",
             on_change=_open_from_box)

# ---------------------------------------------------------------- scheme types
with st.container(border=True):
    st.markdown("#### Scheme types: transfers, banks and countries per scheme")
    types = (profile.groupby("scheme_type")
             .agg(schemes=("scheme_id", "count"), avg_transfers=("n_transfers", "mean"),
                  avg_banks=("n_banks", "mean"), avg_countries=("n_countries", "mean"),
                  median_hours=("duration_hours", "median"), median_usd=("total_usd", "median"),
                  in_clean=("share_in_clean", "mean"))
             .reset_index().sort_values("avg_banks", ascending=False))
    types["in_clean"] *= 100
    types.insert(1, "shape", types["scheme_type"].map(SCHEME_TYPES))
    st.dataframe(
        types, width="stretch", hide_index=True,
        column_config={
            "scheme_type": "Type", "shape": st.column_config.TextColumn("Shape", width="large"), "schemes": "Schemes",
            "avg_transfers": st.column_config.NumberColumn("Avg transfers", format="%.1f"),
            "avg_banks": st.column_config.ProgressColumn("Avg banks", min_value=0,
                                                         max_value=float(types["avg_banks"].max()), format="%.1f"),
            "avg_countries": st.column_config.NumberColumn("Avg countries", format="%.1f"),
            "median_hours": st.column_config.NumberColumn("Median duration (h)", format="%.0f"),
            "median_usd": st.column_config.NumberColumn("Median total USD", format="$%.0f"),
            "in_clean": st.column_config.NumberColumn("Transfers in clean window", format="%.0f%%"),
        })
    st.caption("Scheme transfers after 2022-09-16 are outside the clean window but kept, so a scheme's "
               "exit is its real last transfer.")
    with st.expander("What the scheme types mean (all 8)"):
        st.markdown("\n\n".join(bq2.describe_type(t, profile) for t in SCHEME_TYPES))
        st.caption("Shapes as defined for the IBM AML dataset (Altman et al., 2023). 'Why it is used' is general "
                   "AML background; 'In our data' is computed live from scheme_profile.")
bq2.show_popups()
