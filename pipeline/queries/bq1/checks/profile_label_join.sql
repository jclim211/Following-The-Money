SELECT
    COUNT(*) AS profile_rows,
    COUNT(l.account_key) AS matched_label_rows,
    SUM(CASE WHEN l.account_key IS NULL THEN 1 ELSE 0 END)
        AS unmatched_profile_rows
FROM aml_curated.account_profiles p
LEFT JOIN aml_curated.account_labels l
    ON p.profile_date = l.profile_date
    AND p.account_key = l.account_key
