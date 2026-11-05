"""
BQ2 data, scheme drawings and popups, shared by the BQ2 pages.

Reads the BQ2 outputs in Athena (Glue database of the selected run; aml_bq2_curated for Run 1):
  flow_comparison, holding_time, scheme_profile, country_pairs, bank_entry_exit, scheme_edges, bank_size
The stored queries and every number are unchanged from the original single BQ2 page;
this module only reorganises how they are shown.
"""
from __future__ import annotations

import time

import altair as alt
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import theme, ui
from common.athena import ATHENA_OUTPUT, WORKGROUP, aws_session, load_sql, mock_result
from common.runs import current_run

FOLDER = "bq2/dashboard"

GROUP_COLORS = alt.Scale(domain=["laundering", "normal"], range=[theme.LAUNDERING, theme.NORMAL])
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

ROLE_COLORS = {"mostly entry": theme.ENTRY, "mostly exit": theme.EXIT, "entry and exit": theme.BOTH,
               "pass-through": theme.MIDDLE}
SCHEME_ROLE_COLORS = {"entry": theme.ENTRY, "exit": theme.EXIT, "entry and exit": theme.BOTH,
                      "middle": theme.MIDDLE}


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


# ---------------------------------------------------------------- Athena + S3
# Flow: SQL file in S3 -> Athena runs it and writes a CSV to S3 -> Streamlit reads that CSV from S3.
@st.cache_data(ttl=3600, show_spinner="Querying Athena...")
def _run_query(name: str, database: str) -> pd.DataFrame:
    """Run a stored query and read its result CSV from S3. Athena reuses results for 60 min to save cost."""
    mocked = mock_result(FOLDER, name)
    if mocked is not None:
        return mocked
    session = aws_session()
    athena = session.client("athena")
    qid = athena.start_query_execution(
        QueryString=load_sql(f"{FOLDER}/{name}"),
        QueryExecutionContext={"Database": database},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": f"{ATHENA_OUTPUT}/{FOLDER}/{name}/"},
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}},
    )["QueryExecutionId"]

    while True:
        execution = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        status = execution["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(status.get("StateChangeReason", status["State"]))

    # A reused result can live in an older folder, so always use the location Athena reports.
    bucket, key = execution["ResultConfiguration"]["OutputLocation"].removeprefix("s3://").split("/", 1)
    body = session.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
    df = pd.read_csv(body, dtype=str, keep_default_na=False, na_values=[""])
    for col in df.columns:  # CSV is text; turn numeric columns into numbers
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


def _db() -> str:
    run = current_run()
    return run.db("bq2", "aml_bq2_curated") if run else "aml_bq2_curated"


@st.cache_resource(ttl=3600, show_spinner=False)
def _shared(name: str, database: str) -> pd.DataFrame:
    return _run_query(name, database)


def run_query(name: str) -> pd.DataFrame:
    """Shared, read-only frame for the selected run. Call .copy() before changing it."""
    return _shared(name, _db())


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower() == "true"


def bank_label(df: pd.DataFrame) -> pd.Series:
    """Bank names are not unique (two 'Future Savings Bank'), so always show the id."""
    return df["bank_name"].fillna("unknown") + " (" + df["bank_id"].astype(str) + ")"


# ---------------------------------------------------------------- loaders
def flow() -> pd.DataFrame:
    return run_query("flow_comparison")


def profile() -> pd.DataFrame:
    return run_query("scheme_profile")


def bee() -> pd.DataFrame:
    return _bee(_db())


@st.cache_resource(ttl=3600, show_spinner=False)
def _bee(database) -> pd.DataFrame:
    d = _shared("bank_entry_exit", database).copy()
    for c in ["entry_eligible", "exit_eligible"]:
        d[c] = as_bool(d[c])
    d["bank"] = bank_label(d)
    return d


def edges() -> pd.DataFrame:
    return run_query("scheme_edges")


def info() -> pd.DataFrame:
    i, err = _info(_db())
    if err:
        st.warning(f"Bank size query failed, showing names from bank_entry_exit only: {err}")
    return i


@st.cache_resource(ttl=3600, show_spinner=False)
def _info(database):
    err = None
    try:
        i = _shared("bank_size", database).set_index("bank_id")
    except Exception as ex:  # keep the page usable if the size query fails
        err = str(ex)
        i = _bee(database).set_index("bank_id")[["bank_name", "country"]].assign(total_txns=None, n_accounts=None)
    i["bank"] = i["bank_name"].fillna("unknown") + " (" + i.index.astype(str) + ")"
    return i, err


@st.cache_resource(ttl=3600, show_spinner=False)
def _lookups(database):
    i, _ = _info(database)
    return i["bank"].to_dict(), i["country"].to_dict()


def headline_counts():
    """Laundering / normal transactions and scheme coverage, as on the original page header."""
    f, p = flow(), profile()
    n_laundering = int(f[(f["grp"] == "laundering") & (f["dimension"] == "border")]["n_tx"].sum())
    n_normal = int(f[(f["grp"] == "normal") & (f["dimension"] == "border")]["n_tx"].sum())
    in_clean = int(round((p["n_transfers"] * p["share_in_clean"]).sum()))
    return n_laundering, n_normal, len(p), in_clean


def name_of(b) -> str:
    return _lookups(_db())[0].get(b, f"bank {b}")


def short_name(b, n: int = 24) -> str:
    return name_of(b).split(" (")[0][:n]


def country_of(b) -> str:
    return _lookups(_db())[1].get(b, "?")


def scheme_end_banks(prof: pd.DataFrame) -> pd.DataFrame:
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


def ends() -> pd.DataFrame:
    return _ends(_db())


@st.cache_resource(ttl=3600, show_spinner=False)
def _ends(database) -> pd.DataFrame:
    return scheme_end_banks(_shared("scheme_profile", database))


def touch(e: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([e[["scheme_id", "from_bank"]].rename(columns={"from_bank": "bank_id"}),
                      e[["scheme_id", "to_bank"]].rename(columns={"to_bank": "bank_id"})]).drop_duplicates()


def bank_stats(stype: str = "All types") -> pd.DataFrame:
    """Per bank: schemes through it, entries, exits and role (same rules as the original bank map)."""
    return _bank_stats(_db(), stype)


@st.cache_resource(ttl=3600, show_spinner=False)
def _bank_stats(database, stype) -> pd.DataFrame:
    prof, e_all = _shared("scheme_profile", database), _shared("scheme_edges", database)
    e = e_all if stype == "All types" else e_all[e_all["scheme_type"] == stype]
    prof_f = prof if stype == "All types" else prof[prof["scheme_type"] == stype]
    en = _ends(database)
    ends_f = en[en["scheme_id"].isin(prof_f["scheme_id"])]
    t = touch(e)
    stats = pd.concat([t.groupby("bank_id")["scheme_id"].nunique().rename("n_schemes"),
                       ends_f[ends_f["kind"] == "entry"].groupby("bank_id")["scheme_id"].nunique().rename("entries"),
                       ends_f[ends_f["kind"] == "exit"].groupby("bank_id")["scheme_id"].nunique().rename("exits")],
                      axis=1).fillna(0).astype(int)
    stats["role"] = "entry and exit"
    stats.loc[stats["entries"] >= 2 * stats["exits"], "role"] = "mostly entry"
    stats.loc[stats["exits"] >= 2 * stats["entries"], "role"] = "mostly exit"
    stats.loc[(stats["entries"] + stats["exits"]) == 0, "role"] = "pass-through"
    return stats


# ---------------------------------------------------------------- one scheme
def scheme_edges_of(scheme_id) -> pd.DataFrame:
    """Transfers of one scheme in time order (ties by step), numbered from 1."""
    return _scheme_edges_of(_db(), scheme_id).copy()


@st.cache_resource(ttl=3600, show_spinner=False, max_entries=2000)
def _scheme_edges_of(database, scheme_id) -> pd.DataFrame:
    e = _shared("scheme_edges", database)
    ed = e[e["scheme_id"] == scheme_id].copy()
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


def bank_path(ed: pd.DataFrame) -> list:
    """Banks in time order, consecutive repeats removed (as in the original page)."""
    seq = [ed.iloc[0]["from_bank"]] + ed["to_bank"].tolist()
    return [b for i, b in enumerate(seq) if i == 0 or b != seq[i - 1]]


def _acc_bank(acc: str) -> int:
    return int(str(acc).split(":")[0])


def _bezier(p0, p1, bend):
    """Points of a quadratic curve from p0 to p1, bent sideways by `bend` (fraction of length)."""
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * bend, my + dx * bend
    ts = [i / 16 for i in range(17)]
    return [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1,
             (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1) for t in ts]


def scheme_flow_figure(ed: pd.DataFrame, sel_bank=None, height=None) -> go.Figure:
    """Pipeline drawing of one scheme: green entry accounts on the left, a block of intermediary
    accounts in the middle (in order of first appearance), red exit accounts on the right.
    An account that is both entry and exit (cycles) is drawn on both sides."""
    entries_, exits_ = scheme_end_accounts(ed)
    moves = ed[ed["src"] != ed["dst"]]
    country = dict(zip(ed["src"], ed["from_country"]))
    country.update(zip(ed["dst"], ed["to_country"]))

    first_seen = {}
    for r in ed.itertuples():
        first_seen.setdefault(r.src, r.order)
        first_seen.setdefault(r.dst, r.order)
    middle = sorted([a for a in country if a not in entries_ and a not in exits_], key=first_seen.get)
    ent = sorted(entries_, key=first_seen.get)
    ext = sorted(exits_, key=first_seen.get)

    # positions
    X_ENT, X_EXT, MID_L, MID_R = 0.0, 10.0, 2.6, 7.4
    per_row = max(1, min(6, len(middle)))
    n_rows = (len(middle) + per_row - 1) // per_row if middle else 0
    span = max(len(ent), len(ext), n_rows * 1.6, 3)

    def col_y(n):
        if n == 1:
            return [0.0]
        step = min(1.6, span / max(n - 1, 1))
        return [(n - 1) / 2 * step - i * step for i in range(n)]

    pos = {}
    for a, y in zip(ent, col_y(len(ent))):
        pos[("E", a)] = (X_ENT, y)
    for a, y in zip(ext, col_y(len(ext))):
        pos[("X", a)] = (X_EXT, y)
    for i, a in enumerate(middle):
        r_, c_ = divmod(i, per_row)
        n_in_row = min(per_row, len(middle) - r_ * per_row)
        xs = [MID_L + 0.5 + (MID_R - MID_L - 1) * (k + 0.5) / n_in_row for k in range(n_in_row)]
        y = (n_rows - 1) / 2 * 1.6 - r_ * 1.6
        pos[("M", a)] = (xs[c_], y + (0.35 if c_ % 2 else -0.35) * (per_row > 2))

    def inst_src(a):
        return ("E", a) if a in entries_ else (("M", a) if a not in exits_ else ("X", a))

    def inst_dst(a):
        return ("X", a) if a in exits_ else (("M", a) if a not in entries_ else ("E", a))

    ys = [p[1] for p in pos.values()]
    y_top, y_bot = max(ys) + 1.2, min(ys) - 1.2
    fig = go.Figure()

    # blocks behind the nodes
    def block(x0, x1, fill, line, dash=None):
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y_bot + 0.3, y1=y_top - 0.3, layer="below",
                      fillcolor=fill, line=dict(color=line, width=1, dash=dash))

    block(X_ENT - 0.9, X_ENT + 0.9, "#E9F7F1", theme.ENTRY)
    block(X_EXT - 0.9, X_EXT + 0.9, "#FFEDED", theme.EXIT)
    if middle:
        block(MID_L, MID_R, theme.CANVAS, theme.FAINT, "dot")
    mid_banks = len({_acc_bank(a) for a in middle})
    for x, txt, col in [(X_ENT, f"ENTRY · {len(ent)}", theme.ENTRY), (X_EXT, f"EXIT · {len(ext)}", theme.EXIT)] + (
            [((MID_L + MID_R) / 2, f"INTERMEDIARIES · {len(middle)} accounts, {mid_banks} banks", theme.MUTED)]
            if middle else []):
        fig.add_annotation(x=x, y=y_top, text=f"<b>{txt}</b>", showarrow=False, yanchor="bottom",
                           font=dict(size=11, color=col))

    # transfers: curved lines, arrowheads, hover dots with the details
    lx, ly, hx, hy, htext, order_txt = [], [], [], [], [], []
    has_ccy = "currency" in ed.columns or "payment_currency" in ed.columns
    ccy_col = "currency" if "currency" in ed.columns else "payment_currency"
    for r in moves.itertuples():
        p0, p1 = pos[inst_src(r.src)], pos[inst_dst(r.dst)]
        same_col = abs(p0[0] - p1[0]) < 0.6
        bend = 0.35 if same_col else (0.12 if inst_src(r.src)[0] == "E" and inst_dst(r.dst)[0] == "X" and middle
                                      else 0.06)
        pts = _bezier(p0, p1, bend)
        lx += [p[0] for p in pts] + [None]
        ly += [p[1] for p in pts] + [None]
        fig.add_annotation(x=pts[-1][0], y=pts[-1][1], ax=pts[-4][0], ay=pts[-4][1], xref="x", yref="y",
                           axref="x", ayref="y", text="", showarrow=True, arrowhead=2, arrowsize=1.1,
                           arrowwidth=1.4, arrowcolor="rgba(28,28,28,0.45)", standoff=13)
        hx.append(pts[8][0])
        hy.append(pts[8][1])
        order_txt.append(str(r.order))
        ccy = f" · {getattr(r, ccy_col)}" if has_ccy else ""
        htext.append(f"<b>Transfer {r.order}</b><br>{r.src} → {r.dst}<br>"
                     f"${r.amount_usd:,.0f} USD{ccy} · {r.payment_format}<br>{str(r.ts)[:16]}")
    fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines", hoverinfo="skip", showlegend=False,
                             line=dict(width=1.4, color="rgba(28,28,28,0.30)", shape="spline")))
    fig.add_trace(go.Scatter(x=hx, y=hy, mode="markers+text", text=order_txt, textposition="top center",
                             textfont=dict(size=9, color=theme.MUTED), hovertext=htext, hoverinfo="text",
                             marker=dict(size=7, color=theme.SURFACE, line=dict(width=1, color=theme.FAINT)),
                             showlegend=False, customdata=[["edge"]] * len(hx)))

    # accounts
    for kind, accs, color, name in [("E", ent, theme.ENTRY, "entry account"), ("M", middle, theme.INK, "intermediary"),
                                    ("X", ext, theme.EXIT, "exit account")]:
        if not accs:
            continue
        mine = [_acc_bank(a) == sel_bank for a in accs]
        fig.add_trace(go.Scatter(
            x=[pos[(kind, a)][0] for a in accs], y=[pos[(kind, a)][1] for a in accs], mode="markers+text",
            name=name, customdata=[[a] for a in accs],
            text=[short_name(_acc_bank(a), 18) for a in accs], textposition="bottom center",
            textfont=dict(size=10, color=theme.INK_80),
            hovertext=[f"<b>{a}</b><br>{name_of(_acc_bank(a))}<br>{country.get(a, '?')}<br>{name}"
                       + ("<br>★ selected bank" if m else "") for a, m in zip(accs, mine)],
            hoverinfo="text",
            marker=dict(size=22 if kind != "M" else 14, color=color, opacity=0.95,
                        line=dict(width=[3.5 if m else 1.5 for m in mine],
                                  color=[theme.S_YELLOW if m else theme.SURFACE for m in mine]))))
    fig.update_layout(height=height or int(max(300, 90 * (y_top - y_bot) + 40)),
                      margin=dict(l=0, r=0, t=6, b=0), dragmode="pan", showlegend=False, hovermode="closest",
                      xaxis=dict(visible=False, range=[-1.3, 11.3]),
                      yaxis=dict(visible=False, range=[y_bot - 0.2, y_top + 0.6]))
    return fig


