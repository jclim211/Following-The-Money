"""Shared page furniture: the run bar at the top, the two-level menu, "up next", and the top-N selector."""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from common import theme
from common.runs import RUN_KEY, registry

STATUS_COLORS = {"succeeded": theme.GREEN, "running": theme.BLUE, "failed": theme.RED}


@dataclass
class Section:
    title: str
    short: str
    icon: str
    pages: list            # st.Page objects, in menu order


# ---------------------------------------------------------------- run bar
def top_bar(manage_page=None):
    """Dark bar at the very top: brand, the dataset-run menu, its status. Returns the selected Run (or None)."""
    runs = registry().list_runs()
    ids = [r.run_id for r in runs]
    if ids and st.session_state.get(RUN_KEY) not in ids:
        st.session_state[RUN_KEY] = ids[0]
    by_id = {r.run_id: r for r in runs}

    with st.container(key="topbar"):
        c_brand, c_run, c_meta, c_manage = st.columns([2.9, 3.4, 2.7, 1.5], vertical_alignment="center")
        c_brand.markdown(f'<div class="rv-brand"><div class="logo">{theme.icon("currency_exchange", "#FFFFFF", 24)}</div>'
                         '<div><div class="name">Following the Money</div>'
                         '<div class="sub">IS459 Group 7 · anti-money-laundering analytics</div></div></div>',
                         unsafe_allow_html=True)
        if not runs:
            c_run.markdown('<div class="rv-runmeta">No dataset runs registered</div>', unsafe_allow_html=True)
            return None
        with c_run:
            st.selectbox("Dataset run", ids, key=RUN_KEY, label_visibility="collapsed",
                         format_func=lambda i: f"Run {ids.index(i) + 1} · {by_id[i].name}",
                         help="Each run is the whole pipeline (BQ1 + BQ2) on one dataset. "
                              "Every page shows the run picked here.")
        run = by_id[st.session_state[RUN_KEY]]
        c_meta.markdown(f'<div class="rv-runmeta">{theme.pill(run.status, STATUS_COLORS.get(run.status, theme.GREY))}'
                        f'<div class="per"><div class="l">Data period</div>'
                        f'<div class="v">{theme.esc(run.period or run.created_at)}</div></div></div>',
                        unsafe_allow_html=True)
        if manage_page is not None:
            c_manage.page_link(manage_page, label="Manage runs", icon=":material/tune:")
    return run


# ---------------------------------------------------------------- menu
def _flat(sections):
    return [(s, p) for s in sections for p in s.pages]


def menu(sections: list[Section], current) -> None:
    """Big section tabs, then the current section's pages, where you are, and the next page to visit."""
    cur_sec = next((s for s in sections if any(p.title == current.title for p in s.pages)), sections[0])

    with st.container(key="mainnav"):
        cols = st.columns([len(s.title) + 10 for s in sections])   # wider tabs for longer names
        for i, (col, sec) in enumerate(zip(cols, sections)):
            on = sec is cur_sec
            with col.container(key=f"navon_{i}" if on else f"nav_{i}"):
                st.page_link(sec.pages[0], label=sec.title, icon=sec.icon)

    flat = _flat(sections)
    idx = next(i for i, (_, p) in enumerate(flat) if p.title == current.title)
    nxt = flat[idx + 1] if idx + 1 < len(flat) else None
    next_label = ""
    if nxt is not None:   # name the section too when "next" leaves the current one
        next_label = f"Next: {nxt[1].title}" if nxt[0] is cur_sec else f"Next: {nxt[0].short} · {nxt[1].title}"

    with st.container(key="subnav"):
        n = len(cur_sec.pages)
        next_w = len(next_label) + 9 if nxt is not None else 1
        if n > 1:   # width follows the label length so nothing is cut off
            page_w = [len(p.title) + 9 for p in cur_sec.pages]
            widths = page_w + [max(1, 125 - sum(page_w) - next_w), next_w]
        else:
            widths = [60, max(1, 125 - 60 - next_w), next_w]
        cols = st.columns(widths, vertical_alignment="center")
        if n > 1:
            for i, p in enumerate(cur_sec.pages):
                with cols[i].container(key=f"subon_{i}" if p.title == current.title else f"sub_{i}"):
                    st.page_link(p, label=p.title, icon=p.icon)
        else:
            crumb = (f'<b>{theme.esc(current.title)}</b> · start here, then follow "Next"' if current.title == cur_sec.short
                     else f'{theme.esc(cur_sec.short)} › <b>{theme.esc(current.title)}</b>')
            cols[0].markdown(f'<div class="rv-crumb">{crumb}</div>', unsafe_allow_html=True)
        if nxt is not None:
            with cols[-1].container(key="subnext"):
                st.page_link(nxt[1], label=next_label, icon=":material/arrow_forward:")


def up_next(sections: list[Section], current) -> None:
    """Card at the bottom of each page pointing to the next page."""
    flat = _flat(sections)
    idx = next((i for i, (_, p) in enumerate(flat) if p.title == current.title), None)
    if idx is None:
        return
    if idx + 1 < len(flat):
        sec, page = flat[idx + 1]
        label = f"{sec.short} · {page.title}"
    else:
        sec, page = flat[0]
        label = "Back to the overview"
    with st.container(key="upnext"):
        c1, c2 = st.columns([5, 2], vertical_alignment="center")
        c1.markdown(f'<div class="rv-h">{theme.chip("east", theme.BLUE, 36)}<div><div class="c">Up next</div>'
                    f'<div class="t">{theme.esc(label)}</div></div></div>', unsafe_allow_html=True)
        with c2:
            st.page_link(page, label="Continue", icon=":material/arrow_forward:")


# ---------------------------------------------------------------- top N
TOPN_OPTIONS = ["Top 5", "Top 10", "Top 20", "All"]
_TOPN_STATE = "_top_n_choice"   # survives page switches (widget keys do not)


def top_n(key: str, label: str = "Show") -> int | None:
    """5 / 10 / 20 / All selector, default Top 5, shared across pages. Returns N, or None for All."""
    current = st.session_state.get(_TOPN_STATE, "Top 5")
    wkey = f"topn_{key}"
    if st.session_state.get(wkey) != current:
        st.session_state[wkey] = current

    def _sync():
        val = st.session_state.get(wkey)
        st.session_state[_TOPN_STATE] = val or "Top 5"

    choice = st.segmented_control(label, TOPN_OPTIONS, key=wkey, on_change=_sync,
                                  label_visibility="collapsed") or "Top 5"
    return None if choice == "All" else int(choice.split()[1])


def head(df, n):
    return df if n is None else df.head(n)
