-- Raw data per day: why cleaning keeps only 1 to 16 Sep. Run by hand in
-- Athena (aml_raw). Read-only.
--
-- clean.py rule 5 keeps days up to the last day with more than 10% of the
-- median daily volume (--tail-fraction 0.10). This query shows the raw volume
-- and laundering share per day, before cleaning.
--
-- Result on HI-Medium (2026-11-09):
--   1 to 16 Sep  31,891,251 transactions, 31,146 laundering (0.10%)
--   17 to 28 Sep      6,987 transactions,  4,084 laundering (58%)
-- Every day after 16 Sep is under 0.3% of the median day (814,252), so the
-- rule sets the cutoff at 2022-09-16 (also saved as cutoff_day in the clean
-- job's metrics). Keeping the tail would inflate daily top-N precision.
SELECT substr("timestamp", 1, 10) AS day,
       COUNT(*) AS transactions,
       SUM(CAST(is_laundering AS bigint)) AS laundering,
       ROUND(100.0 * SUM(CAST(is_laundering AS bigint)) / COUNT(*), 3) AS pct_laundering
FROM aml_raw.corrected_transactions
GROUP BY 1
ORDER BY 1;
