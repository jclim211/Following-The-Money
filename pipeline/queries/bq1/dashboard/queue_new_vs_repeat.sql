WITH q AS (
              SELECT r.profile_date, r.account_key, COALESCE(l.account_day_is_laundering, 0) AS y
              FROM risk_rankings r
              LEFT JOIN account_labels l
                ON l.account_key = r.account_key AND l.profile_date = r.profile_date
              WHERE r.daily_rank <= {top_n}),
            f AS (SELECT account_key, MIN(profile_date) AS first_day FROM q GROUP BY account_key)
            SELECT q.profile_date,
                   SUM(CASE WHEN q.profile_date = f.first_day THEN 1 ELSE 0 END) AS new_accounts,
                   SUM(CASE WHEN q.profile_date > f.first_day THEN 1 ELSE 0 END) AS repeat_accounts,
                   SUM(CASE WHEN q.profile_date = f.first_day THEN q.y ELSE 0 END) AS new_laundering,
                   SUM(CASE WHEN q.profile_date > f.first_day THEN q.y ELSE 0 END) AS repeat_laundering
            FROM q JOIN f ON f.account_key = q.account_key
            GROUP BY q.profile_date ORDER BY q.profile_date
