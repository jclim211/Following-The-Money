SELECT account_key, COUNT(DISTINCT profile_date) AS prior_flag_days,
               MIN(profile_date) AS first_flagged
        FROM risk_rankings
        WHERE profile_date < '{profile_date}' AND daily_rank <= {top_n}
          AND account_key IN (SELECT account_key FROM risk_rankings
                              WHERE profile_date = '{profile_date}' AND daily_rank <= {top_n})
        GROUP BY account_key
