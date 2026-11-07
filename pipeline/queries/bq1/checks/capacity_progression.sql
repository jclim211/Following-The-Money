WITH ordered_capacity AS (
    SELECT
        profile_date,
        daily_capacity,
        accounts_reviewed,
        laundering_detected,
        detection_rate,
        cutoff_score,

        LAG(accounts_reviewed) OVER (
            PARTITION BY profile_date
            ORDER BY daily_capacity
        ) AS previous_reviewed,

        LAG(laundering_detected) OVER (
            PARTITION BY profile_date
            ORDER BY daily_capacity
        ) AS previous_detected,

        LAG(detection_rate) OVER (
            PARTITION BY profile_date
            ORDER BY daily_capacity
        ) AS previous_detection_rate,

        LAG(cutoff_score) OVER (
            PARTITION BY profile_date
            ORDER BY daily_capacity
        ) AS previous_cutoff

    FROM aml_curated.capacity_evaluation
)
SELECT COUNT(*) AS capacity_progression_errors
FROM ordered_capacity
WHERE previous_reviewed IS NOT NULL
  AND (
       accounts_reviewed < previous_reviewed
    OR laundering_detected < previous_detected
    OR detection_rate < previous_detection_rate
    OR cutoff_score > previous_cutoff
  )
