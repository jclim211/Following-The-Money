-- BQ1 indicator validation: drop-one-behaviour test. Run by hand in Athena
-- (aml_curated). Same logic as the "Which indicators matter" tab of the old
-- BQ1 page, archive/dashboard_pages/1_BQ1_Account_Risk.py.
--
-- For each of the 7 behaviours, re-rank every account each day WITHOUT that
-- behaviour's points and count the laundering account-days still caught in the
-- daily top 100. A large drop means the behaviour matters; catching MORE without
-- it means its weight could be lowered. "only_*" ranks by that one behaviour.
-- The IsLaundering label is used only to evaluate, never to score.
-- Change 100 (two places per behaviour) to test another daily capacity.
WITH s AS (
    SELECT r.profile_date, r.account_key, r.daily_rank, r.total_amount_usd,
           r.ach_points, r.cross_border_points, r.fan_out_points, r.fan_in_points, r.amount_band_points, r.pass_through_points, r.activity_spike_points,
           COALESCE(l.account_day_is_laundering, 0) AS y
    FROM aml_curated.risk_rankings r
    LEFT JOIN aml_curated.account_labels l
      ON l.account_key = r.account_key AND l.profile_date = r.profile_date
), t AS (
    SELECT s.*, s.ach_points + s.cross_border_points + s.fan_out_points + s.fan_in_points + s.amount_band_points + s.pass_through_points + s.activity_spike_points AS full_pts FROM s
), ranked AS (
    SELECT y, daily_rank,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - ach_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_ach_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(ach_points, 4) DESC, total_amount_usd DESC, account_key) AS only_ach_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - cross_border_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_cross_border_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(cross_border_points, 4) DESC, total_amount_usd DESC, account_key) AS only_cross_border_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - fan_out_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_fan_out_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(fan_out_points, 4) DESC, total_amount_usd DESC, account_key) AS only_fan_out_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - fan_in_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_fan_in_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(fan_in_points, 4) DESC, total_amount_usd DESC, account_key) AS only_fan_in_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - amount_band_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_amount_band_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(amount_band_points, 4) DESC, total_amount_usd DESC, account_key) AS only_amount_band_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - pass_through_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_pass_through_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(pass_through_points, 4) DESC, total_amount_usd DESC, account_key) AS only_pass_through_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(full_pts - activity_spike_points, 4) DESC, total_amount_usd DESC, account_key) AS wo_activity_spike_points,
        ROW_NUMBER() OVER (PARTITION BY profile_date ORDER BY ROUND(activity_spike_points, 4) DESC, total_amount_usd DESC, account_key) AS only_activity_spike_points
    FROM t
)
SELECT
    SUM(CASE WHEN daily_rank <= 100 THEN y ELSE 0 END) AS caught_all_7,
    SUM(CASE WHEN wo_ach_points <= 100 THEN y ELSE 0 END) AS without_ach,
    SUM(CASE WHEN only_ach_points <= 100 THEN y ELSE 0 END) AS only_ach,
    SUM(CASE WHEN wo_cross_border_points <= 100 THEN y ELSE 0 END) AS without_cross_border,
    SUM(CASE WHEN only_cross_border_points <= 100 THEN y ELSE 0 END) AS only_cross_border,
    SUM(CASE WHEN wo_fan_out_points <= 100 THEN y ELSE 0 END) AS without_fan_out,
    SUM(CASE WHEN only_fan_out_points <= 100 THEN y ELSE 0 END) AS only_fan_out,
    SUM(CASE WHEN wo_fan_in_points <= 100 THEN y ELSE 0 END) AS without_fan_in,
    SUM(CASE WHEN only_fan_in_points <= 100 THEN y ELSE 0 END) AS only_fan_in,
    SUM(CASE WHEN wo_amount_band_points <= 100 THEN y ELSE 0 END) AS without_amount_band,
    SUM(CASE WHEN only_amount_band_points <= 100 THEN y ELSE 0 END) AS only_amount_band,
    SUM(CASE WHEN wo_pass_through_points <= 100 THEN y ELSE 0 END) AS without_pass_through,
    SUM(CASE WHEN only_pass_through_points <= 100 THEN y ELSE 0 END) AS only_pass_through,
    SUM(CASE WHEN wo_activity_spike_points <= 100 THEN y ELSE 0 END) AS without_activity_spike,
    SUM(CASE WHEN only_activity_spike_points <= 100 THEN y ELSE 0 END) AS only_activity_spike
FROM ranked;
