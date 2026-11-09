-- BQ1 re-weight check: does the queue find more laundering without fan-in and
-- amount band? Run by hand in Athena (aml_curated). Read-only.
--
-- indicator_validation.sql removes ONE behaviour at a time. This query removes
-- fan-in and amount band TOGETHER (plus two variants), and splits the 16 days
-- into two halves (1 to 8 Sep, 9 to 16 Sep) to check the result is not luck
-- in one period.
--
-- Result on HI-Medium (2026-11-07), laundering account-days caught:
--   half  reviews/day  all 7  without fan-in + amount band
--   h1    100          235    302   (+29%)
--   h2    100          322    395   (+23%)
--   both  100          557    697   (+25%)
--   both  600         1779   2067   (+16%)
--
-- This is a check on the same data the weights were scored on, not a test on
-- new data. The live weights in risk_scoring.py are NOT changed by this.
-- The IsLaundering label is used only to count catches, never to score.
--
-- Points per behaviour (from risk_rankings):
--   a = ACH, x = cross-border, fo = fan-out, fi = fan-in, b = amount band,
--   p = pass-through, sp = activity spike
WITH s AS (
    SELECT r.profile_date, r.account_key, r.daily_rank, r.total_amount_usd,
           r.ach_points AS a, r.cross_border_points AS x, r.fan_out_points AS fo,
           r.fan_in_points AS fi, r.amount_band_points AS b,
           r.pass_through_points AS p, r.activity_spike_points AS sp,
           COALESCE(l.account_day_is_laundering, 0) AS y,
           -- Split the 16 days into two halves
           CASE WHEN r.profile_date <= '2022-09-08' THEN 'h1' ELSE 'h2' END AS h
    FROM aml_curated.risk_rankings r
    LEFT JOIN aml_curated.account_labels l
      ON l.account_key = r.account_key AND l.profile_date = r.profile_date
), k AS (
    -- Re-rank every account each day with some behaviours left out of the sum.
    -- Same tie-break as the pipeline: higher amount first, then account key.
    SELECT h, y, daily_rank,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(a + x + fo + b + p + sp, 4) DESC, total_amount_usd DESC, account_key) AS no_fi,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(a + x + fo + p + sp, 4) DESC, total_amount_usd DESC, account_key) AS no_fi_band,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(a + x + fo + b + p, 4) DESC, total_amount_usd DESC, account_key) AS no_fi_spike,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(a + x + fo + p, 4) DESC, total_amount_usd DESC, account_key) AS core4
    FROM s
)
SELECT h AS half, n AS reviews_per_day,
    SUM(CASE WHEN daily_rank <= n THEN y ELSE 0 END) AS all_7,
    SUM(CASE WHEN no_fi <= n THEN y ELSE 0 END) AS without_fan_in,
    SUM(CASE WHEN no_fi_band <= n THEN y ELSE 0 END) AS without_fan_in_and_amount_band,
    SUM(CASE WHEN no_fi_spike <= n THEN y ELSE 0 END) AS without_fan_in_and_spike,
    SUM(CASE WHEN core4 <= n THEN y ELSE 0 END) AS ach_crossborder_fanout_passthrough_only
FROM k
CROSS JOIN UNNEST(ARRAY[100, 600]) AS t(n)
-- Only rows that could be in any top 600 matter; this keeps the scan small.
WHERE daily_rank <= 600 OR no_fi <= 600 OR no_fi_band <= 600 OR no_fi_spike <= 600 OR core4 <= 600
GROUP BY h, n
ORDER BY n, h;
