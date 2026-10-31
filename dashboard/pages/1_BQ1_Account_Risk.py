"""
BQ1 | Which accounts should investigators review first?

Reads the live BQ1 outputs in Athena (Glue database aml_curated):
  risk_rankings, account_labels, account_profiles, capacity_summary
"""
import re

import altair as alt
import pandas as pd
import streamlit as st

from common.athena import run_query

# points column -> (label, max points from the revised weight table)
BEHAVIOURS = {
    "ach_points": ("ACH share", 25),
    "cross_border_points": ("Cross-border share", 15),
    "fan_out_points": ("Fan-out", 15),
    "fan_in_points": ("Fan-in", 15),
    "amount_band_points": ("Amount band (p50 to p95)", 10),
    "pass_through_points": ("Pass-through within 24h", 10),
    "activity_spike_points": ("Activity spike", 10),
}
POINT_COLS = list(BEHAVIOURS)


def why_flagged(row, top=3) -> str:
    """Top contributing behaviours for one account, e.g. 'ACH share 25, Fan-out 15'."""
    pts = sorted(((row[c], BEHAVIOURS[c][0]) for c in POINT_COLS if row[c] > 0), reverse=True)[:top]
    return ", ".join(f"{name} {p:.0f}" for p, name in pts)


def day_filter(col: str, days: list) -> str:
    return f"{col} IN ({', '.join(repr(d) for d in days)})"


# ---------------------------------------------------------------- layout
st.set_page_config(page_title="BQ1 Investigator Queue", page_icon="🏦", layout="wide")
st.title("🏦 BQ1: Which accounts should investigators review first?")
st.caption("Live from Athena (aml_curated). Risk score 0 to 100 = sum of weight x behaviour score.")

all_days = run_query("SELECT DISTINCT profile_date FROM risk_rankings ORDER BY 1")["profile_date"].astype(str).tolist()

with st.sidebar:
    st.header("Controls")
    day = st.selectbox("Day for queue and drill-down", all_days, index=len(all_days) - 1)
    capacity = st.slider("Daily investigator capacity (accounts)", 50, 1000, 100, step=50)
    eval_days = st.multiselect("Days for the capacity curve", all_days, default=all_days,
                               help="Pick a held-out set of days to report results on unseen days.")
    show_truth = st.toggle("Show ground truth (IsLaundering)", value=True,
                           help="Labels are only used to evaluate the score, never to compute it.")
    st.caption(f"{len(all_days)} days loaded: {all_days[0]} to {all_days[-1]}")

tab_queue, tab_curve, tab_dist, tab_drill = st.tabs(
    ["Investigator queue", "Capacity vs detection", "Score distribution", "Account drill-down"])

