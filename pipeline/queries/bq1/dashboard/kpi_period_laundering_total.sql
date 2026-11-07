SELECT SUM(account_day_is_laundering) AS t FROM account_labels WHERE profile_date IN ({date_list})
