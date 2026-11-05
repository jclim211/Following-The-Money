"""
BQ1 | Which accounts should investigators review first?

Runs the stored queries in S3 on Athena and reads the result CSVs from S3 (Glue database aml_curated):
  risk_rankings, account_labels, account_profiles, capacity_summary

Tabs: investigator queue (with new vs repeat alerts), capacity vs detection
(with a recommended daily cut-off), which indicators matter (drop-one test),
score distribution and account drill-down.
"""
import re

import altair as alt
import pandas as pd
import streamlit as st

from common import theme
from common.athena import run_query
import bq1_data as bd

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


# ---------------------------------------------------------------- layout
theme.page_header("Which accounts should investigators review first?",
                  "Athena results read from S3 (aml_curated). Risk score 0 to 100 = sum of weight x behaviour score.",
                  eyebrow="BQ1 · Account risk")

all_days = run_query("available_dates")["profile_date"].astype(str).tolist()

with st.sidebar:
    st.header("Controls")
    day = st.selectbox("Day for queue and drill-down", all_days, index=len(all_days) - 1)
    capacity = st.slider("Daily investigator capacity (accounts)", 50, 1000, 100, step=50)
    eval_days = st.multiselect("Days for the capacity curve", all_days, default=all_days,
                               help="Pick a held-out set of days to report results on unseen days.")
    show_truth = st.toggle("Show ground truth (IsLaundering)", value=True,
                           help="Labels are only used to evaluate the score, never to compute it.")
    st.caption(f"{len(all_days)} days loaded: {all_days[0]} to {all_days[-1]}")
date_list = ", ".join(repr(d) for d in eval_days)  # values come from the Athena date list

tab_queue, tab_curve, tab_ind, tab_dist, tab_drill = st.tabs(
    ["Investigator queue", "Capacity vs detection", "Which indicators matter", "Score distribution",
     "Account drill-down"])

# ---------------------------------------------------------------- 1. queue
with tab_queue:
    queue = run_query("queue_top_accounts", {"profile_date": day, "top_n": capacity})
    queue["why_flagged"] = queue.apply(why_flagged, axis=1)

    # New vs repeat: was this account already in the top N on an earlier day?
    prior = run_query("queue_prior_flag_days", {"profile_date": day, "top_n": capacity},
                      text_columns=("account_key", "first_flagged"))
    queue = queue.merge(prior, on="account_key", how="left") if len(prior) else queue.assign(
        prior_flag_days=0, first_flagged=None)
    queue["prior_flag_days"] = queue["prior_flag_days"].fillna(0).astype(int)
    queue["alert_status"] = queue["prior_flag_days"].map(
        lambda n: "New" if n == 0 else f"Repeat ({n} earlier day{'s' if n > 1 else ''})")
    n_new = int((queue["prior_flag_days"] == 0).sum())

    caught = int(queue["is_laundering"].sum())
    total_day = int(run_query("kpi_day_laundering_total", {"profile_date": day})["t"].iloc[0])
    active = int(queue["daily_active_accounts"].iloc[0]) if len(queue) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active accounts that day", f"{active:,}")
    c2.metric("Accounts in queue", f"{len(queue):,}",
              f"{n_new:,} new, {len(queue) - n_new:,} repeat", delta_color="off",
              help=f"Repeat = already in the top {capacity} on an earlier day.")
    c3.metric("Lowest score in queue", f"{queue['risk_score'].min():.1f}" if len(queue) else "n/a")
    if show_truth:
        c4.metric("Laundering caught (precision)", f"{caught} ({100 * caught / max(len(queue), 1):.1f}%)",
                  help=f"{total_day:,} laundering accounts active that day, so detection rate is "
                       f"{100 * caught / max(total_day, 1):.2f}%")

    cols = ["daily_rank", "account_key", "risk_score", "why_flagged", "alert_status", "txn_count",
            "total_amount_usd"]
    if show_truth:
        cols.append("is_laundering")
    st.dataframe(
        queue[cols], width="stretch", hide_index=True, height=420,
        column_config={
            "daily_rank": "Rank", "account_key": "Account (bank:account)",
            "risk_score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100, format="%.1f"),
            "why_flagged": "Why flagged (top behaviours, points)",
            "alert_status": st.column_config.TextColumn(
                "Alert status", help=f"Repeat = account was already in the top {capacity} on an earlier day"),
            "txn_count": "Txns", "total_amount_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
            "is_laundering": st.column_config.CheckboxColumn("Laundering"),
        })

    left_c, right_c = st.columns(2, gap="medium")
    with right_c:
        theme.section(f"New vs repeat alerts, top {capacity}", "across all days", "autorenew", theme.PURPLE)
        trend = run_query("queue_new_vs_repeat", {"top_n": capacity}, text_columns=("profile_date",))
        long = trend.melt("profile_date", ["new_accounts", "repeat_accounts"], "status", "accounts")
        long["status"] = long["status"].map({"new_accounts": "New", "repeat_accounts": "Repeat"})
        st.altair_chart(
            alt.Chart(long).mark_bar().encode(
                x=alt.X("profile_date:O", title=None,
                        axis=alt.Axis(labelAngle=-45, labelExpr="slice(datum.label, 5)")),   # 09-01, not 2022-09-01
                y=alt.Y("accounts:Q", title="Accounts"),
                color=alt.Color("status:N", title=None, legend=alt.Legend(orient="bottom"),
                                scale=alt.Scale(range=[theme.BLUE, theme.PURPLE])),
                tooltip=["profile_date", "status", "accounts"]).properties(height=theme.CHART_H - 60),
            width="stretch")
        rep_total, new_total = int(trend["repeat_accounts"].sum()), int(trend["new_accounts"].sum())
        msg = (f"Over {len(trend)} days, {rep_total:,} of {rep_total + new_total:,} queue slots "
               f"({100 * rep_total / max(rep_total + new_total, 1):.1f}%) went to accounts already flagged earlier.")
        if show_truth:
            nl, rl = int(trend["new_laundering"].sum()), int(trend["repeat_laundering"].sum())
            msg += (f" Laundering rate: {100 * nl / max(new_total, 1):.1f}% for new alerts, "
                    f"{100 * rl / max(rep_total, 1):.1f}% for repeat alerts.")
        st.caption(msg + " Repeat alerts can be routed to the analyst who already reviewed the account.")

    with left_c:
        theme.section(f"What drives the top {capacity}", "average points per behaviour", "tune", theme.BLUE)
        drivers = queue[POINT_COLS].mean().rename(lambda c: BEHAVIOURS[c][0]).reset_index()
        drivers.columns = ["behaviour", "avg_points"]
        drivers["max_points"] = [BEHAVIOURS[c][1] for c in POINT_COLS]
        st.altair_chart(
            alt.Chart(drivers).mark_bar().encode(
                x=alt.X("avg_points:Q", title="Average points (bar) out of the weight"),
                y=alt.Y("behaviour:N", sort="-x", title=None),
                tooltip=["behaviour", alt.Tooltip("avg_points:Q", format=".1f"), "max_points"]
            ).properties(height=theme.CHART_H - 40),
            width="stretch")

