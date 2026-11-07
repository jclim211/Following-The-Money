SELECT bank_id, bank_name, country, entries, expected_entries, entry_ratio
FROM aml_bq2_curated.bank_entry_exit
WHERE entry_eligible ORDER BY entry_ratio DESC LIMIT {top_n}
