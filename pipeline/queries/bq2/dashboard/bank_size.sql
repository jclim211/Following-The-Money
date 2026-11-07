WITH sb AS (SELECT from_bank AS bank_id FROM scheme_edges UNION SELECT to_bank FROM scheme_edges),
    acc AS (SELECT TRY_CAST("bank id" AS bigint) AS bank_num, COUNT(DISTINCT "account number") AS n_accounts
            FROM aml_raw.raw_accounts GROUP BY 1)
    SELECT sb.bank_id, b.bank_name, b.country, b.total_txns, a.n_accounts
    FROM sb
    LEFT JOIN aml_clean.banks b ON b.bank_id = sb.bank_id
    LEFT JOIN acc a ON a.bank_num = TRY_CAST(sb.bank_id AS bigint)
