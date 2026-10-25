-- BQ1 Output 3: Weight validation.
-- (a) Do laundering accounts really score higher on each behaviour?
--     A behaviour whose laundering vs normal gap is small is a candidate
--     for a lower weight; a big gap supports a higher weight.
SELECT CASE WHEN is_laundering_account = 1 THEN 'laundering' ELSE 'normal' END AS account_type,
       COUNT(*) AS account_days,
       ROUND(AVG(fan_out_score), 3)              AS fan_out,
       ROUND(AVG(pass_through_score), 3)         AS pass_through,
       ROUND(AVG(fan_in_score), 3)               AS fan_in,
       ROUND(AVG(cross_currency_share_score), 3) AS cross_currency,
       ROUND(AVG(cross_bank_share_score), 3)     AS cross_bank,
       ROUND(AVG(activity_spike_score), 3)       AS activity_spike,
       ROUND(AVG(payment_format_risk_score), 3)  AS payment_format,
       ROUND(AVG(risk_score), 2)                 AS avg_risk_score
FROM is459_aml.account_day_scores
GROUP BY 1;

-- (b) Which weighted behaviours drive the alerts we caught?
--     Average points each behaviour contributed for true laundering
--     accounts inside the top 200 per day. Update weights if you edit weights.json.
SELECT ROUND(AVG(20 * fan_out_score), 2)              AS fan_out_pts,
       ROUND(AVG(20 * pass_through_score), 2)         AS pass_through_pts,
       ROUND(AVG(15 * fan_in_score), 2)               AS fan_in_pts,
       ROUND(AVG(15 * cross_currency_share_score), 2) AS cross_currency_pts,
       ROUND(AVG(10 * cross_bank_share_score), 2)     AS cross_bank_pts,
       ROUND(AVG(10 * activity_spike_score), 2)       AS activity_spike_pts,
       ROUND(AVG(10 * payment_format_risk_score), 2)  AS payment_format_pts
FROM is459_aml.account_day_scores
WHERE daily_rank <= 200 AND is_laundering_account = 1;
