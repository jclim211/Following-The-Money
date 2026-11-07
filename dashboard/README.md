# Dashboard

One Streamlit app for BQ1 and BQ2, deployed to EC2 `is459-g7-dashboard` from GitHub `main`.
Setup, deploy and AWS details are in [../context.md](../context.md).

## How it fits together

```
Home.py                      entry point (streamlit run Home.py)
 |-- main page  common/ui.py ----> ui/frontend/index.html   (the whole UI, one custom component)
 |                   |
 |                   |-- common/ui_data.py      Athena queries for BQ1/BQ2, run in parallel, cached 1 hour
 |                   |-- common/pipeline.py     uploaded runs and the Start button
 |                   |-- common/runs.py         finished runs (runs/<run>/run.json)
 |                   '-- common/pipeline_view.py  pipeline progress view (MOCK data for now)
 '-- classic pages  /classic-bq1, /classic-bq2   pages/1_..., pages/2_...  (earlier Streamlit layout)
```

The front end draws every screen and tells Python which one is open; Python fetches that
screen's data and passes it back. The open screen is kept in the URL as `?view=...`.
The SQL itself is not in this folder: it is in [../pipeline/queries/](../pipeline/queries/),
read from S3 at run time.

## Files

| File | What |
|---|---|
| `Home.py` | Entry point. Registers the main page and the two classic pages (navigation is hidden) |
| `common/ui.py` | Hosts `ui/frontend/index.html`, routes between screens, passes data in |
| `common/ui_data.py` | Data for the main page: BQ1 and BQ2 stored queries, original tables or a run |
| `common/athena.py` | Shared AWS session, `run_query(name, params, database, folder)` for stored queries |
| `common/pipeline.py` | Lists uploads under `runs/`, starts `is459-g7-pipeline` for a run |
| `common/runs.py` | Lists finished runs |
| `common/pipeline_view.py` | Pipeline progress and Spark job view. **Sample numbers only**, marked in the UI |
| `ui/frontend/index.html` | The front end (HTML, CSS and JavaScript in one file) |
| `pages/1_BQ1_Account_Profiles.py` | Classic BQ1 page: daily queue, capacity trade-off, methodology |
| `pages/2_BQ2_Cross_bank_movement.py` | Classic BQ2 page: flows, holding time, schemes, banks, network |
| `bq1_data.py` | BQ1 loading, schema checks and validation helpers (pandas only) |
| `validate.py` | Runs the BQ1 data checks from the command line: `python validate.py` |
| `data_bq1/` | CSV export of the original HI-Medium BQ1 queue (16 days x top 1,000) and capacity summary. Used when Athena is off (`BQ1_DATA_SOURCE=csv`) |
| `tests/` | Mock data and helper scripts ([tests/README.md](tests/README.md)) |
| `.streamlit/config.toml` | Theme |
| `requirements.txt` | Python packages, installed on the server at each deploy |
| `run_dashboard.bat` | Run locally on Windows |

## Add a screen or page

- Main page: add the screen to `ui/frontend/index.html` and its data to `common/ui_data.py`.
- Classic page: add the file to `pages/` **and** register it in `Home.py` with `st.Page(...)`;
  the number prefix alone does not add it, because navigation is set in `Home.py`.
- New SQL: add it under `pipeline/queries/`, upload it to the same path under
  `s3://is459-g7-projectbucket/scripts/queries/`, then call it by name.
