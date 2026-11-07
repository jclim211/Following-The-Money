WITH daily_rank_checks AS (
    SELECT
        profile_date,
        COUNT(*) AS row_count,
        COUNT(DISTINCT daily_rank) AS distinct_rank_count,
        MIN(daily_rank) AS minimum_rank,
        MAX(daily_rank) AS maximum_rank
    FROM aml_curated.risk_rankings
    GROUP BY profile_date
)
SELECT *
FROM daily_rank_checks
WHERE row_count <> distinct_rank_count
   OR minimum_rank <> 1
   OR maximum_rank <> row_count
ORDER BY profile_date
