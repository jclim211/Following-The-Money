WITH r AS (
              SELECT profile_date, account_key, daily_rank,
                     ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY txn_count DESC, account_key) AS base_rank
              FROM risk_rankings WHERE profile_date IN ({date_list})),
            j AS (
              SELECT r.daily_rank, r.base_rank, l.account_day_is_laundering AS y
              FROM r JOIN account_labels l
                ON l.account_key = r.account_key AND l.profile_date = r.profile_date
              WHERE l.profile_date IN ({date_list}) AND (r.daily_rank <= 2000 OR r.base_rank <= 2000)),
            lim AS (SELECT n FROM UNNEST(SEQUENCE(50, 2000, 50)) AS t(n))
            SELECT lim.n AS daily_capacity,
                   SUM(CASE WHEN j.daily_rank <= lim.n THEN j.y ELSE 0 END) AS caught_score,
                   SUM(CASE WHEN j.base_rank  <= lim.n THEN j.y ELSE 0 END) AS caught_baseline
            FROM lim CROSS JOIN j GROUP BY lim.n ORDER BY lim.n
