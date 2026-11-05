"""BQ2: how laundering transactions differ from normal ones (payment format, border, conversion, holding time)."""
import altair as alt
import streamlit as st

from common import bq2, theme
from common.bq2 import DIMENSION_LABELS, GROUP_COLORS

theme.page_header("Laundering vs normal transactions",
                  "Which payment formats, borders and currency conversions laundering uses, and how fast the "
                  "money is sent on.", eyebrow="BQ2 · Flows")
flow = bq2.flow()
theme.legend([(theme.LAUNDERING, "laundering"), (theme.NORMAL, "normal")])

with st.container(border=True):
    st.markdown("#### Share of transactions, laundering vs normal")
    cols = st.columns(3)
    for col, dim in zip(cols, ["payment_format", "border", "conversion"]):
        d = flow[flow["dimension"] == dim]
        with col:
            st.markdown(f"**{DIMENSION_LABELS[dim]}**")
            st.altair_chart(
                alt.Chart(d).mark_bar().encode(
                    y=alt.Y("value:N", title=None, sort="-x"),
                    yOffset="grp:N",
                    x=alt.X("share:Q", title="Share of group", axis=alt.Axis(format="%")),
                    color=alt.Color("grp:N", scale=GROUP_COLORS, title=None, legend=None),
                    tooltip=["grp", "value", alt.Tooltip("n_tx:Q", format=","),
                             alt.Tooltip("share:Q", format=".1%"), alt.Tooltip("usd_median:Q", format="$,.0f")]),
                width="stretch")

    wide = flow.pivot_table(index=["dimension", "value"], columns="grp",
                            values=["share", "usd_median"], aggfunc="first")
    wide.columns = [f"{v}_{g}" for v, g in wide.columns]
    wide = wide.reset_index()
    for c in ["share_laundering", "share_normal"]:
        if c not in wide:
            wide[c] = 0.0
        wide[c] = wide[c].fillna(0.0)
    wide["times_more_common"] = wide["share_laundering"] / wide["share_normal"].where(wide["share_normal"] > 0)
    wide[["share_laundering", "share_normal"]] *= 100
    wide["dimension"] = wide["dimension"].map(DIMENSION_LABELS)
    with st.expander("Table: shares, how many times more common in laundering, median USD"):
        st.dataframe(
            wide[["dimension", "value", "share_laundering", "share_normal", "times_more_common",
                  "usd_median_laundering", "usd_median_normal"]],
            width="stretch", hide_index=True,
            column_config={
                "share_laundering": st.column_config.NumberColumn("Laundering share", format="%.1f%%"),
                "share_normal": st.column_config.NumberColumn("Normal share", format="%.1f%%"),
                "times_more_common": st.column_config.NumberColumn("x more common in laundering", format="%.1f"),
                "usd_median_laundering": st.column_config.NumberColumn("Median USD, laundering", format="$%.0f"),
                "usd_median_normal": st.column_config.NumberColumn("Median USD, normal", format="$%.0f"),
            })

with st.container(border=True):
    st.markdown("#### Holding time: how long until received money is sent on")
    hold = bq2.run_query("holding_time")
    left, right = st.columns([2, 1])
    with left:
        st.altair_chart(
            alt.Chart(hold).mark_bar().encode(
                x=alt.X("bucket:N", title="Time to the account's next outgoing transfer",
                        sort=alt.EncodingSortField("bucket_order")),
                xOffset="grp:N",
                y=alt.Y("share:Q", title="Share of incoming transfers", axis=alt.Axis(format="%")),
                color=alt.Color("grp:N", scale=GROUP_COLORS, title=None, legend=None),
                tooltip=["grp", "bucket", alt.Tooltip("n:Q", format=","), alt.Tooltip("share:Q", format=".1%")]),
            width="stretch")
    with right:
        for g in ["laundering", "normal"]:
            h = hold[hold["grp"] == g]
            moved = 1 - h.loc[h["bucket"] == "never", "share"].sum()
            st.metric(f"{g.capitalize()}: money sent on", f"{moved:.1%}",
                      help="Share of incoming transfers followed by an outgoing transfer from the same account.")
            st.metric(f"{g.capitalize()}: median hold (when sent on)",
                      f"{h['median_hold_minutes'].iloc[0] / 60:.1f} h")
    st.caption("Same-minute outgoing transfers count as sending the money on. The next outgoing transfer can be "
               "any transfer of that account, not necessarily laundering. 'never' is partly because the data "
               "ends on 2022-09-16.")
bq2.show_popups()
