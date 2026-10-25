"""
IS459 Group 7 | BQ1 Dashboard (Streamlit on EC2)
Shows the daily ranked alert list, the capacity vs detection curve,
and which weighted behaviours drive the alerts.

Run on EC2 (same setup as the Week 5 lab):
  streamlit run bq1_dashboard.py --server.address 0.0.0.0 --server.port 8501
"""
import json
import time

import boto3
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------- settings
BUCKET = "<your-bucket-name>"          # EDIT
REGION = "us-east-1"                    # EDIT if your account uses another region
DATABASE = "is459_aml"
TABLE = "account_day_scores"
ATHENA_OUTPUT = f"s3://{BUCKET}/athena-results/streamlit/"
CONFIG_KEY = "config/weights.json"

BEHAVIOURS = ["fan_out", "pass_through", "fan_in", "cross_currency_share",
              "cross_bank_share", "activity_spike", "payment_format_risk"]

athena = boto3.client("athena", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


@st.cache_data(ttl=600, show_spinner=False)
def run_query(sql: str) -> pd.DataFrame:
    """Run a query in Athena and return the (small, aggregated) result."""
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )["QueryExecutionId"]

    while True:
        state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if state["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if state["State"] != "SUCCEEDED":
        raise RuntimeError(state.get("StateChangeReason", state["State"]))

    rows, token = [], None
    while True:
        kwargs = {"QueryExecutionId": qid}
        if token:
            kwargs["NextToken"] = token
        page = athena.get_query_results(**kwargs)
        rows.extend(page["ResultSet"]["Rows"])
        token = page.get("NextToken")
        if not token:
            break
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    data = [[c.get("VarCharValue") for c in r["Data"]] for r in rows[1:]]
    df = pd.DataFrame(data, columns=header)
    for col in df.columns:  # Athena returns text; turn numeric columns into numbers
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_weights() -> dict:
    body = s3.get_object(Bucket=BUCKET, Key=CONFIG_KEY)["Body"].read()
    return json.loads(body)["weights"]


# ---------------------------------------------------------------- layout
st.set_page_config(page_title="BQ1 Alert Prioritisation", layout="wide")
st.title("BQ1: Which accounts should investigators review first?")

days = run_query(f"SELECT DISTINCT txn_date FROM {TABLE} ORDER BY txn_date")["txn_date"].astype(str).tolist()
with st.sidebar:
    day = st.selectbox("Day", days, index=len(days) - 1)
    capacity = st.slider("Daily investigator capacity (alerts)", 25, 1000, 200, step=25)

# Metrics for the chosen day and capacity
m = run_query(f"""
    SELECT SUM(CASE WHEN daily_rank <= {capacity} THEN is_laundering_account ELSE 0 END) AS caught,
           SUM(is_laundering_account) AS total
    FROM {TABLE} WHERE txn_date = '{day}'""").iloc[0]
caught, total = int(m["caught"] or 0), int(m["total"] or 0)
c1, c2, c3 = st.columns(3)
c1.metric("Laundering accounts caught", f"{caught} of {total}")
c2.metric("Recall", f"{100 * caught / total:.1f}%" if total else "n/a")
c3.metric("Precision", f"{100 * caught / capacity:.1f}%")

# Capacity vs detection curve (all days)
st.subheader("Capacity vs detection curve")
curve = run_query(f"""
    WITH totals AS (SELECT SUM(is_laundering_account) AS t FROM {TABLE}),
         limits AS (SELECT n FROM UNNEST(SEQUENCE(25, 2000, 25)) AS x(n))
    SELECT l.n AS daily_limit,
           100.0 * SUM(s.is_laundering_account) / MAX(totals.t) AS recall_pct
    FROM limits l JOIN {TABLE} s ON s.daily_rank <= l.n CROSS JOIN totals
    GROUP BY l.n ORDER BY l.n""")
st.line_chart(curve.set_index("daily_limit")["recall_pct"])
st.caption("Recall = share of all laundering accounts that fall inside the daily limit. "
           "Look for where the curve flattens: extra alerts stop catching much more.")

# Which behaviours drive the flagged accounts
st.subheader("What drives today's alerts (average points out of 100)")
weights = load_weights()
avg_scores = run_query(f"""
    SELECT {", ".join(f"AVG({b}_score) AS {b}" for b in BEHAVIOURS)}
    FROM {TABLE} WHERE txn_date = '{day}' AND daily_rank <= {capacity}""").iloc[0]
points = pd.Series({b: float(avg_scores[b]) * weights[b] for b in BEHAVIOURS}, name="points")
st.bar_chart(points)

# Ranked alert list
st.subheader(f"Ranked alert list: top {capacity} accounts on {day}")
alerts = run_query(f"""
    SELECT daily_rank, account_key, risk_score, fan_out, fan_in,
           ROUND(pass_through, 2) AS pass_through,
           ROUND(cross_currency_share, 2) AS cross_currency,
           ROUND(cross_bank_share, 2) AS cross_bank,
           ROUND(activity_spike, 2) AS activity_spike
    FROM {TABLE}
    WHERE txn_date = '{day}' AND daily_rank <= {capacity}
    ORDER BY daily_rank""")
st.dataframe(alerts, use_container_width=True, hide_index=True)
