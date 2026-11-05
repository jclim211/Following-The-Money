"""Manage runs: see every dataset run, remove one from the dashboard, restore it."""
import pandas as pd
import streamlit as st

from common import theme
from common.runs import read_log, registry

theme.page_header("Manage runs",
                  "Each run is the whole pipeline (BQ1 and BQ2) on one dataset. Runs listed here appear in the "
                  "menu at the top.", eyebrow="Runs")
reg = registry()
runs = reg.list_runs()

if runs:
    st.dataframe(pd.DataFrame([{"Run": f"Run {i + 1}", "Dataset": r.name, "Created": r.created_at,
                                "Status": r.status, "Data period": r.period,
                                "Databases": ", ".join(f"{k}: {v}" for k, v in r.databases.items())}
                               for i, r in enumerate(runs)]), width="stretch", hide_index=True)
else:
    st.info("No runs are registered. Restore one below, or add one to runs.json (see README).")

with st.container(border=True):
    st.markdown("#### Delete a run")
    st.caption("Step 1 removes the run from the dashboard (registry only). Step 2, deleting its S3 outputs and "
               "Athena tables, is not connected yet: per-run storage is still being built, so nothing in AWS "
               "is deleted. The planned deletion is written to the log instead.")
    if runs:
        rid = st.selectbox("Run", [r.run_id for r in runs], key="del_run",
                           format_func=lambda i: next(r.name for r in runs if r.run_id == i))
        run = reg.get(rid)
        typed = st.text_input(f"Type the dataset name to confirm: **{run.name}**", key=f"del_typed_{rid}")
        also_data = st.checkbox("Also delete its S3 outputs and Athena tables", key=f"del_data_{rid}",
                                help="Second confirmation. Dry run until per-run storage exists.")
        if also_data:
            st.warning("This would delete: " + "; ".join(reg.planned_targets(run))
                       + ". Not connected yet, so this is logged as a dry run and nothing in AWS changes.")
        if st.button("Delete run", type="primary", disabled=typed.strip() != run.name):
            reg.remove(rid)
            planned = reg.delete_data(run) if also_data else []
            st.session_state.pop("run_id", None)
            st.toast(f"Removed {run.name} from the dashboard" + (" (data deletion logged as dry run)" if planned else ""))
            st.rerun()

hidden = reg.deleted_runs()
if hidden:
    with st.container(border=True):
        st.markdown("#### Removed runs")
        for r in hidden:
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"**{r.name}** · created {r.created_at}")
            if c2.button("Restore", key=f"restore_{r.run_id}", width="stretch"):
                reg.restore(r.run_id)
                st.rerun()

log = read_log()
if log:
    with st.expander("Deletion log"):
        st.code("\n".join(log), language=None)
