# Deploy (EC2 dashboard server)

Server: EC2 t3.micro `is459-g7-dashboard` (Amazon Linux 2023, us-east-1).

| File | On the server | Purpose |
|---|---|---|
| `update.sh` | `/opt/bq1/update.sh` | Every 2 minutes: fetch `main`, and if there is a new commit install requirements and restart Streamlit |
| `run.sh` | `/opt/bq1/run.sh` | Starts Streamlit from `/opt/bq1/repo/dashboard/Home.py` on port 8501 |
| `systemd/bq1-dashboard.service` | `/etc/systemd/system/` | Keeps Streamlit running and starts it on boot |
| `systemd/bq1-update.service`, `bq1-update.timer` | `/etc/systemd/system/` | Runs `update.sh` every 2 minutes |
| `iam-dashboard-policy.json` | role `is459-g7-dashboard-role` | Read-only Athena/Glue for aml_curated, aml_clean, aml_metrics, S3 read, write only to athena-results/streamlit/ |
| `iam-trust-ec2.json` | same role | Lets EC2 use the role |

- Code is cloned at `/opt/bq1/repo` with a read-only GitHub deploy key (`/root/.ssh/bq1_deploy`).
- Changes to files in this folder are not applied automatically; copy them to the server (Session Manager) and run `systemctl daemon-reload`.
