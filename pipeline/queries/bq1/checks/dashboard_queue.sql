SELECT
    COUNT(*) AS queue_rows,
    COUNT(DISTINCT profile_date) AS days_evaluated,
    MIN(daily_rank) AS minimum_rank,
    MAX(daily_rank) AS maximum_rank,
    SUM(CASE WHEN account_day_is_laundering IS NULL THEN 1 ELSE 0 END) AS missing_labels,
    SUM(CASE WHEN account_country IS NULL OR account_country = '' THEN 1 ELSE 0 END) AS missing_countries
FROM aml_curated.bq1_dashboard_queue