def _hop_meta(ts, usd) -> str:
    return f"{str(ts)[5:16]} · ${usd:,.0f}"


def bank_pipeline_html(sid, sel_bank=None, max_mid: int = 6) -> str:
    """Entry bank(s) -> intermediary banks (time order) -> exit bank(s), as HTML blocks.
    Each block shows when money first reached the bank and how much (USD)."""
    ed = scheme_edges_of(sid)
    en = ends()
    ent_b = sorted(en[(en["scheme_id"] == sid) & (en["kind"] == "entry")]["bank_id"])
    ext_b = sorted(en[(en["scheme_id"] == sid) & (en["kind"] == "exit")]["bank_id"])
    path = bank_path(ed)
    mids = [b for b in dict.fromkeys(path) if b not in ent_b and b not in ext_b]

    def sent(b):
        d = ed[ed["from_bank"] == b]
        return (d["ts"].min(), d["amount_usd"].sum()) if len(d) else (None, 0)

    def recv(b, last=False):
        d = ed[(ed["to_bank"] == b) & (ed["from_bank"] != b)]
        if not len(d):
            d = ed[ed["to_bank"] == b]
        return ((d["ts"].max() if last else d["ts"].min()), d["amount_usd"].sum()) if len(d) else (None, 0)

    def card(b, ts, usd, cls=""):
        sel = " sel" if b == sel_bank else ""
        star = "★ " if b == sel_bank else ""
        return (f'<div class="hop{sel} {cls}"><div class="bank">{star}{theme.esc(short_name(b, 26))}</div>'
                f'<div class="meta">{theme.esc(country_of(b))} · {_hop_meta(ts, usd) if ts else ""}</div></div>')

    def end_block(kind, banks, which):
        cls = "entry" if kind == "Entry" else "exit"
        sel = " sel" if sel_bank in banks else ""
        items = []
        for b in banks[:3]:
            ts, usd = sent(b) if kind == "Entry" else recv(b, last=True)
            star = "★ " if b == sel_bank else ""
            items.append(f'<div class="bank">{star}{theme.esc(short_name(b, 26))}</div>'
                         f'<div class="meta">{theme.esc(country_of(b))}</div>'
                         f'<div class="meta">{which} {_hop_meta(ts, usd) if ts else "n/a"}</div>')
        more = (f'<details><summary>+{len(banks) - 3} more</summary>'
                + "".join(f'<div class="meta">{theme.esc(short_name(b, 26))}</div>' for b in banks[3:])
                + "</details>") if len(banks) > 3 else ""
        return (f'<div class="blk {cls}{sel}"><div class="k">{kind} bank{"s" if len(banks) > 1 else ""}</div>'
                + "".join(items) + more + "</div>")

    chev = '<span class="chev">›</span>'
    if mids:
        cards = [card(b, *recv(b)) for b in mids]
        shown = chev.join(cards[:max_mid])
        rest = (f'<details><summary>Show {len(cards) - max_mid} more intermediary banks</summary>'
                f'<div class="hops">{chev.join(cards[max_mid:])}</div></details>') if len(cards) > max_mid else ""
        mid_html = (f'<div class="blk mid"><div class="k">Intermediary banks · {len(mids)} · in time order</div>'
                    f'<div class="hops">{shown}</div>{rest}</div>')
    else:
        mid_html = ('<div class="blk mid empty"><div class="k">Intermediary banks</div>'
                    '<div class="meta" style="margin-top:8px">None: money goes straight from the entry '
                    'bank(s) to the exit bank(s).</div></div>')
    arrow = '<div class="arrow">→</div>'
    return (f'<div class="pipe">{end_block("Entry", ent_b, "sends")}{arrow}{mid_html}{arrow}'
            f'{end_block("Exit", ext_b, "last in")}</div>')


