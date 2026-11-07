SELECT COUNT(*) AS component_sum_mismatches
FROM aml_curated.risk_rankings
WHERE ach_points IS NULL
   OR cross_border_points IS NULL
   OR fan_out_points IS NULL
   OR fan_in_points IS NULL
   OR amount_band_points IS NULL
   OR pass_through_points IS NULL
   OR activity_spike_points IS NULL
   OR ABS(
        risk_score - ROUND(
            ach_points
          + cross_border_points
          + fan_out_points
          + fan_in_points
          + amount_band_points
          + pass_through_points
          + activity_spike_points,
            4
        )
      ) > 0.0001
