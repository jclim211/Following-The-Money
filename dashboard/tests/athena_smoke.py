"""Run the new BQ1 dashboard queries on Athena and print time, data scanned and results.

Usage (from dashboard/, AWS profile is459 signed in):  python tests/athena_smoke.py
"""
import time, boto3
P = ["ach_points","cross_border_points","fan_out_points","fan_in_points","amount_band_points","pass_through_points","activity_spike_points"]
days = ", ".join(f"'2022-09-{d:02d}'" for d in range(1, 17)); N = 100
rank = ",\n".join(f"ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - {c}, 4) DESC, total_amount_usd DESC, account_key) AS wo_{c},\nROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND({c}, 4) DESC, total_amount_usd DESC, account_key) AS only_{c}" for c in P)
sums = ",\n".join(f"SUM(CASE WHEN wo_{c} <= {N} THEN y ELSE 0 END) AS wo_{c},\nSUM(CASE WHEN only_{c} <= {N} THEN y ELSE 0 END) AS only_{c}" for c in P)
QS = {
"prior": f"""SELECT account_key, COUNT(DISTINCT profile_date) AS prior_flag_days, MIN(profile_date) AS first_flagged
FROM risk_rankings WHERE profile_date < '2022-09-16' AND daily_rank <= {N}
AND account_key IN (SELECT account_key FROM risk_rankings WHERE profile_date = '2022-09-16' AND daily_rank <= {N}) GROUP BY account_key""",
"trend": f"""WITH q AS (SELECT r.profile_date, r.account_key, COALESCE(l.account_day_is_laundering, 0) AS y FROM risk_rankings r
LEFT JOIN account_labels l ON l.account_key = r.account_key AND l.profile_date = r.profile_date WHERE r.daily_rank <= {N}),
f AS (SELECT account_key, MIN(profile_date) AS first_day FROM q GROUP BY account_key)
SELECT q.profile_date, SUM(CASE WHEN q.profile_date = f.first_day THEN 1 ELSE 0 END) AS new_accounts,
SUM(CASE WHEN q.profile_date > f.first_day THEN 1 ELSE 0 END) AS repeat_accounts,
SUM(CASE WHEN q.profile_date = f.first_day THEN q.y ELSE 0 END) AS new_laundering,
SUM(CASE WHEN q.profile_date > f.first_day THEN q.y ELSE 0 END) AS repeat_laundering
FROM q JOIN f ON f.account_key = q.account_key GROUP BY q.profile_date ORDER BY q.profile_date""",
"curve": f"""WITH r AS (SELECT profile_date, account_key, daily_rank, ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY txn_count DESC, account_key) AS base_rank
FROM risk_rankings WHERE profile_date IN ({days})),
j AS (SELECT r.daily_rank, r.base_rank, l.account_day_is_laundering AS y FROM r JOIN account_labels l ON l.account_key = r.account_key AND l.profile_date = r.profile_date
WHERE l.profile_date IN ({days}) AND (r.daily_rank <= 2000 OR r.base_rank <= 2000)),
lim AS (SELECT n FROM UNNEST(SEQUENCE(50, 2000, 50)) AS t(n))
SELECT lim.n AS daily_capacity, SUM(CASE WHEN j.daily_rank <= lim.n THEN j.y ELSE 0 END) AS caught_score,
SUM(CASE WHEN j.base_rank <= lim.n THEN j.y ELSE 0 END) AS caught_baseline FROM lim CROSS JOIN j GROUP BY lim.n ORDER BY lim.n""",
"drop": f"""WITH s AS (SELECT r.profile_date, r.account_key, r.daily_rank, r.total_amount_usd, {', '.join('r.' + c for c in P)}, COALESCE(l.account_day_is_laundering, 0) AS y
FROM risk_rankings r LEFT JOIN account_labels l ON l.account_key = r.account_key AND l.profile_date = r.profile_date WHERE r.profile_date IN ({days})),
t AS (SELECT s.*, {' + '.join('s.' + c for c in P)} AS full_pts FROM s),
ranked AS (SELECT y, daily_rank, {rank} FROM t)
SELECT SUM(CASE WHEN daily_rank <= {N} THEN y ELSE 0 END) AS caught_all, {sums} FROM ranked""",
"page3": "SELECT COUNT(*) AS n, COUNT(DISTINCT profile_date) AS d, SUM(CASE WHEN account_country IS NULL THEN 1 ELSE 0 END) AS null_country FROM bq1_dashboard_queue",
}
a = boto3.Session(profile_name="is459", region_name="us-east-1").client("athena")
ids = {k: a.start_query_execution(QueryString=v, QueryExecutionContext={"Database": "aml_curated"}, WorkGroup="primary",
       ResultConfiguration={"OutputLocation": "s3://is459-g7-projectbucket/athena-results/streamlit/"})["QueryExecutionId"] for k, v in QS.items()}
done = {}
while len(done) < len(ids):
    for k, i in ids.items():
        if k in done: continue
        e = a.get_query_execution(QueryExecutionId=i)["QueryExecution"]
        if e["Status"]["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            done[k] = e
    time.sleep(2)
for k, e in done.items():
    st = e.get("Statistics", {})
    print(f"== {k}: {e['Status']['State']} {st.get('EngineExecutionTimeInMillis', 0)/1000:.1f}s "
          f"{st.get('DataScannedInBytes', 0)/1e6:.0f} MB {e['Status'].get('StateChangeReason', '')}")
    if e["Status"]["State"] == "SUCCEEDED":
        rows = a.get_query_results(QueryExecutionId=ids[k], MaxResults=50)["ResultSet"]["Rows"]
        for r in rows[:45]:
            print("   " + " | ".join(c.get("VarCharValue", "") for c in r["Data"]))
