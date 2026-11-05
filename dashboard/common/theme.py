"""
Design tokens and shared UI pieces for every dashboard page.

Based on the SnowUI Dashboard Design System (Figma community file the team picked):
flat white cards on a light grey canvas, Inter, 16 px card radius, pale tinted KPI
tiles, near-black text with 40 % black for secondary text, and a pastel accent set
with stronger "status" tones for marks that must stand out.

Every colour, size and radius used by the pages comes from here. To restyle the app,
change the tokens below (and .streamlit/config.toml, which mirrors the base colours).

    from common import theme
    theme.apply()                    # once per page run: CSS + chart themes
    theme.page_header("Banks", "Which banks do schemes enter and leave through?", eyebrow="BQ2")
    theme.kpi_row([("Schemes", "4,512", "reconstructed"), ...])
"""
from __future__ import annotations

import html

import altair as alt
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------- tokens
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"

# Neutrals (SnowUI "Black" scale on white)
INK = "#1C1C1C"            # black 100 %: headings, values
INK_80 = "rgba(28,28,28,0.80)"
MUTED = "rgba(28,28,28,0.55)"  # secondary text (SnowUI uses 40 %; 55 % keeps AA contrast on white)
FAINT = "rgba(28,28,28,0.20)"
LINE = "rgba(28,28,28,0.10)"   # borders, dividers
GRID = "rgba(28,28,28,0.06)"   # chart gridlines
SURFACE = "#FFFFFF"            # cards
CANVAS = "#F7F9FB"             # page background ("Primary Light")
TINT_BLUE = "#E3F5FF"          # KPI tile tints ("Primary Blue" / "Primary Purple")
TINT_PURPLE = "#E5ECF6"

# Pastel accents (SnowUI "Secondary")
INDIGO = "#95A4FC"
PURPLE = "#C6C7F8"
CYAN = "#A8C5DA"
BLUE = "#B1E3FF"
GREEN = "#A1E3CB"
MINT = "#BAEDBD"
YELLOW = "#FFE999"
ORANGE = "#FFCB83"

# Strong status tones (SnowUI status text colours) for marks and semantic meaning
S_GREEN = "#4AA785"
S_RED = "#FF4747"
S_YELLOW = "#FFC555"
S_BLUE = "#59A8D4"
S_PURPLE = "#8A8CD9"
S_GREY = "#A0A7B0"

# Semantic roles used across BQ2 (entry = where money goes in, exit = where it leaves)
ENTRY = S_GREEN
EXIT = S_RED
BOTH = S_YELLOW
MIDDLE = S_GREY
SELECTED = INK
LAUNDERING = S_RED
NORMAL = CYAN

# Ordered categorical palette for charts (strong first, then pastels)
CATEGORICAL = [INK, S_PURPLE, S_BLUE, S_GREEN, ORANGE, INDIGO, CYAN, MINT, S_YELLOW, PURPLE]
SEQUENTIAL_RED = ["#FFF1F1", "#FFC9C9", "#FF9A9A", "#FF6B6B", "#E03131"]

# Type scale (px) and spacing (px)
FS_XS, FS_SM, FS_MD, FS_LG, FS_XL, FS_2XL = 12, 14, 16, 18, 24, 32
SPACE = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}
RADIUS_CARD, RADIUS_SM, RADIUS_PILL = 16, 8, 999
SHADOW = "0 1px 2px rgba(28,28,28,0.04)"

# ---------------------------------------------------------------- chart themes
_PLOTLY = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, size=FS_XS, color=INK_80),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=CATEGORICAL,
    margin=dict(l=8, r=8, t=24, b=8),
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor=LINE, tickcolor=LINE, title_font=dict(size=FS_XS)),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=LINE, tickcolor=LINE, title_font=dict(size=FS_XS)),
    hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(family=FONT, size=FS_XS, color=INK)),
    legend=dict(font=dict(size=FS_XS, color=INK_80), bgcolor="rgba(0,0,0,0)"),
    bargap=0.35,
))
pio.templates["snow"] = _PLOTLY
pio.templates.default = "plotly_white+snow"


def _altair_theme():
    return {"config": {
        "background": "transparent",
        "font": FONT,
        "view": {"stroke": "transparent"},
        "range": {"category": CATEGORICAL},
        "axis": {"labelColor": INK_80, "titleColor": MUTED, "labelFontSize": FS_XS, "titleFontSize": FS_XS,
                 "titleFontWeight": 400, "gridColor": GRID, "domainColor": LINE, "tickColor": LINE},
        "legend": {"labelColor": INK_80, "titleColor": MUTED, "labelFontSize": FS_XS, "titleFontSize": FS_XS,
                   "symbolType": "circle"},
        "bar": {"cornerRadiusEnd": 4},
        "header": {"labelColor": INK_80, "titleColor": MUTED},
    }}


