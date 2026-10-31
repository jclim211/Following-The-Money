# Following the Money: context for the team

IS459 Big Data Architecture, Group 7. IBM AML transactions (HI-Medium).
Read this first if you are new to the repo or using Claude/Copilot on it.

- **BQ1** (account risk prioritisation): which accounts should investigators review first under limited daily capacity, and which behaviours matter?
- **BQ2** (laundering networks): how do laundering networks move funds differently from normal transactions, and which banks are disproportionate entry and exit points?

## Repo layout

```
context.md              this file
dashboard/              ONE Streamlit app for both BQs (deployed to EC2)
  Home.py               landing page
  common/athena.py      shared run_query(sql, database) with caching. Use this, do not write your own boto3 code.
  pages/1_BQ1_Account_Risk.py          BQ1 live from Athena: queue, capacity curve vs baseline, score distribution, drill-down
  pages/2_BQ2_Cross_bank_movement.py   BQ2 live from Athena (aml_bq2_curated): flows, holding time, schemes, banks, network
  pages/3_BQ1_Pilot_Queue.py           BQ1 pilot view from CSV exports in data_bq1/ (uses bq1_data.py)
  bq1_data.py, data_bq1/               helpers and CSV exports for page 3
  requirements.txt      add any new Python package here (server installs it on deploy)
  run_dashboard.bat     run locally on Windows
pipeline/               Spark jobs that run on EMR Serverless (copies of s3://is459-g7-projectbucket/scripts/)
  shared/clean.py       raw CSV -> clean Parquet partitioned by day
  bq1/account_profiles.py, bq1/risk_scoring.py
  bq2/schemes.py        Patterns.txt -> clean/schemes
deploy/                 how the EC2 server runs and updates the dashboard
archive/                old drafts (Glue jobs, old schema SQL, old dashboard). Not used.
```

## AWS resources (account 761018854594, us-east-1, shared with other teams)

Only touch resources named `is459-g7-*` or the bucket `is459-g7-projectbucket`.

| What | Where |
|---|---|
| S3 bucket | `is459-g7-projectbucket`: `raw/`, `clean/`, `curated/bq1/`, `curated/bq2/`, `metrics/`, `scripts/`, `athena-results/` |
| Spark jobs | EMR Serverless app `is459-g7-spark`, scripts in `s3://is459-g7-projectbucket/scripts/` |
| Glue databases | `aml_raw`, `aml_clean` (transactions, banks, fx_rates, schemes), `aml_curated` (BQ1 tables + view `bq1_investigator_queue`), `aml_metrics` |
| Athena | workgroup `primary`, results to `s3://is459-g7-projectbucket/athena-results/` |
| Dashboard server | EC2 t3.micro `is459-g7-dashboard`, role `is459-g7-dashboard-role`, SG `is459-g7-dashboard-sg` |

**Important:** `pipeline/` is a copy. EMR runs the files in S3. If you change a job, upload it to `scripts/` as well as committing it here.

## Data the dashboard reads

- BQ1 (`aml_curated`): `risk_rankings` (one row per account per day, score, rank, points per behaviour), `account_labels` (IsLaundering per account-day, evaluation only), `account_profiles` (raw behaviours), `capacity_evaluation`, `capacity_summary`.
- BQ2 (`aml_bq2_curated`, data in `curated/bq2/`): `flow_comparison`, `holding_time`, `scheme_profile`, `country_pairs`, `bank_entry_exit`, `scheme_edges`, plus `aml_clean.banks` and `aml_raw.raw_accounts` for bank size.
- The server can read `aml_curated`, `aml_bq2_curated`, `aml_clean`, `aml_raw` and `aml_metrics`. A new database needs adding to `deploy/iam-dashboard-policy.json` (ask Jie Ching).

## Do I need AWS access?

| You want to | AWS access needed? |
|---|---|
| Edit a page and push to GitHub | **No.** The server reads Athena with its own IAM role. To preview on the live site, someone has to start the server (see "How deploys work"). |
| Run the dashboard on your own laptop | **Yes.** The app reads Athena from your laptop, so it needs AWS credentials (one-time setup below). |
| Run or change EMR jobs, query Athena in the console | Yes, console sign-in. |

## Run the dashboard locally (Windows)

Set this up yourself, once per laptop:

1. Install AWS CLI v2 (version 2.32 or newer has `aws login`): https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html. Check with `aws --version`.
2. Sign in with the group's console login:
   ```
   aws login --profile is459 --region us-east-1
   ```
   A browser opens, sign in with the group IAM user, and the CLI saves short-lived credentials under profile `is459`. They last 12 hours; just run the same command again when they expire.
   Check it worked: `aws sts get-caller-identity --profile is459` should show account 761018854594.
3. First time only (from the `dashboard` folder):
   ```
   py -3.12 -m venv %USERPROFILE%\.venvs\is459-bq1
   %USERPROFILE%\.venvs\is459-bq1\Scripts\pip install -r requirements.txt
   ```
   (`requirements.txt` includes `botocore[crt]`, which Python needs to use `aws login` credentials.)
4. Run: double click `dashboard\run_dashboard.bat`, or `streamlit run Home.py` from `dashboard/`. Opens http://localhost:8501.
   If you see "expired" or "Unable to locate credentials", run step 2 again.

Mac: same steps with `python3 -m venv ~/.venvs/is459-bq1` and `~/.venvs/is459-bq1/bin/streamlit run Home.py`.

## Add or change a page

1. Use the shared helper (as `pages/1_BQ1_Account_Risk.py` does):
   ```python
   from common.athena import run_query
   df = run_query("SELECT ... FROM schemes", database="aml_clean")
   ```
2. New page = new file in `dashboard/pages/`. The number prefix sets the sidebar order.
3. Keep queries aggregated (GROUP BY, LIMIT). Athena charges by data scanned, and pages should load in seconds.
4. Test locally before pushing.

## How deploys work

**There is one dashboard server: `is459-g7-dashboard`. Deploy only by pushing to GitHub `main`.**
Do not copy files to `s3://is459-g7-projectbucket/scripts/dashboard/` or launch another EC2 for the dashboard. That S3 folder is old and no server reads it any more.
To get push access, accept the GitHub invite to `jclim211/Following-The-Money` (ask Jie Ching if you have none).

- The server is normally **stopped** to save budget. To use it: EC2 console > Instances > `is459-g7-dashboard` > Instance state > Start, wait about a minute, then open `http://<Public IPv4>:8501`. The Public IPv4 **changes on every start**, so copy it from the console each time. Stop it again when done.
- Push to `main` on GitHub. The server checks GitHub every 2 minutes (`deploy/update.sh`, run by a systemd timer). If there is a new commit it pulls, installs `dashboard/requirements.txt` and restarts Streamlit.
- A broken push breaks the live site, so test locally first. To roll back, revert the commit and push.
- Logs: EC2 console > `is459-g7-dashboard` > Connect > Session Manager, then `sudo journalctl -u bq1-dashboard -n 50` or `sudo journalctl -t bq1-update`.
- If you change files in `deploy/`, they are NOT applied automatically.

## Cost (project budget USD 250)

- Dashboard server: about USD 12/month if always on. Stop it in the EC2 console when not needed.
- Athena: about USD 5 per TB scanned. Dashboard queries are cached for an hour.
- Delete all `is459-g7-*` resources after the Week 14 presentation.

## House rules

- Never commit AWS keys, `.pem` files or passwords.
- The IsLaundering label is only for evaluation, never as a scoring input.
- Do not touch other teams' resources in the shared account.
