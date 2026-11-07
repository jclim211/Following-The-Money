# Following the Money: context for the team

IS459 Big Data Architecture, Group 7. IBM AML transactions (HI-Medium).
Read this first if you are new to the repo or using Claude/Copilot on it.

- **BQ1** (account risk prioritisation): which accounts should investigators review first under limited daily capacity, and which behaviours matter?
- **BQ2** (laundering networks): how do laundering networks move funds differently from normal transactions, and which banks are disproportionate entry and exit points?

## Repo layout

```
README.md               project overview and "where to find what" (start here)
context.md              this file
dashboard/              ONE Streamlit app for both BQs (deployed to EC2), see dashboard/README.md
  Home.py               entry point: main page + two classic pages
  common/ui.py, ui/frontend/index.html   the main page (custom component)
  common/ui_data.py     data for the main page (stored Athena queries, run in parallel)
  common/athena.py      shared AWS session and run_query(name, params, database, folder)
  common/pipeline.py, common/runs.py     uploads, Start button, finished runs
  common/pipeline_view.py                pipeline progress view, SAMPLE data for now
  pages/                classic BQ1 and BQ2 pages (/classic-bq1, /classic-bq2)
  bq1_data.py, data_bq1/, validate.py    BQ1 helpers, CSV export of the original tables, data checks
  tests/                mock data for running without AWS
  requirements.txt      add any new Python package here (server installs it on deploy)
  run_dashboard.bat     run locally on Windows
pipeline/               copies of s3://is459-g7-projectbucket/scripts/, see pipeline/README.md
  shared/clean.py       raw CSV -> clean Parquet partitioned by day
  bq1/account_profiles.py, bq1/risk_scoring.py
  bq2/schemes.py, bq2/bq2_analysis_v2.py
  orchestration/        Step Functions definition and roles
  queries/              stored Athena SQL the dashboard runs
deploy/                 how the EC2 server runs and updates the dashboard, IAM policies
infra/                  Terraform: the pipeline state machine, dashboard permission to start runs (see infra/README.md)
archive/                replaced versions (Glue jobs, old schema SQL, old dashboards), see archive/README.md. Not used.
```

## AWS resources (account 761018854594, us-east-1, shared with other teams)

Only touch resources named `is459-g7-*` or the bucket `is459-g7-projectbucket`.

| What | Where |
|---|---|
| S3 bucket | `is459-g7-projectbucket`: `raw/`, `clean/`, `curated/bq1/`, `curated/bq2/`, `metrics/`, `scripts/`, `athena-results/` |
| Spark jobs | EMR Serverless app `is459-g7-spark`, scripts in `s3://is459-g7-projectbucket/scripts/` |
| Glue databases | `aml_raw`, `aml_clean` (transactions, banks, fx_rates, schemes), `aml_curated` (BQ1 tables + view `bq1_investigator_queue`), `aml_metrics` |
| Athena | workgroup `primary`, results to `s3://is459-g7-projectbucket/athena-results/` |
| Pipeline | Step Functions `is459-g7-pipeline`, managed by Terraform in `infra/`. Upload to `runs/<run>/raw/{transactions,patterns,accounts}/`, then press Start on the dashboard home page. Uploads do not start runs on their own. |
| Dashboard server | EC2 t3.micro `is459-g7-dashboard`, role `is459-g7-dashboard-role`, SG `is459-g7-dashboard-sg` |

**Important:** `pipeline/` is a copy. EMR runs the files in S3 and the dashboard reads its SQL from `scripts/queries/`. If you change a job or a query, upload it to `scripts/` as well as committing it here.

## Data the dashboard reads

- BQ1 (`aml_curated`): `risk_rankings` (one row per account per day, score, rank, points per behaviour), `account_labels` (IsLaundering per account-day, evaluation only), `account_profiles` (raw behaviours), `capacity_evaluation`, `capacity_summary`.
- BQ2 (`aml_bq2_curated`, data in `curated/bq2/`): `flow_comparison`, `holding_time`, `scheme_profile`, `country_pairs`, `bank_entry_exit`, `scheme_edges`, plus `aml_clean.banks` and `aml_raw.raw_accounts` for bank size.
- The server can read `aml_curated`, `aml_bq2_curated`, `aml_clean`, `aml_raw`, `aml_metrics` and run databases named `aml_hi_*` (see `deploy/README.md`). A new database needs adding to the role's policy (copies in `deploy/iam/`, ask Jie Ching).

## Do I need AWS access?

| You want to | AWS access needed? |
|---|---|
| Edit a page and push to GitHub | **No.** The server reads Athena with its own IAM role. To preview on the live site, someone has to start the server (see "How deploys work"). |
| Run the dashboard on your own laptop | **Yes**, for real data: the app reads Athena from your laptop (one-time setup below). **No** for a layout preview with mock data (`dashboard/tests/README.md`). |
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

1. SQL lives in `pipeline/queries/` and in S3 `scripts/queries/`, not in the page. Add the `.sql` file in both places, then run it by name:
   ```python
   from common.athena import run_query
   df = run_query("capacity_summary", database="aml_curated", folder="bq1/dashboard")
   ```
   Values in braces in the SQL (for example `{profile_date}`) are filled from the `params` dict.
2. Main page: add the screen to `ui/frontend/index.html` and its data to `common/ui_data.py`. Classic page: add a file to `dashboard/pages/` and register it in `Home.py` with `st.Page(...)` (the number prefix alone does nothing, navigation is set in `Home.py`).
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
