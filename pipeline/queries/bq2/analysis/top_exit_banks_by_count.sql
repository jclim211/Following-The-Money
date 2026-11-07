SELECT bank_id, bank_name, country, exits, expected_exits, exit_ratio
FROM aml_bq2_curated.bank_entry_exit
WHERE exit_eligible ORDER BY exits DESC LIMIT {top_n}
