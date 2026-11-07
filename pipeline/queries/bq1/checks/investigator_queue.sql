SELECT
    COUNT(*) AS queue_rows,
    COUNT(DISTINCT profile_date) AS days_evaluated,
    MIN(daily_rank) AS minimum_rank,
    MAX(daily_rank) AS maximum_rank
FROM aml_curated.bq1_investigator_queue
