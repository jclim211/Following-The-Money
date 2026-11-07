WITH t AS (SELECT r.account_key, r.daily_rank, r.total_amount_usd, r.activity_spike_points AS sp, r.ach_points + r.cross_border_points + r.fan_out_points + r.fan_in_points + r.amount_band_points + r.pass_through_points + r.activity_spike_points AS full_pts,
  COALESCE(l.account_day_is_laundering, 0) AS y FROM risk_rankings r LEFT JOIN account_labels l
  ON l.account_key = r.account_key AND l.profile_date = r.profile_date WHERE r.profile_date = '2022-09-01'),
r AS (SELECT y, daily_rank, sp,
  ROW_NUMBER() OVER (ORDER BY ROUND(full_pts - sp, 4) DESC, total_amount_usd DESC, account_key) AS wo_new,
  ROW_NUMBER() OVER (ORDER BY full_pts - sp DESC, account_key) AS wo_old FROM t)
SELECT MAX(ABS(sp)) AS max_spike_points,
  SUM(CASE WHEN daily_rank <= 100 THEN y ELSE 0 END) AS caught_all,
  SUM(CASE WHEN wo_new <= 100 THEN y ELSE 0 END) AS wo_spike_new,
  SUM(CASE WHEN wo_old <= 100 THEN y ELSE 0 END) AS wo_spike_old FROM r
