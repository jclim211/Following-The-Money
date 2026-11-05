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
    data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "n_laundering", "Laundering transactions", ","
else:
    data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "laundering_rate", "Laundering rate", ".1%"

# ---- ranked routes first (top 5 by default)
with st.container(border=True):
    h1, h2 = st.columns([3, 2], vertical_alignment="center")
    h1.markdown(f"#### Top routes by {title.lower()}")
    with h2:
        n = ui.top_n("routes")
    top = ui.head(data.sort_values(field, ascending=False), n).copy()
    top["route"] = top["from_country"] + " → " + top["to_country"]
    st.altair_chart(
        alt.Chart(top).mark_bar(color=theme.LAUNDERING).encode(
            x=alt.X(f"{field}:Q", title=title, axis=alt.Axis(format=fmt)),
            y=alt.Y("route:N", sort="-x", title=None),
            tooltip=["route", alt.Tooltip("n_laundering:Q", format=","), alt.Tooltip("n_normal:Q", format=","),
                     alt.Tooltip("laundering_rate:Q", format=".2%"),
                     alt.Tooltip("x_average:Q", format=".1f", title="x average rate")]
        ).properties(height=max(160, 30 * len(top))),
        width="stretch")
    top[["laundering_rate", "share_of_laundering"]] *= 100
    with st.expander("Table"):
        st.dataframe(
            top[["from_country", "to_country", "n_laundering", "n_normal", "laundering_rate", "x_average",
                 "share_of_laundering"]],
            width="stretch", hide_index=True,
            column_config={
                "from_country": "From", "to_country": "To", "n_laundering": "Laundering", "n_normal": "Normal",
                "laundering_rate": st.column_config.NumberColumn("Laundering rate", format="%.2f%%"),
                "x_average": st.column_config.NumberColumn("x average", format="%.1f"),
                "share_of_laundering": st.column_config.NumberColumn("Share of all laundering", format="%.2f%%"),
            })
    if is_count:
        st.caption("Count: number of laundering transactions on the route. Big routes come first because they "
                   "carry the most of everything.")
    else:
        st.caption(f"Rate: laundering transactions / all transactions on the route. Average across all routes: "
                   f"{avg_rate:.3%}.")

# ---- full heatmap
with st.expander("All routes: heatmap", expanded=False):
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
        ).properties(height=650),
        width="stretch")
    st.caption(f"Average laundering rate across all routes: {avg_rate:.3%}. Crypto is its own row and column; "
               "the diagonal is domestic. Blank cells have no laundering (count view) or too few "
               "laundering transactions (rate view).")
st.caption("Small foreign-to-foreign routes can have high rates. The dataset is synthetic, so this shows "
           "where the generator places laundering, not real-world country risk.")
bq2.show_popups()
