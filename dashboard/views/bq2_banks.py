"""BQ2: which banks are disproportionate entry and exit points. Click a bank to open it."""
from functools import partial

import plotly.graph_objects as go
import streamlit as st

from common import bq2, theme, ui
from common.bq2 import ROLE_COLORS

theme.page_header("Entry and exit banks",
                  "Where schemes put money in and take it out, by count and against what each bank's size "
                  "predicts. Click a bank to see its schemes.", eyebrow="BQ2 · Banks")
bee = bq2.bee()

c1, c2, c3 = st.columns([1, 2, 2], vertical_alignment="center")
side = c1.segmented_control("Point", ["Entry", "Exit"], default="Entry", key="bank_side") or "Entry"
view = c2.segmented_control("Rank by", ["Most schemes", "Most over-represented"], default="Most schemes",
                            key="bank_view", help="Over-represented: ratio of actual to expected schemes, for "
                                                  "banks with 5+ schemes and an expected count of 1+.") \
    or "Most schemes"
with c3:
    n = ui.top_n("banks")

actual, expected, ratio, eligible = (("entries", "expected_entries", "entry_ratio", "entry_eligible")
                                     if side == "Entry" else
                                     ("exits", "expected_exits", "exit_ratio", "exit_eligible"))
if view == "Most schemes":
    d = ui.head(bee[bee[actual] > 0].sort_values([actual, ratio], ascending=False), n)
    field, x_title = actual, f"Schemes that {'enter' if side == 'Entry' else 'exit'} here"
else:
    d = ui.head(bee[bee[eligible] & (bee[expected] >= 1)].sort_values(ratio, ascending=False), n)
    field, x_title = ratio, "Actual / expected schemes"

eligible_set = bee[bee[eligible] & (bee[expected] >= 1)]
if len(eligible_set):
    o = eligible_set.sort_values(ratio, ascending=False).iloc[0]
    theme.takeaway(f"{o['bank_name']} ({o['country']}) gets {o[ratio]:.1f}x the {side.lower()} schemes its size "
                   f"predicts",
                   f"{int(o[actual])} schemes {'enter' if side == 'Entry' else 'leave'} there against "
                   f"{o[expected]:.1f} expected. Among banks with 5+ schemes, no bank is further above its share.",
                   "login" if side == "Entry" else "logout", theme.ENTRY if side == "Entry" else theme.EXIT)

theme.kpi_row([
    (f"Banks used as {side.lower()} point", f"{int((bee[actual] > 0).sum()):,}", "", "account_balance", theme.BLUE),
    ("With 5+ schemes and expected 1+", f"{int(len(eligible_set)):,}", "ranked in the ratio view", "filter_alt",
     theme.PURPLE),
    (f"All {side.lower()} points (scheme x bank)", f"{int(bee[actual].sum()):,}",
     "a scheme with several entry (exit) banks counts once for each", "functions", theme.ORANGE),
])

