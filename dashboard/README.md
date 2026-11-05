# Dashboard

One Streamlit app for BQ1 and BQ2. Run, deploy and data details are in [../context.md](../context.md).

| File | What |
|---|---|
| `Home.py` | Entry point (`streamlit run Home.py`): top navigation, header bar with the dataset-run menu |
| `common/theme.py` | Design tokens (SnowUI style), shared CSS, Plotly and Altair chart themes, KPI tiles and cards. All colours live here |
| `common/ui.py` | Header bar with the run menu, and the shared Top 5 / 10 / 20 / All selector |
| `common/runs.py`, `runs.json` | Run registry (stub): which dataset runs exist and which Athena databases each one reads |
| `common/athena.py` | Shared `run_query()` for BQ1 (S3 .sql → Athena → S3 .csv), with caching |
| `common/bq2.py` | BQ2 queries (unchanged), scheme drawing, bank path pipeline, bank and scheme popups |
| `views/overview.py` | Landing page |
| `views/bq2_summary.py` | BQ2 summary: KPI tiles, headline findings, top banks and schemes |
| `views/bq2_banks.py` | Entry and exit banks (count and over-represented), banks used as both, network map |
| `views/bq2_schemes.py` | Scheme list and scheme types |
| `views/bq2_routes.py` | Country routes: top routes and heatmap |
| `views/bq2_flows.py` | Laundering vs normal: payment format, border, conversion, holding time |
| `views/bq1_account_risk.py` | BQ1 investigator queue, capacity vs detection, indicators, score distribution, drill-down |
| `views/bq1_pilot_queue.py` | BQ1 pilot queue from Athena, CSV exports in `data_bq1/` as fallback (helpers in `bq1_data.py`) |
| `views/manage_runs.py` | List, remove and restore runs |
| `requirements.txt` | Python packages (installed on the server at each deploy) |
| `run_dashboard.bat` | Run locally on Windows |

## Pages and navigation

Pages live in `views/` and are registered in `Home.py` (`st.navigation`, menu at the top). A new page is a new
file in `views/` plus one `st.Page(...)` line in `Home.py`. Start each page with
`theme.page_header(...)` and take colours from `common/theme.py`, never hard-coded hex values.
BQ2 pages end with `bq2.show_popups()` so a clicked bank or scheme opens in a popup.

## Dataset runs

A run is the whole pipeline (BQ1 and BQ2) on one dataset. The menu in the header lists every run in `runs.json`,
and every page reads the Athena databases of the selected run (`run.db("bq1")`, `run.db("bq2")`).
Run 1 is the current HI-Medium data and points at the existing databases, so nothing about the data changed.

**Add a run** (once the per-run pipeline writes each run to its own databases):
1. Run the pipeline on the new dataset.
2. Add an entry to `runs.json` with `run_id`, the dataset `name`, `created_at`, `status`, `period`, its
   `databases` (`bq1`, `bq2`, `clean`) and its `s3_prefix`.
3. Push to `main`. The run appears in the header menu.

**Delete a run:** Runs > Manage runs, pick the run, type its dataset name, press Delete run. This removes it from
the dashboard (stored in `dashboard/.state/`, not in git) and logs it; it can be restored on the same page.
Ticking "Also delete its S3 outputs and Athena tables" is a dry run for now: the planned deletion is logged and
nothing in AWS changes. To connect it, implement `delete_data` in `common/runs.py` once runs have their own
storage.

## Run locally without AWS (UI work only)

```
python tests/make_mock_athena.py
DASHBOARD_MOCK_DIR=tests/mock_athena BQ1_DATA_SOURCE=csv streamlit run Home.py
```
The mock numbers are random. Never use them as results.
