SELECT
    account_day_is_laundering,
    COUNT(*) AS account_days
FROM aml_curated.account_labels
GROUP BY account_day_is_laundering
ORDER BY account_day_is_laundering