def hops_table(ed: pd.DataFrame) -> pd.DataFrame:
    """Every transfer that crosses banks, in time order."""
    h = ed[ed["from_bank"] != ed["to_bank"]].copy()
    h["from"] = h["from_bank"].map(name_of)
    h["to"] = h["to_bank"].map(name_of)
    return h[["order", "ts", "from", "to", "amount_usd", "payment_format"]]


# ---------------------------------------------------------------- popups
BANK_DIALOG, SCHEME_DIALOG = "_dlg_bank", "_dlg_scheme"


def open_bank(bank_id):
    st.session_state[BANK_DIALOG] = int(bank_id)
    st.session_state.pop(SCHEME_DIALOG, None)


def open_scheme(scheme_id, from_bank=None):
    st.session_state[SCHEME_DIALOG] = (int(scheme_id), from_bank)
    st.session_state.pop(BANK_DIALOG, None)


def pick_bank_from_chart(key):
    for p in st.session_state[key]["selection"]["points"]:
        cd = p.get("customdata")
        cd = cd[0] if isinstance(cd, list) and cd else cd
        if cd not in (None, "edge", "other"):
            open_bank(int(cd))
            break


def pick_from_table(key, ids, kind):
    rows = st.session_state[key]["selection"]["rows"]
    if rows and rows[0] < len(ids):
        (open_bank if kind == "bank" else open_scheme)(ids[rows[0]])