# ---------------------------------------------------------------- 1. queue
with tab_queue:
    queue = run_query(f"""
        SELECT r.daily_rank, r.account_key, r.bank_id, r.account_id, r.risk_score, r.txn_count,
               r.total_amount_usd, r.daily_active_accounts, {', '.join('r.' + c for c in POINT_COLS)},
               COALESCE(l.account_day_is_laundering, 0) AS is_laundering
        FROM risk_rankings r
        LEFT JOIN account_labels l
          ON l.account_key = r.account_key AND l.profile_date = r.profile_date
        WHERE r.profile_date = '{day}' AND r.daily_rank <= {capacity}
        ORDER BY r.daily_rank""")
    queue["why_flagged"] = queue.apply(why_flagged, axis=1)

    caught = int(queue["is_laundering"].sum())
    total_day = int(run_query(f"SELECT SUM(account_day_is_laundering) AS t FROM account_labels "
                              f"WHERE profile_date = '{day}'")["t"].iloc[0])
    active = int(queue["daily_active_accounts"].iloc[0]) if len(queue) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active accounts that day", f"{active:,}")
    c2.metric("Accounts in queue", f"{len(queue):,}")
    c3.metric("Lowest score in queue", f"{queue['risk_score'].min():.1f}" if len(queue) else "n/a")
    if show_truth:
        c4.metric("Laundering caught (precision)", f"{caught} ({100 * caught / max(len(queue), 1):.1f}%)",
                  help=f"{total_day:,} laundering accounts active that day, so detection rate is "
                       f"{100 * caught / max(total_day, 1):.2f}%")

    cols = ["daily_rank", "account_key", "risk_score", "why_flagged", "txn_count", "total_amount_usd"]
    if show_truth:
        cols.append("is_laundering")
    st.dataframe(
        queue[cols], width="stretch", hide_index=True, height=520,
        column_config={
            "daily_rank": "Rank", "account_key": "Account (bank:account)",
            "risk_score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100, format="%.1f"),
            "why_flagged": "Why flagged (top behaviours, points)",
            "txn_count": "Txns", "total_amount_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
            "is_laundering": st.column_config.CheckboxColumn("Laundering"),
        })

    st.subheader(f"What drives the top {capacity} (average points per behaviour)")
    drivers = queue[POINT_COLS].mean().rename(lambda c: BEHAVIOURS[c][0]).reset_index()
    drivers.columns = ["behaviour", "avg_points"]
    drivers["max_points"] = [BEHAVIOURS[c][1] for c in POINT_COLS]
    st.altair_chart(
        alt.Chart(drivers).mark_bar().encode(
            x=alt.X("avg_points:Q", title="Average points (bar) out of the weight"),
            y=alt.Y("behaviour:N", sort="-x", title=None),
            tooltip=["behaviour", alt.Tooltip("avg_points:Q", format=".1f"), "max_points"]),
        width="stretch")

