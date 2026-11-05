"""
Design tokens and shared UI pieces for every dashboard page.

Revolut-style design system: white cards on a light grey canvas, a near-black top bar,
bold Inter type with tight tracking, large rounded corners, one strong primary blue for
everything you can click, and a vivid accent palette (indigo, purple, pink, orange,
yellow, green, red, teal) with a soft tint of each for icon chips and callouts.

Rules the pages follow:
  * Clickable = blue. Buttons and links are blue pills (solid for the main action, soft
    blue for the rest); list rows you can click get a chevron and turn blue on hover.
    Nothing that is not clickable uses the primary blue as a fill.
  * Information = white cards, black text, a coloured icon chip.
  * Charts are at most about a quarter of the screen (CHART_H tall, half width) and can
    be zoomed (Plotly) or opened full screen (hover, then the expand icon).

Every colour, size and radius used by the pages comes from here. To restyle the app,
change the tokens below (and .streamlit/config.toml, which mirrors the base colours).
"""
from __future__ import annotations

import html

import altair as alt
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------- tokens
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"

# Neutrals
INK = "#191C1F"          # text, top bar
INK_80 = "#3A4048"       # body text
MUTED = "#5F6872"        # secondary text (AA on white)
FAINT = "#B8BFC8"        # disabled, dotted lines
LINE = "#E3E6EA"         # borders, dividers
GRID = "#EDEFF2"         # chart gridlines
SURFACE = "#FFFFFF"      # cards
CANVAS = "#F4F5F7"       # page background

# Primary (clickable things only)
BLUE = "#0666EB"
BLUE_DARK = "#0450BD"
BLUE_SOFT = "#E7F0FF"

# Accents, each with a soft tint for chips and callouts
INDIGO, INDIGO_SOFT = "#494FDF", "#ECEDFC"
PURPLE, PURPLE_SOFT = "#8B5CF6", "#F2ECFE"
PINK, PINK_SOFT = "#E8457C", "#FDECF2"
ORANGE, ORANGE_SOFT = "#FF7A00", "#FFF1E3"
YELLOW, YELLOW_SOFT = "#F2B200", "#FFF7DA"
GREEN, GREEN_SOFT = "#00A36C", "#E2F6EE"
RED, RED_SOFT = "#E5484D", "#FDECEC"
TEAL, TEAL_SOFT = "#0E9FB3", "#E1F4F7"
GREY, GREY_SOFT = "#8A94A0", "#EFF1F4"
SOFT = {BLUE: BLUE_SOFT, INDIGO: INDIGO_SOFT, PURPLE: PURPLE_SOFT, PINK: PINK_SOFT, ORANGE: ORANGE_SOFT,
        YELLOW: YELLOW_SOFT, GREEN: GREEN_SOFT, RED: RED_SOFT, TEAL: TEAL_SOFT, GREY: GREY_SOFT}

# Semantic roles used across BQ2 (entry = where money goes in, exit = where it leaves)
ENTRY = GREEN
EXIT = RED
BOTH = ORANGE
MIDDLE = GREY
SELECTED = YELLOW
LAUNDERING = RED
NORMAL = INDIGO

# Old names kept so older code keeps working
S_GREEN, S_RED, S_YELLOW, S_BLUE, S_PURPLE, S_GREY = GREEN, RED, YELLOW, BLUE, PURPLE, GREY
TINT_BLUE, TINT_PURPLE = BLUE_SOFT, INDIGO_SOFT

CATEGORICAL = [BLUE, PURPLE, PINK, ORANGE, TEAL, GREEN, YELLOW, INDIGO, RED, GREY]
SEQUENTIAL_RED = ["#FFF0F0", "#FFC2C4", "#FF8F94", "#F0565C", "#C42A30"]
GRADIENT = f"linear-gradient(120deg, {BLUE} 0%, {INDIGO} 55%, {PURPLE} 100%)"

# Type scale (px), spacing (px), radii
FS_XS, FS_SM, FS_MD, FS_LG, FS_XL, FS_2XL, FS_3XL = 12, 14, 16, 18, 22, 28, 36
SPACE = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}
RADIUS_CARD, RADIUS_SM, RADIUS_PILL = 20, 12, 999
SHADOW = "0 1px 2px rgba(25,28,31,0.04), 0 4px 16px rgba(25,28,31,0.04)"

