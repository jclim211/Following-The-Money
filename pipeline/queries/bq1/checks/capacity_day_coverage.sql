SELECT
    daily_capacity,
    COUNT(*) AS evaluation_rows,
    COUNT(DISTINCT profile_date) AS days_available,
    MIN(profile_date) AS first_date,
    MAX(profile_date) AS last_date
FROM aml_curated.capacity_evaluation
GROUP BY daily_capacity
ORDER BY daily_capacity