color = theme.ENTRY if side == "Entry" else theme.EXIT
with theme.card("card_bank_rank"):
    theme.section(f"{'Top' if n else 'All'} {len(d)} {side.lower()} banks · {view.lower()}",
                  "Click a bar or a row to open the bank", "leaderboard", color)
    left, right = st.columns([1, 1.45], gap="medium")
    with left:
        dd = d.iloc[::-1]
        fig = go.Figure(go.Bar(
            x=dd[field], y=dd["bank"].str.slice(0, 30), orientation="h",
            marker=dict(color=color, cornerradius=5),
            text=[f"{v:,.1f}x" if field == ratio else f"{v:,.0f}" for v in dd[field]], textposition="outside",
            cliponaxis=False, customdata=[[int(b)] for b in dd["bank_id"]],
            hovertemplate="<b>%{y}</b><br>" + x_title + ": %{x:,.1f}<br><i>Click to open</i><extra></extra>"))
        fig.update_layout(height=min(theme.CHART_H + 60, max(200, 30 * len(d) + 50)), xaxis_title=x_title,
                          margin=dict(l=8, r=40, t=8, b=8))
        theme.plotly_chart(fig, key="bank_rank", on_select=partial(bq2.pick_bank_from_chart, "bank_rank"),
                        selection_mode="points", width="stretch", config={"displayModeBar": False})
    with right:
        ids = d["bank_id"].astype(int).tolist()
        tkey = f"bank_tbl_{side}_{view}_{n}"
        st.dataframe(
            d[["bank", "country", actual, expected, ratio]], width="stretch", hide_index=True, key=tkey,
            on_select=partial(bq2.pick_from_table, tkey, ids, "bank"), selection_mode="single-row",
            height=min(theme.CHART_H + 60, 38 + 35 * max(len(d), 1)),
            column_config={
                "bank": st.column_config.TextColumn("Bank (id)", width="medium"),
                "country": st.column_config.TextColumn("Country", width="small"),
                actual: st.column_config.ProgressColumn("Actual", format="%d", min_value=0, width="small",
                                                        max_value=int(max(bee[actual].max(), 1))),
                expected: st.column_config.NumberColumn("Expected", format="%.1f", width="small",
                                                        help="Schemes expected from the bank's share of activity"),
                ratio: st.column_config.NumberColumn("Actual / expected", format="%.1fx", width="small"),
            })
    st.caption(f"Entry banks hold an account that only sends inside a scheme; exit banks hold an account that only "
               f"receives (cycles fall back to first sender / last receiver). Expected = all {side.lower()} points "
               f"({int(bee[actual].sum()):,}) x the bank's share of all sent (entry) or received (exit) clean "
               "transactions. A ratio of 5 means five times more schemes than its size predicts.")

with theme.card("card_bank_both"):
    theme.section("Banks used as both entry and exit", "5+ schemes on each side", "sync_alt", theme.ORANGE)
    both = bee[bee["entry_eligible"] & bee["exit_eligible"]].assign(total=lambda x: x["entries"] + x["exits"])
    both = ui.head(both.sort_values("total", ascending=False), n)
    bids = both["bank_id"].astype(int).tolist()
    bkey = f"both_tbl_{n}"
    st.dataframe(
        both[["bank", "country", "entries", "entry_ratio", "exits", "exit_ratio"]],
        width="stretch", hide_index=True, key=bkey,
        on_select=partial(bq2.pick_from_table, bkey, bids, "bank"), selection_mode="single-row",
        column_config={
            "bank": "Bank (id)", "country": "Country",
            "entries": st.column_config.ProgressColumn("Entries", format="%d", min_value=0,
                                                       max_value=int(max(bee["entries"].max(), 1))),
            "exits": st.column_config.ProgressColumn("Exits", format="%d", min_value=0,
                                                     max_value=int(max(bee["exits"].max(), 1))),
            "entry_ratio": st.column_config.NumberColumn("Entry ratio", format="%.1fx"),
            "exit_ratio": st.column_config.NumberColumn("Exit ratio", format="%.1fx"),
        })

