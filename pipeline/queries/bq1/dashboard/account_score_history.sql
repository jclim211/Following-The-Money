SELECT r.profile_date, r.daily_rank, r.daily_active_accounts, r.risk_score,
                   r.ach_points, r.cross_border_points, r.fan_out_points, r.fan_in_points, r.amount_band_points, r.pass_through_points, r.activity_spike_points,
                   COALESCE(l.account_day_is_laundering, 0) AS is_laundering
            FROM risk_rankings r
            LEFT JOIN account_labels l
              ON l.account_key = r.account_key AND l.profile_date = r.profile_date
            WHERE r.account_key = '{account_key}'
            ORDER BY r.profile_date