CHART_H = 260            # default chart height: about a quarter of a laptop screen with half width

# ---------------------------------------------------------------- chart themes
_PLOTLY = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, size=FS_XS, color=INK_80),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=CATEGORICAL, height=CHART_H,
    margin=dict(l=8, r=8, t=24, b=8),
    xaxis=dict(gridcolor=GRID, zeroline=False, linecolor=LINE, tickcolor=LINE, title_font=dict(size=FS_XS)),
    yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=LINE, tickcolor=LINE, title_font=dict(size=FS_XS)),
    hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(family=FONT, size=FS_XS, color="#FFFFFF")),
    legend=dict(font=dict(size=FS_XS, color=INK_80), bgcolor="rgba(0,0,0,0)"),
    bargap=0.3,
))
pio.templates["revo"] = _PLOTLY
pio.templates.default = "plotly_white+revo"


def _altair_theme():
    return {"config": {
        "background": "transparent",
        "font": FONT,
        "view": {"stroke": "transparent", "continuousHeight": CHART_H - 40},
        "range": {"category": CATEGORICAL},
        "axis": {"labelColor": INK_80, "titleColor": MUTED, "labelFontSize": FS_XS, "titleFontSize": FS_XS,
                 "titleFontWeight": 500, "labelLimit": 220, "gridColor": GRID, "domainColor": LINE, "tickColor": LINE},
        "legend": {"labelColor": INK_80, "titleColor": MUTED, "labelFontSize": FS_XS, "titleFontSize": FS_XS,
                   "symbolType": "circle"},
        "bar": {"cornerRadiusEnd": 4, "fill": BLUE},
        "line": {"stroke": BLUE, "strokeWidth": 2.5},
        "point": {"fill": BLUE},
        "header": {"labelColor": INK_80, "titleColor": MUTED},
    }}


try:  # Altair 5.5+
    @alt.theme.register("revo", enable=True)
    def _revo_theme():
        return alt.theme.ThemeConfig(_altair_theme())
except AttributeError:  # older Altair
    alt.themes.register("revo", _altair_theme)
    alt.themes.enable("revo")

# ---------------------------------------------------------------- CSS
_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,1,0&display=block');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {{ font-family: {FONT}; }}
.stApp, [data-testid="stAppViewContainer"] {{ background: {CANVAS} !important; }}
header[data-testid="stHeader"] {{ background: transparent; pointer-events: none; }}
header[data-testid="stHeader"] button, header[data-testid="stHeader"] [data-testid="stToolbar"] {{ pointer-events: auto; }}
.block-container {{ padding-top: 2.6rem !important; padding-bottom: 3rem; max-width: 1400px; }}
[data-testid="stButtonGroup"] [data-testid="stTooltipIcon"] button {{ border: none !important; background: transparent !important; }}
h1, h2, h3, h4 {{ color: {INK}; font-weight: 700; letter-spacing: -0.02em; }}
h4 {{ font-size: {FS_LG}px !important; }}
p, li {{ color: {INK_80}; }}
[data-testid="stCaptionContainer"], .stCaption, [data-testid="stCaptionContainer"] p {{ color: {MUTED}; }}
.ms {{ font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; font-size: 22px;
    line-height: 1; letter-spacing: normal; text-transform: none; display: inline-block; white-space: nowrap;
    direction: ltr; -webkit-font-smoothing: antialiased; font-feature-settings: 'liga'; vertical-align: middle; }}

