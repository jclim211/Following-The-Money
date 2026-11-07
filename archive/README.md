# Archive

Earlier versions that the current pipeline and dashboard replaced. Nothing here is run or
imported by the current code. It is kept to show how the design changed.

| Path | What it was | Replaced by |
|---|---|---|
| `glue_jobs/01_ingest_clean.py`, `02_account_risk_scoring.py` | First BQ1 pipeline as AWS Glue jobs | EMR Serverless Spark jobs in `pipeline/` |
| `config_old/weights.json` | BQ1 weight table read by the Glue scoring job | Weights in `pipeline/bq1/risk_scoring.py` |
| `orchestration/state_machine.json` | First Step Functions draft (Glue jobs, BQ1 only) | `pipeline/orchestration/is459-g7-pipeline.asl.json` |
| `athena_old_schema/` | Athena SQL for the first schema (`is459_aml`) | `pipeline/queries/` |
| `tests/make_sample.py`, `run_local.py` | Local Spark test of the Glue jobs on a small synthetic CSV | Job metrics and the checks in `pipeline/queries/bq1/checks/` |
| `bq1_dashboard_old_schema.py` | First BQ1 Streamlit dashboard, on the old schema | `dashboard/` |
| `bq2_starter_page.py` | Starter BQ2 page reading `aml_clean.schemes` | `dashboard/pages/2_BQ2_Cross_bank_movement.py` and the main page |
| `dashboard_pages/1_BQ1_Account_Risk.py` | BQ1 Account Risk page (capacity curve, drop-one-behaviour tab) | BQ1 Account Profiles page and the main page |
| `bq1_pilot/` | A teammate's standalone BQ1 dashboard (`app.py`) notes, changelog and sample data script, merged into the BQ1 Account Profiles page | `dashboard/pages/1_BQ1_Account_Profiles.py` |
| `ec2-userdata-initial.sh` | First EC2 setup, copied the app from S3 | Git based deploy in `deploy/` |