def bank_schemes(sel) -> pd.DataFrame:
    """The bank's schemes with its role in each and the bank path (logic from the original page)."""
    e, prof, en = edges(), profile(), ends()
    mine = touch(e)[lambda t: t["bank_id"] == sel]["scheme_id"].unique()
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
                         "path": " → ".join(("★ " if b == sel else "") + short_name(b) for b in path)})
    bs = prof[prof["scheme_id"].isin(mine)].merge(pd.DataFrame(pos_rows), on="scheme_id", how="left")
    is_in = bs["scheme_id"].isin(en[(en["bank_id"] == sel) & (en["kind"] == "entry")]["scheme_id"])
    is_out = bs["scheme_id"].isin(en[(en["bank_id"] == sel) & (en["kind"] == "exit")]["scheme_id"])
    bs["role"] = "middle"
    bs.loc[is_in, "role"] = "entry"
    bs.loc[is_out, "role"] = "exit"
    bs.loc[is_in & is_out, "role"] = "entry and exit"
    role_rank = {"entry and exit": 0, "entry": 1, "exit": 2, "middle": 3}
    return (bs.assign(_rank=bs["role"].map(role_rank)).sort_values(["_rank", "total_usd"], ascending=[True, False])
            .drop(columns="_rank").reset_index(drop=True))


