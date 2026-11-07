# Orchestration (Step Functions)

The state machine `is459-g7-pipeline` runs one dataset end to end. Terraform in
[../../infra/](../../infra/) deploys these files, so change them here and run `terraform apply`.

| File | What |
|---|---|
| `is459-g7-pipeline.asl.json` | The state machine definition (Amazon States Language) |
| `pipeline-role-policy.json`, `pipeline-role-trust.json` | IAM role the state machine runs as: EMR Serverless jobs, passing the EMR job role, Glue, Athena |
| `trigger-event-pattern.json` | EventBridge pattern for uploads under `runs/`. Still read by `infra/main.tf`, which keeps the rule **disabled** |
| `trigger.py`, `trigger-role-policy.json`, `trigger-role-trust.json` | The old upload trigger (Lambda) and its role. Not used any more, kept for reference |

## Input

```json
{"run": "hi-small-4", "db": "aml_hi_small_4", "dataset": "HI-Small"}
```

The dashboard's Start button builds this input (`dashboard/common/pipeline.py`). All paths come
from `run`: `s3://is459-g7-projectbucket/runs/<run>/{raw,clean,curated,metrics}`.

## States

1. `SetPaths`: works out the S3 folders for the run.
2. `CreateDatabase`: Glue database `db` (already existing is fine).
3. `Clean`: EMR Serverless job `shared/clean.py`.
4. `RunBQ1AndBQ2` (parallel): `bq1/account_profiles.py` then `bq1/risk_scoring.py`, and
   `bq2/schemes.py` then `bq2/bq2_analysis_v2.py`.
5. `CreateCrawler`, `StartCrawler`, `WaitForCrawler`, `CheckCrawler`: Glue crawler catalogues the
   run's Parquet folders into `db`.
6. `BuildCountryLookup`, `CreateDashboardView`: Athena builds the BQ1 account country lookup and
   the `bq1_dashboard_queue` view.
7. `WriteRunRecord`: writes `runs/<run>/run.json` last. The dashboard lists a run as finished only
   when this file exists.

Failures are caught and end the run in `PipelineFailed`. To retry a run whose Spark jobs already finished, add
`"from_crawler": true` to the input and it starts at the crawler.
