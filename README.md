# Following the Money (IS459 Group 7)

A big data pipeline and dashboard on AWS for the IBM Transactions for Anti Money Laundering
dataset (Kaggle, HI-Small and HI-Medium files).

## Business questions

- **BQ1, account risk prioritisation:** investigators can only review a fixed number of accounts
  a day. Which accounts should they review first, and which behaviours matter most?
- **BQ2, laundering networks:** how do laundering networks move funds differently from normal
  transactions, and which banks are disproportionate entry and exit points?

The `Is Laundering` label is used only to evaluate results, never as a scoring input.

## Architecture

```
 S3 runs/<run>/raw/           transactions CSV, Patterns.txt, accounts CSV
        |
 Step Functions  is459-g7-pipeline   (pipeline/orchestration/is459-g7-pipeline.asl.json)
        |
        |-- EMR Serverless Spark: shared/clean.py           raw CSV -> clean Parquet (by day), banks, fx rates
        |-- in parallel:
        |     BQ1: bq1/account_profiles.py -> bq1/risk_scoring.py    profiles, scores, ranks, capacity results
        |     BQ2: bq2/schemes.py -> bq2/bq2_analysis_v2.py          schemes, flows, holding time, entry/exit banks
        |-- Glue crawler          catalogues the Parquet output as a Glue database per run
        |-- Athena                country lookup and dashboard view for BQ1
        |-- run.json              written last, marks the run as finished
        |
 Athena (stored queries in pipeline/queries/)
        |
 Streamlit dashboard on EC2 is459-g7-dashboard   (dashboard/, deployed from GitHub main)
```

All resources are in AWS account 761018854594, region us-east-1. Every resource is named
`is459-g7-*`; the bucket is `is459-g7-projectbucket`.

## Where to find what

| I want to see... | File or folder |
|---|---|
| Data cleaning rules | [pipeline/shared/clean.py](pipeline/shared/clean.py) (rules in the header) |
| BQ1 behaviour profiles (fan-in, fan-out, pass-through, ...) | [pipeline/bq1/account_profiles.py](pipeline/bq1/account_profiles.py) |
| BQ1 risk score, weights, daily ranking and capacity evaluation | [pipeline/bq1/risk_scoring.py](pipeline/bq1/risk_scoring.py) |
| BQ1 indicator check (drop one behaviour at a time) | [pipeline/bq1/athena/indicator_validation.sql](pipeline/bq1/athena/indicator_validation.sql), [pipeline/queries/bq1/analysis/](pipeline/queries/bq1/analysis/) |
| BQ1 data quality checks | [pipeline/queries/bq1/checks/](pipeline/queries/bq1/checks/), [dashboard/validate.py](dashboard/validate.py) |
| BQ2 scheme parsing (Patterns.txt) | [pipeline/bq2/schemes.py](pipeline/bq2/schemes.py) |
| BQ2 analysis tables | [pipeline/bq2/bq2_analysis_v2.py](pipeline/bq2/bq2_analysis_v2.py) |
| Orchestration (Step Functions) | [pipeline/orchestration/](pipeline/orchestration/) |
| Every SQL query the dashboard runs | [pipeline/queries/](pipeline/queries/) |
| Dashboard code | [dashboard/](dashboard/) |
| Infrastructure as code (Terraform) | [infra/](infra/) |
| How the EC2 server runs and updates the dashboard, IAM policies | [deploy/](deploy/) |
| Earlier versions we replaced (Glue jobs, first dashboard) | [archive/](archive/) |
| Team guide: AWS resources, local setup, deploy rules, cost | [context.md](context.md) |

## Repository layout

```
README.md            this file
context.md           team guide (setup, AWS resources, deploy rules, cost)
pipeline/            everything that runs in AWS: Spark jobs, Step Functions, SQL   (pipeline/README.md)
dashboard/           Streamlit app (dashboard/README.md)
infra/               Terraform for the state machine and the dashboard's permission to start runs
deploy/              EC2 server scripts, systemd units and IAM policies
archive/             replaced code, kept to show how the project evolved, not used (archive/README.md)
```

## Run it

- **Dashboard:** EC2 instance `is459-g7-dashboard`, `http://<public IPv4>:8501`. The server is
  stopped when not in use and its IP changes on every start (see [context.md](context.md)).
- **Locally:** see "Run the dashboard locally" in [context.md](context.md). To preview the layout
  without AWS, use the mock data in [dashboard/tests/](dashboard/tests/).
- **A new pipeline run:** see [infra/README.md](infra/README.md) ("Upload a run").
