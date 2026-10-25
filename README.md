# IS459 Group 7: BQ1 Pipeline (Account Prioritisation)

This pipeline turns raw IBM AML transactions into a **daily ranked alert list**
using our own **weighted risk score**, then checks the score against the
`Is Laundering` label.

```
Kaggle CSV
   |
   v
S3 raw/  --Glue Job 1-->  S3 clean/ (Parquet, by date)  --Glue Job 2-->  S3 curated/ (account-day scores)
                                                                              |
                                                       Glue Crawler -> Glue Data Catalog
                                                                              |
                                                                Athena (top N, validation)
                                                                              |
                                                                Streamlit on EC2 (dashboard)

Step Functions runs Job 1 -> Job 2 -> Crawler -> Athena query in one click.
```

## What is in this folder

| File | What it does |
|---|---|
| `glue_jobs/01_ingest_clean.py` | Reads the raw CSV, fixes column names, parses timestamps, builds account keys (bank + account), writes Parquet partitioned by date |
| `glue_jobs/02_account_risk_scoring.py` | One row per account per day, the 7 behaviours, 0-1 percentile scores, weighted risk score, daily rank |
| `config/weights.json` | Our weight table (must add up to 100). Change weights here, no code changes needed |
| `athena/01 to 05 *.sql` | Alert list, capacity curve, payment format check, weight validation, baseline comparison |
| `orchestration/state_machine.json` | Step Functions definition (X-factor: automation) |
| `streamlit/bq1_dashboard.py` | Dashboard: capacity slider, recall/precision, capacity curve, behaviour points, alert list |
| `tests/` | Small synthetic dataset and a local Spark test (already run successfully) |

## How the score works

For each account on each day:

1. Calculate 7 behaviours: fan-out, pass-through, fan-in, cross-currency share,
   cross-bank share, activity spike, payment format risk.
2. Convert each to a 0-1 score = the account's percentile rank among all
   accounts that day (so different units become comparable).
3. `Risk Score = 100 x SUM(weight x score)` using `config/weights.json`.
4. Rank accounts per day. Investigators review the top N.

Notes on the behaviours:
- **Pass-through** compares money in vs money out on the same day, within
  each currency (so no exchange rates are needed). 1.0 means everything
  received was sent out again.
- **Activity spike** compares today's number of transactions with the
  account's average day.
- **Ground truth:** an account-day is labelled laundering if any of its
  transactions that day has `Is Laundering = 1`. It is used only to check
  the score, never to calculate it.

## Deploy step by step

Use **HI-Small** for building and testing, then **HI-Medium** for the real run.
Region below assumes `us-east-1`. Change it if your account uses another.

### Step 1: S3 bucket and files (Week 4 lab skills)
1. Create one bucket, e.g. `is459-g7-aml-<yourname>`, with these folders:
   `raw/`, `clean/`, `curated/`, `config/`, `scripts/`, `athena-results/`
2. Download `HI-Small_Trans.csv` (and later `HI-Medium_Trans.csv`) from Kaggle
   and upload to `raw/`.
3. Upload `config/weights.json` to `config/`.

### Step 2: IAM role for Glue
- AWS Academy Learner Lab: use the existing `LabRole`.
- Project IAM account: create a role for Glue with `AWSGlueServiceRole` plus
  read/write access to your bucket.

### Step 3: Glue Job 1 (ingest and clean)
1. Glue > ETL jobs > Script editor > Spark > paste `01_ingest_clean.py`.
2. Name: `is459-bq1-01-ingest-clean`. Glue version 5.0, worker type G.1X,
   **2 workers for HI-Small, 5 for HI-Medium**, timeout 30 minutes.
3. Job parameters:
   - `--RAW_PATH` = `s3://<bucket>/raw/HI-Small_Trans.csv`
   - `--CLEAN_PATH` = `s3://<bucket>/clean/transactions/`
4. Run it and check that date folders appear in `clean/transactions/`.

