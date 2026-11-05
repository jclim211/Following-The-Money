"""Shared page furniture: the header bar with the run menu, and the top-N selector."""
from __future__ import annotations

import streamlit as st

from common import theme
from common.runs import RUN_KEY, registry

STATUS_COLORS = {"succeeded": theme.S_GREEN, "running": theme.S_BLUE, "failed": theme.S_RED}


def header_bar():
    """Brand on the left, run menu on the right. Returns the selected Run (or None)."""
    runs = registry().list_runs()
    ids = [r.run_id for r in runs]
    if ids and st.session_state.get(RUN_KEY) not in ids:
        st.session_state[RUN_KEY] = ids[0]

    left, mid, right = st.columns([3, 2, 2], vertical_alignment="center")
    with left:
        st.markdown('<div class="snow-brand"><div class="logo">FM</div><div>'
                    '<div class="name">Following the Money</div>'
                    '<div class="sub">IS459 Group 7 · AML analytics</div></div></div>',
                    unsafe_allow_html=True)
    if not runs:
        right.warning("No runs registered.")
        st.divider()
        return None
    by_id = {r.run_id: r for r in runs}
    with mid:
        st.selectbox("Dataset run", ids, key=RUN_KEY, label_visibility="collapsed",
                     format_func=lambda i: f"Run {ids.index(i) + 1} · {by_id[i].name}",
                     help="Each run is the whole pipeline (BQ1 + BQ2) on one dataset. "
                          "Every page shows the run picked here.")
    run = by_id[st.session_state[RUN_KEY]]
    with right:
        st.markdown(f'<div class="snow-runmeta">'
                    f'{theme.pill(run.status, STATUS_COLORS.get(run.status, theme.S_GREY))}'
                    f'&nbsp; {theme.esc(run.period or "created " + run.created_at)}</div>',
                    unsafe_allow_html=True)
    st.markdown(f'<hr style="margin:10px 0 18px 0;border:none;border-top:1px solid {theme.LINE}">',
                unsafe_allow_html=True)
    return run


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
