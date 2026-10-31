# Dashboard

One Streamlit app for BQ1 and BQ2. Run, deploy and data details are in [../context.md](../context.md).

| File | What |
|---|---|
| `Home.py` | Landing page (entry point: `streamlit run Home.py`) |
| `common/athena.py` | Shared `run_query(sql, database)` with caching |
| `pages/1_BQ1_Account_Risk.py` | Investigator queue with why flagged, capacity vs detection vs baseline, score distribution, account drill-down |
| `pages/2_BQ2_Cross_bank_movement.py` | BQ2: cross-bank movement, holding time, scheme profiles, entry and exit banks, network view (aml_bq2_curated) |
| `pages/3_BQ1_Pilot_Queue.py` | BQ1 pilot queue, capacity trade-off and methodology from CSV exports in `data_bq1/` (helpers in `bq1_data.py`) |
| `requirements.txt` | Python packages (installed on the server at each deploy) |
| `run_dashboard.bat` | Run locally on Windows |