def ego_figure(sel) -> go.Figure:
    """Who sends scheme money to the bank (left) and who it sends to (right), up to 15 per side."""
    e, stats = edges(), bank_stats()
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
                                     line=dict(width=1 + 2 * r["schemes"] ** 0.5, color="rgba(28,28,28,0.12)")))
        if len(df_):
            ego.add_trace(go.Scatter(
                x=[x] * len(df_), y=y_list, mode="markers+text", showlegend=False,
                text=[short_name(b) for b in df_.index],
                textposition="middle left" if arrow == "in" else "middle right",
                customdata=[[int(b)] for b in df_.index], hoverinfo="text",
                hovertext=[(f"{name_of(b)} → this bank" if arrow == "in" else f"this bank → {name_of(b)}")
                           + f"<br>{r['schemes']} schemes, ${r['usd']:,.0f}<br>{country_of(b)}"
                           for b, r in df_.iterrows()],
                marker=dict(size=[10 + 3 * v ** 0.5 for v in df_["schemes"]],
                            color=[ROLE_COLORS[stats["role"].get(b, "pass-through")] for b in df_.index],
                            line=dict(width=1, color=theme.SURFACE))))
    ego.add_trace(go.Scatter(x=[1.0], y=[0.0], mode="markers+text", text=[short_name(sel, 40)],
                             textposition="top center", showlegend=False, customdata=[["edge"]],
                             hoverinfo="text", hovertext=[f"<b>{name_of(sel)}</b> (selected)"],
                             marker=dict(size=30, symbol="diamond", color=theme.INK,
                                         line=dict(width=2, color=theme.S_YELLOW))))
    rows = max(len(left), len(right), 1)
    ego.update_layout(height=max(320, 30 * rows), margin=dict(l=0, r=0, t=10, b=0), dragmode="pan",
                      xaxis=dict(visible=False, range=[-1.1, 3.1]), yaxis=dict(visible=False),
                      hovermode="closest")
    ego.add_annotation(x=0, y=(rows + 1) / 2, text=f"<b>Sends to it</b> ({len(inflow)} banks)", showarrow=False)
    ego.add_annotation(x=2, y=(rows + 1) / 2, text=f"<b>Receives from it</b> ({len(outflow)} banks)",
                       showarrow=False)
    return ego


