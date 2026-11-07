SELECT *
FROM aml_curated.bq1_investigator_queue
WHERE profile_date = (
    SELECT MAX(profile_date)
    FROM aml_curated.bq1_investigator_queue
)
ORDER BY daily_rank