try:  # Altair 5.5+
    @alt.theme.register("snow", enable=True)
    def _snow_theme():
        return alt.theme.ThemeConfig(_altair_theme())
except AttributeError:  # older Altair
    alt.themes.register("snow", _altair_theme)
    alt.themes.enable("snow")

# ---------------------------------------------------------------- CSS
_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {{ font-family: {FONT}; }}
.stApp {{ background: {CANVAS}; }}
.block-container {{ padding-top: 4.6rem; padding-bottom: 3rem; max-width: 1360px; }}
[class*="st-key-rank_"] button, [class*="st-key-rank_"] button div {{ justify-content: flex-start; text-align: left; }}
[class*="st-key-rank_"] button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
h1, h2, h3, h4 {{ color: {INK}; font-weight: 600; letter-spacing: -0.01em; }}
h1 {{ font-size: {FS_2XL - 4}px !important; }}
h2 {{ font-size: {FS_XL - 2}px !important; }}
h3 {{ font-size: {FS_LG}px !important; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {MUTED}; }}

/* cards: bordered containers, metrics, dataframes, charts */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px !important;
    border-color: {LINE} !important; box-shadow: {SHADOW}; }}
[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS_CARD}px;
    padding: {SPACE['md']}px {SPACE['md'] + 4}px; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: {FS_SM}px; font-weight: 500; }}
[data-testid="stMetricValue"] {{ color: {INK}; font-size: {FS_XL}px; font-weight: 600; }}
[data-testid="stDataFrame"] {{ border-radius: {RADIUS_SM + 4}px; overflow: hidden; }}
[data-testid="stExpander"] details {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; border-color: {LINE}; }}
[data-testid="stTabs"] button[role="tab"] p {{ font-size: {FS_SM}px; font-weight: 500; }}
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
.stButton > button, .stDownloadButton > button {{ border-radius: {RADIUS_SM + 4}px; font-weight: 500; }}
[data-testid="stAlert"] {{ border-radius: {RADIUS_SM + 4}px; }}
hr {{ border-color: {LINE}; }}

/* header bar */
.snow-brand {{ display:flex; align-items:center; gap:10px; }}
.snow-brand .logo {{ width:32px; height:32px; border-radius:10px; background:{INK}; color:#fff; display:flex;
    align-items:center; justify-content:center; font-weight:700; font-size:14px; }}
.snow-brand .name {{ font-weight:600; color:{INK}; font-size:{FS_SM + 1}px; line-height:1.1; }}
.snow-brand .sub {{ color:{MUTED}; font-size:{FS_XS}px; }}
.snow-runmeta {{ color:{MUTED}; font-size:{FS_XS}px; padding-top: 6px; }}

/* page header */
.snow-eyebrow {{ color:{MUTED}; font-size:{FS_XS}px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
    margin-bottom:2px; }}
.snow-title {{ color:{INK}; font-size:{FS_XL + 2}px; font-weight:600; letter-spacing:-0.01em; margin:0; }}
.snow-subtitle {{ color:{MUTED}; font-size:{FS_SM}px; margin:4px 0 {SPACE['md']}px 0; max-width: 900px; }}

/* KPI tiles */
.snow-kpis {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:{SPACE['md']}px;
    margin: 0 0 {SPACE['md']}px 0; }}
.snow-kpi {{ border-radius:{RADIUS_CARD}px; padding:{SPACE['md'] + 4}px {SPACE['lg']}px; }}
.snow-kpi .lbl {{ color:{INK}; font-size:{FS_SM}px; font-weight:600; }}
.snow-kpi .val {{ color:{INK}; font-size:{FS_XL}px; font-weight:600; margin-top:8px; line-height:1.15;
    overflow-wrap:anywhere; }}
.snow-kpi .sub {{ color:{INK_80}; font-size:{FS_XS}px; margin-top:4px; }}

/* pills, legend, finding cards */
.snow-pill {{ display:inline-block; padding:2px 10px; border-radius:{RADIUS_PILL}px; font-size:{FS_XS}px;
    font-weight:600; line-height:18px; }}
.snow-legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; color:{INK_80}; font-size:{FS_XS}px; margin:4px 0 8px; }}
.snow-legend span.dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px;
    vertical-align:-1px; }}
