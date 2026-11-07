SELECT COUNT(*) AS cutoff_mismatches
FROM aml_curated.capacity_evaluation c
JOIN aml_curated.risk_rankings r
    ON c.profile_date = r.profile_date
   AND r.daily_rank = c.daily_capacity
WHERE ABS(c.cutoff_score - r.risk_score) > 0.0001
