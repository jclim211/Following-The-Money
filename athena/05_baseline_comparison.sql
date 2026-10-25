-- X-factor evidence: our weighted score vs a simple baseline rule
-- ("flag the accounts with the most transactions that day").
WITH baseline AS (
  SELECT is_laundering_account,
         ROW_NUMBER() OVER (PARTITION BY txn_date ORDER BY n_txn DESC, account_key) AS base_rank,
         daily_rank
  FROM is459_aml.account_day_scores
),
totals AS (SELECT SUM(is_laundering_account) AS total FROM baseline),
limits AS (SELECT n FROM (VALUES 50, 100, 200, 500, 1000) AS t(n))
SELECT l.n AS daily_limit,
       ROUND(100.0 * SUM(CASE WHEN b.daily_rank <= l.n THEN b.is_laundering_account ELSE 0 END) / MAX(t.total), 1) AS our_score_recall_pct,
       ROUND(100.0 * SUM(CASE WHEN b.base_rank  <= l.n THEN b.is_laundering_account ELSE 0 END) / MAX(t.total), 1) AS baseline_recall_pct
FROM limits l
CROSS JOIN baseline b
CROSS JOIN totals t
GROUP BY l.n
ORDER BY l.n;