# ---------------------------------------------------------------- 2. capacity curve
with tab_curve:
    if not eval_days:
        st.info("Pick at least one day in the sidebar.")
    else:
        curve = run_query("capacity_vs_baseline", {"date_list": date_list})
        total = int(run_query("kpi_period_laundering_total", {"date_list": date_list})["t"].iloc[0])
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

        cl, cr = st.columns(2, gap="medium")
        with cl:
            theme.section("Capacity vs detection", "our risk score against the transaction-count baseline", "show_chart", theme.BLUE)
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
                color=alt.Color("method:N", title=None, legend=alt.Legend(orient="bottom"),
                                scale=alt.Scale(range=[theme.GREY, theme.BLUE])),
                tooltip=["daily_capacity", "method", alt.Tooltip("pct:Q", format=".2f")])
            rule = alt.Chart(pd.DataFrame({"x": [capacity]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
            st.altair_chart((line + rule).properties(height=theme.CHART_H - 20), width="stretch")
            st.caption(f"{n_days} day(s), {total:,} laundering account-days in total. "
                       "Look for where the curve flattens: extra reviews stop catching much more. "
                       "Baseline ranks accounts by transaction count only.")

        with cr:
            theme.section("Recommended daily alert limit", "where extra reviews stop paying off", "flag", theme.ORANGE)
            knee = bd.knee_capacity(curve["daily_capacity"], curve["caught_score"])
            marg = bd.marginal_yield(curve["daily_capacity"], curve["caught_score"], n_days)
            min_per_100 = st.slider(
                "Keep adding reviews while each extra 100 reviews still finds at least this many laundering accounts",
                1, 40, 10,
                help="A compliance manager's rule: what hit rate makes an extra review worth the investigator's time?")
            by_rule = bd.threshold_capacity(curve["daily_capacity"], curve["caught_score"], n_days, min_per_100)
            k_row = curve[curve["daily_capacity"] == knee].iloc[0]
            r_row = curve[curve["daily_capacity"] == by_rule].iloc[0]
            c1, c2 = st.columns(2)
            c1.metric("Knee of the curve", f"{knee:,} per day",
                      f"catches {k_row['Our risk score']:.1f}% of laundering, precision {k_row['precision_score']:.1f}%",
                      delta_color="off",
                      help="Kneedle method: the point furthest above the straight line from the first to the last "
                           "capacity. After it, each extra review adds noticeably less.")
            c2.metric(f"By your rule ({min_per_100} per 100 extra)", f"{by_rule:,} per day",
                      f"catches {r_row['Our risk score']:.1f}% of laundering, precision {r_row['precision_score']:.1f}%",
                      delta_color="off")
            marg = marg.dropna()
            bars = alt.Chart(marg).mark_bar().encode(
                x=alt.X("daily_capacity:Q", title="Accounts reviewed per day (top N)"),
                y=alt.Y("found_per_100_extra:Q", title="Laundering found per 100 extra reviews"),
                color=alt.condition(alt.datum.found_per_100_extra >= min_per_100, alt.value(theme.S_PURPLE),
                                    alt.value(theme.FAINT)),
                tooltip=["daily_capacity", alt.Tooltip("found_per_100_extra:Q", format=".1f")])
            thr = alt.Chart(pd.DataFrame({"y": [min_per_100]})).mark_rule(strokeDash=[4, 4]).encode(y="y:Q")
            knee_rule = alt.Chart(pd.DataFrame({"x": [knee]})).mark_rule(color=theme.S_RED).encode(x="x:Q")
            st.altair_chart((bars + thr + knee_rule).properties(height=theme.CHART_H - 60), width="stretch")
            st.caption("Each bar is the extra laundering found by reviewing 50 more accounts a day, scaled per 100 "
                       "reviews. Grey bars fall below your rule. Red line = knee of the detection curve.")

        with st.expander("Stored results from the scoring job (capacity_summary)"):
            st.dataframe(run_query("capacity_summary"),
                         width="stretch", hide_index=True)

# ---------------------------------------------------------------- 3. which indicators matter
with tab_ind:
    st.subheader("Which behavioural indicators matter most?")
    st.caption(f"Drop-one test at {capacity} accounts per day on the days picked in the sidebar. For each "
               "behaviour we re-rank every account without that behaviour's points and count how much "
               "laundering the queue still catches. A big drop means the behaviour matters.")
    run_key = f"drop_one_{capacity}_{','.join(eval_days)}"
    if not eval_days:
        st.info("Pick at least one day in the sidebar.")
    elif not st.session_state.get(run_key) and not st.button(
            f"Run the drop-one test at {capacity}/day on {len(eval_days)} day(s)", type="primary",
            help="Re-ranks every account 14 times, so it takes about 1.5 minutes on all 16 days. "
                 "The result is cached for an hour."):
        st.info("This test re-ranks about 15 million account-days, so it runs only when you click the button.")
    else:
        st.session_state[run_key] = True
        drop = run_query("indicator_contribution", {"date_list": date_list, "top_n": capacity},
                         folder="bq1/analysis").iloc[0]
        all_caught = int(drop["caught_all"])
        res = pd.DataFrame([{
            "behaviour": BEHAVIOURS[c][0], "weight": BEHAVIOURS[c][1],
            "caught_without": int(drop[f"wo_{c}"]), "caught_alone": int(drop[f"only_{c}"])}
            for c in POINT_COLS])
        res["lost_when_removed"] = all_caught - res["caught_without"]
        res["change_pct"] = -100 * res["lost_when_removed"] / max(all_caught, 1)

        c1, c2 = st.columns(2)
        c1.metric(f"Laundering caught with all 7 behaviours ({len(eval_days)} days)", f"{all_caught:,}")
        top = res.sort_values("lost_when_removed", ascending=False).iloc[0]
        c2.metric("Most important behaviour", top["behaviour"],
                  f"removing it loses {int(top['lost_when_removed']):,} catches ({top['change_pct']:.1f}%)",
                  delta_color="off")

        res["effect"] = res["lost_when_removed"].map(lambda v: "Helps" if v > 0 else ("Hurts" if v < 0 else "No effect"))
        il, ir = st.columns([1, 1.2], gap="medium")
        il.altair_chart(
            alt.Chart(res).mark_bar().encode(
                x=alt.X("lost_when_removed:Q", title="Laundering catches lost when this behaviour is removed"),
                y=alt.Y("behaviour:N", sort="-x", title=None),
                color=alt.Color("effect:N", title=None, legend=alt.Legend(orient="bottom"),
                                scale=alt.Scale(domain=["Helps", "No effect", "Hurts"],
                                                range=[theme.S_PURPLE, theme.FAINT, theme.S_RED])),
                tooltip=["behaviour", "weight", "caught_without", "lost_when_removed",
                         alt.Tooltip("change_pct:Q", format=".1f")]).properties(height=theme.CHART_H - 40),
            width="stretch")
        ir.dataframe(
            res[["behaviour", "weight", "caught_without", "lost_when_removed", "change_pct", "caught_alone"]],
            width="stretch", hide_index=True,
            column_config={
                "behaviour": "Behaviour", "weight": "Weight",
                "caught_without": st.column_config.NumberColumn("Caught without it", format="%d"),
                "lost_when_removed": st.column_config.NumberColumn("Lost when removed", format="%d"),
                "change_pct": st.column_config.NumberColumn("Change", format="%.1f%%"),
                "caught_alone": st.column_config.NumberColumn(
                    "Caught using only this behaviour", format="%d",
                    help="Ranking by this one behaviour. Ties (for example many accounts with 100% ACH) "
                         "are broken by account key, so treat this as a rough guide."),
            })
        st.caption("Red bars mean the queue catches more laundering without that behaviour, so its weight "
                   "could be lowered. Labels are used here only to evaluate, never to score.")

# ---------------------------------------------------------------- 4. score distribution
with tab_dist:
    dist = run_query("score_distribution", {"profile_date": day})
    dist["group"] = dist["is_laundering"].map({1: "Laundering", 0: "Normal"})
    dist["share"] = 100 * dist["accounts"] / dist.groupby("group")["accounts"].transform("sum")
    cutoff = float(queue["risk_score"].min()) if len(queue) else None

    dl, dr = st.columns([1.4, 1], gap="medium")
    mode = dr.radio("Y axis", ["Share within each group", "Account count (log scale)"], horizontal=True)
    y = (alt.Y("share:Q", title="% of accounts in group", stack=None) if mode.startswith("Share")
         else alt.Y("accounts:Q", title="Accounts", scale=alt.Scale(type="log"), stack=None))
    dist["bin_end"] = dist["score_bin"] + 2.5
    bars = alt.Chart(dist).mark_bar(opacity=0.55).encode(
        x=alt.X("score_bin:Q", title="Risk score", scale=alt.Scale(domain=[0, 100])), x2="bin_end:Q",
        y=y,
        color=alt.Color("group:N", title=None, legend=alt.Legend(orient="bottom"),
                        scale=alt.Scale(domain=["Laundering", "Normal"], range=[theme.LAUNDERING, theme.NORMAL])),
        tooltip=["group", "score_bin", "accounts", alt.Tooltip("share:Q", format=".2f")])
    chart = bars
    if cutoff is not None:
        chart = bars + alt.Chart(pd.DataFrame({"x": [cutoff]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
    dl.altair_chart(chart.properties(height=theme.CHART_H), width="stretch")
    dr.caption(f"{day}. Dashed line = lowest score that still makes the top {capacity} queue. "
               "A good score pushes laundering accounts to the right of normal ones.")

# ---------------------------------------------------------------- 5. drill-down
with tab_drill:
    pick = st.selectbox("Account from today's queue", queue["account_key"].tolist() if len(queue) else [],
                        format_func=lambda k: f"#{int(queue.loc[queue.account_key == k, 'daily_rank'].iloc[0])}  {k}")
    typed = st.text_input("Or type any account key (bank:account)", "")
    key = typed.strip() or pick
    if key and not re.fullmatch(r"[A-Za-z0-9:]+", key):
        st.error("Account key can only contain letters, digits and ':'.")
        key = None

    if key:
        hist = run_query("account_score_history", {"account_key": key})
        prof = run_query("account_profile_detail", {"account_key": key, "profile_date": day})

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
                    base.mark_bar(color=theme.LINE).encode(x=alt.X("max_points:Q", title="Points (grey = weight)"))
                    + base.mark_bar().encode(x="points:Q", tooltip=["behaviour", "points", "max_points"]),
                    width="stretch")
            with right:
                st.markdown("**Risk score across days**")
                st.altair_chart(
                    alt.Chart(hist).mark_line(point=True).encode(
                        x=alt.X("profile_date:O", title=None), y=alt.Y("risk_score:Q", title="Risk score",
                                                                        scale=alt.Scale(domain=[0, 100])),
                        color=alt.Color("is_laundering:N", title="Laundering") if show_truth else alt.value(theme.S_PURPLE),
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
