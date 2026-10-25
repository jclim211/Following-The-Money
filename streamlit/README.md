# BQ1 Streamlit dashboard

`app.py` reads the live BQ1 outputs from Athena (Glue database `aml_curated`,
workgroup `primary`, region `us-east-1`). It only runs SELECT queries.
Query results are written to `s3://is459-g7-projectbucket/athena-results/streamlit/`.

`bq1_dashboard.py` is the older draft for the earlier schema (`is459_aml.account_day_scores`) and is no longer used.

## Tabs
1. **Investigator queue**: top N accounts for a chosen day, with "why flagged" (top 3 behaviours by points) and average points per behaviour.
2. **Capacity vs detection**: detection rate and precision for N = 50 to 2,000 per day, against the simple baseline (rank by transaction count). Pick held-out days in the sidebar.
3. **Score distribution**: risk scores of laundering vs normal accounts for the day, with the queue cut-off line.
4. **Account drill-down**: points per behaviour, score across days and the raw behavioural indicators.

## Run locally (Windows)
1. Sign in if needed: `aws login --profile is459`
2. First time only:
   ```
   py -3.12 -m venv %USERPROFILE%\.venvs\is459-bq1
   %USERPROFILE%\.venvs\is459-bq1\Scripts\pip install -r requirements.txt
   ```
3. Start it (or double click `run_dashboard.bat`):
   ```
   %USERPROFILE%\.venvs\is459-bq1\Scripts\streamlit run app.py
   ```
4. Open http://localhost:8501

First load takes about 30 seconds (several Athena queries). After that, results are cached for an hour.

## Settings
Environment variables: `BQ1_AWS_PROFILE` (default `is459`, set to empty on EC2 to use the instance role) and `BQ1_REGION` (default `us-east-1`).
