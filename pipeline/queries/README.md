# Stored Athena queries

The dashboard does not hold SQL in its Python code. It reads these files from
`s3://is459-g7-projectbucket/scripts/queries/` and runs them in Athena (workgroup `primary`).
Values in braces, such as `{profile_date}` or `{top_n}`, are filled in by the dashboard
(`dashboard/common/athena.py`, `fill_placeholders`) from validated inputs only.

| Folder | Database | Used by |
|---|---|---|
| `bq1/dashboard/` | `aml_curated` (original HI-Medium tables) | BQ1 screens use `dashboard_queue` and `capacity_summary`. The other files served the old BQ1 Account Risk page (`archive/dashboard_pages/`) and are kept for reference |
| `bq1/checks/` | `aml_curated` | Data quality checks on the BQ1 tables (row counts, rank order, score sums, value ranges). Run by hand |
| `bq1/analysis/` | `aml_curated` | One-off analysis, such as the contribution of each behaviour to the catch rate |
| `bq2/dashboard/` | `aml_bq2_curated` | BQ2 screens: flows, holding time, schemes, entry and exit banks, network (`scheme_detail` is not used now) |
| `bq2/analysis/` | `aml_bq2_curated` | Top entry and exit banks |
| `run/` | the run's own database, `aml_<run>` | BQ1 and BQ2 pages for a pipeline run |

Copied from S3 on 7 Nov 2026. If you change a query, upload it to the same path in S3.
