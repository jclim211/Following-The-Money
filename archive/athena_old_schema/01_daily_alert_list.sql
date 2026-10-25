-- BQ1 Output 1: Ranked alert list for ONE day.
-- Change the date and the daily limit (200) to match investigator capacity.
SELECT daily_rank,
       account_key,
       risk_score,
       fan_out, fan_in,
       ROUND(pass_through, 2)         AS pass_through,
       ROUND(cross_currency_share, 2) AS cross_currency_share,
       ROUND(cross_bank_share, 2)     AS cross_bank_share,
       ROUND(activity_spike, 2)       AS activity_spike,
       ROUND(payment_format_risk, 2)  AS payment_format_risk
FROM is459_aml.account_day_scores
WHERE txn_date = '2022-09-05'
  AND daily_rank <= 200
ORDER BY daily_rank;
