SELECT
    SUM(CASE
        WHEN accounts_reviewed <= 0
          OR accounts_reviewed > daily_capacity
        THEN 1 ELSE 0 END) AS invalid_review_counts,

    SUM(CASE
        WHEN laundering_detected < 0
          OR laundering_detected > accounts_reviewed
        THEN 1 ELSE 0 END) AS invalid_detected_counts,

    SUM(CASE
        WHEN total_laundering_account_days < laundering_detected
        THEN 1 ELSE 0 END) AS invalid_laundering_totals,

    SUM(CASE
        WHEN precision < 0 OR precision > 1
          OR detection_rate < 0 OR detection_rate > 1
        THEN 1 ELSE 0 END) AS invalid_rates,

    SUM(CASE
        WHEN cutoff_score IS NULL
          OR cutoff_score < 0 OR cutoff_score > 100
        THEN 1 ELSE 0 END) AS invalid_cutoffs
FROM aml_curated.capacity_evaluation