# ---------------------------------------------------------------- network map (on request)
with st.expander("Bank network map: which banks the schemes run through", icon=":material/hub:"):
    prof, edges_all = bq2.profile(), bq2.edges()
    m1, m2 = st.columns(2)
    stype = m1.selectbox("Scheme type", ["All types"] + sorted(prof["scheme_type"].unique()), key="map_type")
    top_n = m2.slider("Banks on the map (most schemes first)", 5, 150, 20, step=5, key="map_n")
    e = edges_all if stype == "All types" else edges_all[edges_all["scheme_type"] == stype]
    stats = bq2.bank_stats(stype)
    theme.legend([(ROLE_COLORS["mostly entry"], "mostly entry"), (ROLE_COLORS["mostly exit"], "mostly exit"),
                  (ROLE_COLORS["entry and exit"], "entry and exit"), (ROLE_COLORS["pass-through"], "pass-through"),
                  (theme.INK_80, "other banks (not on the map)")])
    top = stats.sort_values(["n_schemes", "entries", "exits"], ascending=False).head(top_n).index.tolist()
    OTHER = -1
    lk = e.assign(from_bank=e["from_bank"].where(e["from_bank"].isin(top), OTHER),
                  to_bank=e["to_bank"].where(e["to_bank"].isin(top), OTHER))
    lk = lk[(lk["from_bank"] != lk["to_bank"])]
    be = (lk.groupby(["from_bank", "to_bank"])
          .agg(transfers=("scheme_id", "size"), schemes=("scheme_id", "nunique"), usd=("amount_usd", "sum"))
          .reset_index())
    n_other = int(stats.shape[0] - len(top))
    pos = bq2.spring_positions(tuple(int(b) for b in top) + (OTHER,),
                               tuple((int(a), int(b), 1) for a, b in be[["from_bank", "to_bank"]].itertuples(index=False)))

    def label_of(b):
        return "Other banks" if b == -1 else bq2.name_of(b)

    fig = go.Figure()
    xs, ys, mx, my, mtext = [], [], [], [], []
    for r in be.itertuples():
        (x0, y0), (x1, y1) = pos[r.from_bank], pos[r.to_bank]
        xs += [x0, x1, None]
        ys += [y0, y1, None]
        mx.append(x0 + 0.6 * (x1 - x0))
        my.append(y0 + 0.6 * (y1 - y0))
        mtext.append(f"{label_of(r.from_bank)} → {label_of(r.to_bank)}<br>"
                     f"{r.schemes} schemes, {r.transfers} transfers, ${r.usd:,.0f}")
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                             line=dict(width=0.7, color="rgba(28,28,28,0.12)")))
    fig.add_trace(go.Scatter(x=mx, y=my, mode="markers", hovertext=mtext, hoverinfo="text", showlegend=False,
                             marker=dict(size=4, color="rgba(28,28,28,0.25)"), customdata=[["edge"]] * len(mx)))
    fig.add_trace(go.Scatter(
        x=[pos[OTHER][0]], y=[pos[OTHER][1]], mode="markers+text", showlegend=False,
        text=["Other banks"], textposition="bottom center", customdata=[["other"]], hoverinfo="text",
        hovertext=[f"{n_other:,} banks not on the map. Raise the slider to show more of them."],
        marker=dict(size=22, symbol="square", color=theme.INK_80)))
    on_map = stats.loc[top]
    for role, color in ROLE_COLORS.items():
        dm = on_map[on_map["role"] == role]
        if dm.empty:
            continue
        fig.add_trace(go.Scatter(
            x=[pos[b][0] for b in dm.index], y=[pos[b][1] for b in dm.index], mode="markers", showlegend=False,
            customdata=[[int(b)] for b in dm.index],
            hovertext=[f"<b>{bq2.name_of(b)}</b><br>{bq2.country_of(b)}<br>{r.n_schemes} schemes, "
                       f"{r.entries} entries, {r.exits} exits<br><i>Click to open</i>" for b, r in dm.iterrows()],
            hoverinfo="text",
            marker=dict(size=[8 + 3 * v ** 0.5 for v in dm["n_schemes"]], color=color,
                        line=dict(width=1, color=theme.SURFACE))))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), dragmode="pan",
                      xaxis=dict(visible=False), yaxis=dict(visible=False), hovermode="closest")
    theme.plotly_chart(fig, key="bankmap", on_select=partial(bq2.pick_bank_from_chart, "bankmap"),
                    selection_mode="points", width="stretch", config={"scrollZoom": True})
    st.caption("Click a bank to open it. Node size = schemes through the bank. 'Mostly' means at least twice "
               "as many entries as exits (or the reverse). Scroll to zoom, drag to pan.")
bq2.show_popups()
