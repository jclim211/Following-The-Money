# Pipeline

Everything that runs in AWS. The Spark jobs and SQL here are copies of what is in
`s3://is459-g7-projectbucket/scripts/`; EMR and the dashboard run the S3 copies. If you change a
file here, upload it to the same path under `scripts/` too (checked identical on 7 Nov 2026).

| Folder | What | S3 copy |
|---|---|---|
| `shared/clean.py` | Step 1, both BQs: raw CSV to clean Parquet partitioned by day, plus `banks` and `fx_rates` | `scripts/shared/` |
| `bq1/account_profiles.py` | BQ1: one behaviour profile per account per day; labels written separately | `scripts/bq1/` |
| `bq1/risk_scoring.py` | BQ1: weighted risk score, daily rank, results at each daily capacity | `scripts/bq1/` |
| `bq1/athena/` | BQ1 SQL run by hand in Athena: dashboard preparation and the drop-one-behaviour test | not in S3 |
| `bq2/schemes.py` | BQ2: parses `Patterns.txt` into one row per scheme transfer | `scripts/bq2/` |
| `bq2/bq2_analysis_v2.py` | BQ2: flow comparison, holding time, scheme profile, country pairs, entry/exit banks, scheme edges | `scripts/bq2/` |
| `orchestration/` | Step Functions state machine and its IAM role ([orchestration/README.md](orchestration/README.md)) | deployed by `infra/` |
| `queries/` | Stored Athena queries the dashboard runs ([queries/README.md](queries/README.md)) | `scripts/queries/` |

Each job's header lists its inputs, outputs and rules.

## Order of a run

```
clean.py
  -> BQ1: account_profiles.py -> risk_scoring.py      (in parallel with)
     BQ2: schemes.py          -> bq2_analysis_v2.py
  -> Glue crawler -> Athena country lookup and dashboard view -> run.json
```

## Where the data goes

| Data | Original HI-Medium tables | A pipeline run `<run>` |
|---|---|---|
| Raw files | `raw/` | `runs/<run>/raw/{transactions,patterns,accounts}/` |
| Clean Parquet | `clean/` (Glue DB `aml_clean`) | `runs/<run>/clean/` |
| BQ1 output | `curated/bq1/` (Glue DB `aml_curated`) | `runs/<run>/curated/bq1/` |
| BQ2 output | `curated/bq2/` (Glue DB `aml_bq2_curated`) | `runs/<run>/curated/bq2/` |
| Job metrics (row counts, timings, checks) | `metrics/` (Glue DB `aml_metrics`) | `runs/<run>/metrics/` |

Each run gets its own Glue database (named `aml_hi_*`), so runs never overwrite each other or
the original tables.
