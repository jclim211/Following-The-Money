# Deploy (EC2 dashboard server)

Server: EC2 t3.micro `is459-g7-dashboard` (Amazon Linux 2023, us-east-1).

| File | On the server | Purpose |
|---|---|---|
| `update.sh` | `/opt/bq1/update.sh` | Every 2 minutes: fetch `main`, and if there is a new commit install requirements and restart Streamlit |
| `run.sh` | `/opt/bq1/run.sh` | Starts Streamlit from `/opt/bq1/repo/dashboard/Home.py` on port 8501 |
| `systemd/bq1-dashboard.service` | `/etc/systemd/system/` | Keeps Streamlit running and starts it on boot |
| `systemd/bq1-update.service`, `bq1-update.timer` | `/etc/systemd/system/` | Runs `update.sh` every 2 minutes |
| `iam/` | role `is459-g7-dashboard-role` | The role's policies, see below |

- Code is cloned at `/opt/bq1/repo` with a read-only GitHub deploy key (`/root/.ssh/bq1_deploy`).
- Changes to files in this folder are not applied automatically; copy them to the server (Session Manager) and run `systemctl daemon-reload`.

## IAM role `is459-g7-dashboard-role`

The files in `iam/` are copies of the role's inline policies, exported from IAM on 7 Nov 2026.
Editing them does not change AWS.

| File | Inline policy | Grants |
|---|---|---|
| `iam/trust-ec2.json` | trust policy | Lets EC2 use the role |
| `iam/is459-g7-dashboard-athena-read.json` | `is459-g7-dashboard-athena-read` | Athena in workgroup `primary`; Glue read for `aml_curated`, `aml_clean`, `aml_metrics`, `aml_bq2_curated`, `aml_raw`; S3 read of the data folders; writes to `athena-results/streamlit/` |
| `iam/is459-g7-dashboard-s3-flow.json` | `is459-g7-dashboard-s3-flow` | Read the stored queries `scripts/queries/*`; read and write `athena-results/*` |
| `iam/is459-g7-dashboard-runs.json` | `is459-g7-dashboard-runs` | Read `runs/*` and run databases named `aml_hi_*` |
| `iam/BQ1DashboardAthenaAccess.json` | `BQ1DashboardAthenaAccess` | An early broad policy: Athena and Glue on all resources, S3 read and write on the whole bucket. Mostly covered by the policies above, but it is also what lets the dashboard read a run whose name does not start with `hi-` (database not `aml_hi_*`). Before removing it, widen `is459-g7-dashboard-runs` |
| (in `infra/main.tf`) | `is459-g7-dashboard-pipeline` | List `runs/`, read `run.json`, start and list executions of `is459-g7-pipeline`. Managed by Terraform |

The role also has the AWS managed policy `AmazonSSMManagedInstanceCore` for Session Manager.
