SELECT CAST(MIN(day) AS varchar) AS first_day, CAST(MAX(day) AS varchar) AS last_day FROM {db}.transactions