/* ---------- cards ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: {RADIUS_CARD}px !important; }}
[data-testid="stExpander"] details {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; border: 1px solid {LINE}; }}
[data-testid="stExpander"] summary p {{ font-weight: 600; color: {INK}; }}
[data-testid="stExpander"] summary:hover p {{ color: {BLUE}; }}
[data-testid="stMetric"] {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; padding: 16px 20px;
    box-shadow: {SHADOW}; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: {FS_SM}px; font-weight: 500; }}
[data-testid="stMetricValue"] {{ color: {INK}; font-size: {FS_XL + 2}px; font-weight: 800; letter-spacing: -0.02em; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border-radius: {RADIUS_SM}px; overflow: hidden;
    border: 1px solid #CBD2DA; background: {SURFACE}; }}
[data-testid="stAlert"] {{ border-radius: {RADIUS_SM + 4}px; }}
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
/* tabs = a row of pills: white with a border, black when selected (works for react-aria and baseweb tabs) */
[data-testid="stTabs"] [role="tablist"] {{ gap: 8px; border-bottom: none !important; box-shadow: none !important;
    flex-wrap: wrap; padding: 2px 0 6px; }}
[data-testid="stTabs"] [role="tab"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: {RADIUS_PILL}px;
    padding: 8px 16px !important; min-height: 40px; cursor: pointer; transition: background .15s, border-color .15s; }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: {FS_SM}px; font-weight: 600; color: {INK_80}; }}
[data-testid="stTabs"] [role="tab"]:hover {{ background: {BLUE_SOFT}; border-color: {BLUE}; }}
[data-testid="stTabs"] [role="tab"]:hover p {{ color: {BLUE}; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background: {INK}; border-color: {INK}; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: #FFFFFF; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"],
[data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none !important; }}
hr {{ border-color: {LINE}; }}

/* bordered containers = white cards */
.st-key-card, [class*="st-key-card_"] {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; padding: 20px 22px;
    box-shadow: {SHADOW}; }}

/* ---------- buttons: clickable = blue ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ border-radius: {RADIUS_PILL}px;
    font-weight: 600; border: none; background: {BLUE_SOFT}; color: {BLUE}; min-height: 40px; padding: 0 18px;
    transition: background .15s, color .15s; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ background: {BLUE}; color: #FFFFFF; }}
.stButton > button p, .stDownloadButton > button p {{ font-weight: 600; color: inherit; }}
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {{ background: {BLUE};
    color: #FFFFFF; }}
.stButton > button[kind="primary"]:hover {{ background: {BLUE_DARK}; }}
.stButton > button:disabled {{ background: {GREY_SOFT}; color: {FAINT}; }}

/* ranked list rows (keys rank_*): a clickable row with a chevron */
[class*="st-key-rank_"] button {{ background: {SURFACE}; color: {INK}; border: 1px solid {LINE};
    border-radius: 14px; min-height: 46px; justify-content: flex-start; padding: 0 40px 0 14px; position: relative; }}
[class*="st-key-rank_"] button div {{ justify-content: flex-start; text-align: left; width: 100%; }}
[class*="st-key-rank_"] button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500;
    color: {INK}; }}
[class*="st-key-rank_"] button::after {{ content: 'chevron_right'; font-family: 'Material Symbols Rounded';
    font-size: 22px; color: {BLUE}; position: absolute; right: 12px; top: 50%; transform: translateY(-50%); }}
[class*="st-key-rank_"] button strong {{ font-weight: 800; color: {INK}; }}
[class*="st-key-rank_"] button:hover {{ background: {BLUE_SOFT}; border-color: {BLUE}; }}
[class*="st-key-rank_"] button:hover p {{ color: {BLUE}; }}

/* page links = blue text pills */
[data-testid="stPageLink-NavLink"] {{ border-radius: {RADIUS_PILL}px; padding: 6px 14px; background: {BLUE_SOFT};
    width: fit-content; transition: background .15s; }}
[data-testid="stPageLink-NavLink"] p, [data-testid="stPageLink-NavLink"] span {{ color: {BLUE} !important;
    font-weight: 600; }}
[data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE}; }}
[data-testid="stPageLink-NavLink"]:hover p, [data-testid="stPageLink-NavLink"]:hover span {{ color: #FFFFFF !important; }}

/* segmented controls (Top 5 / 10 / 20 / All etc.) */
[data-testid="stButtonGroup"] button[kind^="segmented"], [data-testid="stButtonGroup"] button[kind^="pills"] {{ border-radius: {RADIUS_PILL}px !important; border: 1px solid {LINE} !important;
    background: {SURFACE}; margin-right: 6px; min-height: 36px; padding: 0 14px; }}
[data-testid="stButtonGroup"] button p {{ font-weight: 600; color: {INK_80}; }}
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"],
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: {INK} !important; border-color: {INK} !important; }}
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] p,
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #FFFFFF; }}
[data-testid="stButtonGroup"] button:hover {{ border-color: {BLUE} !important; }}

