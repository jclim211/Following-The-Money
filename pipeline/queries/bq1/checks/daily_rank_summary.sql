SELECT profile_date, count(*) n, max(daily_rank) mr, max(risk_score) mx, min(risk_score) mn FROM risk_rankings GROUP BY 1 ORDER BY 1
