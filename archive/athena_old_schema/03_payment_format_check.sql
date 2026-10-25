-- Use BEFORE finalising weights.json: which payment formats are riskier?
-- lift > 1 means the format is used more in laundering than average.
-- Put the clearly high-lift formats into "high_risk_payment_formats".
WITH overall AS (
  SELECT AVG(CAST(is_laundering AS DOUBLE)) AS base_rate
  FROM is459_aml.transactions
)
SELECT payment_format,
       COUNT(*)                                        AS n_transactions,
       SUM(is_laundering)                              AS n_laundering,
       ROUND(100.0 * AVG(CAST(is_laundering AS DOUBLE)), 3) AS laundering_rate_pct,
       ROUND(AVG(CAST(is_laundering AS DOUBLE)) / MAX(o.base_rate), 2) AS lift
FROM is459_aml.transactions
CROSS JOIN overall o
GROUP BY payment_format
ORDER BY lift DESC;
