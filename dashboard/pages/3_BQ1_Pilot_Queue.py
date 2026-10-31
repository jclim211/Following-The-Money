"""BQ1 AML investigator dashboard (IS459 Group 7).

Reads the two small curated exports from Athena (see README) and shows:
  1. the daily top-100 investigator queue, with an explanation per account;
  2. the capacity trade-off behind the 100-reviews-per-day pilot;
  3. methodology, limitations and data checks.

Page 3 of the shared dashboard (dashboard/Home.py). Data: dashboard/data_bq1/.
Merged from BQ1_Streamlit_Dashboard_Merged_v2 (v2.1, see BQ1_PILOT_CHANGELOG.md).
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # bq1_data.py sits in dashboard/
import bq1_data as bd  # noqa: E402

DATA_DIR = Path(os.environ.get("BQ1_DATA_DIR", Path(__file__).resolve().parents[1] / "data_bq1"))

# Palette: one series colour + one highlight colour (both checked for contrast
# and colour-blind separation), plus neutral inks for text, tracks and grid.
SERIES = "#2E6DB4"     # navy-blue: every ordinary mark
ACCENT = "#0FA3A3"     # teal: the selected account / recommended capacity
TRACK = "#E3E8EF"      # light grey: "maximum possible" bars
INK = "#1B2A3A"
MUTED = "#5B6675"
GRID = "#EDF0F4"
PLOT_CONFIG = {"displayModeBar": False}

# Country name (as in the export) -> ISO 3166 code, shown as a flag image in the queue table.
# Images, not emoji, because Windows browsers show flag emoji as two letters.
# Fixed 40x30 images so every flag (and badge) is the same size; w40 heights vary 20 to 40px.
# Covers every value of aml_clean.banks.country (33 countries + "Crypto", checked 2026-10-31).
COUNTRY_ISO = {
    "Australia": "au", "Austria": "at", "Belgium": "be", "Brazil": "br", "Canada": "ca", "China": "cn",
    "Croatia": "hr", "Cyprus": "cy", "Estonia": "ee", "Finland": "fi", "France": "fr", "Germany": "de",
    "Greece": "gr", "India": "in", "Ireland": "ie", "Israel": "il", "Italy": "it", "Japan": "jp",
    "Latvia": "lv", "Lithuania": "lt", "Luxembourg": "lu", "Malta": "mt", "Mexico": "mx",
    "Netherlands": "nl", "Portugal": "pt", "Russia": "ru", "Saudi Arabia": "sa", "Slovakia": "sk",
    "Slovenia": "si", "Spain": "es", "Switzerland": "ch", "UK": "gb", "US": "us",
}


def _badge(text, bg, fg="#FFFFFF"):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30" viewBox="0 0 40 30">'
           f'<rect width="40" height="30" rx="4" fill="{bg}"/><text x="20" y="21" font-family="Arial" '
           f'font-size="16" font-weight="bold" fill="{fg}" text-anchor="middle">{text}</text></svg>')
    return "data:image/svg+xml;utf8," + quote(svg)


CRYPTO_BADGE = _badge("&#8383;", "#F2A900")   # Bitcoin sign: the dataset's crypto banks have no country
UNKNOWN_BADGE = _badge("?", "#9CA3AF")         # any country not in COUNTRY_ISO


def flag_url(country):
    if country == "Crypto":
        return CRYPTO_BADGE
    iso = COUNTRY_ISO.get(country)
    return f"https://flagcdn.com/40x30/{iso}.png" if iso else UNKNOWN_BADGE

st.set_page_config(page_title="BQ1 AML Investigator Queue", page_icon="🏦", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
      h1 {color: #12263F; font-size: 1.9rem !important; margin-bottom: 0 !important;}
      .subtitle {color: #5B6675; margin-top: .2rem; margin-bottom: 1rem;}
      div[data-testid="stMetricValue"] {color: #12263F;}
      .why {background: #F2F7FB; border-left: 4px solid #0FA3A3; padding: .8rem 1rem;
            border-radius: 6px; color: #1B2A3A; line-height: 1.5;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ST_VERSION = tuple(int(p) for p in st.__version__.split(".")[:2] if p.isdigit())


def full_width(fn, *args, **kwargs):
    """Call a Streamlit element at full width on both old and new Streamlit."""
    if _ST_VERSION >= (1, 46):
        try:
            return fn(*args, width="stretch", **kwargs)
        except TypeError:
            pass
    return fn(*args, use_container_width=True, **kwargs)


def show(fig: go.Figure) -> None:
    full_width(st.plotly_chart, fig, config=PLOT_CONFIG)


def style(fig: go.Figure, title: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0, "xanchor": "left", "font": {"size": 15, "color": INK}},
        template="plotly_white",
        height=height,
        margin={"l": 10, "r": 20, "t": 50, "b": 10},
        font={"color": MUTED, "size": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="white",
        showlegend=False,
        hoverlabel={"bgcolor": "white", "font_size": 12, "font_color": INK},
        barcornerradius=4,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor="#C9D1DB", title_font={"size": 12})
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor="#C9D1DB", title_font={"size": 12})
    return fig


def money(x: float) -> str:
    if x >= 1e9:
        return f"${x / 1e9:,.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:,.2f}M"
    return f"${x:,.0f}"


def account_label(row) -> str:
    return f"#{int(row['daily_rank'])} · {row['account_key']}"


@st.cache_data(show_spinner=False)
def load(data_dir: str):
    queue = bd.load_queue(Path(data_dir) / bd.QUEUE_FILE)
    capacity = bd.load_capacity(Path(data_dir) / bd.CAPACITY_FILE)
    return queue, capacity, bd.run_checks(queue, capacity)


# ---------------------------------------------------------------------------
# Load data (stop with clear instructions if the exports are missing)
# ---------------------------------------------------------------------------
missing = [f for f in (bd.QUEUE_FILE, bd.CAPACITY_FILE) if not (DATA_DIR / f).exists()]
if missing:
    st.title("BQ1 AML Investigator Queue")
    st.error(
        f"Missing data file(s) in `{DATA_DIR}`: {', '.join(missing)}.\n\n"
        "Export them from Athena (README, step 1) and save them into the `data/` folder."
    )
    st.stop()

try:
    queue, capacity, checks = load(str(DATA_DIR))
except bd.SchemaError as err:
    st.title("BQ1 AML Investigator Queue")
    st.error(f"The exported CSV does not match the expected Athena schema.\n\n{err}")
    st.stop()

failed = [c for c in checks if not c.passed]
dates = sorted(queue["profile_date"].unique(), reverse=True)
latest = dates[0]
max_available = bd.available_capacity(queue)

# ---------------------------------------------------------------------------
# Header + sidebar filters
# ---------------------------------------------------------------------------
st.title("🏦 BQ1 · Daily AML Investigator Queue")
st.markdown(
    '<div class="subtitle">Which accounts should a fixed-capacity investigation team review first? '
    "Accounts are ranked each day by an explainable 100-point behavioural risk score. "
    "<b>A high score means review first, not proven laundering.</b></div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Filters")
    date = st.selectbox(
        "Review date",
        dates,
        index=0,
        format_func=lambda d: pd.Timestamp(d).strftime("%d %b %Y") + ("  (latest)" if d == latest else ""),
    )
    date = pd.Timestamp(date)
    day_rows = queue[queue["profile_date"] == date]

    day_max_rank = int(day_rows["daily_rank"].max())
    capacity_options = [c for c in [100, 500, 1000] if c <= day_max_rank]
    if not capacity_options:
        capacity_options = [day_max_rank]
    daily_capacity = st.select_slider(
        "Daily investigator capacity",
        options=capacity_options,
        value=capacity_options[0],
        help="Show the highest-ranked N accounts for the selected date.",
    )
    capacity_rows = day_rows[day_rows["daily_rank"] <= daily_capacity]

    if bd.COUNTRY_COLUMN in capacity_rows.columns:
        countries = st.multiselect(
            "Account country",
            sorted(capacity_rows[bd.COUNTRY_COLUMN].dropna().unique()),
            placeholder="All countries",
            help="Country recorded for the account side of its transactions.",
        )
    else:
        countries = []
        st.caption("Country filter will appear when `account_country` is included in the export.")

    country_rows = capacity_rows
    if countries:
        country_rows = country_rows[country_rows[bd.COUNTRY_COLUMN].isin(countries)]

    banks = st.multiselect(
        "Bank ID", sorted(country_rows["bank_id"].dropna().unique(), key=lambda b: (len(b), b)),
        placeholder="All banks",
    )
    rank_range = st.slider("Rank range", 1, daily_capacity, (1, daily_capacity))

    if bd.LABEL_COLUMN in queue.columns:
        show_ground_truth = st.toggle(
            "Show ground truth",
            value=False,
            help=("Evaluation mode only. The label was joined after scoring and ranking and "
                  "would not be known during a real investigation."),
        )
    else:
        show_ground_truth = False
        st.caption("Ground-truth toggle will appear when the evaluation label is included in the export.")

    st.divider()
    if failed:
        st.error(f"Data checks: {len(failed)} of {len(checks)} failed. See the Methodology tab.")
    else:
        st.success(f"Data checks: all {len(checks)} passed")
    if max_available < 1000:
        st.warning(
            f"This export contains only the top {max_available:,} ranks per day. "
            "Export ranks 1-1,000 to enable the 500 and 1,000 capacity options."
        )
    st.caption(
        "Source: IBM Transactions for AML (HI-Medium, synthetic). "
        "Pipeline: S3 → Glue → EMR Serverless (Spark) → S3 Parquet → Athena → this app."
    )

selected = capacity_rows[capacity_rows["daily_rank"].between(*rank_range)]
if countries:
    selected = selected[selected[bd.COUNTRY_COLUMN].isin(countries)]
if banks:
    selected = selected[selected["bank_id"].isin(banks)]
selected = selected.sort_values("daily_rank")

tab_queue, tab_capacity, tab_method = st.tabs(
    ["Daily Investigator Queue", "Capacity Trade-off", "Methodology and Limitations"]
)

# ---------------------------------------------------------------------------
# Tab 1: Daily Investigator Queue
# ---------------------------------------------------------------------------
def render_queue_tab() -> None:
    filtered = rank_range != (1, daily_capacity) or bool(countries) or bool(banks)
    st.markdown(
        f"#### Top {daily_capacity:,} queue for {date.strftime('%d %B %Y')}"
        + (" · filtered view" if filtered else "")
    )
    if selected.empty:
        st.warning("No accounts match these filters. Widen the rank range or clear the bank filter.")
        return

    k = bd.day_kpis(selected)
    active_accounts = bd.active_accounts_for_day(day_rows)
    cols = st.columns(5)
    tiles = [
        (f"Active accounts on {date.strftime('%d %b %Y')}",
         f"{active_accounts:,}" if active_accounts is not None else "N/A",
         "All account profiles created that day" if active_accounts is not None else "Add daily_active_accounts to the export"),
        ("Accounts in queue", f"{k['queue_size']:,}",
         f"Selected capacity: {daily_capacity:,}" if not filtered else f"Capacity {daily_capacity:,}, after filters"),
        ("Highest risk score", f"{k['highest']:.2f}", "Out of 100"),
        ("Lowest score in queue", f"{k['cutoff']:.2f}", "Current cut-off score"),
        (("Ground-truth hits" if show_ground_truth else "Value in queue"),
         (f"{k.get('laundering_hits', 0):,}" if show_ground_truth else money(k["value"])),
         ("Labelled laundering account-days" if show_ground_truth else "Total USD moved by these accounts")),
    ]
    for col, (label, value, help_txt) in zip(cols, tiles):
        with col.container(border=True):
            st.metric(label, value)
            st.caption(help_txt)

    # Account picker drives the highlight in the charts and the explanation panel.
    names = {
        r.account_key: f"#{int(r.daily_rank)} · {r.account_key}  ·  score {r.risk_score:.2f}"
        for r in selected.itertuples()
    }
    pick = st.selectbox(
        "Explain an account (highlighted in teal below)",
        list(names),
        index=0,
        key=f"account_{date.date()}",
        format_func=names.get,
    )
    row = selected[selected["account_key"] == pick].iloc[0]

    left, right = st.columns(2)

    # Top 10 by score
    top = selected.head(10).copy()
    top["label"] = top.apply(account_label, axis=1)
    colors = [ACCENT if key == pick else SERIES for key in top["account_key"]]
    fig = go.Figure(
        go.Bar(
            x=top["risk_score"], y=top["label"], orientation="h",
            marker={"color": colors},
            text=top["risk_score"].map(lambda s: f"{s:.2f}"), textposition="outside",
            textfont={"color": INK},
            customdata=top[["bank_id", "txn_count", "total_amount_usd"]],
            hovertemplate="<b>%{y}</b><br>Risk score %{x:.2f}<br>Bank %{customdata[0]}"
            "<br>Transactions %{customdata[1]}<br>Value $%{customdata[2]:,.2f}<extra></extra>",
        )
    )
    style(fig, "Top 10 accounts by risk score", height=380)
    fig.update_xaxes(range=[0, 105], title="Risk score (0-100)")
    fig.update_yaxes(autorange="reversed", title=None, gridcolor="rgba(0,0,0,0)")
    with left:
        show(fig)

    # Value vs score scatter
    is_pick = selected["account_key"] == pick
    fig = go.Figure()
    for mask, color, size, name in [(~is_pick, SERIES, 9, "Queue"), (is_pick, ACCENT, 15, "Selected")]:
        part = selected[mask]
        fig.add_trace(
            go.Scatter(
                x=part["total_amount_usd"], y=part["risk_score"], mode="markers", name=name,
                marker={"color": color, "size": size, "opacity": 0.8 if name == "Queue" else 1,
                        "line": {"color": "white", "width": 2}},
                customdata=part[["account_key", "bank_id", "daily_rank"]],
                hovertemplate="<b>#%{customdata[2]} · %{customdata[0]}</b><br>Bank %{customdata[1]}"
                "<br>Risk score %{y:.2f}<br>Value $%{x:,.2f}<extra></extra>",
            )
        )
    style(fig, "Transaction value vs risk score (teal = selected account)", height=380)
    fig.update_xaxes(type="log", title="Total USD moved that day (log scale)")
    fig.update_yaxes(title="Risk score")
    with right:
        show(fig)

    # Explanation for the chosen account
    st.markdown("#### Why is this account in the queue?")
    left, right = st.columns([1.15, 1])
    comp = bd.component_table(row)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=comp["max_points"], y=comp["component"], orientation="h",
                         marker={"color": TRACK}, hoverinfo="skip"))
    fig.add_trace(
        go.Bar(
            x=comp["points"], y=comp["component"], orientation="h", marker={"color": ACCENT},
            text=[f"{p:g} / {m}" for p, m in zip(comp["points"], comp["max_points"])],
            textposition="outside", textfont={"color": INK}, cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.2f} points<extra></extra>",
        )
    )
    style(fig, f"Score breakdown for {row['account_key']} (grey = maximum points)", height=340)
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(range=[0, 30], title="Points")
    fig.update_yaxes(autorange="reversed", title=None, gridcolor="rgba(0,0,0,0)")
    with left:
        show(fig)
    with right:
        st.markdown(f'<div class="why">{bd.explain(row)}</div>', unsafe_allow_html=True)
        fact_measures = ["Transactions", "Total value (USD)", "ACH share", "Cross-border share",
                         "Fan-in / fan-out", "Pass-through within 24h", "Activity vs 7-day average"]
        fact_values = [
            f"{int(row['txn_count'])}",
            f"${row['total_amount_usd']:,.2f}",
            bd._pct(row["ach_share"]),
            bd._pct(row["cross_border_share"]),
            f"{int(row['fan_in'])} / {int(row['fan_out'])}",
            bd._pct(row["pass_through_share_24h"]),
            f"{row['activity_spike_ratio']:.2f}x",
        ]
        if bd.COUNTRY_COLUMN in row.index:
            fact_measures.insert(0, "Account country")
            fact_values.insert(0, row[bd.COUNTRY_COLUMN])
        if show_ground_truth and bd.LABEL_COLUMN in row.index:
            fact_measures.append("Ground truth (evaluation only)")
            fact_values.append("Laundering" if int(row[bd.LABEL_COLUMN]) == 1 else "Not laundering")
        facts = pd.DataFrame(
            {
                "Measure": fact_measures,
                "Value": fact_values,
            }
        )
        st.write("")
        full_width(st.dataframe, facts, hide_index=True)
        st.caption(
            "Prioritisation only: a high score tells investigators where to look first. "
            "It does not prove money laundering."
        )

    # Average contribution across the queue
    avg = bd.average_components(selected)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=avg["max_points"], y=avg["component"], orientation="h",
                         marker={"color": TRACK}, hoverinfo="skip"))
    fig.add_trace(
        go.Bar(
            x=avg["points"], y=avg["component"], orientation="h", marker={"color": SERIES},
            text=[f"{p:.1f} / {m}" for p, m in zip(avg["points"], avg["max_points"])],
            textposition="outside", textfont={"color": INK}, cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Average %{x:.2f} points<extra></extra>",
        )
    )
    style(fig, "What drives this queue: average points per component", height=320)
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(range=[0, 30], title="Average points across the accounts shown")
    fig.update_yaxes(autorange="reversed", title=None, gridcolor="rgba(0,0,0,0)")
    show(fig)

    # Main table
    st.markdown("#### Investigator queue")
    table_columns = ["daily_rank"]
    if bd.COUNTRY_COLUMN in selected.columns:
        table_columns.append(bd.COUNTRY_COLUMN)
    table_columns += ["bank_id", "account_id", "account_key", "risk_score", "txn_count",
                      "total_amount_usd", "ach_share", "cross_border_share", "fan_in", "fan_out",
                      "pass_through_share_24h", "activity_spike_ratio"]
    if show_ground_truth and bd.LABEL_COLUMN in selected.columns:
        table_columns.append(bd.LABEL_COLUMN)
    table = selected[table_columns].copy()
    if bd.COUNTRY_COLUMN in table.columns:
        table[bd.COUNTRY_COLUMN] = table[bd.COUNTRY_COLUMN].map(flag_url)
    for col in ["ach_share", "pass_through_share_24h"]:
        table[col] = table[col] * 100
    table["cross_border_share"] = table["cross_border_share"].map(bd._pct)
    if show_ground_truth and bd.LABEL_COLUMN in table.columns:
        table[bd.LABEL_COLUMN] = table[bd.LABEL_COLUMN].map(
            {1: "Laundering", 0: "Not laundering"}
        )
    full_width(
        st.dataframe,
        table,
        hide_index=True,
        height=420,
        column_config={
            "daily_rank": st.column_config.NumberColumn("Rank", format="%d"),
            bd.COUNTRY_COLUMN: st.column_config.ImageColumn(
                "Country", width="small", help="Flag of the account's country (inferred from its transactions). Gold = crypto bank, grey ? = unknown"
            ),
            "bank_id": st.column_config.TextColumn("Bank ID"),
            "account_id": st.column_config.TextColumn("Account"),
            "account_key": st.column_config.TextColumn("Account key"),
            "risk_score": st.column_config.NumberColumn("Risk score", format="%.2f"),
            "txn_count": st.column_config.NumberColumn("Transactions", format="%d"),
            "total_amount_usd": st.column_config.NumberColumn("Value (USD)", format="$%.2f"),
            "ach_share": st.column_config.NumberColumn("ACH share", format="%.0f%%"),
            "cross_border_share": st.column_config.TextColumn("Cross-border"),
            "fan_in": st.column_config.NumberColumn("Fan-in", format="%d"),
            "fan_out": st.column_config.NumberColumn("Fan-out", format="%d"),
            "pass_through_share_24h": st.column_config.NumberColumn("Pass-through 24h", format="%.0f%%"),
            "activity_spike_ratio": st.column_config.NumberColumn("Activity vs normal", format="%.2fx"),
            bd.LABEL_COLUMN: st.column_config.TextColumn("Ground truth"),
        },
    )
    out = selected.copy()
    out["profile_date"] = out["profile_date"].dt.date
    if not show_ground_truth and bd.LABEL_COLUMN in out.columns:
        out = out.drop(columns=[bd.LABEL_COLUMN])
    st.download_button(
        "Download this queue (CSV)",
        out.to_csv(index=False).encode("utf-8"),
        file_name=f"bq1_queue_{date.date()}.csv",
        mime="text/csv",
    )


with tab_queue:
    render_queue_tab()

# ---------------------------------------------------------------------------
# Tab 2: Capacity Trade-off
# ---------------------------------------------------------------------------
with tab_capacity:
    cap = bd.capacity_view(capacity)
    rec = cap[cap["daily_capacity"] == bd.RECOMMENDED_CAPACITY].iloc[0]
    st.markdown("#### Recommended pilot: 100 reviews per day")
    cols = st.columns(5)
    tiles = [
        ("Reviews per day", f"{int(rec['daily_capacity'])}", "Assumed team capacity"),
        ("Planning threshold", f"{rec['recommended_score_threshold']:.1f}", "Median rank-100 score"),
        ("Laundering found / day", f"{rec['avg_laundering_detected_per_day']:.2f}", "Labelled account-days"),
        ("Precision", f"{rec['overall_precision']:.2%}", "Share of reviews that hit"),
        ("Detection rate", f"{rec['overall_detection_rate']:.2%}", "Share of all laundering found"),
    ]
    for col, (label, value, help_txt) in zip(cols, tiles):
        with col.container(border=True):
            st.metric(label, value)
            st.caption(help_txt)

    ref = bd.random_review_reference(capacity)
    st.info(
        f"For scale: about {ref['laundering_per_day']:,.0f} of roughly {ref['active_per_day']:,.0f} active "
        f"account-days each day are labelled laundering, so reviewing 100 accounts at random would hit "
        f"about {ref['base_rate']:.2%}. The ranked queue hits {rec['overall_precision']:.2%}, "
        f"about {ref['lift']:.0f} times better."
    )

    bar_colors = [ACCENT if c == bd.RECOMMENDED_CAPACITY else SERIES for c in cap["daily_capacity"]]
    mark_sizes = [14 if c == bd.RECOMMENDED_CAPACITY else 9 for c in cap["daily_capacity"]]

    def capacity_line(y, title, ytitle, fmt, hover_fmt):
        fig = go.Figure(
            go.Scatter(
                x=cap["label"], y=y, mode="lines+markers+text",
                line={"color": SERIES, "width": 2},
                marker={"color": bar_colors, "size": mark_sizes, "line": {"color": "white", "width": 2}},
                text=[fmt(v) for v in y], textposition="top center", textfont={"color": INK},
                hovertemplate="<b>%{x} reviews/day</b><br>" + hover_fmt + "<extra></extra>",
                cliponaxis=False,
            )
        )
        style(fig, title, height=330)
        fig.update_xaxes(type="category", title="Reviews per day")
        fig.update_yaxes(title=ytitle, rangemode="tozero")
        return fig

    left, right = st.columns(2)
    fig = go.Figure(
        go.Bar(
            x=cap["label"], y=cap["avg_laundering_detected_per_day"], marker={"color": bar_colors},
            text=cap["avg_laundering_detected_per_day"].map(lambda v: f"{v:.1f}"), textposition="outside",
            textfont={"color": INK}, cliponaxis=False,
            hovertemplate="<b>%{x} reviews/day</b><br>%{y:.2f} laundering account-days found<extra></extra>",
        )
    )
    style(fig, "More reviews find more laundering…", height=330)
    fig.update_xaxes(type="category", title="Reviews per day")
    fig.update_yaxes(title="Laundering account-days found per day")
    with left:
        show(fig)
    with right:
        show(capacity_line(cap["overall_precision"] * 100, "…but each extra review is less likely to hit",
                           "Precision (%)", lambda v: f"{v:.1f}%", "Precision %{y:.2f}%"))

    left, right = st.columns(2)
    with left:
        show(capacity_line(cap["overall_detection_rate"] * 100, "Share of all laundering found",
                           "Detection rate (%)", lambda v: f"{v:.1f}%", "Detection rate %{y:.2f}%"))
    with right:
        show(capacity_line(cap["recommended_score_threshold"], "Score needed to make the queue",
                           "Median cut-off score", lambda v: f"{v:.1f}", "Median cut-off %{y:.2f}"))

    steps = cap.dropna(subset=["step"])
    step_colors = [ACCENT if s.endswith(" 100") else SERIES for s in steps["step"]]
    fig = go.Figure(
        go.Bar(
            x=steps["step"], y=steps["found_per_extra_review"], marker={"color": step_colors},
            text=steps["found_per_extra_review"].map(lambda v: f"{v:.2f}"), textposition="outside",
            textfont={"color": INK}, cliponaxis=False,
            customdata=steps[["extra_reviews", "extra_found"]],
            hovertemplate="<b>%{x}</b><br>%{customdata[0]:,.0f} extra reviews/day"
            "<br>%{customdata[1]:.2f} extra laundering found/day<br>%{y:.3f} found per extra review<extra></extra>",
        )
    )
    style(fig, "Payoff of each step up: extra laundering found per extra review", height=330)
    fig.update_xaxes(type="category", title="Change in daily capacity")
    fig.update_yaxes(title="Extra found per extra review")
    show(fig)

    st.markdown(
        f"""