.snow-finding {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:{RADIUS_CARD}px; padding:{SPACE['md']}px {SPACE['md'] + 4}px;
    height:100%; }}
.snow-finding .tag {{ color:{MUTED}; font-size:{FS_XS}px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }}
.snow-finding .head {{ color:{INK}; font-size:{FS_MD}px; font-weight:600; margin:6px 0 4px; line-height:1.3; }}
.snow-finding .body {{ color:{INK_80}; font-size:{FS_SM}px; line-height:1.45; }}

/* pipeline (bank path in time order) */
.pipe {{ display:flex; align-items:stretch; gap:0; overflow-x:auto; padding:4px 2px 8px; }}
.pipe .blk {{ border-radius:{RADIUS_CARD}px; padding:12px 14px; min-width:170px; max-width:260px; flex: 0 0 auto; }}
.pipe .blk.mid {{ flex: 1 1 auto; max-width:none; min-width:220px; background:{CANVAS}; border:1px dashed {FAINT}; }}
.pipe .blk.mid.empty {{ flex: 0 1 240px; align-self: center; }}
.pipe .blk.entry {{ background:#E9F7F1; border:1px solid {ENTRY}; }}
.pipe .blk.exit {{ background:#FFEDED; border:1px solid {EXIT}; }}
.pipe .blk .k {{ font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }}
.pipe .blk.entry .k {{ color:{ENTRY}; }} .pipe .blk.exit .k {{ color:{EXIT}; }} .pipe .blk.mid .k {{ color:{MUTED}; }}
.pipe .bank {{ color:{INK}; font-weight:600; font-size:{FS_SM}px; margin-top:6px; line-height:1.25; }}
.pipe .meta {{ color:{INK_80}; font-size:{FS_XS}px; margin-top:2px; }}
.pipe .arrow {{ align-self:center; color:{FAINT}; font-size:22px; padding:0 8px; flex:0 0 auto; }}
.pipe .hops {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; align-items:center; }}
.pipe .hop {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:10px; padding:6px 10px; min-width:120px; }}
.pipe .hop .bank {{ margin-top:0; font-size:13px; }}
.pipe .hop.sel, .pipe .blk.sel {{ box-shadow: 0 0 0 2px {INK}; }}
.pipe .chev {{ color:{FAINT}; font-size:14px; }}
.pipe details summary {{ cursor:pointer; color:{INK_80}; font-size:{FS_XS}px; margin-top:8px; }}
</style>
"""


def apply() -> None:
    """Inject the shared CSS. Call once per run (Home.py does this before the page runs)."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- components
def esc(x) -> str:
    return html.escape(str(x))


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    st.markdown(
        (f'<div class="snow-eyebrow">{esc(eyebrow)}</div>' if eyebrow else "")
        + f'<div class="snow-title">{esc(title)}</div>'
        + (f'<div class="snow-subtitle">{subtitle}</div>' if subtitle else '<div style="height:12px"></div>'),
        unsafe_allow_html=True)


_TILE_TINTS = [TINT_BLUE, TINT_PURPLE]


def kpi_row(items) -> None:
    """items: list of (label, value, sub) tuples. Tiles alternate the two SnowUI tints."""
    tiles = []
    for i, it in enumerate(items):
        label, value, sub = (list(it) + [""])[:3]
        tiles.append(f'<div class="snow-kpi" style="background:{_TILE_TINTS[i % 2]}">'
                     f'<div class="lbl">{esc(label)}</div><div class="val">{esc(value)}</div>'
                     + (f'<div class="sub">{esc(sub)}</div>' if sub else "") + "</div>")
    st.markdown(f'<div class="snow-kpis">{"".join(tiles)}</div>', unsafe_allow_html=True)


def pill(text: str, color: str, fg: str = "#FFFFFF") -> str:
    return f'<span class="snow-pill" style="background:{color};color:{fg}">{esc(text)}</span>'


def legend(items) -> None:
    """items: list of (colour, label)."""
    st.markdown('<div class="snow-legend">' + "".join(
        f'<span><span class="dot" style="background:{c}"></span>{esc(lbl)}</span>' for c, lbl in items)
        + "</div>", unsafe_allow_html=True)


def finding(tag: str, headline: str, body: str) -> None:
    st.markdown(f'<div class="snow-finding"><div class="tag">{esc(tag)}</div>'
                f'<div class="head">{esc(headline)}</div><div class="body">{body}</div></div>',
                unsafe_allow_html=True)


def section(title: str, caption: str = "") -> None:
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)