@st.dialog("Bank", width="large")
def bank_dialog(sel):
    stats, ratios, inf = bank_stats(), bee().set_index("bank_id"), info()
    s = stats.loc[sel] if sel in stats.index else pd.Series({"n_schemes": 0, "entries": 0, "exits": 0,
                                                             "role": "pass-through"})
    rr = ratios.loc[sel] if sel in ratios.index else None
    size_txns, size_acc = inf["total_txns"].get(sel), inf["n_accounts"].get(sel)

    st.markdown(f'<div class="snow-eyebrow">{theme.esc(country_of(sel))} · bank {sel}</div>'
                f'<div class="snow-title">{theme.esc(name_of(sel).split(" (")[0])}</div>'
                f'<div style="margin:6px 0 14px">{theme.pill(s["role"], ROLE_COLORS[s["role"]])}</div>',
                unsafe_allow_html=True)
    ratio_txt = ("n/a" if rr is None else
                 " / ".join("n/a" if pd.isna(v) else f"{v:.1f}x" for v in (rr["entry_ratio"], rr["exit_ratio"])))
    theme.kpi_row([
        ("Schemes through it", f"{int(s['n_schemes']):,}", "all scheme types"),
        ("Entries / exits", f"{int(s['entries'])} / {int(s['exits'])}", "schemes entering / leaving here"),
        ("Entry / exit ratio", ratio_txt, "actual / expected for its size"),
        ("Size", "n/a" if pd.isna(size_txns) else f"{int(size_txns):,} txns",
         "" if pd.isna(size_acc) else f"{int(size_acc):,} accounts"),
    ])

    bs = bank_schemes(sel)
    tab_s, tab_flow = st.tabs([f"Its {len(bs)} schemes", "Money in and out"])
    with tab_s:
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        with c1:
            n = ui.top_n("bank_dialog")
        roles = c2.multiselect("Role", ["entry", "exit", "entry and exit", "middle"], key=f"dlg_roles_{sel}",
                               placeholder="All roles", label_visibility="collapsed")
        view = bs[bs["role"].isin(roles)] if roles else bs
        tbl = ui.head(view, n)
        ev = st.dataframe(
            tbl[["scheme_id", "scheme_type", "role", "first_seen", "other_banks", "n_transfers",
                 "duration_hours", "total_usd"]],
            key=f"dlg_tbl_{sel}_{n}_{len(roles)}", on_select="rerun", selection_mode="single-row",
            width="stretch", hide_index=True, height=min(420, 38 + 35 * max(len(tbl), 1)),
            column_config={
                "scheme_id": "Scheme", "scheme_type": "Type", "role": "This bank is",
                "first_seen": "First appears at", "other_banks": "Other banks", "n_transfers": "Transfers",
                "duration_hours": st.column_config.NumberColumn("Duration (h)", format="%.0f"),
                "total_usd": st.column_config.NumberColumn("Total USD", format="$%.0f"),
            })
        st.caption("Entry and exit schemes first, then schemes where the bank is in the middle; largest USD first. "
                   "Select a row to see its bank path.")
        rows = ev.selection.rows if ev else []
        pick = int(tbl.iloc[rows[0]]["scheme_id"]) if rows else (int(tbl.iloc[0]["scheme_id"]) if len(tbl) else None)
        if pick is not None:
            r = bs[bs["scheme_id"] == pick].iloc[0]
            st.markdown(f"**Scheme #{pick} · {r['scheme_type']}** · this bank: "
                        f"{theme.pill(r['role'], SCHEME_ROLE_COLORS[r['role']])}", unsafe_allow_html=True)
            st.markdown(bank_pipeline_html(pick, sel), unsafe_allow_html=True)
            if st.button(f"Open scheme #{pick}", type="primary", key=f"dlg_open_{sel}_{pick}"):
                open_scheme(pick, from_bank=sel)
                st.rerun()
    with tab_flow:
        st.plotly_chart(ego_figure(sel), key=f"dlg_ego_{sel}", width="stretch",
                        config={"displayModeBar": False})
        st.caption("Money flows left to right through the selected bank (black diamond). Line width = number of "
                   "schemes. Up to 15 banks per side, most schemes first.")


