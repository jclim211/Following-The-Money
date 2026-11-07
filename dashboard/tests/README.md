# Dashboard test helpers

These are helper scripts and mock data, not an automated test suite.

| File | What |
|---|---|
| `make_mock_athena.py` | Writes random, correctly shaped CSVs into `mock_athena/` so the UI can be run without AWS. Never present them as results |
| `mock_athena/bq2/dashboard/` | Mock results of the BQ2 queries |
| `mock_athena/bq1/dashboard/` | Mock results of the BQ1 queries. The main page currently uses `../data_bq1/` instead in mock mode |
| `mock_athena/runs.json`, `mock_athena/uploads.json` | A saved list of finished runs and uploads for the home page (written by hand, not by the script) |
| `athena_smoke.py` | Needs AWS: runs the BQ1 queries on Athena and prints time, data scanned and results |

## Preview the dashboard without AWS

From `dashboard/`:

```
DASHBOARD_MOCK_DIR=tests/mock_athena BQ1_DATA_SOURCE=csv streamlit run Home.py
```

Windows PowerShell: `$env:DASHBOARD_MOCK_DIR="tests/mock_athena"; $env:BQ1_DATA_SOURCE="csv"; streamlit run Home.py`
