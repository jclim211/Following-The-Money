-- BQ1 data range check. Run by hand in Athena. Read-only.
--
-- The BQ1 queries (indicator_validation.sql, reweight_validation.sql) have no
-- date filter because the curated tables only hold the days that survived
-- cleaning. This shows that range.
--
-- Result on HI-Medium (2026-11-09): both tables 2022-09-01 to 2022-09-16,
-- 16 days, 14,887,977 account-days.
SELECT 'risk_rankings' AS table_name, MIN(profile_date) AS first_day, MAX(profile_date) AS last_day,
       COUNT(DISTINCT profile_date) AS days, COUNT(*) AS account_days
FROM aml_curated.risk_rankings
UNION ALL
SELECT 'account_labels', MIN(profile_date), MAX(profile_date),
       COUNT(DISTINCT profile_date), COUNT(*)
FROM aml_curated.account_labels;
