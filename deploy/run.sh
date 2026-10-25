#!/bin/bash
# Installed on the EC2 server as /opt/bq1/run.sh and started by bq1-dashboard.service.
if [ -f /opt/bq1/repo/dashboard/Home.py ]; then
  cd /opt/bq1/repo/dashboard && app=Home.py
else
  cd /opt/bq1/repo/streamlit && app=app.py   # old layout, kept as a fallback
fi
exec /opt/bq1/venv/bin/streamlit run "$app" --server.address 0.0.0.0 --server.port 8501 \
  --server.headless true --browser.gatherUsageStats false