**How to read this**

- **More reviews find more.** Going from 50 to 100 reviews a day finds about
  **{rec['extra_found']:.2f} more** labelled laundering account-days per day.
- **Precision falls as lower-ranked accounts are added.** It drops only
  **{(cap.loc[0, 'overall_precision'] - rec['overall_precision']) * 100:.2f} percentage points** from 50 to 100,
  but much faster after that. Beyond 100, each extra review finds
  **{steps.iloc[1]['found_per_extra_review'] / steps.iloc[0]['found_per_extra_review']:.0%}** as much
  as the step from 50 to 100 did, or less.
- **100 reviews a day is the practical pilot** for a small, fixed-capacity team. If the real team can
  sustainably review more, read off the matching row below instead. This is a planning choice, not a
  universal optimum.
- **Use the rank, not a fixed score.** The queue is "rank 1–100 each day". The score at rank 100 moves
  from day to day; {rec['recommended_score_threshold']:.1f} is only the median, for planning.
"""
    )
    cap_table = cap[["daily_capacity", "days_evaluated", "avg_accounts_reviewed_per_day",
                     "avg_laundering_detected_per_day", "recommended_score_threshold",
                     "overall_precision", "overall_detection_rate"]].copy()
    cap_table["overall_precision"] *= 100
    cap_table["overall_detection_rate"] *= 100
    full_width(
        st.dataframe,
        cap_table,
        hide_index=True,
        column_config={
            "daily_capacity": st.column_config.NumberColumn("Reviews/day", format="%d"),
            "days_evaluated": st.column_config.NumberColumn("Days tested", format="%d"),
            "avg_accounts_reviewed_per_day": st.column_config.NumberColumn("Avg reviewed/day", format="%.0f"),
            "avg_laundering_detected_per_day": st.column_config.NumberColumn("Avg found/day", format="%.2f"),
            "recommended_score_threshold": st.column_config.NumberColumn("Median cut-off", format="%.2f"),
            "overall_precision": st.column_config.NumberColumn("Precision", format="%.2f%%"),
            "overall_detection_rate": st.column_config.NumberColumn("Detection rate", format="%.2f%%"),
        },
    )

# ---------------------------------------------------------------------------
# Tab 3: Methodology and Limitations
# ---------------------------------------------------------------------------
with tab_method:
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(
            """
