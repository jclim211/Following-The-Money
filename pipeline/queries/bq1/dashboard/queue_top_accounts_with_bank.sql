SELECT r.daily_rank, r.account_key, r.bank_id, b.bank_name, r.account_id, r.risk_score, r.txn_count,
               r.total_amount_usd, r.daily_active_accounts, r.ach_points, r.cross_border_points, r.fan_out_points, r.fan_in_points, r.amount_band_points, r.pass_through_points, r.activity_spike_points,
               COALESCE(l.account_day_is_laundering, 0) AS is_laundering
        FROM risk_rankings r
        LEFT JOIN account_labels l
          ON l.account_key = r.account_key AND l.profile_date = r.profile_date
        LEFT JOIN aml_clean.banks b ON b.bank_id = r.bank_id
        WHERE r.profile_date = '{profile_date}' AND r.daily_rank <= {top_n}
        ORDER BY r.daily_rank
