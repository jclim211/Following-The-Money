"""BQ2: country routes (heatmap + ranked routes, top 5 first)."""
import altair as alt
import streamlit as st

from common import bq2, theme, ui

theme.page_header("Country routes", "Where laundering happens most, and which routes are most suspicious per "
                  "transfer.", eyebrow="BQ2 · Routes")

pairs = bq2.run_query("country_pairs").copy()
pairs["n_total"] = pairs["n_laundering"] + pairs["n_normal"]
avg_rate = pairs["n_laundering"].sum() / pairs["n_total"].sum()
pairs["x_average"] = pairs["laundering_rate"] / avg_rate

# ---- takeaway
best = pairs.sort_values("n_laundering", ascending=False).iloc[0]
theme.takeaway(f"{best['from_country']} → {best['to_country']} carries {best['share_of_laundering']:.1%} of all "
               "laundering",
               f"{int(best['n_laundering']):,} laundering transactions; its rate is "
               f"{best['laundering_rate'] / avg_rate:.1f}x the average route. The dataset is synthetic, so this is "
               "where the generator places laundering, not real-world country risk.", "public", theme.PURPLE)

left, right = st.columns([1, 1])
view = left.radio("Rank routes by", ["Laundering transactions (count)", "Laundering rate"], horizontal=True,
                  captions=["Where does most laundering happen?",
                            "How suspicious is one transfer on this route?"])
is_count = view.startswith("Laundering transactions")
# Separate keys so each view keeps its own minimum: 1 for count, 30 for rate.
min_n = right.slider("Minimum laundering transactions per route", 1, 200, 1 if is_count else 30,
                     key="min_count" if is_count else "min_rate",
                     help="Hides routes with fewer laundering transactions. In the rate view this stops tiny "
                          "routes from getting extreme rates by chance (2 of 3 transfers = 67%).")
if is_count:
    data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "n_laundering", "Laundering transactions", "~s"
else:
    data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "laundering_rate", "Laundering rate", ".1%"

# ---- ranked routes (top 5 by default)
with theme.card("card_routes"):
    h1, h2 = st.columns([3, 2], vertical_alignment="center")
    with h1:
        theme.section(f"Top routes by {title.lower()}",
                      "Where most laundering happens" if is_count else
                      f"Laundering / all transactions on the route; average {avg_rate:.3%}",
                      "leaderboard", theme.RED)
    with h2:
        n = ui.top_n("routes")
    top = ui.head(data.sort_values(field, ascending=False), n).copy()
    top["route"] = top["from_country"] + " → " + top["to_country"]
    left, right = st.columns([1, 1.25], gap="medium")
    with left:
        st.altair_chart(
            alt.Chart(top).mark_bar(color=theme.LAUNDERING, cornerRadiusEnd=5).encode(
                x=alt.X(f"{field}:Q", title=title, axis=alt.Axis(format=fmt)),
                y=alt.Y("route:N", sort="-x", title=None),
                tooltip=["route", alt.Tooltip("n_laundering:Q", format=","), alt.Tooltip("n_normal:Q", format=","),
                         alt.Tooltip("laundering_rate:Q", format=".2%"),
                         alt.Tooltip("x_average:Q", format=".1f", title="x average rate")]
            ).properties(height=min(theme.CHART_H + 40, 60 + 30 * len(top))),   # height includes the axes
            width="stretch")
    top[["laundering_rate", "share_of_laundering"]] *= 100
    with right:
        st.dataframe(
            top[["from_country", "to_country", "n_laundering", "n_normal", "laundering_rate", "x_average",
                 "share_of_laundering"]],
            width="stretch", hide_index=True, height=min(theme.CHART_H + 40, 38 + 35 * max(len(top), 1)),
            column_config={
                "from_country": st.column_config.TextColumn("From", width="small"),
                "to_country": st.column_config.TextColumn("To", width="small"),
                "n_laundering": st.column_config.ProgressColumn(
                    "Laundering", format="%d", min_value=0, max_value=int(max(pairs["n_laundering"].max(), 1))),
                "n_normal": st.column_config.NumberColumn("Normal", format="localized", width="small"),
                "laundering_rate": st.column_config.NumberColumn("Rate", format="%.2f%%", width="small",
                                                                 help="Laundering / all transactions on the route"),
                "x_average": st.column_config.NumberColumn("x average", format="%.1fx", width="small"),
                "share_of_laundering": st.column_config.NumberColumn("Share", format="%.1f%%", width="small",
                                                                     help="Share of all laundering transactions"),
            })

# ---- full heatmap
with st.expander("All routes: heatmap (hover for numbers, expand to full screen)", icon=":material/grid_on:"):
    if is_count:
        color = alt.Color(f"{field}:Q", title=title, scale=alt.Scale(type="log", range=theme.SEQUENTIAL_RED))
    else:
        color = alt.Color(f"{field}:Q", title=title, scale=alt.Scale(range=theme.SEQUENTIAL_RED),
                          legend=alt.Legend(format="%"))
    volume = (pairs.groupby("from_country")["n_laundering"].sum()
              .add(pairs.groupby("to_country")["n_laundering"].sum(), fill_value=0)
              .sort_values(ascending=False))
    order = volume.index.tolist()
    st.altair_chart(
        alt.Chart(data).mark_rect(cornerRadius=2).encode(
            x=alt.X("to_country:N", sort=order, title="To country"),
            y=alt.Y("from_country:N", sort=order, title="From country"),
            color=color,
            tooltip=["from_country", "to_country", alt.Tooltip("n_laundering:Q", format=","),
                     alt.Tooltip("n_normal:Q", format=","), alt.Tooltip("laundering_rate:Q", format=".2%"),
                     alt.Tooltip("x_average:Q", format=".1f", title="x average rate")]
        ).properties(height=440),
        width="stretch")
    st.caption(f"Average laundering rate across all routes: {avg_rate:.3%}. Crypto is its own row and column; "
               "the diagonal is domestic. Blank cells have no laundering (count view) or too few "
               "laundering transactions (rate view).")
st.caption("Small foreign-to-foreign routes can have high rates. The dataset is synthetic, so this shows "
           "where the generator places laundering, not real-world country risk.")
bq2.show_popups()
