SELECT
    MIN(risk_score) AS minimum_score,
    MAX(risk_score) AS maximum_score,
    SUM(
        CASE
            WHEN risk_score IS NULL
              OR risk_score < 0
              OR risk_score > 100
            THEN 1
            ELSE 0
        END
    ) AS invalid_score_rows
FROM aml_curated.risk_rankings