### Step 4: Glue Job 2 (risk scoring)
1. New script job, paste `02_account_risk_scoring.py`.
2. Name: `is459-bq1-02-risk-scoring`, same settings as Job 1.
3. Job parameters:
   - `--CLEAN_PATH` = `s3://<bucket>/clean/transactions/`
   - `--CURATED_PATH` = `s3://<bucket>/curated/account_day_scores/`
   - `--CONFIG_PATH` = `s3://<bucket>/config/weights.json`
4. Run it and check `curated/account_day_scores/`.

### Step 5: Glue crawlers and Data Catalog
1. Create database `is459_aml`.
2. Crawler `is459-bq1-clean-crawler` on `s3://<bucket>/clean/transactions/`
   (creates table `transactions`).
3. Crawler `is459-bq1-curated-crawler` on `s3://<bucket>/curated/account_day_scores/`
   (creates table `account_day_scores`).
4. Run both crawlers.

### Step 6: Athena (validation and insights)
Set the query result location to `s3://<bucket>/athena-results/`, then run:
1. `03_payment_format_check.sql`: pick the high-lift formats and update
   `high_risk_payment_formats` in `weights.json`. Re-upload it and rerun Job 2.
2. `02_capacity_curve.sql`: recall and precision at each daily limit.
3. `04_weight_validation.sql`: do laundering accounts score higher on each
   behaviour? Which behaviours drive the alerts we caught?
4. `05_baseline_comparison.sql`: our score vs a simple "most transactions" rule.
5. `01_daily_alert_list.sql`: the alert list for one day.

### Step 7: Step Functions (automation, X-factor)
1. Replace `<BUCKET>` in `orchestration/state_machine.json`.
2. Step Functions > Create state machine > Code > paste the JSON.
3. The execution role needs permission to start the Glue jobs and crawler,
   run Athena queries and write to the results folder (Learner Lab: `LabRole`).
4. Optional: an EventBridge schedule to run it daily.

### Step 8: Streamlit dashboard on EC2 (Week 5 lab skills)
1. Same EC2 setup as the Week 5 lab (port 8501 open, AWS credentials configured).
2. `pip install streamlit boto3 pandas`
3. Edit `BUCKET` and `REGION` at the top of `bq1_dashboard.py`.
4. `streamlit run bq1_dashboard.py --server.address 0.0.0.0 --server.port 8501`

## Tuning the weights
1. Edit `config/weights.json` (keep the total at 100).
2. Upload it to `s3://<bucket>/config/`.
3. Rerun Job 2 (or the Step Functions pipeline), then rerun the Athena checks.
4. If you tune weights based on results, tune on the earlier days and confirm
   on the later days so the result is not over-fitted.
5. Also update the weights inside `04_weight_validation.sql` part (b).

## Cost controls (budget USD 250)
- Develop on HI-Small with 2 workers. Only switch to HI-Medium once it works.
- Set a job timeout (30 minutes) on every Glue job.
- Parquet + date partitions keep Athena scans small.
- Stop the EC2 instance when the dashboard is not in use.
- Avoid Glue notebooks left running. If you use one, set `%idle_timeout 30`.
- Delete all resources after the Week 14 presentation, as the brief requires.

## Suggested split for the demo (everyone presents one part)
| Member | Component |
|---|---|
| 1 | S3 zones + Glue Job 1 (ingestion and cleaning) |
| 2 | Glue Job 2 (behaviours and weighted score) |
| 3 | Crawlers + Athena validation (capacity curve, weight check) |
| 4 | Step Functions automation |
| 5 | Streamlit dashboard |

## Things to verify before the final run
- `high_risk_payment_formats` in `weights.json` (default `ACH` is a placeholder
  until you run `03_payment_format_check.sql`).
- The weight values themselves (agree them as a team).
- The date in `01_daily_alert_list.sql` matches a date in your dataset.
- Job worker counts and run times on HI-Medium (record them for the
  cost/performance evidence).
