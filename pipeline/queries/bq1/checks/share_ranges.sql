SELECT
    SUM(CASE WHEN ach_share < 0 OR ach_share > 1 THEN 1 ELSE 0 END)
        AS invalid_ach_share,
    SUM(CASE WHEN cross_border_share < 0 OR cross_border_share > 1 THEN 1 ELSE 0 END)
        AS invalid_cross_border_share,
    SUM(CASE WHEN crypto_share < 0 OR crypto_share > 1 THEN 1 ELSE 0 END)
        AS invalid_crypto_share,
    SUM(CASE WHEN amount_band_share < 0 OR amount_band_share > 1 THEN 1 ELSE 0 END)
        AS invalid_amount_band_share,
    SUM(CASE WHEN pass_through_share_24h < 0 OR pass_through_share_24h > 1 THEN 1 ELSE 0 END)
        AS invalid_pass_through_share
FROM aml_curated.account_profiles
