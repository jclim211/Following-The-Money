#!/bin/bash
# BQ1 dashboard bootstrap (Amazon Linux 2023)
set -euxo pipefail
dnf install -y python3.11 python3.11-pip git
mkdir -p /opt/bq1/app
cd /opt/bq1
python3.11 -m venv venv
aws s3 sync s3://is459-g7-projectbucket/scripts/dashboard/ /opt/bq1/app/ --region us-east-1
/opt/bq1/venv/bin/pip install --no-cache-dir -r /opt/bq1/app/requirements.txt

cat > /etc/systemd/system/bq1-dashboard.service <<'EOF'
[Unit]
Description=BQ1 Streamlit dashboard
After=network-online.target
[Service]
WorkingDirectory=/opt/bq1/app
Environment=BQ1_AWS_PROFILE=
Environment=BQ1_REGION=us-east-1
ExecStart=/opt/bq1/venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
Restart=always
[Install]
WantedBy=multi-user.target
EOF

# Auto update: pull new code every 2 minutes, restart only if something changed.
cat > /opt/bq1/update.sh <<'EOF'
#!/bin/bash
cd /opt/bq1/app
if [ -d .git ]; then
  before=$(git rev-parse HEAD); git pull -q --ff-only; after=$(git rev-parse HEAD)
  changed=$([ "$before" != "$after" ] && echo yes || true)
else
  out=$(aws s3 sync s3://is459-g7-projectbucket/scripts/dashboard/ /opt/bq1/app/ --region us-east-1 --exact-timestamps)
  changed=$([ -n "$out" ] && echo yes || true)
fi
if [ -n "$changed" ]; then
  /opt/bq1/venv/bin/pip install -q --no-cache-dir -r requirements.txt
  systemctl restart bq1-dashboard
fi
EOF
chmod +x /opt/bq1/update.sh

cat > /etc/systemd/system/bq1-update.service <<'EOF'
[Unit]
Description=Update BQ1 dashboard code
[Service]
Type=oneshot
ExecStart=/opt/bq1/update.sh
EOF
cat > /etc/systemd/system/bq1-update.timer <<'EOF'
[Unit]
Description=Check for BQ1 dashboard updates every 2 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now bq1-dashboard bq1-update.timer
