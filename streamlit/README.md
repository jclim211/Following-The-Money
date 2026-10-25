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

## Hosted version (EC2)
- Link: http://54.83.81.34:8501 (the address changes if the server is stopped and started again)
- Server: EC2 t3.micro `is459-g7-dashboard` in us-east-1, IAM role `is459-g7-dashboard-role` (Athena read, is459-g7 bucket only), security group `is459-g7-dashboard-sg` (port 8501 only).
- **To change the dashboard:** edit `streamlit/app.py`, then commit and push to `main`. The server pulls `main` every 2 minutes and restarts Streamlit when there is a new commit. No AWS console steps needed.
- Test before pushing: run it locally (above) so a broken push does not take the demo down.
- Save budget: stop the instance in the EC2 console when it is not needed (about USD 12/month if always on, under USD 1/month stopped).
- Admin: Session Manager (EC2 > Connect > Session Manager). Logs: `journalctl -u bq1-dashboard -u bq1-update`.

## Settings
Environment variables: `BQ1_AWS_PROFILE` (default `is459`, set to empty on EC2 to use the instance role) and `BQ1_REGION` (default `us-east-1`).
