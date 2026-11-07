SELECT
    (SELECT COUNT(*) 
     FROM aml_curated.account_profiles) AS profile_rows,

    (SELECT COUNT(*) 
     FROM aml_curated.risk_rankings) AS ranking_rows
