"""
IS459 Group 7 | BQ2 Dashboard: how do laundering networks move funds across banks?

Reads the BQ2 outputs in Athena (Glue database aml_bq2_curated):
  flow_comparison, holding_time, scheme_profile, country_pairs, bank_entry_exit, scheme_edges
and, for bank size proxies, aml_clean.banks and aml_raw.raw_accounts. Needs plotly and networkx.

Second page of the BQ1 app (Streamlit picks up files in pages/ automatically):
  streamlit run app.py
Uses the same AWS profile and EC2 fallback as app.py (BQ1_AWS_PROFILE, BQ1_REGION).
"""
import os
import time
from functools import partial

import altair as alt
import boto3
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from botocore.exceptions import ProfileNotFound

# ---------------------------------------------------------------- settings
REGION = os.getenv("BQ1_REGION", "us-east-1")
PROFILE = os.getenv("BQ1_AWS_PROFILE", "is459")
DATABASE = "aml_bq2_curated"
WORKGROUP = "primary"
ATHENA_OUTPUT = "s3://is459-g7-projectbucket/athena-results/streamlit/"

GROUP_COLORS = alt.Scale(domain=["laundering", "normal"], range=["#d62728", "#9ca3af"])
DIMENSION_LABELS = {"payment_format": "Payment format", "conversion": "Currency conversion",
                    "border": "Border"}

# Laundering patterns as defined for the IBM AML dataset (Altman et al., 2023)
SCHEME_TYPES = {
    "FAN-OUT": "One account splits money and sends it to many accounts.",
    "FAN-IN": "Many accounts send money into one account.",
    "GATHER-SCATTER": "Fan-in then fan-out: many accounts pay one account, which then pays many others.",
    "SCATTER-GATHER": "Fan-out then fan-in: one account pays many middle accounts, which all pay one final account.",
    "CYCLE": "Money moves along a chain of accounts and comes back to the account it started from.",
    "RANDOM": "Money hops along a random path of accounts, with no fixed shape.",
    "BIPARTITE": "A group of accounts pays another group of accounts (many to many, one layer).",
    "STACK": "Two bipartite layers in a row: senders pay middle accounts, which pay final accounts.",
}

# Longer explanation per type: why it is used (general AML background) and how it looks in the graph.
SCHEME_DETAILS = {
    "FAN-OUT": ("Breaking one large sum into many smaller transfers keeps each one below reporting thresholds "
                "and spreads the money out (structuring, 'smurfing').",
                "One account with many outgoing arrows. It is the entry account; every receiver is an exit account."),
    "FAN-IN": ("Collects money from many sources, often money mules, into one account before it is moved on "
               "or withdrawn.",
               "Many arrows pointing into one account. Every payer is an entry account; the collector is the exit account."),
    "GATHER-SCATTER": ("The hub account mixes money from many sources, so it is hard to tell which incoming "
                       "payment funds which outgoing one.",
                       "Arrows into one hub account, then out of it. The payers are entry accounts, the final receivers exit accounts."),
    "SCATTER-GATHER": ("Layering: the middle accounts break the direct link between where the money starts "
                       "and where it ends up.",
                       "A diamond: one entry account, a fan of middle accounts, one collecting exit account."),
    "CYCLE": ("Round-tripping: the money comes back to its owner looking like income from other parties.",
              "A loop. No account only sends or only receives, so entry = first sender and exit = last receiver, often the same bank."),
    "RANDOM": ("No fixed shape, so simple pattern rules miss it; every hop adds distance from the source.",
               "A meandering chain of accounts with no hub, from the entry account to the exit account."),
    "BIPARTITE": ("Many-to-many payments mix funds between two groups, so single flows are hard to follow.",
                  "Two groups with arrows criss-crossing between them. Senders are entry accounts, receivers exit accounts."),
    "STACK": ("An extra layer of middle accounts adds distance and mixing on top of a bipartite pattern.",
              "Three groups: senders (entry accounts), middle accounts, receivers (exit accounts)."),
}


def describe_type(t: str, prof: pd.DataFrame) -> str:
    """Markdown block: shape, why it is used, how it looks, and live numbers from scheme_profile."""
    d = prof[prof["scheme_type"] == t]
    why, looks = SCHEME_DETAILS.get(t, ("", ""))
    return (f"**{t}**: {SCHEME_TYPES.get(t, '')}  \n"
            f"*Why it is used:* {why}  \n"
            f"*In the graph:* {looks}  \n"
            f"*In our data:* {len(d):,} schemes, on average {d['n_transfers'].mean():.1f} transfers across "
            f"{d['n_banks'].mean():.1f} banks and {d['n_countries'].mean():.1f} countries; median duration "
            f"{d['duration_hours'].median():.0f} h, median ${d['total_usd'].median():,.0f}.")


# ---------------------------------------------------------------- Athena helper (same as app.py)
@st.cache_resource
def athena_client():
    try:
        session = boto3.Session(profile_name=PROFILE, region_name=REGION) if PROFILE else boto3.Session(region_name=REGION)
    except ProfileNotFound:
        session = boto3.Session(region_name=REGION)
    return session.client("athena")