#### How the score works
Each transaction is split into an **outgoing leg** (for the sender) and an **incoming leg**
(for the receiver). Spark then groups the legs into one **account-day profile**: one row per
active account per date. Every profile gets up to 100 points from seven behaviours:
"""
        )
        weights = pd.DataFrame(
            {
                "Component": list(bd.COMPONENTS),
                "Max points": [m for _, m in bd.COMPONENTS.values()],
                "What it measures": [
                    "Share of the day's activity paid by ACH",
                    "Share of eligible activity that crossed countries",
                    "Distinct accounts it sent money to (scaled to the day's 95th percentile)",
                    "Distinct accounts it received money from (scaled to the day's 95th percentile)",
                    "Share of activity between the day's median and 95th-percentile amount",
                    "Share of money sent out within 24h of money arriving",
                    "Today's transactions vs the previous 7-day average (scaled to the 95th percentile)",
                ],
            }
        )
        full_width(st.dataframe, weights, hide_index=True)
        st.markdown(
            """
- **Ranking resets every date.** Accounts are sorted by score (ties: higher value first, then
  account key). An account can be rank 5 one day and rank 200 the next, or absent if inactive.
- **Labels are kept out until evaluation.** The laundering label is built in a separate branch
  and joined only after scores and ranks are fixed. It is hidden by default and appears only when
  **Show ground truth** is enabled for evaluation; an investigator would not know it beforehand.
