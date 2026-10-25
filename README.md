# Following the Money (IS459 Group 7)

Big data pipeline and dashboard for the IBM AML transactions dataset.

```
raw CSV (S3) -> EMR Serverless Spark (clean, profiles, scoring, schemes) -> S3 Parquet
   -> Glue Data Catalog -> Athena -> Streamlit dashboard on EC2
```

- Live dashboard: http://54.83.81.34:8501
- **Start here: [context.md](context.md)** for the repo layout, AWS resources, how to run locally and how deploys work.
- Dashboard code: [dashboard/](dashboard/) (BQ1 and BQ2 pages share one Athena helper)
- Spark jobs: [pipeline/](pipeline/)
- Server setup: [deploy/](deploy/)
