#!/bin/bash
# Installed on the EC2 server as /opt/bq1/update.sh and run every 2 minutes by bq1-update.timer.
# Pulls the latest main from GitHub; restarts Streamlit only if there is a new commit.
export HOME=/root
cd /opt/bq1/repo
before=$(git rev-parse HEAD)
git fetch -q origin main && git reset -q --hard origin/main
after=$(git rev-parse HEAD)
if [ "$before" != "$after" ]; then
  req=dashboard/requirements.txt; [ -f "$req" ] || req=streamlit/requirements.txt
  /opt/bq1/venv/bin/pip install -q --no-cache-dir -r "$req"
  systemctl restart bq1-dashboard
  logger -t bq1-update "deployed $after"
fi