- **Country means the account-side country.** It comes from `from_country` for outgoing activity
  and `to_country` for incoming activity. It is not an external bank-headquarters lookup.
- **Capacity results** compare each daily top-N with the labels: *precision* = laundering found ÷
  accounts reviewed; *detection rate* = laundering found ÷ all labelled laundering account-days.

#### Adding a new date
1. Upload the new raw transactions to S3 and refresh the crawler if needed.
2. Run the Glue cleaning job, then `account_profiles.py` and `risk_scoring.py` on EMR Serverless.
3. Refresh the curated partitions. The Athena view keeps ranks 1–100 for the new date automatically.
4. Re-export the two CSVs (README, step 1). The app opens on the newest date.
"""
        )
    with right:
        st.markdown(
            """
#### Limitations
- **Synthetic data.** IBM's simulated transactions, not real bank records.
- **Only 16 dates** are available, so results are an average over a short window.
- **Weights are project assumptions**, set from exploratory lift analysis, not learned by a model.
- **A high score is a priority to investigate, not proof** of criminal activity.
- **100 reviews/day assumes a small pilot team.** Other capacities are in the trade-off tab.
- **Detection metrics depend on the dataset's labels.**
- **Batch, not real time.** The pipeline is run per batch of dates.
- **This version reads exported CSVs**, not a live Athena connection. The enriched queue must
  include ranks 1-1,000 plus the optional daily population, country and evaluation-label fields.
"""
        )
        st.markdown("#### Data checks")
        check_df = pd.DataFrame(
            {
                "Check": [c.name for c in checks],
                "Result": ["✅ Pass" if c.passed else "❌ Fail" for c in checks],
                "Detail": [c.detail for c in checks],
            }
        )
        full_width(st.dataframe, check_df, hide_index=True)
