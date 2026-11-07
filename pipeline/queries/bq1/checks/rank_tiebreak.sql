WITH t AS (SELECT profile_date, account_key, daily_rank, total_amount_usd, ach_points + cross_border_points + fan_out_points + fan_in_points + amount_band_points + pass_through_points + activity_spike_points AS full_pts
  FROM risk_rankings WHERE profile_date IN ('2022-09-01', '2022-09-02', '2022-09-03', '2022-09-04', '2022-09-05', '2022-09-06', '2022-09-07', '2022-09-08', '2022-09-09', '2022-09-10', '2022-09-11', '2022-09-12', '2022-09-13', '2022-09-14', '2022-09-15', '2022-09-16')),
r AS (SELECT daily_rank,
  ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts, 4) DESC, total_amount_usd DESC, account_key) AS new_rank,
  ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY full_pts DESC, account_key) AS old_rank FROM t)
SELECT COUNT(*) AS rows_checked,
  SUM(CASE WHEN new_rank <> daily_rank THEN 1 ELSE 0 END) AS new_mismatch_all,
  SUM(CASE WHEN daily_rank <= 100 AND new_rank <> daily_rank THEN 1 ELSE 0 END) AS new_mismatch_top100,
  SUM(CASE WHEN old_rank <> daily_rank THEN 1 ELSE 0 END) AS old_mismatch_all,
  SUM(CASE WHEN daily_rank <= 100 AND old_rank <> daily_rank THEN 1 ELSE 0 END) AS old_mismatch_top100 FROM r
