# Dashboard

One Streamlit app for BQ1 and BQ2. Run, deploy and data details are in [../context.md](../context.md).

| File | What |
|---|---|
| `Home.py` | Landing page (entry point: `streamlit run Home.py`) |
| `common/athena.py` | Shared `run_query(sql, database)` with caching |
| `pages/1_BQ1_Account_Risk.py` | Investigator queue with why flagged, capacity vs detection vs baseline, score distribution, account drill-down |
| `pages/2_BQ2_Laundering_Networks.py` | Starter: schemes by type, entry and exit banks, scheme explorer |
| `requirements.txt` | Python packages (installed on the server at each deploy) |
| `run_dashboard.bat` | Run locally on Windows |