# ---------------------------------------------------------------- 2. capacity curve
with tab_curve:
    if not eval_days:
        st.info("Pick at least one day in the sidebar.")
    else:
        curve = run_query(f"""
            WITH r AS (
              SELECT profile_date, account_key, daily_rank,
                     ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY txn_count DESC, account_key) AS base_rank
              FROM risk_rankings WHERE {day_filter('profile_date', eval_days)}),
            j AS (
              SELECT r.daily_rank, r.base_rank, l.account_day_is_laundering AS y
              FROM r JOIN account_labels l
                ON l.account_key = r.account_key AND l.profile_date = r.profile_date
              WHERE {day_filter('l.profile_date', eval_days)} AND (r.daily_rank <= 2000 OR r.base_rank <= 2000)),
            lim AS (SELECT n FROM UNNEST(SEQUENCE(50, 2000, 50)) AS t(n))
            SELECT lim.n AS daily_capacity,
                   SUM(CASE WHEN j.daily_rank <= lim.n THEN j.y ELSE 0 END) AS caught_score,
                   SUM(CASE WHEN j.base_rank  <= lim.n THEN j.y ELSE 0 END) AS caught_baseline
            FROM lim CROSS JOIN j GROUP BY lim.n ORDER BY lim.n""")
        total = int(run_query(f"SELECT SUM(account_day_is_laundering) AS t FROM account_labels "
                              f"WHERE {day_filter('profile_date', eval_days)}")["t"].iloc[0])
        n_days = len(eval_days)
        curve["Our risk score"] = 100 * curve["caught_score"] / total
        curve["Baseline: most transactions"] = 100 * curve["caught_baseline"] / total
        curve["precision_score"] = 100 * curve["caught_score"] / (curve["daily_capacity"] * n_days)
        curve["precision_baseline"] = 100 * curve["caught_baseline"] / (curve["daily_capacity"] * n_days)

        at = curve[curve["daily_capacity"] == capacity].iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Precision at {capacity}/day", f"{at['precision_score']:.1f}%",
                  f"{at['precision_score'] - at['precision_baseline']:+.1f} pts vs baseline")
        c2.metric(f"Laundering caught at {capacity}/day", f"{int(at['caught_score']):,}",
                  f"{int(at['caught_score'] - at['caught_baseline']):+,} vs baseline")
        lift = at["caught_score"] / at["caught_baseline"] if at["caught_baseline"] else float("nan")
        c3.metric("Lift over baseline", f"{lift:.1f}x")

        metric = st.radio("Show", ["Detection rate (% of all laundering caught)", "Precision (% of queue that is laundering)"],
                          horizontal=True)
        if metric.startswith("Detection"):
            long = curve.melt("daily_capacity", ["Our risk score", "Baseline: most transactions"], "method", "pct")
            y_title = "% of laundering account-days caught"
        else:
            long = curve.rename(columns={"precision_score": "Our risk score",
                                         "precision_baseline": "Baseline: most transactions"}) \
                        .melt("daily_capacity", ["Our risk score", "Baseline: most transactions"], "method", "pct")
            y_title = "% of reviewed accounts that are laundering"
        line = alt.Chart(long).mark_line(point=True).encode(
            x=alt.X("daily_capacity:Q", title="Accounts reviewed per day (top N)"),
            y=alt.Y("pct:Q", title=y_title),
            color=alt.Color("method:N", title=None, legend=alt.Legend(orient="bottom")),
            tooltip=["daily_capacity", "method", alt.Tooltip("pct:Q", format=".2f")])
        rule = alt.Chart(pd.DataFrame({"x": [capacity]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
        st.altair_chart(line + rule, width="stretch")
        st.caption(f"{n_days} day(s), {total:,} laundering account-days in total. "
                   "Look for where the curve flattens: extra reviews stop catching much more. "
                   "Baseline ranks accounts by transaction count only.")

        with st.expander("Stored results from the scoring job (capacity_summary)"):
            st.dataframe(run_query("SELECT * FROM capacity_summary ORDER BY daily_capacity"),
                         width="stretch", hide_index=True)

# ---------------------------------------------------------------- 3. score distribution
with tab_dist:
    dist = run_query(f"""
        SELECT FLOOR(r.risk_score / 2.5) * 2.5 AS score_bin,
               COALESCE(l.account_day_is_laundering, 0) AS is_laundering, COUNT(*) AS accounts
        FROM risk_rankings r
        LEFT JOIN account_labels l
          ON l.account_key = r.account_key AND l.profile_date = r.profile_date
        WHERE r.profile_date = '{day}'
        GROUP BY 1, 2""")
    dist["group"] = dist["is_laundering"].map({1: "Laundering", 0: "Normal"})
    dist["share"] = 100 * dist["accounts"] / dist.groupby("group")["accounts"].transform("sum")
    cutoff = float(queue["risk_score"].min()) if len(queue) else None

    mode = st.radio("Y axis", ["Share within each group", "Account count (log scale)"], horizontal=True)
    y = (alt.Y("share:Q", title="% of accounts in group", stack=None) if mode.startswith("Share")
         else alt.Y("accounts:Q", title="Accounts", scale=alt.Scale(type="log"), stack=None))
    dist["bin_end"] = dist["score_bin"] + 2.5
    bars = alt.Chart(dist).mark_bar(opacity=0.55).encode(
        x=alt.X("score_bin:Q", title="Risk score", scale=alt.Scale(domain=[0, 100])), x2="bin_end:Q",
        y=y,
        color=alt.Color("group:N", title=None, legend=alt.Legend(orient="bottom")),
        tooltip=["group", "score_bin", "accounts", alt.Tooltip("share:Q", format=".2f")])
    chart = bars
    if cutoff is not None:
        chart = bars + alt.Chart(pd.DataFrame({"x": [cutoff]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
    st.altair_chart(chart, width="stretch")
    st.caption(f"{day}. Dashed line = lowest score that still makes the top {capacity} queue. "
               "A good score pushes laundering accounts to the right of normal ones.")

# ---------------------------------------------------------------- 4. drill-down
with tab_drill:
    pick = st.selectbox("Account from today's queue", queue["account_key"].tolist() if len(queue) else [],
                        format_func=lambda k: f"#{int(queue.loc[queue.account_key == k, 'daily_rank'].iloc[0])}  {k}")
    typed = st.text_input("Or type any account key (bank:account)", "")
    key = typed.strip() or pick
    if key and not re.fullmatch(r"[A-Za-z0-9:]+", key):
        st.error("Account key can only contain letters, digits and ':'.")
        key = None

    if key:
        hist = run_query(f"""
            SELECT r.profile_date, r.daily_rank, r.daily_active_accounts, r.risk_score,
                   {', '.join('r.' + c for c in POINT_COLS)},
                   COALESCE(l.account_day_is_laundering, 0) AS is_laundering
            FROM risk_rankings r
            LEFT JOIN account_labels l
              ON l.account_key = r.account_key AND l.profile_date = r.profile_date
            WHERE r.account_key = '{key}'
            ORDER BY r.profile_date""")
        prof = run_query(f"SELECT * FROM account_profiles WHERE account_key = '{key}' AND profile_date = '{day}'")

        if hist.empty:
            st.warning("No scores found for this account.")
        else:
            hist["profile_date"] = hist["profile_date"].astype(str)
            today = hist[hist["profile_date"] == day]
            row = today.iloc[0] if len(today) else hist.iloc[-1]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Day shown", row["profile_date"])
            c2.metric("Risk score", f"{row['risk_score']:.1f}")
            c3.metric("Daily rank", f"{int(row['daily_rank']):,} of {int(row['daily_active_accounts']):,}")
            if show_truth:
                c4.metric("Laundering that day", "Yes" if row["is_laundering"] else "No")

            left, right = st.columns(2)
            with left:
                st.markdown("**Why flagged: points per behaviour**")
                pts = pd.DataFrame({"behaviour": [BEHAVIOURS[c][0] for c in POINT_COLS],
                                    "points": [row[c] for c in POINT_COLS],
                                    "max_points": [BEHAVIOURS[c][1] for c in POINT_COLS]})
                base = alt.Chart(pts).encode(y=alt.Y("behaviour:N", sort=None, title=None))
                st.altair_chart(
                    base.mark_bar(color="#e5e7eb").encode(x=alt.X("max_points:Q", title="Points (grey = weight)"))
                    + base.mark_bar().encode(x="points:Q", tooltip=["behaviour", "points", "max_points"]),
                    width="stretch")
            with right:
                st.markdown("**Risk score across days**")
                st.altair_chart(
                    alt.Chart(hist).mark_line(point=True).encode(
                        x=alt.X("profile_date:O", title=None), y=alt.Y("risk_score:Q", title="Risk score",
                                                                        scale=alt.Scale(domain=[0, 100])),
                        color=alt.Color("is_laundering:N", title="Laundering") if show_truth else alt.value("#4c78a8"),
                        tooltip=["profile_date", "risk_score", "daily_rank"]),
                    width="stretch")

            st.markdown("**Behavioural indicators (raw profile)**")
            if prof.empty:
                st.info(f"No profile row for {day}.")
            else:
                p = prof.iloc[0]
                ind = pd.DataFrame([
                    ("Transactions (in / out)", f"{int(p.txn_count)} ({int(p.incoming_txn_count)} / {int(p.outgoing_txn_count)})"),
                    ("Amount USD (in / out)", f"${p.incoming_amount_usd:,.0f} / ${p.outgoing_amount_usd:,.0f}"),
                    ("ACH share", f"{p.ach_share:.0%}"),
                    ("Cross-border share", f"{p.cross_border_share:.0%}"),
                    ("Fan-out (accounts paid)", str(int(p.fan_out))),
                    ("Fan-in (accounts paying in)", str(int(p.fan_in))),
                    ("Amount band share (p50 to p95)", f"{p.amount_band_share:.0%}"),
                    ("Pass-through within 24h", f"{p.pass_through_share_24h:.0%}"),
                    ("Activity spike (vs 7-day avg)", f"{p.activity_spike_ratio:.2f}x"),
                ], columns=["Indicator", "Value"])
                st.dataframe(ind, width="stretch", hide_index=True)