@st.cache_data(ttl=3600, show_spinner="Querying Athena...")
def run_query(sql: str) -> pd.DataFrame:
    """Run a read-only query and return the result. Athena reuses results for 60 min to save cost."""
    athena = athena_client()
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}},
    )["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(status.get("StateChangeReason", status["State"]))

    rows, token = [], None
    while True:
        kwargs = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kwargs["NextToken"] = token
        page = athena.get_query_results(**kwargs)
        rows.extend(page["ResultSet"]["Rows"])
        token = page.get("NextToken")
        if not token:
            break
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    df = pd.DataFrame([[c.get("VarCharValue") for c in r["Data"]] for r in rows[1:]], columns=header)
    for col in df.columns:  # Athena returns text; turn numeric columns into numbers
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower() == "true"


def bank_label(df: pd.DataFrame) -> pd.Series:
    """Bank names are not unique (two 'Future Savings Bank'), so always show the id."""
    return df["bank_name"].fillna("unknown") + " (" + df["bank_id"].astype(str) + ")"


# ---------------------------------------------------------------- layout
st.set_page_config(page_title="BQ2 Cross-bank Movement", page_icon="🏦", layout="wide")
st.title("🏦 BQ2: How do laundering networks move funds across banks?")
flow = run_query("SELECT * FROM flow_comparison")
profile = run_query("SELECT * FROM scheme_profile")
st.caption(f"Live from Athena (aml_bq2_curated). Clean HI-Medium transactions 2022-09-01 to 09-16, "
           f"plus the {len(profile):,} laundering schemes reconstructed from Patterns.txt.")
n_laundering = int(flow[(flow["grp"] == "laundering") & (flow["dimension"] == "border")]["n_tx"].sum())
n_normal = int(flow[(flow["grp"] == "normal") & (flow["dimension"] == "border")]["n_tx"].sum())
in_clean = int(round((profile["n_transfers"] * profile["share_in_clean"]).sum()))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Laundering transactions", f"{n_laundering:,}")
c2.metric("Normal transactions", f"{n_normal:,}")
c3.metric("Reconstructed schemes", f"{len(profile):,}")
c4.metric("Laundering covered by schemes", f"{100 * in_clean / max(n_laundering, 1):.0f}%",
          help=f"{in_clean:,} scheme transfers match a clean laundering transaction. "
               "Scheme-based views (types, banks, network) describe this share.")

tab_flow, tab_country, tab_bank, tab_net = st.tabs(
    ["Laundering vs normal", "Country routes", "Entry and exit banks", "Scheme explorer"])

# ---------------------------------------------------------------- 1. laundering vs normal
with tab_flow:
    st.subheader("Share of transactions, laundering vs normal")
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
                    color=alt.Color("grp:N", scale=GROUP_COLORS, title=None, legend=alt.Legend(orient="bottom")),
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

    st.subheader("Holding time: how long until received money is sent on")
    hold = run_query("SELECT * FROM holding_time ORDER BY grp, bucket_order")
    left, right = st.columns([2, 1])
    with left:
        st.altair_chart(
            alt.Chart(hold).mark_bar().encode(
                x=alt.X("bucket:N", title="Time to the account's next outgoing transfer",
                        sort=alt.EncodingSortField("bucket_order")),
                xOffset="grp:N",
                y=alt.Y("share:Q", title="Share of incoming transfers", axis=alt.Axis(format="%")),
                color=alt.Color("grp:N", scale=GROUP_COLORS, title=None, legend=alt.Legend(orient="bottom")),
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

    st.subheader("Scheme types: transfers, banks and countries per scheme")
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

# ---------------------------------------------------------------- 2. country routes
with tab_country:
    pairs = run_query("SELECT * FROM country_pairs")
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
        st.info("**Count: where does most laundering happen?** Number of laundering transactions on the route. "
                "Big routes come first because they carry the most of everything.")
    else:
        st.info(f"**Rate: how suspicious is one transfer on this route?** Laundering transactions / all "
                f"transactions on the route. Average across all routes: {avg_rate:.3%}.")

    if is_count:
        data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "n_laundering", "Laundering transactions", ","
        color = alt.Color(f"{field}:Q", title=title, scale=alt.Scale(type="log", scheme="reds"))
    else:
        data, field, title, fmt = pairs[pairs["n_laundering"] >= min_n], "laundering_rate", "Laundering rate", ".1%"
        color = alt.Color(f"{field}:Q", title=title, scale=alt.Scale(scheme="reds"), legend=alt.Legend(format="%"))

    volume = (pairs.groupby("from_country")["n_laundering"].sum()
              .add(pairs.groupby("to_country")["n_laundering"].sum(), fill_value=0)
              .sort_values(ascending=False))
    order = volume.index.tolist()
    st.altair_chart(
        alt.Chart(data).mark_rect().encode(
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

    st.markdown(f"**Top 15 routes by {title.lower()}**")
    top = data.sort_values(field, ascending=False).head(15).copy()
    top[["laundering_rate", "share_of_laundering"]] *= 100
    st.dataframe(
        top[
            ["from_country", "to_country", "n_laundering", "n_normal", "laundering_rate", "x_average",
             "share_of_laundering"]],
        width="stretch", hide_index=True,
        column_config={
            "from_country": "From", "to_country": "To", "n_laundering": "Laundering", "n_normal": "Normal",
            "laundering_rate": st.column_config.NumberColumn("Laundering rate", format="%.2f%%"),
            "x_average": st.column_config.NumberColumn("x average", format="%.1f"),
            "share_of_laundering": st.column_config.NumberColumn("Share of all laundering", format="%.2f%%"),
        })
    st.caption("Small foreign-to-foreign routes can have high rates. The dataset is synthetic, so this shows "
               "where the generator places laundering, not real-world country risk.")

# ---------------------------------------------------------------- 3. entry and exit banks
with tab_bank:
    bee = run_query("SELECT * FROM bank_entry_exit")
    for c in ["entry_eligible", "exit_eligible"]:
        bee[c] = as_bool(bee[c])
    bee["bank"] = bank_label(bee)

    left, mid, right = st.columns([1, 2, 1])
    side = left.radio("Point", ["Entry", "Exit"], horizontal=True)
    view = mid.radio("Rank by", ["Most schemes (count)", "Most over-represented (ratio, 5+ schemes, expected 1+)"],
                     horizontal=True)
    top_n = right.slider("Banks shown", 5, 50, 15, step=5)

    actual, expected, ratio, eligible = (("entries", "expected_entries", "entry_ratio", "entry_eligible")
                                         if side == "Entry" else
                                         ("exits", "expected_exits", "exit_ratio", "exit_eligible"))
    if view.startswith("Most schemes"):
        d = bee[bee[actual] > 0].sort_values([actual, ratio], ascending=False).head(top_n)
        field, x_title = actual, f"Schemes that {'enter' if side == 'Entry' else 'exit'} here"
    else:
        d = bee[bee[eligible] & (bee[expected] >= 1)].sort_values(ratio, ascending=False).head(top_n)
        field, x_title = ratio, "Actual / expected schemes"

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Banks used as {side.lower()} point", f"{int((bee[actual] > 0).sum()):,}")
    c2.metric("With 5+ schemes and expected 1+", f"{int((bee[eligible] & (bee[expected] >= 1)).sum()):,}")
    c3.metric(f"All {side.lower()} points (scheme x bank)", f"{int(bee[actual].sum()):,}",
              help="A scheme with several entry (exit) banks counts once for each of them.")

    st.altair_chart(
        alt.Chart(d).mark_bar().encode(
            x=alt.X(f"{field}:Q", title=x_title),
            y=alt.Y("bank:N", sort="-x", title=None),
            color=alt.Color("country:N", title="Country"),
            tooltip=["bank", "country", alt.Tooltip(f"{actual}:Q", title="Actual"),
                     alt.Tooltip(f"{expected}:Q", format=".2f", title="Expected"),
                     alt.Tooltip(f"{ratio}:Q", format=".1f", title="Ratio")]
        ).properties(height=max(300, 26 * len(d))),
        width="stretch")
    st.dataframe(
        d[["bank", "country", actual, expected, ratio]], width="stretch", hide_index=True,
        column_config={
            "bank": "Bank (id)", "country": "Country", actual: "Actual schemes",
            expected: st.column_config.NumberColumn("Expected for its size", format="%.2f"),
            ratio: st.column_config.NumberColumn("Actual / expected", format="%.1f"),
        })
    st.caption(f"Entry banks hold an account that only sends inside a scheme; exit banks hold an account that only "
               f"receives (cycles fall back to first sender / last receiver). Expected = all {side.lower()} points "
               f"({int(bee[actual].sum()):,}) x the bank's share of all sent (entry) or received (exit) clean "
               "transactions. A ratio of 5 means five times more schemes than its size predicts. The ratio view "
               "only ranks banks with 5+ schemes and an expected count of at least 1, so tiny banks cannot top it.")

    st.markdown("**Banks used as both entry and exit (5+ each)**")
    both = bee[bee["entry_eligible"] & bee["exit_eligible"]].assign(total=lambda x: x["entries"] + x["exits"])
    st.dataframe(
        both.sort_values("total", ascending=False)[["bank", "country", "entries", "entry_ratio", "exits",
                                                    "exit_ratio"]],
        width="stretch", hide_index=True,
        column_config={
            "bank": "Bank (id)", "country": "Country", "entries": "Entries", "exits": "Exits",
            "entry_ratio": st.column_config.NumberColumn("Entry ratio", format="%.1f"),
            "exit_ratio": st.column_config.NumberColumn("Exit ratio", format="%.1f"),
        })

# ---------------------------------------------------------------- 4. scheme explorer
ROLE_COLORS = {"mostly entry": "#16a34a", "mostly exit": "#dc2626", "entry and exit": "#f59e0b",
               "pass-through": "#94a3b8"}

# Size proxies for the banks schemes touch: clean transactions (clean/banks) and accounts (accounts.csv).
# The dataset has no real bank size (assets, branches, customers).
BANK_SQL = """
    WITH sb AS (SELECT from_bank AS bank_id FROM scheme_edges UNION SELECT to_bank FROM scheme_edges),
    acc AS (SELECT TRY_CAST("bank id" AS bigint) AS bank_num, COUNT(DISTINCT "account number") AS n_accounts
            FROM aml_raw.raw_accounts GROUP BY 1)
    SELECT sb.bank_id, b.bank_name, b.country, b.total_txns, a.n_accounts
    FROM sb
    LEFT JOIN aml_clean.banks b ON b.bank_id = sb.bank_id
    LEFT JOIN acc a ON a.bank_num = TRY_CAST(sb.bank_id AS bigint)"""


@st.cache_data(show_spinner=False)
def spring_positions(nodes: tuple, edges: tuple) -> dict:
    """Force-directed layout; cached so the map does not move between reruns."""
    g = nx.Graph()
    g.add_nodes_from(nodes)
    g.add_weighted_edges_from(edges)
    pos = nx.spring_layout(g, seed=7, weight="weight", iterations=100)
    return {n: (float(x), float(y)) for n, (x, y) in pos.items()}


def set_bank(bank_id):
    st.session_state["bank_sel"] = bank_id
    st.session_state.pop("scheme_sel", None)


def clear_bank():
    st.session_state.pop("bank_sel", None)
    st.session_state.pop("scheme_sel", None)


def pick_bank_from(key):
    for p in st.session_state[key]["selection"]["points"]:
        cd = p.get("customdata")
        cd = cd[0] if isinstance(cd, list) and cd else cd
        if cd not in (None, "edge", "other"):
            set_bank(int(cd))
            break


def pick_scheme_from_table(key):
    rows = st.session_state[key]["selection"]["rows"]
    if rows:
        st.session_state["scheme_sel"] = st.session_state["bank_schemes_ids"][rows[0]]
        st.session_state["dialog_scheme"] = st.session_state["scheme_sel"]


def open_scheme(scheme_id):
    st.session_state["scheme_sel"] = scheme_id
    st.session_state["dialog_scheme"] = scheme_id


def pick_scheme_from_box():
    if st.session_state.get("scheme_pick") is not None:
        st.session_state["scheme_sel"] = st.session_state["scheme_pick"]
        st.session_state["dialog_scheme"] = st.session_state["scheme_pick"]


with tab_net:
    edges_all = run_query("SELECT * FROM scheme_edges")
    try:
        info = run_query(BANK_SQL).set_index("bank_id")
    except Exception as ex:  # keep the page usable if the size query fails
        st.warning(f"Bank size query failed, showing names from bank_entry_exit only: {ex}")
        info = bee.set_index("bank_id")[["bank_name", "country"]].assign(total_txns=None, n_accounts=None)
    info["bank"] = info["bank_name"].fillna("unknown") + " (" + info.index.astype(str) + ")"
    ratios = bee.set_index("bank_id")

    def name_of(b):
        return info["bank"].get(b, f"bank {b}")

    def country_of(b):
        return info["country"].get(b, "?")

    def label_of(b):
        return "Other banks" if b == -1 else name_of(b)

    def scheme_edges_of(scheme_id):
        """Transfers of one scheme in time order (ties by step), numbered from 1."""
        ed = edges_all[edges_all["scheme_id"] == scheme_id].copy()
        ed["ts"] = ed["ts"].astype(str)
        ed = ed.sort_values(["ts", "step"]).reset_index(drop=True)
        ed["order"] = ed.index + 1
        return ed

    def scheme_end_accounts(ed):
        """Entry accounts = only send, exit accounts = only receive (self-transfers ignored).
        Same rule as bq2_analysis.py, with the same first-sender / last-receiver fallback."""
        moves = ed[ed["src"] != ed["dst"]]
        outs, ins = set(moves["src"]), set(moves["dst"])
        entries_, exits_ = outs - ins, ins - outs
        if not entries_:
            entries_ = {ed.iloc[0]["src"]}
        if not exits_:
            exits_ = {ed.sort_values(["ts", "step"], ascending=[False, True]).iloc[0]["dst"]}
        return entries_, exits_

    def scheme_figure(ed, sel_bank=None, small=False):
        """Accounts as nodes, transfers as arrows. Entry accounts only send inside the scheme, exit accounts
        only receive; with none (cycles) the first sender / last receiver is used. sel_bank gets a yellow ring."""
        entries_, exits_ = scheme_end_accounts(ed)
        country = dict(zip(ed["src"], ed["from_country"]))
        country.update(zip(ed["dst"], ed["to_country"]))
        nodes = sorted(country)
        spos = spring_positions(tuple(nodes), tuple((a, b, 1) for a, b in zip(ed["src"], ed["dst"]) if a != b))

        fig = go.Figure()
        for r in ed.itertuples():
            if r.src == r.dst:
                continue
            (x0, y0), (x1, y1) = spos[r.src], spos[r.dst]
            fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y", text="",
                               showarrow=True, arrowhead=2, arrowsize=1 if small else 1.2,
                               arrowwidth=1 if small else 1.3, arrowcolor="#64748b",
                               standoff=7 if small else 12, startstandoff=7 if small else 12)
        fig.add_trace(go.Scatter(
            x=[spos[a][0] + 0.55 * (spos[b][0] - spos[a][0]) for a, b in zip(ed["src"], ed["dst"])],
            y=[spos[a][1] + 0.55 * (spos[b][1] - spos[a][1]) for a, b in zip(ed["src"], ed["dst"])],
            mode="markers" if small else "markers+text", text=ed["order"].astype(str), textposition="top center",
            textfont=dict(size=10, color="#64748b"), marker=dict(size=4 if small else 6, color="#94a3b8"),
            showlegend=False, customdata=[["edge"]] * len(ed), hoverinfo="text",
            hovertext=[f"{r.order}. {r.src} → {r.dst}<br>${r.amount_usd:,.0f} · {r.payment_format}<br>{r.ts[:16]}"
                       for r in ed.itertuples()]))
        role = {n: ("entry and exit" if n in entries_ and n in exits_ else "mostly entry" if n in entries_
                    else "mostly exit" if n in exits_ else "pass-through") for n in nodes}
        node_names = {"mostly entry": "entry account", "mostly exit": "exit account",
                      "entry and exit": "entry and exit (same account)", "pass-through": "other account"}
        tag = {"mostly entry": "ENTRY · ", "mostly exit": "EXIT · ", "entry and exit": "ENTRY + EXIT · ",
               "pass-through": ""}
        for rl, color in ROLE_COLORS.items():
            ns = [n for n in nodes if role[n] == rl]
            if not ns:
                continue
            mine_ = [int(n.split(":")[0]) == sel_bank for n in ns]
            fig.add_trace(go.Scatter(
                x=[spos[n][0] for n in ns], y=[spos[n][1] for n in ns],
                mode="markers" if small else "markers+text", name=node_names[rl], customdata=[[n] for n in ns],
                text=[tag[rl] + name_of(int(n.split(":")[0])).split(" (")[0][:22] for n in ns],
                textposition="bottom center", textfont=dict(size=10),
                hovertext=[f"<b>{n}</b><br>{name_of(int(n.split(':')[0]))}<br>{country[n]}" for n in ns],
                hoverinfo="text",
                marker=dict(size=11 if small else 18,
                            # same account enters and exits the money: half green, half red
                            color=ROLE_COLORS["mostly entry"] if rl == "entry and exit" else color,
                            gradient=(dict(type="horizontal", color=ROLE_COLORS["mostly exit"])
                                      if rl == "entry and exit" else None),
                            line=dict(width=[(3 if small else 4) if m else 1 for m in mine_],
                                      color=["#facc15" if m else "#111827" for m in mine_]))))
        fig.update_layout(height=260 if small else 560, margin=dict(l=0, r=0, t=10, b=0), dragmode="pan",
                          xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=not small,
                          legend=dict(orientation="h", y=1.04), hovermode="closest")
        return fig

    def scheme_end_banks(prof):
        """One row per (scheme, bank, entry|exit) from scheme_profile's entry_banks / exit_banks lists.
        Falls back to the single entry_bank / exit_bank columns if the lists are missing (older run)."""
        parts = []
        for kind, many, one in [("entry", "entry_banks", "entry_bank"), ("exit", "exit_banks", "exit_bank")]:
            if many in prof:
                x = prof[["scheme_id", many]].copy()
                x["bank_id"] = x[many].astype(str).str.split(",")
                x = x.explode("bank_id")
            else:
                x = prof[["scheme_id", one]].rename(columns={one: "bank_id"})
            x["bank_id"] = pd.to_numeric(x["bank_id"], errors="coerce")
            parts.append(x.dropna(subset=["bank_id"])[["scheme_id", "bank_id"]].assign(kind=kind))
        out = pd.concat(parts).drop_duplicates()
        out["bank_id"] = out["bank_id"].astype("int64")
        return out

    ends = scheme_end_banks(profile)

    # ---- A. bank map
    st.subheader("Bank map: which banks the schemes run through")
    c1, c2 = st.columns(2)
    stype = c1.selectbox("Scheme type", ["All types"] + sorted(profile["scheme_type"].unique()), key="map_type")
    top_n = c2.slider("Banks on the map (most schemes first)", 10, 150, 20, step=5)
    e = edges_all if stype == "All types" else edges_all[edges_all["scheme_type"] == stype]
    prof_f = profile if stype == "All types" else profile[profile["scheme_type"] == stype]
    if stype != "All types":
        st.info(describe_type(stype, profile))
    with st.expander("What the scheme types mean (all 8)"):
        st.markdown("\n\n".join(describe_type(t, profile) for t in SCHEME_TYPES))
        st.caption("Shapes as defined for the IBM AML dataset (Altman et al., 2023). 'Why it is used' is general "
                   "AML background; 'In our data' is computed live from scheme_profile.")
    dot = '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{};margin:0 6px 0 14px"></span>'
    st.markdown(
        "Colours: "
        + dot.format(ROLE_COLORS["mostly entry"]) + "**mostly entry** (where schemes put money in)"
        + dot.format(ROLE_COLORS["mostly exit"]) + "**mostly exit** (where schemes take money out)"
        + dot.format(ROLE_COLORS["entry and exit"]) + "**entry and exit** (both, in similar numbers)"
        + dot.format(ROLE_COLORS["pass-through"]) + "**pass-through** (only in the middle of schemes)"
        + dot.format("#475569").replace("50%", "2px") + "**other banks** (not on the map)",
        unsafe_allow_html=True)

    ends_f = ends[ends["scheme_id"].isin(prof_f["scheme_id"])]
    touch = pd.concat([e[["scheme_id", "from_bank"]].rename(columns={"from_bank": "bank_id"}),
                       e[["scheme_id", "to_bank"]].rename(columns={"to_bank": "bank_id"})]).drop_duplicates()
    stats = pd.concat([touch.groupby("bank_id")["scheme_id"].nunique().rename("n_schemes"),
                       ends_f[ends_f["kind"] == "entry"].groupby("bank_id")["scheme_id"].nunique().rename("entries"),
                       ends_f[ends_f["kind"] == "exit"].groupby("bank_id")["scheme_id"].nunique().rename("exits")],
                      axis=1).fillna(0).astype(int)
    stats["role"] = "entry and exit"
    stats.loc[stats["entries"] >= 2 * stats["exits"], "role"] = "mostly entry"
    stats.loc[stats["exits"] >= 2 * stats["entries"], "role"] = "mostly exit"
    stats.loc[(stats["entries"] + stats["exits"]) == 0, "role"] = "pass-through"

    sel = st.session_state.get("bank_sel")
    top = stats.sort_values(["n_schemes", "entries", "exits"], ascending=False).head(top_n).index.tolist()
    if sel in stats.index and sel not in top:
        top.append(sel)
    # Links to banks not on the map go to one "Other banks" node, so the map stays one connected picture.
    OTHER = -1
    lk = e.assign(from_bank=e["from_bank"].where(e["from_bank"].isin(top), OTHER),
                  to_bank=e["to_bank"].where(e["to_bank"].isin(top), OTHER))
    lk = lk[(lk["from_bank"] != lk["to_bank"])]
    be = (lk.groupby(["from_bank", "to_bank"])
          .agg(transfers=("scheme_id", "size"), schemes=("scheme_id", "nunique"), usd=("amount_usd", "sum"))
          .reset_index())
    n_other = int(stats.shape[0] - len(top))
    pos = spring_positions(tuple(int(b) for b in top) + (OTHER,),
                           tuple((int(a), int(b), 1) for a, b in be[["from_bank", "to_bank"]].itertuples(index=False)))

    map_col, list_col = st.columns([3, 1])
    with map_col:
        fig = go.Figure()
        xs, ys, mx, my, mtext = [], [], [], [], []
        for r in be.itertuples():
            (x0, y0), (x1, y1) = pos[r.from_bank], pos[r.to_bank]
            xs += [x0, x1, None]
            ys += [y0, y1, None]
            mx.append(x0 + 0.6 * (x1 - x0))  # marker nearer the receiver shows the direction
            my.append(y0 + 0.6 * (y1 - y0))
            mtext.append(f"{label_of(r.from_bank)} → {label_of(r.to_bank)}<br>"
                         f"{r.schemes} schemes, {r.transfers} transfers, ${r.usd:,.0f}")
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(width=0.7, color="rgba(148,163,184,0.45)")))
        fig.add_trace(go.Scatter(x=mx, y=my, mode="markers", hovertext=mtext, hoverinfo="text", showlegend=False,
                                 marker=dict(size=4, color="rgba(148,163,184,0.7)"),
                                 customdata=[["edge"]] * len(mx)))
        fig.add_trace(go.Scatter(
            x=[pos[OTHER][0]], y=[pos[OTHER][1]], mode="markers+text", name="other banks (not on the map)",
            text=["Other banks"], textposition="bottom center", customdata=[["other"]], hoverinfo="text",
            hovertext=[f"{n_other:,} banks not on the map. Raise the slider to show more of them."],
            marker=dict(size=22, symbol="square", color="#475569")))
        on_map = stats.loc[top]
        for role, color in ROLE_COLORS.items():
            d = on_map[on_map["role"] == role]
            if d.empty:
                continue
            fig.add_trace(go.Scatter(
                x=[pos[b][0] for b in d.index], y=[pos[b][1] for b in d.index], mode="markers", name=role,
                customdata=[[int(b)] for b in d.index],
                hovertext=[f"<b>{name_of(b)}</b><br>{country_of(b)}<br>{r.n_schemes} schemes, "
                           f"{r.entries} entries, {r.exits} exits<br><i>Click to see its {r.n_schemes} schemes</i>"
                           for b, r in d.iterrows()],
                hoverinfo="text",
                marker=dict(size=[8 + 3 * n ** 0.5 for n in d["n_schemes"]], color=color,
                            line=dict(width=[3 if b == sel else 0.5 for b in d.index], color="#111827"))))
        fig.update_layout(height=600, margin=dict(l=0, r=0, t=10, b=0), dragmode="pan",
                          xaxis=dict(visible=False), yaxis=dict(visible=False),
                          legend=dict(orientation="h", y=1.04), hovermode="closest")
        st.plotly_chart(fig, key="bankmap", on_select=partial(pick_bank_from, "bankmap"), selection_mode="points",
                        width="stretch", config={"scrollZoom": True})
        st.caption("Click a bank to open it. Node size = schemes through the bank. 'Mostly' means at least twice "
                   "as many entries as exits (or the reverse). Scroll to zoom, drag to pan. Grey dots sit on each "
                   "link, nearer the receiving bank; hover them for the flow.")

    with list_col:
        for label, col in [("Top entry banks", "entries"), ("Top exit banks", "exits")]:
            st.markdown(f"**{label}**")
            for b, r in stats[stats[col] > 0].sort_values(col, ascending=False).head(10).iterrows():
                st.button(f"{name_of(b)} · {r[col]}", key=f"{col}_{b}", on_click=set_bank, args=(int(b),),
                          width="stretch")

    # ---- B. selected bank
    sel = st.session_state.get("bank_sel")
    if sel is not None:
        st.divider()
        h1, h2 = st.columns([4, 1])
        h1.subheader(f"{name_of(sel)}, {country_of(sel)}")
        h2.button("Clear bank", on_click=clear_bank, width="stretch")
        s = stats.loc[sel] if sel in stats.index else pd.Series({"n_schemes": 0, "entries": 0, "exits": 0})
        rr = ratios.loc[sel] if sel in ratios.index else None
        size_txns, size_acc = info["total_txns"].get(sel), info["n_accounts"].get(sel)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Schemes through this bank", f"{int(s['n_schemes']):,}")
        c2.metric("Entries / exits", f"{int(s['entries'])} / {int(s['exits'])}")
        c3.metric("Entry / exit ratio",
                  "n/a" if rr is None else
                  " / ".join("n/a" if pd.isna(v) else f"{v:.1f}x" for v in (rr["entry_ratio"], rr["exit_ratio"])),
                  help="All scheme types: actual schemes / what the bank's share of clean transactions predicts.")
        c4.metric("Size: clean transactions", "n/a" if pd.isna(size_txns) else f"{int(size_txns):,}",
                  help="Sent plus received clean transactions, 2022-09-01 to 09-16.")
        c5.metric("Size: accounts", "n/a" if pd.isna(size_acc) else f"{int(size_acc):,}",
                  help="Accounts listed for this bank in accounts.csv.")

        mine = touch[touch["bank_id"] == sel]["scheme_id"].unique()

        # Flows around the bank: who sends scheme money to it (left), who it sends to (right).
        st.markdown(f"**Where the money comes from and goes to, in its {stype.lower()} schemes** "
                    "(click a bank to jump to it)")
        inflow = (e[(e["to_bank"] == sel) & (e["from_bank"] != sel)].groupby("from_bank")
                  .agg(schemes=("scheme_id", "nunique"), usd=("amount_usd", "sum"))
                  .sort_values(["schemes", "usd"], ascending=False))
        outflow = (e[(e["from_bank"] == sel) & (e["to_bank"] != sel)].groupby("to_bank")
                   .agg(schemes=("scheme_id", "nunique"), usd=("amount_usd", "sum"))
                   .sort_values(["schemes", "usd"], ascending=False))
        left, right = inflow.head(15), outflow.head(15)
        ego = go.Figure()

        def side_y(n):
            return [(n - 1) / 2 - i for i in range(n)]

        for df_, x, y_list, arrow in [(left, 0.0, side_y(len(left)), "in"), (right, 2.0, side_y(len(right)), "out")]:
            for (b, r), y in zip(df_.iterrows(), y_list):
                xa, ya, xb, yb = (x, y, 1.0, 0.0) if arrow == "in" else (1.0, 0.0, x, y)
                ego.add_trace(go.Scatter(x=[xa, xb], y=[ya, yb], mode="lines", hoverinfo="skip", showlegend=False,
                                         line=dict(width=1 + 2 * r["schemes"] ** 0.5, color="rgba(148,163,184,0.5)")))
            if len(df_):
                ego.add_trace(go.Scatter(
                    x=[x] * len(df_), y=y_list, mode="markers+text", showlegend=False,
                    text=[name_of(b).split(" (")[0][:24] for b in df_.index],
                    textposition="middle left" if arrow == "in" else "middle right",
                    customdata=[[int(b)] for b in df_.index], hoverinfo="text",
                    hovertext=[(f"{name_of(b)} → this bank" if arrow == "in" else f"this bank → {name_of(b)}")
                               + f"<br>{r['schemes']} schemes, ${r['usd']:,.0f}<br>{country_of(b)}"
                               for b, r in df_.iterrows()],
                    marker=dict(size=[10 + 3 * v ** 0.5 for v in df_["schemes"]],
                                color=[ROLE_COLORS[stats["role"].get(b, "pass-through")] for b in df_.index],
                                line=dict(width=0.5, color="#111827"))))
        ego.add_trace(go.Scatter(x=[1.0], y=[0.0], mode="markers+text", text=[name_of(sel).split(" (")[0]],
                                 textposition="top center", showlegend=False, customdata=[["edge"]],
                                 hoverinfo="text", hovertext=[f"<b>{name_of(sel)}</b> (selected)"],
                                 marker=dict(size=30, symbol="diamond", color="#facc15",
                                             line=dict(width=1, color="#111827"))))
        rows = max(len(left), len(right), 1)
        ego.update_layout(height=max(320, 30 * rows), margin=dict(l=0, r=0, t=10, b=0), dragmode="pan",
                          xaxis=dict(visible=False, range=[-1.1, 3.1]), yaxis=dict(visible=False),
                          hovermode="closest")
        ego.add_annotation(x=0, y=(rows + 1) / 2, text=f"<b>Sends to it</b> ({len(inflow)} banks)",
                           showarrow=False)
        ego.add_annotation(x=2, y=(rows + 1) / 2, text=f"<b>Receives from it</b> ({len(outflow)} banks)",
                           showarrow=False)
        st.plotly_chart(ego, key=f"egomap_{sel}", on_select=partial(pick_bank_from, f"egomap_{sel}"),
                        selection_mode="points", width="stretch")
        st.caption("Money flows left to right through the selected bank (yellow diamond). Line width = number of "
                   "schemes; colours as on the map. Up to 15 banks per side, most schemes first.")

        # Position of the bank inside each of its schemes.
        def bank_path(g):
            seq = [g.iloc[0]["from_bank"]] + g["to_bank"].tolist()
            return [b for i, b in enumerate(seq) if i == 0 or b != seq[i - 1]]

        me = e[e["scheme_id"].isin(mine)].copy()
        me["ts"] = me["ts"].astype(str)
        pos_rows = []
        for sid_, g in me.groupby("scheme_id"):
            g = g.sort_values(["ts", "step"]).reset_index(drop=True)
            hit = g.index[(g["from_bank"] == sel) | (g["to_bank"] == sel)]
            path = bank_path(g)
            pos_rows.append({"scheme_id": sid_,
                             "first_seen": f"transfer {int(hit[0]) + 1} of {len(g)}" if len(hit) else "",
                             "other_banks": len(set(path) - {sel}),
                             "path": " → ".join(("★ " if b == sel else "") + name_of(b).split(" (")[0]
                                                for b in path)})
        bs = prof_f[prof_f["scheme_id"].isin(mine)].merge(pd.DataFrame(pos_rows), on="scheme_id", how="left")
        is_in = bs["scheme_id"].isin(ends[(ends["bank_id"] == sel) & (ends["kind"] == "entry")]["scheme_id"])
        is_out = bs["scheme_id"].isin(ends[(ends["bank_id"] == sel) & (ends["kind"] == "exit")]["scheme_id"])
        bs["role"] = "middle"
        bs.loc[is_in, "role"] = "entry"
        bs.loc[is_out, "role"] = "exit"
        bs.loc[is_in & is_out, "role"] = "entry and exit"
        # Entry and exit schemes first, then middle; largest USD first inside each group.
        role_rank = {"entry and exit": 0, "entry": 1, "exit": 2, "middle": 3}
        bs = (bs.assign(_rank=bs["role"].map(role_rank)).sort_values(["_rank", "total_usd"], ascending=[True, False])
              .drop(columns="_rank").reset_index(drop=True))

        st.markdown(f"### Its {len(bs)} schemes ({stype.lower()})")
        st.caption("Entry and exit schemes first, then schemes where the bank is in the middle; largest USD first.")

        # ---- graphs: 3 by default, all (12 per page), or the ones you pick
        GALLERY = 3
        PAGE = 12
        labels_bs = {int(r.scheme_id): f"#{int(r.scheme_id)} {r.scheme_type} ({r.role}), ${r.total_usd:,.0f}"
                     for r in bs.itertuples()}
        g1, g2 = st.columns([1, 3])
        show_all = g1.toggle(f"Show all {len(bs)} graphs", key=f"all_graphs_{sel}", disabled=len(bs) <= GALLERY)
        chosen = g2.multiselect("Or choose which schemes to show", list(labels_bs), format_func=labels_bs.get,
                                key=f"chosen_{sel}", placeholder="Pick schemes")
        if chosen:
            gal = bs[bs["scheme_id"].isin(chosen)]
        elif show_all:
            pages = (len(bs) + PAGE - 1) // PAGE
            page = st.number_input(f"Page (of {pages}, {PAGE} graphs each)", 1, max(pages, 1), 1,
                                   key=f"page_{sel}") if pages > 1 else 1
            gal = bs.iloc[(page - 1) * PAGE: page * PAGE]
        else:
            gal = bs.head(GALLERY)

        for start in range(0, len(gal), 3):
            for col, r in zip(st.columns(3), gal.iloc[start:start + 3].itertuples()):
                with col.container(border=True):
                    st.markdown(f"**#{int(r.scheme_id)} {r.scheme_type}** · this bank: **{r.role}**  \n"
                                f"{int(r.n_transfers)} transfers, {int(r.n_banks)} banks, "
                                f"{r.duration_hours:.0f} h, ${r.total_usd:,.0f}")
                    st.plotly_chart(scheme_figure(scheme_edges_of(r.scheme_id), sel, small=True),
                                    key=f"mini_{sel}_{int(r.scheme_id)}", width="stretch",
                                    config={"displayModeBar": False})
                    st.button("Open", key=f"open_{sel}_{int(r.scheme_id)}", on_click=open_scheme,
                              args=(int(r.scheme_id),), width="stretch")
        if not chosen and not show_all and len(bs) > GALLERY:
            st.caption(f"Showing {GALLERY} of {len(bs)}. Use 'Show all' or pick schemes above.")

        # ---- table: 3 rows by default, all on request
        show_rows = st.toggle(f"Show all {len(bs)} rows in the table", key=f"all_rows_{sel}",
                              disabled=len(bs) <= GALLERY)
        tbl = bs if show_rows else bs.head(GALLERY)
        st.session_state["bank_schemes_ids"] = tbl["scheme_id"].astype(int).tolist()
        st.markdown("**Where the bank sits in each scheme, and the other banks.** Click a row to open the scheme.")
        st.dataframe(
            tbl[["scheme_id", "scheme_type", "role", "first_seen", "other_banks", "path", "n_transfers",
                 "duration_hours", "total_usd"]],
            key=f"bank_schemes_{sel}_{show_rows}", on_select=partial(pick_scheme_from_table, f"bank_schemes_{sel}_{show_rows}"),
            selection_mode="single-row",
            width="stretch", hide_index=True, height=min(420, 38 + 35 * len(tbl)),
            column_config={
                "scheme_id": "Scheme", "scheme_type": "Type", "role": "This bank is",
                "first_seen": "First appears at", "other_banks": "Other banks",
                "path": st.column_config.TextColumn("Bank path in time order (★ = this bank)", width="large"),
                "n_transfers": "Transfers",
                "duration_hours": st.column_config.NumberColumn("Duration (h)", format="%.0f"),
                "total_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
            })

    # ---- C. open any scheme; every scheme opens in a popup, so no scrolling
    st.divider()
    st.subheader("Open any scheme")
    pick_opts = prof_f.sort_values("n_transfers", ascending=False)
    pick_labels = {int(r.scheme_id): f"#{int(r.scheme_id)} {r.scheme_type}: {int(r.n_transfers)} transfers, "
                                     f"{int(r.n_banks)} banks, ${r.total_usd:,.0f}" for r in pick_opts.itertuples()}
    st.selectbox("Scheme (largest first)", list(pick_labels), format_func=pick_labels.get, index=None,
                 placeholder="Choose a scheme; it opens in a popup", key="scheme_pick",
                 on_change=pick_scheme_from_box)

    def badge(text, color):
        return (f'<span style="background:{color};color:white;padding:2px 8px;border-radius:6px;'
                f'font-weight:600;font-size:0.85em">{text}</span>')

    @st.dialog("Scheme", width="large")
    def scheme_dialog(sid):
        p = profile[profile["scheme_id"] == sid].iloc[0]
        ed = scheme_edges_of(sid)
        sel_bank = st.session_state.get("bank_sel")
        st.markdown(f"### #{int(sid)} {p['scheme_type']}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Transfers / accounts", f"{int(p['n_transfers'])} / {int(p['n_accounts'])}")
        c2.metric("Banks / countries", f"{int(p['n_banks'])} / {int(p['n_countries'])}")
        c3.metric("Duration", f"{p['duration_hours']:.0f} h")
        c4.metric("Total USD", f"${p['total_usd']:,.0f}")

        green, red = ROLE_COLORS["mostly entry"], ROLE_COLORS["mostly exit"]
        ent_b = sorted(ends[(ends["scheme_id"] == sid) & (ends["kind"] == "entry")]["bank_id"])
        ext_b = sorted(ends[(ends["scheme_id"] == sid) & (ends["kind"] == "exit")]["bank_id"])

        def bank_list(banks):
            return "; ".join(f"**{name_of(b)}**, {country_of(b)}" for b in banks)

        both = [b for b in ent_b if b in ext_b]
        st.markdown(badge(f"ENTRY ({len(ent_b)})", green) + " " + bank_list(ent_b), unsafe_allow_html=True)
        st.markdown(badge(f"EXIT ({len(ext_b)})", red) + " " + bank_list(ext_b), unsafe_allow_html=True)
        if both:
            st.markdown(badge("ENTRY", green) + badge("EXIT", red) + " Same bank on both sides: " + bank_list(both),
                        unsafe_allow_html=True)

        seq = [ed.iloc[0]["from_bank"]] + ed["to_bank"].tolist()
        path = [b for i, b in enumerate(seq) if i == 0 or b != seq[i - 1]]
        st.markdown("**Bank path in time order:** " + " → ".join(
            (f"**★ {name_of(b)}**" if b == sel_bank else name_of(b)) for b in path))
        with st.expander(f"About {p['scheme_type']} schemes"):
            st.markdown(describe_type(p["scheme_type"], profile))

        ev = st.plotly_chart(scheme_figure(ed, sel_bank), key=f"scheme_graph_{int(sid)}", on_select="rerun",
                             selection_mode="points", width="stretch", config={"scrollZoom": True})
        st.caption("Nodes are accounts, labelled with their bank. Green = entry accounts (only send in this scheme), "
                   "red = exit accounts (only receive), half green / half red = the same account is both (cycles). Arrows are transfers; the grey number is "
                   "the time order (hover for amount, format and time). "
                   + ("Yellow rings and ★ mark the bank you selected. " if sel_bank in set(path) else "")
                   + f"{p['share_in_clean']:.0%} of its transfers are inside the clean window. "
                   "Click an account to list its transfers.")

        picked = []
        for pt in (ev.selection.points if ev else []):
            cd = pt.get("customdata")
            cd = cd[0] if isinstance(cd, list) and cd else cd
            if cd not in (None, "edge"):
                picked.append(cd)
        shown = ed[ed["src"].isin(picked) | ed["dst"].isin(picked)] if picked else ed
        st.markdown(f"**Transfers{' of ' + ', '.join(picked) if picked else ''}**")
        st.dataframe(shown[["order", "ts", "src", "dst", "from_country", "to_country", "amount_usd",
                            "payment_format"]],
                     width="stretch", hide_index=True,
                     column_config={"order": "#", "amount_usd": st.column_config.NumberColumn("USD", format="$%.0f")})

    # Open the popup once per click; clicks inside it rerun only the popup, so it stays open.
    pending = st.session_state.pop("dialog_scheme", None)
    if pending is not None and pending in set(profile["scheme_id"]):
        scheme_dialog(int(pending))
