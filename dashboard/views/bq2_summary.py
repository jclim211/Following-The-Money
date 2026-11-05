"""BQ2 Summary: the headline numbers and findings, top 5 first. Click a bank or scheme for details."""
import streamlit as st

from common import bq2, theme, ui

theme.page_header("How laundering networks move money",
                  "Headline numbers for this run. Click any bank or scheme to open it.",
                  eyebrow="BQ2 · Summary")

flow, prof, hold = bq2.flow(), bq2.profile(), bq2.run_query("holding_time")
pairs, bee = bq2.run_query("country_pairs"), bq2.bee()
n_laundering, n_normal, n_schemes, in_clean = bq2.headline_counts()

top_entry = bee.sort_values(["entries", "entry_ratio"], ascending=False).iloc[0]
top_exit = bee.sort_values(["exits", "exit_ratio"], ascending=False).iloc[0]
top_route = pairs.sort_values("n_laundering", ascending=False).iloc[0]

theme.kpi_row([
    ("Laundering transactions", f"{n_laundering:,}", f"of {n_laundering + n_normal:,} transactions"),
    ("Laundering rate", f"{n_laundering / max(n_laundering + n_normal, 1):.2%}", "share of all transactions"),
    ("Schemes found", f"{n_schemes:,}", f"cover {100 * in_clean / max(n_laundering, 1):.0f}% of laundering"),
    ("Top entry bank", top_entry["bank_name"], f"{int(top_entry['entries']):,} schemes enter here"),
    ("Top exit bank", top_exit["bank_name"], f"{int(top_exit['exits']):,} schemes leave here"),
    ("Top route", f"{top_route['from_country']} → {top_route['to_country']}",
     f"{int(top_route['n_laundering']):,} laundering transactions"),
])

# ---------------------------------------------------------------- findings
pf = flow[flow["dimension"] == "payment_format"]
pl = pf[pf["grp"] == "laundering"].sort_values("share", ascending=False).iloc[0]
pn = pf[(pf["grp"] == "normal") & (pf["value"] == pl["value"])]["share"].sum()


def moved_on(g):
    h = hold[hold["grp"] == g]
    return 1 - h.loc[h["bucket"] == "never", "share"].sum(), h["median_hold_minutes"].iloc[0] / 60


ml, hl = moved_on("laundering")
mn, hn = moved_on("normal")
over = bee[bee["entry_eligible"] & (bee["expected_entries"] >= 1)].sort_values("entry_ratio", ascending=False)
over_exit = bee[bee["exit_eligible"] & (bee["expected_exits"] >= 1)].sort_values("exit_ratio", ascending=False)

st.markdown("#### What we found")
f1, f2, f3, f4 = st.columns(4)
with f1:
    theme.finding("Payment format", f"{pl['value']} carries {pl['share']:.0%} of laundering",
                  f"against {pn:.0%} of normal transactions.")
    st.page_link("views/bq2_flows.py", label="Laundering vs normal", icon=":material/arrow_forward:")
with f2:
    theme.finding("Holding time", f"Laundered money moves on more often: {ml:.0%} vs {mn:.0%}",
                  f"Median hold before it is sent on: {hl:.1f} h for laundering, {hn:.1f} h for normal.")
    st.page_link("views/bq2_flows.py", label="Holding time", icon=":material/arrow_forward:")
with f3:
    if len(over):
        o = over.iloc[0]
        theme.finding("Entry banks", f"{o['bank_name']} gets {o['entry_ratio']:.1f}x the schemes its size predicts",
                      f"{int(o['entries'])} schemes enter there"
                      + (f"; top exit outlier is {over_exit.iloc[0]['bank_name']} "
                         f"({over_exit.iloc[0]['exit_ratio']:.1f}x)." if len(over_exit) else "."))
    st.page_link("views/bq2_banks.py", label="Entry and exit banks", icon=":material/arrow_forward:")
with f4:
    theme.finding("Country routes",
                  f"{top_route['from_country']} → {top_route['to_country']} carries "
                  f"{top_route['share_of_laundering']:.1%} of laundering",
                  f"{int(top_route['n_laundering']):,} laundering transactions, rate "
                  f"{top_route['laundering_rate']:.2%}. The dataset is synthetic.")
    st.page_link("views/bq2_routes.py", label="Country routes", icon=":material/arrow_forward:")

# ---------------------------------------------------------------- top lists
st.write("")
h1, h2 = st.columns([3, 2], vertical_alignment="bottom")
h1.markdown("#### Banks and schemes to look at first")
with h2:
    n = ui.top_n("summary")

stats = bee.set_index("bank_id")  # same counts as the Entry and exit banks page
c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.markdown("**Top entry banks** · schemes entering")
    bq2.bank_button_list(stats, "entries", "sum_entry", n)
with c2.container(border=True):
    st.markdown("**Top exit banks** · schemes leaving")
    bq2.bank_button_list(stats, "exits", "sum_exit", n)
with c3.container(border=True):
    st.markdown("**Largest schemes** · total USD")
    for r in ui.head(prof.sort_values("total_usd", ascending=False), n).itertuples():
        st.button(f"#{int(r.scheme_id)} {r.scheme_type} · ${r.total_usd:,.0f}", key=f"rank_sum_s_{int(r.scheme_id)}",
                  on_click=bq2.open_scheme, args=(int(r.scheme_id),), width="stretch")

st.caption("Entry banks hold an account that only sends inside a scheme; exit banks one that only receives "
           "(cycles fall back to first sender / last receiver).")
bq2.show_popups()