@st.dialog("Scheme", width="large")
def scheme_dialog(sid, from_bank=None):
    prof = profile()
    p = prof[prof["scheme_id"] == sid].iloc[0]
    ed = scheme_edges_of(sid)
    sel_bank = from_bank
    st.markdown(f'<div class="snow-eyebrow">{theme.esc(p["scheme_type"])}</div>'
                f'<div class="snow-title">Scheme #{int(sid)}</div>'
                f'<div class="snow-subtitle">{theme.esc(SCHEME_TYPES.get(p["scheme_type"], ""))}</div>',
                unsafe_allow_html=True)
    theme.kpi_row([
        ("Transfers / accounts", f"{int(p['n_transfers'])} / {int(p['n_accounts'])}"),
        ("Banks / countries", f"{int(p['n_banks'])} / {int(p['n_countries'])}"),
        ("Duration", f"{p['duration_hours']:.0f} h"),
        ("Total", f"${p['total_usd']:,.0f}"),
    ])
    st.markdown("**Bank path in time order**")
    st.markdown(bank_pipeline_html(sid, sel_bank), unsafe_allow_html=True)

    st.markdown("**How the money moves between accounts**")
    theme.legend([(theme.ENTRY, "entry account (only sends)"), (theme.INK, "intermediary account"),
                  (theme.EXIT, "exit account (only receives)")]
                 + ([(theme.S_YELLOW, "★ selected bank")] if sel_bank is not None else []))
    ev = st.plotly_chart(scheme_flow_figure(ed, sel_bank), key=f"scheme_graph_{int(sid)}", on_select="rerun",
                         selection_mode="points", width="stretch",
                         config={"scrollZoom": True, "displayModeBar": False})
    st.caption("Numbers on the arrows are the time order; hover a dot for amount, payment format and time. "
               "In cycles the same account is drawn on both sides. "
               f"{p['share_in_clean']:.0%} of its transfers are inside the clean window. "
               "Click an account to list its transfers.")

    picked = []
    for pt in (ev.selection.points if ev else []):
        cd = pt.get("customdata")
        cd = cd[0] if isinstance(cd, list) and cd else cd
        if cd not in (None, "edge"):
            picked.append(cd)
    shown = ed[ed["src"].isin(picked) | ed["dst"].isin(picked)] if picked else ed
    with st.expander(f"Transfers{' of ' + ', '.join(picked) if picked else ''} ({len(shown)})", expanded=bool(picked)):
        st.dataframe(shown[["order", "ts", "src", "dst", "from_country", "to_country", "amount_usd",
                            "payment_format"]],
                     width="stretch", hide_index=True,
                     column_config={"order": "#", "amount_usd": st.column_config.NumberColumn("USD", format="$%.0f")})
    with st.expander(f"About {p['scheme_type']} schemes"):
        st.markdown(describe_type(p["scheme_type"], prof))
    if from_bank is not None:
        if st.button(f"← Back to {short_name(from_bank)}"):
            open_bank(from_bank)
            st.rerun()


def show_popups():
    """Call at the end of every BQ2 page: opens the popup the last click asked for, once."""
    b = st.session_state.pop(BANK_DIALOG, None)
    s = st.session_state.pop(SCHEME_DIALOG, None)
    if s is not None and s[0] in set(profile()["scheme_id"]):
        scheme_dialog(*s)
    elif b is not None:
        bank_dialog(b)


def bank_button_list(df: pd.DataFrame, col: str, key: str, n: int | None):
    """A ranked list of banks as buttons; clicking opens the bank popup."""
    for b, r in ui.head(df[df[col] > 0].sort_values(col, ascending=False), n).iterrows():
        st.button(f"{short_name(b, 30)} · {r[col]:,}", key=f"rank_{key}_{b}", on_click=open_bank, args=(int(b),),
                  width="stretch")


@st.cache_data(show_spinner=False)
def spring_positions(nodes: tuple, edges_: tuple) -> dict:
    """Force-directed layout; cached so the map does not move between reruns."""
    g = nx.Graph()
    g.add_nodes_from(nodes)
    g.add_weighted_edges_from(edges_)
    pos = nx.spring_layout(g, seed=7, weight="weight", iterations=100)
    return {n: (float(x), float(y)) for n, (x, y) in pos.items()}