/* ---------- top bar (run menu) ---------- */
.st-key-topbar {{ background: {INK}; border-radius: {RADIUS_CARD}px; padding: 12px 18px; margin-bottom: 4px; }}
.st-key-topbar p, .st-key-topbar span {{ color: #FFFFFF; }}
.st-key-topbar [data-baseweb="select"] > div, .st-key-topbar [data-testid="stSelectbox"] [role="group"]
    {{ background: #2B3036 !important; border: 1px solid #444C55 !important; border-radius: {RADIUS_PILL}px !important;
    min-height: 46px; padding-left: 8px; }}
.st-key-topbar [data-baseweb="select"] div, .st-key-topbar [data-baseweb="select"] span,
.st-key-topbar [data-testid="stSelectbox"] input {{ color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF;
    font-weight: 600 !important; font-size: {FS_MD}px !important; background: transparent !important; }}
.st-key-topbar [data-baseweb="select"] svg, .st-key-topbar [data-testid="stSelectbox"] svg {{ fill: #FFFFFF !important;
    color: #FFFFFF !important; }}
.st-key-topbar [data-testid="stSelectbox"] [role="group"]:hover {{ border-color: {BLUE} !important; }}
/* full-width page links inside menus and cards */
.st-key-mainnav [data-testid="stElementContainer"], .st-key-mainnav .stPageLink, .st-key-mainnav .stPageLink > div,
.st-key-subnav [data-testid="stElementContainer"], .st-key-subnav .stPageLink, .st-key-subnav .stPageLink > div,
[class*="st-key-card_q"] [data-testid="stElementContainer"], [class*="st-key-card_q"] .stPageLink,
[class*="st-key-card_q"] .stPageLink > div {{ width: 100% !important; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"], .st-key-subnav [data-testid="stPageLink-NavLink"],
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"] {{ width: 100% !important; max-width: none !important; }}
.st-key-topbar [data-testid="stPageLink-NavLink"] {{ background: #2B3036; }}
.st-key-topbar [data-testid="stPageLink-NavLink"] p, .st-key-topbar [data-testid="stPageLink-NavLink"] span
    {{ color: #FFFFFF !important; }}
.st-key-topbar [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE}; }}
.rv-brand {{ display:flex; align-items:center; gap:12px; }}
.rv-brand .logo {{ width:40px; height:40px; border-radius:12px; background:{GRADIENT}; color:#fff; display:flex;
    align-items:center; justify-content:center; }}
.rv-brand .name {{ font-weight:700; color:#fff; font-size:{FS_MD}px; line-height:1.15; letter-spacing:-0.01em; }}
.rv-brand > div {{ min-width: 0; }}
.rv-brand .sub {{ color:#AEB6BF; font-size:{FS_XS}px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.rv-runmeta {{ display:flex; align-items:center; gap:10px; color:#AEB6BF; font-size:{FS_SM - 1}px; min-width:0; }}
.rv-runmeta .per {{ min-width:0; line-height:1.2; }}
.rv-runmeta .per .l {{ color:#8B95A1; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; }}
.rv-runmeta .per .v {{ color:#E6E9ED; font-size:{FS_SM - 1}px; font-weight:600; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; }}
.rv-runlbl {{ color:#AEB6BF; font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
    margin-bottom:-6px; }}

/* ---------- main menu: big section tabs ---------- */
.st-key-mainnav {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; padding: 8px; box-shadow: {SHADOW}; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"] {{ width: 100%; justify-content: center; background: transparent;
    border-radius: 14px; min-height: 52px; padding: 8px 12px; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"] p {{ color: {INK} !important; font-size: {FS_MD}px; font-weight: 700; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"] span {{ color: {INK} !important; font-size: 22px; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE_SOFT}; }}
.st-key-mainnav [data-testid="stPageLink-NavLink"]:hover p,
.st-key-mainnav [data-testid="stPageLink-NavLink"]:hover span {{ color: {BLUE} !important; }}
.st-key-mainnav [class*="st-key-navon_"] [data-testid="stPageLink-NavLink"] {{ background: {INK}; }}
.st-key-mainnav [class*="st-key-navon_"] [data-testid="stPageLink-NavLink"] p,
.st-key-mainnav [class*="st-key-navon_"] [data-testid="stPageLink-NavLink"] span {{ color: #FFFFFF !important; }}

/* ---------- sub menu: pages of the current section ---------- */
.st-key-subnav {{ padding: 6px 2px 0; }}
.st-key-subnav [data-testid="stPageLink-NavLink"] {{ width: 100%; justify-content: center; background: {SURFACE};
    border: 1px solid {LINE}; min-height: 42px; }}
.st-key-subnav [data-testid="stPageLink-NavLink"] p {{ color: {INK_80} !important; font-weight: 600; }}
.st-key-subnav [data-testid="stPageLink-NavLink"] span {{ color: {INK_80} !important; }}
.st-key-subnav [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE_SOFT}; border-color: {BLUE}; }}
.st-key-subnav [data-testid="stPageLink-NavLink"]:hover p,
.st-key-subnav [data-testid="stPageLink-NavLink"]:hover span {{ color: {BLUE} !important; }}
.st-key-subnav [class*="st-key-subon_"] [data-testid="stPageLink-NavLink"] {{ background: {BLUE}; border-color: {BLUE}; }}
.st-key-subnav [class*="st-key-subon_"] [data-testid="stPageLink-NavLink"] p,
.st-key-subnav [class*="st-key-subon_"] [data-testid="stPageLink-NavLink"] span {{ color: #FFFFFF !important; }}
.st-key-subnav [class*="st-key-subnext"] [data-testid="stPageLink-NavLink"] {{ background: {INK}; border-color: {INK}; }}
.st-key-subnav [class*="st-key-subnext"] [data-testid="stPageLink-NavLink"] p,
.st-key-subnav [class*="st-key-subnext"] [data-testid="stPageLink-NavLink"] span {{ color: #FFFFFF !important; }}
.st-key-subnav [class*="st-key-subnext"] [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE}; }}
.rv-crumb {{ color:{MUTED}; font-size:{FS_SM}px; font-weight:600; padding-top:10px; white-space:nowrap; }}
.rv-crumb b {{ color:{INK}; }}

/* ---------- up next card ---------- */
.st-key-upnext {{ background: {SURFACE}; border-radius: {RADIUS_CARD}px; padding: 18px 22px; box-shadow: {SHADOW};
    margin-top: 24px; }}
.st-key-upnext [data-testid="stPageLink-NavLink"] {{ background: {BLUE}; padding: 10px 20px; }}
.st-key-upnext [data-testid="stPageLink-NavLink"] p, .st-key-upnext [data-testid="stPageLink-NavLink"] span
    {{ color: #FFFFFF !important; }}
.st-key-upnext [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE_DARK}; }}
.st-key-upnext [data-testid="stColumn"]:last-child [data-testid="stElementContainer"] {{ width: 100% !important; }}
.st-key-upnext .stPageLink, .st-key-upnext .stPageLink > div {{ display: flex; justify-content: flex-end;
    align-items: flex-end; width: 100%; }}

/* ---------- page header ---------- */
.rv-eyebrow {{ color:{BLUE}; font-size:{FS_XS}px; font-weight:700; letter-spacing:.07em; text-transform:uppercase;
    margin: 18px 0 4px; }}
.rv-title {{ color:{INK}; font-size:{FS_3XL - 4}px; font-weight:800; letter-spacing:-0.025em; margin:0; line-height:1.15; }}
.rv-subtitle {{ color:{MUTED}; font-size:{FS_MD - 1}px; margin:6px 0 18px 0; max-width: 920px; line-height:1.45; }}

/* ---------- KPI tiles ---------- */
.rv-kpis {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:14px; margin: 0 0 18px 0; }}
.rv-kpi {{ background:{SURFACE}; border-radius:{RADIUS_CARD}px; padding:16px 18px; box-shadow:{SHADOW};
    display:flex; flex-direction:column; gap:2px; }}
.rv-kpi .top {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.rv-kpi .lbl {{ color:{MUTED}; font-size:{FS_SM - 1}px; font-weight:600; line-height:1.2; }}
.rv-kpi .val {{ color:{INK}; font-size:{FS_XL + 2}px; font-weight:800; letter-spacing:-0.02em; line-height:1.15;
    overflow-wrap:anywhere; }}
.rv-kpi .sub {{ color:{MUTED}; font-size:{FS_XS}px; margin-top:2px; }}
.rv-chip {{ width:36px; height:36px; border-radius:12px; display:inline-flex; align-items:center; justify-content:center;
    flex: 0 0 auto; }}
.rv-chip .ms {{ font-size:20px; }}

/* ---------- callouts, pills, legend, findings ---------- */
.rv-take {{ display:flex; gap:14px; align-items:flex-start; border-radius:{RADIUS_CARD}px; padding:16px 20px;
    margin: 0 0 18px 0; }}
.rv-take .head {{ color:{INK}; font-size:{FS_MD + 1}px; font-weight:700; line-height:1.35; letter-spacing:-0.01em; }}
.rv-take .body {{ color:{INK_80}; font-size:{FS_SM}px; margin-top:2px; line-height:1.45; }}
.rv-pill {{ display:inline-block; padding:3px 11px; border-radius:{RADIUS_PILL}px; font-size:{FS_XS}px;
    font-weight:700; line-height:18px; }}
.rv-legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; color:{INK_80}; font-size:{FS_SM - 1}px; margin:2px 0 10px;
    font-weight:500; }}
.rv-legend span.dot {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:7px;
    vertical-align:-1px; }}
.rv-finding {{ background:{SURFACE}; border-radius:{RADIUS_CARD}px; padding:18px 20px; box-shadow:{SHADOW};
    min-height: 212px; margin-bottom: 8px; }}
.rv-finding .tag {{ color:{MUTED}; font-size:{FS_XS}px; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
    margin-top:12px; }}
.rv-finding .head {{ color:{INK}; font-size:{FS_MD + 1}px; font-weight:700; margin:4px 0 6px; line-height:1.3;
    letter-spacing:-0.01em; }}
.rv-finding .body {{ color:{INK_80}; font-size:{FS_SM}px; line-height:1.45; }}
.rv-h {{ display:flex; align-items:center; gap:10px; margin: 6px 0 10px; }}
.rv-h .t {{ color:{INK}; font-size:{FS_LG + 1}px; font-weight:700; letter-spacing:-0.015em; }}
.rv-h .c {{ color:{MUTED}; font-size:{FS_SM - 1}px; font-weight:500; }}

/* ---------- landing page ---------- */
.rv-hero {{ background:{GRADIENT}; border-radius:28px; padding:34px 38px; color:#fff; position:relative; overflow:hidden;
    margin-top: 18px; }}
.rv-hero:after {{ content:''; position:absolute; right:-80px; top:-80px; width:320px; height:320px; border-radius:50%;
    background: rgba(255,255,255,0.10); }}
.rv-hero .k {{ font-size:{FS_XS}px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; opacity:.85; }}
.rv-hero .t {{ font-size:40px; font-weight:800; letter-spacing:-0.03em; line-height:1.1; margin:8px 0 10px; max-width: 760px; }}
.rv-hero .s {{ font-size:{FS_MD}px; opacity:.92; max-width:720px; line-height:1.5; }}
.rv-hero .tags {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
.rv-hero .tag {{ background: rgba(255,255,255,0.18); border-radius:999px; padding:6px 12px; font-size:{FS_SM - 1}px;
    font-weight:600; }}
.rv-steps {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:14px; }}
.rv-step {{ background:{SURFACE}; border-radius:{RADIUS_CARD}px; padding:16px 18px; box-shadow:{SHADOW};
    display:flex; gap:12px; align-items:center; }}
.rv-step .n {{ color:{INK}; font-weight:700; font-size:{FS_SM + 1}px; }}
.rv-step .d {{ color:{MUTED}; font-size:{FS_XS + 1}px; line-height:1.35; }}
.rv-qcard-head {{ display:flex; gap:14px; align-items:center; margin-bottom:6px; }}
.rv-qcard-head .k {{ color:{MUTED}; font-size:{FS_XS}px; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }}
.rv-qcard-head .t {{ color:{INK}; font-size:{FS_XL}px; font-weight:800; letter-spacing:-0.02em; line-height:1.15; }}
.rv-qcard-q {{ color:{INK_80}; font-size:{FS_SM + 1}px; line-height:1.5; margin: 6px 0 14px; }}
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"] {{ width: 100%; background: {CANVAS}; border-radius: 14px;
    min-height: 50px; padding: 10px 16px; justify-content: flex-start; }}
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"] p {{ color: {INK} !important; font-size: {FS_MD - 1}px; }}
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"] span {{ color: {BLUE} !important; }}
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"]:hover {{ background: {BLUE_SOFT}; }}
[class*="st-key-card_q"] [data-testid="stPageLink-NavLink"]:hover p {{ color: {BLUE} !important; }}
[class*="st-key-card_q"] [data-testid="stCaptionContainer"] {{ margin: -10px 0 0 16px; }}
[class*="st-key-card_q"] [data-testid="stVerticalBlock"] {{ gap: 0.55rem; }}

/* ---------- pipeline (bank path in time order) ---------- */
.pipe {{ display:flex; align-items:stretch; gap:0; overflow-x:auto; padding:4px 2px 8px; }}
.pipe .blk {{ border-radius:{RADIUS_SM + 4}px; padding:12px 14px; min-width:170px; max-width:260px; flex: 0 0 auto; }}
.pipe .blk.mid {{ flex: 1 1 auto; max-width:none; min-width:220px; background:{CANVAS}; border:1.5px dashed {FAINT}; }}
.pipe .blk.mid.empty {{ flex: 0 1 240px; align-self: center; }}
.pipe .blk.entry {{ background:{GREEN_SOFT}; border:1.5px solid {ENTRY}; }}
.pipe .blk.exit {{ background:{RED_SOFT}; border:1.5px solid {EXIT}; }}
.pipe .blk .k {{ font-size:11px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }}
.pipe .blk.entry .k {{ color:{ENTRY}; }} .pipe .blk.exit .k {{ color:{EXIT}; }} .pipe .blk.mid .k {{ color:{MUTED}; }}
.pipe .bank {{ color:{INK}; font-weight:700; font-size:{FS_SM}px; margin-top:6px; line-height:1.25; }}
.pipe .meta {{ color:{INK_80}; font-size:{FS_XS}px; margin-top:2px; }}
.pipe .arrow {{ align-self:center; color:{GREY}; padding:0 6px; flex:0 0 auto; }}
.pipe .hops {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; align-items:center; }}
.pipe .hop {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:7px 11px; min-width:120px; }}
.pipe .hop .bank {{ margin-top:0; font-size:13px; }}
.pipe .hop.sel, .pipe .blk.sel {{ box-shadow: 0 0 0 3px {YELLOW}; }}
.pipe .chev {{ color:{FAINT}; }}
.pipe details summary {{ cursor:pointer; color:{BLUE}; font-weight:600; font-size:{FS_XS}px; margin-top:8px; }}
</style>
"""


def apply() -> None:
    """Inject the shared CSS. Home.py calls this once per run, before the page runs."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- components
def esc(x) -> str:
    return html.escape(str(x))


def icon(name: str, color: str = INK, size: int = 22) -> str:
    """A Material Symbols Rounded icon as HTML."""
    return f'<span class="ms" style="color:{color};font-size:{size}px">{esc(name)}</span>'


def chip(name: str, color: str = BLUE, size: int = 36) -> str:
    """Icon on a soft tinted square (Revolut-style)."""
    return (f'<span class="rv-chip" style="background:{SOFT.get(color, BLUE_SOFT)};width:{size}px;height:{size}px">'
            f'{icon(name, color, int(size * 0.56))}</span>')


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    st.markdown(
        (f'<div class="rv-eyebrow">{esc(eyebrow)}</div>' if eyebrow else '<div style="height:18px"></div>')
        + f'<div class="rv-title">{esc(title)}</div>'
        + (f'<div class="rv-subtitle">{subtitle}</div>' if subtitle else '<div style="height:14px"></div>'),
        unsafe_allow_html=True)


_KPI_COLORS = [BLUE, PURPLE, PINK, GREEN, RED, ORANGE, TEAL, INDIGO]


def kpi_row(items) -> None:
    """items: (label, value[, sub[, icon[, colour]]]) tuples. White tiles with a coloured icon chip."""
    tiles = []
    for i, it in enumerate(items):
        label, value, sub, ic, col = (list(it) + ["", "", ""])[:5]
        col = col or _KPI_COLORS[i % len(_KPI_COLORS)]
        top = f'<div class="top">{chip(ic, col)}<div class="lbl">{esc(label)}</div></div>' if ic else \
            f'<div class="lbl">{esc(label)}</div>'
        tiles.append(f'<div class="rv-kpi">{top}<div class="val">{esc(value)}</div>'
                     + (f'<div class="sub">{esc(sub)}</div>' if sub else "") + "</div>")
    st.markdown(f'<div class="rv-kpis">{"".join(tiles)}</div>', unsafe_allow_html=True)


def takeaway(headline: str, body: str = "", ic: str = "lightbulb", color: str = BLUE) -> None:
    """The one sentence a reader should leave the page with."""
    st.markdown(f'<div class="rv-take" style="background:{SOFT.get(color, BLUE_SOFT)}">{chip(ic, color, 40)}'
                f'<div><div class="head">{esc(headline)}</div>'
                + (f'<div class="body">{body}</div>' if body else "") + "</div></div>",
                unsafe_allow_html=True)


def pill(text: str, color: str, fg: str = "#FFFFFF") -> str:
    return f'<span class="rv-pill" style="background:{color};color:{fg}">{esc(text)}</span>'


def soft_pill(text: str, color: str) -> str:
    return f'<span class="rv-pill" style="background:{SOFT.get(color, GREY_SOFT)};color:{color}">{esc(text)}</span>'


def legend(items) -> None:
    """items: list of (colour, label)."""
    st.markdown('<div class="rv-legend">' + "".join(
        f'<span><span class="dot" style="background:{c}"></span>{esc(lbl)}</span>' for c, lbl in items)
        + "</div>", unsafe_allow_html=True)


def finding(tag: str, headline: str, body: str, ic: str = "insights", color: str = BLUE) -> None:
    st.markdown(f'<div class="rv-finding">{chip(ic, color, 40)}<div class="tag">{esc(tag)}</div>'
                f'<div class="head">{esc(headline)}</div><div class="body">{body}</div></div>',
                unsafe_allow_html=True)


def section(title: str, caption: str = "", ic: str = "", color: str = BLUE) -> None:
    """Card heading with an optional icon chip."""
    st.markdown(f'<div class="rv-h">{chip(ic, color, 32) if ic else ""}<div><div class="t">{esc(title)}</div>'
                + (f'<div class="c">{caption}</div>' if caption else "") + "</div></div>",
                unsafe_allow_html=True)


def plotly_chart(fig, **kwargs):
    """st.plotly_chart with the house look.

    Streamlit paints its own background and font onto a Plotly figure unless the figure's layout sets them
    itself (the template is not enough), so they are set here explicitly."""
    if fig.layout.paper_bgcolor is None:
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    if fig.layout.plot_bgcolor is None:
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)")
    if fig.layout.font.family is None:
        fig.update_layout(font=dict(family=FONT, size=FS_XS, color=INK_80))
    kwargs.setdefault("theme", None)
    return st.plotly_chart(fig, **kwargs)


def card(key: str):
    """A white card container. Use as `with theme.card("card_x"):`; keys must start with card_."""
    return st.container(key=key if key.startswith("card") else f"card_{key}")
