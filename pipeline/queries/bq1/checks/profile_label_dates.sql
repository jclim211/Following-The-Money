WITH profile_stats AS (
    SELECT
        COUNT(*) AS profile_rows,
        COUNT(DISTINCT profile_date) AS profile_dates,
        MIN(profile_date) AS first_date,
        MAX(profile_date) AS last_date
    FROM aml_curated.account_profiles
),
label_stats AS (
    SELECT
        COUNT(*) AS label_rows,
        COUNT(DISTINCT profile_date) AS label_dates,
        MIN(profile_date) AS first_date,
        MAX(profile_date) AS last_date
    FROM aml_curated.account_labels
)
SELECT *
FROM profile_stats
CROSS JOIN label_stats
