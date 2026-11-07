SELECT FLOOR(r.risk_score / 2.5) * 2.5 AS score_bin,
               COALESCE(l.account_day_is_laundering, 0) AS is_laundering, COUNT(*) AS accounts
        FROM risk_rankings r
        LEFT JOIN account_labels l
          ON l.account_key = r.account_key AND l.profile_date = r.profile_date
        WHERE r.profile_date = '{profile_date}'
        GROUP BY 1, 2
