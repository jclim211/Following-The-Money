SELECT
    profile_date,
    account_key,
    COUNT(*) AS rows_per_account_day
FROM aml_curated.account_profiles
GROUP BY profile_date, account_key
HAVING COUNT(*) > 1
LIMIT 20
