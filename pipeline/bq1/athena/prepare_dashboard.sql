-- BQ1 enriched dashboard preparation
-- Run section 1 once. Re-run it only after replacing the clean dataset.
-- If the external location already contains files, delete/repoint that prefix
-- before re-running the CTAS statement.

-- 1) Build a small account-to-country lookup from the account side of each
-- transaction. "Country" here is the account-side country, not an externally
-- verified bank-headquarters country.
CREATE TABLE aml_curated.account_country_lookup
WITH (
    format = 'PARQUET',
    external_location = 's3://is459-g7-projectbucket/curated/bq1/account_country_lookup/'
) AS
WITH account_country_legs AS (
    SELECT
        CAST(from_bank AS VARCHAR) AS bank_id,
        CAST(from_account AS VARCHAR) AS account_id,
        from_country AS account_country
    FROM aml_clean.transactions
    WHERE from_country IS NOT NULL

    UNION ALL

    SELECT
        CAST(to_bank AS VARCHAR) AS bank_id,
        CAST(to_account AS VARCHAR) AS account_id,
        to_country AS account_country
    FROM aml_clean.transactions
    WHERE to_country IS NOT NULL
), country_counts AS (
    SELECT
        bank_id,
        account_id,
        account_country,
        COUNT(*) AS appearances
    FROM account_country_legs
    GROUP BY bank_id, account_id, account_country
)
SELECT
    bank_id,
    account_id,
    CONCAT(bank_id, ':', account_id) AS account_key,
    MAX_BY(account_country, appearances) AS account_country
FROM country_counts
GROUP BY bank_id, account_id;


-- 2) Create the evaluation-enabled dashboard view. Scores and ranks already
-- exist before labels are joined, preventing the label from affecting ranking.
CREATE OR REPLACE VIEW aml_curated.bq1_dashboard_queue AS
SELECT
    r.profile_date,
    r.daily_rank,
    r.daily_active_accounts,
    r.bank_id,
    r.account_id,
    r.account_key,
    COALESCE(c.account_country, 'Unknown') AS account_country,
    r.risk_score,
    r.txn_count,
    r.total_amount_usd,
    r.ach_share,
    r.cross_border_share,
    r.fan_in,
    r.fan_out,
    r.amount_band_share,
    r.pass_through_share_24h,
    r.activity_spike_ratio,
    r.ach_points,
    r.cross_border_points,
    r.fan_out_points,
    r.fan_in_points,
    r.amount_band_points,
    r.pass_through_points,
    r.activity_spike_points,
    l.account_day_is_laundering
FROM aml_curated.risk_rankings r
LEFT JOIN aml_curated.account_labels l
    ON r.profile_date = l.profile_date
   AND r.account_key = l.account_key
LEFT JOIN aml_curated.account_country_lookup c
    ON r.account_key = c.account_key
WHERE r.daily_rank <= 1000;


-- 3) Validate the enriched output. Expected: 16,000 rows, 16 dates,
-- ranks 1-1,000, no missing labels and no missing country values.
SELECT
    COUNT(*) AS queue_rows,
    COUNT(DISTINCT profile_date) AS days_evaluated,
    MIN(daily_rank) AS minimum_rank,
    MAX(daily_rank) AS maximum_rank,
    SUM(CASE WHEN account_day_is_laundering IS NULL THEN 1 ELSE 0 END) AS missing_labels,
    SUM(CASE WHEN account_country IS NULL OR account_country = '' THEN 1 ELSE 0 END) AS missing_countries
FROM aml_curated.bq1_dashboard_queue;


-- 4) Export this query as data/bq1_investigator_queue.csv.
SELECT *
FROM aml_curated.bq1_dashboard_queue
ORDER BY profile_date, daily_rank;

