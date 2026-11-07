SELECT profile_date, count(*) n, sum(account_day_is_laundering) l FROM account_labels GROUP BY 1 ORDER BY 1
