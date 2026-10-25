-- BQ1 Output 2: Capacity vs detection curve (all days combined).
-- recall    = share of all laundering accounts that appear in the top N each day
-- precision = share of the flagged accounts that really are laundering
WITH totals AS (
  SELECT SUM(is_laundering_account) AS total_laundering
  FROM is459_aml.account_day_scores
),
limits AS (
  SELECT n FROM (VALUES 25, 50, 100, 200, 500, 1000, 2000) AS t(n)
)
SELECT l.n                                              AS daily_limit,
       SUM(s.is_laundering_account)                     AS laundering_caught,
       ROUND(100.0 * SUM(s.is_laundering_account) / MAX(t.total_laundering), 1) AS recall_pct,
       ROUND(100.0 * SUM(s.is_laundering_account) / COUNT(*), 2)                AS precision_pct
FROM limits l
JOIN is459_aml.account_day_scores s ON s.daily_rank <= l.n
CROSS JOIN totals t
GROUP BY l.n
ORDER BY l.n;
